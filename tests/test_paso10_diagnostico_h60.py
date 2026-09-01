"""El diagnóstico deja de contarse a sí mismo — Capa 10, Paso 10, bloque B.3.

Contrato: `.agents/CONTRATO_PASO_10.md` v1.4.0, **Operación 7**. Hallazgo: **H-60**.

**QUÉ PASABA.** El canal que lee el rastro **escribía en el rastro**: cada consulta a
`GET /admin/prospeccion/diagnostico` dejaba un `RASTRO_LEIDO_DEGRADADO` en `pipeline.jsonl`, y la
consulta siguiente lo leía y se lo atribuía a la corrida que estuviera en marcha. Sobre la corrida
23 —`COMPLETED`, `errores = 0`, sin una sola incidencia— el Cockpit anunciaba *«Al día, con 2
avisos»*, y los dos avisos eran sus propias preguntas. Sobre la 25, mirándola con insistencia,
llegó a decir **49**. **La cifra no medía la corrida: medía cuántas veces se miró la pantalla.**

**LA TRAMPA DE ESTAS PRUEBAS, Y POR QUÉ LA FIXTURE HACE LO QUE HACE.** En la suite, el fichero que
el endpoint **lee** —resuelto contra el directorio de la base— y el que **escribe** —el del gestor
de trazabilidad de la API— son dos ficheros distintos. En producción **son el mismo**, y ahí es
donde vive el defecto. Una prueba escrita sobre la separación pasaría hoy sin reparar nada: por
eso `rastro_compartido` apunta los dos al mismo sitio. *Es la misma familia que la Convención C4:
si la prueba no ejercita la ruta real, no prueba la ruta real.*

**Y LA VENTANA TIENE QUE INCLUIR EL AHORA.** El evento que la API escribe lleva la hora actual, así
que sobre una corrida sembrada en el pasado no caería dentro y el bucle no se reproduciría. Las
corridas de este fichero se siembran **alrededor de ahora**, a propósito.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import trazabilidad_api
from src.api.main import app
from src.diagnostico import EstadoProspeccion, diagnosticar
from src.memoria import Memoria


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def rastro_compartido(tmp_path, monkeypatch):
    """Base temporal **y un solo `pipeline.jsonl`** para lectura y escritura, como en producción.

    Devuelve `(memoria, ruta_del_rastro)`.
    """
    ruta_db = str(tmp_path / "licitaciones.db")
    monkeypatch.setenv("DB_PATH_INCOOP", ruta_db)
    memoria = Memoria(db_path=ruta_db)
    memoria.setup_db()

    rastro = str(tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(trazabilidad_api, "log_path", rastro)
    return memoria, rastro


def sembrar_corrida_en_curso_ahora(memoria, identificador=91):
    """Una corrida `COMPLETED` cuya ventana contiene el instante actual."""
    ahora = datetime.now(timezone.utc)
    inicio = (ahora - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fin = (ahora + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with memoria.conectar() as conexion:
        with conexion:
            conexion.execute(
                "INSERT INTO ejecuciones (id, start_time, end_time, estado, errores) "
                "VALUES (?, ?, ?, 'COMPLETED', 0);",
                (identificador, inicio, fin),
            )
    return inicio, fin


def romper_una_linea(rastro):
    """Deja el rastro degradado, que es la condición que disparaba el evento."""
    with open(rastro, "a", encoding="utf-8") as fichero:
        fichero.write('s": 69.11}}\n')


def eventos_de(rastro, nombre):
    if not os.path.exists(rastro):
        return []
    encontrados = []
    with open(rastro, encoding="utf-8", errors="replace") as fichero:
        for linea in fichero:
            try:
                evento = json.loads(linea)
            except ValueError:
                continue
            if evento.get("evento") == nombre or evento.get("tipo_evento") == nombre:
                encontrados.append(evento)
    return encontrados


# ==============================================================================
# La postcondición de la Operación 7
# ==============================================================================


def test_dos_consultas_seguidas_devuelven_lo_mismo(client, rastro_compartido):
    """**Consultar el diagnóstico no puede alterar el diagnóstico.**

    Es H-60 en su forma más corta. Con el defecto vivo, la primera consulta no ve degradaciones
    —todavía no ha escrito la suya— y la segunda ve una: la de la primera.
    """
    memoria, rastro = rastro_compartido
    sembrar_corrida_en_curso_ahora(memoria)
    romper_una_linea(rastro)

    primera = client.get("/api/v1/admin/prospeccion/diagnostico").json()
    segunda = client.get("/api/v1/admin/prospeccion/diagnostico").json()

    assert primera["estado"] == segunda["estado"]
    assert primera["degradaciones"] == segunda["degradaciones"], (
        "la segunda consulta está viendo lo que escribió la primera"
    )
    assert segunda["degradaciones"] == [], "y ninguna de las dos inventa una avería"
    assert segunda["estado"] == EstadoProspeccion.COMPLETADA.value


def test_consultar_el_diagnostico_no_escribe_un_evento_degradado(client, rastro_compartido):
    """Camino B: **el aviso del rastro deja de escribirse en el rastro.**

    El hecho no se pierde —viaja en el cuerpo de la respuesta, donde ya viajaba desde el Paso 9—;
    lo que desaparece es la constancia que se convertía en avería ajena.
    """
    memoria, rastro = rastro_compartido
    sembrar_corrida_en_curso_ahora(memoria)
    romper_una_linea(rastro)

    for _ in range(3):
        assert client.get("/api/v1/admin/prospeccion/diagnostico").status_code == 200

    assert eventos_de(rastro, "RASTRO_LEIDO_DEGRADADO") == [], (
        "el canal de diagnóstico no puede escribir en el canal que diagnostica"
    )


def test_el_rastro_roto_se_sigue_declarando_en_la_respuesta(client, rastro_compartido):
    """Lo que se quita es el evento, **no el dato**. Callarlo sería cambiar H-60 por H-55 otra vez."""
    memoria, rastro = rastro_compartido
    sembrar_corrida_en_curso_ahora(memoria)
    romper_una_linea(rastro)

    cuerpo = client.get("/api/v1/admin/prospeccion/diagnostico").json()

    assert cuerpo["rastro_degradado"] is True
    assert cuerpo["rastro_lineas_ilegibles"] >= 1


# ==============================================================================
# El matiz A: quién es la corrida y quién la mira
# ==============================================================================


def escribir(ruta, eventos):
    with open(str(ruta), "w", encoding="utf-8") as fichero:
        for evento in eventos:
            fichero.write(json.dumps(evento) + "\n")
    return str(ruta)


FILA = {
    "id": 91, "estado": "COMPLETED", "errores": 0,
    "start_time": "2026-09-01T05:00:00Z", "end_time": "2026-09-01T05:10:00Z",
}


def evento_degradado(componente, nombre):
    return {
        "esquema": 1, "timestamp": "2026-09-01T05:05:00Z", "run_id": None,
        "componente": componente, "evento": nombre, "estado": "DEGRADADO",
        "datos": {"error": "lo que sea"},
    }


def test_una_degradacion_de_la_api_no_es_una_averia_de_la_corrida(tmp_path):
    """**La corrida la ejecutan las Capas 3 a 7; la API es quien la mira.**

    No es una lista de excepciones: es la distinción que H-60 borró. Un fallo del observador no
    es un fallo de lo observado, y confundirlos fue lo que puso el distintivo en ámbar sobre una
    prospección impecable.
    """
    ruta = escribir(tmp_path / "r.jsonl", [evento_degradado("api", "LO_QUE_SEA_DE_LA_API")])

    resultado = diagnosticar(dict(FILA), ruta_rastro=ruta)

    assert resultado.degradaciones == []
    assert resultado.estado is EstadoProspeccion.COMPLETADA


def test_una_degradacion_del_pipeline_si_es_una_averia_de_la_corrida(tmp_path):
    """El contrapeso, y hace tanta falta como el filtro.

    Sin esta prueba, filtrar de más —o filtrarlo todo— pasaría inadvertido, y volveríamos a
    **H-45**: el distintivo verde sobre una corrida que no pudo mirar. Se comprueban dos
    componentes distintos para que el filtro no pueda acertar por casualidad.
    """
    ruta = escribir(tmp_path / "r.jsonl", [
        evento_degradado("centinela", "boletin_fetch_degraded"),
        evento_degradado("lector", "doc_ocr_degraded"),
    ])

    resultado = diagnosticar(dict(FILA), ruta_rastro=ruta)

    assert [d.componente for d in resultado.degradaciones] == ["centinela", "lector"]
    assert resultado.estado is EstadoProspeccion.COMPLETADA_CON_DEGRADACION


def test_una_corrida_con_las_dos_cosas_sólo_cuenta_la_suya(tmp_path):
    """El caso mezclado, que es el que ocurre de verdad: la API sondeando durante una corrida
    que además degradó por su cuenta."""
    ruta = escribir(tmp_path / "r.jsonl", [
        evento_degradado("api", "RASTRO_LEIDO_DEGRADADO"),
        evento_degradado("centinela", "boletin_fetch_degraded"),
        evento_degradado("api", "RASTRO_LEIDO_DEGRADADO"),
    ])

    resultado = diagnosticar(dict(FILA), ruta_rastro=ruta)

    assert len(resultado.degradaciones) == 1
    assert resultado.degradaciones[0].componente == "centinela"
    assert "1 cosa no se pudo hacer" in resultado.motivo
