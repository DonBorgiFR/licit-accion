"""El Lanzador y Despertador — Capa 10, Paso 2: healthcheck de arranque en frío.

Este módulo contiene la comprobación previa del ecosistema y **la función única que decide
si hay escritorio**. Su contrato vive en `.agents/CONTRATO_CAPA_10.md`, validado el
2026-08-13, y conviene leerlo antes de tocar nada de aquí.

Tres decisiones de diseño gobiernan el fichero y no son estilísticas:

1. **`es_sesion_interactiva()` es el punto único de decisión**, y ante la duda contesta
   `False`. Toda llamada a interfaz gráfica de la capa —el diálogo de error de aquí y la
   apertura del navegador del Paso 7— pasa por ella. El riesgo es asimétrico: equivocarse
   hacia "sí hay escritorio" deja un diálogo esperando para siempre en la Session 0 de la
   tarea nocturna, invisible y sin que el proceso termine nunca; equivocarse hacia "no hay"
   sólo pierde el diálogo, y quedan el registro y el código de salida. Ante un empate
   técnico se elige el error recuperable.

2. **`ejecutar_healthcheck()` no modifica nada, ni siquiera el registro.** El contrato
   declara la comprobación como operación de sólo lectura, y hay una trampa concreta:
   instanciar `Memoria()` **crea el directorio de datos** (reparación de H-24), y escribir
   en `pipeline.jsonl` también. Por eso la comprobación es pura y devuelve un diagnóstico;
   emitir el evento es cosa del llamador, con `registrar_evento_lanzador()`. Crear cosas es
   competencia del estado `ARRANCANDO`, no de `COMPROBANDO`.

3. **Una base inexistente no es un fallo**, es una instalación nueva. Se informa de que se
   creará al arrancar. Confundir "no está" con "está roto" es exactamente el diagnóstico
   confuso que esta capa existe para evitar (H-24: un clon limpio no podía arrancar, y el
   síntoma no decía por qué).

La configuración —puerto, host, rutas, topes— **llega inyectada**, no se lee aquí: el
fichero `config/lanzador.yaml` y su lector estricto son el Paso 3. Así el healthcheck se
puede ejercitar sin fichero (Convención C4) y ningún paso queda a medias.
"""

import json
import os
import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Tuple

from src import PROJECT_ROOT, ruta_datos, ruta_proyecto

# ==============================================================================
# Códigos de salida (contrato, sección "Códigos de salida")
# ==============================================================================
#
# El código de salida es información, no un formalismo: el Programador de tareas de Windows
# lo registra, y es la única señal que verá quien revise por qué una noche no se prospectó.

EXITO = 0
#: Reservado a lo que el contrato no previó. Todo lo anticipado tiene su número propio, así
#: que un `1` es en sí mismo la noticia de que ocurrió algo no contemplado.
ERROR_NO_PREVISTO = 1
HEALTHCHECK_INSATISFACTORIO = 10
CONFIGURACION_INVALIDA = 11
PUERTO_OCUPADO_AJENO = 20
SERVIDOR_NO_RESPONDE = 21
#: No es un fallo —el sistema está protegiendo un proceso destructivo—, pero tampoco puede
#: ser 0: el Programador registraría una noche sana en la que no se prospectó nada.
PIPELINE_OMITIDO = 30
PIPELINE_FALLIDO = 31
APAGADO_INCOMPLETO = 40


# ==============================================================================
# Errores tipados
# ==============================================================================

class ErrorLanzador(Exception):
    """Base de los errores del Lanzador. Cada uno transporta su código de salida."""

    codigo_salida = ERROR_NO_PREVISTO


class ConfiguracionLanzadorInvalida(ErrorLanzador):
    """`config/lanzador.yaml` ausente, ilegible o incoherente. No se arranca con valores
    por defecto: misma doctrina que `src/retencion.py` y misma lección que H-18."""

    codigo_salida = CONFIGURACION_INVALIDA


