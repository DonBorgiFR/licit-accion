"""El Depurador — Capa 9: motor de archivado (Paso 4) y de purga documental (Paso 5).

Dos de las tres operaciones del contrato, en orden creciente de daño posible:

* **Archivar** no borra nada. Escribe `deleted_at` y `deleted_reason`, con lo que el lote sale
  del canal principal del Funnel pero sigue en la base, sigue contando en los KPIs históricos
  y puede rescatarse vaciando esa columna.
* **Purgar peso documental** sí es irreversible, pero sólo sobre el peso: borra el PDF del
  disco y vacía `texto_extraido`. La fila del documento permanece con su URL, su hash y su
  rastro —se sabe qué hubo y por qué ya no está— y **ninguna fila de negocio se toca**.

Falta la tercera, la eliminación física de filas, que es la única capaz de destruir memoria
comercial y por eso exige confirmación explícita. Vive en el Paso 6.

**Lo que este motor tiene prohibido**, según `.agents/CONTRATO_CAPA_9.md`:

* Escribir en `estado_operativo`. No es su columna. Un expediente adjudicado sigue adjudicado
  después de archivarse; lo que pierde es presencia en pantalla, no condición de negocio.
* Borrar una sola fila. Purgar libera peso, no registros.
* Desarchivar. El rescate `ARCHIVADO → VIVO` existe, pero lo pide una persona: si un criterio
  automático archivara y otro criterio automático desarchivara, el sistema oscilaría sin que
  nadie se enterase.
* Inventarse plazos. Sin política declarada no se archiva ni se purga, y se dice en voz alta.
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src import ruta_datos
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


#: Vocabulario de la columna `purgas.tipo`, declarado en el DDL del esquema v6. Se usa el
#: declarado y no uno nuevo: inventar un estado que nadie más consulta es exactamente el
#: defecto que H-33 documentó, y esta capa no puede permitírselo en su propia auditoría.
TIPO_PURGA_DOCUMENTAL = "DOCUMENTAL"

#: La rotación de copias es parte de la Operación 2 del contrato ("documentos purgados,
#: bytes liberados, **copias rotadas**"), pero ocurre en otro momento del pipeline: después
#: de crear la copia nueva. Comparte tipo y se distingue por este campo del detalle.
OPERACION_DOCUMENTOS = "documentos"
OPERACION_ROTACION_COPIAS = "rotacion_copias"


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
    """Motor de ciclo de vida del dato: archiva (Paso 4) y purga peso documental (Paso 5).

    Le falta la tercera operación del contrato, la eliminación física de filas, que es la
    única irreversible sobre la memoria comercial y vive en el Paso 6.
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

    # -----------------------------------------------------------------------------------
    # Internos
    # -----------------------------------------------------------------------------------

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

        directorio = ruta_datos("documents")
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
