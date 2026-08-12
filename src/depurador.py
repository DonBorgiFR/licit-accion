"""El Depurador — Capa 9: archivado (Paso 4), purga documental (Paso 5) y eliminación (Paso 6).

Las tres operaciones del contrato, en orden creciente de daño posible:

* **Archivar** no borra nada. Escribe `deleted_at` y `deleted_reason`, con lo que el lote sale
  del canal principal del Funnel pero sigue en la base, sigue contando en los KPIs históricos
  y puede rescatarse vaciando esa columna.
* **Purgar peso documental** sí es irreversible, pero sólo sobre el peso: borra el PDF del
  disco y vacía `texto_extraido`. La fila del documento permanece con su URL, su hash y su
  rastro —se sabe qué hubo y por qué ya no está— y **ninguna fila de negocio se toca**.
* **Eliminar físicamente** destruye registros y es terminal. Sólo alcanza a lo que nunca
  llegó a ser negocio: expedientes archivados, fuera de cuarentena, cuyos lotes jamás
  pasaron por `Presentada`, `Adjudicada`, `Perdida`, `Estudiando` ni `Descartada`. Exige
  lista explícita, confirmación expresa y copia de seguridad previa correcta.

**Lo que este motor tiene prohibido**, según `.agents/CONTRATO_CAPA_9.md`:

* Escribir en `estado_operativo`. No es su columna. Un expediente adjudicado sigue adjudicado
  después de archivarse; lo que pierde es presencia en pantalla, no condición de negocio.
* Borrar filas sin que una persona lo pida. La eliminación **nunca se deduce** y el pipeline
  no la invoca: `run.py` no puede destruir un expediente ni queriendo.
* Desactivar las claves foráneas. `PRAGMA foreign_keys=OFF` está prohibido: el `RESTRICT` es
  la red que impide dejar huérfanos, no un obstáculo a rodear. Si bloquea, hay que pararse.
* Desarchivar. El rescate `ARCHIVADO → VIVO` existe, pero lo pide una persona: si un criterio
  automático archivara y otro criterio automático desarchivara, el sistema oscilaría sin que
  nadie se enterase.
* Inventarse plazos. Sin política declarada no se archiva, ni se purga, ni se elimina, y se
  dice en voz alta.
"""

import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

from src import normalizar_estado_operativo, ruta_datos
from src.memoria import MARCA_LOG_ESTADO, Memoria
from src.retencion import PoliticaRetencion


# =======================================================================================
# Errores tipados del contrato (Capa 9). Ninguno se degrada a un valor por defecto
# silencioso: un fallo de purga siempre es distinguible de una purga que no encontró nada
# que borrar (Convención C2).
# =======================================================================================

class PurgaBloqueadaPorMemoriaComercial(Exception):
    """Se intentó eliminar un expediente con negocio o criterio humano invertido. HTTP 409."""


class PurgaBloqueadaPorIntegridad(Exception):
    """Una clave foránea `RESTRICT` detuvo el borrado. HTTP 409.

    **Indica un caso no previsto: es un defecto, no un uso normal.** Si la cascada
    hoja→raíz está bien ordenada, esto no puede ocurrir; que ocurra significa que hay una
    tabla que apunta al expediente y que nadie tuvo en cuenta.
    """


class CopiaSeguridadFallida(Exception):
    """No se pudo crear la copia previa. **La eliminación no se ejecuta.** HTTP 503."""


class ConfirmacionRequerida(Exception):
    """Se pidió una eliminación sin confirmación explícita. HTTP 400."""

#: Motivos de archivado. Se guardan en `deleted_reason` y se cuentan por separado porque
#: responden a preguntas distintas: uno mide licitaciones caducadas con normalidad, el otro
#: delata expedientes que llegaron sin fecha límite legible desde el origen.
MOTIVO_FECHA_LIMITE = "fecha_limite_vencida"
MOTIVO_SIN_FECHA_LIMITE = "sin_fecha_limite_conocida"

#: Valores con los que el pipeline representa "no hay fecha límite". `normalizar_fecha_utc()`
#: devuelve el literal "N/A" cuando no puede interpretar la fecha de origen, y las filas
#: antiguas pueden traer NULL o cadena vacía. Se enumeran de forma explícita: apoyarse en que
#: 'N' ordene después de '2' en una comparación de texto sería otra coherencia por accidente,
#: que es justo lo que H-27 documentó.
FECHAS_LIMITE_DESCONOCIDAS = ("N/A", "")


#: Vocabulario de la columna `purgas.tipo`, declarado en el DDL del esquema v6. Se usa el
#: declarado y no uno nuevo: inventar un estado que nadie más consulta es exactamente el
#: defecto que H-33 documentó, y esta capa no puede permitírselo en su propia auditoría.
TIPO_PURGA_DOCUMENTAL = "DOCUMENTAL"

#: La rotación de copias es parte de la Operación 2 del contrato ("documentos purgados,
#: bytes liberados, **copias rotadas**"), pero ocurre en otro momento del pipeline: después
#: de crear la copia nueva. Comparte tipo y se distingue por este campo del detalle.
OPERACION_DOCUMENTOS = "documentos"
OPERACION_ROTACION_COPIAS = "rotacion_copias"

#: Tipo de la Operación 3 en la tabla `purgas`, según el vocabulario declarado en el DDL.
TIPO_ELIMINACION = "ELIMINACION"

#: La invariante central de la capa. Un lote que alcanzó **alguna vez** uno de estos
#: estados hace que su expediente sea ineliminable para siempre. No es configurable desde
#: el fichero de política a propósito: es una regla de negocio del contrato, no un plazo.
#:
#: `Descartada` figura por un motivo que no es sentimental sino económico: si se borrase,
#: el pipeline volvería a capturar la licitación y a presentarla, y el equipo comercial
#: gastaría atención en reevaluar algo que ya rechazó *(dirección, 2026-08-07)*.
ESTADOS_QUE_BLOQUEAN_ELIMINACION = (
    "presentada",
    "adjudicada",
    "perdida",
    "estudiando",
    "descartada",
)

#: Campos donde se deposita el dinero y el esfuerzo. Si alguno tiene valor, hubo negocio,
#: por mucho que el estado actual del lote diga otra cosa.
CAMPOS_COMERCIALES = (
    "importe_adjudicacion",
    "dinero_en_la_mesa",
    "horas_internas_invertidas",
    "costes_externos",
    "importe_garantia_retenida",
    "empresa_adjudicataria",
)

