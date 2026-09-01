"""El diagnóstico de la última prospección — Capa 10, Paso 9, bloque D.

Su contrato vive en `.agents/CONTRATO_PASO_9.md`, sección E.1. Implementa la máquina de estados
con la que el sistema afirma algo sobre sí mismo, y que gobierna el **tercer canal** de la capa:
el distintivo del Cockpit.

**Por qué existe, y con una fecha concreta.** La corrida 16 del 2026-08-27 consta `COMPLETED` con
`errores = 0`, y dentro de ella el Centinela **no pudo consultar ninguna de sus dos fuentes**
—DOGC 404, BOPB 500—. Con lo que había antes de este módulo, el Cockpit pintaba sobre esa corrida
un distintivo verde de «Datos al día». No era un defecto de la pantalla: es que **nadie
transportaba la degradación hasta donde se mira**. Eso es H-45 y el distintivo de fallo siendo un
solo defecto en dos pantallas.

Tres decisiones gobiernan el fichero:

1. **Ninguna conclusión sale de una sola fuente.** El estado lo dice la fila de `ejecuciones`; el
   motivo, el rastro. Preguntar sólo a la tabla es lo que producía el verde mentiroso; preguntar
   sólo al rastro dejaría sin diagnóstico a una corrida que murió antes de escribir nada.

2. **Es una función pura y recibe la fila ya leída.** No importa `Memoria` ni abre la base: quien
   la llama le pasa lo que ya tenía. Así se prueba entera sin base de datos y no hay dos sitios
   distintos decidiendo qué es una corrida viva — ese juicio lo da `listar_ejecuciones()`, que a
   su vez lo delega en el mismo criterio que usa el cerrojo (H-43).

3. **Las degradaciones se atribuyen por ventana temporal, no por `run_id`.** El Centinela no
   tiene noción de corrida *(contrato v1.1.0)*, y es justamente el componente cuyas degradaciones
   más importan. Es además como se atribuyó a mano el evento que acotó H-41.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.rastro import EstadoEvento, RastroIlegible, a_instante, leer_rastro

#: Evento con el que el lanzador declara que cortó el pipeline por agotar su tope (contrato de
#: la Capa 10, v1.3.0). Es lo único que distingue «se colgó y lo cortamos» de «murió sin más».
EVENTO_TOPE_AGOTADO = "LANZADOR_PIPELINE_AGOTADO"


class EstadoProspeccion(str, Enum):
    """Los estados que el sistema puede afirmar sobre su última prospección (sección E.1).

    **`COMPLETADA_CON_DEGRADACION` es el que este paso añade**, y el que faltaba: separa
    *«terminó»* de *«terminó pudiendo hacerlo todo»*. Los demás ya los distinguía el
    `ProspeccionIndicator` desde el Paso 7.
    """

    SIN_PROSPECCIONES = "SIN_PROSPECCIONES"
    EN_CURSO = "EN_CURSO"
    INTERRUMPIDA_POR_TOPE = "INTERRUMPIDA_POR_TOPE"
    INTERRUMPIDA = "INTERRUMPIDA"
    SIN_CERRAR = "SIN_CERRAR"
    FALLIDA = "FALLIDA"
    COMPLETADA_CON_DEGRADACION = "COMPLETADA_CON_DEGRADACION"
    COMPLETADA = "COMPLETADA"
    DESCONOCIDA = "DESCONOCIDA"
    """La fila dice algo que este módulo no sabe interpretar *(añadido en la v1.2.0 del
    contrato)*. No se traduce a `FALLIDA`: afirmar una avería sobre un valor que no se entiende
    es inventar, y la Convención C6 lo prohíbe en las dos direcciones."""


#: Componentes cuya degradación **no** es una avería de la corrida *(H-60, Operación 7)*.
#:
#: No es una lista de excepciones: es una distinción que se había borrado. **La corrida la
#: ejecutan las Capas 3 a 7 y el lanzador; la API es quien la mira.** Un fallo del observador no
#: es un fallo de lo observado, y confundirlos puso el distintivo en ámbar sobre prospecciones
#: impecables — «Al día, con 2 avisos» sobre la corrida 23, y con **49** sobre la 25, que sólo
#: medían cuántas veces se había mirado la pantalla mientras corrían.
#:
#: La atribución correcta de verdad sería por `run_id`, no por ventana temporal; se descartó en
#: el contrato v1.3.0 porque exige que todos los escritores lo declaren, y eso es trabajo del
#: tamaño de un paso. Mientras la atribución sea temporal, **cualquier evento de la API cae en la
#: ventana de la corrida por coincidir en el reloj**, así que el filtro cierra la familia entera
#: y no sólo el caso de `RASTRO_LEIDO_DEGRADADO`.
COMPONENTES_AJENOS_A_LA_CORRIDA = frozenset({"api"})


@dataclass(frozen=True)
class Degradacion:
    """Algo que la corrida no pudo hacer, tal y como lo dejó escrito quien no pudo hacerlo."""

    componente: str
    evento: str
    detalle: str
    cuando: Optional[str]


@dataclass
class DiagnosticoProspeccion:
    """Lo que se puede afirmar de la última prospección, y con qué respaldo.

    Los campos son estructurados a propósito: la frase que lee una persona la compone la
    pantalla, no este módulo. Mezclar aquí el texto de la interfaz ataría el diagnóstico a un
    idioma y a un ancho de columna.
    """

    estado: EstadoProspeccion
    ejecucion_id: Optional[int] = None
    inicio: Optional[str] = None
    fin: Optional[str] = None
    motivo: str = ""
    """Una frase corta y factual. **No es la copia de la pantalla**, es el resumen del porqué."""

    ultimo_evento: Optional[str] = None
    ultimo_evento_cuando: Optional[str] = None
    """Lo último que la corrida llegó a escribir. Es lo que se necesitó a mano para acotar H-41,
    y por eso se sirve siempre y no sólo cuando algo va mal."""

    degradaciones: List[Degradacion] = field(default_factory=list)
    errores_registrados: int = 0
    rastro_degradado: bool = False
    """El rastro tenía líneas ilegibles al leerlo (H-55). **Se declara en vez de callarse**: un
    diagnóstico construido sobre un fichero incompleto no puede presentarse como completo."""

    rastro_lineas_ilegibles: int = 0
    """⚠️ **Es del fichero entero, no de la ventana de esta corrida**, y el prefijo `rastro_` lo
    dice a propósito. Una línea partida no conserva su fecha, así que no se puede saber a qué
    corrida pertenecía; lo que sí se puede afirmar —y es lo que aquí se afirma— es que **este
    diagnóstico se construyó leyendo un fichero con N agujeros**. Leerlo como «esta corrida tuvo
    N líneas rotas» sería atribuirle un daño que quizá no es suyo."""

    rastro_legible: bool = True
    """`False` si el fichero no se pudo abrir siquiera. El diagnóstico **se sirve igual** con lo
    que diga la tabla: el canal de diagnóstico no puede tumbar aquello que diagnostica
    *(transición prohibida nº 4)*."""


def diagnosticar(
    ultima: Optional[Dict[str, Any]],
    ruta_rastro: Optional[str] = None,
) -> DiagnosticoProspeccion:
    """Diagnostica la última prospección a partir de su fila y del rastro.

    Args:
        ultima: la fila de `ejecuciones` más reciente, tal y como la devuelve
            `Memoria.listar_ejecuciones()` —incluido su `duenyo_vivo`—, o `None` si no hay
            ninguna. **No se consulta la base desde aquí** (decisión 2 de la cabecera).
        ruta_rastro: por defecto, el `pipeline.jsonl` que resuelva `leer_rastro()`.
    """
    if not ultima:
        return DiagnosticoProspeccion(
            estado=EstadoProspeccion.SIN_PROSPECCIONES,
            motivo="Todavía no consta ninguna prospección.",
        )

    eventos, legible, ilegibles = _eventos_de_la_corrida(ultima, ruta_rastro)
    degradaciones = [
        Degradacion(
            componente=evento.componente,
            evento=evento.evento,
            detalle=str(evento.datos.get("error") or evento.datos.get("motivo")
                        or evento.datos.get("reason") or ""),
            cuando=evento.timestamp or None,
        )
        for evento in eventos
        if evento.estado is EstadoEvento.DEGRADADO
        and evento.componente not in COMPONENTES_AJENOS_A_LA_CORRIDA
    ]
    ultimo = eventos[-1] if eventos else None

    estado, motivo = _resolver_estado(ultima, eventos, degradaciones)

    return DiagnosticoProspeccion(
        estado=estado,
        ejecucion_id=ultima.get("id"),
        inicio=ultima.get("start_time"),
        fin=ultima.get("end_time"),
        motivo=motivo,
        ultimo_evento=ultimo.evento if ultimo else None,
        ultimo_evento_cuando=ultimo.timestamp if ultimo else None,
        degradaciones=degradaciones,
        errores_registrados=int(ultima.get("errores") or 0),
        rastro_degradado=ilegibles > 0,
        rastro_lineas_ilegibles=ilegibles,
        rastro_legible=legible,
    )


def _resolver_estado(ultima, eventos, degradaciones):
    """La máquina de estados de la sección E.1, y nada más."""
    estado_fila = str(ultima.get("estado") or "")
    identificador = ultima.get("id")

    if estado_fila == "RUNNING":
        duenyo_vivo = ultima.get("duenyo_vivo")
        if duenyo_vivo is True:
            return (EstadoProspeccion.EN_CURSO,
                    f"La prospección nº {identificador} está en marcha.")
        if duenyo_vivo is False:
            # Un cuelgue cortado por el tope y una muerte sin más se parecen en que la fila
            # queda igual, y no se parecen en nada más: ante un tope agotado se mira por qué no
            # acababa; ante una muerte, qué la mató. Lo distingue el evento del lanzador.
            if any(evento.evento == EVENTO_TOPE_AGOTADO for evento in eventos):
                return (EstadoProspeccion.INTERRUMPIDA_POR_TOPE,
                        f"La prospección nº {identificador} se cortó por agotar su tope de duración.")
            return (EstadoProspeccion.INTERRUMPIDA,
                    f"La prospección nº {identificador} quedó sin terminar: su proceso ya no existe.")
        return (EstadoProspeccion.SIN_CERRAR,
                f"La prospección nº {identificador} consta iniciada y no se puede comprobar si sigue viva.")

    if estado_fila == "FAILED":
        return (EstadoProspeccion.FALLIDA, f"La prospección nº {identificador} falló.")

    if estado_fila == "COMPLETED":
        if degradaciones:
            cuantas = len(degradaciones)
            return (EstadoProspeccion.COMPLETADA_CON_DEGRADACION,
                    f"La prospección nº {identificador} terminó, pero {cuantas} "
                    f"{'cosa no se pudo hacer' if cuantas == 1 else 'cosas no se pudieron hacer'}.")
        return (EstadoProspeccion.COMPLETADA,
                f"La prospección nº {identificador} terminó sin incidencias.")

    return (EstadoProspeccion.DESCONOCIDA,
            f"La prospección nº {identificador} consta como '{estado_fila}', "
            f"que no es un estado que este sistema sepa interpretar.")


def _eventos_de_la_corrida(ultima, ruta_rastro):
    """Los eventos de la ventana de la corrida. Devuelve `(eventos, legible, ilegibles)`.

    **Un rastro roto no impide diagnosticar.** Si no se puede abrir, se devuelve una lista vacía
    y `legible=False`, y el diagnóstico sigue adelante con lo que diga la tabla: el canal de
    diagnóstico no puede tumbar aquello que diagnostica *(transición prohibida nº 4)*.
    """
    try:
        resultado = leer_rastro(
            ruta=ruta_rastro,
            desde=a_instante(ultima.get("start_time")),
            hasta=a_instante(ultima.get("end_time")),
        )
    except RastroIlegible:
        return [], False, 0
    return resultado.eventos, True, resultado.lineas_ilegibles


# ==============================================================================
# El estado de las fuentes del Centinela (bloque 9.E — H-45, cara pantalla)
# ==============================================================================

#: Los tres finales posibles de una consulta a una fuente. `started` no está: un arranque sin
#: final es información sobre un proceso muerto, no sobre la fuente.
EVENTOS_TERMINALES_FUENTE = {
    "boletin_fetch_succeeded": "OK",
    "boletin_fetch_degraded": "DEGRADADA",
    "boletin_fetch_omitido": "OMITIDA",
}


@dataclass(frozen=True)
class EstadoFuente:
    """Qué pasó la última vez que se consultó una fuente oficial, y cuándo fue.

    Existe porque **un canal vacío tiene tres causas que no se parecen en nada** y en pantalla
    se veían iguales: no hay novedades, no se pudo consultar, o nadie está mirando. Es H-45, y
    la evidencia de que no era teórico son las 26 descargas degradadas de 27 con las que el
    Cockpit enseñaba un `0` que se leía como *«no hay oportunidades»*.
    """

    fuente: str
    estado: str
    """`OK` · `DEGRADADA` · `OMITIDA` · `SIN_DATOS`."""

    detalle: str = ""
    cuando: Optional[str] = None
    alertas: Optional[int] = None
    """Cuántas trajo la última consulta correcta. `None` si no la hubo."""


def estado_de_las_fuentes(
    fuentes_esperadas: Optional[List[str]] = None,
    ruta_rastro: Optional[str] = None,
) -> List[EstadoFuente]:
    """El último desenlace conocido de cada fuente del Centinela.

    **No se acota a la última corrida, a diferencia de `diagnosticar()`**, y es deliberado: la
    pregunta que responde no es *«¿qué pasó anoche?»* sino *«¿cuándo fue la última vez que pude
    mirar aquí?»*. Una fuente que lleva tres semanas caída tiene que poder decirlo aunque la
    corrida de anoche ni la intentara.

    Args:
        fuentes_esperadas: las declaradas en `config/centinela_config.yaml`. Las que no aparezcan
            en el rastro se devuelven como `SIN_DATOS` — **no se omiten**: una fuente configurada
            de la que no consta nada es justo lo que hay que enseñar.
    """
    try:
        eventos = leer_rastro(ruta=ruta_rastro).eventos
    except RastroIlegible:
        eventos = []

    ultimos: Dict[str, EstadoFuente] = {}
    for evento in eventos:
        estado = EVENTOS_TERMINALES_FUENTE.get(evento.evento)
        if estado is None:
            continue
        nombre = str(evento.datos.get("fuente") or "").upper()
        if not nombre:
            continue
        # El rastro es cronológico, así que el último que se lee es el más reciente.
        ultimos[nombre] = EstadoFuente(
            fuente=nombre,
            estado=estado,
            detalle=str(evento.datos.get("error") or evento.datos.get("motivo") or ""),
            cuando=evento.timestamp or None,
            alertas=evento.datos.get("total_alertas") if estado == "OK" else None,
        )

    for nombre in (fuentes_esperadas or []):
        clave = nombre.upper()
        if clave not in ultimos:
            ultimos[clave] = EstadoFuente(
                fuente=clave,
                estado="SIN_DATOS",
                detalle="No consta ninguna consulta a esta fuente en el registro.",
            )

    return sorted(ultimos.values(), key=lambda f: f.fuente)
