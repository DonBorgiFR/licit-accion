"""El rastro del ecosistema — Capa 10, Paso 9, bloque B: el lector canónico.

Su contrato vive en `.agents/CONTRATO_PASO_9.md`, validado el 2026-08-27, y conviene leerlo
antes de tocar nada de aquí. Este módulo implementa la **Operación 1** de aquel contrato: leer
`data/pipeline.jsonl` y devolver eventos con una sola forma, vengan de la gramática que vengan.

**Por qué existe.** El contrato de la Capa 10 declara `pipeline.jsonl` como el canal que sirve
«siempre, para el diagnóstico: reconstruir después qué ocurrió». Medido el 2026-08-27, ese
fichero contiene **cuatro gramáticas de evento incompatibles** —2.306 líneas con `action`, 1.965
con `tipo_evento`, 378 con `event` y 105 con `componente`—, y el Centinela escribe él solo en dos
de ellas. Quien lo lea con una sola gramática o revienta —lo que ocurrió el 2026-08-13, con un
`KeyError: 'action'`— o, peor, **descarta en silencio la mitad de las entradas** y presenta un
relato incompleto como si fuera completo. Es H-39.

Cuatro decisiones de diseño gobiernan el fichero, y ninguna es estilística:

1. **Ninguna línea desaparece en silencio.** Una línea que no parsea suma en `lineas_ilegibles`,
   su número queda anotado y el resultado se marca `degradado`. No es celo: hay **14 líneas
   partidas vivas** en el rastro real (H-55), dos de ellas posteriores a su catalogación, así
   que romperse no es deuda histórica sino condición permanente del fichero. Un lector que las
   saltara calladamente cometería exactamente el defecto que viene a reparar.

2. **Leer no modifica nada, ni siquiera el directorio de datos.** Es la lección del Paso 2 de
   esta misma capa: `ejecutar_healthcheck()` se dejó fuera del registro porque *escribir el
   registro crea la carpeta de destino*. Un lector de diagnóstico que tocara lo que examina es
   la misma trampa, y aquí sería peor: se invoca desde la API, en caliente.

3. **La integridad se exige al escribir, no al leer** *(decisión del 2026-07-27, registro de
   decisiones del proyecto)*. El lector **no valida ni rechaza**: si encuentra un `componente`
   fuera del vocabulario, lo conserva tal cual. Rechazar aquí significaría perder rastro ya
   escrito, que es lo único que no se puede recuperar. Quien valida es el escritor (Operación 2,
   bloque 9.C).

4. **El estado histórico se resuelve por catálogo declarado, jamás olfateando la cadena.** La
   Convención C3 prohíbe afirmar el modo degradado inspeccionando texto. `CATALOGO_HISTORICO`
   compara **nombres completos** contra una lista cerrada de ocho, y todo lo que no esté en ella
   se traduce a `DESCONOCIDO` — que es admitir que no se sabe, no suponer que fue bien. Buscar
   la subcadena `degrad` clasificaría mañana un evento que nadie ha revisado.
"""

import json
import os
import sys
import threading
import time
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src import ruta_datos

# ==============================================================================
# Vocabulario canónico (sección C del contrato)
# ==============================================================================

#: Versión del esquema de evento. Se estampa en cada línea que escriba el bloque 9.C, y es lo
#: que hace el fichero autodescriptivo: sin ella, distinguir una línea canónica de una
#: histórica vuelve a ser adivinar, que es como se llegó a H-39.
ESQUEMA_EVENTO = 1


class EstadoEvento(str, Enum):
    """Los cinco estados que puede declarar un evento.

    `DEGRADADO` **no existía en ninguna parte del vocabulario** antes de este paso: los 67
    eventos que hoy denotan degradación o fallo lo hacen sólo con su nombre. Y `DESCONOCIDO`
    **no es sinónimo de `INFO`**, por el mismo motivo por el que la Convención C6 distingue
    `nivel_interes="DESCONOCIDO"` de `"NULO"`: lo que no se pudo medir no puntúa en ninguna
    dirección, y dar por bueno lo que no consta es inventar hacia el lado cómodo.
    """

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEGRADADO = "DEGRADADO"
    DESCONOCIDO = "DESCONOCIDO"