#: Extrae los estados entrecomillados de una entrada del histórico, cuyo formato fija
#: `entrada_log_cambio_estado()`: "... ESTADO lote 1: 'nueva' -> 'presentada'".
_ESTADOS_EN_LOG = re.compile(r"'([^']*)'")

MOTIVO_NO_ARCHIVADO = "no_archivado"
MOTIVO_CUARENTENA = "cuarentena_no_cumplida"
MOTIVO_MEMORIA_COMERCIAL = "memoria_comercial"


@dataclass
class ResultadoPurgaDocumental:
    """Lo que liberó —o lo que decidió no tocar— una pasada de purga documental."""

    ejecutado: bool
    #: Filas que pasaron a `PURGADO`. Sólo cuenta aquello cuyo peso se liberó de verdad.
    documentos_purgados: int = 0
    ficheros_borrados: int = 0
    bytes_liberados: int = 0
    #: Ficheros que no se pudieron borrar. No es lo mismo que no tener nada que purgar, y
    #: por eso se cuenta aparte (Convención C2).
    errores_borrado: int = 0
    version_politica: Optional[str] = None
    corte_utc: Optional[str] = None
    motivo_degradacion: Optional[str] = None

    @property
    def hubo_cambios(self) -> bool:
        return self.documentos_purgados > 0


@dataclass
class ResultadoRotacionCopias:
    """Copias de seguridad retiradas por antigüedad."""

    ejecutado: bool
    copias_rotadas: int = 0
    version_politica: Optional[str] = None
    motivo_degradacion: Optional[str] = None


@dataclass
class ExpedienteEvaluado:
    """Veredicto sobre un expediente concreto, con el motivo cuando se le impide borrar.

    El motivo no es decoración: el contrato exige que la salida incluya "los bloqueados
    con su motivo", **igual de importante que los eliminados**. Una purga que bloquea mucho
    es una señal de que el histórico está vivo, no un fallo.
    """

    expediente_id: str
    eliminable: bool
    motivo: Optional[str] = None
    detalle_motivo: Optional[str] = None
    lotes: int = 0
    documentos: int = 0


@dataclass
class ResultadoPrevisualizacion:
    """Qué desaparecería si se confirmara ahora. No altera nada, pero consta quién miró."""

    ejecutado: bool
    eliminables: List[ExpedienteEvaluado] = field(default_factory=list)
    bloqueados: List[ExpedienteEvaluado] = field(default_factory=list)
    version_politica: Optional[str] = None
    motivo_degradacion: Optional[str] = None


@dataclass
class ResultadoEliminacion:
    """Lo que se destruyó, lo que se protegió y con qué copia de seguridad detrás."""

    ejecutado: bool
    expedientes_eliminados: int = 0
    lotes_eliminados: int = 0
    documentos_eliminados: int = 0
    analisis_eliminados: int = 0
    ficheros_borrados: int = 0
    bytes_liberados: int = 0
    bloqueados: List[ExpedienteEvaluado] = field(default_factory=list)
    backup_asociado: Optional[str] = None
    version_politica: Optional[str] = None
    motivo_degradacion: Optional[str] = None


@dataclass
class ResultadoArchivado:
    """Lo que hizo —o lo que decidió no hacer— una pasada de archivado."""

    ejecutado: bool
    lotes_archivados: int = 0
    expedientes_archivados: int = 0
    por_motivo: Dict[str, int] = field(default_factory=dict)
    version_politica: Optional[str] = None
    corte_utc: Optional[str] = None
    #: Relleno sólo si `ejecutado` es False. Nunca se degrada a un cero silencioso: un
    #: archivado que no pudo ejecutarse tiene que ser distinguible de uno que no encontró
    #: nada que archivar (Convención C2).
    motivo_degradacion: Optional[str] = None

    @property
    def hubo_cambios(self) -> bool:
        return self.lotes_archivados > 0 or self.expedientes_archivados > 0


def directorio_documentos(db_path: Optional[str] = None) -> str:
    """Dónde viven los pliegos descargados: **junto a la base**, no en `data/` sin más.

    Existe para que haya un solo sitio que lo decida. `Lector._path_for_document()` los
    escribe en `dirname(db_path)/documents` con caída a `ruta_datos()`, y cualquier otro
    módulo que dedujera la ruta por su cuenta acertaría sólo mientras las dos coincidieran
    —que es hoy, y por accidente—. Un Depurador que buscara los ficheros en otro directorio
    no fallaría: no encontraría nada y diría que no hay nada que purgar.
    """
    base = ruta_datos()
    if db_path:
        base = os.path.dirname(db_path) or ruta_datos()
    return os.path.join(base, "documents")


def medir_almacenamiento(db_path: Optional[str] = None) -> Dict[str, int]:
    """Inventario de lo que ocupa cada cosa, en bytes. **No toca nada.**

    Existe para responder a la pregunta con la que empieza cualquier decisión de purga:
    *¿dónde está el peso?* Separa lo purgable —pliegos y copias— de lo que no lo es —la
    base—, porque son los dos platos de la balanza y confundirlos lleva a purgar lo que no
    libera espacio: la memoria comercial son filas, no ficheros.
    """
    def peso_de(directorio: str):
        total = 0
        ficheros = 0
        if not os.path.isdir(directorio):
            return 0, 0
        for raiz, _, nombres in os.walk(directorio):
            for nombre in nombres:
                try:
                    total += os.path.getsize(os.path.join(raiz, nombre))
                    ficheros += 1
                except OSError:
                    continue
        return total, ficheros

    ruta_db = db_path or os.environ.get("DB_PATH_INCOOP") or ruta_datos("licitaciones.db")
    documentos_bytes, documentos_ficheros = peso_de(directorio_documentos(ruta_db))
    copias_bytes, copias_ficheros = peso_de(os.path.join(os.path.dirname(ruta_db), "backups"))

    base_bytes = os.path.getsize(ruta_db) if os.path.exists(ruta_db) else 0
    registro = ruta_datos("pipeline.jsonl")
    registros_bytes = os.path.getsize(registro) if os.path.exists(registro) else 0

    return {
        "base_datos_bytes": base_bytes,
        "documentos_bytes": documentos_bytes,
        "documentos_ficheros": documentos_ficheros,
        "copias_bytes": copias_bytes,
        "copias_ficheros": copias_ficheros,
        "registros_bytes": registros_bytes,
        "total_bytes": base_bytes + documentos_bytes + copias_bytes + registros_bytes,
        # Lo que una purga podría liberar. La base no entra: sus filas son la memoria
        # comercial, y no se purgan jamás.
        "purgable_bytes": documentos_bytes + copias_bytes,
    }


