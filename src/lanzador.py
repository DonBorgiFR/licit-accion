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
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import yaml

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
# Configuración versionada (Regla 4) — Capa 10, Paso 3
# ==============================================================================
#
# Ningún plazo ni puerto inventado. Este lector **no aplica valores por defecto**: si el
# fichero falta, no se puede leer o declara algo incoherente, lanza
# `ConfiguracionLanzadorInvalida` y el lanzador no arranca. Misma doctrina que
# `src/retencion.py`, y por la misma razón (H-18).

NOMBRE_FICHERO_CONFIG = "lanzador.yaml"

#: `HH:MM` en 24 h. Se valida con expresión regular **y** con rangos, porque `"25:70"`
#: encaja en un patrón laxo y no es una hora.
PATRON_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class ConfiguracionServidor:
    host: str
    puerto: int
    espera_api_segundos: int
    espacio_minimo_mb: int


@dataclass(frozen=True)
class ConfiguracionCockpit:
    ruta_bundle: str
    abrir_navegador: bool


@dataclass(frozen=True)
class ConfiguracionApagado:
    gracia_endpoint_segundos: int
    gracia_senal_segundos: int


@dataclass(frozen=True)
class ConfiguracionDespertador:
    hora: str
    ejecutar_si_se_perdio: bool


@dataclass(frozen=True)
class ConfiguracionLanzador:
    """Parámetros de arranque vigentes y la versión bajo la que se ejecutó.

    Inmutable a propósito, igual que `PoliticaRetencion`: se lee una vez y no puede
    alterarse a mitad de un arranque, de modo que lo registrado y lo realmente hecho
    siempre concuerdan.

    **Ningún bloque es opcional.** Es la diferencia con `retencion.yaml`, donde un bloque
    ausente significa "no ejecutes esa operación" —una degradación segura para algo
    irreversible—. Aquí no hay equivalente: un lanzador sin puerto no puede hacer la mitad
    de su trabajo, simplemente no puede arrancar.
    """

    version: str
    servidor: ConfiguracionServidor
    cockpit: ConfiguracionCockpit
    apagado: ConfiguracionApagado
    despertador: ConfiguracionDespertador

    def ruta_bundle_absoluta(self) -> str:
        """Ancla la ruta del bundle a la raíz del proyecto, nunca al directorio de trabajo.

        Lección de H-18, y la razón de que el acceso directo del Paso 7 no necesite fijar
        el directorio de trabajo: el de un acceso directo no es el que uno cree.
        """
        ruta = self.cockpit.ruta_bundle
        return ruta if os.path.isabs(ruta) else ruta_proyecto(ruta)


def _exigir_mapa(datos: Any, nombre: str) -> Dict[str, Any]:
    if not isinstance(datos, dict):
        raise ConfiguracionLanzadorInvalida(
            f"El bloque '{nombre}' de {NOMBRE_FICHERO_CONFIG} debe ser un mapa de claves, "
            f"y se recibió {datos!r}."
        )
    return datos


def _entero_en_rango(datos: Dict[str, Any], clave: str, minimo: int, maximo: int, bloque: str) -> int:
    """Exige un entero dentro de rango, rechazando lo que YAML acepta y aquí no."""
    if clave not in datos:
        raise ConfiguracionLanzadorInvalida(
            f"Falta '{clave}' en el bloque '{bloque}' de {NOMBRE_FICHERO_CONFIG}. "
            "Sin ese valor el lanzador no puede decidir, y no se inventa."
        )
    valor = datos[clave]
    # `bool` es subclase de `int` en Python: `True` colaría como el puerto 1.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ConfiguracionLanzadorInvalida(
            f"'{clave}' debe ser un número entero, y se recibió {valor!r}."
        )
    if not (minimo <= valor <= maximo):
        raise ConfiguracionLanzadorInvalida(
            f"'{clave}' debe estar entre {minimo} y {maximo}, y se recibió {valor}."
        )
    return valor


def _booleano_explicito(datos: Dict[str, Any], clave: str, bloque: str) -> bool:
    """Exige `true` o `false` literales.

    No se acepta `"si"`, `1` ni la ausencia de la clave: un booleano deducido es una
    decisión que nadie declaró, y aquí gobiernan si se abre una ventana en la cara de
    alguien y si una tarea perdida se recupera.
    """
    if clave not in datos:
        raise ConfiguracionLanzadorInvalida(
            f"Falta '{clave}' en el bloque '{bloque}' de {NOMBRE_FICHERO_CONFIG}."
        )
    valor = datos[clave]
    if not isinstance(valor, bool):
        raise ConfiguracionLanzadorInvalida(
            f"'{clave}' debe ser true o false de forma explícita, y se recibió {valor!r}."
        )
    return valor


