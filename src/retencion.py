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
from typing import Any, Dict, Optional, Tuple

import yaml

from src import ESTADOS_OPERATIVOS_VALIDOS, normalizar_estado_operativo, ruta_proyecto

NOMBRE_FICHERO = "retencion.yaml"

#: Estados que el archivado automático no puede tocar por mucho que lo diga el fichero.
#: `Presentada` es una oferta entregada y sin resolver: lo más vivo del embudo. Archivarla
#: la sacaría del canal principal justo mientras se espera la adjudicación.
ESTADOS_NO_ARCHIVABLES = ("presentada",)


class PoliticaRetencionInvalida(Exception):
    """La política de retención falta, no se puede leer o es incoherente.

    Error tipado del Contrato de la Capa 9. Se traduce a HTTP 503: la purga **no** se
    ejecuta. Nunca se degrada a un plazo por defecto.
    """


@dataclass(frozen=True)
class PoliticaArchivado:
    """Criterio de archivado automático (Capa 9, Paso 4).

    Archivar es la operación reversible del Depurador: escribe `deleted_at` y saca el lote
    del canal principal, sin tocar ni un fichero ni la columna `estado_operativo`.
    """

    dias_tras_fecha_limite: int
    #: Normalizados en minúsculas: toda comparación de estado se hace así (H-27).
    estados_archivables: Tuple[str, ...]
    archivar_expediente_con_todos_sus_lotes: bool


@dataclass(frozen=True)
class PoliticaRetencion:
    """Plazos vigentes y la versión bajo la que se ejecuta una purga.

    Inmutable a propósito: la política se lee una vez y no puede alterarse a mitad de una
    purga, de modo que el evento de auditoría y lo realmente borrado siempre concuerdan.

    `archivado` es opcional y vale `None` cuando el fichero no declara el bloque. No es una
    excepción a la doctrina de "sin valores por defecto", sino su aplicación: sin criterio
    declarado **no se archiva nada**, y el pipeline lo dice en voz alta. Lo que no se
    tolera es un bloque presente y mal formado, que se rechaza como cualquier otro error.
    """

    version: str
    documentos_dias: int
    backups_dias: int
    archivado: Optional[PoliticaArchivado] = None


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


def _leer_archivado(datos: Dict[str, Any]) -> Optional[PoliticaArchivado]:
    """Lee y valida el bloque `archivado`, que es opcional pero no puede ser aproximado.

    Ausente → `None`, y el Depurador no archiva. Presente → se exige entero, lista de
    estados reconocibles y booleano explícito.
    """
    if "archivado" not in datos:
        return None

    bloque = datos["archivado"]
    if not isinstance(bloque, dict):
        raise PoliticaRetencionInvalida(
            f"El bloque 'archivado' de {NOMBRE_FICHERO} debe ser un mapa de claves, "
            f"y se recibió {bloque!r}."
        )

    dias = _entero_positivo(bloque, "dias_tras_fecha_limite")

    crudos = bloque.get("estados_archivables")
    if not isinstance(crudos, list) or not crudos:
        raise PoliticaRetencionInvalida(
            "'estados_archivables' debe ser una lista no vacía de estados operativos. "
            "Una lista vacía no significa 'archívalo todo': significa que no hay criterio."
        )

    estados = []
    for crudo in crudos:
        if not isinstance(crudo, str):
            raise PoliticaRetencionInvalida(
                f"'estados_archivables' contiene {crudo!r}, que no es un estado operativo."
            )
        estado = normalizar_estado_operativo(crudo)
        if estado not in ESTADOS_OPERATIVOS_VALIDOS:
            raise PoliticaRetencionInvalida(
                f"'{crudo}' no es un estado operativo reconocido. Válidos: "
                f"{', '.join(ESTADOS_OPERATIVOS_VALIDOS)}. Un estado mal escrito no "
                "archivaría nada y el fallo pasaría inadvertido."
            )
        if estado in ESTADOS_NO_ARCHIVABLES:
            raise PoliticaRetencionInvalida(
                f"'{crudo}' no puede archivarse automáticamente. Una oferta presentada y "
                "sin resolver es lo más vivo del embudo: archivarla escondería el trabajo "
                "en curso justo mientras se espera la adjudicación."
            )
        if estado not in estados:
            estados.append(estado)

    cascada = bloque.get("archivar_expediente_con_todos_sus_lotes")
    if not isinstance(cascada, bool):
        raise PoliticaRetencionInvalida(
            "'archivar_expediente_con_todos_sus_lotes' debe ser true o false de forma "
            f"explícita, y se recibió {cascada!r}."
        )

    return PoliticaArchivado(
        dias_tras_fecha_limite=dias,
        estados_archivables=tuple(estados),
        archivar_expediente_con_todos_sus_lotes=cascada,
    )


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
        archivado=_leer_archivado(datos),
    )
