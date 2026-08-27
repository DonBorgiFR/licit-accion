"""H-56 · El Centinela deja de pedir un dictamen y recibir el análisis de otro.

`GeminiProvider.consultar()` fijaba **siempre** `ESQUEMA_OPENAPI_ANALISIS_SEMANTICO` como
`responseSchema`, y `proveedor_llm_factory()` sirve el mismo proveedor a los dos consumidores
—lo dice su propio docstring—. De modo que cuando el Centinela pedía su dictamen, la API de
Gemini estaba **obligada por structured output** a contestar con el esquema del analista de
licitaciones.

El resultado no era un modelo respondiendo mal: era **un modelo obligado a responder otra cosa**.
La intersección entre lo que el proveedor imponía y lo que el Centinela exige era **vacía**, y por
eso el evento de degradación nombraba los cuatro campos a la vez, siempre los mismos. Medido en el
rastro: `boletin_llm_started` 10, `boletin_llm_degraded` 10, `boletin_llm_succeeded` **0**. No
podía funcionar ningún día.

**Estas pruebas afirman sobre la PETICIÓN, no sobre la respuesta**, y es el punto entero del
fichero. Comprobar que el dictamen sale bien exigiría llamar al modelo, y eso lo prohíbe la
Convención C5. Lo que sí se puede afirmar sin salir a la red —y es donde vivía el fallo— es que
**se está pidiendo lo que se necesita**.
"""

import json
from unittest.mock import patch

import pytest

from src.analista import (
    ESQUEMA_OPENAPI_ANALISIS_SEMANTICO,
    EsquemaIncompatibleError,
    GeminiProvider,
    OllamaProvider,
    campos_obligatorios_de_esquema,
    verificar_esquema_cubre,
)
from src.centinela import (
    ESQUEMA_OPENAPI_DICTAMEN_CENTINELA,
    AlertaBoletinDTO,
    AnalistaBoletinesIA,
    DictamenCentinelaDTO,
)


# =====================================================================
# ANDAMIAJE
# =====================================================================

def alerta():
    return AlertaBoletinDTO(
        fuente="BOPB",
        num_boletin="2026-08-27",
        fecha_publicacion="2026-08-27T07:00:00Z",
        organo_emisor="Ajuntament de Prova",
        municipio="Prova",
        titulo_anuncio="Aprovació inicial del pressupost del servei de neteja",
        texto_sumario="Dotació pressupostària per al servei de neteja d'equipaments municipals.",
        id_alerta="alerta-de-prueba",
    )


class ProveedorEspia:
    """Registra con qué esquema se le llamó. No sale a la red (Convención C5)."""

    def __init__(self):
        self.esquema_recibido = "NO SE LLAMO"
        self.veces = 0

    def consultar(self, prompt_sistema, prompt_usuario, timeout=120, response_schema=None):
        self.veces += 1
        self.esquema_recibido = response_schema
        return {
            "raw_response": json.dumps({
                "es_oportunidad_temprana": True,
                "nivel_interes": "ALTO",
                "categoria_fase_temprana": "PRESUPUESTO",
                "resumen_ejecutivo": "Oportunitat clara.",
                "acciones_recomendadas": ["Contactar amb l'òrgan"],
                "estimacion_meses_hasta_licitacion": 4,
            }),
            "modelo": "espia/1.0",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tiempo_seg": 0.0,
        }


# =====================================================================
# 1 · LA FORMA DEL DEFECTO, FIJADA COMO HECHO
# =====================================================================

def test_el_esquema_del_analista_no_sirve_para_el_centinela():
    """**La prueba que documenta H-56.** Los dos esquemas no comparten un solo campo.

    Se conserva aunque el defecto esté reparado: es lo que explica por qué el error de
    degradación nombraba los cuatro campos a la vez y siempre los mismos.
    """
    del_analista = campos_obligatorios_de_esquema(ESQUEMA_OPENAPI_ANALISIS_SEMANTICO)
    del_centinela = set(DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS)

    assert del_analista & del_centinela == set()


def test_el_esquema_del_centinela_cubre_lo_que_su_dto_exige():
    """**La regresión central.** Si los dos se desincronizan, cae aquí y no en producción."""
    verificar_esquema_cubre(
        ESQUEMA_OPENAPI_DICTAMEN_CENTINELA,
        DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS,
    )


def test_un_esquema_incompleto_detiene_la_llamada_en_vez_de_degradarla():
    """Se detiene, no se degrada: gastar cuota sabiendo que no servirá es peor que parar."""
    incompleto = {"type": "OBJECT", "properties": {}, "required": ["nivel_interes"]}

    with pytest.raises(EsquemaIncompatibleError) as exc:
        verificar_esquema_cubre(incompleto, DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS, "el Centinela")

    # El error dice qué falta, no sólo que algo falla.
    assert "es_oportunidad_temprana" in str(exc.value)
    assert "resumen_ejecutivo" in str(exc.value)


