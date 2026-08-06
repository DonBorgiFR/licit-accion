"""
tests/test_centinela_cli.py — Pruebas Unitarias de la Consola CLI del Centinela (Capa 6 - Paso 9)
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
from typing import Tuple
from src.memoria import Memoria

from src.centinela import (
    AlertaBoletinDTO,
    DictamenCentinelaDTO,
    cli_inspeccionar_alerta,
    cli_listar_alertas,
    cli_actualizar_estado_alerta
)

def crear_base_prueba(tmp_path) -> Tuple[str, AlertaBoletinDTO]:
    db_path = os.path.join(str(tmp_path), "test_licitaciones_cli.db")
    memoria = Memoria(db_path=db_path)
    memoria.setup_db()

    dictamen = DictamenCentinelaDTO(
        es_oportunidad_temprana=True,
        nivel_interes="ALTO",
        categoria_fase_temprana="PRESUPUESTO",
        resumen_ejecutivo="Oportunidad previa presupuestaria",
        acciones_recomendadas=["Llamar al ayuntamiento"]
    )
    alerta = AlertaBoletinDTO(
        fuente="DOGC",
        num_boletin="777",
        fecha_publicacion="2026-07-26T08:00:00Z",
        organo_emisor="Ajuntament de Girona",
        municipio="Girona",
        titulo_anuncio="Aprovació inicial del pressupost de Girona 2027",
        seccion_boletin="Anuncis",
        url_anuncio="https://example.com/777",
        texto_sumario="Presupuesto municipal",
        score_temprano=80,
        dictamen_ia=dictamen,
        estado_operativo="NUEVA_FASE_TEMPRANA"
    )
    memoria.guardar_alerta_boletin(alerta)
    return db_path, alerta


def test_cli_inspeccionar_alerta_exito(tmp_path, capsys):
    """Verifica que la inspección CLI muestra la ficha detallada de una alerta existente."""
    db_path, alerta = crear_base_prueba(tmp_path)

    res = cli_inspeccionar_alerta(alerta.id_alerta, db_path=db_path)
    captured = capsys.readouterr()

    assert res is True
    assert "FICHA DE INSPECCIÓN" in captured.out
    assert "Girona" in captured.out
    assert "Score Temprano: 80" in captured.out
    assert "Llamar al ayuntamiento" in captured.out


def test_cli_inspeccionar_alerta_inexistente(tmp_path, capsys):
    """Verifica el comportamiento defensivo al inspeccionar una alerta inexistente."""
    db_path = os.path.join(str(tmp_path), "test_licitaciones_cli.db")
    memoria = Memoria(db_path=db_path)
    memoria.setup_db()

    res = cli_inspeccionar_alerta("id_fantasma_12345", db_path=db_path)
    captured = capsys.readouterr()

    assert res is False
    assert "No se encontró ninguna alerta" in captured.out


def test_cli_listar_alertas(tmp_path, capsys):
    """Verifica el listado de alertas en formato tabla por consola."""
    db_path, alerta = crear_base_prueba(tmp_path)

    cli_listar_alertas(db_path=db_path)
    captured = capsys.readouterr()

    assert "LISTADO DE ALERTAS DE FASE TEMPRANA" in captured.out
    assert "DOGC" in captured.out
    assert "80pts" in captured.out


def test_cli_actualizar_estado_alerta(tmp_path):
    """Verifica la actualización del estado operativo de una alerta desde CLI."""
    db_path, alerta = crear_base_prueba(tmp_path)

    res_upd = cli_actualizar_estado_alerta(
        id_alerta=alerta.id_alerta,
        nuevo_estado="EN_ESTUDIO_PROACTIVO",
        notas="Reunión comercial agendada",
        db_path=db_path
    )
    assert res_upd is True

    memoria = Memoria(db_path=db_path)
    alerta_actualizada = memoria.obtener_alerta_boletin(alerta.id_alerta)

    assert alerta_actualizada.estado_operativo == "EN_ESTUDIO_PROACTIVO"
    assert alerta_actualizada.notas_usuario == "Reunión comercial agendada"