def _texto_no_vacio(datos: Dict[str, Any], clave: str, bloque: str) -> str:
    valor = datos.get(clave)
    if not isinstance(valor, str) or not valor.strip():
        raise ConfiguracionLanzadorInvalida(
            f"'{clave}' del bloque '{bloque}' debe ser un texto no vacío, y se recibió {valor!r}."
        )
    return valor.strip()


def cargar_configuracion(ruta: Optional[str] = None) -> ConfiguracionLanzador:
    """Lee y valida `config/lanzador.yaml`. **No aplica valores por defecto.**

    `ruta` permite inyectar un fichero alternativo en las pruebas. Una ruta absoluta se
    respeta intacta; una relativa se ancla a la raíz del proyecto, nunca al directorio de
    trabajo (Convención C1 y Paso D3).

    Lanza `ConfiguracionLanzadorInvalida` —código de salida 11— si falta, no es legible, no
    es un mapa YAML o declara algo fuera de rango.
    """
    if ruta is None:
        ruta = ruta_proyecto(os.path.join("config", NOMBRE_FICHERO_CONFIG))
    elif not os.path.isabs(ruta):
        ruta = ruta_proyecto(ruta)

    if not os.path.exists(ruta):
        raise ConfiguracionLanzadorInvalida(
            f"No se encuentra la configuración del lanzador en '{ruta}'. "
            "Sin ella no se arranca: no se inventan puerto ni plazos."
        )

    try:
        with open(ruta, "r", encoding="utf-8") as fichero:
            crudo = yaml.safe_load(fichero)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfiguracionLanzadorInvalida(
            f"No se pudo leer la configuración del lanzador en '{ruta}': {exc}"
        ) from exc

    if not isinstance(crudo, dict) or "lanzador" not in crudo:
        raise ConfiguracionLanzadorInvalida(
            f"'{ruta}' no contiene un bloque 'lanzador' válido."
        )

    datos = _exigir_mapa(crudo["lanzador"], "lanzador")

    version = datos.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ConfiguracionLanzadorInvalida(
            "La configuración debe declarar una 'version' no vacía: cada arranque registra "
            "bajo qué versión se ejecutó, y sin ella el rastro no es reconstruible."
        )

    servidor = _exigir_mapa(datos.get("servidor"), "servidor")
    cockpit = _exigir_mapa(datos.get("cockpit"), "cockpit")
    apagado = _exigir_mapa(datos.get("apagado"), "apagado")
    despertador = _exigir_mapa(datos.get("despertador"), "despertador")

    hora = _texto_no_vacio(despertador, "hora", "despertador")
    if not PATRON_HORA.match(hora):
        raise ConfiguracionLanzadorInvalida(
            f"'hora' debe tener el formato 24 h HH:MM, y se recibió '{hora}'. "
            "Una hora inválida registraría la tarea programada en un momento que nadie "
            "eligió, o no la registraría en absoluto."
        )

    return ConfiguracionLanzador(
        version=version.strip(),
        servidor=ConfiguracionServidor(
            host=_texto_no_vacio(servidor, "host", "servidor"),
            # Por debajo de 1024 son puertos privilegiados; por encima de 65535 no existen.
            puerto=_entero_en_rango(servidor, "puerto", 1024, 65535, "servidor"),
            espera_api_segundos=_entero_en_rango(servidor, "espera_api_segundos", 1, 600, "servidor"),
            espacio_minimo_mb=_entero_en_rango(servidor, "espacio_minimo_mb", 1, 10 ** 7, "servidor"),
        ),
        cockpit=ConfiguracionCockpit(
            ruta_bundle=_texto_no_vacio(cockpit, "ruta_bundle", "cockpit"),
            abrir_navegador=_booleano_explicito(cockpit, "abrir_navegador", "cockpit"),
        ),
        apagado=ConfiguracionApagado(
            gracia_endpoint_segundos=_entero_en_rango(apagado, "gracia_endpoint_segundos", 1, 300, "apagado"),
            gracia_senal_segundos=_entero_en_rango(apagado, "gracia_senal_segundos", 1, 300, "apagado"),
        ),
        despertador=ConfiguracionDespertador(
            hora=hora,
            ejecutar_si_se_perdio=_booleano_explicito(despertador, "ejecutar_si_se_perdio", "despertador"),
        ),
    )


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
    #: Cada fallo lleva **su** código de salida, en vez de decidirlo el llamador con una
    #: cadena de casos especiales. Quien revise por qué no arrancó una noche distingue
    #: "me falta una dependencia" (10) de "alguien ocupa mi puerto" (20) sin abrir el
    #: registro, que es justo para lo que sirve un código de salida.
    codigo_salida: int = HEALTHCHECK_INSATISFACTORIO