def test_el_centinela_no_se_construye_con_un_esquema_que_no_le_sirve():
    """La incompatibilidad se detecta al construir, antes de que haya nada que analizar."""
    roto = {"type": "OBJECT", "properties": {}, "required": ["otra_cosa"]}

    with patch("src.centinela.ESQUEMA_OPENAPI_DICTAMEN_CENTINELA", roto):
        with pytest.raises(EsquemaIncompatibleError):
            AnalistaBoletinesIA(autoinicializar_proveedor=False)


# =====================================================================
# 2 · LA PETICIÓN LLEVA EL ESQUEMA DEL LLAMADOR
# =====================================================================

def test_el_centinela_pide_su_propio_esquema_y_no_el_del_analista():
    """**La prueba que habría cazado H-56 el primer día.**"""
    espia = ProveedorEspia()
    analista = AnalistaBoletinesIA(proveedor_llm=espia)

    analista.analizar_alerta(alerta())

    assert espia.veces == 1
    assert espia.esquema_recibido is not None, "se llamó sin esquema: el proveedor caería al del analista"
    assert espia.esquema_recibido is not ESQUEMA_OPENAPI_ANALISIS_SEMANTICO
    assert campos_obligatorios_de_esquema(espia.esquema_recibido) >= set(
        DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS
    )


def test_con_el_esquema_correcto_el_dictamen_ya_no_se_degrada():
    """El efecto que se busca: un dictamen completo deja de caer en modo degradado."""
    analista = AnalistaBoletinesIA(proveedor_llm=ProveedorEspia())

    resultado = analista.analizar_alerta(alerta())

    assert resultado.estado_operativo == "ANALIZADA_IA"
    assert resultado.dictamen_ia.nivel_interes == "ALTO"
    assert resultado.dictamen_ia.modo_degradado is False


# =====================================================================
# 3 · LO QUE VIAJA DE VERDAD EN LA PETICIÓN HTTP
# =====================================================================

class _RespuestaFalsa:
    """Sustituye a `urlopen` sin tocar la red (Convención C5)."""

    status = 200

    def __init__(self, cuerpo):
        self._cuerpo = json.dumps(cuerpo).encode("utf-8")

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _capturar_payload(response_schema):
    """Devuelve el cuerpo JSON que `GeminiProvider` enviaría con ese esquema."""
    capturado = {}

    def falso_urlopen(req, timeout=None):
        capturado["payload"] = json.loads(req.data.decode("utf-8"))
        return _RespuestaFalsa({
            "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        })

    proveedor = GeminiProvider(api_key="clave-de-prueba")
    with patch("urllib.request.urlopen", falso_urlopen):
        proveedor.consultar("sistema", "usuario", response_schema=response_schema)
    return capturado["payload"]


def test_la_peticion_http_lleva_el_esquema_que_pidio_el_llamador():
    """Se afirma sobre el cuerpo que sale por el cable, no sobre lo que creemos que sale."""
    payload = _capturar_payload(ESQUEMA_OPENAPI_DICTAMEN_CENTINELA)

    enviado = payload["generationConfig"]["responseSchema"]

    assert set(enviado["required"]) >= set(DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS)
    assert "subrogacion" not in enviado["properties"]


def test_sin_esquema_el_proveedor_conserva_el_del_analista():
    """Compatibilidad hacia atrás *(Regla 14)*: el llamador que ya funcionaba no se toca."""
    payload = _capturar_payload(None)

    assert payload["generationConfig"]["responseSchema"] == ESQUEMA_OPENAPI_ANALISIS_SEMANTICO


def test_el_enum_de_nivel_de_interes_no_ofrece_desconocido():
    """`DESCONOCIDO` es del sistema, no del modelo *(Convención C6)*.

    El DTO lo admite porque es el valor del Modo Degradado. Ofrecérselo al modelo dejaría
    que un análisis dubitativo se declarase degradado, y esa declaración entraría como si
    fuera un veredicto real: quien decide que no se pudo medir es quien mide.
    """
    niveles = ESQUEMA_OPENAPI_DICTAMEN_CENTINELA["properties"]["nivel_interes"]["enum"]

    assert "DESCONOCIDO" not in niveles
    assert set(niveles) == {"ALTO", "MEDIO", "BAJO", "NULO"}


# =====================================================================
# 4 · OLLAMA: SE DOCUMENTA, NO SE EMULA
# =====================================================================

def test_ollama_acepta_el_esquema_y_no_revienta():
    """No admite esquemas, pero la interfaz es común: recibirlo no puede ser un error.

    Ollama sólo ofrece `format: "json"`, que garantiza JSON válido pero no su forma. Emular
    aquí una validación propia daría la ilusión de una garantía que el proveedor no da.
    """
    capturado = {}

    def falso_urlopen(req, timeout=None):
        capturado["payload"] = json.loads(req.data.decode("utf-8"))
        return _RespuestaFalsa({"message": {"content": "{}"}})

    proveedor = OllamaProvider()
    with patch("urllib.request.urlopen", falso_urlopen):
        proveedor.consultar("sistema", "usuario", response_schema=ESQUEMA_OPENAPI_DICTAMEN_CENTINELA)

    assert capturado["payload"]["format"] == "json"
    assert "responseSchema" not in capturado["payload"]
