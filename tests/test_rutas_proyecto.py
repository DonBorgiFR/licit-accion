"""
tests/test_rutas_proyecto.py — Resolución de rutas contra la raíz del proyecto

Regresión del hallazgo H-18: `config/` y `data/` se resolvían contra el directorio de
trabajo. Ejecutado desde otra carpeta, el perfil comercial de Incoop no se cargaba y el
sistema seguía adelante en silencio con los valores por defecto. No fallaba: puntuaba
distinto. Es requisito del lanzador VBS de la Capa 10, que arranca con un directorio de
trabajo arbitrario.
"""

import os

from src import PROJECT_ROOT, ruta_proyecto
from src.filtro import Filtro
from src.pmp_service import PMPService
from src.radar import Radar


LICITACION_DE_REFERENCIA = {
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


def test_ruta_proyecto_respeta_las_absolutas_y_ancla_las_relativas(tmp_path):
    absoluta = str(tmp_path / "cualquiera.db")
    assert ruta_proyecto(absoluta) == absoluta

    resuelta = ruta_proyecto("config/perfil_incoop.yaml")
    assert os.path.isabs(resuelta)
    assert resuelta == str((PROJECT_ROOT / "config" / "perfil_incoop.yaml").resolve())


def test_el_perfil_comercial_se_carga_desde_cualquier_directorio(tmp_path, monkeypatch):
    """
    El perfil debe cargarse igual desde la raíz que desde una carpeta ajena. Antes se
    cargaba vacío fuera de la raíz, sin error ni aviso.
    """
    desde_la_raiz = Filtro().perfil
    assert desde_la_raiz, "El perfil debe cargarse desde la raíz del proyecto"

    monkeypatch.chdir(tmp_path)
    desde_fuera = Filtro().perfil

    assert desde_fuera == desde_la_raiz
    assert Radar().perfil == desde_la_raiz


def test_la_puntuacion_no_depende_del_directorio_de_trabajo(tmp_path, monkeypatch):
    """
    El caso que hacía esto grave: la misma licitación puntuaba 71 desde la raíz y 47
    desde otra carpeta, con el umbral de recomendación en 65. La diferencia entre
    recomendar y descartar dependía de dónde se hubiera lanzado el proceso.
    """
    score_raiz = Filtro().filtrar(dict(LICITACION_DE_REFERENCIA))["score"]

    monkeypatch.chdir(tmp_path)
    score_fuera = Filtro().filtrar(dict(LICITACION_DE_REFERENCIA))["score"]

    assert score_fuera == score_raiz


def test_los_datos_de_pmp_se_encuentran_desde_cualquier_directorio(tmp_path, monkeypatch):
    pmp_raiz = PMPService().obtener_pmp("Badalona")

    monkeypatch.chdir(tmp_path)
    assert PMPService().obtener_pmp("Badalona") == pmp_raiz


def test_el_sistema_arranca_en_una_instalacion_nueva(tmp_path):
    """
    Regresión de H-24: `data/` está excluida de Git, así que en un clon limpio no existe.
    `setup_db()` adquiere el cerrojo de migración ANTES de abrir la primera conexión, y era
    `conectar()` quien creaba el directorio: la creación del `.lock` fallaba con
    FileNotFoundError y **un clon del repositorio no podía arrancar el sistema**.

    Se detectó al borrar los datos de la beta y arrancar desde cero absoluto.
    """
    from src.memoria import Memoria

    db_path = tmp_path / "instalacion_nueva" / "subcarpeta" / "licitaciones.db"
    assert not db_path.parent.exists(), "El directorio no debe existir antes de instanciar"

    memoria = Memoria(db_path=str(db_path))
    memoria.setup_db()

    assert db_path.exists()
    kpis = memoria.obtener_resumen_kpis()
    assert kpis["total_expedientes"] == 0
    assert kpis["total_lotes"] == 0
    assert kpis["volumen_total_pbl"] == 0.0


def test_el_registro_de_respaldo_del_lector_no_escribe_contra_el_directorio_de_trabajo(
    tmp_path, monkeypatch
):
    """
    Regresión de H-28, último resto de H-18. `Lector.registrar_log_JSONL()` tiene una vía
    de respaldo para cuando la base de datos no está disponible, y esa vía resolvía
    `os.path.join("data", "pipeline.jsonl")` **contra el directorio de trabajo**.

    Dos consecuencias, y la segunda es la grave: lanzado desde otra carpeta creaba un
    `data/` espurio donde no tocaba; y al no pasar por `ruta_datos()` ignoraba
    `DATA_DIR_INCOOP`, de modo que durante la suite habría escrito en el `data/` real del
    proyecto — exactamente lo que H-25 vino a impedir.

    Sobrevivió al Paso D3 porque sólo se ejecuta cuando `self.db` no está disponible.
    """
    from src import ruta_datos
    from src.lector import Lector

    destino = tmp_path / "datos_redirigidos"
    monkeypatch.setenv("DATA_DIR_INCOOP", str(destino))

    cwd_ajeno = tmp_path / "otro_directorio"
    cwd_ajeno.mkdir()
    monkeypatch.chdir(cwd_ajeno)

    lector = Lector(db_memoria=None)
    lector.registrar_log_JSONL(action="prueba_h28", reason="regresion")

    assert (destino / "pipeline.jsonl").exists(), "El registro debe ir al directorio redirigido"
    assert not (cwd_ajeno / "data").exists(), "No debe crear un data/ en el directorio de trabajo"
    assert ruta_datos("pipeline.jsonl") == str(destino / "pipeline.jsonl")
