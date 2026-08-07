"""Política de retención de datos — Capa 9, Paso 2.

Único punto de lectura de `config/retencion.yaml`. Antes de este módulo, los plazos que
deciden qué se borra del disco vivían como literales dentro de las llamadas de
`src/main.py` (`dias_retencion=90`, `dias_retencion=7`): un criterio operativo invisible
y sin versión, en contra de la Regla 4.

**Este módulo no aplica valores por defecto.** Si la política falta o es incoherente,
lanza `PoliticaRetencionInvalida` y el llamador decide. Es deliberado, y es la lección de
H-18: cuando `config/perfil_incoop.yaml` no se encontraba, el perfil se cargaba vacío y el
sistema seguía en silencio con otros criterios —la misma licitación puntuaba 71 desde la
raíz y 47 desde otra carpeta—. Un fichero de configuración ausente no puede degradarse a
un comportamiento distinto que nadie ha pedido: **aquí, no poder leer la política significa
no purgar**, que es la degradación segura para una operación irreversible.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict

import yaml

from src import ruta_proyecto

NOMBRE_FICHERO = "retencion.yaml"


class PoliticaRetencionInvalida(Exception):
    """La política de retención falta, no se puede leer o es incoherente.

    Error tipado del Contrato de la Capa 9. Se traduce a HTTP 503: la purga **no** se
    ejecuta. Nunca se degrada a un plazo por defecto.
    """


@dataclass(frozen=True)
class PoliticaRetencion:
    """Plazos vigentes y la versión bajo la que se ejecuta una purga.

    Inmutable a propósito: la política se lee una vez y no puede alterarse a mitad de una
    purga, de modo que el evento de auditoría y lo realmente borrado siempre concuerdan.
    """

    version: str
    documentos_dias: int
    backups_dias: int


def _entero_positivo(datos: Dict[str, Any], clave: str) -> int:
    """Exige un entero estrictamente positivo, rechazando lo que YAML acepta y aquí no."""
    if clave not in datos:
        raise PoliticaRetencionInvalida(
            f"Falta la clave '{clave}' en {NOMBRE_FICHERO}. "
            "Sin plazo declarado no se puede decidir qué borrar."
        )
    valor = datos[clave]
    # `bool` es subclase de `int` en Python: `True` pasaría como 1 día de retención.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise PoliticaRetencionInvalida(
            f"'{clave}' debe ser un número entero de días, y se recibió {valor!r}."
        )
    if valor <= 0:
        raise PoliticaRetencionInvalida(
            f"'{clave}' debe ser mayor que cero, y se recibió {valor}. "
            "Un plazo de 0 días purgaría lo recién descargado."
        )
    return valor


def cargar_politica(ruta: str = None) -> PoliticaRetencion:
    """Lee y valida la política de retención.

    `ruta` permite inyectar un fichero alternativo en las pruebas. Una ruta absoluta se
    respeta intacta; una relativa se ancla a la raíz del proyecto, nunca al directorio de
    trabajo (Convención C1 y Paso D3).

    Lanza `PoliticaRetencionInvalida` si el fichero falta, no es legible, no es un mapa
    YAML o declara plazos que no son enteros positivos.
    """
    if ruta is None:
        ruta = ruta_proyecto(os.path.join("config", NOMBRE_FICHERO))
    elif not os.path.isabs(ruta):
        ruta = ruta_proyecto(ruta)

    if not os.path.exists(ruta):
        raise PoliticaRetencionInvalida(
            f"No se encuentra la política de retención en '{ruta}'. "
            "Sin política declarada no se purga nada."
        )

    try:
        with open(ruta, "r", encoding="utf-8") as fichero:
            crudo = yaml.safe_load(fichero)
    except (OSError, yaml.YAMLError) as exc:
        raise PoliticaRetencionInvalida(
            f"No se pudo leer la política de retención en '{ruta}': {exc}"
        ) from exc

    if not isinstance(crudo, dict) or not isinstance(crudo.get("retencion"), dict):
        raise PoliticaRetencionInvalida(
            f"'{ruta}' no contiene un bloque 'retencion' válido."
        )

    datos = crudo["retencion"]

    version = datos.get("version")
    if not isinstance(version, str) or not version.strip():
        raise PoliticaRetencionInvalida(
            "La política debe declarar una 'version' no vacía: cada purga registra bajo "
            "qué versión se ejecutó, y sin ella el rastro de auditoría no es reconstruible."
        )

    return PoliticaRetencion(
        version=version.strip(),
        documentos_dias=_entero_positivo(datos, "documentos_dias"),
        backups_dias=_entero_positivo(datos, "backups_dias"),
    )