#: Vocabulario cerrado de componentes. **Lo usa el escritor para validar, no el lector.**
COMPONENTES = frozenset(
    {"radar", "lector", "analista", "centinela", "depurador", "memoria", "api", "lanzador"}
)

#: Traducciones declaradas de nombres de componente que el histórico escribió de otra forma.
#: `analista_ia` y `analista` son el mismo componente, y presentarlos como dos sería mentir
#: sobre la estructura del sistema. Cualquier valor que no esté aquí **pasa tal cual** (nota 3).
ALIAS_COMPONENTES = {"analista_ia": "analista"}

#: Catálogo histórico de estados (sección D del contrato). **Cerrado: ocho nombres, 67 líneas.**
#: No crece después de la unificación del bloque 9.C, porque a partir de ahí el estado lo
#: declara quien escribe. Se comparan nombres completos, nunca subcadenas (Convención C3).
CATALOGO_HISTORICO: Dict[str, EstadoEvento] = {
    "boletin_fetch_degraded": EstadoEvento.DEGRADADO,
    "doc_ocr_degraded": EstadoEvento.DEGRADADO,
    "LANZADOR_DEGRADADO": EstadoEvento.DEGRADADO,
    "doc_download_failed": EstadoEvento.ERROR,
    "API_KPIS_FAILED": EstadoEvento.ERROR,
    "API_LICITACIONES_LIST_FAILED": EstadoEvento.ERROR,
    "LANZADOR_APAGADO_INCOMPLETO": EstadoEvento.ERROR,
    "LANZADOR_CERROJO_EJECUCION_HUERFANO": EstadoEvento.WARNING,
}


class Gramatica(str, Enum):
    """Las cuatro formas que conviven en el rastro, más la canónica y la que no se reconoce."""

    CANONICA = "CANONICA"
    A = "A"  # action / run_id / updated_by      — memoria, lanzador, lector
    B = "B"  # tipo_evento / modulo / payload    — api, centinela
    C = "C"  # event / claves sueltas            — analista
    D = "D"  # componente / evento / detalles    — centinela
    DESCONOCIDA = "DESCONOCIDA"


#: Tope de números de línea ilegible que se conservan. El **recuento** no se topa nunca; lo que
#: se acota es la lista, para que un fichero rotado de 10 MB lleno de basura no se lleve la
#: memoria por delante. Si se alcanza, `numeros_ilegibles_truncados` lo dice.
TOPE_NUMEROS_ILEGIBLES = 100


# ==============================================================================
# Errores tipados (sección G del contrato)
# ==============================================================================


class RastroIlegible(Exception):
    """El fichero existe pero no se puede abrir (permisos, bloqueo del sistema).

    **Que no exista no es esto**: un sistema recién instalado no tiene rastro, y eso no es una
    avería. Ese caso devuelve un resultado vacío con `existe=False`, sin excepción.
    """


# ==============================================================================
# Lo que el lector devuelve
# ==============================================================================


@dataclass(frozen=True)
class EventoCanonico:
    """Un evento del rastro, ya traducido, venga de la gramática que venga."""

    timestamp: str
    """Tal y como se escribió. **No se reformatea**: el histórico convive en dos formatos —2.789
    líneas con `...Z` y 1.965 con `...+00:00` y microsegundos— y normalizar la cadena perdería
    los microsegundos, que es lo único que ordena los eventos que la API escribe en ráfaga
    dentro del mismo segundo. Para comparar está `instante`."""

    instante: Optional[datetime]
    """El `timestamp` interpretado, en UTC. `None` si la fecha no era legible — que también es
    un dato, y por eso no se inventa una."""

    run_id: Optional[int]
    """`None` significa **el rastro no lo dice**, y no es lo mismo que `0`, que significa
    *evento del lanzador fuera de una corrida*. Las gramáticas C y D no lo escriben nunca, así
    que atribuir sus eventos a una corrida se hace **por ventana temporal** (ver `leer_rastro`),
    que es como se atribuyó a mano el `boletin_fetch_started` que acotó H-41."""

    componente: str
    evento: str
    estado: EstadoEvento
    datos: Dict[str, Any]
    gramatica: Gramatica
    linea: int
    """Número de línea en el fichero, 1-indexado. Es lo que permite ir a mirarla."""


