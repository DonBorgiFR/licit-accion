"""Regresiones de la política de retención — Capa 9, Paso 2.

Los plazos que deciden qué se borra del disco vivían como literales dentro de las llamadas
de `src/main.py` (`dias_retencion=90` y `dias_retencion=7`): un criterio operativo
invisible y sin versión, en contra de la Regla 4.

La prueba central es `test_una_politica_ausente_no_se_degrada_a_valores_por_defecto`. Es la
lección de H-18: cuando `config/perfil_incoop.yaml` no se encontraba, el perfil se cargaba
vacío y el sistema continuaba en silencio con otros criterios. Aquí una política ilegible
debe **impedir la purga**, no sustituirse por plazos inventados.
"""

import textwrap

import pytest

from src.retencion import (
    NOMBRE_FICHERO,
    PoliticaRetencion,
    PoliticaRetencionInvalida,
    cargar_politica,
)


def escribir_politica(tmp_path, contenido):
    ruta = tmp_path / NOMBRE_FICHERO
    ruta.write_text(textwrap.dedent(contenido), encoding="utf-8")
    return str(ruta)


# --------------------------------------------------------------------------------------
# La política real del proyecto
# --------------------------------------------------------------------------------------

def test_la_politica_del_proyecto_es_valida_y_declara_los_plazos_acordados():
    """180 días de documentos por decisión de dirección del 2026-08-07."""
    politica = cargar_politica()
    assert politica.documentos_dias == 180
    assert politica.backups_dias == 7
    assert politica.version


def test_la_politica_es_inmutable():
    """Se lee una vez y no puede alterarse a mitad de una purga.

    Si pudiera, el evento de auditoría y lo realmente borrado podrían discrepar.
    """
    politica = cargar_politica()
    with pytest.raises(Exception):
        politica.documentos_dias = 1


# --------------------------------------------------------------------------------------
# Ausencia y corrupción: nunca se degrada a valores por defecto
# --------------------------------------------------------------------------------------

def test_una_politica_ausente_no_se_degrada_a_valores_por_defecto(tmp_path):
    """La lección de H-18: un fichero que falta no puede cambiar el comportamiento en silencio."""
    with pytest.raises(PoliticaRetencionInvalida, match="No se encuentra"):
        cargar_politica(str(tmp_path / "no_existe.yaml"))


def test_un_yaml_corrupto_se_rechaza(tmp_path):
    ruta = escribir_politica(tmp_path, "retencion: [esto no es\n  un mapa: {{{")
    with pytest.raises(PoliticaRetencionInvalida):
        cargar_politica(ruta)


def test_un_fichero_sin_bloque_retencion_se_rechaza(tmp_path):
    ruta = escribir_politica(tmp_path, "otra_cosa:\n  version: '1.0.0'\n")
    with pytest.raises(PoliticaRetencionInvalida, match="bloque 'retencion'"):
        cargar_politica(ruta)


# --------------------------------------------------------------------------------------
# Validación de los plazos
# --------------------------------------------------------------------------------------

BASE = """
    retencion:
      version: "1.0.0"
      documentos_dias: 180
      backups_dias: 7
    """


def test_falta_un_plazo(tmp_path):
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: 180
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="backups_dias"):
        cargar_politica(ruta)


@pytest.mark.parametrize("valor", [0, -1, -180])
def test_un_plazo_no_positivo_se_rechaza(tmp_path, valor):
    """Un plazo de 0 días purgaría lo recién descargado."""
    ruta = escribir_politica(tmp_path, f"""
        retencion:
          version: "1.0.0"
          documentos_dias: {valor}
          backups_dias: 7
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="mayor que cero"):
        cargar_politica(ruta)


@pytest.mark.parametrize("valor", ["'180'", "180.5", "null"])
def test_un_plazo_que_no_es_entero_se_rechaza(tmp_path, valor):
    ruta = escribir_politica(tmp_path, f"""
        retencion:
          version: "1.0.0"
          documentos_dias: {valor}
          backups_dias: 7
        """)
    with pytest.raises(PoliticaRetencionInvalida):
        cargar_politica(ruta)


def test_un_booleano_no_cuela_como_plazo(tmp_path):
    """`bool` es subclase de `int` en Python: `true` pasaría como 1 día de retención."""
    ruta = escribir_politica(tmp_path, """
        retencion:
          version: "1.0.0"
          documentos_dias: true
          backups_dias: 7
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="número entero"):
        cargar_politica(ruta)


# --------------------------------------------------------------------------------------
# Versionado (Regla 4)
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("version", ["", "'  '", "123", "null"])
def test_sin_version_declarada_la_politica_se_rechaza(tmp_path, version):
    """Cada purga registra bajo qué versión se ejecutó; sin ella no hay rastro reconstruible."""
    ruta = escribir_politica(tmp_path, f"""
        retencion:
          version: {version or "''"}
          documentos_dias: 180
          backups_dias: 7
        """)
    with pytest.raises(PoliticaRetencionInvalida, match="version"):
        cargar_politica(ruta)


# --------------------------------------------------------------------------------------
# Anclaje de rutas (Convención C1 / Paso D3)
# --------------------------------------------------------------------------------------

def test_una_ruta_absoluta_se_respeta_intacta(tmp_path):
    """Las pruebas deben poder inyectar ficheros temporales sin que se reanclen."""
    ruta = escribir_politica(tmp_path, BASE)
    assert cargar_politica(ruta) == PoliticaRetencion("1.0.0", 180, 7)


def test_la_ruta_por_defecto_no_depende_del_directorio_de_trabajo(monkeypatch, tmp_path):
    """H-18: el resultado no puede cambiar según desde dónde se lance el proceso."""
    desde_la_raiz = cargar_politica()
    monkeypatch.chdir(tmp_path)
    assert cargar_politica() == desde_la_raiz
