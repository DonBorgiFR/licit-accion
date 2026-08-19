"""Bloque 3, Paso 2 · El título legible.

Son **dos problemas con el mismo síntoma**, y confundirlos lleva a arreglar el que no es: uno de
presentación —la tabla recorta a dos líneas— y otro de datos, que la fuente vuelca el anuncio
entero en el campo. El título más largo de la base mide **1.663 caracteres** y su título real son
las primeras veinte palabras. Lo segundo no lo arregla ningún ancho de columna.

Lo que estas regresiones fijan:

* El original **nunca se toca**: sigue íntegro y es lo que sirve la API en `titulo`.
* Las tres reglas, en orden, y cada una con el caso real que la justifica.
* **Ninguna palabra partida**, que es lo que pidió dirección expresamente.
* El tope es **200**, y hay una prueba que documenta por qué no 120.
"""

import pytest

from src import TOPE_TITULO, VERSION_TITULO, titulo_legible
from src.api.schemas import LicitacionSchema

# El peor caso real de la base: título de verdad, salto de párrafo, y el acuerdo del pleno.
REAL_1663 = (
    "EXPEDIENT214 2026 - CONTRACTACIÓ DEL SERVEI DE DESENVOLUPAMENT DE PROJECTES COMUNITARIS "
    "I DELS SERVEIS D'INTERVENCIÓ SOCIOEDUCATIVA NO RESIDENCIAL DEL CONSELL COMARCAL DE "
    "L'ALTA RIBAGORÇA.\n\n"
    "El Ple del Consell Comarcal de l'Alta Ribagorça, en sessió ordinària 229 02 2026 10 02 07 "
    "2026, celebrada el dia 2 de juliol de 2026, va adoptar, entre altres, l'acord d'iniciar i "
    "desenvolupar l'expedient de contractació dels serveis " + "de la manera que segueix. " * 40
)

# Real: una sola frase seguida de la descripción del objeto. No hay salto de párrafo.
REAL_FRASE = (
    "Prestació dels serveis de realització de tasques tècniques especialitzades al Teatre de "
    "Blanes. Comprèn la realització de les tasques necessàries per dur a terme els muntatges, "
    "assajos, funcions i desmuntatges de les activitats programades al teatre municipal."
)

# Real, y ya legible: 135 caracteres. No debe tocarse.
REAL_CORRECTO = (
    "Serveis especialitzats de cerca, avaluació i selecció de personal i membres dels òrgans "
    "de govern del Grup Institut Català de Finances."
)


# ======================================================================================
# Las tres reglas, cada una con su caso real
# ======================================================================================

def test_regla_1_corta_el_cuerpo_del_anuncio():
    """El peor caso de la base: 1.663 caracteres de los que el título son los primeros 187."""
    corto = titulo_legible(REAL_1663)

    assert corto.endswith("L'ALTA RIBAGORÇA."), "Conserva la frase completa, con su punto"
    assert "El Ple del Consell Comarcal" not in corto, "Y deja fuera el acuerdo del pleno"
    assert len(corto) < 200


def test_regla_2_corta_en_la_primera_frase():
    """El caso que más se repite: una frase, y detrás la descripción del objeto."""
    corto = titulo_legible(REAL_FRASE)

    assert corto == "Prestació dels serveis de realització de tasques tècniques especialitzades al Teatre de Blanes."
    assert not corto.endswith("…"), "Cortar por la frase da un título completo, no truncado"


def test_regla_3_el_tope_no_parte_palabras():
    """Lo que pidió dirección expresamente."""
    largo = "Servicio de " + "mantenimiento integral y limpieza de dependencias " * 20

    corto = titulo_legible(largo)

    assert len(corto) <= TOPE_TITULO
    assert corto.endswith("…")
    ultima = corto[:-1].strip().split(" ")[-1]
    assert ultima in largo.split(), f"'{ultima}' no es una palabra entera del original"


def test_un_titulo_ya_legible_no_se_toca():
    """135 caracteres es un título de licitación normal y completo."""
    assert titulo_legible(REAL_CORRECTO) == REAL_CORRECTO


# ======================================================================================
# Por qué el tope es 200
# ======================================================================================

