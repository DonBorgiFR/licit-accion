"""Regresiones del lector canónico del rastro — Capa 10, Paso 9, bloque B.

Contrato: `.agents/CONTRATO_PASO_9.md`, sección F, Operación 1.

**Qué se afirma aquí y qué no.** Estas pruebas usan rastros sintéticos, porque una prueba que
dependiera de `data/pipeline.jsonl` real fallaría en un clon limpio y cambiaría de resultado
cada mañana. La verificación contra el fichero real —que es la que cierra el bloque— vive en
`tools/verificar_rastro_real.py`, fuera de la suite, por la misma doctrina de la Convención C5
que sacó de aquí las llamadas al LLM.

**La prueba que de verdad importa es `test_una_linea_rota_se_cuenta_y_degrada`.** Todo lo demás
es traducción; eso es la invariante. Un lector que saltara las líneas rotas en silencio pasaría
las otras dieciocho pruebas de este fichero.
"""

import json
from datetime import datetime, timezone

import pytest

from src.rastro import (
    CATALOGO_HISTORICO,
    EstadoEvento,
    Gramatica,
    RastroIlegible,
    leer_rastro,
)


def escribir(ruta, lineas):
    """Escribe un rastro sintético. Las líneas son texto crudo: así se pueden partir a mano."""
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return str(ruta)


# ==============================================================================
# Las cuatro gramáticas
# ==============================================================================


def test_gramatica_a_action(tmp_path):
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:29:10Z", "run_id": 16, "action": "run_end",
        "updated_by": "radar", "reason": "success", "duration_ms": 63268,
    })])
    evento = leer_rastro(ruta=ruta).eventos[0]

    assert evento.gramatica is Gramatica.A
    assert evento.componente == "radar"
    assert evento.evento == "run_end"
    assert evento.run_id == 16
    assert evento.datos == {"reason": "success", "duration_ms": 63268}


def test_gramatica_b_tipo_evento(tmp_path):
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-26T11:44:41.656495+00:00", "modulo": "api",
        "tipo_evento": "API_KPIS_FETCHED", "estado": "INFO",
        "payload": {"total_expedientes": 41},
    })])
    evento = leer_rastro(ruta=ruta).eventos[0]

    assert evento.gramatica is Gramatica.B
    assert evento.componente == "api"
    assert evento.evento == "API_KPIS_FETCHED"
    assert evento.datos == {"total_expedientes": 41}


def test_gramatica_c_event_del_analista(tmp_path):
    """La gramática del analista vuelca sus claves en la raíz; todas deben acabar en `datos`."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:29:02Z", "event": "SCORE_RECALIBRATED",
        "expediente_id": "26/2026", "score_original": 47.0, "score_recalibrado": 52.0,
    })])
    evento = leer_rastro(ruta=ruta).eventos[0]

    assert evento.gramatica is Gramatica.C
    assert evento.componente == "analista"
    assert evento.evento == "SCORE_RECALIBRATED"
    assert evento.datos["expediente_id"] == "26/2026"
    assert evento.datos["score_recalibrado"] == 52.0
    assert "timestamp" not in evento.datos


def test_gramatica_d_es_la_que_acoto_h41(tmp_path):
    """La gramática de 105 líneas, la minoritaria, y la que localizó la muerte del pipeline.

    Un lector que sólo hablara `action` la habría descartado en silencio. Ver la sección B.1
    del contrato.
    """
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:29:03Z", "componente": "centinela",
        "evento": "boletin_fetch_started",
        "detalles": {"fuente": "DOGC", "url": "https://dogc.gencat.cat/es/rss/index.html"},
    })])
    evento = leer_rastro(ruta=ruta).eventos[0]

    assert evento.gramatica is Gramatica.D
    assert evento.componente == "centinela"
    assert evento.evento == "boletin_fetch_started"
    assert evento.datos["fuente"] == "DOGC"


def test_las_cuatro_gramaticas_conviven_y_se_cuentan(tmp_path):
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "action": "run_start",
                    "run_id": 16, "updated_by": "radar"}),
        json.dumps({"timestamp": "2026-08-27T05:00:01Z", "modulo": "api",
                    "tipo_evento": "API_KPIS_FETCHED", "estado": "INFO", "payload": {}}),
        json.dumps({"timestamp": "2026-08-27T05:00:02Z", "event": "PROMPT_GENERATED"}),
        json.dumps({"timestamp": "2026-08-27T05:00:03Z", "componente": "centinela",
                    "evento": "boletin_fetch_started", "detalles": {}}),
    ])
    resultado = leer_rastro(ruta=ruta)

    assert resultado.lineas_totales == 4
    assert resultado.gramaticas == {"A": 1, "B": 1, "C": 1, "D": 1}
    assert not resultado.degradado


def test_la_linea_canonica_no_se_confunde_con_la_gramatica_d(tmp_path):
    """Las dos tienen `componente` y `evento`: lo que las separa es `esquema`, y por eso existe."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "esquema": 1, "timestamp": "2026-08-27T05:29:06Z", "run_id": 16,
        "componente": "centinela", "evento": "boletin_fetch_degraded",
        "estado": "DEGRADADO", "datos": {"fuente": "DOGC"},
    })])
    evento = leer_rastro(ruta=ruta).eventos[0]

    assert evento.gramatica is Gramatica.CANONICA
    assert evento.estado is EstadoEvento.DEGRADADO


