"""El Depurador — Capa 9, Paso 4: motor de archivado.

Primer código del Depurador propiamente dicho, y deliberadamente el más inofensivo de sus
tres motores: **archivar no borra nada**. Escribe `deleted_at` y `deleted_reason`, con lo que
el lote sale del canal principal del Funnel pero sigue en la base, sigue contando en los KPIs
históricos y puede rescatarse vaciando esa columna. Purgar documentos (Paso 5) y eliminar
filas (Paso 6) son irreversibles; esto no.

**Lo que este motor tiene prohibido**, según `.agents/CONTRATO_CAPA_9.md`:

* Escribir en `estado_operativo`. No es su columna. Un expediente adjudicado sigue adjudicado
  después de archivarse; lo que pierde es presencia en pantalla, no condición de negocio.
* Tocar un solo fichero del disco. Eso es el Paso 5.
* Desarchivar. El rescate `ARCHIVADO → VIVO` existe, pero lo pide una persona: si un criterio
  automático archivara y otro criterio automático desarchivara, el sistema oscilaría sin que
  nadie se enterase.
* Inventarse plazos. Sin política declarada no se archiva, y se dice en voz alta.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from src.memoria import Memoria
from src.retencion import PoliticaRetencion

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


class Depurador:
    """Motor de ciclo de vida del dato. En el Paso 4 sólo sabe archivar."""

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
    # Internos
    # -----------------------------------------------------------------------------------

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
