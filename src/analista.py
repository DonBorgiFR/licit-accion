import os
import time
import json
import urllib.request
import urllib.error
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

# =====================================================================
# JERARQUÍA DE ERRORES ESTRUCTURADOS DE LA CAPA 5
# =====================================================================

class AnalistaException(Exception):
    """Excepción base para la Capa 5 (El Analista IA)"""
    pass

class ValidationError(AnalistaException):
    """Fallo en la validación del esquema DTO o datos deserializados del LLM"""
    pass

class ProviderError(AnalistaException):
    """Fallo en la llamada o respuesta del proveedor LLM (Ollama / Gemini)"""
    pass


# =====================================================================
# DATACLASSES DTO DE ANÁLISIS SEMÁNTICO (CONTRATOS DE SERVICIO v5.1.0)
# =====================================================================

@dataclass(frozen=True)
class SubrogacionDTO:
    """Metadatos de obligación de subrogación de personal (Art. 130 LCSP)"""
    detectada: bool = False
    num_trabajadores: Optional[int] = None
    convenio_colectivo: Optional[str] = None
    desglose_salarial_completo: bool = False
    coste_estimado_anual: Optional[float] = None
    riesgo_evaluado: str = "MEDIO"  # 'BAJO', 'MEDIO', 'ALTO', 'CRITICO'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'SubrogacionDTO':
        if not isinstance(data, dict):
            return cls()
        
        num_tr = data.get("num_trabajadores")
        if num_tr is not None:
            try:
                num_tr = int(num_tr)
            except (ValueError, TypeError):
                num_tr = None

        coste_est = data.get("coste_estimado_anual")
        if coste_est is not None:
            try:
                coste_est = float(coste_est)
            except (ValueError, TypeError):
                coste_est = None

        riesgo = str(data.get("riesgo_evaluado", "MEDIO")).upper()
        if riesgo not in ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']:
            riesgo = "MEDIO"

        return cls(
            detectada=bool(data.get("detectada", False)),
            num_trabajadores=num_tr,
            convenio_colectivo=str(data["convenio_colectivo"]) if data.get("convenio_colectivo") else None,
            desglose_salarial_completo=bool(data.get("desglose_salarial_completo", False)),
            coste_estimado_anual=coste_est,
            riesgo_evaluado=riesgo
        )


@dataclass(frozen=True)
class RevisionPreciosDTO:
    """Evaluación de fórmulas de revisión de precios e inflación (Art. 103 LCSP)"""
    permitida: bool = False
    formula_detectada: Optional[str] = None
    art_103_aplica: bool = False
    observaciones: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'RevisionPreciosDTO':
        if not isinstance(data, dict):
            return cls()
        
        return cls(
            permitida=bool(data.get("permitida", False)),
            formula_detectada=str(data["formula_detectada"]) if data.get("formula_detectada") else None,
            art_103_aplica=bool(data.get("art_103_aplica", False)),
            observaciones=str(data["observaciones"]) if data.get("observaciones") else None
        )


@dataclass(frozen=True)
class CriteriosAdjudicacionDTO:
    """Distribución de ponderaciones entre juicio de valor y fórmulas automáticas"""
    peso_precio_formulas: int = 50
    peso_juicio_valor: int = 50
    requiere_memoria_tecnica: bool = True
    criterios_desglose: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'CriteriosAdjudicacionDTO':
        if not isinstance(data, dict):
            return cls()

        try:
            peso_pf = int(data.get("peso_precio_formulas", 50))
        except (ValueError, TypeError):
            peso_pf = 50

        try:
            peso_jv = int(data.get("peso_juicio_valor", 50))
        except (ValueError, TypeError):
            peso_jv = 50

        desglose = data.get("criterios_desglose")
        if not isinstance(desglose, list):
            desglose = []

        return cls(
            peso_precio_formulas=peso_pf,
            peso_juicio_valor=peso_jv,
            requiere_memoria_tecnica=bool(data.get("requiere_memoria_tecnica", True)),
            criterios_desglose=desglose
        )


@dataclass(frozen=True)
class GarantiaDefinitivaDTO:
    """Garantía definitiva y modalidad de cobertura (arts. 107–108 LCSP)."""
    requerida: Optional[bool] = None
    porcentaje: Optional[float] = None
    modalidad: Optional[str] = None  # aval, seguro de caución, efectivo o null
    observaciones: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'GarantiaDefinitivaDTO':
        if not isinstance(data, dict):
            return cls()
        try:
            porcentaje = float(data["porcentaje"]) if data.get("porcentaje") is not None else None
        except (ValueError, TypeError):
            porcentaje = None
        requerida = data.get("requerida")
        return cls(
            requerida=bool(requerida) if requerida is not None else None,
            porcentaje=porcentaje,
            modalidad=str(data["modalidad"]) if data.get("modalidad") else None,
            observaciones=str(data["observaciones"]) if data.get("observaciones") else None,
        )


@dataclass(frozen=True)
class PenalidadesDTO:
    """Penalidades y causas de resolución relevantes (arts. 192–194 LCSP)."""
    existen: Optional[bool] = None
    porcentaje_maximo: Optional[float] = None
    causas_resolucion: List[str] = field(default_factory=list)
    riesgo_evaluado: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'PenalidadesDTO':
        if not isinstance(data, dict):
            return cls()
        try:
            porcentaje = float(data["porcentaje_maximo"]) if data.get("porcentaje_maximo") is not None else None
        except (ValueError, TypeError):
            porcentaje = None
        causas = data.get("causas_resolucion")
        return cls(
            existen=bool(data["existen"]) if data.get("existen") is not None else None,
            porcentaje_maximo=porcentaje,
            causas_resolucion=[str(c) for c in causas] if isinstance(causas, list) else [],
            riesgo_evaluado=str(data["riesgo_evaluado"]).upper() if data.get("riesgo_evaluado") else None,
        )


@dataclass(frozen=True)
class ClausulasSocialesDTO:
    """Cláusulas sociales y su posible encaje competitivo para Incoop (art. 202 LCSP)."""
    existen: Optional[bool] = None
    requisitos: List[str] = field(default_factory=list)
    ventaja_incoop: Optional[bool] = None
    observaciones: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'ClausulasSocialesDTO':
        if not isinstance(data, dict):
            return cls()
        requisitos = data.get("requisitos")
        return cls(
            existen=bool(data["existen"]) if data.get("existen") is not None else None,
            requisitos=[str(r) for r in requisitos] if isinstance(requisitos, list) else [],
            ventaja_incoop=bool(data["ventaja_incoop"]) if data.get("ventaja_incoop") is not None else None,
            observaciones=str(data["observaciones"]) if data.get("observaciones") else None,
        )


@dataclass(frozen=True)
class DictamenIA:
    """Evaluación ejecutiva final del Analista IA"""
    recomendacion: str = "REVISAR_RIESGO"  # 'RECOMENDADA', 'REVISAR_RIESGO', 'DESCARTADA_POR_RIESGO'
    motivos: List[str] = field(default_factory=list)
    ajuste_score: int = 0
    resumen_ejecutivo: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'DictamenIA':
        if not isinstance(data, dict):
            return cls()

        rec = str(data.get("recomendacion", "REVISAR_RIESGO")).upper()
        if rec not in ['RECOMENDADA', 'REVISAR_RIESGO', 'DESCARTADA_POR_RIESGO']:
            rec = "REVISAR_RIESGO"

        try:
            ajuste = int(data.get("ajuste_score", 0))
        except (ValueError, TypeError):
            ajuste = 0

        motivos_list = data.get("motivos")
        if not isinstance(motivos_list, list):
            motivos_list = []

        return cls(
            recomendacion=rec,
            motivos=[str(m) for m in motivos_list],
            ajuste_score=ajuste,
            resumen_ejecutivo=str(data.get("resumen_ejecutivo", ""))
        )