@dataclass
class ResultadoRastro:
    """El resultado de una lectura, **con su propia degradación declarada en un campo**.

    Que `degradado` sea un booleano y no algo que el consumidor tenga que deducir es la
    Convención C3 aplicada al propio lector: si contara mal y lo dijera con un mensaje de texto,
    el consumidor no podría distinguir "leí todo" de "leí lo que pude".
    """

    eventos: List[EventoCanonico] = field(default_factory=list)
    lineas_totales: int = 0
    lineas_ilegibles: int = 0
    numeros_ilegibles: List[int] = field(default_factory=list)
    numeros_ilegibles_truncados: bool = False
    gramaticas: Dict[str, int] = field(default_factory=dict)
    existe: bool = True

    @property
    def degradado(self) -> bool:
        """Hubo líneas que no se pudieron leer. Ver la nota 1 de la cabecera del módulo."""
        return self.lineas_ilegibles > 0


# ==============================================================================
# Operación 1 — Leer el rastro
# ==============================================================================


def leer_rastro(
    ruta: Optional[str] = None,
    run_id: Optional[int] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    tope: Optional[int] = None,
) -> ResultadoRastro:
    """Lee el rastro y devuelve sus eventos traducidos a la forma canónica.

    **No escribe nada y no crea ningún directorio** (nota 2 de la cabecera).

    Los filtros se aplican **de forma conjuntiva e independiente**, sin ninguna astucia:

    * `run_id` conserva sólo los eventos cuyo `run_id` coincide. Los que no lo declaran —toda
      la gramática C y toda la D— **quedan fuera**, y eso es correcto: no consta que sean suyos.
    * `desde` / `hasta` conservan los eventos dentro de la ventana, ambos extremos incluidos.
      **Es el filtro que sirve para atribuir eventos históricos a una corrida**, tomando las
      marcas de la fila de `ejecuciones`. Quien decide cuál usar es el llamador, no este módulo.
    * `tope` conserva los **últimos** N eventos, no los primeros: quien diagnostica quiere el
      final del rastro. El recuento de líneas y de ilegibles sigue siendo el del fichero entero.

    Args:
        ruta: por defecto, `data/pipeline.jsonl` resuelto por `ruta_datos()`.

    Raises:
        RastroIlegible: el fichero existe pero no se pudo abrir.
    """
    destino = ruta or ruta_datos("pipeline.jsonl")

    if not os.path.exists(destino):
        return ResultadoRastro(existe=False)

    resultado = ResultadoRastro()
    gramaticas: Counter = Counter()
    seleccionados: Any = deque(maxlen=tope) if tope else []

    try:
        # `errors="replace"` en vez de dejar que un byte inválido reviente la lectura entera:
        # la línea afectada dejará de parsear y contará como ilegible, que es exactamente el
        # tratamiento honesto. Perder el fichero completo por un byte sería lo contrario.
        with open(destino, encoding="utf-8", errors="replace") as fichero:
            for numero, linea in enumerate(fichero, start=1):
                if not linea.strip():
                    continue
                resultado.lineas_totales += 1

                evento = _traducir(linea, numero)
                if evento is None:
                    resultado.lineas_ilegibles += 1
                    if len(resultado.numeros_ilegibles) < TOPE_NUMEROS_ILEGIBLES:
                        resultado.numeros_ilegibles.append(numero)
                    else:
                        resultado.numeros_ilegibles_truncados = True
                    continue

                gramaticas[evento.gramatica.value] += 1

                if not _pasa_filtros(evento, run_id, desde, hasta):
                    continue
                seleccionados.append(evento)
    except OSError as exc:
        raise RastroIlegible(f"No se pudo leer el rastro en '{destino}': {exc}") from exc

    resultado.eventos = list(seleccionados)
    resultado.gramaticas = dict(gramaticas)
    return resultado


