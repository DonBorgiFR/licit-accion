"""Regresiones de H-45 — Capa 10, Paso 9, bloque E: el Centinela deja de estar ciego.

Contrato: `.agents/CONTRATO_PASO_9.md`, Operación 4.

**El defecto que esto protege.** Un canal vacío tiene tres causas que no se parecen en nada —no
hay novedades, no se pudo consultar, nadie está mirando— y en pantalla se veían las tres igual.
Medido el 2026-08-27: **26 descargas degradadas de 27** y `boletines_alertas` con 0 filas,
mientras el Cockpit enseñaba un `0` que se lee como *«no hay oportunidades»*. Es la familia de
H-21: no rompe nada, y una persona concluye lo contrario de lo que pasa.

**La prueba que más importa es `test_una_fuente_apagada_deja_constancia`**: apagar una fuente
sin decirlo es sustituir un silencio por otro.
"""

import json

import pytest

from src.centinela import IngestorBoletines
from src.diagnostico import estado_de_las_fuentes


def rastro(tmp_path, eventos):
    ruta = tmp_path / "pipeline.jsonl"
    ruta.write_text(
        "\n".join(json.dumps({"esquema": 1, **e}) for e in eventos) + "\n", encoding="utf-8"
    )
    return str(ruta)


def evento(nombre, fuente, cuando, estado="INFO", **datos):
    return {"timestamp": cuando, "run_id": None, "componente": "centinela",
            "evento": nombre, "estado": estado, "datos": {"fuente": fuente, **datos}}


# ==============================================================================
# Las tres causas de un canal vacío, separadas
# ==============================================================================


def test_las_tres_causas_de_un_canal_vacio_se_distinguen(tmp_path):
    ruta = rastro(tmp_path, [
        evento("boletin_fetch_succeeded", "BOPB", "2026-08-27T07:00:00Z", total_alertas=53),
        evento("boletin_fetch_degraded", "DOGC", "2026-08-27T07:00:01Z",
               estado="DEGRADADO", error="HTTP Error 404: Not Found"),
        evento("boletin_fetch_omitido", "BOE", "2026-08-27T07:00:02Z",
               motivo="fuente desactivada en config/centinela_config.yaml"),
    ])

    por_nombre = {f.fuente: f for f in estado_de_las_fuentes(ruta_rastro=ruta)}

    assert por_nombre["BOPB"].estado == "OK"
    assert por_nombre["BOPB"].alertas == 53
    assert por_nombre["DOGC"].estado == "DEGRADADA"
    assert "404" in por_nombre["DOGC"].detalle
    assert por_nombre["BOE"].estado == "OMITIDA"
    assert "desactivada" in por_nombre["BOE"].detalle


def test_una_fuente_configurada_sin_rastro_no_se_omite(tmp_path):
    """No aparecer sería el cuarto silencio. Una fuente de la que no consta nada, se dice."""
    ruta = rastro(tmp_path, [
        evento("boletin_fetch_succeeded", "BOPB", "2026-08-27T07:00:00Z", total_alertas=1),
    ])

    por_nombre = {f.fuente: f for f in
                  estado_de_las_fuentes(fuentes_esperadas=["bopb", "dogc"], ruta_rastro=ruta)}

    assert por_nombre["DOGC"].estado == "SIN_DATOS"
    assert por_nombre["DOGC"].cuando is None


def test_manda_la_consulta_mas_reciente(tmp_path):
    """Que ayer fallara no importa si hoy funcionó, y al revés importa mucho."""
    ruta = rastro(tmp_path, [
        evento("boletin_fetch_succeeded", "BOPB", "2026-08-26T07:00:00Z", total_alertas=40),
        evento("boletin_fetch_degraded", "BOPB", "2026-08-27T07:00:00Z",
               estado="DEGRADADO", error="HTTP Error 500"),
    ])

    bopb = estado_de_las_fuentes(ruta_rastro=ruta)[0]

    assert bopb.estado == "DEGRADADA"
    assert bopb.cuando == "2026-08-27T07:00:00Z"


def test_un_arranque_sin_desenlace_no_dice_nada_de_la_fuente(tmp_path):
    """`boletin_fetch_started` informa de un proceso muerto, no del estado de la fuente.

    Es justo el evento que quedó suelto en la corrida que reventó (H-41): tomarlo por un
    desenlace haría que una fuente pareciera consultada cuando el proceso murió intentándolo.
    """
    ruta = rastro(tmp_path, [
        evento("boletin_fetch_started", "BOPB", "2026-08-27T07:00:00Z", url="https://x"),
    ])

    por_nombre = {f.fuente: f for f in
                  estado_de_las_fuentes(fuentes_esperadas=["bopb"], ruta_rastro=ruta)}

    assert por_nombre["BOPB"].estado == "SIN_DATOS"


def test_un_rastro_ausente_no_revienta(tmp_path):
    fuentes = estado_de_las_fuentes(fuentes_esperadas=["bopb"],
                                    ruta_rastro=str(tmp_path / "no_existe.jsonl"))

    assert [f.estado for f in fuentes] == ["SIN_DATOS"]


