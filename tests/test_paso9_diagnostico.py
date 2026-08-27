"""Regresiones de la máquina de estados del diagnóstico — Capa 10, Paso 9, bloque D.

Contrato: `.agents/CONTRATO_PASO_9.md`, sección E.1.

**La prueba que justifica el bloque entero es
`test_una_corrida_sin_errores_pero_ciega_no_esta_al_dia`.** Reproduce la corrida 16 del
2026-08-27, que consta `COMPLETED` con `errores = 0` mientras el Centinela no podía consultar
ninguna de sus dos fuentes. Todo lo demás de este fichero es la máquina de estados alrededor.
"""

import json

import pytest

from src.diagnostico import EstadoProspeccion, diagnosticar


def rastro(tmp_path, eventos):
    """Escribe un rastro canónico sintético y devuelve su ruta."""
    ruta = tmp_path / "pipeline.jsonl"
    ruta.write_text(
        "\n".join(json.dumps({"esquema": 1, **evento}) for evento in eventos) + "\n",
        encoding="utf-8",
    )
    return str(ruta)


def corrida(**campos):
    """Una fila de `ejecuciones` como la sirve `Memoria.listar_ejecuciones()`."""
    fila = {
        "id": 17,
        "start_time": "2026-08-27T05:00:00Z",
        "end_time": "2026-08-27T05:10:00Z",
        "estado": "COMPLETED",
        "errores": 0,
        "duenyo_vivo": None,
    }
    fila.update(campos)
    return fila


def evento(nombre, estado="INFO", componente="radar", cuando="2026-08-27T05:05:00Z", **datos):
    return {"timestamp": cuando, "run_id": 17, "componente": componente,
            "evento": nombre, "estado": estado, "datos": datos}


# ==============================================================================
# El estado que este paso añade
# ==============================================================================