# Versión del contrato del DTO de análisis semántico (Regla 4 - Versionado obligatorio).
# v1 -> esquema original.
# v2 -> incorpora el campo explícito `modo_degradado`, que sustituye a la detección
#       por heurística de cadena sobre `dictamen.resumen_ejecutivo`.
# v3 -> incorpora garantía definitiva, penalidades/resolución y cláusulas sociales.
ESQUEMA_DTO_VERSION = 3

# Bloques obligatorios que debe contener la respuesta del LLM para considerarse válida.
_BLOQUES_REQUERIDOS = ("subrogacion", "revision_precios", "criterios", "dictamen")


@dataclass(frozen=True)
class AnalisisSemanticoDTO:
    """Contenedor raíz del análisis semántico completo de una licitación"""
    subrogacion: SubrogacionDTO
    revision_precios: RevisionPreciosDTO
    criterios: CriteriosAdjudicacionDTO
    dictamen: DictamenIA
    garantia_definitiva: GarantiaDefinitivaDTO = field(default_factory=GarantiaDefinitivaDTO)
    penalidades: PenalidadesDTO = field(default_factory=PenalidadesDTO)
    clausulas_sociales: ClausulasSocialesDTO = field(default_factory=ClausulasSocialesDTO)
    version_esquema: int = ESQUEMA_DTO_VERSION
    # Marca explícita de que este análisis NO proviene de una lectura real del pliego.
    # Es la única fuente de verdad para el Recalibrador y para el Cockpit: nunca debe
    # inferirse del texto del resumen ejecutivo.
    modo_degradado: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def degradado(cls, motivo: str) -> 'AnalisisSemanticoDTO':
        """
        Construye un DTO vacío marcado explícitamente como degradado.
        Se usa cuando no ha sido posible obtener un análisis real del pliego.
        """
        return cls(
            subrogacion=SubrogacionDTO(),
            revision_precios=RevisionPreciosDTO(),
            criterios=CriteriosAdjudicacionDTO(),
            dictamen=DictamenIA(
                recomendacion="REVISAR_RIESGO",
                motivos=[motivo],
                resumen_ejecutivo=f"Análisis IA no disponible: {motivo}"
            ),
            version_esquema=ESQUEMA_DTO_VERSION,
            modo_degradado=True
        )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> 'AnalisisSemanticoDTO':
        if not isinstance(data, dict):
            data = {}

        return cls(
            subrogacion=SubrogacionDTO.from_dict(data.get("subrogacion")),
            revision_precios=RevisionPreciosDTO.from_dict(data.get("revision_precios")),
            criterios=CriteriosAdjudicacionDTO.from_dict(data.get("criterios")),
            dictamen=DictamenIA.from_dict(data.get("dictamen")),
            garantia_definitiva=GarantiaDefinitivaDTO.from_dict(data.get("garantia_definitiva")),
            penalidades=PenalidadesDTO.from_dict(data.get("penalidades")),
            clausulas_sociales=ClausulasSocialesDTO.from_dict(data.get("clausulas_sociales")),
            version_esquema=int(data.get("version_esquema", 1)),
            modo_degradado=bool(data.get("modo_degradado", False))
        )

    @classmethod
    def from_json(cls, json_str: str, estricto: bool = True) -> 'AnalisisSemanticoDTO':
        """
        Deserializa un DTO desde JSON.

        estricto=True  (defecto, respuestas del LLM): un JSON ilegible o con la forma
            equivocada eleva ValidationError, de modo que el orquestador pueda
            reintentar con otro proveedor en lugar de dar por bueno un análisis vacío.
        estricto=False (relecturas desde SQLite): degrada a un DTO marcado en vez de
            propagar la excepción, para que un registro histórico corrupto no impida
            leer el resto del expediente.
        """
        try:
            parsed = json.loads(json_str)
        except Exception as e:
            if estricto:
                raise ValidationError(f"La respuesta no es JSON válido: {e}") from e
            return cls.degradado("registro histórico ilegible en base de datos")

        if not isinstance(parsed, dict):
            if estricto:
                raise ValidationError(
                    f"Se esperaba un objeto JSON en la raíz, se recibió {type(parsed).__name__}"
                )
            return cls.degradado("registro histórico con estructura inesperada")

        # Validación de forma: JSON sintácticamente válido pero con el esquema
        # equivocado es el fallo más frecuente de los modelos sin salida estructurada.
        faltantes = [b for b in _BLOQUES_REQUERIDOS if not isinstance(parsed.get(b), dict)]
        if faltantes:
            if estricto:
                raise ValidationError(
                    f"Faltan o son inválidos los bloques obligatorios del esquema: {', '.join(faltantes)}"
                )
            return cls.degradado(f"registro histórico incompleto (faltan: {', '.join(faltantes)})")

        return cls.from_dict(parsed)


# =====================================================================
# ARQUITECTURA DE PROVEEDORES LLM (PATTERN PROVIDER - CAPA 5 PASO 3)
# =====================================================================