# ==============================================================================
# La invariante: ninguna línea desaparece en silencio
# ==============================================================================


def test_una_linea_rota_se_cuenta_y_degrada(tmp_path):
    """**La prueba central del bloque.** Es H-39 en su forma peor y H-55 en su forma viva.

    El fragmento reproduce una de las 14 líneas partidas reales: una escritura de la API cortada
    a media clave, sin su principio.
    """
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "action": "run_start",
                    "run_id": 16, "updated_by": "radar"}),
        's": 69.11}}',
        json.dumps({"timestamp": "2026-08-27T05:00:02Z", "action": "run_end",
                    "run_id": 16, "updated_by": "radar"}),
    ])
    resultado = leer_rastro(ruta=ruta)

    assert resultado.lineas_totales == 3, "la línea rota sigue siendo una línea del fichero"
    assert resultado.lineas_ilegibles == 1
    assert resultado.numeros_ilegibles == [2], "hay que poder ir a mirarla"
    assert resultado.degradado is True
    assert len(resultado.eventos) == 2


def test_un_json_valido_que_no_es_objeto_cuenta_como_ilegible(tmp_path):
    """Parsea, pero no puede ser un evento. Fabricarle uno vacío sería inventar una entrada."""
    ruta = escribir(tmp_path / "r.jsonl", ['"esto es una cadena suelta"', "42"])
    resultado = leer_rastro(ruta=ruta)

    assert resultado.lineas_ilegibles == 2
    assert resultado.eventos == []
    assert resultado.degradado is True


def test_una_gramatica_desconocida_se_conserva_entera(tmp_path):
    """No se descarta —perdería rastro— y no se le inventa un nombre."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:00:00Z", "algo": "que nadie ha visto nunca",
    })])
    resultado = leer_rastro(ruta=ruta)

    assert resultado.lineas_ilegibles == 0
    evento = resultado.eventos[0]
    assert evento.gramatica is Gramatica.DESCONOCIDA
    assert evento.estado is EstadoEvento.DESCONOCIDO
    assert evento.datos == {"algo": "que nadie ha visto nunca"}


def test_las_lineas_en_blanco_no_cuentan_como_nada(tmp_path):
    ruta = tmp_path / "r.jsonl"
    ruta.write_text(
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "action": "run_start",
                    "run_id": 1, "updated_by": "radar"}) + "\n\n\n",
        encoding="utf-8",
    )
    resultado = leer_rastro(ruta=str(ruta))

    assert resultado.lineas_totales == 1
    assert resultado.lineas_ilegibles == 0


# ==============================================================================
# El catálogo, y la Convención C3
# ==============================================================================


def test_el_catalogo_traduce_los_ocho_nombres_declarados(tmp_path):
    lineas = [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "componente": "centinela",
                    "evento": nombre, "detalles": {}})
        for nombre in CATALOGO_HISTORICO
    ]
    eventos = leer_rastro(ruta=escribir(tmp_path / "r.jsonl", lineas)).eventos

    for evento in eventos:
        assert evento.estado is CATALOGO_HISTORICO[evento.evento]
        assert evento.estado is not EstadoEvento.DESCONOCIDO


def test_no_se_olfatea_la_cadena_del_nombre(tmp_path):
    """**Convención C3.** Un nombre que contiene «degrad» pero no está catalogado es DESCONOCIDO.

    Es la diferencia entre un catálogo declarado y una heurística de texto: la heurística
    clasificaría mañana un evento que nadie ha revisado; el catálogo admite que no lo sabe.
    """
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "componente": "centinela",
                    "evento": "boletin_fetch_degraded_v2", "detalles": {}}),
        json.dumps({"timestamp": "2026-08-27T05:00:01Z", "action": "algo_failed",
                    "run_id": 1, "updated_by": "radar"}),
    ])
    eventos = leer_rastro(ruta=ruta).eventos

    assert all(e.estado is EstadoEvento.DESCONOCIDO for e in eventos)


def test_un_evento_historico_sin_catalogar_no_se_da_por_bueno(tmp_path):
    """`DESCONOCIDO` no es `INFO`. Convención C6: lo que no se pudo medir no puntúa."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:00:00Z", "action": "run_start",
        "run_id": 1, "updated_by": "radar",
    })])
    assert leer_rastro(ruta=ruta).eventos[0].estado is EstadoEvento.DESCONOCIDO