def _pasa_filtros(
    evento: EventoCanonico,
    run_id: Optional[int],
    desde: Optional[datetime],
    hasta: Optional[datetime],
) -> bool:
    """Aplica los filtros declarados en `leer_rastro`, sin combinarlos entre sí."""
    if run_id is not None and evento.run_id != run_id:
        return False
    if (desde is not None or hasta is not None) and evento.instante is None:
        # Sin fecha legible no se puede afirmar que caiga dentro de la ventana. Se excluye en
        # vez de colarlo: incluirlo sería atribuir a una corrida un evento que quizá no es suyo.
        return False
    if desde is not None and evento.instante < desde:
        return False
    if hasta is not None and evento.instante > hasta:
        return False
    return True


# ==============================================================================
# La traducción de las cuatro gramáticas (sección D del contrato)
# ==============================================================================


def _traducir(linea: str, numero: int) -> Optional[EventoCanonico]:
    """Traduce una línea a la forma canónica, o devuelve `None` si no es un evento.

    Devolver `None` **no descarta la línea**: quien llama la cuenta como ilegible y anota su
    número. Es la nota 1 de la cabecera, y la razón de que esta función no lance.
    """
    try:
        crudo = json.loads(linea)
    except (ValueError, UnicodeDecodeError):
        return None

    # JSON válido que no es un objeto: parsea, pero no puede ser un evento. Contarlo como
    # ilegible es lo honesto; convertirlo en un evento vacío sería fabricar una entrada.
    if not isinstance(crudo, dict):
        return None

    gramatica = _gramatica_de(crudo)
    componente, evento, estado, datos = _campos_de(crudo, gramatica)

    return EventoCanonico(
        timestamp=str(crudo.get("timestamp", "")),
        instante=a_instante(crudo.get("timestamp")),
        run_id=_a_run_id(crudo.get("run_id")),
        componente=componente,
        evento=evento,
        estado=estado,
        datos=datos,
        gramatica=gramatica,
        linea=numero,
    )


def _gramatica_de(crudo: Dict[str, Any]) -> Gramatica:
    """Decide en qué idioma está escrita la línea.

    El orden importa: una línea canónica tiene `evento` **y** `componente`, igual que la
    gramática D, así que `esquema` se comprueba primero. Es justamente para eso que existe.
    """
    if "esquema" in crudo:
        return Gramatica.CANONICA
    if "action" in crudo:
        return Gramatica.A
    if "tipo_evento" in crudo:
        return Gramatica.B
    if "evento" in crudo:
        return Gramatica.D
    if "event" in crudo:
        return Gramatica.C
    return Gramatica.DESCONOCIDA


def _campos_de(crudo: Dict[str, Any], gramatica: Gramatica):
    """Extrae `componente`, `evento`, `estado` y `datos` según la gramática detectada."""
    if gramatica is Gramatica.CANONICA:
        datos = crudo.get("datos")
        return (
            _componente(crudo.get("componente")),
            str(crudo.get("evento", "")),
            _a_estado(crudo.get("estado")),
            datos if isinstance(datos, dict) else {},
        )

    if gramatica is Gramatica.A:
        nombre = str(crudo.get("action", ""))
        datos = {
            clave: crudo[clave]
            for clave in ("expediente_id", "reason", "duration_ms")
            if clave in crudo
        }
        return _componente(crudo.get("updated_by")), nombre, _estado_historico(nombre), datos

    if gramatica is Gramatica.B:
        # Es la única gramática que ya trae su estado escrito, así que se conserva el suyo en
        # vez de pasarlo por el catálogo: lo que el escritor declaró manda sobre lo que se
        # pueda deducir del nombre.
        payload = crudo.get("payload")
        return (
            _componente(crudo.get("modulo")),
            str(crudo.get("tipo_evento", "")),
            _a_estado(crudo.get("estado")),
            payload if isinstance(payload, dict) else {"payload": payload},
        )

    if gramatica is Gramatica.C:
        nombre = str(crudo.get("event", ""))
        datos = {c: v for c, v in crudo.items() if c not in ("timestamp", "event")}
        return "analista", nombre, _estado_historico(nombre), datos

    if gramatica is Gramatica.D:
        nombre = str(crudo.get("evento", ""))
        detalles = crudo.get("detalles")
        return (
            _componente(crudo.get("componente")),
            nombre,
            _estado_historico(nombre),
            detalles if isinstance(detalles, dict) else {"detalles": detalles},
        )

    # Gramática desconocida: parsea y es un objeto, pero ninguna clave dice qué ocurrió. No se
    # descarta —perdería rastro— y no se le inventa un nombre: se conserva entero en `datos` y
    # se declara `DESCONOCIDO`, que es la respuesta honesta.
    return (
        "",
        "",
        EstadoEvento.DESCONOCIDO,
        {c: v for c, v in crudo.items() if c != "timestamp"},
    )


