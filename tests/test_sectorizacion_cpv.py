"""Regresiones de la sectorización por CPV (H-26).

El sector `social` era inalcanzable: `educativo` declara "85312110" (guarderías escolares
sociales), cuyo prefijo de 3 dígitos es `853` —la rama de asistencia social del CPV—, y la
asignación se quedaba con el primer sector del YAML que casara cualquier prefijo. Los siete
CPVs sociales del perfil se etiquetaban como educativos.

El defecto **no alteraba el score** (+40 por cualquiera de los dos sectores), y por eso ni la
suite ni el arranque en vivo lo detectaron: no había ninguna cifra incorrecta en pantalla.
Alteraba `sector_detectado`, que se persiste en la base y alimenta la API y el Cockpit.
"""

import pytest

from src.filtro import Filtro


# Los siete CPVs que el perfil declara como sector social. Ninguno es una guardería.
CPVS_SOCIALES = [
    "85300000",  # Asistencia social general
    "85310000",  # Asistencia social con o sin alojamiento
    "85311000",  # Asistencia social con alojamiento
    "85312000",  # Asistencia social sin alojamiento
    "85312100",  # Centros de día
    "85312300",  # Asesoramiento sobre bienestar social
    "85320000",  # Servicios sociales comunitarios
]

# Un representante por sector, para comprobar que la corrección no desplaza a los demás.
CPVS_POR_SECTOR = [
    ("80110000", "educativo"),
    ("92510000", "cultural"),
    ("55523100", "restauracion"),
    ("90910000", "mantenimiento"),
    ("79400000", "consultoria"),
    ("98130000", "comunitario_asociativo"),
]


def licitacion(cpv):
    """Expediente mínimo y neutro: sólo varía el CPV."""
    return {
        "titulo": "Prestació de serveis",
        "organo": "Ajuntament de Terrassa",
        "importe": 150000.0,
        "vec": 150000.0,
        "tipo_contrato_codigo": "2",
        "estado": "PUB",
        "cpvs": [cpv],
        "fecha_limite": "2099-12-31",
        "procedimiento_codigo": "1",
        "country_subentity_code": "ES511",
        "localidad": "Terrassa",
    }


@pytest.mark.parametrize("cpv", CPVS_SOCIALES)
def test_los_cpvs_sociales_se_asignan_al_sector_social(cpv):
    """El defecto original: los siete devolvían 'Educativo'."""
    assert Filtro().filtrar(licitacion(cpv))["sector_detectado"] == "Social"


def test_la_guarderia_escolar_social_sigue_siendo_educativa():
    """Decisión de negocio del 2026-08-07: en su base es una guardería.

    Es el caso que impide corregir H-26 moviendo el CPV de sector: hacerlo eliminaría el
    síntoma etiquetando como social justo el único CPV de la familia que no lo es.
    """
    assert Filtro().filtrar(licitacion("85312110"))["sector_detectado"] == "Educativo"


def test_un_hermano_no_declarado_cae_del_lado_correcto_por_prelacion():
    """`85322000` (acción comunitaria) apareció en la beta y no está en el perfil.

    Sin código exacto, `853` empata entre educativo, social y consultoría. Lo desempata
    `prelacion_sectores`, no el orden de las claves del YAML.
    """
    filtro = Filtro()
    assert filtro.filtrar(licitacion("85322000"))["sector_detectado"] == "Social"
    assert filtro._resolver_sector_cpv("85322000") == ("social", "prefijo de 3 + prelación")


@pytest.mark.parametrize("cpv,sector", CPVS_POR_SECTOR)
def test_los_demas_sectores_no_se_ven_desplazados(cpv, sector):
    assert Filtro().filtrar(licitacion(cpv))["sector_detectado"] == sector.capitalize()


def test_el_codigo_completo_gana_al_prefijo_aunque_el_prefijo_sea_mas_prioritario():
    """La prelación desempata dentro de un nivel; nunca asciende un sector de otro.

    `85312110` casa por código completo en educativo y por prefijo en social. Como social
    encabeza la prelación, un algoritmo que mezclara ambos niveles lo mandaría a social.
    """
    filtro = Filtro()
    assert filtro.prelacion_sectores.index("social") < filtro.prelacion_sectores.index("educativo")
    assert filtro._resolver_sector_cpv("85312110") == ("educativo", "código completo")


def test_un_cpv_fuera_del_perfil_no_casa_ningun_sector():
    """Debe caer a la red de seguridad por división, no inventarse un sector."""
    assert Filtro()._resolver_sector_cpv("72000000") == (None, None)


def test_ningun_cpv_del_perfil_queda_huerfano():
    """Todo CPV declarado debe resolver al sector que lo declara.

    Es la prueba que habría destapado H-26 el primer día: no afirma sobre casos elegidos a
    mano, sino sobre el perfil entero.
    """
    filtro = Filtro()
    for sector, cpvs in filtro.perfil["sectores_cpv"].items():
        for cpv in cpvs:
            resuelto, _ = filtro._resolver_sector_cpv(str(cpv).strip())
            assert resuelto == sector, f"{cpv} declarado en '{sector}' resuelve a '{resuelto}'"


def test_ningun_cpv_esta_declarado_en_dos_sectores():
    """`85312300` estaba en social y en consultoría a la vez.

    Un CPV duplicado deja su sector en manos de la prelación en lugar de una decisión.
    """
    filtro = Filtro()
    duplicados = {c: s for c, s in filtro.cpv_exacto.items() if len(s) > 1}
    assert not duplicados, f"CPVs declarados en varios sectores: {duplicados}"


def test_la_prelacion_cubre_todos_los_sectores_declarados():
    """Un sector nuevo sin sitio en la prelación reintroduciría el defecto por la puerta de atrás."""
    filtro = Filtro()
    assert set(filtro.prelacion_sectores) == set(filtro.perfil["sectores_cpv"])


def test_la_correccion_no_altera_el_score():
    """El contrato del cambio: sólo se mueve el sector, nunca la puntuación.

    Antes y después de H-26 un CPV core suma +40. Si esta prueba falla, la corrección se ha
    llevado por delante la comparabilidad con lo puntuado hasta ahora.
    """
    filtro = Filtro()
    scores = {filtro.filtrar(licitacion(cpv))["score"] for cpv in CPVS_SOCIALES + ["85312110"]}
    assert len(scores) == 1, f"El sector no debe mover el score, y se obtuvieron {scores}"
