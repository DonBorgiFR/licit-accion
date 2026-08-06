"""
tests/conftest.py — Aislamiento del directorio de datos durante las pruebas

La suite escribía en el `data/` real del proyecto: creaba `licitaciones.db` y volcaba
`pipeline.jsonl` y los informes CSV en la carpeta de trabajo. Con datos reales dentro, eso
significa que ejecutar los tests tocaba la base de producción.

Aquí se redirige `DATA_DIR_INCOOP` a un directorio temporal para que cualquier ruta por
defecto del sistema caiga fuera del proyecto.

**Se fija al importar este fichero, no dentro de un fixture.** `src/api/dependencies.py` crea
su gestor de trazabilidad como singleton de módulo, y ese constructor ya crea el directorio de
destino: ocurre al importar, durante la recolección de pruebas, mucho antes de que se ejecute
ningún fixture. pytest importa `conftest.py` antes que los módulos de prueba, así que éste es
el único punto lo bastante temprano.

**No se toca `DB_PATH_INCOOP`**: en `Memoria.__init__` esa variable tiene prioridad sobre el
argumento `db_path`, así que fijarla globalmente redirigiría también las pruebas que pasan su
propia ruta temporal y destruiría su aislamiento.
"""

import os
import shutil
import tempfile

import pytest

_DIRECTORIO_DE_DATOS = tempfile.mkdtemp(prefix="bfr_incoop_pruebas_")
os.environ["DATA_DIR_INCOOP"] = _DIRECTORIO_DE_DATOS


@pytest.fixture(scope="session", autouse=True)
def limpiar_directorio_de_datos():
    """Retira el directorio temporal al terminar la sesión de pruebas."""
    yield _DIRECTORIO_DE_DATOS
    shutil.rmtree(_DIRECTORIO_DE_DATOS, ignore_errors=True)