class Depurador:
    """Motor de ciclo de vida del dato: archiva, purga peso documental y elimina.

    Las dos primeras operaciones puede dispararlas la política en cada corrida. La tercera,
    nunca: exige que una persona la pida sobre una lista concreta y tras previsualizarla.
    """

    def __init__(
        self,
        memoria: Memoria,
        politica: Optional[PoliticaRetencion] = None,
        run_id: int = 0,
    ):
        self.memoria = memoria
        self.politica = politica
        self.run_id = run_id

    # -----------------------------------------------------------------------------------
    # Operación 1 del contrato — Archivar
    # -----------------------------------------------------------------------------------

    def archivar(
        self,
        ahora: Optional[datetime] = None,
        solicitado_por: str = "pipeline",
    ) -> ResultadoArchivado:
        """Archiva los lotes cuyo plazo venció hace más de lo que tolera la política.

        Precondición: política válida con bloque `archivado`. Sin ella no se archiva nada.
        Postcondición: los archivados tienen `deleted_at` y `deleted_reason`; salen del canal
        principal y siguen contando en los KPIs históricos. Ninguna fila cambia de estado
        operativo y ningún fichero se toca.
        Idempotencia: garantizada por construcción. Todo `UPDATE` filtra por
        `deleted_at IS NULL`, así que una segunda pasada no altera un archivado previo ni lo
        vuelve a contar.
        """
        degradacion = self._motivo_para_no_archivar()
        if degradacion:
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", degradacion)
            return ResultadoArchivado(ejecutado=False, motivo_degradacion=degradacion)

        criterio = self.politica.archivado
        ahora = ahora or datetime.now(timezone.utc)
        corte = (ahora - timedelta(days=criterio.dias_tras_fecha_limite)).strftime("%Y-%m-%dT%H:%M:%SZ")
        marca_temporal = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

        estados = list(criterio.estados_archivables)
        marcadores_estado = ", ".join("?" for _ in estados)
        marcadores_desconocidas = ", ".join("?" for _ in FECHAS_LIMITE_DESCONOCIDAS)

        # El filtro de estado se aplica normalizado (H-27): la columna admite hoy tanto
        # 'Inactiva' como 'inactiva', y comparar contra el literal devolvería cero filas
        # sin que nada fallase.
        condicion_estado = f"LOWER(TRIM(COALESCE(l.estado_operativo, ''))) IN ({marcadores_estado})"

        sql_por_fecha_limite = f"""
            UPDATE lotes SET deleted_at = ?, deleted_reason = ?
            WHERE id IN (
                SELECT l.id FROM lotes l
                JOIN expedientes e ON e.id = l.expediente_id
                WHERE l.deleted_at IS NULL
                  AND l.rescatado_at IS NULL
                  AND {condicion_estado}
                  AND e.fecha_limite IS NOT NULL
                  AND TRIM(e.fecha_limite) NOT IN ({marcadores_desconocidas})
                  AND e.fecha_limite < ?
            );
        """

        # Sin fecha límite legible se recurre a la de ingesta, que es NOT NULL y siempre
        # existe. No es un plazo de presentación, y por eso el motivo se guarda distinto:
        # que una licitación se archive por aquí es una señal sobre la calidad del feed de
        # origen, no una caducidad normal. La alternativa —no archivarla nunca— la dejaría
        # en el Funnel para siempre.
        sql_sin_fecha_limite = f"""
            UPDATE lotes SET deleted_at = ?, deleted_reason = ?
            WHERE id IN (
                SELECT l.id FROM lotes l
                JOIN expedientes e ON e.id = l.expediente_id
                WHERE l.deleted_at IS NULL
                  AND l.rescatado_at IS NULL
                  AND {condicion_estado}
                  AND (e.fecha_limite IS NULL OR TRIM(e.fecha_limite) IN ({marcadores_desconocidas}))
                  AND e.fecha_ingesta < ?
            );
        """

        # Un expediente se archiva cuando ninguno de sus lotes sigue vivo. El `EXISTS` no
        # sobra: sin él, un expediente sin lotes cumpliría el `NOT EXISTS` de forma trivial y
        # se archivaría por no tener nada dentro.
        sql_expedientes = """
            UPDATE expedientes SET deleted_at = ?, deleted_reason = ?
            WHERE deleted_at IS NULL
              AND rescatado_at IS NULL
              AND EXISTS (SELECT 1 FROM lotes WHERE expediente_id = expedientes.id)
              AND NOT EXISTS (
                  SELECT 1 FROM lotes
                  WHERE expediente_id = expedientes.id AND deleted_at IS NULL
              );
        """

        razon_fecha_limite = (
            f"Archivado automático: más de {criterio.dias_tras_fecha_limite} días desde la "
            f"fecha límite (política de retención v{self.politica.version})"
        )
        razon_sin_fecha = (
            f"Archivado automático: sin fecha límite conocida y más de "
            f"{criterio.dias_tras_fecha_limite} días desde la ingesta "
            f"(política de retención v{self.politica.version})"
        )
        razon_expediente = (
            f"Archivado automático: ninguno de sus lotes sigue vivo "
            f"(política de retención v{self.politica.version})"
        )

        por_motivo = {MOTIVO_FECHA_LIMITE: 0, MOTIVO_SIN_FECHA_LIMITE: 0}
        expedientes_archivados = 0

        # Una sola transacción: o queda archivado y auditado, o no queda nada. Un archivado
        # sin su fila en `purgas` sería un cambio de estado sin rastro.
        with self.memoria.db_lock():
            with self.memoria.conectar() as conn:
                with conn:
                    cursor = conn.cursor()

                    cursor.execute(
                        sql_por_fecha_limite,
                        [marca_temporal, razon_fecha_limite, *estados, *FECHAS_LIMITE_DESCONOCIDAS, corte],
                    )
                    por_motivo[MOTIVO_FECHA_LIMITE] = cursor.rowcount or 0

                    cursor.execute(
                        sql_sin_fecha_limite,
                        [marca_temporal, razon_sin_fecha, *estados, *FECHAS_LIMITE_DESCONOCIDAS, corte],
                    )
                    por_motivo[MOTIVO_SIN_FECHA_LIMITE] = cursor.rowcount or 0

                    if criterio.archivar_expediente_con_todos_sus_lotes:
                        cursor.execute(sql_expedientes, (marca_temporal, razon_expediente))
                        expedientes_archivados = cursor.rowcount or 0

                    lotes_archivados = sum(por_motivo.values())

                    if lotes_archivados or expedientes_archivados:
                        self.memoria.registrar_purga(
                            tipo="ARCHIVADO",
                            solicitada_por=solicitado_por,
                            version_politica=self.politica.version,
                            resultado="COMPLETADA",
                            expedientes_archivados=expedientes_archivados,
                            detalle=json.dumps(
                                {
                                    "lotes_archivados": lotes_archivados,
                                    "por_motivo": por_motivo,
                                    "corte_utc": corte,
                                    "dias_tras_fecha_limite": criterio.dias_tras_fecha_limite,
                                    "estados_archivables": list(estados),
                                },
                                ensure_ascii=False,
                            ),
                            conn=conn,
                        )

        resultado = ResultadoArchivado(
            ejecutado=True,
            lotes_archivados=sum(por_motivo.values()),
            expedientes_archivados=expedientes_archivados,
            por_motivo=por_motivo,
            version_politica=self.politica.version,
            corte_utc=corte,
        )

        self._registrar_evento(
            "DEPURADOR_ARCHIVADO",
            f"lotes={resultado.lotes_archivados} "
            f"expedientes={resultado.expedientes_archivados} "
            f"por_motivo={por_motivo} corte={corte} politica=v{self.politica.version}",
        )
        return resultado

    # -----------------------------------------------------------------------------------
    # Operación 2 del contrato — Purgar peso documental
    # -----------------------------------------------------------------------------------

    def purgar_documentos(
        self,
        ahora: Optional[datetime] = None,
        solicitado_por: str = "pipeline",
    ) -> ResultadoPurgaDocumental:
        """Libera el peso documental que ya superó la retención: ficheros y texto extraído.

        Precondición: política válida y permiso de escritura en `data/documents/`.
        Postcondición: los ficheros salen del disco, `texto_extraido` queda vacío y el
        documento pasa a `PURGADO`. **Ninguna fila de `lotes` se modifica**: esta operación
        no toca la memoria comercial, sólo su peso.
        Idempotencia: un documento ya `PURGADO` no vuelve a seleccionarse ni a contarse.

        Qué **no** hace: decidir plazos por su cuenta, tocar `estado_operativo` ni borrar
        una sola fila. Eliminar filas es el Paso 6 y exige confirmación explícita.
        """
        degradacion = self._motivo_para_no_purgar()
        if degradacion:
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", degradacion)
            return ResultadoPurgaDocumental(ejecutado=False, motivo_degradacion=degradacion)

        ahora = ahora or datetime.now(timezone.utc)
        corte = (ahora - timedelta(days=self.politica.documentos_dias)).strftime("%Y-%m-%dT%H:%M:%SZ")

        self._registrar_evento(
            "DEPURADOR_PURGA_INICIADA",
            f"tipo=documental corte={corte} retencion_dias={self.politica.documentos_dias} "
            f"politica=v{self.politica.version} solicitada_por={solicitado_por}",
        )

        candidatos = self.memoria.obtener_documentos_para_purga(corte)
        if not candidatos:
            self._registrar_evento(
                "DEPURADOR_PURGA_COMPLETADA",
                f"tipo=documental documentos=0 bytes=0 corte={corte} "
                f"politica=v{self.politica.version}",
            )
            return ResultadoPurgaDocumental(
                ejecutado=True,
                version_politica=self.politica.version,
                corte_utc=corte,
            )

        # Primero el disco y después la base, y no al revés. Si fallara la escritura en la
        # base tras haber borrado, la corrida siguiente reencontraría el documento y lo
        # terminaría de purgar; al revés quedaría marcado `PURGADO` con el fichero todavía
        # en disco, invisible para siempre a cualquier purga posterior.
        ids_purgables: List[int] = []
        bytes_liberados = 0
        ficheros_borrados = 0
        errores_borrado = 0

        for doc in candidatos:
            ruta = doc.get("local_path")

            if not ruta or not os.path.exists(ruta):
                # Sin fichero en disco no hay bytes que liberar, pero puede quedar texto en
                # la base: sigue siendo purgable, y purgarlo es precisamente lo que vacía
                # `texto_extraido`.
                ids_purgables.append(doc["id"])
                continue

            liberado, borrado, error = self._borrar_fichero_y_sidecar(ruta)
            bytes_liberados += liberado
            if error:
                # El fichero sigue ahí: no se marca como purgado. Marcarlo lo sacaría de
                # futuras selecciones y dejaría el fichero huérfano en disco para siempre.
                # (Los cerrojos de fichero en Windows son reales: lección del Paso D1.)
                errores_borrado += 1
                print(f"  [!] [depurador] No se pudo borrar '{ruta}': {error}")
                continue

            ficheros_borrados += borrado
            ids_purgables.append(doc["id"])

        documentos_purgados = 0
        if ids_purgables:
            with self.memoria.db_lock():
                with self.memoria.conectar() as conn:
                    with conn:
                        documentos_purgados = self.memoria.marcar_documentos_como_purgados(
                            ids_purgables, conn=conn
                        )
                        self.memoria.registrar_purga(
                            tipo=TIPO_PURGA_DOCUMENTAL,
                            solicitada_por=solicitado_por,
                            version_politica=self.politica.version,
                            resultado="COMPLETADA",
                            documentos_purgados=documentos_purgados,
                            bytes_liberados=bytes_liberados,
                            detalle=json.dumps(
                                {
                                    "operacion": OPERACION_DOCUMENTOS,
                                    "ficheros_borrados": ficheros_borrados,
                                    "errores_borrado": errores_borrado,
                                    "candidatos": len(candidatos),
                                    "corte_utc": corte,
                                    "retencion_dias": self.politica.documentos_dias,
                                },
                                ensure_ascii=False,
                            ),
                            conn=conn,
                        )

        resultado = ResultadoPurgaDocumental(
            ejecutado=True,
            documentos_purgados=documentos_purgados,
            ficheros_borrados=ficheros_borrados,
            bytes_liberados=bytes_liberados,
            errores_borrado=errores_borrado,
            version_politica=self.politica.version,
            corte_utc=corte,
        )

        self._registrar_evento(
            "DEPURADOR_PURGA_COMPLETADA",
            f"tipo=documental documentos={documentos_purgados} "
            f"ficheros={ficheros_borrados} bytes={bytes_liberados} "
            f"errores={errores_borrado} corte={corte} politica=v{self.politica.version}",
        )
        return resultado

    def rotar_copias(self, solicitado_por: str = "pipeline") -> ResultadoRotacionCopias:
        """Retira las copias de seguridad que superan su plazo.

        Es la otra mitad de la Operación 2: las copias son peso que crece sin límite y sin
        valor comercial. Va aparte de `purgar_documentos()` porque en el pipeline ocurre en
        otro momento —después de crear la copia de esta corrida—, no porque sea otra cosa.
        """
        if self.politica is None:
            motivo = (
                "politica_retencion_ausente: no se rotan copias sin política declarada, y "
                "no se aplican plazos por defecto"
            )
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", motivo)
            return ResultadoRotacionCopias(ejecutado=False, motivo_degradacion=motivo)

        try:
            rotadas = self.memoria.rotar_backups(dias_retencion=self.politica.backups_dias)
        except Exception as exc:
            # Una rotación fallida no puede confundirse con "no había nada que rotar"
            # (Convención C2): es justo lo que hacía el `except` amplio del pipeline, que
            # además la anunciaba como un fallo del backup.
            motivo = f"rotacion_copias_fallida: {type(exc).__name__}: {exc}"
            self._registrar_evento("DEPURADOR_PURGA_ABORTADA", motivo)
            return ResultadoRotacionCopias(
                ejecutado=False,
                version_politica=self.politica.version,
                motivo_degradacion=motivo,
            )

        if rotadas:
            self.memoria.registrar_purga(
                tipo=TIPO_PURGA_DOCUMENTAL,
                solicitada_por=solicitado_por,
                version_politica=self.politica.version,
                resultado="COMPLETADA",
                documentos_purgados=0,
                detalle=json.dumps(
                    {
                        "operacion": OPERACION_ROTACION_COPIAS,
                        "copias_rotadas": rotadas,
                        "retencion_dias": self.politica.backups_dias,
                    },
                    ensure_ascii=False,
                ),
            )

        self._registrar_evento(
            "DEPURADOR_PURGA_COMPLETADA",
            f"tipo=rotacion_copias copias={rotadas} "
            f"retencion_dias={self.politica.backups_dias} politica=v{self.politica.version}",
        )
        return ResultadoRotacionCopias(
            ejecutado=True,
            copias_rotadas=rotadas,
            version_politica=self.politica.version,
        )

    def previsualizar_purga_documental(
        self, ahora: Optional[datetime] = None
    ) -> ResultadoPurgaDocumental:
        """Qué documentos se purgarían ahora, **sin borrar nada**.

        Alimenta la pantalla de administración: mirar antes de decidir. Devuelve la misma
        forma que `purgar_documentos()` para que la interfaz no tenga que distinguir entre
        el ensayo y la función, con `documentos_purgados` como recuento de candidatos y
        `bytes_liberados` como estimación tomada del disco.
        """
        degradacion = self._motivo_para_no_purgar()
        if degradacion:
            return ResultadoPurgaDocumental(ejecutado=False, motivo_degradacion=degradacion)

        ahora = ahora or datetime.now(timezone.utc)
        corte = (ahora - timedelta(days=self.politica.documentos_dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        candidatos = self.memoria.obtener_documentos_para_purga(corte)

        bytes_estimados = 0
        ficheros = 0
        for doc in candidatos:
            ruta = doc.get("local_path")
            if ruta and os.path.exists(ruta):
                ficheros += 1
                try:
                    bytes_estimados += os.path.getsize(ruta)
                except OSError:
                    pass

        return ResultadoPurgaDocumental(
            ejecutado=True,
            documentos_purgados=len(candidatos),
            ficheros_borrados=ficheros,
            bytes_liberados=bytes_estimados,
            version_politica=self.politica.version,
            corte_utc=corte,
        )

    # -----------------------------------------------------------------------------------
    # Rescate manual: la única vía ARCHIVADO → VIVO
    # -----------------------------------------------------------------------------------

    def rescatar(self, expediente_ids: Sequence[str], solicitado_por: str = "usuario") -> int:
        """Devuelve al canal principal expedientes archivados. **Sólo a petición de una persona.**

        La transición `ARCHIVADO → VIVO` existe pero nunca es automática: si un criterio
        archivara y otro desarchivara, el sistema oscilaría sin que nadie se enterase.

        Marca `rescatado_at` además de vaciar `deleted_at`, y esa marca es la que hace que el
        rescate sirva de algo: sin ella, la corrida siguiente volvería a archivar el lote
        —la fecha límite sigue vencida— y quien lo rescató vería su decisión deshecha sola.
        Mismo criterio que el Paso D5 aplicó al Centinela.

        **No toca `estado_operativo`.** Un lote que el Radar marcó `Inactiva` al desaparecer
        del feed vuelve al canal siendo `Inactiva`: recuperar visibilidad no es cambiar de
        situación comercial, y eso lo decide quien mire la ficha.

        Devuelve cuántos expedientes se rescataron.
        """
        if not expediente_ids:
            return 0

        marca = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marcadores = ", ".join("?" for _ in expediente_ids)
        ids = list(expediente_ids)

        with self.memoria.db_lock():
            with self.memoria.conectar() as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"UPDATE expedientes SET deleted_at = NULL, deleted_reason = NULL, "
                        f"rescatado_at = ? WHERE id IN ({marcadores}) AND deleted_at IS NOT NULL;",
                        [marca, *ids],
                    )
                    rescatados = cursor.rowcount or 0
                    cursor.execute(
                        f"UPDATE lotes SET deleted_at = NULL, deleted_reason = NULL, "
                        f"rescatado_at = ? WHERE expediente_id IN ({marcadores}) "
                        f"AND deleted_at IS NOT NULL;",
                        [marca, *ids],
                    )
                    lotes = cursor.rowcount or 0

        self._registrar_evento(
            "DEPURADOR_RESCATE_MANUAL",
            f"expedientes={rescatados} lotes={lotes} solicitado_por={solicitado_por} "
            f"ids={','.join(ids)}",
        )
        return rescatados

    # -----------------------------------------------------------------------------------
    # Operación 3 del contrato — Eliminar físicamente
    # -----------------------------------------------------------------------------------

    def previsualizar_eliminacion(
        self,
        expediente_ids: Optional[Sequence[str]] = None,
        ahora: Optional[datetime] = None,
        solicitado_por: str = "usuario",
    ) -> ResultadoPrevisualizacion:
        """Qué desaparecería si se confirmara ahora. **No altera absolutamente nada.**

        Existe porque el diseño de la capa prohíbe el botón que borra a ciegas: se enseña
        exactamente qué va a desaparecer antes de que nadie confirme. Sin `expediente_ids`
        evalúa todo lo archivado, que es la vista que necesita la pantalla de administración.

        Emite `DEPURADOR_PURGA_PREVISUALIZADA`: no altera nada, **pero consta quién miró**.
        """
        degradacion = self._motivo_para_no_eliminar()
        if degradacion:
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", degradacion)
            return ResultadoPrevisualizacion(ejecutado=False, motivo_degradacion=degradacion)

        ahora = ahora or datetime.now(timezone.utc)
        corte = self._corte_cuarentena(ahora)

        with self.memoria.conectar() as conn:
            conn.row_factory = sqlite3.Row
            candidatos = self._candidatos(conn, expediente_ids)
            evaluados = [self._evaluar_expediente(conn, exp_id, corte) for exp_id in candidatos]

        evaluados = [e for e in evaluados if e is not None]
        eliminables = [e for e in evaluados if e.eliminable]
        bloqueados = [e for e in evaluados if not e.eliminable]

        self._registrar_evento(
            "DEPURADOR_PURGA_PREVISUALIZADA",
            f"solicitada_por={solicitado_por} evaluados={len(evaluados)} "
            f"eliminables={len(eliminables)} bloqueados={len(bloqueados)} "
            f"cuarentena_hasta={corte} politica=v{self.politica.version}",
        )
        return ResultadoPrevisualizacion(
            ejecutado=True,
            eliminables=eliminables,
            bloqueados=bloqueados,
            version_politica=self.politica.version,
        )

    def eliminar_expedientes(
        self,
        expediente_ids: Sequence[str],
        confirmado: bool = False,
        ahora: Optional[datetime] = None,
        solicitado_por: str = "usuario",
    ) -> ResultadoEliminacion:
        """Borra físicamente expedientes que nunca llegaron a ser negocio. **Terminal.**

        Precondiciones: lista explícita, confirmación expresa, política con bloque
        `eliminacion`, expedientes archivados y fuera de cuarentena, invariante de memoria
        comercial superada y **copia de seguridad previa correcta**.
        Postcondición: filas eliminadas en orden hoja→raíz sin dejar un solo huérfano.
        Atomicidad: una única transacción. Si algo la interrumpe, se revierte entera; nunca
        queda un expediente sin lotes ni un lote sin expediente.

        Lo bloqueado **no aborta la operación**: se elimina lo eliminable y se devuelve lo
        protegido con su motivo, que según el contrato importa tanto como lo borrado.
        """
        if not confirmado:
            raise ConfirmacionRequerida(
                "La eliminación física es irreversible y exige confirmación explícita. "
                "Previsualice primero con `previsualizar_eliminacion()`."
            )

        degradacion = self._motivo_para_no_eliminar()
        if degradacion:
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", degradacion)
            return ResultadoEliminacion(ejecutado=False, motivo_degradacion=degradacion)

        if not expediente_ids:
            return ResultadoEliminacion(ejecutado=True, version_politica=self.politica.version)

        ahora = ahora or datetime.now(timezone.utc)
        corte = self._corte_cuarentena(ahora)

        # 1. Veredicto antes de tocar nada.
        with self.memoria.conectar() as conn:
            conn.row_factory = sqlite3.Row
            evaluados = [
                e for e in (
                    self._evaluar_expediente(conn, exp_id, corte) for exp_id in expediente_ids
                ) if e is not None
            ]

        eliminables = [e for e in evaluados if e.eliminable]
        bloqueados = [e for e in evaluados if not e.eliminable]

        for bloqueado in bloqueados:
            self._registrar_evento(
                "DEPURADOR_ELIMINACION_BLOQUEADA",
                f"expediente={bloqueado.expediente_id} motivo={bloqueado.motivo} "
                f"detalle={bloqueado.detalle_motivo}",
            )

        if not eliminables:
            self._registrar_evento(
                "DEPURADOR_PURGA_ABORTADA",
                f"tipo=eliminacion causa=nada_eliminable bloqueados={len(bloqueados)} "
                f"solicitada_por={solicitado_por}",
            )
            return ResultadoEliminacion(
                ejecutado=True,
                bloqueados=bloqueados,
                version_politica=self.politica.version,
            )

        ids = [e.expediente_id for e in eliminables]
        self._registrar_evento(
            "DEPURADOR_PURGA_INICIADA",
            f"tipo=eliminacion expedientes={len(ids)} bloqueados={len(bloqueados)} "
            f"politica=v{self.politica.version} solicitada_por={solicitado_por}",
        )

        # 2. Copia de seguridad previa. Si falla, no se ejecuta nada (Regla 5): purgar es
        #    irreversible y una eliminación sin red no es una degradación aceptable.
        try:
            backup = self.memoria.realizar_backup(run_id=self.run_id)
        except Exception as exc:
            motivo = f"copia_seguridad_fallida: {type(exc).__name__}: {exc}"
            self._registrar_evento("DEPURADOR_MODO_DEGRADADO", motivo)
            self._registrar_evento(
                "DEPURADOR_PURGA_ABORTADA", f"tipo=eliminacion causa={motivo}"
            )
            raise CopiaSeguridadFallida(
                "No se pudo crear la copia de seguridad previa, de modo que no se ha "
                f"eliminado nada: {exc}"
            ) from exc

        self._registrar_evento(
            "DEPURADOR_BACKUP_CREADO",
            f"ruta={backup} bytes={os.path.getsize(backup) if os.path.exists(backup) else 0}",
        )

        # 3. Ficheros antes que filas. Al revés perderíamos las rutas al borrar `documentos`
        #    y los PDFs quedarían en disco sin nadie que recordara de quién eran.
        bytes_liberados, ficheros_borrados = self._borrar_ficheros_de(ids)

        # 4. Cascada hoja→raíz en una única transacción, con las claves foráneas activas.
        #    `PRAGMA foreign_keys=OFF` está prohibido en esta capa: el RESTRICT es la red
        #    que impide dejar huérfanos, no un obstáculo a rodear.
        marcadores = ", ".join("?" for _ in ids)
        try:
            with self.memoria.db_lock():
                with self.memoria.conectar() as conn:
                    with conn:
                        cursor = conn.cursor()
                        docs = cursor.execute(
                            f"DELETE FROM documentos WHERE expediente_id IN ({marcadores});", ids
                        ).rowcount or 0
                        analisis = cursor.execute(
                            f"DELETE FROM analisis_semantico WHERE expediente_id IN ({marcadores});",
                            ids,
                        ).rowcount or 0
                        lotes = cursor.execute(
                            f"DELETE FROM lotes WHERE expediente_id IN ({marcadores});", ids
                        ).rowcount or 0
                        expedientes = cursor.execute(
                            f"DELETE FROM expedientes WHERE id IN ({marcadores});", ids
                        ).rowcount or 0

                        self.memoria.registrar_purga(
                            tipo=TIPO_ELIMINACION,
                            solicitada_por=solicitado_por,
                            version_politica=self.politica.version,
                            resultado="COMPLETADA",
                            documentos_purgados=docs,
                            bytes_liberados=bytes_liberados,
                            expedientes_eliminados=expedientes,
                            bloqueados=len(bloqueados),
                            backup_asociado=backup,
                            detalle=json.dumps(
                                {
                                    "expedientes": ids,
                                    "lotes_eliminados": lotes,
                                    "analisis_eliminados": analisis,
                                    "ficheros_borrados": ficheros_borrados,
                                    "bloqueados": [
                                        {"expediente": b.expediente_id, "motivo": b.motivo}
                                        for b in bloqueados
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                            conn=conn,
                        )
        except sqlite3.IntegrityError as exc:
            # La transacción ya revirtió sola. No queda nada a medias.
            motivo = f"integridad_referencial: {exc}"
            self._registrar_evento("DEPURADOR_PURGA_ABORTADA", f"tipo=eliminacion causa={motivo}")
            raise PurgaBloqueadaPorIntegridad(
                "Una clave foránea detuvo la eliminación y se ha revertido entera. Esto "
                f"indica una tabla que apunta al expediente y que la cascada no contempla: {exc}"
            ) from exc

        resultado = ResultadoEliminacion(
            ejecutado=True,
            expedientes_eliminados=expedientes,
            lotes_eliminados=lotes,
            documentos_eliminados=docs,
            analisis_eliminados=analisis,
            ficheros_borrados=ficheros_borrados,
            bytes_liberados=bytes_liberados,
            bloqueados=bloqueados,
            backup_asociado=backup,
            version_politica=self.politica.version,
        )

        self._registrar_evento(
            "DEPURADOR_PURGA_COMPLETADA",
            f"tipo=eliminacion expedientes={expedientes} lotes={lotes} documentos={docs} "
            f"analisis={analisis} bytes={bytes_liberados} bloqueados={len(bloqueados)} "
            f"backup={backup} politica=v{self.politica.version}",
        )
        return resultado

    # -----------------------------------------------------------------------------------
    # La invariante de memoria comercial
    # -----------------------------------------------------------------------------------

    def _evaluar_expediente(
        self, conn, expediente_id: str, corte_cuarentena: str
    ) -> Optional[ExpedienteEvaluado]:
        """Decide si un expediente puede eliminarse, y si no, por qué exactamente.

        Devuelve `None` si el expediente no existe: eliminar algo inexistente se salta sin
        error (idempotencia del contrato), no es un bloqueo que reportar.

        **El estado actual no basta**: un lote puede estar hoy en `Inactiva` habiendo pasado
        por `Presentada` —lo hace `soft_delete_obsoletos()` cada vez que una licitación
        desaparece del feed—. Por eso se miran tres fuentes, y basta una para bloquear.
        """
        expediente = conn.execute(
            "SELECT deleted_at, COALESCE(log_cambios, '') AS log_cambios "
            "FROM expedientes WHERE id = ?;",
            (expediente_id,),
        ).fetchone()
        if expediente is None:
            return None

        lotes = conn.execute(
            "SELECT lote_numero, estado_operativo, "
            + ", ".join(CAMPOS_COMERCIALES)
            + " FROM lotes WHERE expediente_id = ?;",
            (expediente_id,),
        ).fetchall()
        documentos = conn.execute(
            "SELECT COUNT(*) FROM documentos WHERE expediente_id = ?;", (expediente_id,)
        ).fetchone()[0]

        def veredicto(motivo, detalle):
            return ExpedienteEvaluado(
                expediente_id=expediente_id, eliminable=False, motivo=motivo,
                detalle_motivo=detalle, lotes=len(lotes), documentos=documentos,
            )

        # Transición prohibida nº 1: `VIVO → ELIMINADO` directo. Hay que pasar por archivado,
        # que impide borrar algo que está en juego ahora mismo.
        if not expediente["deleted_at"]:
            return veredicto(
                MOTIVO_NO_ARCHIVADO,
                "El expediente sigue vivo. Sólo se elimina lo que ya está archivado.",
            )

        if expediente["deleted_at"] > corte_cuarentena:
            return veredicto(
                MOTIVO_CUARENTENA,
                f"Archivado el {expediente['deleted_at']}, y la política exige "
                f"{self.politica.eliminacion.dias_archivado_minimo} días archivado antes "
                f"de poder eliminarse (no cumple hasta pasado el corte {corte_cuarentena}).",
            )

        # Fuente 1 — el estado en que está ahora cada lote.
        for lote in lotes:
            estado = normalizar_estado_operativo(lote["estado_operativo"])
            if estado in ESTADOS_QUE_BLOQUEAN_ELIMINACION:
                return veredicto(
                    MOTIVO_MEMORIA_COMERCIAL,
                    f"El lote {lote['lote_numero']} está en '{estado}'.",
                )

        # Fuente 2 — el dinero y las horas, que no mienten aunque el estado haya cambiado.
        for lote in lotes:
            for campo in CAMPOS_COMERCIALES:
                valor = lote[campo]
                if valor not in (None, 0, 0.0, ""):
                    return veredicto(
                        MOTIVO_MEMORIA_COMERCIAL,
                        f"El lote {lote['lote_numero']} tiene '{campo}' con valor {valor!r}.",
                    )

        # Fuente 3 — el histórico de estados (H-31). Es la única evidencia de por dónde pasó
        # un lote que hoy figura como caducado, y sin ella un expediente con oferta
        # presentada pero sin costes anotados sería indistinguible de una `Nueva` cualquiera.
        estado_historico = self._estado_bloqueante_en_historico(expediente["log_cambios"])
        if estado_historico:
            return veredicto(
                MOTIVO_MEMORIA_COMERCIAL,
                f"El histórico registra que algún lote pasó por '{estado_historico}'.",
            )

        return ExpedienteEvaluado(
            expediente_id=expediente_id, eliminable=True,
            lotes=len(lotes), documentos=documentos,
        )

    @staticmethod
    def _estado_bloqueante_en_historico(log_cambios: str) -> Optional[str]:
        """Busca en el histórico del expediente cualquier paso por un estado que bloquee.

        Mira los dos extremos de cada transición: haber **salido** de `Presentada` es tanta
        prueba de que hubo oferta como haber entrado.
        """
        for linea in (log_cambios or "").splitlines():
            if MARCA_LOG_ESTADO not in linea:
                continue
            for capturado in _ESTADOS_EN_LOG.findall(linea):
                estado = normalizar_estado_operativo(capturado)
                if estado in ESTADOS_QUE_BLOQUEAN_ELIMINACION:
                    return estado
        return None

    # -----------------------------------------------------------------------------------
    # Internos
    # -----------------------------------------------------------------------------------

    def _corte_cuarentena(self, ahora: datetime) -> str:
        dias = self.politica.eliminacion.dias_archivado_minimo
        return (ahora - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _candidatos(self, conn, expediente_ids: Optional[Sequence[str]]) -> List[str]:
        """Los expedientes a evaluar: los pedidos, o todo lo archivado si no se pide nada."""
        if expediente_ids is not None:
            return list(expediente_ids)
        filas = conn.execute(
            "SELECT id FROM expedientes WHERE deleted_at IS NOT NULL ORDER BY deleted_at;"
        ).fetchall()
        return [fila["id"] for fila in filas]

    def _borrar_ficheros_de(self, expediente_ids: Sequence[str]):
        """Retira del disco los ficheros de los expedientes que van a desaparecer."""
        marcadores = ", ".join("?" for _ in expediente_ids)
        with self.memoria.conectar() as conn:
            rutas = [
                fila[0] for fila in conn.execute(
                    f"SELECT local_path FROM documentos WHERE expediente_id IN ({marcadores}) "
                    "AND local_path IS NOT NULL;",
                    list(expediente_ids),
                ).fetchall()
            ]

        bytes_liberados = 0
        ficheros = 0
        for ruta in rutas:
            if not os.path.exists(ruta):
                continue
            liberado, borrado, error = self._borrar_fichero_y_sidecar(ruta)
            bytes_liberados += liberado
            ficheros += borrado
            if error:
                # No detiene la eliminación: la fila se va igual y el fichero quedaría
                # huérfano, así que se dice en voz alta para poder recogerlo a mano.
                print(f"  [!] [depurador] Fichero no borrado antes de eliminar '{ruta}': {error}")
        return bytes_liberados, ficheros

    def _motivo_para_no_eliminar(self) -> Optional[str]:
        """Precondiciones de la eliminación física."""
        if self.politica is None:
            return (
                "politica_retencion_ausente: no se elimina sin política declarada, y no se "
                "aplican plazos por defecto"
            )
        if self.politica.eliminacion is None:
            return (
                "politica_sin_bloque_eliminacion: config/retencion.yaml no declara el bloque "
                "'eliminacion', de modo que no hay criterio de cuarentena que aplicar"
            )
        return None

    def _borrar_fichero_y_sidecar(self, ruta: str):
        """Borra el PDF y su sidecar de metadatos, midiendo lo liberado **antes** de borrar.

        Devuelve `(bytes_liberados, ficheros_borrados, error)`. El tamaño se toma con el
        fichero todavía en disco porque después ya no hay a quién preguntárselo, y
        `bytes_liberados` es una postcondición del contrato, no un adorno del informe.
        """
        bytes_liberados = 0
        borrados = 0
        try:
            bytes_liberados += os.path.getsize(ruta)
            os.remove(ruta)
            borrados += 1
        except OSError as exc:
            return 0, 0, exc

        sidecar = ruta + ".meta.json"
        if os.path.exists(sidecar):
            try:
                bytes_liberados += os.path.getsize(sidecar)
                os.remove(sidecar)
                borrados += 1
            except OSError as exc:
                # El pliego ya no está: el peso se liberó. Que quede su sidecar de
                # metadatos no invalida la purga, pero se dice.
                print(f"  [!] [depurador] Sidecar no borrado '{sidecar}': {exc}")

        return bytes_liberados, borrados, None

    def _motivo_para_no_purgar(self) -> Optional[str]:
        """Precondiciones de la purga documental. Devuelve la causa, o None si se puede.

        Purgar es irreversible: en caso de duda, la degradación correcta es no hacer nada.
        """
        if self.politica is None:
            return (
                "politica_retencion_ausente: no se purga sin política declarada, y no se "
                "aplican plazos por defecto"
            )

        directorio = directorio_documentos(getattr(self.memoria, "db_path", None))
        if os.path.isdir(directorio) and not self._directorio_escribible(directorio):
            return (
                f"sin_permiso_escritura: no se puede escribir en '{directorio}', de modo "
                "que tampoco se puede garantizar el borrado de sus ficheros"
            )
        return None

    @staticmethod
    def _directorio_escribible(directorio: str) -> bool:
        """Comprueba el permiso escribiendo de verdad, no preguntando.

        `os.access()` miente en Windows: informa del atributo de sólo lectura, no de la ACL
        efectiva. La única comprobación fiable es intentarlo.
        """
        try:
            with tempfile.NamedTemporaryFile(dir=directorio, prefix=".depurador_", suffix=".tmp"):
                return True
        except OSError:
            return False

    def _motivo_para_no_archivar(self) -> Optional[str]:
        """Comprueba las precondiciones. Devuelve la causa concreta, o None si se puede.

        En caso de duda el Depurador no hace nada, al revés que las capas de lectura: allí lo
        correcto era seguir con datos parciales, aquí lo correcto es detenerse.
        """
        if self.politica is None:
            return (
                "politica_retencion_ausente: no se archiva sin política declarada, y no se "
                "aplican plazos por defecto"
            )
        if self.politica.archivado is None:
            return (
                "politica_sin_bloque_archivado: config/retencion.yaml no declara el bloque "
                "'archivado', de modo que no hay criterio que aplicar"
            )
        return None

    def _registrar_evento(self, accion: str, motivo: str) -> None:
        """Traza en `data/pipeline.jsonl` (Regla 3).

        Un fallo de escritura del registro no puede tumbar el pipeline, pero tampoco puede
        pasar inadvertido: se avisa por terminal (Convención C2).
        """
        try:
            self.memoria.registrar_log_json(
                run_id=self.run_id,
                action=accion,
                reason=motivo,
                updated_by="depurador",
            )
        except Exception as exc:
            print(f"[!] No se pudo registrar el evento {accion} del Depurador: {exc}")