class HealthcheckInsatisfactorio(ErrorLanzador):
    """Falta una dependencia crítica del entorno. Arrancar igual sería cambiar un
    diagnóstico preciso por un fallo confuso diez segundos después."""

    codigo_salida = HEALTHCHECK_INSATISFACTORIO


class PuertoOcupadoPorTercero(ErrorLanzador):
    """El puerto responde, pero no es nuestra API. Ni pelearse por él ni elegir otro en
    silencio: detenerse y decirlo."""

    codigo_salida = PUERTO_OCUPADO_AJENO


class ServidorNoRespondio(ErrorLanzador):
    """`/health` no contestó dentro del tope declarado."""

    codigo_salida = SERVIDOR_NO_RESPONDE


class CerrojoTomadoPorProcesoVivo(ErrorLanzador):
    """Otra corrida está en marcha. Desde la Capa 9 el pipeline borra ficheros del disco:
    dos corridas simultáneas no son un desperdicio, son dos procesos destruyendo peso
    documental a la vez."""

    codigo_salida = PIPELINE_OMITIDO


class ApagadoIncompleto(ErrorLanzador):
    """Agotados los tres niveles de apagado, el proceso sigue vivo."""

    codigo_salida = APAGADO_INCOMPLETO


# ==============================================================================
# La invariante central: ninguna llamada gráfica sin comprobar la sesión
# ==============================================================================

#: Versión mínima de Python. El proyecto usa anotaciones y `dataclasses` modernas; por
#: debajo de esto el fallo no sería un diagnóstico sino un `SyntaxError` sin contexto.
PYTHON_MINIMO: Tuple[int, int] = (3, 10)


def es_sesion_interactiva() -> bool:
    """¿Hay un escritorio donde mostrar algo? **Punto único de decisión de la capa.**

    Decide consultando el **identificador de sesión del proceso**, que es un hecho del
    sistema operativo, y nunca el modo de invocación, que es una intención declarada y
    puede llegar equivocada —por un defecto, por un acceso directo mal cableado o porque
    alguien registró la tarea programada con el modo que no era—.

    La Session 0 es la de los servicios: existe sin escritorio interactivo, y es donde
    corre una tarea programada marcada con *"ejecutar tanto si el usuario ha iniciado
    sesión como si no"*. Un diálogo allí espera para siempre a un usuario que no existe.

    **Ante cualquier duda devuelve `False`**, por la asimetría del daño explicada en la
    cabecera del módulo: un diálogo de más cuelga el proceso; un diálogo de menos deja
    intactos el registro y el código de salida.
    """
    try:
        import ctypes

        identificador = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.ProcessIdToSessionId(  # type: ignore[attr-defined]
            os.getpid(), ctypes.byref(identificador)
        )
        if not ok:
            return False
        return identificador.value != 0
    except Exception:
        # No es Windows, o no se pudo consultar. Se asume que no hay escritorio: es el
        # lado seguro del error. (C2: el estado resultante es distinguible y el llamador
        # registra la omisión con `LANZADOR_GUI_OMITIDA`.)
        return False


def avisar_fallo_fatal(titulo: str, mensaje: str) -> bool:
    """Único canal gráfico de error de la capa. Devuelve si llegó a mostrarse.

    Se usa **sólo** para fallos anteriores a que FastAPI sirva el Cockpit, porque hasta
    entonces no existe la pantalla donde avisar: sin esto, quien hace doble clic no ve
    absolutamente nada y concluye que el botón está roto.

    Se usa `MessageBoxW` de `user32` y no `tkinter` a propósito: `tkinter` es una
    dependencia más y puede fallar por su cuenta justo sin escritorio, que es el caso que
    hay que cubrir sin equivocarse.
    """
    if not es_sesion_interactiva():
        return False
    try:
        import ctypes

        MB_ICONERROR = 0x10
        MB_SETFOREGROUND = 0x10000
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            None, mensaje, titulo, MB_ICONERROR | MB_SETFOREGROUND
        )
        return True
    except Exception:
        # Que falle el aviso no puede tumbar al proceso que intentaba avisar: el llamador
        # conserva el registro y el código de salida, que son los canales que no dependen
        # de que haya escritorio.
        return False


