"""Router administrativo de lectura — Capa 9, Paso 7.

Los cuatro endpoints con los que se mira antes de decidir. Lo que estas pruebas protegen no
es que devuelvan un 200, sino tres propiedades que hacen que la purga en dos tiempos sea
real:

* **Que mirar no borre.** Si la previsualización alterase algo, el "previsualizar y luego
  confirmar" del diseño sería una ficción.
* **Que lo protegido se vea con su motivo**, y no sólo lo eliminable. Una pantalla que sólo
  enseñara lo que va a desaparecer no permitiría comprobar que lo intocable no está en riesgo.
* **Que una política ilegible dé 503 y no un listado vacío.** "No hay nada que purgar" y "no
  he podido leer el criterio" no pueden parecerse en pantalla (Convención C2).
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from src import ruta_datos
from src.api.main import app
from src.memoria import Memoria


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def base_api(tmp_path, monkeypatch):
    """Base temporal servida por la API, con los documentos donde los deja el Lector."""
    ruta = str(tmp_path / "licitaciones.db")
    monkeypatch.setenv("DB_PATH_INCOOP", ruta)
    memoria = Memoria(db_path=ruta)
    memoria.setup_db()
    return memoria


def sembrar_expediente(memoria, exp_id, deleted_at=None, estado="Nueva", fecha_limite="2024-01-05T23:59:00Z"):
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta, fecha_limite, "
                "deleted_at) VALUES (?, 'Limpieza', 'Ajuntament', '2024-01-01T09:00:00Z', ?, ?);",
                (exp_id, fecha_limite, deleted_at),
            )
            conn.execute(
                "INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo, "
                "deleted_at) VALUES (?, 1, 'Lote unico', ?, ?);",
                (exp_id, estado, deleted_at),
            )


# --------------------------------------------------------------------------------------
# GET /admin/almacenamiento
# --------------------------------------------------------------------------------------

def test_el_almacenamiento_distingue_lo_purgable_de_lo_que_no_lo_es(client, base_api):
    """La base nunca es purgable: sus filas son la memoria comercial, no ficheros.

    Confundir las dos cosas lleva a purgar donde no hay espacio que ganar, que es
    exactamente el error que el diseño de la capa quiere impedir.
    """
    carpeta = os.path.join(os.path.dirname(base_api.db_path), "documents", "EXP1")
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "pliego.pdf"), "wb") as fichero:
        fichero.write(b"x" * 2048)

    respuesta = client.get("/api/v1/admin/almacenamiento")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["documentos_bytes"] == 2048
    assert datos["documentos_ficheros"] == 1
    assert datos["base_datos_bytes"] > 0
    assert datos["purgable_bytes"] == datos["documentos_bytes"] + datos["copias_bytes"]
    assert datos["purgable_bytes"] < datos["total_bytes"], "La base no entra en lo purgable"


def test_el_almacenamiento_mide_los_documentos_donde_el_lector_los_deja(client, base_api):
    """Los pliegos viven junto a la base, no en `data/` sin más.

    Si el Depurador dedujera la ruta por su cuenta no fallaría: informaría de cero bytes y
    no encontraría nada que purgar. Un error silencioso, de la familia de H-18.
    """
    carpeta = os.path.join(os.path.dirname(base_api.db_path), "documents")
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "junto_a_la_base.pdf"), "wb") as fichero:
        fichero.write(b"y" * 512)
    # Un fichero en la otra ubicación candidata no debe contarse.
    otra = ruta_datos("documents")
    os.makedirs(otra, exist_ok=True)
    with open(os.path.join(otra, "en_otro_sitio.pdf"), "wb") as fichero:
        fichero.write(b"z" * 4096)

    datos = client.get("/api/v1/admin/almacenamiento").json()

    assert datos["documentos_bytes"] == 512


# --------------------------------------------------------------------------------------
# GET /admin/retencion
# --------------------------------------------------------------------------------------

def test_la_politica_vigente_se_sirve_con_su_version_y_sus_bloques(client, base_api):
    """Se lee el fichero real del proyecto: es la política bajo la que se purgaría hoy."""
    respuesta = client.get("/api/v1/admin/retencion")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["version"] == "1.2.0"
    assert datos["documentos_dias"] == 180
    assert datos["archivado"]["dias_tras_fecha_limite"] == 60
    assert "presentada" not in [e.lower() for e in datos["archivado"]["estados_archivables"]]
    assert datos["eliminacion"]["dias_archivado_minimo"] == 365


def test_los_estados_se_sirven_en_la_grafia_que_el_cockpit_pinta(client, base_api):
    """La política los guarda normalizados (H-27), pero la pantalla no debe verlos así.

    Servir 'nueva' pintaría la política en minúsculas junto a los 'Nueva' del Funnel. La
    grafía visible sale del enum y no de una capitalización improvisada: `.capitalize()`
    convertiría `anulada_administracion` en `Anulada_administracion`, con una mayúscula menos.
    """
    estados = client.get("/api/v1/admin/retencion").json()["archivado"]["estados_archivables"]

    assert "Nueva" in estados
    assert "Adjudicada" in estados
    assert all(estado[0].isupper() for estado in estados), estados


def test_una_politica_ilegible_da_503_y_no_un_listado_vacio(client, base_api, monkeypatch):
    """"No hay nada que purgar" y "no he podido leer el criterio" no pueden confundirse."""
    from src.retencion import PoliticaRetencionInvalida

    def politica_rota(*args, **kwargs):
        raise PoliticaRetencionInvalida("config/retencion.yaml no encontrado")

    monkeypatch.setattr("src.api.routers.admin.cargar_politica", politica_rota)

    assert client.get("/api/v1/admin/retencion").status_code == 503
    assert client.get("/api/v1/admin/purga/previsualizacion").status_code == 503


# --------------------------------------------------------------------------------------
# GET /admin/purga/previsualizacion
# --------------------------------------------------------------------------------------

def test_la_previsualizacion_ensena_lo_protegido_con_su_motivo(client, base_api):
    """Ver sólo lo eliminable no permitiría comprobar que lo intocable no está en riesgo."""
    sembrar_expediente(base_api, "EXP-NADIE-MIRO", deleted_at="2024-02-01T09:00:00Z")
    sembrar_expediente(base_api, "EXP-ADJUDICADO", deleted_at="2024-02-01T09:00:00Z",
                       estado="Adjudicada")
    sembrar_expediente(base_api, "EXP-RECIEN", deleted_at="2026-08-11T09:00:00Z")

    datos = client.get("/api/v1/admin/purga/previsualizacion").json()

    assert [e["expediente_id"] for e in datos["eliminables"]] == ["EXP-NADIE-MIRO"]
    bloqueados = {b["expediente_id"]: b["motivo"] for b in datos["bloqueados"]}
    assert bloqueados["EXP-ADJUDICADO"] == "memoria_comercial"
    assert bloqueados["EXP-RECIEN"] == "cuarentena_no_cumplida"
    assert datos["version_politica"] == "1.2.0"
    assert datos["degradado"] is None


def test_previsualizar_no_altera_absolutamente_nada(client, base_api):
    """Es la propiedad que sostiene toda la purga en dos tiempos."""
    sembrar_expediente(base_api, "EXP-1", deleted_at="2024-02-01T09:00:00Z")
    carpeta = os.path.join(os.path.dirname(base_api.db_path), "documents")
    os.makedirs(carpeta, exist_ok=True)
    ruta_pdf = os.path.join(carpeta, "pliego.pdf")
    with open(ruta_pdf, "wb") as fichero:
        fichero.write(b"contenido")
    with base_api.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, "
                "estado, local_path, texto_extraido, updated_at) VALUES ('EXP-1', 'PCA.pdf', "
                "'http://x/p.pdf', 'PCA', 'h1', 'PROCESADO', ?, 'texto', "
                "'2024-01-01T09:00:00Z');",
                (ruta_pdf,),
            )

    respuesta = client.get("/api/v1/admin/purga/previsualizacion").json()

    assert respuesta["documental"]["documentos_candidatos"] == 1
    assert respuesta["documental"]["bytes_estimados"] > 0
    assert os.path.exists(ruta_pdf), "Mirar no borra"
    with base_api.conectar() as conn:
        estado, texto = conn.execute(
            "SELECT estado, texto_extraido FROM documentos WHERE expediente_id='EXP-1';"
        ).fetchone()
        assert (estado, texto) == ("PROCESADO", "texto")
        assert conn.execute("SELECT COUNT(*) FROM expedientes;").fetchone()[0] == 1


def test_la_previsualizacion_deja_constancia_de_quien_miro(client, base_api):
    """No altera nada, pero no es anónima: es una operación irreversible la que se estudia."""
    sembrar_expediente(base_api, "EXP-1", deleted_at="2024-02-01T09:00:00Z")

    client.get("/api/v1/admin/purga/previsualizacion?solicitado_por=direccion")

    # El rastro del Depurador se escribe junto a la base, igual que los documentos
    # (`Memoria.registrar_log_json`). En producción ambos caen en `data/`.
    registro = os.path.join(os.path.dirname(base_api.db_path), "pipeline.jsonl")
    with open(registro, encoding="utf-8") as fichero:
        lineas = [json.loads(linea) for linea in fichero if linea.strip()]
    previsualizaciones = [
        linea for linea in lineas
        if linea.get("action") == "DEPURADOR_PURGA_PREVISUALIZADA"
        and "direccion" in str(linea.get("reason", ""))
    ]
    assert previsualizaciones, "Debe constar quién consultó qué se borraría"


# --------------------------------------------------------------------------------------
# GET /admin/ejecuciones
# --------------------------------------------------------------------------------------

def test_el_historial_responde_que_encontro_cada_prospeccion(client, base_api):
    """El punto 8 del diseño: la tabla dejó de ser sólo cuándo empezó y acabó una corrida."""
    with base_api.conectar() as conn:
        with conn:
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO ejecuciones (start_time, end_time, estado, expedientes_nuevos, "
                    "lotes_evaluados, version_scoring, version_politica_retencion) VALUES "
                    "(?, ?, 'COMPLETADA', ?, ?, '2.0.0', '1.2.0');",
                    (f"2026-08-0{i}T09:00:00Z", f"2026-08-0{i}T09:05:00Z", i * 2, i * 5),
                )

    datos = client.get("/api/v1/admin/ejecuciones?limit=2").json()

    assert datos["total"] == 3
    assert datos["total_pages"] == 2
    assert len(datos["items"]) == 2
    assert datos["items"][0]["id"] > datos["items"][1]["id"], "Más reciente primero"
    assert datos["items"][0]["expedientes_nuevos"] == 6
    assert datos["items"][0]["version_politica_retencion"] == "1.2.0"


def test_el_historial_vacio_no_es_un_error(client, base_api):
    """Una instalación nueva no ha prospectado todavía, y eso no es un fallo."""
    respuesta = client.get("/api/v1/admin/ejecuciones")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "items": [], "total": 0, "page": 1, "limit": 25, "total_pages": 0
    }


def test_los_cuatro_endpoints_estan_publicados_en_el_esquema(client):
    """Si no salen en OpenAPI, el Cockpit del Paso 9 no puede consumirlos."""
    esquema = client.get("/openapi.json").json()["paths"]

    for ruta in ("/api/v1/admin/almacenamiento", "/api/v1/admin/retencion",
                 "/api/v1/admin/purga/previsualizacion", "/api/v1/admin/ejecuciones"):
        assert ruta in esquema, f"Falta {ruta} en el esquema OpenAPI"
        assert list(esquema[ruta]) == ["get"], f"{ruta} sólo debe permitir lectura en el Paso 7"
