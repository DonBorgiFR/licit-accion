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