# ==============================================================================
# Estado del puerto
# ==============================================================================

class EstadoPuerto(str, Enum):
    """Los tres estados del puerto, que es donde se equivocan estos lanzadores."""

    LIBRE = "LIBRE"
    #: Responde y es nuestra API. Se reutiliza y **no se apaga al terminar**.
    NUESTRA_API = "NUESTRA_API"
    #: Escucha algo que no es nuestro. Detenerse.
    AJENO = "AJENO"


#: Campos que sólo tiene la respuesta de nuestro `/api/v1/health`. Se comprueba la **forma**
#: y no el código de estado: nuestra API degradada contesta 503 y **sigue siendo nuestra**,
#: mientras que cualquier servicio ajeno puede devolver un 200 alegremente.
CAMPOS_HEALTH_PROPIO = frozenset({"db_path", "wal_mode_active", "query_test_ok"})


def estado_del_puerto(host: str, puerto: int, timeout: float = 2.0) -> Tuple[EstadoPuerto, Optional[str]]:
    """Distingue libre / nuestra API / ajeno. Devuelve el estado y un detalle legible.

    Reutilizar es más seguro que arrancar: un lanzador que arranca a ciegas acaba dejando
    instancias duplicadas que se pisan en la misma base.
    """
    if not _hay_algo_escuchando(host, puerto, timeout):
        return EstadoPuerto.LIBRE, None

    try:
        import urllib.request

        url = f"http://{host}:{puerto}/api/v1/health"
        peticion = urllib.request.Request(url, headers={"User-Agent": "lanzador-incoop"})
        try:
            with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
                cuerpo = respuesta.read()
        except Exception as e_http:
            # Un 503 llega aquí como HTTPError y **sí trae cuerpo**: nuestra API degradada
            # sigue siendo nuestra, así que se inspecciona igual antes de darla por ajena.
            cuerpo = getattr(e_http, "read", lambda: b"")()
            if not cuerpo:
                return EstadoPuerto.AJENO, f"el puerto {puerto} responde pero no como nuestra API ({e_http})"

        datos = json.loads(cuerpo.decode("utf-8"))
        if isinstance(datos, dict) and CAMPOS_HEALTH_PROPIO.issubset(datos.keys()):
            estado = datos.get("status", "?")
            return EstadoPuerto.NUESTRA_API, f"API propia viva en {host}:{puerto} (status={estado})"
        return EstadoPuerto.AJENO, f"el puerto {puerto} responde JSON, pero no es nuestro /health"
    except Exception as e:
        return EstadoPuerto.AJENO, f"el puerto {puerto} está ocupado por otro proceso ({type(e).__name__})"


def _hay_algo_escuchando(host: str, puerto: int, timeout: float) -> bool:
    destino = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        with socket.create_connection((destino, puerto), timeout=timeout):
            return True
    except OSError:
        return False


# ==============================================================================
# Diagnóstico de arranque en frío
# ==============================================================================

@dataclass
class Comprobacion:
    """Una comprobación del healthcheck.

    `remedio` no es decorativo: el arranque en frío es **el momento en que más falta hace
    un diagnóstico claro y el único en que no hay nadie experto delante**. Decir qué falla
    sin decir cómo resolverlo deja a la persona igual de atascada.
    """

    nombre: str
    ok: bool
    detalle: str
    remedio: Optional[str] = None
    #: Una comprobación informativa no impide arrancar (p. ej. "la base no existe todavía").
    critica: bool = True


