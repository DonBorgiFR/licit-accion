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
from collections import Counter, deque
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