@dataclass
class DiagnosticoArranque:
    comprobaciones: List[Comprobacion] = field(default_factory=list)
    estado_puerto: Optional[EstadoPuerto] = None

    @property
    def fallos(self) -> List[Comprobacion]:
        return [c for c in self.comprobaciones if not c.ok and c.critica]

    @property
    def codigo_salida(self) -> int:
        """El del **primer** fallo en el orden en que se comprueba. Si todo va bien, `EXITO`.

        Con varios fallos a la vez, un único código es por fuerza una simplificación, así
        que lo que importa es que el orden de comprobación signifique algo. Es: configuración
        (11) → entorno (10) → puerto (20).

        De ahí sale la semántica útil: **el 20 sólo aparece cuando el puerto es el único
        problema** —"todo está listo salvo que alguien ocupa mi sitio"—, mientras que si
        además falta el bundle o una dependencia manda el 10, que es la verdad: el entorno
        no está preparado, y arreglar el puerto no lo arreglaría. El detalle completo de
        todos los fallos viaja en `resumen()`, que es lo que se muestra y se registra.
        """
        fallos = self.fallos
        return fallos[0].codigo_salida if fallos else EXITO

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
            codigo_salida=PUERTO_OCUPADO_AJENO,
        ),
        estado,
    )


def comprobar_arranque(
    ruta_config: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[Optional[ConfiguracionLanzador], DiagnosticoArranque]:
    """Punto de entrada del estado `COMPROBANDO`: carga la configuración y comprueba con ella.

    Devuelve la configuración —o `None` si no se pudo leer— y el diagnóstico. **Sigue sin
    modificar nada**: leer un YAML y consultar el sistema no deja rastro en disco.

    La configuración se carga **antes** del resto porque de ella salen el puerto, la ruta
    del bundle y el mínimo de disco: comprobar el puerto 8000 porque es el de siempre,
    cuando el fichero declara otro, sería diagnosticar un sistema distinto del que se va a
    arrancar.
    """
    try:
        config = cargar_configuracion(ruta_config)
    except ConfiguracionLanzadorInvalida as exc:
        diagnostico = DiagnosticoArranque()
        diagnostico.comprobaciones.append(
            Comprobacion(
                "Configuración del lanzador", False, str(exc),
                remedio=f"Revisar config/{NOMBRE_FICHERO_CONFIG}. "
                        "No se arranca con valores por defecto: un puerto o un plazo inventados "
                        "harían que el sistema se comportara distinto de lo que nadie declaró.",
                codigo_salida=CONFIGURACION_INVALIDA,
            )
        )
        return None, diagnostico

    diagnostico = ejecutar_healthcheck(
        host=config.servidor.host,
        puerto=config.servidor.puerto,
        ruta_bundle=config.ruta_bundle_absoluta(),
        espacio_minimo_mb=config.servidor.espacio_minimo_mb,
        db_path=db_path,
    )
    diagnostico.comprobaciones.insert(
        0,
        Comprobacion(
            "Configuración del lanzador", True,
            f"v{config.version}, puerto {config.servidor.puerto}, "
            f"despertador a las {config.despertador.hora}",
        ),
    )
    return config, diagnostico


# ==============================================================================
# Supervisor del servidor (Capa 10, Paso 5)
# ==============================================================================
#
# La pieza más delicada de la capa, porque es la única que **mata procesos**. Todo lo que
# hay aquí gira en torno a una sola idea: el lanzador sólo apaga lo que él encendió, y para
# saberlo el número de proceso no basta.

NOMBRE_FICHERO_PID = "lanzador.pid"

#: `PROCESS_QUERY_LIMITED_INFORMATION`. Basta para preguntar cuándo nació un proceso y no
#: pide privilegios: se consulta la identidad de procesos ajenos, no se toca ninguno.
_ACCESO_CONSULTA = 0x1000


def instante_creacion_proceso(pid: int) -> Optional[int]:
    """Instante de creación del proceso, o `None` si no existe.

    **Es la mitad que le falta al PID para ser una identidad.** Windows recicla los
    identificadores: un proceso que muere deja su número libre y el sistema se lo puede dar
    a otro cualquiera. Con el número a secas, *"apago sólo lo mío"* puede acabar matando algo
    inocente que heredó el número, y la reclamación de cerrojos huérfanos puede ver "el PID
    sigue vivo" sobre un dueño que ya murió — que es el plantón de diez minutos de H-15.

    El instante de creación no se recicla, así que el par (pid, instante) sí identifica.
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        manejador = kernel32.OpenProcess(_ACCESO_CONSULTA, False, pid)
        if not manejador:
            return None
        try:
            creacion, salida = wintypes.FILETIME(), wintypes.FILETIME()
            nucleo, usuario = wintypes.FILETIME(), wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                manejador, ctypes.byref(creacion), ctypes.byref(salida),
                ctypes.byref(nucleo), ctypes.byref(usuario),
            )
            if not ok:
                return None
            return (creacion.dwHighDateTime << 32) | creacion.dwLowDateTime
        finally:
            kernel32.CloseHandle(manejador)
    except Exception:
        return None


def es_nuestro_proceso(pid: int, instante_creacion: Optional[int]) -> bool:
    """¿Sigue vivo **el mismo** proceso que anotamos, y no otro que heredó su número?

    Sin `instante_creacion` anotado se responde `False`: ante la duda no se mata nada. Es la
    misma asimetría que gobierna `es_sesion_interactiva()` — no apagar deja un proceso de
    más, que es visible y molesto; apagar el que no era puede tumbar el trabajo de alguien.
    """
    if instante_creacion is None:
        return False
    return instante_creacion_proceso(pid) == instante_creacion


@dataclass(frozen=True)
class MarcaServidor:
    """Lo que el lanzador anota del servidor que arrancó él.

    `testigo` es el secreto que exige `POST /api/v1/admin/apagar`. Vive aquí y no en la
    configuración a propósito: se genera en cada arranque y muere con él, de modo que quien
    puede apagar el servidor es quien tiene acceso al fichero, no quien leyó un `.yaml`
    versionado en Git.
    """

    pid: int
    instante_creacion: Optional[int]
    host: str
    puerto: int
    testigo: str
    iniciado_at: str


def ruta_marca_servidor(db_path: Optional[str] = None) -> str:
    directorio = os.path.dirname(_ruta_base(db_path)) or ruta_datos()
    return os.path.join(directorio, NOMBRE_FICHERO_PID)


def escribir_marca_servidor(marca: MarcaServidor, db_path: Optional[str] = None) -> str:
    ruta = ruta_marca_servidor(db_path)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fichero:
        json.dump({
            "pid": marca.pid,
            "instante_creacion": marca.instante_creacion,
            "host": marca.host,
            "puerto": marca.puerto,
            "testigo": marca.testigo,
            "iniciado_at": marca.iniciado_at,
        }, fichero)
    return ruta


def leer_marca_servidor(db_path: Optional[str] = None) -> Optional[MarcaServidor]:
    """Devuelve la marca, o `None` si no hay o está ilegible.

    Una marca ilegible se trata como ausente y **no** como un error: significa que no consta
    que hayamos arrancado nada, y la conducta correcta ante eso es no apagar nada.
    """
    ruta = ruta_marca_servidor(db_path)
    try:
        with open(ruta, "r", encoding="utf-8") as fichero:
            datos = json.load(fichero)
        return MarcaServidor(
            pid=int(datos["pid"]),
            instante_creacion=datos.get("instante_creacion"),
            host=datos.get("host", "127.0.0.1"),
            puerto=int(datos["puerto"]),
            testigo=datos["testigo"],
            iniciado_at=datos.get("iniciado_at", ""),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def borrar_marca_servidor(db_path: Optional[str] = None) -> None:
    try:
        os.remove(ruta_marca_servidor(db_path))
    except OSError:
        pass


def esperar_api(host: str, puerto: int, tope_segundos: int, intervalo: float = 0.25) -> Optional[float]:
    """Espera **consultando** `/health` hasta que conteste. Devuelve lo que tardó, o `None`.

    Nunca se duerme un tiempo fijo: el error clásico de estos lanzadores es `sleep 5` y abrir
    el navegador, que en un equipo lento saca una pantalla en blanco y parece que el sistema
    no funciona; y en uno rápido regala cinco segundos a cada arranque.
    """
    inicio = time.monotonic()
    while time.monotonic() - inicio < tope_segundos:
        estado, _ = estado_del_puerto(host, puerto, timeout=1.0)
        if estado is EstadoPuerto.NUESTRA_API:
            return time.monotonic() - inicio
        time.sleep(intervalo)
    return None


def arrancar_servidor(
    config: ConfiguracionLanzador,
    db_path: Optional[str] = None,
) -> Tuple[Optional[MarcaServidor], float]:
    """Arranca `uvicorn` en un grupo de procesos propio y espera a que conteste.

    Devuelve la marca y los segundos que tardó. Lanza `ServidorNoRespondio` si vence el tope.

    **El grupo propio no es un detalle**: sin `CREATE_NEW_PROCESS_GROUP`, el `CTRL_BREAK_EVENT`
    del nivel 2 de apagado nos mataría también a nosotros, porque iría al grupo que
    compartimos con el hijo.
    """
    creacion_grupo_propio = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proceso = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app",
         "--host", config.servidor.host, "--port", str(config.servidor.puerto)],
        cwd=str(PROJECT_ROOT),
        creationflags=creacion_grupo_propio,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tardanza = esperar_api(config.servidor.host, config.servidor.puerto,
                           config.servidor.espera_api_segundos)
    if tardanza is None:
        # No dejamos huérfano lo que no llegó a servir: si no responde, no queda vivo.
        try:
            proceso.kill()
        except Exception:
            pass
        registrar_evento_lanzador(
            "LANZADOR_SERVIDOR_NO_RESPONDE",
            motivo=f"{config.servidor.host}:{config.servidor.puerto} no contestó en "
                   f"{config.servidor.espera_api_segundos}s",
            db_path=db_path,
        )
        raise ServidorNoRespondio(
            f"La API no respondió en {config.servidor.espera_api_segundos}s."
        )

    marca = MarcaServidor(
        pid=proceso.pid,
        instante_creacion=instante_creacion_proceso(proceso.pid),
        host=config.servidor.host,
        puerto=config.servidor.puerto,
        testigo=secrets.token_urlsafe(32),
        iniciado_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    escribir_marca_servidor(marca, db_path)
    registrar_evento_lanzador(
        "LANZADOR_SERVIDOR_ARRANCADO",
        motivo=f"pid {marca.pid} respondiendo en {tardanza:.1f}s",
        db_path=db_path,
    )
    return marca, tardanza


def _sigue_vivo(marca: MarcaServidor, plazo: float) -> bool:
    """Sondea hasta que el proceso desaparece o vence el plazo. `True` si sigue vivo.

    **Se verifica en cada nivel**: nunca se envía la señal y se da por hecho que funcionó.
    """
    inicio = time.monotonic()
    while time.monotonic() - inicio < plazo:
        if not es_nuestro_proceso(marca.pid, marca.instante_creacion):
            return False
        time.sleep(0.1)
    return es_nuestro_proceso(marca.pid, marca.instante_creacion)


def apagar_servidor(
    config: ConfiguracionLanzador,
    db_path: Optional[str] = None,
) -> str:
    """Apagado ordenado en tres niveles, verificando cada uno. Devuelve el nivel alcanzado.

    **Sólo apaga lo que el lanzador encendió.** Si no hay marca, o el proceso que la marca
    señala ya no es el nuestro, no se toca nada: puede ser una API que alguien levantó a
    mano para desarrollar, o un proceso inocente que heredó el número.
    """
    marca = leer_marca_servidor(db_path)
    if marca is None:
        return "sin_marca"

    if not es_nuestro_proceso(marca.pid, marca.instante_creacion):
        # El proceso murió por su cuenta, o su número lo heredó otro. En ambos casos aquí no
        # hay nada nuestro que apagar; lo único pendiente es retirar la marca.
        borrar_marca_servidor(db_path)
        return "ya_no_estaba"

    nivel = _apagar_por_niveles(marca, config)

    if nivel == "no_murio":
        registrar_evento_lanzador(
            "LANZADOR_APAGADO_INCOMPLETO",
            motivo=f"pid {marca.pid} sigue vivo tras los tres niveles",
            db_path=db_path,
        )
        raise ApagadoIncompleto(f"El servidor (pid {marca.pid}) sigue vivo tras los tres niveles.")

    borrar_marca_servidor(db_path)
    registrar_evento_lanzador("LANZADOR_APAGADO", motivo=f"nivel alcanzado: {nivel}", db_path=db_path)
    _avisar_si_quedo_cerrojo(db_path)
    return nivel


def _apagar_por_niveles(marca: MarcaServidor, config: ConfiguracionLanzador) -> str:
    # Nivel 1 — pedirle a uvicorn que se cierre desde dentro. Es el único que termina las
    # peticiones en curso, devuelve el cerrojo y ejecuta el `lifespan`. Y el único que
    # funciona **sin consola**, que es justo el caso del `.vbs`.
    if _pedir_apagado_por_http(marca):
        if not _sigue_vivo(marca, config.apagado.gracia_endpoint_segundos):
            return "endpoint"

    # Nivel 2 — CTRL_BREAK_EVENT al grupo. Medido el 2026-08-13: apaga uvicorn en 0,3 s.
    # `CTRL_C_EVENT` **no** sirve: queda deshabilitado en un grupo creado con
    # CREATE_NEW_PROCESS_GROUP, comprobado el mismo día.
    try:
        os.kill(marca.pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        if not _sigue_vivo(marca, config.apagado.gracia_senal_segundos):
            return "senal"
    except (OSError, AttributeError, ValueError):
        pass

    # Nivel 3 — TerminateProcess. No corrompe la base —SQLite en WAL sobrevive igual que a
    # un corte de luz—, pero pierde la escritura en vuelo y puede dejar el cerrojo huérfano.
    try:
        import ctypes

        manejador = ctypes.windll.kernel32.OpenProcess(0x0001, False, marca.pid)  # PROCESS_TERMINATE
        if manejador:
            try:
                ctypes.windll.kernel32.TerminateProcess(manejador, 1)
            finally:
                ctypes.windll.kernel32.CloseHandle(manejador)
        if not _sigue_vivo(marca, 5.0):
            return "terminate"
    except Exception:
        pass

    return "no_murio"


def _pedir_apagado_por_http(marca: MarcaServidor) -> bool:
    """Nivel 1. Devuelve si la petición se aceptó (no si el proceso ya murió: eso se sondea)."""
    try:
        import urllib.request

        peticion = urllib.request.Request(
            f"http://{marca.host}:{marca.puerto}/api/v1/admin/apagar",
            data=json.dumps({"testigo": marca.testigo}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(peticion, timeout=5.0) as respuesta:
            return respuesta.status < 400
    except Exception:
        return False


def _avisar_si_quedo_cerrojo(db_path: Optional[str] = None) -> None:
    """El cerrojo se comprueba **después** de apagar; no se supone liberado.

    La reclamación por PID y TTL es la red que lo recoge, pero conviene saber cuándo actúa:
    un cerrojo huérfano tras cada apagado señalaría que el nivel 1 no está funcionando y que
    siempre estamos cayendo al hachazo.
    """
    cerrojo = _ruta_base(db_path) + ".lock"
    if os.path.exists(cerrojo):
        registrar_evento_lanzador(
            "LANZADOR_CERROJO_HUERFANO_TRAS_APAGADO",
            motivo=f"{cerrojo} sigue presente tras el apagado",
            db_path=db_path,
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
    if diagnostico.satisfactorio:
        # Llamar aquí con un diagnóstico correcto no debería ocurrir nunca. Devolver el 0
        # que arrojaría `codigo_salida` convertiría un fallo en un éxito silencioso, que es
        # la transición prohibida nº 5 del contrato. Se sale por el código de lo no previsto.
        registrar_evento_lanzador(
            "LANZADOR_DEGRADADO",
            motivo="se pidió comunicar un fallo fatal con un diagnóstico satisfactorio",
        )
        return ERROR_NO_PREVISTO

    resumen = diagnostico.resumen()
    print(resumen, file=sys.stderr)
    registrar_evento_lanzador("LANZADOR_HEALTHCHECK_FALLIDO", motivo=resumen.replace("\n", " | "))

    if not avisar_fallo_fatal(titulo, resumen):
        registrar_evento_lanzador(
            "LANZADOR_GUI_OMITIDA",
            motivo="sin sesión interactiva: el aviso viaja por código de salida y registro",
        )

    return diagnostico.codigo_salida