@dataclass
class DiagnosticoArranque:
    comprobaciones: List[Comprobacion] = field(default_factory=list)
    estado_puerto: Optional[EstadoPuerto] = None

    @property
    def fallos(self) -> List[Comprobacion]:
        return [c for c in self.comprobaciones if not c.ok and c.critica]

    @property
    def satisfactorio(self) -> bool:
        return not self.fallos

    @property
    def avisos(self) -> List[Comprobacion]:
        return [c for c in self.comprobaciones if not c.ok and not c.critica]

    def resumen(self) -> str:
        """Texto legible para el diálogo nativo, el registro y la consola."""
        if self.satisfactorio:
            lineas = ["Comprobación de arranque satisfactoria."]
            for aviso in self.avisos:
                lineas.append(f"  · {aviso.nombre}: {aviso.detalle}")
            return "\n".join(lineas)

        lineas = ["No se puede arrancar el Ecosistema de Licitaciones.", ""]
        for fallo in self.fallos:
            lineas.append(f"✖ {fallo.nombre}: {fallo.detalle}")
            if fallo.remedio:
                lineas.append(f"  Cómo resolverlo: {fallo.remedio}")
        return "\n".join(lineas)


def ejecutar_healthcheck(
    host: str,
    puerto: int,
    ruta_bundle: Optional[str] = None,
    espacio_minimo_mb: int = 200,
    db_path: Optional[str] = None,
    timeout_puerto: float = 2.0,
) -> DiagnosticoArranque:
    """Comprobación previa del ecosistema. **No modifica nada.**

    La configuración llega inyectada porque `config/lanzador.yaml` y su lector estricto son
    el Paso 3; así esto se puede ejercitar sin fichero (Convención C4).
    """
    diagnostico = DiagnosticoArranque()
    añadir = diagnostico.comprobaciones.append

    añadir(_comprobar_python())
    añadir(_comprobar_dependencias())
    añadir(_comprobar_configuracion_existente())
    añadir(_comprobar_base_de_datos(db_path))
    añadir(_comprobar_espacio(espacio_minimo_mb, db_path))
    añadir(_comprobar_bundle(ruta_bundle))

    comprobacion_puerto, estado = _comprobar_puerto(host, puerto, timeout_puerto)
    añadir(comprobacion_puerto)
    diagnostico.estado_puerto = estado

    return diagnostico


def _comprobar_python() -> Comprobacion:
    actual = sys.version_info[:2]
    if actual >= PYTHON_MINIMO:
        return Comprobacion(
            "Intérprete de Python", True,
            f"Python {actual[0]}.{actual[1]} en {sys.executable}",
        )
    return Comprobacion(
        "Intérprete de Python", False,
        f"Python {actual[0]}.{actual[1]}, se necesita {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} o superior",
        remedio="Instalar una versión de Python igual o posterior a la indicada desde python.org.",
    )


#: Sólo lo que impide arrancar. `pytesseract` y `langdetect` no están: su ausencia degrada
#: el OCR y la detección de idioma, que es un modo degradado ya contemplado por la Capa 4,
#: no un impedimento para levantar el sistema (Regla 5).
DEPENDENCIAS_CRITICAS = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn[standard]"),
    ("pydantic", "pydantic"),
    ("yaml", "pyyaml"),
    ("requests", "requests"),
    ("feedparser", "feedparser"),
    ("fitz", "PyMuPDF"),
    ("bs4", "beautifulsoup4"),
)


def _comprobar_dependencias() -> Comprobacion:
    import importlib.util

    ausentes = [
        paquete for modulo, paquete in DEPENDENCIAS_CRITICAS
        if importlib.util.find_spec(modulo) is None
    ]
    if not ausentes:
        return Comprobacion(
            "Dependencias", True,
            f"las {len(DEPENDENCIAS_CRITICAS)} dependencias críticas están disponibles",
        )
    return Comprobacion(
        "Dependencias", False,
        f"faltan {len(ausentes)}: {', '.join(ausentes)}",
        remedio="Ejecutar «pip install -r requirements.txt» desde la raíz del proyecto.",
    )


#: Ficheros de configuración sin los cuales el pipeline decide distinto en silencio. Es la
#: lección de H-18: sin `perfil_incoop.yaml` el perfil comercial se cargaba vacío y la misma
#: licitación puntuaba 71 desde la raíz y 47 desde otra carpeta, con el umbral en 65.
CONFIGURACION_CRITICA = ("perfil_incoop.yaml", "fuentes.yaml", "retencion.yaml")


