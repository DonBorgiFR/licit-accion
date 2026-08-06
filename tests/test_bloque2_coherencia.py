"""Regresiones del contrato de coherencia LCSP de la beta."""

from src.analista import (
    AnalisisSemanticoDTO,
    ClausulasSocialesDTO,
    CriteriosAdjudicacionDTO,
    DictamenIA,
    GarantiaDefinitivaDTO,
    PenalidadesDTO,
    RevisionPreciosDTO,
    SubrogacionDTO,
)
from src.filtro import Filtro
from src.radar import Radar


def test_radar_no_confunde_negaciones_ni_revision_de_oficio():
    radar = Radar()
    assert radar._detectar_subrogacion_preliminar("No procedeix la subrogació de personal") is False
    assert radar._detectar_subrogacion_preliminar("Sin obligación de subrogación") is False
    assert radar._detectar_subrogacion_preliminar("Subrogación de 12 trabajadores") is True
    assert radar._detectar_revision_precios_preliminar("Revisión de oficio del acuerdo") is False
    assert radar._detectar_revision_precios_preliminar("Sin revisión de precios") is False
    assert radar._detectar_revision_precios_preliminar("Se admite revisión de precios por IPC") is True


def test_filtro_publica_score_canonico_y_no_penaliza_senal_preliminar():
    filtro = Filtro()
    base = {
        "titulo": "Servicio educativo municipal",
        "organo": "Ajuntament de Mataró",
        "importe": 150000.0,
        "vec": 150000.0,
        "tipo_contrato_codigo": "2",
        "estado": "PUB",
        "cpvs": ["80110000"],
        "fecha_limite": "2099-12-31",
        "procedimiento_codigo": "1",
        "country_subentity_code": "ES511",
        "localidad": "Mataró",
    }
    sin_senal = filtro.filtrar(base)
    con_senal = filtro.filtrar({**base, "subrogacion_detectada": True, "revision_precios_detectada": False})
    assert 0 <= sin_senal["score"] <= 100
    assert sin_senal["score"] == con_senal["score"]
    assert con_senal["score_bruto"] > 0


def test_dto_v3_preserva_las_seis_clausulas_criticas():
    dto = AnalisisSemanticoDTO(
        subrogacion=SubrogacionDTO(),
        revision_precios=RevisionPreciosDTO(),
        criterios=CriteriosAdjudicacionDTO(),
        dictamen=DictamenIA(),
        garantia_definitiva=GarantiaDefinitivaDTO(requerida=True, porcentaje=5.0, modalidad="seguro de caución"),
        penalidades=PenalidadesDTO(existen=True, riesgo_evaluado="ALTO"),
        clausulas_sociales=ClausulasSocialesDTO(existen=True, ventaja_incoop=True),
    )
    recuperado = AnalisisSemanticoDTO.from_json(dto.to_json())
    assert recuperado.version_esquema == 3
    assert recuperado.garantia_definitiva.modalidad == "seguro de caución"
    assert recuperado.penalidades.riesgo_evaluado == "ALTO"
    assert recuperado.clausulas_sociales.ventaja_incoop is True


def test_los_kpis_de_cabecera_y_de_desglose_cuentan_la_misma_poblacion(tmp_path):
    """
    Regresión de H-21, hermano del H-08 ya cerrado: `total_expedientes` hacía un COUNT(*)
    plano sobre `expedientes`, tabla que NO tiene `deleted_at` —el archivado lógico vive en
    `lotes`—, mientras que el resto del panel filtraba los archivados. El Cockpit anunciaba
    "51 Expedientes" encima de un desglose que sumaba 22 lotes.

    Un expediente cuyos lotes están todos archivados es un expediente archivado.
    """
    import os
    from src.memoria import Memoria

    memoria = Memoria(db_path=os.path.join(str(tmp_path), "kpis.db"))
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            for i in (1, 2):
                conn.execute(
                    "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta) VALUES (?, ?, ?, ?);",
                    (f"EXP-{i}", f"Servicio {i}", "Ajuntament de Prova", "2026-08-06T08:00:00Z")
                )
            # EXP-1 sigue vivo; EXP-2 tiene su único lote archivado.
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, estado_operativo) VALUES (?, ?, ?, ?, ?);",
                ("EXP-1", 1, "Lote vivo", 100000.0, "Nueva")
            )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, estado_operativo, deleted_at) VALUES (?, ?, ?, ?, ?, ?);",
                ("EXP-2", 1, "Lote archivado", 50000.0, "Nueva", "2026-08-06T08:00:00Z")
            )

    kpis = memoria.obtener_resumen_kpis()

    assert kpis["total_expedientes"] == 1, "El expediente con todos sus lotes archivados no debe contar"
    assert kpis["total_lotes"] == 1
    # El volumen licitado responde a la misma población: 100.000 del lote vivo, sin los
    # 50.000 del archivado.
    assert kpis["volumen_total_pbl"] == 100000.0


def test_el_funnel_no_lista_expedientes_archivados(tmp_path):
    """
    Regresión de H-22, detectado al abrir el Cockpit contra la base real. La subconsulta de
    lotes filtraba `deleted_at IS NULL`, pero el LEFT JOIN dejaba pasar igualmente los
    expedientes sin ningún lote vivo: llegaban con todos los campos a NULL y se pintaban como
    filas de "0 € y 0 pts".

    En la base de trabajo eran 29 expedientes archivados mezclados con 22 vivos: la tabla con
    la que se decide a qué concurso presentarse mostraba más del doble de los reales.
    """
    import os
    from src.memoria import Memoria

    memoria = Memoria(db_path=os.path.join(str(tmp_path), "funnel.db"))
    memoria.setup_db()

    with memoria.conectar() as conn:
        with conn:
            for i in (1, 2):
                conn.execute(
                    "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta) VALUES (?, ?, ?, ?);",
                    (f"EXP-{i}", f"Servicio {i}", "Ajuntament de Prova", "2026-08-06T08:00:00Z")
                )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, estado_operativo) VALUES (?, ?, ?, ?, ?);",
                ("EXP-1", 1, "Lote vivo", 100000.0, "Nueva")
            )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, pbl, estado_operativo, deleted_at) VALUES (?, ?, ?, ?, ?, ?);",
                ("EXP-2", 1, "Lote archivado", 50000.0, "Nueva", "2026-08-06T08:00:00Z")
            )

    filas, total = memoria.listar_expedientes_paginados(page=1, limit=50)

    assert total == 1, "El expediente con todos sus lotes archivados no debe aparecer en el funnel"
    assert [f["id"] for f in filas] == ["EXP-1"]