def _componente(valor: Any) -> str:
    """Normaliza el nombre del componente por alias declarado, y **conserva lo que no conoce**.

    Ver la nota 3 de la cabecera: la integridad se exige al escribir, no al leer.
    """
    if valor is None:
        return ""
    texto = str(valor)
    return ALIAS_COMPONENTES.get(texto, texto)


def _estado_historico(nombre_evento: str) -> EstadoEvento:
    """Resuelve el estado de un evento que no lo escribió, **por catálogo cerrado**.

    Comparación por nombre completo contra `CATALOGO_HISTORICO`. Lo que no esté catalogado
    responde `DESCONOCIDO`: no se busca dentro de la cadena, no se deduce y no se supone.
    """
    return CATALOGO_HISTORICO.get(nombre_evento, EstadoEvento.DESCONOCIDO)


def _a_estado(valor: Any) -> EstadoEvento:
    """Interpreta un `estado` ya escrito; lo que no encaje en el vocabulario es `DESCONOCIDO`."""
    try:
        return EstadoEvento(str(valor))
    except ValueError:
        return EstadoEvento.DESCONOCIDO


def _a_run_id(valor: Any) -> Optional[int]:
    """`None` cuando el rastro no lo dice. Ver la nota del campo en `EventoCanonico`."""
    if valor is None:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def a_instante(valor: Any) -> Optional[datetime]:
    """Interpreta los dos formatos de fecha que conviven, y devuelve `None` si no lo es.

    Todo se lleva a UTC. Una fecha sin zona horaria se asume UTC, que es lo que escriben los
    seis puntos de escritura del proyecto sin excepción.
    """
    if not isinstance(valor, str) or not valor:
        return None
    try:
        instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None
    if instante.tzinfo is None:
        return instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


# ==============================================================================
# Operación 2 — Escribir un evento canónico (bloque 9.C)
# Operación 5 — Escribir una línea entera o ninguna, y no perder ninguna (H-55, bloque 10.B.3)
# ==============================================================================

#: El cerrojo del rastro (H-55). **Uno solo para todo el proceso**, y no uno por fichero: los
#: destinos distintos son las rutas temporales de las pruebas, la escritura dura menos de un
#: milisegundo, y un diccionario de cerrojos por ruta crecería sin nadie que lo vaciara.
_CERROJO = threading.Lock()

try:  # pragma: no cover - depende del sistema operativo
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None
try:  # pragma: no cover
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

#: Sufijo del fichero de cerrojo. **Se crea y no se borra nunca**: borrarlo abriría la carrera
#: clásica —un proceso elimina el fichero que otro acaba de abrir y los dos creen tenerlo—, y su
#: coste es un fichero vacío junto al rastro.
SUFIJO_CERROJO = ".lock"

#: Cuánto se espera al cerrojo entre procesos antes de rendirse y escribir igual. Cinco segundos
#: son tres órdenes de magnitud por encima de lo que dura una escritura: si no se ha soltado en
#: ese plazo, lo que pasa no es contención, es que algo está mal.
TOPE_ESPERA_CERROJO = 5.0