def _comprobar_configuracion_existente() -> Comprobacion:
    ausentes = [
        nombre for nombre in CONFIGURACION_CRITICA
        if not os.path.isfile(ruta_proyecto(os.path.join("config", nombre)))
    ]
    if not ausentes:
        return Comprobacion(
            "Ficheros de configuración", True,
            f"{len(CONFIGURACION_CRITICA)} ficheros presentes en config/",
        )
    return Comprobacion(
        "Ficheros de configuración", False,
        f"faltan en config/: {', '.join(ausentes)}",
        remedio="Recuperarlos del repositorio; sin ellos el sistema puntuaría con criterios que nadie ha declarado.",
    )


def _ruta_base(db_path: Optional[str]) -> str:
    return db_path or ruta_datos("licitaciones.db")


def _comprobar_base_de_datos(db_path: Optional[str]) -> Comprobacion:
    """Lee la versión de esquema **sin instanciar `Memoria`**, que crearía el directorio.

    Una base inexistente es una instalación nueva, no una avería: se informa y no se
    bloquea el arranque.
    """
    from src.memoria import ESQUEMA_VERSION_ACTUAL

    ruta = _ruta_base(db_path)
    if not os.path.exists(ruta):
        return Comprobacion(
            "Base de datos", False,
            f"no existe todavía en {ruta}; se creará en esquema v{ESQUEMA_VERSION_ACTUAL} al arrancar",
            critica=False,
        )
    try:
        # `mode=ro` garantiza que la comprobación no puede escribir ni crear nada, ni
        # siquiera los ficheros auxiliares del WAL.
        uri = f"file:{ruta}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conexion:
            fila = conexion.execute("SELECT MAX(version) FROM metadata").fetchone()
        version = fila[0] if fila else None
    except Exception as e:
        return Comprobacion(
            "Base de datos", False,
            f"existe en {ruta} pero no se pudo leer su esquema ({type(e).__name__}: {e})",
            remedio="Comprobar que el fichero no está corrupto ni abierto en exclusiva por otro programa.",
        )

    if version == ESQUEMA_VERSION_ACTUAL:
        return Comprobacion("Base de datos", True, f"esquema v{version}, al día")
    return Comprobacion(
        "Base de datos", True,
        f"esquema v{version}; se migrará a v{ESQUEMA_VERSION_ACTUAL} al arrancar",
    )


def _comprobar_espacio(minimo_mb: int, db_path: Optional[str]) -> Comprobacion:
    """El pipeline descarga pliegos y crea copias antes de purgar. Sin margen, la copia
    previa falla y —por la Regla 5 de la Capa 9— la purga no se ejecuta: el disco lleno se
    manifestaría como un sistema que deja de limpiarse, que es lo contrario de lo obvio."""
    objetivo = os.path.dirname(_ruta_base(db_path)) or str(PROJECT_ROOT)
    while objetivo and not os.path.isdir(objetivo):
        padre = os.path.dirname(objetivo)
        if padre == objetivo:
            break
        objetivo = padre
    try:
        libres_mb = shutil.disk_usage(objetivo).free // (1024 * 1024)
    except Exception as e:
        return Comprobacion(
            "Espacio en disco", False,
            f"no se pudo medir el espacio libre en {objetivo} ({type(e).__name__})",
            remedio="Comprobar que la unidad de destino está accesible.",
        )
    if libres_mb >= minimo_mb:
        return Comprobacion("Espacio en disco", True, f"{libres_mb} MB libres")
    return Comprobacion(
        "Espacio en disco", False,
        f"sólo {libres_mb} MB libres, se necesitan al menos {minimo_mb} MB",
        remedio="Liberar espacio, o purgar peso documental desde la pantalla de Administración del Cockpit.",
    )


def _comprobar_bundle(ruta_bundle: Optional[str]) -> Comprobacion:
    """Sin `frontend/dist/index.html` no hay Cockpit que servir. Es el primer síntoma que
    verá quien clone el repositorio sin compilar, y merece decirlo con precisión en vez de
    un 404 desnudo."""
    ruta = ruta_bundle or ruta_proyecto(os.path.join("frontend", "dist"))
    indice = os.path.join(ruta, "index.html")
    if os.path.isfile(indice):
        return Comprobacion("Cockpit compilado", True, f"bundle presente en {ruta}")
    return Comprobacion(
        "Cockpit compilado", False,
        f"no se encontró {indice}",
        remedio="Ejecutar «npm install && npm run build» dentro de frontend/. "
                "Node.js hace falta para compilar, no para usar el sistema.",
    )