def test_el_tope_es_200_y_no_120():
    """Deja constancia de la medición, para que nadie lo baje 'porque se ve mejor'.

    Sobre los 63 expedientes reales, ya aplicados párrafo y frase, con 120 llegan enteros 27
    (43 %) y con 200 llegan 48 (76 %). La diferencia no son títulos desbocados: son títulos
    correctos de 125-135 caracteres que con 120 se recortarían sin motivo.
    """
    assert TOPE_TITULO == 200
    assert titulo_legible(REAL_CORRECTO) == REAL_CORRECTO, "135 caracteres llegan enteros"
    assert titulo_legible(REAL_CORRECTO, tope=120).endswith("…"), "Con 120 se recortaría"


# ======================================================================================
# Casos límite
# ======================================================================================

@pytest.mark.parametrize("entrada", [None, "", "   ", "\n\n"])
def test_entradas_vacias_no_revientan(entrada):
    assert titulo_legible(entrada) == ""


def test_no_corta_por_una_abreviatura_en_versales():
    """Los pliegos están llenos de 'S.A.', 'U.T.E.' y 'S.C.C.L.'.

    **La mayúscula detrás no es un detalle del ejemplo: es lo que hace válida la prueba.** Con
    minúscula, la regla de frase no dispararía de todos modos —exige mayúscula después del
    punto— y esto pasaría sin ejercitar nada. Con 'De' detrás, sólo la cautela del punto
    precedido de versal impide que el título quede en 'Servicio prestado por ACME S.A.'
    """
    t = "Servicio prestado por ACME S.A. De gestion integral, " + "instalaciones deportivas " * 8

    corto = titulo_legible(t)

    assert corto != "Servicio prestado por ACME S.A.", "Cortó por la abreviatura"
    assert corto.startswith("Servicio prestado por ACME S.A. De gestion integral,")


def test_si_corta_por_un_punto_de_frase_de_verdad():
    """La contraparte de la anterior: la cautela no puede desactivar la regla.

    Sin esta prueba, hacer el lookbehind más estricto pasaría inadvertido y la regla 2 dejaría
    de funcionar sin que nada se pusiera rojo.
    """
    t = "Servicio de conserjeria del centro civico. " + "Incluye tareas auxiliares varias. " * 8

    assert titulo_legible(t) == "Servicio de conserjeria del centro civico."


def test_los_saltos_de_linea_sueltos_tambien_cortan():
    """Algunas fuentes separan con un solo salto, no con párrafo."""
    assert titulo_legible("Título de la licitación\nCuerpo del anuncio que sigue") == "Título de la licitación"


def test_los_espacios_repetidos_se_normalizan():
    assert titulo_legible("Servicio   de    limpieza") == "Servicio de limpieza"


def test_hay_version_declarada():
    """Regla 4: el criterio está versionado aunque no se persista por fila."""
    assert VERSION_TITULO == "1.0.0"


# ======================================================================================
# La frontera de la API
# ======================================================================================

def test_la_api_sirve_los_dos_titulos():
    """El corto para la tabla y el completo para la ficha. **El original no se modifica.**"""
    s = LicitacionSchema.model_validate(
        {"id": "EXP-1", "titulo": REAL_1663, "organo": "Consell Comarcal", "fuente": "CCAA"}
    )

    assert s.titulo == REAL_1663, "El campo `titulo` conserva el original íntegro"
    assert len(s.titulo_corto) < 200
    assert s.titulo_corto.endswith("L'ALTA RIBAGORÇA.")


def test_titulo_corto_viaja_en_el_json():
    """Si no sale en la serialización, la tabla no puede pintarlo."""
    s = LicitacionSchema.model_validate(
        {"id": "EXP-1", "titulo": REAL_FRASE, "organo": "O", "fuente": "F"}
    )

    d = s.model_dump()

    assert "titulo_corto" in d and "titulo" in d
    assert d["titulo_corto"] != d["titulo"]


def test_un_expediente_sin_titulo_no_rompe_la_pagina():
    """H-C3: la tolerancia a nulos de la frontera de lectura sigue en pie."""
    s = LicitacionSchema.model_validate(
        {"id": "EXP-1", "titulo": None, "organo": "O", "fuente": "F"}
    )

    assert s.titulo == "(sin título)"
    assert s.titulo_corto == "(sin título)"