if msvcrt is not None:  # pragma: no cover - rama de Windows
    def _bloquear(descriptor):
        """Toma el byte 0 del fichero de cerrojo, reintentando hasta el tope.

        Se usa `LK_NBLCK` en un bucle propio y **no `LK_LOCK`**, que reintenta diez veces con un
        segundo de separación: con esperas reales de microsegundos, esa granularidad convertiría
        una espera trivial en un segundo entero, o en un fallo tras diez.
        """
        limite = time.monotonic() + TOPE_ESPERA_CERROJO
        espera = 0.0002
        while True:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= limite:
                    raise
                time.sleep(espera)
                espera = min(espera * 2, 0.01)

    def _desbloquear(descriptor):
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

elif fcntl is not None:  # pragma: no cover - rama POSIX
    def _bloquear(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_EX)

    def _desbloquear(descriptor):
        fcntl.flock(descriptor, fcntl.LOCK_UN)

else:  # pragma: no cover - sistema sin ninguno de los dos
    _bloquear = _desbloquear = None

#: Veces que no se pudo tomar el cerrojo entre procesos **y se escribió igual**. Es la conducta
#: que fija la sección F del contrato: un rastro con una línea rara es peor que uno limpio, pero
#: **perder el evento es peor que las dos cosas**.
escrituras_sin_cerrojo_de_fichero = 0


@contextmanager
def _cerrojo_entre_procesos(destino):
    """Serializa el acceso al rastro **entre procesos distintos**, con un cerrojo del sistema.

    **Por qué hizo falta, y cómo se supo.** El contrato declaraba *«alcance: sólo intra-proceso»*
    sobre una evidencia real —16 de las 19 líneas rotas del rastro se produjeron sin ninguna
    corrida activa—, y esa evidencia era cierta e incompleta. En la corrida 24 del 2026-09-01, ya
    con el cerrojo de módulo puesto, aparecieron **dos líneas rotas nuevas** y las dos con la
    firma contraria: un evento del pipeline encajado entre dos del servidor. **La API y el
    pipeline escriben a la vez todos los días.** Medido: dos procesos de cuatro hilos perdían
    entre el 1,3 % y el 5,5 % de los eventos, sin una sola línea rota — la pérdida no deja huella.

    **El cerrojo no es el fichero del rastro, es un fichero aparte.** Bloquear un rango del propio
    `pipeline.jsonl` abierto en modo añadir sería bloquear una posición que cada proceso resuelve
    por su cuenta; el byte 0 de un fichero de cerrojo dedicado es una referencia común y estable.
    """
    global escrituras_sin_cerrojo_de_fichero

    if _bloquear is None:
        yield
        return

    descriptor = None
    try:
        descriptor = os.open(destino + SUFIJO_CERROJO, os.O_RDWR | os.O_CREAT)
        _bloquear(descriptor)
    except OSError:
        # Ni crear el fichero de cerrojo ni tomarlo. **Se escribe igual y se cuenta** (sección F).
        # La suma no necesita protección: aquí ya se tiene el cerrojo de módulo.
        escrituras_sin_cerrojo_de_fichero += 1
        if descriptor is not None:
            os.close(descriptor)
        yield
        return

    try:
        yield
    finally:
        try:
            _desbloquear(descriptor)
        except OSError:
            pass
        os.close(descriptor)

#: Cuántas veces hubo que esperar al cerrojo. **Es un contador, no un evento, y eso se decidió
#: con un caso delante**: escribir en el rastro un evento sobre el hecho de escribir en el rastro
#: es la autorreferencia que produjo H-60, y aquí ocurriría dentro del único punto de escritura
#: del proyecto — justo cuando más carga hay. Se lee desde `tools/`, no desde el fichero.
escrituras_contendidas = 0