class LLMProvider(ABC):
    """Interfaz abstracta del contrato de servicio para conectores de IA."""
    @abstractmethod
    def consultar(self, prompt_sistema: str, prompt_usuario: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Envía una petición al proveedor LLM esperando respuesta en formato JSON.
        Devuelve un dict con: 'raw_response', 'modelo', 'prompt_tokens', 'completion_tokens', 'tiempo_seg'.
        Eleva ProviderError si falla la comunicación.
        """
        pass


# Esquema OpenAPI estricto para salidas estructuradas de Gemini API (Structured Outputs)
ESQUEMA_OPENAPI_ANALISIS_SEMANTICO = {
    "type": "OBJECT",
    "properties": {
        "subrogacion": {
            "type": "OBJECT",
            "properties": {
                "detectada": {"type": "BOOLEAN"},
                "num_trabajadores": {"type": "INTEGER", "nullable": True},
                "convenio_colectivo": {"type": "STRING", "nullable": True},
                "desglose_salarial_completo": {"type": "BOOLEAN"},
                "coste_estimado_anual": {"type": "NUMBER", "nullable": True},
                "riesgo_evaluado": {"type": "STRING", "enum": ["BAJO", "MEDIO", "ALTO", "CRITICO"]}
            },
            "required": ["detectada", "desglose_salarial_completo", "riesgo_evaluado"]
        },
        "revision_precios": {
            "type": "OBJECT",
            "properties": {
                "permitida": {"type": "BOOLEAN"},
                "formula_detectada": {"type": "STRING", "nullable": True},
                "art_103_aplica": {"type": "BOOLEAN"},
                "observaciones": {"type": "STRING", "nullable": True}
            },
            "required": ["permitida", "art_103_aplica"]
        },
        "criterios": {
            "type": "OBJECT",
            "properties": {
                "peso_precio_formulas": {"type": "INTEGER"},
                "peso_juicio_valor": {"type": "INTEGER"},
                "requiere_memoria_tecnica": {"type": "BOOLEAN"},
                "criterios_desglose": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "nombre": {"type": "STRING"},
                            "peso": {"type": "INTEGER"}
                        },
                        "required": ["nombre", "peso"]
                    }
                }
            },
            "required": ["peso_precio_formulas", "peso_juicio_valor", "requiere_memoria_tecnica", "criterios_desglose"]
        },
        "dictamen": {
            "type": "OBJECT",
            "properties": {
                "recomendacion": {"type": "STRING", "enum": ["RECOMENDADA", "REVISAR_RIESGO", "DESCARTADA_POR_RIESGO"]},
                "motivos": {"type": "ARRAY", "items": {"type": "STRING"}},
                "ajuste_score": {"type": "INTEGER"},
                "resumen_ejecutivo": {"type": "STRING"}
            },
            "required": ["recomendacion", "motivos", "ajuste_score", "resumen_ejecutivo"]
        },
        "version_esquema": {"type": "INTEGER"}
    },
    "required": ["subrogacion", "revision_precios", "criterios", "dictamen", "version_esquema"]
}


class OllamaProvider(LLMProvider):
    """Adaptador para el servidor local Ollama (Aceleración GPU NVIDIA RTX 5070 con gestión de VRAM)."""
    def __init__(self, host: str = "http://localhost:11434", modelo: str = "llama3.1:8b", temperature: float = 0.1, vram_options: Optional[Dict[str, Any]] = None, max_retries: int = 2, backoff_factor: float = 1.5):
        self.host = host.rstrip('/')
        self.modelo = modelo
        self.temperature = temperature
        self.vram_options = vram_options or {"num_ctx": 16384, "num_gpu": 99}
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def consultar(self, prompt_sistema: str, prompt_usuario: str, timeout: int = 60) -> Dict[str, Any]:
        url = f"{self.host}/api/chat"
        opts = {"temperature": self.temperature}
        if self.vram_options:
            opts.update(self.vram_options)

        payload = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": prompt_usuario}
            ],
            "options": opts,
            "format": "json",
            "stream": False
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        
        start_time = time.perf_counter()
        body = None
        last_err = None

        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = resp.status
                    if status != 200:
                        raise ProviderError(f"Ollama devolvió código HTTP {status}")
                    body = json.loads(resp.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(self.backoff_factor ** attempt)
                    continue
                raise ProviderError(f"Ollama devolvió HTTP {e.code}: {e.reason}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(self.backoff_factor ** attempt)
                    continue
                raise ProviderError(f"Error al conectar con Ollama ({self.host}): {e}") from e

        if not body:
            raise ProviderError(f"Error al conectar con Ollama ({self.host}): {last_err}")

        elapsed = time.perf_counter() - start_time
        message_content = body.get("message", {}).get("content", "")
        if not message_content:
            raise ProviderError("Respuesta vacía recibida desde Ollama")
            
        prompt_eval_count = body.get("prompt_eval_count", 0) or 0
        eval_count = body.get("eval_count", 0) or 0

        return {
            "raw_response": message_content,
            "modelo": f"ollama/{self.modelo}",
            "prompt_tokens": prompt_eval_count,
            "completion_tokens": eval_count,
            "tiempo_seg": elapsed
        }


class GeminiProvider(LLMProvider):
    """Adaptador para la API de Google Gemini (Proveedor Cloud con Structured Outputs OpenAPI)."""
    def __init__(self, api_key: Optional[str] = None, modelo: str = "gemini-3.1-flash-lite", temperature: float = 0.1, usar_schema: bool = True, max_retries: int = 3, backoff_factor: float = 2.0):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.modelo = modelo
        self.temperature = temperature
        self.usar_schema = usar_schema
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def consultar(self, prompt_sistema: str, prompt_usuario: str, timeout: int = 120) -> Dict[str, Any]:
        api_key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ProviderError("Variable de entorno GEMINI_API_KEY no configurada para GeminiProvider")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:generateContent?key={api_key}"
        
        gen_config = {
            "responseMimeType": "application/json",
            "temperature": self.temperature
        }
        if self.usar_schema:
            gen_config["responseSchema"] = ESQUEMA_OPENAPI_ANALISIS_SEMANTICO

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{prompt_sistema}\n\n{prompt_usuario}"}
                    ]
                }
            ],
            "generationConfig": gen_config
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        
        start_time = time.perf_counter()
        body = None
        last_err = None

        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = resp.status
                    if status != 200:
                        raise ProviderError(f"Gemini API devolvió código HTTP {status}")
                    body = json.loads(resp.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep((self.backoff_factor ** attempt) + (time.time() % 0.5))
                    continue
                raise ProviderError(f"Gemini API devolvió HTTP {e.code}: {e.reason}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep((self.backoff_factor ** attempt) + (time.time() % 0.5))
                    continue
                raise ProviderError(f"Error al conectar con Gemini API ({self.modelo}): {e}") from e

        if not body:
            raise ProviderError(f"Error al conectar con Gemini API ({self.modelo}): {last_err}")
            
        elapsed = time.perf_counter() - start_time
        
        try:
            candidates = body.get("candidates", [])
            text = candidates[0]["content"]["parts"][0]["text"]
        except (IndexError, KeyError, TypeError):
            raise ProviderError("Estructura de respuesta inesperada desde Gemini API")
            
        usage = body.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0) or 0
        completion_tokens = usage.get("candidatesTokenCount", 0) or 0

        return {
            "raw_response": text,
            "modelo": f"gemini/{self.modelo}",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tiempo_seg": elapsed
        }


# =====================================================================
# FACTORÍA DE PROVEEDORES LLM
# =====================================================================

def proveedor_llm_factory(config_path: str = "config/analista_config.yaml") -> LLMProvider:
    """
    Factoría estandarizada para instanciar el proveedor de LLM según la configuración activa.
    Se utiliza tanto en AnalistaIA como en AnalistaBoletinesIA (Centinela).
    """
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    pref = (config.get("proveedor_preferente") or "gemini").lower()
    gemini_cfg = config.get("gemini", {})
    ollama_cfg = config.get("ollama", {})

    if pref == "gemini":
        modelo = gemini_cfg.get("modelo_principal") or gemini_cfg.get("modelo", "gemini-3.1-flash-lite")
        return GeminiProvider(
            modelo=modelo,
            temperature=float(gemini_cfg.get("temperature", 0.1)),
            usar_schema=bool(gemini_cfg.get("usar_response_schema", True))
        )
    elif pref == "ollama" and ollama_cfg.get("activo", False):
        return OllamaProvider(
            host=ollama_cfg.get("host", "http://localhost:11434"),
            modelo=ollama_cfg.get("modelo", "llama3.1:8b"),
            temperature=float(ollama_cfg.get("temperature", 0.1)),
            vram_options=ollama_cfg.get("vram_options")
        )
    else:
        # Default fallback to Gemini principal
        modelo = gemini_cfg.get("modelo_principal") or gemini_cfg.get("modelo", "gemini-3.1-flash-lite")
        return GeminiProvider(
            modelo=modelo,
            temperature=float(gemini_cfg.get("temperature", 0.1)),
            usar_schema=bool(gemini_cfg.get("usar_response_schema", True))
        )


# =====================================================================
# MOTOR DE SEGMENTACIÓN INTELIGENTE (SMART LCSP CHUNKING - CAPA 5 PASO 4)
# =====================================================================

import re

class SmartLCSPChunker:
    """
    Motor de Segmentación Inteligente (Smart LCSP Chunking).
    Aísla las cláusulas contractuales clave (subrogación, revisión de precios, criterios de adjudicación)
    reduciendo drásticamente el volumen de caracteres enviado al LLM.
    """
    PATRONES_SUBROGACION_DEFECTO = [
        r"subrogaci[oó]n", r"subrogaci[oó]", r"personal a subrogar",
        r"convenio colectivo", r"art(?:[íi]culo|\.)?\s*130", r"plantilla", r"coste salarial"
    ]
    PATRONES_REVISION_PRECIOS_DEFECTO = [
        r"revisi[oó]n de precios", r"revisi[oó] de preus", r"art(?:[íi]culo|\.)?\s*103",
        r"f[oó]rmula de revisi[oó]n", r"ipc", r"desindexaci[oó]n"
    ]
    PATRONES_CRITERIOS_DEFECTO = [
        r"criterios? de adjudicaci[oó]n", r"criteris d'adjudicaci[oó]",
        r"juicio de valor", r"f[oó]rmula", r"oferta econ[oó]mica", r"memoria t[eé]cnica"
    ]

    def __init__(self, config_chunker: Optional[Dict[str, Any]] = None):
        cfg = config_chunker or {}
        self.ventana = int(cfg.get("tamano_ventana_caracteres", 1200))
        self.max_caracteres = int(cfg.get("max_caracteres_prompt", 15000))
        self.min_caracteres_sin_segmentar = int(cfg.get("min_caracteres_sin_segmentar", 3000))

        pat_sub = cfg.get("patrones_subrogacion") or self.PATRONES_SUBROGACION_DEFECTO
        pat_rev = cfg.get("patrones_revision_precios") or self.PATRONES_REVISION_PRECIOS_DEFECTO
        pat_crit = cfg.get("patrones_criterios") or self.PATRONES_CRITERIOS_DEFECTO

        self.regex_subrogacion = [re.compile(p, re.IGNORECASE) for p in pat_sub]
        self.regex_revision = [re.compile(p, re.IGNORECASE) for p in pat_rev]
        self.regex_criterios = [re.compile(p, re.IGNORECASE) for p in pat_crit]

    def _extraer_intervalos(self, texto: str, regex_list: List[re.Pattern]) -> List[Tuple[int, int]]:
        intervalos = []
        largo = len(texto)
        for rx in regex_list:
            for m in rx.finditer(texto):
                inicio = max(0, m.start() - self.ventana)
                fin = min(largo, m.end() + self.ventana)
                intervalos.append((inicio, fin))
        return intervalos

    @staticmethod
    def _fusionar_intervalos(intervalos: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if not intervalos:
            return []
        sorted_inter = sorted(intervalos, key=lambda x: x[0])
        fusionados = [sorted_inter[0]]
        for inicio, fin in sorted_inter[1:]:
            last_start, last_end = fusionados[-1]
            if inicio <= last_end:
                fusionados[-1] = (last_start, max(last_end, fin))
            else:
                fusionados.append((inicio, fin))
        return fusionados

    def segmentar_pliego(self, texto_pliego: str, expediente_id: str = "DESCONOCIDO") -> Dict[str, Any]:
        largo_original = len(texto_pliego) if texto_pliego else 0
        
        # Caso 1: Texto corto -> pasar íntegro
        if largo_original <= self.min_caracteres_sin_segmentar:
            return {
                "texto_ensamblado": texto_pliego or "",
                "estado_segmentacion": "TEXTO_CORTO_DIRECTO",
                "metricas": {
                    "caracteres_originales": largo_original,
                    "caracteres_segmentados": largo_original,
                    "ratio_compresion_porcentaje": 0.0,
                    "num_matches_totales": 0
                }
            }

        inter_sub = self._extraer_intervalos(texto_pliego, self.regex_subrogacion)
        inter_rev = self._extraer_intervalos(texto_pliego, self.regex_revision)
        inter_crit = self._extraer_intervalos(texto_pliego, self.regex_criterios)

        todos_intervalos = inter_sub + inter_rev + inter_crit
        fusionados = self._fusionar_intervalos(todos_intervalos)

        # Caso 2: Sin coincidencias regex -> Fallback truncado directo
        if not fusionados:
            texto_truncado = texto_pliego[:self.max_caracteres]
            largo_truncado = len(texto_truncado)
            compresion = round((1.0 - (largo_truncado / float(largo_original))) * 100, 2) if largo_original > 0 else 0.0
            return {
                "texto_ensamblado": f"[AVISO: Sin coincidencia explícita de cláusulas LCSP. Truncado directo de los primeros {self.max_caracteres} caracteres]\n\n" + texto_truncado,
                "estado_segmentacion": "SEGMENTACION_FALLBACK",
                "metricas": {
                    "caracteres_originales": largo_original,
                    "caracteres_segmentados": largo_truncado,
                    "ratio_compresion_porcentaje": compresion,
                    "num_matches_totales": 0
                }
            }

        # Caso 3: Extraer y ensamblar fragmentos fusionados
        bloques = []
        for inicio, fin in fusionados:
            bloques.append(texto_pliego[inicio:fin].strip())

        texto_ensamblado = "\n\n--- [FRAGMENTO DE CLÁUSULAS LCSP DETECTADAS] ---\n\n".join(bloques)
        if len(texto_ensamblado) > self.max_caracteres:
            texto_ensamblado = texto_ensamblado[:self.max_caracteres]

        largo_segmentado = len(texto_ensamblado)
        compresion = round((1.0 - (largo_segmentado / float(largo_original))) * 100, 2) if largo_original > 0 else 0.0

        return {
            "texto_ensamblado": texto_ensamblado,
            "estado_segmentacion": "SEGMENTACION_OK",
            "metricas": {
                "caracteres_originales": largo_original,
                "caracteres_segmentados": largo_segmentado,
                "ratio_compresion_porcentaje": compresion,
                "num_matches_totales": len(todos_intervalos)
            }
        }


PROMPT_SISTEMA_LCSP = """
Eres un experto analista jurídico-financiero de contratación pública en España (Ley 9/2017 LCSP).
Tu tarea es analizar el texto extraído de pliegos (PCA y PPT) y generar un análisis semántico estricto en JSON.

Debes devolver EXCLUSIVAMENTE un objeto JSON con este esquema exacto:
{
  "subrogacion": {
    "detectada": true/false,
    "num_trabajadores": integer o null,
    "convenio_colectivo": string o null,
    "desglose_salarial_completo": true/false,
    "coste_estimado_anual": float o null,
    "riesgo_evaluado": "BAJO" | "MEDIO" | "ALTO" | "CRITICO"
  },
  "revision_precios": {
    "permitida": true/false,
    "formula_detectada": string o null,
    "art_103_aplica": true/false,
    "observaciones": string o null
  },
  "criterios": {
    "peso_precio_formulas": integer (0-100),
    "peso_juicio_valor": integer (0-100),
    "requiere_memoria_tecnica": true/false,
    "criterios_desglose": [
      {"nombre": string, "peso": integer}
    ]
  },
  "dictamen": {
    "recomendacion": "RECOMENDADA" | "REVISAR_RIESGO" | "DESCARTADA_POR_RIESGO",
    "motivos": [string],
    "ajuste_score": integer (entre -30 y +15),
    "resumen_ejecutivo": string
  },
  "version_esquema": 1
}
Sin bloques markdown, únicamente el objeto JSON crudo.
"""

class GestorPromptsLCSP:
    """
    Gestor de plantillas y prompts especializados para la LCSP en Castellano y Catalán (Capa 5 Paso 5).
    Carga dinámicamente config/prompts_lcsp.yaml con fallback defensivo a plantillas integradas.
    """
    PROMPT_FALLBACK_SISTEMA = PROMPT_SISTEMA_LCSP

    def __init__(self, yaml_path: str = "config/prompts_lcsp.yaml"):
        self.yaml_path = yaml_path
        self.version = "1.0.0"
        self.sistema_base = ""
        self.ejemplos_few_shot = []
        self._cargar_prompts()

    def _cargar_prompts(self):
        if os.path.exists(self.yaml_path):
            try:
                with open(self.yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        self.version = str(data.get("version", "1.0.0"))
                        self.sistema_base = str(data.get("sistema_base", "")).strip()
                        self.ejemplos_few_shot = data.get("ejemplos_few_shot", [])
            except Exception as e:
                print(f"[!] Advertencia al cargar {self.yaml_path}: {e}. Usando plantilla fallback.")
        
        if not self.sistema_base:
            self.sistema_base = self.PROMPT_FALLBACK_SISTEMA.strip()

    def construir_prompt(
        self,
        texto_segmentado: str,
        idioma: str = "es",
        expediente_id: str = "DESCONOCIDO"
    ) -> Tuple[str, str, str]:
        """
        Construye la tupla (prompt_sistema, prompt_usuario, version_prompt).
        """
        prompt_sistema = self.sistema_base

        bloque_few_shot = ""
        if self.ejemplos_few_shot:
            ejemplos_txt = []
            for ex in self.ejemplos_few_shot[:2]:
                if isinstance(ex, dict):
                    in_txt = str(ex.get("entrada", "")).strip()
                    out_txt = str(ex.get("salida", "")).strip()
                    ejemplos_txt.append(f"EJEMPLO ENTRADA:\n{in_txt}\n\nEJEMPLO SALIDA JSON:\n{out_txt}")
            if ejemplos_txt:
                bloque_few_shot = "\n\nEJEMPLOS DE REFERENCIA (FEW-SHOT):\n" + "\n---\n".join(ejemplos_txt)

        if bloque_few_shot:
            prompt_sistema += bloque_few_shot

        prompt_usuario = (
            f"Análisis del pliego (Idioma detectado: {idioma.upper()}) para expediente '{expediente_id}':\n\n"
            f"{texto_segmentado}"
        )

        return prompt_sistema, prompt_usuario, self.version

    def healthcheck_prompts(self) -> Dict[str, Any]:
        existe = os.path.exists(self.yaml_path)
        return {
            "yaml_path": self.yaml_path,
            "existe": existe,
            "version": self.version,
            "num_ejemplos_few_shot": len(self.ejemplos_few_shot),
            "status": "OK" if existe else "DEGRADADO_FALLBACK"
        }

# =====================================================================
# ALGORITMO DE RECALIBRACIÓN DEL SCORING (CAPA 5 PASO 6)
# =====================================================================

class RecalibradorScoring:
    """
    Algoritmo de Recalibración del Scoring Comercial (Capa 2 + Capa 5).
    Combina la puntuación cuantitativa inicial del Filtro con el análisis cualitativo semántico.
    """
    AJUSTES_DEFECTO = {
        "subrogacion_critica": -25,
        "subrogacion_alta": -15,
        "subrogacion_baja_o_nula": 5,
        "revision_precios_ok": 10,
        "sin_revision_plurianual": -10,
        "precio_dominante": -10
    }

    def __init__(self, config_recalibracion: Optional[Dict[str, Any]] = None):
        cfg = config_recalibracion or {}
        self.umbral_recomendada = float(cfg.get("umbral_recomendada", 65.0))
        self.umbral_descartada = float(cfg.get("umbral_descartada", 40.0))
        self.ajustes = cfg.get("ajustes") or self.AJUSTES_DEFECTO

    def recalibrar(
        self,
        score_cuantitativo: float,
        dto: AnalisisSemanticoDTO,
        duracion_meses: Optional[int] = None,
        expediente_id: str = "DESCONOCIDO"
    ) -> Dict[str, Any]:
        """
        Recalibra el score cuantitativo inicial agregando penalizaciones/bonificaciones semánticas.
        Devuelve dict con score_original, ajuste_semantico, score_recalibrado, dictamen_final y motivos.
        """
        # Caso Degradado (Regla 5): Conservar score cuantitativo intacto.
        # Fuente de verdad: el campo explícito `modo_degradado` (esquema DTO v2+).
        # Para registros históricos v1, que carecen del campo, se mantiene como último
        # recurso la heurística de cadena original — acotada a esos registros para que
        # no pueda dispararse por accidente en análisis reales.
        es_degradado = bool(getattr(dto, "modo_degradado", False))
        if not es_degradado and int(getattr(dto, "version_esquema", 1)) < 2:
            resumen_legacy = dto.dictamen.resumen_ejecutivo or ""
            es_degradado = "degradado" in resumen_legacy.lower()

        if es_degradado:
            score_final = max(0.0, min(100.0, float(score_cuantitativo)))
            dictamen = "REVISAR_RIESGO" if score_final >= self.umbral_descartada else "DESCARTADA_POR_RIESGO"
            return {
                "score_original": float(score_cuantitativo),
                "ajuste_semantico": 0,
                "score_recalibrado": round(score_final, 2),
                "dictamen_final": dictamen,
                "veto_activado": False,
                "motivos_recalibracion": ["Modo degradado activo: Scoring cuantitativo preservado sin ajustes semánticos."]
            }

        ajuste = 0
        motivos = []
        veto_activado = False

        # 1. Evaluación de Subrogación (Art. 130 LCSP)
        riesgo_sub = (dto.subrogacion.riesgo_evaluado or "BAJO").upper()
        if riesgo_sub == "CRITICO":
            adj_val = int(self.ajustes.get("subrogacion_critica", -25))
            ajuste += adj_val
            veto_activado = True
            motivos.append(f"Subrogación de personal con riesgo CRÍTICO ({adj_val} pts, Veto comercial)")
        elif riesgo_sub == "ALTO":
            adj_val = int(self.ajustes.get("subrogacion_alta", -15))
            ajuste += adj_val
            motivos.append(f"Subrogación de personal con riesgo ALTO ({adj_val} pts)")
        elif riesgo_sub == "BAJO" and not dto.subrogacion.detectada:
            adj_val = int(self.ajustes.get("subrogacion_baja_o_nula", 5))
            ajuste += adj_val
            motivos.append(f"Sin obligación de subrogación de personal (+{adj_val} pts)")

        # 2. Evaluación de Revisión de Precios (Art. 103 LCSP)
        if dto.revision_precios.permitida and dto.revision_precios.formula_detectada:
            adj_val = int(self.ajustes.get("revision_precios_ok", 10))
            ajuste += adj_val
            motivos.append(f"Fórmula explícita de revisión de precios detectada (+{adj_val} pts)")
        elif not dto.revision_precios.permitida and (duracion_meses or 0) > 24:
            adj_val = int(self.ajustes.get("sin_revision_plurianual", -10))
            ajuste += adj_val
            motivos.append(f"Sin revisión de precios en contrato plurianual de {duracion_meses} meses ({adj_val} pts)")

        # 3. Evaluación de Criterios de Adjudicación (Art. 145 LCSP).
        # El README define que el precio por encima del 60 % inicia una guerra de
        # precios desfavorable para Incoop. No se penaliza automáticamente el juicio
        # de valor: puede ser precisamente una ventaja competitiva de la cooperativa.
        peso_pf = dto.criterios.peso_precio_formulas
        if peso_pf > 60:
            adj_val = int(self.ajustes.get("precio_dominante", -10))
            ajuste += adj_val
            motivos.append(f"Predominio de precio/fórmulas ({peso_pf}% > 60%) ({adj_val} pts)")

        # El LLM puede explicar una recomendación, pero no alterar el score. Aplicarlo
        # junto a estas reglas deterministas provocaba doble penalización/bonificación.
        if dto.dictamen.ajuste_score != 0:
            motivos.append(
                f"Ajuste propuesto por IA ({dto.dictamen.ajuste_score:+d} pts) no aplicado: "
                "el scoring comercial es determinista."
            )

        # Cálculo de Score Recalibrado Final acotado en [0, 100]
        score_calc = float(score_cuantitativo) + ajuste
        score_recalibrado = max(0.0, min(100.0, score_calc))

        # Asignación del Dictamen Final
        if veto_activado or score_recalibrado < self.umbral_descartada or dto.dictamen.recomendacion == "DESCARTADA_POR_RIESGO":
            dictamen_final = "DESCARTADA_POR_RIESGO"
        elif score_recalibrado >= self.umbral_recomendada and dto.dictamen.recomendacion == "RECOMENDADA":
            dictamen_final = "RECOMENDADA"
        else:
            dictamen_final = "REVISAR_RIESGO"

        return {
            "score_original": float(score_cuantitativo),
            "ajuste_semantico": ajuste,
            "score_recalibrado": round(score_recalibrado, 2),
            "dictamen_final": dictamen_final,
            "veto_activado": veto_activado,
            "motivos_recalibracion": motivos
        }

    def healthcheck_recalibrador(self) -> Dict[str, Any]:
        return {
            "umbral_recomendada": self.umbral_recomendada,
            "umbral_descartada": self.umbral_descartada,
            "status": "OK"
        }


# =====================================================================
# CLASE PRINCIPAL ANALISTA IA - ORQUESTACIÓN Y FALLBACK RESILIENTE
# =====================================================================

class AnalistaIA:
    """Orquestador del análisis semántico con IA para la Capa 5."""
    def __init__(self, config_path: str = "config/analista_config.yaml"):
        self.config_path = config_path
        self.config = self._cargar_configuracion()
        self.providers: Dict[str, LLMProvider] = {}
        self._inicializar_proveedores()
        self.chunker = SmartLCSPChunker(self.config.get("chunker", {}))
        self.gestor_prompts = GestorPromptsLCSP(self.config.get("prompts_path", "config/prompts_lcsp.yaml"))
        self.recalibrador = RecalibradorScoring(self.config.get("recalibracion", {}))

    def _cargar_configuracion(self) -> Dict[str, Any]:
        config_defecto = {
            "proveedor_preferente": "gemini",
            "permitir_fallback": True,
            "timeout_segundos": 120,
            "prompts_path": "config/prompts_lcsp.yaml",
            "ollama": {"activo": False, "host": "http://localhost:11434", "modelo": "llama3.1:8b", "temperature": 0.1},
            "gemini": {"modelo_principal": "gemini-3.1-flash-lite", "modelo_respaldo": "gemini-3.6-flash", "temperature": 0.1},
            "chunker": {
                "tamano_ventana_caracteres": 1200,
                "max_caracteres_prompt": 15000,
                "min_caracteres_sin_segmentar": 3000
            },
            "recalibracion": {
                "umbral_recomendada": 65.0,
                "umbral_descartada": 40.0
            }
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                    if isinstance(cfg, dict):
                        config_defecto.update(cfg)
            except Exception as e:
                print(f"[!] Advertencia al cargar {self.config_path}: {e}. Usando valores por defecto.")
        return config_defecto

    def _inicializar_proveedores(self):
        ollama_cfg = self.config.get("ollama", {})
        self.providers["ollama"] = OllamaProvider(
            host=ollama_cfg.get("host", "http://localhost:11434"),
            modelo=ollama_cfg.get("modelo", "llama3.1:8b"),
            temperature=float(ollama_cfg.get("temperature", 0.1)),
            vram_options=ollama_cfg.get("vram_options")
        )
        gemini_cfg = self.config.get("gemini", {})
        modelo_gemini = gemini_cfg.get("modelo_principal") or gemini_cfg.get("modelo", "gemini-3.1-flash-lite")
        self.providers["gemini"] = GeminiProvider(
            modelo=modelo_gemini,
            temperature=float(gemini_cfg.get("temperature", 0.1)),
            usar_schema=bool(gemini_cfg.get("usar_response_schema", True))
        )

    def registrar_log_jsonl(self, event_type: str, data: Dict[str, Any], log_dir: str = "data") -> None:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "pipeline.jsonl")
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": event_type,
            **data
        }
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def recalibrar_score(
        self,
        score_cuantitativo: float,
        analisis_dto: AnalisisSemanticoDTO,
        duracion_meses: Optional[int] = None,
        expediente_id: str = "DESCONOCIDO"
    ) -> Dict[str, Any]:
        """
        Recalibra el score cuantitativo combinándolo con el análisis semántico y registra el evento JSONL.
        """
        res_rec = self.recalibrador.recalibrar(
            score_cuantitativo=score_cuantitativo,
            dto=analisis_dto,
            duracion_meses=duracion_meses,
            expediente_id=expediente_id
        )

        self.registrar_log_jsonl("SCORE_RECALIBRATED", {
            "expediente_id": expediente_id,
            **res_rec
        })

        return res_rec

    def analizar_pliego(
        self,
        texto_pliego: str,
        expediente_id: str = "DESCONOCIDO",
        idioma: str = "es",
        proveedor_override: Optional[str] = None
    ) -> Tuple[AnalisisSemanticoDTO, Dict[str, Any]]:
        """
        Ejecuta la segmentación inteligente, construcción de prompt bilingüe y consulta semántica al modelo de IA.
        Devuelve el AnalisisSemanticoDTO y el diccionario de metadatos asociados.
        """
        # 1. Segmentación Inteligente (Smart LCSP Chunking)
        seg_res = self.chunker.segmentar_pliego(texto_pliego, expediente_id=expediente_id)
        texto_procesado = seg_res["texto_ensamblado"]
        metricas_chunker = seg_res["metricas"]

        self.registrar_log_jsonl("SMART_CHUNKING_COMPLETED", {
            "expediente_id": expediente_id,
            "estado_segmentacion": seg_res["estado_segmentacion"],
            **metricas_chunker
        })

        # 2. Construcción de Prompts Especializados LCSP (Capa 5 Paso 5)
        prompt_sistema, prompt_usuario, v_prompt = self.gestor_prompts.construir_prompt(
            texto_segmentado=texto_procesado,
            idioma=idioma,
            expediente_id=expediente_id
        )

        self.registrar_log_jsonl("PROMPT_GENERATED", {
            "expediente_id": expediente_id,
            "idioma": idioma,
            "version_prompt": v_prompt,
            "chars_prompt_sistema": len(prompt_sistema),
            "chars_prompt_usuario": len(prompt_usuario)
        })

        pref = (proveedor_override or self.config.get("proveedor_preferente", "ollama")).lower()
        permitir_fallback = bool(self.config.get("permitir_fallback", True))
        timeout = int(self.config.get("timeout_segundos", 60))

        orden_proveedores = [pref]
        if permitir_fallback:
            alt = "gemini" if pref == "ollama" else "ollama"
            orden_proveedores.append(alt)

        self.registrar_log_jsonl("LLM_REQUEST_START", {
            "expediente_id": expediente_id,
            "proveedor_preferente": pref,
            "permitir_fallback": permitir_fallback
        })

        ultimo_error = None
        for i, prov_name in enumerate(orden_proveedores):
            provider = self.providers.get(prov_name)
            if not provider:
                continue

            try:
                if i > 0:
                    self.registrar_log_jsonl("LLM_FALLBACK_TRIGGERED", {
                        "expediente_id": expediente_id,
                        "original_provider": orden_proveedores[0],
                        "target_provider": prov_name,
                        "reason": str(ultimo_error)
                    })

                res = provider.consultar(prompt_sistema, prompt_usuario, timeout=timeout)
                # Parseo ESTRICTO: una respuesta con JSON válido pero esquema incorrecto
                # eleva ValidationError y se trata como fallo del proveedor, activando el
                # siguiente de la cadena. Nunca se da por bueno un análisis vacío.
                dto = AnalisisSemanticoDTO.from_json(res["raw_response"], estricto=True)

                metadatos = {
                    "modelo_llm": res["modelo"],
                    "prompt_tokens": res["prompt_tokens"],
                    "completion_tokens": res["completion_tokens"],
                    "tiempo_procesamiento_seg": round(res["tiempo_seg"], 3),
                    "estado_analisis": "COMPLETADO",
                    "error_detalle": None,
                    "metricas_segmentacion": metricas_chunker,
                    "version_prompt": v_prompt
                }

                self.registrar_log_jsonl("LLM_REQUEST_SUCCESS", {
                    "expediente_id": expediente_id,
                    "provider": prov_name,
                    "modelo": res["modelo"],
                    "duration_ms": int(res["tiempo_seg"] * 1000),
                    "prompt_tokens": res["prompt_tokens"],
                    "completion_tokens": res["completion_tokens"]
                })

                return dto, metadatos

            except Exception as e:
                ultimo_error = e
                # Se distingue el fallo de contrato (respuesta inservible) del fallo de
                # transporte (red/servicio), porque exigen acciones operativas distintas.
                tipo_fallo = "ESQUEMA_INVALIDO" if isinstance(e, ValidationError) else "TRANSPORTE"
                self.registrar_log_jsonl("LLM_REQUEST_FAILED", {
                    "expediente_id": expediente_id,
                    "provider": prov_name,
                    "tipo_fallo": tipo_fallo,
                    "error": str(e)
                })

        # Si fallan todos los proveedores -> Modo Degradado
        err_msg = f"Fallo en proveedores LLM ({orden_proveedores}): {ultimo_error}"
        dto_degradado = AnalisisSemanticoDTO.degradado(
            "indisponibilidad de los proveedores LLM (fallo de red, servicio o esquema de respuesta)"
        )
        metadatos_degradado = {
            "modelo_llm": "ninguno/degradado",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tiempo_procesamiento_seg": 0.0,
            "estado_analisis": "DEGRADADO",
            "error_detalle": err_msg,
            "metricas_segmentacion": metricas_chunker,
            "version_prompt": v_prompt
        }

        self.registrar_log_jsonl("LLM_REQUEST_DEGRADED", {
            "expediente_id": expediente_id,
            "error_detail": err_msg
        })

        return dto_degradado, metadatos_degradado

    def procesar_expediente(
        self,
        expediente_id: str,
        texto_pliego: str,
        score_cuantitativo: float,
        duracion_meses: Optional[int] = None,
        idioma: str = "es",
        proveedor_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Orquesta el ciclo semántico completo para un expediente (Capa 5 Paso 7):
        1. Emisión evento `doc_analysis_started`
        2. Análisis del pliego (`analizar_pliego`: Smart Chunking + Prompting + Inferencia LLM Fallback)
        3. Recalibración del scoring (`recalibrar_score`)
        4. Emisión evento final `doc_analysis_completed` o `doc_analysis_degraded` (modo ANALISIS_DIFERIDO)
        5. Retorno del objeto resultado consolidado.
        """
        largo_pliego = len(texto_pliego) if texto_pliego else 0
        self.registrar_log_jsonl("doc_analysis_started", {
            "expediente_id": expediente_id,
            "tamanio_pliego_bytes": largo_pliego,
            "idioma": idioma,
            "score_cuantitativo_inicial": score_cuantitativo
        })

        dto, metadatos = self.analizar_pliego(
            texto_pliego=texto_pliego,
            expediente_id=expediente_id,
            idioma=idioma,
            proveedor_override=proveedor_override
        )

        res_recalibracion = self.recalibrar_score(
            score_cuantitativo=score_cuantitativo,
            analisis_dto=dto,
            duracion_meses=duracion_meses,
            expediente_id=expediente_id
        )

        es_degradado = (metadatos.get("estado_analisis") == "DEGRADADO")
        estado_operativo = "ANALISIS_DIFERIDO" if es_degradado else "COMPLETADO"

        event_name = "doc_analysis_degraded" if es_degradado else "doc_analysis_completed"
        self.registrar_log_jsonl(event_name, {
            "expediente_id": expediente_id,
            "estado_operativo": estado_operativo,
            "modelo_llm": metadatos.get("modelo_llm"),
            "score_original": res_recalibracion["score_original"],
            "score_recalibrado": res_recalibracion["score_recalibrado"],
            "dictamen_final": res_recalibracion["dictamen_final"],
            "duracion_total_seg": metadatos.get("tiempo_procesamiento_seg", 0.0)
        })

        return {
            "expediente_id": expediente_id,
            "estado_operativo": estado_operativo,
            "dto": dto,
            "metadatos": metadatos,
            "recalibracion": res_recalibracion
        }

    def healthcheck_analista(self) -> Dict[str, Any]:
        """
        Comprueba el estado operativo de los conectores Ollama, Gemini, Prompts, Recalibrador y Logger (Regla 6).
        """
        status_ollama = "UNAVAILABLE"
        status_gemini = "UNAVAILABLE"
        
        # Test Ollama
        try:
            host_ollama = self.providers["ollama"].host if "ollama" in self.providers else "http://localhost:11434"
            req = urllib.request.Request(f"{host_ollama}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    status_ollama = "OK"
        except Exception:
            pass

        # Test Gemini API Key
        if os.getenv("GEMINI_API_KEY"):
            status_gemini = "CONFIGURED"

        overall = "OK"
        if status_ollama != "OK" and status_gemini != "CONFIGURED":
            overall = "CRITICAL"
        elif status_ollama != "OK" or status_gemini != "CONFIGURED":
            overall = "DEGRADADO"

        hc_prompts = self.gestor_prompts.healthcheck_prompts()
        hc_recalibrador = self.recalibrador.healthcheck_recalibrador()

        # Check logger directory
        log_dir = "data"
        can_write_log = os.access(log_dir if os.path.exists(log_dir) else ".", os.W_OK)

        return {
            "status": overall,
            "ollama_status": status_ollama,
            "gemini_status": status_gemini,
            "prompts_status": hc_prompts,
            "recalibrador_status": hc_recalibrador,
            "logger_writer_status": "OK" if can_write_log else "UNAVAILABLE",
            "proveedor_preferente": self.config.get("proveedor_preferente")
        }

    def generar_reporte_csv(self, memoria: Any, csv_path: str = "data/reports/analisis_semantico_summary.csv") -> str:
        """
        Genera/actualiza un informe comercial CSV consolidado en data/reports/analisis_semantico_summary.csv.
        Codificación UTF-8-sig (con BOM para Excel) y delimitador ';'.
        """
        import csv
        import sqlite3
        reports_dir = os.path.dirname(csv_path)
        if reports_dir and not os.path.exists(reports_dir):
            os.makedirs(reports_dir, exist_ok=True)

        sql = """
        SELECT 
            e.id AS expediente_id,
            e.titulo,
            l.pbl AS presupuesto_base,
            l.score_total AS score_cuantitativo,
            a.dictamen_ajuste_score AS ajuste_semantico,
            (COALESCE(l.score_total, 50.0) + COALESCE(a.dictamen_ajuste_score, 0)) AS score_recalibrado,
            a.dictamen_recomendacion AS dictamen_final,
            a.subrogacion_detectada,
            a.subrogacion_num_trabajadores AS num_trabajadores,
            a.subrogacion_riesgo AS riesgo_subrogacion,
            a.revision_precios_permitida,
            a.revision_precios_formula,
            a.modelo_llm,
            a.tiempo_procesamiento_seg,
            a.estado_analisis,
            a.created_at AS fecha_analisis
        FROM analisis_semantico a
        JOIN expedientes e ON e.id = a.expediente_id
        LEFT JOIN lotes l ON l.expediente_id = e.id
        ORDER BY score_recalibrado DESC;
        """
        with memoria.conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()

        fieldnames = [
            "expediente_id", "titulo", "presupuesto_base", "score_cuantitativo",
            "ajuste_semantico", "score_recalibrado", "dictamen_final",
            "subrogacion_detectada", "num_trabajadores", "riesgo_subrogacion",
            "revision_precios_permitida", "revision_precios_formula",
            "modelo_llm", "tiempo_procesamiento_seg", "estado_analisis", "fecha_analisis"
        ]

        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(fieldnames)
            for r in rows:
                score_rec = max(0.0, min(100.0, float(r["score_recalibrado"] or 50.0)))
                writer.writerow([
                    r["expediente_id"],
                    r["titulo"],
                    f"{float(r['presupuesto_base'] or 0.0):.2f}",
                    f"{float(r['score_cuantitativo'] or 0.0):.2f}",
                    r["ajuste_semantico"] or 0,
                    f"{score_rec:.2f}",
                    r["dictamen_final"],
                    "SI" if r["subrogacion_detectada"] else "NO",
                    r["num_trabajadores"] if r["num_trabajadores"] is not None else "N/D",
                    r["riesgo_subrogacion"],
                    "SI" if r["revision_precios_permitida"] else "NO",
                    r["revision_precios_formula"] or "N/D",
                    r["modelo_llm"],
                    f"{float(r['tiempo_procesamiento_seg'] or 0.0):.2f}",
                    r["estado_analisis"],
                    r["fecha_analisis"]
                ])

        return csv_path

    def procesar_lote_pendientes(self, memoria: Any, limite: int = 50, run_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Procesa de forma resiliente por lotes las licitaciones pendientes en SQLite v4 (Capa 5 Paso 8).
        """
        start_time = time.perf_counter()
        pendientes = memoria.listar_expedientes_pendientes_analisis(limit=limite)
        total_pendientes = len(pendientes)
        
        exitos = 0
        degradados = 0
        
        for item in pendientes:
            exp_id = item["id"]
            try:
                datos_exp = memoria.obtener_datos_completos_expediente(exp_id)
                res = self.procesar_expediente(
                    expediente_id=exp_id,
                    texto_pliego=datos_exp["texto_pliego"],
                    score_cuantitativo=datos_exp["score_cuantitativo"],
                    idioma=datos_exp["idioma"]
                )
                
                # Persistir en BD SQLite v4
                memoria.guardar_analisis_semantico(
                    expediente_id=exp_id,
                    dto=res["dto"],
                    metadatos=res["metadatos"],
                    run_id=run_id
                )
                
                if res["estado_operativo"] == "COMPLETADO":
                    exitos += 1
                else:
                    degradados += 1
            except Exception as e:
                degradados += 1
                print(f"[!] Error al procesar licitación {exp_id} en lote: {e}")

        # Generar reporte CSV comercial
        csv_path = "data/reports/analisis_semantico_summary.csv"
        try:
            csv_path = self.generar_reporte_csv(memoria=memoria, csv_path=csv_path)
        except Exception as e_csv:
            print(f"[!] Advertencia: no se pudo generar el reporte CSV: {e_csv}")

        elapsed = time.perf_counter() - start_time
        
        self.registrar_log_jsonl("SEMANTIC_BATCH_COMPLETED", {
            "total_pendientes": total_pendientes,
            "procesados_exito": exitos,
            "procesados_degradados": degradados,
            "tiempo_total_lote_seg": round(elapsed, 2),
            "reporte_csv_path": csv_path
        })

        return {
            "total_pendientes": total_pendientes,
            "procesados_exito": exitos,
            "procesados_degradados": degradados,
            "tiempo_total_lote_seg": round(elapsed, 2),
            "reporte_csv_path": csv_path
        }

    def inspeccionar_expediente(self, memoria: Any, expediente_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera y muestra por terminal un informe visual estructurado con el dictamen cualitativo (Capa 5 Paso 9).
        """
        raw = memoria.obtener_analisis_semantico_raw(expediente_id)
        if not raw:
            print(f"[!] No se encontró ningún análisis semántico registrado para el expediente '{expediente_id}'.")
            return None

        print("\n" + "=" * 80)
        print(f" INFORME DE ANÁLISIS SEMÁNTICO - LICITACIÓN: {expediente_id} ".center(80, "="))
        print("=" * 80)
        print(f" Status Análisis   : {raw.get('estado_analisis')}")
        print(f" Dictamen Final    : {raw.get('dictamen_recomendacion')}")
        print(f" Ajuste de Score   : {raw.get('dictamen_ajuste_score')} pts")
        print(f" Modelo LLM Usado  : {raw.get('modelo_llm')}")
        print(f" Tiempo Inferencia : {raw.get('tiempo_procesamiento_seg', 0.0):.2f} s")
        print(f" Fecha de Análisis : {raw.get('created_at')}")
        print("-" * 80)
        print(" [SUBROGACIÓN DE PERSONAL] (Art. 130 LCSP)")
        sub_det = "SÍ (ALERTA)" if raw.get("subrogacion_detectada") else "NO"
        print(f"   - Obligación Detectada : {sub_det}")
        print(f"   - Riesgo Evaluado      : {raw.get('subrogacion_riesgo')}")
        print(f"   - Personal Afectado    : {raw.get('subrogacion_num_trabajadores') or 'No especificado'}")
        print(f"   - Convenio Colectivo   : {raw.get('subrogacion_convenio') or 'No especificado'}")
        print(f"   - Coste Anual Est.     : {raw.get('subrogacion_coste_anual') or 'No especificado'}")
        print("-" * 80)
        print(" [REVISIÓN DE PRECIOS] (Art. 103 LCSP)")
        rev_perm = "SÍ" if raw.get("revision_precios_permitida") else "NO"
        print(f"   - Revisión Permitida   : {rev_perm}")
        print(f"   - Fórmula Detectada    : {raw.get('revision_precios_formula') or 'Ninguna'}")
        print(f"   - Observaciones        : {raw.get('revision_precios_obs') or 'Sin observaciones'}")
        print("-" * 80)
        print(" [CRITERIOS DE ADJUDICACIÓN] (Art. 145 LCSP)")
        print(f"   - Peso Fórmulas        : {raw.get('criterios_peso_formulas')}%")
        print(f"   - Peso Juicio de Valor : {raw.get('criterios_peso_juicio_valor')}%")
        print(f"   - Memoria Técnica      : {'SÍ' if raw.get('criterios_requiere_memoria') else 'NO'}")
        print("-" * 80)
        print(" [RESUMEN EJECUTIVO Y MOTIVOS]")
        print(f"   Resumen : {raw.get('dictamen_resumen')}")
        try:
            motivos = json.loads(raw.get("dictamen_motivos_json") or "[]")
            for m in motivos:
                print(f"   - Motivo : {m}")
        except Exception:
            pass
        print("=" * 80 + "\n")
        return raw

    def reanalizar_expediente(self, memoria: Any, expediente_id: str, run_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fuerza la re-evaluación semántica de un expediente individual en SQLite v4 (Capa 5 Paso 9).
        """
        print(f"[~] Re-analizando expediente '{expediente_id}'...")
        datos_exp = memoria.obtener_datos_completos_expediente(expediente_id)
        if not datos_exp["texto_pliego"]:
            print(f"[!] Advertencia: No se encontró texto de pliegos extraído para {expediente_id}.")

        res = self.procesar_expediente(
            expediente_id=expediente_id,
            texto_pliego=datos_exp["texto_pliego"],
            score_cuantitativo=datos_exp["score_cuantitativo"],
            idioma=datos_exp["idioma"]
        )

        memoria.guardar_analisis_semantico(
            expediente_id=expediente_id,
            dto=res["dto"],
            metadatos=res["metadatos"],
            run_id=run_id
        )

        print(f"[+] Re-análisis completado para {expediente_id}. Estado: {res['estado_operativo']} | Dictamen: {res['recalibracion']['dictamen_final']}.")
        return res


def main_cli():
    import sys
    import argparse
    from src.memoria import Memoria

    parser = argparse.ArgumentParser(description="CLI del Analista IA - Capa 5 (Incoop Licitaciones)")
    parser.add_argument("--healthcheck", action="store_true", help="Ejecuta autodiagnóstico de conectores LLM y componentes.")
    parser.add_argument("--inspeccionar", type=str, metavar="EXPEDIENTE_ID", help="Inspecciona el dictamen semántico cualitativo de un expediente.")
    parser.add_argument("--reanalizar", type=str, metavar="EXPEDIENTE_ID", help="Fuerza el re-análisis semántico de un expediente específico en BD.")
    parser.add_argument("--procesar-lote", action="store_true", help="Procesa por lotes las licitaciones pendientes en BD.")
    parser.add_argument("--limite", type=int, default=50, help="Límite máximo de expedientes a procesar en lote (por defecto 50).")
    parser.add_argument("--reporte-csv", action="store_true", help="Genera/actualiza el reporte comercial CSV.")
    
    args = parser.parse_args()

    analista = AnalistaIA()
    memoria = Memoria()

    if args.healthcheck:
        hc = analista.healthcheck_analista()
        print(json.dumps(hc, indent=2, ensure_ascii=False))
        sys.exit(0 if hc["status"] in ["OK", "DEGRADADO"] else 1)

    if args.inspeccionar:
        analista.inspeccionar_expediente(memoria, args.inspeccionar)
        sys.exit(0)

    if args.reanalizar:
        analista.reanalizar_expediente(memoria, args.reanalizar)
        sys.exit(0)

    if args.procesar_lote:
        res = analista.procesar_lote_pendientes(memoria, limite=args.limite)
        print(f"[+] Lote procesado: {res}")
        sys.exit(0)

    if args.reporte_csv:
        csv_path = analista.generar_reporte_csv(memoria)
        print(f"[+] Reporte CSV generado en: {csv_path}")
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main_cli()
