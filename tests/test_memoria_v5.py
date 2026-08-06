"""
tests/test_memoria_v5.py — Pruebas Unitarias de Persistencia SQLite Esquema v5 (Capa 6 - Paso 2)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import sqlite3
import pytest
from src.memoria import Memoria
from src.centinela import AlertaBoletinDTO, DictamenCentinelaDTO


@pytest.fixture
def tmp_db_path(tmp_path):
    """Fixture que proporciona una ruta a un archivo de BD temporal."""
    return str(tmp_path / "licitaciones_test_v5.db")


def test_inicializacion_limpia_v5(tmp_db_path):
    """Verifica que setup_db() crea una base de datos nueva en versión de Esquema 5."""
    memoria = Memoria(db_path=tmp_db_path)
    memoria.setup_db()

    with memoria.conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM metadata LIMIT 1;")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 5

        # Verificar existencia de la tabla boletines_alertas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boletines_alertas';")
        assert cursor.fetchone() is not None

        # Verificar vista analítica vista_alertas_tempranas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='vista_alertas_tempranas';")
        assert cursor.fetchone() is not None


def test_migracion_desde_v4_a_v5(tmp_db_path):
    """Verifica la migración automática y segura desde un esquema v4 preexistente a v5."""
    from src.memoria import (
        SQL_CREATE_METADATA, SQL_CREATE_EXPEDIENTES, SQL_CREATE_LOTES,
        SQL_CREATE_DOCUMENTOS, SQL_CREATE_ANALISIS_SEMANTICO
    )
    # 1. Crear una base de datos simulada en esquema v4 sin boletines_alertas
    conn = sqlite3.connect(tmp_db_path)
    with conn:
        conn.execute(SQL_CREATE_METADATA)
        conn.execute("INSERT INTO metadata VALUES (4);")
        conn.execute(SQL_CREATE_EXPEDIENTES)
        conn.execute(SQL_CREATE_LOTES)
        conn.execute(SQL_CREATE_DOCUMENTOS)
        conn.execute(SQL_CREATE_ANALISIS_SEMANTICO)
    conn.close()

    # 2. Instanciar Memoria y ejecutar setup_db() (debe migrar a v5)
    memoria = Memoria(db_path=tmp_db_path)
    memoria.setup_db()



    with memoria.conectar() as conn_check:
        cursor = conn_check.cursor()
        cursor.execute("SELECT version FROM metadata LIMIT 1;")
        assert cursor.fetchone()[0] == 5

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='boletines_alertas';")
        assert cursor.fetchone() is not None


def test_crud_alerta_boletin(tmp_db_path):
    """Verifica las operaciones DAO de guardar, obtener y listar AlertaBoletinDTO."""
    memoria = Memoria(db_path=tmp_db_path)
    memoria.setup_db()

    dictamen = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="PRESUPUESTO",
        resumen_ejecutivo="Dotación de 300k€ para equipamiento juvenil.",
        acciones_recomendadas=["Presentar candidatura"],
        estimacion_meses_hasta_licitacion=3
    )

    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="9500",
        fecha_publicacion="2026-07-26T12:00:00Z",
        organo_emisor="Ajuntament de Girona",
        municipio="Girona",
        titulo_anuncio="Aprovació inicial del pressupost per a serveis de joventut",
        score_temprano=85,
        motivos_score=["+40 Afinidad Temática"],
        dictamen_ia=dictamen,
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )

    # 1. Guardar
    res = memoria.guardar_alerta_boletin(alerta)
    assert res is True

    # 2. Obtener por id_alerta
    recuperada = memoria.obtener_alerta_boletin(alerta.id_alerta)
    assert recuperada is not None
    assert recuperada.id_alerta == alerta.id_alerta
    assert recuperada.fuente == "DOGC"
    assert recuperada.num_boletin == "9500"
    assert recuperada.organo_emisor == "Ajuntament de Girona"
    assert recuperada.dictamen_ia is not None
    assert recuperada.dictamen_ia.nivel_interes == "ALTO"

    # 3. Listar
    lista = memoria.listar_alertas_tempranas(fuente="DOGC")
    assert len(lista) == 1
    assert lista[0].id_alerta == alerta.id_alerta


def test_vinculacion_y_actualizacion_estado(tmp_db_path):
    """Verifica la actualización de estado y vinculación relacional con licitaciones de expedientes."""
    memoria = Memoria(db_path=tmp_db_path)
    memoria.setup_db()

    # Insertar expediente simulado
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, fecha_ingesta) VALUES (?, ?, ?);",
                ("EXP-2026-001", "Licitació de Casal de Joventut", "2026-07-26T12:00:00Z")
            )

    alerta = AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="2026-1234",
        fecha_publicacion="2026-07-20T10:00:00Z",
        organo_emisor="Diputació de Barcelona",
        municipio="Mataró",
        titulo_anuncio="Bases reguladores per a serveis comunitaris",
        estado_operativo="EN_ESTUDIO_PROACTIVO"
    )
    memoria.guardar_alerta_boletin(alerta)

    # Vincular a expediente
    ok_vinc = memoria.vincular_alerta_a_expediente(alerta.id_alerta, "EXP-2026-001")
    assert ok_vinc is True

    alerta_actualizada = memoria.obtener_alerta_boletin(alerta.id_alerta)
    assert alerta_actualizada.expediente_licitacion_vinculado == "EXP-2026-001"
    assert alerta_actualizada.estado_operativo == "CONVERTIDA_A_LICITACION"

    # Cambiar estado manualmente
    ok_est = memoria.actualizar_estado_alerta_boletin(alerta.id_alerta, "EN_ESTUDIO_PROACTIVO", notas="Revisado con EspaiTRES")
    assert ok_est is True
    
    alerta_notas = memoria.obtener_alerta_boletin(alerta.id_alerta)
    assert alerta_notas.estado_operativo == "EN_ESTUDIO_PROACTIVO"
    assert alerta_notas.notas_usuario == "Revisado con EspaiTRES"


def test_healthcheck_v5(tmp_db_path):
    """Verifica que healthcheck_memoria() reporta OK en esquema v5."""
    memoria = Memoria(db_path=tmp_db_path)
    memoria.setup_db()

    hc = memoria.healthcheck_memoria()
    assert hc["status"] == "OK"
    assert hc["version_actual"] == 5
    assert "boletines_alertas" in hc["tablas_detectadas"]