def test_una_corrida_sin_errores_pero_ciega_no_esta_al_dia(tmp_path):
    """**La prueba central del bloque.** Es la corrida 16 del 2026-08-27, tal cual ocurrió.

    `COMPLETED`, `errores = 0`, y dentro el Centinela no pudo consultar ninguna de sus dos
    fuentes. Antes de este módulo el Cockpit pintaba verde encima. Un verde sobre una corrida
    ciega no rompe nada y miente en pantalla, que es la familia de H-21.
    """
    ruta = rastro(tmp_path, [
        evento("run_start"),
        evento("boletin_fetch_degraded", estado="DEGRADADO", componente="centinela",
               fuente="DOGC", error="HTTP Error 404: Not Found"),
        evento("boletin_fetch_degraded", estado="DEGRADADO", componente="centinela",
               fuente="BOPB", error="HTTP Error 500: Internal Server Error"),
        evento("run_end"),
    ])

    resultado = diagnosticar(corrida(), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.COMPLETADA_CON_DEGRADACION
    assert resultado.errores_registrados == 0, "la fila sigue diciendo cero, y ése es el punto"
    assert len(resultado.degradaciones) == 2
    assert resultado.degradaciones[0].componente == "centinela"
    assert "404" in resultado.degradaciones[0].detalle, "la degradación trae su porqué"
    assert "500" in resultado.degradaciones[1].detalle


def test_una_corrida_limpia_si_esta_al_dia(tmp_path):
    ruta = rastro(tmp_path, [evento("run_start"), evento("run_end")])

    resultado = diagnosticar(corrida(), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.COMPLETADA
    assert resultado.degradaciones == []


def test_una_degradacion_fuera_de_la_ventana_no_es_de_esta_corrida(tmp_path):
    """La atribución es por ventana temporal, así que la ventana tiene que gobernar de verdad."""
    ruta = rastro(tmp_path, [
        evento("boletin_fetch_degraded", estado="DEGRADADO", componente="centinela",
               cuando="2026-08-26T09:00:00Z", fuente="DOGC", error="de ayer"),
        evento("run_start"),
        evento("run_end"),
    ])

    resultado = diagnosticar(corrida(), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.COMPLETADA
    assert resultado.degradaciones == []


# ==============================================================================
# Los demás estados de la sección E.1
# ==============================================================================


def test_sin_ninguna_prospeccion(tmp_path):
    resultado = diagnosticar(None, ruta_rastro=rastro(tmp_path, [evento("run_start")]))

    assert resultado.estado is EstadoProspeccion.SIN_PROSPECCIONES
    assert resultado.ejecucion_id is None


def test_en_curso_cuando_su_duenyo_vive(tmp_path):
    ruta = rastro(tmp_path, [evento("run_start")])

    resultado = diagnosticar(
        corrida(estado="RUNNING", end_time=None, duenyo_vivo=True), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.EN_CURSO


def test_interrumpida_cuando_su_duenyo_ha_muerto(tmp_path):
    ruta = rastro(tmp_path, [evento("run_start"), evento("doc_download_started")])

    resultado = diagnosticar(
        corrida(estado="RUNNING", end_time=None, duenyo_vivo=False), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.INTERRUMPIDA
    assert resultado.ultimo_evento == "doc_download_started", (
        "lo último que llegó a escribir es justo lo que se necesitó a mano para acotar H-41"
    )


def test_interrumpida_por_tope_es_un_estado_distinto(tmp_path):
    """Ante un `31` se mira el pipeline; ante un `32`, por qué no acababa. No se confunden."""
    ruta = rastro(tmp_path, [
        evento("run_start"),
        evento("LANZADOR_PIPELINE_AGOTADO", componente="lanzador", reason="60 min"),
    ])

    resultado = diagnosticar(
        corrida(estado="RUNNING", end_time=None, duenyo_vivo=False), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.INTERRUMPIDA_POR_TOPE


def test_sin_cerrar_cuando_no_se_puede_saber(tmp_path):
    """`None` es una fila anterior al esquema v8: no se elige por el lector entre viva y rota."""
    ruta = rastro(tmp_path, [evento("run_start")])

    resultado = diagnosticar(
        corrida(estado="RUNNING", end_time=None, duenyo_vivo=None), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.SIN_CERRAR


def test_fallida(tmp_path):
    ruta = rastro(tmp_path, [evento("run_start"), evento("run_failed", estado="ERROR")])

    resultado = diagnosticar(corrida(estado="FAILED", errores=3), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.FALLIDA
    assert resultado.errores_registrados == 3


def test_un_estado_que_no_se_entiende_no_se_traduce_a_averia(tmp_path):
    """Convención C6: inventar hacia «falló» es tan malo como inventar hacia «fue bien»."""
    ruta = rastro(tmp_path, [evento("run_start")])

    resultado = diagnosticar(corrida(estado="LO_QUE_SEA"), ruta_rastro=ruta)

    assert resultado.estado is EstadoProspeccion.DESCONOCIDA
    assert "LO_QUE_SEA" in resultado.motivo


# ==============================================================================
# El canal de diagnóstico no puede tumbar lo que diagnostica
# ==============================================================================


def test_un_rastro_con_lineas_rotas_se_diagnostica_y_se_declara(tmp_path):
    """H-55: el diagnóstico sale, y dice sobre qué se construyó."""
    ruta = tmp_path / "pipeline.jsonl"
    ruta.write_text(
        json.dumps({"esquema": 1, **evento("run_start")}) + "\n"
        + 's": 69.11}}\n'
        + json.dumps({"esquema": 1, **evento("run_end")}) + "\n",
        encoding="utf-8",
    )

    resultado = diagnosticar(corrida(), ruta_rastro=str(ruta))

    assert resultado.estado is EstadoProspeccion.COMPLETADA
    assert resultado.rastro_degradado is True
    assert resultado.rastro_lineas_ilegibles == 1
    assert resultado.rastro_legible is True


def test_un_rastro_ilegible_no_impide_diagnosticar(tmp_path, monkeypatch):
    """Transición prohibida nº 4: el canal de diagnóstico no tumba aquello que diagnostica."""
    from src import rastro as modulo_rastro

    def no_se_puede(*args, **kwargs):
        raise modulo_rastro.RastroIlegible("bloqueado")

    monkeypatch.setattr(modulo_rastro, "leer_rastro", no_se_puede)
    monkeypatch.setattr("src.diagnostico.leer_rastro", no_se_puede)

    resultado = diagnosticar(corrida(estado="FAILED", errores=2))

    assert resultado.estado is EstadoProspeccion.FALLIDA, "la tabla basta para el estado"
    assert resultado.rastro_legible is False
    assert resultado.degradaciones == []


def test_un_rastro_ausente_tampoco_impide_diagnosticar(tmp_path):
    resultado = diagnosticar(corrida(), ruta_rastro=str(tmp_path / "no_existe.jsonl"))

    assert resultado.estado is EstadoProspeccion.COMPLETADA
    assert resultado.rastro_legible is True, "no existir no es ser ilegible"
    assert resultado.ultimo_evento is None