def _comprobar_puerto(host: str, puerto: int, timeout: float) -> Tuple[Comprobacion, EstadoPuerto]:
    estado, detalle = estado_del_puerto(host, puerto, timeout)
    if estado is EstadoPuerto.LIBRE:
        return Comprobacion("Puerto", True, f"{host}:{puerto} libre, se arrancará servidor propio"), estado
    if estado is EstadoPuerto.NUESTRA_API:
        return Comprobacion("Puerto", True, detalle or "API propia viva; se reutilizará"), estado
    return (
        Comprobacion(
            "Puerto", False,
            detalle or f"el puerto {puerto} está ocupado por otro proceso",
            remedio=f"Cerrar el programa que ocupa el puerto {puerto}, o cambiar el puerto en config/lanzador.yaml.",
        ),
        estado,
    )


# ==============================================================================
# Registro (Regla 3)
# ==============================================================================

def registrar_evento_lanzador(
    accion: str,
    motivo: Optional[str] = None,
    run_id: int = 0,
    db_path: Optional[str] = None,
) -> None:
    """Escribe un evento `LANZADOR_*` en `data/pipeline.jsonl`.

    Deliberadamente **fuera** de `ejecutar_healthcheck()`: escribir el registro crea el
    directorio de datos, y la comprobación debe poder ejecutarse sin efectos. Quien decide
    dejar rastro es el llamador.

    `run_id=0` es el valor reservado por el contrato para "evento del lanzador fuera de una
    corrida", porque estos eventos ocurren antes de que exista una ejecución de pipeline.
    """
    ruta = _ruta_base(db_path)
    directorio = os.path.dirname(ruta) or ruta_datos()
    try:
        os.makedirs(directorio, exist_ok=True)
        entrada = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": run_id,
            "action": accion,
            "updated_by": "lanzador",
        }
        if motivo:
            entrada["reason"] = motivo
        with open(os.path.join(directorio, "pipeline.jsonl"), "a", encoding="utf-8") as fichero:
            fichero.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except Exception as e:
        # Sin registro quedan el código de salida y la consola. Se avisa por stderr en vez
        # de silenciar (C2): que falle la auditoría no puede tumbar el arranque, pero
        # tampoco puede pasar desapercibido.
        print(f"[!] No se pudo registrar el evento {accion}: {e}", file=sys.stderr)


def comunicar_fallo_fatal(diagnostico: DiagnosticoArranque, titulo: str = "Ecosistema de Licitaciones") -> int:
    """Comunica un fallo anterior a que exista el Cockpit y devuelve el código de salida.

    Aplica la tabla de canales del contrato: **con escritorio**, diálogo nativo; **sin
    escritorio** —Session 0—, jamás, porque el proceso quedaría colgado esperando a un
    usuario inexistente. En ambos casos, registro y código de salida.

    Que se omitiera el diálogo se registra con `LANZADOR_GUI_OMITIDA`: sin esa huella, "no
    salió ningún diálogo en Session 0" es indistinguible de "no hubo ningún fallo del que
    avisar".
    """
    resumen = diagnostico.resumen()
    print(resumen, file=sys.stderr)
    registrar_evento_lanzador("LANZADOR_HEALTHCHECK_FALLIDO", motivo=resumen.replace("\n", " | "))

    if not avisar_fallo_fatal(titulo, resumen):
        registrar_evento_lanzador(
            "LANZADOR_GUI_OMITIDA",
            motivo="sin sesión interactiva: el aviso viaja por código de salida y registro",
        )

    if diagnostico.estado_puerto is EstadoPuerto.AJENO:
        return PUERTO_OCUPADO_AJENO
    return HEALTHCHECK_INSATISFACTORIO