# ==============================================================================
# Apagar una fuente no puede ser otro silencio
# ==============================================================================


def test_una_fuente_apagada_deja_constancia(tmp_path, monkeypatch):
    """**La prueba central del bloque.** Hasta el 2026-08-27 devolvía `[]` sin decir nada.

    Misma doctrina que el código `30` del lanzador: ni éxito ni avería, **omisión deliberada, y
    consta**. Sin este evento, «la tengo apagada» y «no hay novedades» vuelven a ser la misma
    pantalla.
    """
    destino = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr("src.centinela.ruta_datos", lambda *p: str(tmp_path.joinpath(*p)))

    ingestor = IngestorBoletines()
    ingestor.config.setdefault("fuentes_oficiales", {}).setdefault("dogc", {})["activo"] = False

    assert ingestor.obtener_feed_dogc() == []

    from src.rastro import leer_rastro

    eventos = leer_rastro(ruta=str(destino)).eventos
    omisiones = [e for e in eventos if e.evento == "boletin_fetch_omitido"]
    assert omisiones, "apagar una fuente en silencio es sustituir un silencio por otro"
    assert omisiones[0].datos["fuente"] == "DOGC"
    assert "desactivada" in omisiones[0].datos["motivo"]


def test_una_fuente_activa_sin_url_tambien_consta(tmp_path, monkeypatch):
    """Una configuración a medias no puede parecerse a una fuente sana y sin novedades."""
    destino = tmp_path / "pipeline.jsonl"
    monkeypatch.setattr("src.centinela.ruta_datos", lambda *p: str(tmp_path.joinpath(*p)))

    ingestor = IngestorBoletines()
    ingestor.config.setdefault("fuentes_oficiales", {})["bopb"] = {"activo": True}

    assert ingestor.obtener_feed_bopb() == []

    from src.rastro import leer_rastro

    omisiones = [e for e in leer_rastro(ruta=str(destino)).eventos
                 if e.evento == "boletin_fetch_omitido"]
    assert omisiones and "url_feed" in omisiones[0].datos["motivo"]
    assert omisiones[0].estado.value == "WARNING"


# ==============================================================================
# La configuración vigente, que es lo que se decidió el 2026-08-27
# ==============================================================================


def test_el_dogc_esta_desactivado_y_conserva_su_url():
    """Decisión de dirección del 2026-08-27: el DOGC ya no publica RSS.

    La URL se conserva a propósito —documenta qué se intentaba y permite reactivar la fuente
    cambiando una línea—, así que la prueba comprueba las dos cosas a la vez.
    """
    fuentes = IngestorBoletines().config.get("fuentes_oficiales", {})

    assert fuentes["dogc"]["activo"] is False
    assert fuentes["dogc"]["url_feed"], "la URL se conserva como documentación"


def test_el_bopb_apunta_al_feed_vigente():
    """La anterior, `https://bop.diba.cat/rss`, devolvía 500 desde antes del 2026-08-18."""
    bopb = IngestorBoletines().config["fuentes_oficiales"]["bopb"]

    assert bopb["activo"] is True
    assert bopb["url_feed"] == "https://bop.diba.cat/dades-obertes/butlleti-del-dia/feed"


# ==============================================================================
# H-57 — un análisis degradado no puede borrar la alerta de la cabecera
# ==============================================================================


def test_una_alerta_con_analisis_diferido_sigue_contando(tmp_path):
    """Convención C6: lo que no se pudo medir no puntúa **en ninguna dirección**.

    Detectado al cerrar el Paso 9 mirando la pantalla (C7): el KPI «Canal Centinela» decía `0`
    mientras la tabla de debajo enseñaba 5 alertas. Estaban en `ANALISIS_DIFERIDO_BOLETIN` —el
    LLM no pudo dictaminar, H-56— y el contador sólo miraba dos estados. Es la misma forma del
    defecto que C6 documenta: un fallo de análisis hacía **desaparecer** la alerta.
    """
    from src.memoria import Memoria

    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    with memoria.conectar() as conn:
        with conn:
            for n, estado in enumerate(
                ["NUEVA_FASE_TEMPRANA", "EN_ESTUDIO_PROACTIVO",
                 "ANALISIS_DIFERIDO_BOLETIN", "DESCARTADA_POR_REGLAS"]
            ):
                conn.execute(
                    "INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, "
                    "fecha_publicacion, organo_emisor, titulo_anuncio, estado_operativo, "
                    "score_temprano, fecha_ingesta, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?);",
                    (f"id-{n}", "BOPB", f"BOPB-{n}", "2026-08-27T07:00:00Z",
                     "Ajuntament de prueba", f"Anuncio {n}", estado, 40,
                     "2026-08-27T07:00:00Z", "2026-08-27T07:00:00Z"),
                )

    kpis = memoria.obtener_resumen_kpis()

    assert kpis["alertas_tempranas_activas"] == 3, (
        "las tres vivas cuentan; sólo la descartada por reglas queda fuera"
    )