def test_la_gramatica_b_conserva_su_propio_estado(tmp_path):
    """Lo que el escritor declaró manda sobre lo que se pueda deducir del nombre."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:00:00Z", "modulo": "api",
        "tipo_evento": "API_KPIS_FETCHED", "estado": "ERROR", "payload": {},
    })])
    assert leer_rastro(ruta=ruta).eventos[0].estado is EstadoEvento.ERROR


# ==============================================================================
# Fichero ausente, ilegible, y la ausencia de efectos
# ==============================================================================


def test_un_rastro_ausente_no_es_una_averia(tmp_path):
    resultado = leer_rastro(ruta=str(tmp_path / "no_existe.jsonl"))

    assert resultado.existe is False
    assert resultado.eventos == []
    assert resultado.degradado is False, "no haber nada que leer no es haber leído mal"


def test_leer_no_crea_el_directorio_de_datos(tmp_path):
    """Nota 2 de la cabecera: es la trampa que el Paso 2 ya documentó con el healthcheck."""
    inexistente = tmp_path / "sin_crear"
    leer_rastro(ruta=str(inexistente / "pipeline.jsonl"))

    assert not inexistente.exists()


def test_un_rastro_ilegible_lanza_su_error_tipado(tmp_path, monkeypatch):
    ruta = escribir(tmp_path / "r.jsonl", ["{}"])

    def abrir_falla(*args, **kwargs):
        raise PermissionError("bloqueado por otro proceso")

    monkeypatch.setattr("builtins.open", abrir_falla)
    with pytest.raises(RastroIlegible):
        leer_rastro(ruta=ruta)


# ==============================================================================
# Filtros
# ==============================================================================


def test_filtro_por_run_id(tmp_path):
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "action": "a",
                    "run_id": 15, "updated_by": "radar"}),
        json.dumps({"timestamp": "2026-08-27T05:00:01Z", "action": "b",
                    "run_id": 16, "updated_by": "radar"}),
    ])
    eventos = leer_rastro(ruta=ruta, run_id=16).eventos

    assert [e.evento for e in eventos] == ["b"]


def test_run_id_ausente_no_es_cero(tmp_path):
    """`None` = el rastro no lo dice. `0` = evento del lanzador fuera de una corrida."""
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:00:00Z", "componente": "centinela",
                    "evento": "boletin_fetch_started", "detalles": {}}),
        json.dumps({"timestamp": "2026-08-27T05:00:01Z", "action": "LANZADOR_INICIADO",
                    "run_id": 0, "updated_by": "lanzador"}),
    ])
    eventos = leer_rastro(ruta=ruta).eventos

    assert eventos[0].run_id is None
    assert eventos[1].run_id == 0
    assert leer_rastro(ruta=ruta, run_id=0).eventos[0].evento == "LANZADOR_INICIADO"


def test_la_ventana_temporal_atribuye_lo_que_no_declara_run_id(tmp_path):
    """Es como se atribuyó a mano a la corrida 16 el `boletin_fetch_started` que acotó H-41."""
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-27T05:20:00Z", "componente": "centinela",
                    "evento": "antes_de_la_corrida", "detalles": {}}),
        json.dumps({"timestamp": "2026-08-27T05:29:03Z", "componente": "centinela",
                    "evento": "boletin_fetch_started", "detalles": {}}),
        json.dumps({"timestamp": "2026-08-27T06:00:00Z", "componente": "centinela",
                    "evento": "despues_de_la_corrida", "detalles": {}}),
    ])
    eventos = leer_rastro(
        ruta=ruta,
        desde=datetime(2026, 8, 27, 5, 28, 7, tzinfo=timezone.utc),
        hasta=datetime(2026, 8, 27, 5, 29, 10, tzinfo=timezone.utc),
    ).eventos

    assert [e.evento for e in eventos] == ["boletin_fetch_started"]


def test_sin_fecha_legible_queda_fuera_de_la_ventana(tmp_path):
    """Incluirlo sería atribuir a una corrida un evento que quizá no es suyo."""
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "no es una fecha", "action": "a", "run_id": 16, "updated_by": "radar",
    })])
    resultado = leer_rastro(ruta=ruta)

    assert resultado.eventos[0].instante is None
    assert leer_rastro(
        ruta=ruta, desde=datetime(2026, 1, 1, tzinfo=timezone.utc)
    ).eventos == []


def test_los_dos_formatos_de_fecha_se_ordenan_entre_si(tmp_path):
    """2.789 líneas con `Z` y 1.965 con `+00:00` y microsegundos, en el mismo fichero."""
    ruta = escribir(tmp_path / "r.jsonl", [
        json.dumps({"timestamp": "2026-08-26T11:44:41Z", "action": "primero",
                    "run_id": 1, "updated_by": "radar"}),
        json.dumps({"timestamp": "2026-08-26T11:44:41.656495+00:00", "modulo": "api",
                    "tipo_evento": "segundo", "estado": "INFO", "payload": {}}),
    ])
    primero, segundo = leer_rastro(ruta=ruta).eventos

    # Dentro del mismo segundo, los microsegundos son lo único que ordena la ráfaga de la API.
    assert primero.instante < segundo.instante
    assert segundo.timestamp == "2026-08-26T11:44:41.656495+00:00", "no se reformatea"


def test_el_tope_devuelve_los_ultimos_y_no_falsea_los_recuentos(tmp_path):
    """Quien diagnostica quiere el final del rastro, no su principio."""
    lineas = [
        json.dumps({"timestamp": f"2026-08-27T05:00:{n:02d}Z", "action": f"e{n}",
                    "run_id": 1, "updated_by": "radar"})
        for n in range(10)
    ]
    lineas.insert(5, "{rota")
    resultado = leer_rastro(ruta=escribir(tmp_path / "r.jsonl", lineas), tope=3)

    assert [e.evento for e in resultado.eventos] == ["e7", "e8", "e9"]
    assert resultado.lineas_totales == 11
    assert resultado.lineas_ilegibles == 1, "el tope acota lo devuelto, no lo contado"


# ==============================================================================
# Componentes
# ==============================================================================


def test_analista_ia_y_analista_son_el_mismo_componente(tmp_path):
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-27T05:00:00Z", "action": "guardar_analisis_semantico",
        "run_id": 16, "updated_by": "analista_ia",
    })])
    assert leer_rastro(ruta=ruta).eventos[0].componente == "analista"


def test_un_componente_fuera_del_vocabulario_se_conserva(tmp_path):
    """La integridad se exige al escribir, no al leer (decisión del 2026-07-27).

    `reconciliacion_h54` existe de verdad en el rastro real: lo escribió la herramienta que
    cerró H-54. Rechazarlo aquí sería perder rastro ya escrito.
    """
    ruta = escribir(tmp_path / "r.jsonl", [json.dumps({
        "timestamp": "2026-08-25T10:00:00Z", "action": "purga",
        "run_id": 0, "updated_by": "reconciliacion_h54",
    })])
    assert leer_rastro(ruta=ruta).eventos[0].componente == "reconciliacion_h54"