@contextmanager
def cerrojo_rastro(destino=None):
    """Serializa el acceso al fichero de rastro: entre hilos siempre, y entre procesos si se le
    dice sobre qué fichero *(`destino=None` toma sólo el de módulo)*.

    **Por qué existe** *(H-55, medido el 2026-09-01)*. `registrar_evento()` abre en modo `"a"`,
    escribe y cierra, y ese trío **no es atómico entre hilos** en Windows: dos hilos que resuelven
    el mismo final de fichero escriben uno encima del otro. El resultado medido con 16 hilos es
    que **se pierde entre el 4,8 % y el 5,8 % de los eventos**, y sólo 0-2 líneas quedan partidas.
    Las roturas eran el síntoma catalogado; la pérdida es el daño.

    **Y no basta con los hilos**, aunque el contrato lo dio por bueno con evidencia real: de las
    19 líneas partidas históricas, 16 se produjeron sin ninguna corrida activa. La corrida 24 del
    2026-09-01 refutó la apuesta a la primera —dos roturas nuevas, las dos con un evento del
    pipeline entre dos del servidor—, así que con `destino` se toma además
    `_cerrojo_entre_procesos()`. **Los dos cerrojos, y en este orden**: primero el de módulo,
    después el de fichero, de modo que los hilos de un proceso hacen cola sin llegar a tocar el
    sistema de ficheros.

    **Lo que este contexto NO debe abarcar nunca es la validación de un evento.**
    `registrar_evento()` lanza `EventoInvalido` antes de escribir, y `registrar_evento_tolerante()`
    lo captura para **volver a llamar** al escritor con un evento de rechazo. Si el cerrojo
    abarcara la validación, esa segunda llamada se encontraría con que su propia pila ya lo tiene
    tomado y **el proceso se quedaría clavado**.
    """
    global escrituras_contendidas
    if not _CERROJO.acquire(blocking=False):
        _CERROJO.acquire()
        # Dentro del cerrojo, así que la suma no necesita protección propia.
        escrituras_contendidas += 1
    try:
        if destino is None:
            yield
        else:
            with _cerrojo_entre_procesos(destino):
                yield
    finally:
        _CERROJO.release()


class EventoInvalido(ValueError):
    """Falta un campo obligatorio, o `estado` no pertenece al vocabulario.

    **Se rechaza antes de escribir**, no después: media línea en el rastro es peor que ninguna,
    y de eso ya hay 14 (H-55).
    """


def registrar_evento(
    componente: str,
    evento: str,
    estado: Any,
    datos: Optional[Dict[str, Any]] = None,
    run_id: Optional[int] = None,
    ruta: Optional[str] = None,
) -> None:
    """Escribe **un** evento canónico en el rastro. Es el único punto de escritura del proyecto.

    `estado` es obligatorio y **no tiene valor por defecto**. Un punto de llamada que se lo
    dejara olvidado estaría declarando éxito por descuido, que es la familia de la Convención
    C2: un fallo indistinguible de un éxito no es un fallo gestionado, es un fallo escondido.
    Cuesta explicitarlo en los sitios de llamada, y ésa es exactamente la intención.

    `run_id=None` significa **el escritor no sabe a qué corrida pertenece** *(contrato v1.1.0)*.
    No es `0`, que significa «fuera de una corrida». El Centinela entero cae en el primer caso.

    **Un fallo de escritura no tumba al llamador**: avisa por `stderr` y sigue. Que falle la
    auditoría no puede costar una prospección — pero tampoco puede pasar desapercibido, así que
    no se silencia (Convención C2). Es la conducta que ya tenía `registrar_evento_lanzador()`.

    Raises:
        EventoInvalido: `componente` o `evento` vacíos, o `estado` fuera del vocabulario.
    """
    if not componente or not str(componente).strip():
        raise EventoInvalido("un evento sin componente no dice quién lo escribió")
    if not evento or not str(evento).strip():
        raise EventoInvalido("un evento sin nombre no dice qué ocurrió")

    try:
        estado_valido = estado if isinstance(estado, EstadoEvento) else EstadoEvento(str(estado))
    except ValueError:
        raise EventoInvalido(
            f"estado '{estado}' no pertenece al vocabulario "
            f"{[e.value for e in EstadoEvento]}"
        ) from None

    entrada = {
        "esquema": ESQUEMA_EVENTO,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "componente": str(componente),
        "evento": str(evento),
        "estado": estado_valido.value,
        "datos": datos if isinstance(datos, dict) else {},
    }

    destino = ruta or ruta_datos("pipeline.jsonl")
    try:
        directorio = os.path.dirname(os.path.abspath(destino))
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        # `default=str` para que un valor no serializable —una fecha, un objeto del dominio— no
        # convierta un evento en una excepción dentro del pipeline. El rastro registra lo que
        # pasó; no es el sitio donde validar los tipos de negocio.
        #
        # Se serializa **fuera** del cerrojo: dentro sólo va lo que tiene que ser indivisible,
        # que es abrir, escribir y cerrar. Serializar dentro alargaría la espera de los demás
        # hilos sin ganar nada.
        linea = json.dumps(entrada, ensure_ascii=False, default=str) + "\n"
        with cerrojo_rastro(destino):
            with open(destino, "a", encoding="utf-8") as fichero:
                fichero.write(linea)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[!] No se pudo registrar el evento {evento}: {exc}", file=sys.stderr)


def estado_declarado_o_catalogo(estado: Any, nombre_evento: str) -> EstadoEvento:
    """Resuelve el `estado` de un envoltorio cuyo llamador todavía no lo declara.

    **Es andamio de migración, y por eso está acotado.** Los seis envoltorios de las capas 3 a 7
    conservan su firma —Regla 14: no se rompe lo que ya funciona— y ganan un `estado` opcional.
    Mientras un punto de llamada no lo declare, se resuelve por el mismo catálogo cerrado que usa
    la lectura, y lo que no esté en él dice `DESCONOCIDO`.

    **Lo que esto NO hace es sustituir la declaración explícita.** El catálogo se construyó con
    los ocho nombres que están escritos en el fichero, y el código emite bastantes más que
    todavía no han disparado nunca —`boletin_llm_degraded`, `doc_ocr_failed`,
    `LLM_REQUEST_FAILED`—: sin declararlos en su sitio, el rastro seguiría acumulando
    `DESCONOCIDO` sobre degradaciones reales.
    """
    if estado is not None:
        try:
            return estado if isinstance(estado, EstadoEvento) else EstadoEvento(str(estado))
        except ValueError:
            # No se valida aquí: si el valor es inválido se deja pasar para que lo rechace el
            # escritor, que es quien sabe registrar el rechazo. Lanzar desde el andamio se
            # saltaría la puerta tolerante y le costaría una prospección a la Capa 3.
            return estado
    return CATALOGO_HISTORICO.get(nombre_evento, EstadoEvento.DESCONOCIDO)


def registrar_evento_tolerante(
    componente: str,
    evento: str,
    estado: Any,
    datos: Optional[Dict[str, Any]] = None,
    run_id: Optional[int] = None,
    ruta: Optional[str] = None,
) -> None:
    """Como `registrar_evento`, pero **nunca lanza**: es la puerta que usan los envoltorios.

    Concilia dos exigencias del contrato que, juntas, parecen contradictorias: la sección G
    tipifica `EventoInvalido` y a la vez declara que *«ninguno de los tres detiene el pipeline:
    un fallo de auditoría no puede costar una prospección»*.

    La conciliación es que **el rechazo se registra en vez de propagarse**. Un evento inválido no
    se escribe —media línea es peor que ninguna—, pero su rechazo sí, con `RASTRO_EVENTO_RECHAZADO`
    y estado `ERROR`. Así el defecto queda en el propio rastro en lugar de desaparecer, que es la
    Convención C2: degradar a algo indistinguible del éxito está prohibido.

    **La versión estricta sigue existiendo y es la que usa el código nuevo**, para que una
    equivocación se note al escribirla y no seis meses después leyendo el fichero.
    """
    try:
        registrar_evento(componente, evento, estado, datos, run_id, ruta)
    except EventoInvalido as exc:
        registrar_evento(
            componente="memoria",
            evento="RASTRO_EVENTO_RECHAZADO",
            estado=EstadoEvento.ERROR,
            datos={"evento_rechazado": str(evento), "motivo": str(exc)},
            run_id=run_id,
            ruta=ruta,
        )
