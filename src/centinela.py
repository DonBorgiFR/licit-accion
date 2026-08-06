"""
src/centinela.py — El Centinela de Boletines (Capa 6 - Fase Temprana)
Ecosistema Automático de Licitaciones (bfr_incoop)

Módulo responsable del rastreo, análisis semántico y scoring de publicaciones oficiales
previas (DOGC y BOPB) sobre presupuestos, subvenciones, convenios y consultas preliminares.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import csv
import os
from typing import List, Optional, Dict, Any, Tuple

from src import ruta_proyecto


# ==============================================================================
# Excepciones Tipadas de Capa 6 (Paso 1)
# ==============================================================================

class CentinelaError(Exception):
    """Excepción base para el módulo Centinela."""
    pass

class BoletinDTOValidationError(CentinelaError):
    """Error emitido cuando la validación de campos requeridos de un DTO de boletín falla."""
    pass

class BoletinDeserializationError(CentinelaError):
    """Error emitido cuando falla la deserialización desde JSON o Diccionario."""
    pass

# ==============================================================================
# Estados Válidos y Constantes de Negocio (Reglas 2 y 4)
# ==============================================================================

ESTADOS_BOLETIN_VALIDOS = {
    "NUEVA_FASE_TEMPRANA",
    "EN_ESTUDIO_PROACTIVO",
    "CONVERTIDA_A_LICITACION",
    "DESCARTADA_TEMPRANA",
    "ANALISIS_DIFERIDO_BOLETIN"
}

CATEGORIAS_FASE_TEMPRANA_VALIDAS = {
    "PRESUPUESTO",
    "SUBVENCION",
    "CONVENIO",
    "CONSULTA_PRELIMINAR",
    "OTROS"
}

NIVELES_INTERES_VALIDOS = {
    "ALTO",
    "MEDIO",
    "BAJO",
    "NULO",
    # Valor exclusivo del Modo Degradado: la IA no pudo emitir un veredicto. No es
    # sinónimo de "NULO". Existe para que sea imposible leer un análisis fallido
    # como un desinterés real, aunque quien lo lea ignore `modo_degradado`.
    "DESCONOCIDO"
}

# ==============================================================================
# Estructuras DTO Defensivas (Paso 1)
# ==============================================================================

@dataclass
class DictamenCentinelaDTO:
    """
    DTO cualitativo que representa el dictamen del Analista IA sobre un anuncio de boletín.
    """
    es_oportunidad_temprana: bool
    nivel_interes: str  # 'ALTO', 'MEDIO', 'BAJO', 'NULO', 'DESCONOCIDO'
    categoria_fase_temprana: str  # 'PRESUPUESTO', 'SUBVENCION', 'CONVENIO', 'CONSULTA_PRELIMINAR', 'OTROS'
    resumen_ejecutivo: str
    acciones_recomendadas: List[str] = field(default_factory=list)
    estimacion_meses_hasta_licitacion: Optional[int] = None
    # Esquema v2: el estado degradado se afirma con un campo estructurado, nunca
    # inspeccionando el texto del resumen (Convención C3).
    modo_degradado: bool = False
    version_esquema: int = 2

    # Campos sin los cuales un dictamen no puede proceder de un análisis real. Se
    # exigen en modo estricto para que un `{}` deje de deserializar como veredicto
    # válido rellenado con valores por defecto.
    CAMPOS_OBLIGATORIOS = (
        "es_oportunidad_temprana",
        "nivel_interes",
        "categoria_fase_temprana",
        "resumen_ejecutivo",
    )

    def __post_init__(self):
        if not isinstance(self.es_oportunidad_temprana, bool):
            raise BoletinDTOValidationError("`es_oportunidad_temprana` debe ser un valor booleano.")
        
        self.nivel_interes = str(self.nivel_interes).upper()
        if self.nivel_interes not in NIVELES_INTERES_VALIDOS:
            raise BoletinDTOValidationError(
                f"`nivel_interes` inválido: '{self.nivel_interes}'. Permitidos: {NIVELES_INTERES_VALIDOS}"
            )
            
        self.categoria_fase_temprana = str(self.categoria_fase_temprana).upper()
        if self.categoria_fase_temprana not in CATEGORIAS_FASE_TEMPRANA_VALIDAS:
            raise BoletinDTOValidationError(
                f"`categoria_fase_temprana` inválida: '{self.categoria_fase_temprana}'. Permitidos: {CATEGORIAS_FASE_TEMPRANA_VALIDAS}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], estricto: bool = False) -> "DictamenCentinelaDTO":
        if not isinstance(data, dict):
            raise BoletinDeserializationError("Los datos de entrada deben ser un diccionario Python.")

        # En modo estricto se valida la FORMA del esquema, no sólo que sea un dict.
        # Sin esto, un `{}` deserializaba como dictamen válido con nivel_interes="NULO"
        # y el evaluador lo penalizaba con -30 pts: un análisis fallido se convertía
        # en un descarte comercial indistinguible de un veredicto real (Convención C2).
        if estricto:
            ausentes = [
                campo for campo in cls.CAMPOS_OBLIGATORIOS
                if campo not in data
                or data[campo] is None
                or (isinstance(data[campo], str) and not data[campo].strip())
            ]
            if ausentes:
                raise BoletinDeserializationError(
                    f"Dictamen incompleto: faltan o vienen vacíos {ausentes}. "
                    "Un dictamen sin estos campos no procede de un análisis real."
                )

        try:
            return cls(
                es_oportunidad_temprana=bool(data.get("es_oportunidad_temprana", False)),
                nivel_interes=str(data.get("nivel_interes", "NULO")).upper(),
                categoria_fase_temprana=str(data.get("categoria_fase_temprana", "OTROS")).upper(),
                resumen_ejecutivo=str(data.get("resumen_ejecutivo", "")),
                acciones_recomendadas=list(data.get("acciones_recomendadas", [])),
                estimacion_meses_hasta_licitacion=(
                    int(data["estimacion_meses_hasta_licitacion"])
                    if data.get("estimacion_meses_hasta_licitacion") is not None
                    else None
                ),
                modo_degradado=bool(data.get("modo_degradado", False)),
                version_esquema=int(data.get("version_esquema", 2))
            )
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise BoletinDeserializationError(f"Error al deserializar DictamenCentinelaDTO: {e}") from e

    @classmethod
    def from_json(cls, json_str: str, estricto: bool = False) -> "DictamenCentinelaDTO":
        try:
            data = json.loads(json_str)
            return cls.from_dict(data, estricto=estricto)
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise BoletinDeserializationError(f"Error al decodificar JSON para DictamenCentinelaDTO: {e}") from e


@dataclass
class AlertaBoletinDTO:
    """
    DTO principal que representa una alerta de oportunidad en fase temprana desde DOGC/BOPB.
    """
    fuente: str  # 'DOGC' | 'BOPB'
    num_boletin: str
    fecha_publicacion: str  # ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)
    organo_emisor: str
    municipio: str
    titulo_anuncio: str
    seccion_boletin: str = ""
    url_anuncio: str = ""
    url_pdf: str = ""
    texto_sumario: str = ""
    score_temprano: int = 0
    motivos_score: List[str] = field(default_factory=list)
    dictamen_ia: Optional[DictamenCentinelaDTO] = None
    estado_operativo: str = "NUEVA_FASE_TEMPRANA"
    expediente_licitacion_vinculado: Optional[str] = None
    notas_usuario: str = ""
    fecha_ingesta: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    id_alerta: Optional[str] = None

    def __post_init__(self):
        # 1. Validación de fuente
        if not self.fuente or self.fuente.upper() not in {"DOGC", "BOPB"}:
            raise BoletinDTOValidationError(f"`fuente` debe ser 'DOGC' o 'BOPB', recibido: '{self.fuente}'")
        self.fuente = self.fuente.upper()

        # 2. Validación de campos requeridos no vacíos
        if not self.num_boletin or not str(self.num_boletin).strip():
            raise BoletinDTOValidationError("`num_boletin` no puede estar vacío.")
        if not self.titulo_anuncio or not str(self.titulo_anuncio).strip():
            raise BoletinDTOValidationError("`titulo_anuncio` no puede estar vacío.")
        if not self.organo_emisor or not str(self.organo_emisor).strip():
            raise BoletinDTOValidationError("`organo_emisor` no puede estar vacío.")

        # 3. Validación de estado operativo
        self.estado_operativo = str(self.estado_operativo).upper()
        if self.estado_operativo not in ESTADOS_BOLETIN_VALIDOS:
            raise BoletinDTOValidationError(
                f"`estado_operativo` inválido: '{self.estado_operativo}'. Permitidos: {ESTADOS_BOLETIN_VALIDOS}"
            )

        # 4. Cálculo determinista del SHA256 id_alerta si no fue provisto
        if not self.id_alerta:
            raw_string = f"{self.fuente}|{self.num_boletin.strip()}|{self.titulo_anuncio.strip().lower()}"
            self.id_alerta = hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.dictamen_ia is not None:
            data["dictamen_ia"] = self.dictamen_ia.to_dict()
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlertaBoletinDTO":
        if not isinstance(data, dict):
            raise BoletinDeserializationError("Los datos de entrada deben ser un diccionario Python.")
        
        try:
            dictamen_raw = data.get("dictamen_ia")
            dictamen_dto = None
            if dictamen_raw:
                if isinstance(dictamen_raw, str):
                    dictamen_dto = DictamenCentinelaDTO.from_json(dictamen_raw)
                elif isinstance(dictamen_raw, dict):
                    dictamen_dto = DictamenCentinelaDTO.from_dict(dictamen_raw)
                elif isinstance(dictamen_raw, DictamenCentinelaDTO):
                    dictamen_dto = dictamen_raw

            return cls(
                id_alerta=data.get("id_alerta"),
                fuente=str(data.get("fuente", "")),
                num_boletin=str(data.get("num_boletin", "")),
                fecha_publicacion=str(data.get("fecha_publicacion", "")),
                organo_emisor=str(data.get("organo_emisor", "")),
                municipio=str(data.get("municipio", "")),
                titulo_anuncio=str(data.get("titulo_anuncio", "")),
                seccion_boletin=str(data.get("seccion_boletin", "")),
                url_anuncio=str(data.get("url_anuncio", "")),
                url_pdf=str(data.get("url_pdf", "")),
                texto_sumario=str(data.get("texto_sumario", "")),
                score_temprano=int(data.get("score_temprano", 0)),
                motivos_score=list(data.get("motivos_score", [])),
                dictamen_ia=dictamen_dto,
                estado_operativo=str(data.get("estado_operativo", "NUEVA_FASE_TEMPRANA")),
                expediente_licitacion_vinculado=data.get("expediente_licitacion_vinculado"),
                notas_usuario=str(data.get("notas_usuario", "")),
                fecha_ingesta=str(data.get("fecha_ingesta", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
            )

        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise BoletinDeserializationError(f"Error al deserializar AlertaBoletinDTO: {e}") from e

    @classmethod
    def from_json(cls, json_str: str) -> "AlertaBoletinDTO":
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise BoletinDeserializationError(f"Error al decodificar JSON para AlertaBoletinDTO: {e}") from e


# ==============================================================================
# Excepciones Adicionales de Ingesta (Paso 3)
# ==============================================================================

class CentinelaNetworkError(CentinelaError):
    """Error emitido en fallos de red/HTTP al conectar con los servidores oficiales."""
    pass

class CentinelaParseError(CentinelaError):
    """Error emitido en fallos de parseo de feeds XML/Atom."""
    pass

class CentinelaConfigError(CentinelaError):
    """Error emitido en fallos de carga del fichero de configuración yaml."""
    pass


# ==============================================================================
# Helpers de Trazabilidad y Normalización de Fechas (Paso 3)
# ==============================================================================

def log_evento_jsonl(evento_tipo: str, detalles: Dict[str, Any], log_path: str = "data/pipeline.jsonl") -> None:
    """
    Registra eventos estructurados deterministas en el log central JSONL (Regla 3).
    """
    log_path = ruta_proyecto(log_path)
    try:
        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        payload = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "componente": "centinela",
            "evento": evento_tipo,
            "detalles": detalles
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[!] Error al escribir evento JSONL en {log_path}: {e}")


def normalizar_fecha_boletin_utc(fecha_raw: str) -> str:
    """
    Normaliza fechas de feeds Atom/RSS a formato ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ).
    """
    if not fecha_raw or not fecha_raw.strip():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw = fecha_raw.strip()
    try:
        # Formato ISO 8601 (2026-07-26T08:00:00+02:00 o 2026-07-26T08:00:00Z)
        if "T" in raw:
            val = raw
            if val.endswith("Z"):
                val = val[:-1] + "+00:00"
            dt = datetime.fromisoformat(val)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Formato RFC 822 / RSS (Sun, 26 Jul 2026 08:00:00 GMT / +0200)
        from email.utils import parsedate_to_datetime
        dt_rfc = parsedate_to_datetime(raw)
        return dt_rfc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Fallback simple YYYY-MM-DD
        try:
            dt_simple = datetime.strptime(raw[:10], "%Y-%m-%d")
            return dt_simple.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==============================================================================
# Ingestor Resiliente de Fuentes Oficiales (Paso 3)
# ==============================================================================

class IngestorBoletines:
    """
    Cliente / Ingestor resiliente de fuentes oficiales de boletines (DOGC y BOPB).
    Soporta reintentos con backoff exponencial, modo degradado, normalización UTC y trazabilidad JSONL.
    """
    def __init__(self, config_path: str = "config/centinela_config.yaml"):
        import time
        self.config_path = ruta_proyecto(config_path)
        self.config = self.cargar_configuracion()

    def cargar_configuracion(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            raise CentinelaConfigError(f"No se encontró el archivo de configuración: {self.config_path}")
        try:
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if not data or "fuentes_oficiales" not in data:
                    raise CentinelaConfigError("El archivo de configuración YAML no contiene 'fuentes_oficiales'.")
                return data
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise CentinelaConfigError(f"Error al leer la configuración YAML: {e}") from e

    def _http_get_with_retry(self, url: str, timeout: int = 15, max_retries: int = 3) -> str:
        """
        Ejecuta una petición HTTP GET con reintentos y backoff exponencial (1s, 2s, 4s).
        """
        import urllib.request
        import urllib.error
        import time

        headers = {
            "User-Agent": "EcosistemaIncoop/1.0 (+https://incoop.cat; licitaciones-centinela)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"
        }

        last_error = None
        for intento in range(1, max_retries + 1):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        content_bytes = response.read()
                        try:
                            return content_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            return content_bytes.decode("latin-1", errors="replace")
                    else:
                        last_error = f"HTTP Error {response.status}"
            except Exception as e:
                last_error = str(e)

            if intento < max_retries:
                espera = 2 ** (intento - 1)
                time.sleep(espera)

        raise CentinelaNetworkError(f"Error HTTP tras {max_retries} reintentos en '{url}': {last_error}")

    def _find_elem(self, node, tags: List[str], namespaces: Dict[str, str] = None):

        """
        Helper defensivo para buscar nodos XML sin evaluar la veracidad booleana de Element (que falla en nodos hoja).
        """
        for tag in tags:
            try:
                found = node.find(tag, namespaces) if namespaces else node.find(tag)
                if found is not None:
                    return found
            except Exception:
                pass
        return None

    def parsear_xml_dogc(self, xml_content: str) -> List[AlertaBoletinDTO]:
        """
        Parsea el contenido XML Atom/RSS del DOGC y extrae AlertaBoletinDTOs.
        """
        import xml.etree.ElementTree as ET
        alertas = []
        try:
            root = ET.fromstring(xml_content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            entries = root.findall("{http://www.w3.org/2005/Atom}entry") or root.findall("atom:entry", ns) or root.findall(".//entry")
            if not entries:
                entries = root.findall(".//item")

            for entry in entries:
                title_node = self._find_elem(entry, ["{http://www.w3.org/2005/Atom}title", "atom:title", "title"], ns)
                title = title_node.text.strip() if (title_node is not None and title_node.text) else ""

                date_node = self._find_elem(entry, ["{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated", "atom:published", "atom:updated", "published", "updated", "pubDate", "dc:date"], ns)
                published = date_node.text.strip() if (date_node is not None and date_node.text) else ""

                link_node = self._find_elem(entry, ["{http://www.w3.org/2005/Atom}link", "atom:link", "link"], ns)
                link = ""
                if link_node is not None:
                    link = link_node.attrib.get("href", "") or (link_node.text or "").strip()

                summary_node = self._find_elem(entry, ["{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content", "atom:summary", "atom:content", "summary", "content", "description"], ns)
                summary = summary_node.text.strip() if (summary_node is not None and summary_node.text) else ""

                author_node = self._find_elem(entry, ["{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name", "atom:author/atom:name", "author/name", "author", "dc:creator"], ns)
                organo = author_node.text.strip() if (author_node is not None and author_node.text) else "Generalitat de Catalunya"

                if title:
                    alerta = AlertaBoletinDTO(
                        fuente="DOGC",
                        num_boletin="SUMARI-DOGC",
                        fecha_publicacion=normalizar_fecha_boletin_utc(published),
                        organo_emisor=organo,
                        municipio="Catalunya",
                        titulo_anuncio=title,
                        seccion_boletin="Diari Oficial",
                        url_anuncio=link,
                        texto_sumario=summary if summary else title
                    )
                    alertas.append(alerta)
            return alertas

        except ET.ParseError as e:
            raise CentinelaParseError(f"Error de sintaxis XML al parsear DOGC: {e}") from e
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise CentinelaParseError(f"Error al procesar XML del DOGC: {e}") from e

    def parsear_xml_bopb(self, xml_content: str) -> List[AlertaBoletinDTO]:
        """
        Parsea el contenido XML RSS del BOPB (Diputació de Barcelona) y extrae AlertaBoletinDTOs.
        """
        import xml.etree.ElementTree as ET
        alertas = []
        try:
            root = ET.fromstring(xml_content)
            items = root.findall(".//item")
            for item in items:
                title_node = self._find_elem(item, ["title"])
                title = title_node.text.strip() if (title_node is not None and title_node.text) else ""

                link_node = self._find_elem(item, ["link"])
                link = link_node.text.strip() if (link_node is not None and link_node.text) else ""

                pub_node = self._find_elem(item, ["pubDate", "dc:date"])
                pub_date = pub_node.text.strip() if (pub_node is not None and pub_node.text) else ""

                desc_node = self._find_elem(item, ["description"])
                description = desc_node.text.strip() if (desc_node is not None and desc_node.text) else ""

                guid_node = self._find_elem(item, ["guid"])
                guid = guid_node.text.strip() if (guid_node is not None and guid_node.text) else "BOPB-ITEM"

                if title:
                    organo = "Diputació de Barcelona / Ents Locals"
                    municipio = "Barcelona (Província)"
                    if "-" in title:
                        partes = title.split("-", 1)
                        possible_organo = partes[0].strip()
                        if len(possible_organo) > 3:
                            organo = possible_organo

                    alerta = AlertaBoletinDTO(
                        fuente="BOPB",
                        num_boletin=guid,
                        fecha_publicacion=normalizar_fecha_boletin_utc(pub_date),
                        organo_emisor=organo,
                        municipio=municipio,
                        titulo_anuncio=title,
                        seccion_boletin="Administració Local",
                        url_anuncio=link,
                        texto_sumario=description if description else title
                    )
                    alertas.append(alerta)
            return alertas
        except ET.ParseError as e:
            raise CentinelaParseError(f"Error de sintaxis XML al parsear BOPB: {e}") from e
        except Exception as e:
            if isinstance(e, CentinelaError):
                raise
            raise CentinelaParseError(f"Error al procesar XML del BOPB: {e}") from e


    def obtener_feed_dogc(self) -> List[AlertaBoletinDTO]:
        cfg = self.config.get("fuentes_oficiales", {}).get("dogc", {})
        if not cfg.get("activo", True):
            return []

        url = cfg.get("url_feed")
        if not url:
            return []

        log_evento_jsonl("boletin_fetch_started", {"fuente": "DOGC", "url": url})
        try:
            xml_str = self._http_get_with_retry(url)
            alertas = self.parsear_xml_dogc(xml_str)
            log_evento_jsonl("boletin_fetch_succeeded", {"fuente": "DOGC", "total_alertas": len(alertas)})
            return alertas
        except Exception as e:
            log_evento_jsonl("boletin_fetch_degraded", {"fuente": "DOGC", "error": str(e)})
            print(f"[!] Modo Degradado Activo (Centinela DOGC): {e}")
            return []

    def obtener_feed_bopb(self) -> List[AlertaBoletinDTO]:
        cfg = self.config.get("fuentes_oficiales", {}).get("bopb", {})
        if not cfg.get("activo", True):
            return []

        url = cfg.get("url_feed")
        if not url:
            return []

        log_evento_jsonl("boletin_fetch_started", {"fuente": "BOPB", "url": url})
        try:
            xml_str = self._http_get_with_retry(url)
            alertas = self.parsear_xml_bopb(xml_str)
            log_evento_jsonl("boletin_fetch_succeeded", {"fuente": "BOPB", "total_alertas": len(alertas)})
            return alertas
        except Exception as e:
            log_evento_jsonl("boletin_fetch_degraded", {"fuente": "BOPB", "error": str(e)})
            print(f"[!] Modo Degradado Activo (Centinela BOPB): {e}")
            return []

    def ejecutar_ingesta_completa(self) -> List[AlertaBoletinDTO]:
        """
        Ejecuta la ingesta consolidada multifuente (DOGC + BOPB), deduplicando por id_alerta SHA256.
        """
        alertas_dogc = self.obtener_feed_dogc()
        alertas_bopb = self.obtener_feed_bopb()

        consolidadas: Dict[str, AlertaBoletinDTO] = {}
        for a in alertas_dogc + alertas_bopb:
            if a.id_alerta not in consolidadas:
                consolidadas[a.id_alerta] = a

        resultado = list(consolidadas.values())
        log_evento_jsonl("boletin_batch_completed", {"total_consolidadas": len(resultado)})
        return resultado

    def healthcheck_centinela(self) -> Dict[str, Any]:
        """
        Ejecuta un autodiagnóstico determinista del ingestor del centinela (Regla 6).
        """
        res = {
            "status": "OK",
            "config_path": self.config_path,
            "fuentes_configuradas": [],
            "error": None
        }
        try:
            fuentes = self.config.get("fuentes_oficiales", {})
            res["fuentes_configuradas"] = list(fuentes.keys())
            if not fuentes:
                res["status"] = "ERROR"
                res["error"] = "No hay fuentes configuradas en fuentes_oficiales."
        except Exception as e:
            res["status"] = "CRITICAL"
            res["error"] = str(e)

        return res


# ==============================================================================
# Excepción y Motor de Filtrado por Reglas Duras (Paso 4)
# ==============================================================================

class CentinelaFilterError(CentinelaError):
    """Error emitido en fallos del motor de filtrado por reglas duras."""
    pass


class FiltroBoletinesReglas:
    """
    Motor de Segmentación y Filtrado por Reglas Duras de Fase Temprana (Paso 4).
    Evalúa anuncios de boletines oficiales contra palabras de veto y patrones clave LCSP.
    """
    def __init__(self, config_path: str = "config/centinela_config.yaml"):
        self.config_path = ruta_proyecto(config_path)
        self.config = self.cargar_configuracion()

    def cargar_configuracion(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return self._configuracion_por_defecto()
        try:
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if not data:
                    return self._configuracion_por_defecto()
                return data
        except Exception:
            return self._configuracion_por_defecto()

    def _configuracion_por_defecto(self) -> Dict[str, Any]:
        return {
            "keywords_tempranas": {
                "presupuestos": ["aprovació inicial del pressupost", "aprobacion inicial del presupuesto", "modificació de crèdit", "modificacion de credito"],
                "consultas_mercado": ["consultes preliminars", "consultas preliminares", "consulta prèvia", "art. 115 lcsp", "articulo 115 lcsp"],
                "subvenciones": ["pla estratègic de subvencions", "plan estrategico de subvenciones", "bases reguladores de subvencions"],
                "convenios_encargos": ["conveni de col·laboració", "convenio de colaboracion", "encàrrec a mitjà propi", "encargo a medio propio"],
                "informacion_previa": ["anunci d'informació prèvia", "anuncio de informacion previa"]
            },
            "palabras_descarte": [
                "multa", "sanció", "sancion", "tràfic", "trafico", "pèrdua dni", "licència d'obres menor", "licencia de obras menor", "notificació por compareixença"
            ],
            "scoring_temprano": {
                "umbral_minimo": 30,
                "pts_presupuestos": 40,
                "pts_consultas_mercado": 50,
                "pts_subvenciones": 30,
                "pts_convenios_encargos": 30,
                "pts_informacion_previa": 40
            }
        }

    def evaluar_alerta(self, alerta: AlertaBoletinDTO) -> Tuple[bool, int, List[str]]:
        """
        Evalúa individualmente una alerta de boletín contra reglas duras.
        Devuelve (es_aceptada, score_total, motivos_list).
        """
        texto_analisis = f"{alerta.titulo_anuncio} {alerta.texto_sumario}".lower()

        params = self.config.get("parametros_fase_temprana", {})

        # 1. Comprobación contextual de palabras de veto (con filtro de contexto negativo)
        palabras_descarte = params.get("exclusiones_tempranas", []) or self.config.get("palabras_descarte", [])
        frases_negativas = ["no incluye", "no inclou", "excloses", "excluidas", "excepto", "excepte", "sense perjudici"]

        for kw in palabras_descarte:
            kw_low = kw.lower()
            if kw_low in texto_analisis:
                # Verificar si va precedida de frase de negación/excepción
                idx = texto_analisis.find(kw_low)
                prefijo = texto_analisis[max(0, idx - 30):idx]
                if any(neg in prefijo for neg in frases_negativas):
                    continue  # Desestimar veto por contexto negativo ("no incluye obras")
                return (False, 0, [f"VETO: Palabra de descarte '{kw}' detectada en el anuncio."])


        # 2. Puntuación por categorías tempranas LCSP
        keywords_cfg = params.get("palabras_clave_tempranas", {}) or self.config.get("keywords_tempranas", {})
        scoring_cfg = self.config.get("scoring_temprano", {})
        umbral_minimo = params.get("score_minimo_alerta", scoring_cfg.get("umbral_minimo", 30))

        score_total = 0
        motivos = []

        materia_pts = {
            "presupuestos": scoring_cfg.get("pts_presupuestos", 40),
            "consultas_mercado": scoring_cfg.get("pts_consultas_mercado", 50),
            "consultas_preliminares": scoring_cfg.get("pts_consultas_mercado", 50),
            "subvenciones": scoring_cfg.get("pts_subvenciones", 30),
            "convenios_encargos": scoring_cfg.get("pts_convenios_encargos", 30),
            "convenios_y_encargos": scoring_cfg.get("pts_convenios_encargos", 30),
            "informacion_previa": scoring_cfg.get("pts_informacion_previa", 40)
        }

        materia_nombres = {
            "presupuestos": "Presupuestos / Modificación de Crédito",
            "consultas_mercado": "Consulta Preliminar de Mercado (Art. 115 LCSP)",
            "consultas_preliminares": "Consulta Preliminar de Mercado (Art. 115 LCSP)",
            "subvenciones": "Plan Estratégico de Subvenciones",
            "convenios_encargos": "Convenio de Colaboración / Encargo a Medio Propio",
            "convenios_y_encargos": "Convenio de Colaboración / Encargo a Medio Propio",
            "informacion_previa": "Anuncio de Información Previa (Art. 134 LCSP)"
        }

        for cat_key, kw_list in keywords_cfg.items():
            for kw in kw_list:
                if kw.lower() in texto_analisis:
                    pts = materia_pts.get(cat_key, 30)
                    score_total += pts
                    cat_name = materia_nombres.get(cat_key, cat_key)
                    motivos.append(f"REGLA: Coincidencia en '{cat_name}' (kw: '{kw}') (+{pts} pts)")
                    break

        # 3. Verificación de umbral de aceptación
        if score_total >= umbral_minimo:
            return (True, score_total, motivos)
        else:
            if not motivos:
                motivos.append("DESCARTE: No coincide con ninguna categoría clave de fase temprana.")
            else:
                motivos.append(f"DESCARTE: Score insuficiente ({score_total} pts < umbral {umbral_minimo} pts).")
            return (False, score_total, motivos)

    def filtrar_alerta(self, alerta: AlertaBoletinDTO) -> AlertaBoletinDTO:
        """
        Aplica el filtro por reglas duras a una alerta DTO y actualiza sus atributos.
        """
        aceptada, score, motivos = self.evaluar_alerta(alerta)
        alerta.score_temprano = score
        alerta.motivos_score = motivos
        alerta.estado_operativo = "NUEVA_FASE_TEMPRANA" if aceptada else "DESCARTADA_POR_REGLAS"
        return alerta

    def filtrar_lote_boletines(self, alertas: List[AlertaBoletinDTO]) -> Tuple[List[AlertaBoletinDTO], Dict[str, Any]]:
        """
        Filtra un lote de DTOs, actualizando sus estados y generando métricas estructuradas JSONL.
        """
        aceptadas = []
        descartadas_veto = 0
        descartadas_score = 0

        for a in alertas:
            es_aceptada, score, motivos = self.evaluar_alerta(a)
            a.score_temprano = score
            a.motivos_score = motivos
            if es_aceptada:
                a.estado_operativo = "NUEVA_FASE_TEMPRANA"
                aceptadas.append(a)
            else:
                a.estado_operativo = "DESCARTADA_POR_REGLAS"
                if any("VETO:" in m for m in motivos):
                    descartadas_veto += 1
                else:
                    descartadas_score += 1

        metricas = {
            "total_ingresadas": len(alertas),
            "aceptadas": len(aceptadas),
            "descartadas_veto": descartadas_veto,
            "descartadas_score": descartadas_score
        }

        log_evento_jsonl("boletin_filtered_batch", metricas)
        return aceptadas, metricas

    def healthcheck_filtro_centinela(self) -> Dict[str, Any]:
        """
        Autodiagnóstico determinista del motor de reglas duras del centinela (Regla 6).
        """
        params = self.config.get("parametros_fase_temprana", {})
        kw_cfg = params.get("palabras_clave_tempranas", {}) or self.config.get("keywords_tempranas", {})
        exclusiones = params.get("exclusiones_tempranas", []) or self.config.get("palabras_descarte", [])
        umbral = params.get("score_minimo_alerta", 30)

        res = {
            "status": "OK",
            "config_path": self.config_path,
            "categorias_cargadas": len(kw_cfg),
            "palabras_descarte_cargadas": len(exclusiones),
            "umbral_minimo": umbral,
            "error": None
        }
        return res


# ==============================================================================
# Excepción y Analista IA de Boletines (Paso 5)
# ==============================================================================

class CentinelaLLMError(CentinelaError):
    """Error emitido en fallos del analista LLM del centinela."""
    pass


class AnalistaBoletinesIA:
    """
    Analista IA de Boletines Oficiales (Paso 5).
    Utiliza modelos LLM (Ollama con fallback a Gemini o Modo Degradado) para clasificar
    semánticamente anuncios de fase temprana y generar DictamenCentinelaDTO.
    """
    def __init__(self, proveedor_llm=None, config_prompts_path: str = "config/prompts_lcsp.yaml",
                 autoinicializar_proveedor: bool = True):
        """
        `autoinicializar_proveedor=False` fuerza la ausencia de proveedor. Es necesario
        porque, desde que la factoría funciona, pasar `proveedor_llm=None` ya no expresa
        "sin LLM": construye un proveedor real que sale a la red. Sin esta vía no había
        forma de ejercitar el Modo Degradado ni de mantener las pruebas herméticas.
        """
        self.config_prompts_path = ruta_proyecto(config_prompts_path)
        if proveedor_llm is not None:
            self.proveedor_llm = proveedor_llm
        elif autoinicializar_proveedor:
            self.proveedor_llm = self._inicializar_proveedor_llm()
        else:
            self.proveedor_llm = None

    def _inicializar_proveedor_llm(self):
        try:
            from src.analista import proveedor_llm_factory
            return proveedor_llm_factory(self.config_prompts_path) if hasattr(self, 'config_path') else proveedor_llm_factory()
        except Exception as e:
            print(f"[!] Advertencia al inicializar proveedor LLM en centinela: {e}")
            return None

    def construir_prompt_analisis(self, alerta: AlertaBoletinDTO) -> str:
        """
        Construye el prompt especializado bilingüe utilizando la plantilla de config/prompts_lcsp.yaml.
        """
        prompt_template = None
        if os.path.exists(self.config_prompts_path):
            try:
                import yaml
                with open(self.config_prompts_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "centinela_boletines" in data:
                        prompt_template = data["centinela_boletines"]
            except Exception:
                pass

        if not prompt_template:
            prompt_template = """Analiza el anuncio de boletín oficial ({fuente}):
Órgano: {organo_emisor}
Municipio: {municipio}
Título: {titulo_anuncio}
Sumario: {texto_sumario}
PMP Estimado Pagador: {pmp_dias} días

Devuelve un JSON con: es_oportunidad_temprana (bool), nivel_interes ("ALTO"|"MEDIO"|"BAJO"|"NULO"), categoria_fase_temprana ("PRESUPUESTO"|"SUBVENCION"|"CONVENIO"|"CONSULTA_PRELIMINAR"|"OTROS"), resumen_ejecutivo, acciones_recomendadas ([str]), estimacion_meses_hasta_licitacion (int o null)."""

        pmp_dias = 30
        try:
            from src.pmp_service import PMPService
            pmp_svc = PMPService()
            pmp_dias = pmp_svc.obtener_pmp(alerta.municipio or alerta.organo_emisor)
        except Exception:
            pass

        return (
            prompt_template
            .replace("{fuente}", alerta.fuente or "")
            .replace("{organo_emisor}", alerta.organo_emisor or "")
            .replace("{municipio}", alerta.municipio or "")
            .replace("{titulo_anuncio}", alerta.titulo_anuncio or "")
            .replace("{texto_sumario}", alerta.texto_sumario or "")
            .replace("{pmp_dias}", str(pmp_dias))
        )


    def _dictamen_fallback_degradado(self, motivo: str = "Análisis IA diferido por indisponibilidad de modelo") -> DictamenCentinelaDTO:
        """
        Construye un dictamen de fallback seguro en Modo Degradado (Regla 5).
        """
        return DictamenCentinelaDTO(
            # `es_oportunidad_temprana=True` significa aquí "no descartar sin mirar",
            # no un juicio favorable: quien decide es el humano, no este fallback.
            es_oportunidad_temprana=True,
            # Antes decía "MEDIO", y el evaluador lo premiaba con +15 pts: un análisis
            # que nunca ocurrió subía la prioridad de la alerta. DESCONOCIDO no puntúa.
            nivel_interes="DESCONOCIDO",
            categoria_fase_temprana="OTROS",
            resumen_ejecutivo=f"Modo Degradado: {motivo}.",
            acciones_recomendadas=["Revisar anuncio manualmente en portal oficial", "Re-analizar cuando el modelo LLM esté disponible"],
            estimacion_meses_hasta_licitacion=None,
            modo_degradado=True
        )

    def analizar_alerta(self, alerta: AlertaBoletinDTO) -> AlertaBoletinDTO:
        """
        Analiza cualitativamente una alerta de boletín con el proveedor LLM.
        Si el LLM no responde, aplica Modo Degradado sin interrumpir la alerta.
        """
        if not self.proveedor_llm:
            log_evento_jsonl("boletin_llm_degraded", {"id_alerta": alerta.id_alerta, "motivo": "Sin proveedor LLM configurado"})
            alerta.dictamen_ia = self._dictamen_fallback_degradado("Sin proveedor LLM disponible")
            alerta.estado_operativo = "ANALISIS_DIFERIDO_BOLETIN"
            return alerta

        log_evento_jsonl("boletin_llm_started", {"id_alerta": alerta.id_alerta, "fuente": alerta.fuente})
        prompt_usuario = self.construir_prompt_analisis(alerta)
        prompt_sistema = (
            "Eres un analista experto en licitaciones públicas LCSP en Catalunya y España.\n"
            "Tu tarea es analizar anuncios de boletines oficiales (DOGC/BOPB) y clasificar si representan "
            "una oportunidad de negocio en fase temprana para Incoop, SCCL.\n"
            "Debes responder EXCLUSIVAMENTE con un JSON válido estructurado como DictamenCentinelaDTO:\n"
            '{"es_oportunidad_temprana": true|false, "nivel_interes": "ALTO"|"MEDIO"|"BAJO"|"NULO", '
            '"categoria_fase_temprana": "PRESUPUESTO"|"SUBVENCION"|"CONVENIO"|"CONSULTA_PRELIMINAR"|"OTROS", '
            '"resumen_ejecutivo": "string", "acciones_recomendadas": ["string"], '
            '"estimacion_meses_hasta_licitacion": int|null}'
        )

        try:
            res_llm = self.proveedor_llm.consultar(prompt_sistema, prompt_usuario, timeout=120)
            raw_json = res_llm.get("raw_response", "")

            clean_text = raw_json.strip()
            if "```" in clean_text:
                lines = clean_text.split("\n")
                clean_lines = [l for l in lines if not l.strip().startswith("```")]
                clean_text = "\n".join(clean_lines).strip()

            # Estricto: si la respuesta no trae la forma completa del esquema, se trata
            # como fallo y se degrada. Antes se aceptaba y los huecos se rellenaban solos.
            dictamen = DictamenCentinelaDTO.from_json(clean_text, estricto=True)


            alerta.dictamen_ia = dictamen
            alerta.estado_operativo = "ANALIZADA_IA"
            log_evento_jsonl("boletin_llm_succeeded", {"id_alerta": alerta.id_alerta, "nivel_interes": dictamen.nivel_interes, "modelo": res_llm.get("modelo")})
            return alerta

        except Exception as e:
            log_evento_jsonl("boletin_llm_degraded", {"id_alerta": alerta.id_alerta, "error": str(e)})
            print(f"[!] Modo Degradado (Analista Centinela LLM): {e}")
            alerta.dictamen_ia = self._dictamen_fallback_degradado(f"Error LLM: {e}")
            alerta.estado_operativo = "ANALISIS_DIFERIDO_BOLETIN"
            return alerta


    def analizar_lote_alertas(self, alertas: List[AlertaBoletinDTO]) -> List[AlertaBoletinDTO]:
        """
        Analiza un lote de alertas DTOs con el proveedor LLM.
        """
        resultado = []
        for a in alertas:
            res_dto = self.analizar_alerta(a)
            resultado.append(res_dto)
        return resultado

    def healthcheck_analista_centinela(self) -> Dict[str, Any]:
        """
        Autodiagnóstico determinista del analista IA del centinela (Regla 6).
        """
        res = {
            "status": "OK",
            "proveedor_llm_disponible": self.proveedor_llm is not None,
            "config_prompts_path": self.config_prompts_path,
            "error": None
        }
        return res


# ==============================================================================
# Excepción y Evaluador de Scoring y Priorización Temprana (Paso 6)
# ==============================================================================

class CentinelaScoringError(CentinelaError):
    """Error emitido en fallos del evaluador de scoring y priorización del centinela."""
    pass


class EvaluadorScoringCentinela:
    """
    Evaluador de Scoring Consolidado y Priorización Temprana (Paso 6).
    Consolida de forma determinista el score de reglas duras y la cualificación del Analista IA.
    """
    def __init__(self, config_path: str = "config/centinela_config.yaml"):
        self.config_path = ruta_proyecto(config_path)
        self.config = self.cargar_configuracion()

    def cargar_configuracion(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return {"umbral_prioridad_alta": 70, "umbral_minimo_aceptacion": 40}
        try:
            import yaml
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data or {}
        except Exception:
            return {"umbral_prioridad_alta": 70, "umbral_minimo_aceptacion": 40}

    def evaluar_alerta(self, alerta: AlertaBoletinDTO) -> AlertaBoletinDTO:
        """
        Calcula el score final consolidado y asigna el estado operativo y priorización final.
        """
        score_base = alerta.score_temprano
        score_ajustado = score_base
        motivos = list(alerta.motivos_score)

        # Ajuste cualitativo según dictamen IA si está disponible.
        # Un dictamen degradado no expresa ningún juicio: se conserva el score de las
        # reglas duras, que sí es un dato real, y no se infiere interés ni desinterés
        # (contrato del Bloque 2, regla 4). Antes, un análisis fallido restaba 30 pts
        # y hacía desaparecer la alerta.
        if alerta.dictamen_ia is not None and getattr(alerta.dictamen_ia, "modo_degradado", False):
            motivos.append(
                "SCORE: Dictamen IA en Modo Degradado; se conserva la puntuación de reglas "
                "duras sin inferir interés (0 pts)"
            )
        elif alerta.dictamen_ia is not None:
            interes = str(alerta.dictamen_ia.nivel_interes).upper()
            if interes == "ALTO":
                score_ajustado += 30
                motivos.append("SCORE: Bonificación por dictamen IA de Interés ALTO (+30 pts)")
            elif interes == "MEDIO":
                score_ajustado += 15
                motivos.append("SCORE: Bonificación por dictamen IA de Interés MEDIO (+15 pts)")
            elif interes == "BAJO":
                motivos.append("SCORE: Dictamen IA de Interés BAJO (0 pts)")
            elif interes == "NULO":
                score_ajustado -= 30
                motivos.append("SCORE: Penalización por dictamen IA de Interés NULO (-30 pts)")

        # Evaluación de riesgo financiero PMP (Periodo Medio de Pago)
        try:
            from src.pmp_service import PMPService

            pmp_svc = PMPService()
            pmp_dias, penalizacion_pmp, clasif_pmp = pmp_svc.evaluar_riesgo_pmp(alerta.municipio or alerta.organo_emisor)
            if penalizacion_pmp < 0:
                score_ajustado += penalizacion_pmp
                motivos.append(f"FINANCIERO: Penalización por PMP de {pmp_dias} días ({clasif_pmp}) ({penalizacion_pmp} pts)")
        except Exception as e:
            print(f"[!] Advertencia evaluando PMP en centinela: {e}")



        # Acotar score en rango [0, 100]
        score_final = max(0, min(100, score_ajustado))
        alerta.score_temprano = score_final
        alerta.motivos_score = motivos

        # Matriz de priorización de estados
        params = self.config.get("parametros_fase_temprana", {})
        umbral_alta = params.get("score_prioridad_alta", 70)
        umbral_min = params.get("score_minimo_alerta", 40)

        if alerta.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN":
            if score_final < umbral_min:
                alerta.estado_operativo = "DESCARTADA_POR_REGLAS"
        else:
            if score_final >= umbral_alta:
                alerta.estado_operativo = "NUEVA_FASE_TEMPRANA"
            elif score_final >= umbral_min:
                alerta.estado_operativo = "NUEVA_FASE_TEMPRANA"
            else:
                alerta.estado_operativo = "DESCARTADA_POR_REGLAS"

        return alerta

    def evaluar_lote(self, alertas: List[AlertaBoletinDTO]) -> Tuple[List[AlertaBoletinDTO], Dict[str, Any]]:
        """
        Evalúa y prioriza un lote completo de alertas DTOs.
        """
        evaluadas = []
        alta_prio = 0
        media_prio = 0
        descartadas = 0
        diferidas = 0

        params = self.config.get("parametros_fase_temprana", {})
        umbral_alta = params.get("score_prioridad_alta", 70)

        for a in alertas:
            res_dto = self.evaluar_alerta(a)
            evaluadas.append(res_dto)

            if res_dto.estado_operativo == "ANALISIS_DIFERIDO_BOLETIN":
                diferidas += 1
            elif res_dto.estado_operativo == "DESCARTADA_POR_REGLAS":
                descartadas += 1
            elif res_dto.score_temprano >= umbral_alta:
                alta_prio += 1
            else:
                media_prio += 1

        metricas = {
            "total_evaluadas": len(alertas),
            "alta_prioridad": alta_prio,
            "media_prioridad": media_prio,
            "descartadas": descartadas,
            "diferidas": diferidas
        }

        log_evento_jsonl("boletin_scoring_batch", metricas)
        return evaluadas, metricas

    def healthcheck_scoring_centinela(self) -> Dict[str, Any]:
        """
        Autodiagnóstico determinista del evaluador de scoring (Regla 6).
        """
        params = self.config.get("parametros_fase_temprana", {})
        return {
            "status": "OK",
            "config_path": self.config_path,
            "score_prioridad_alta": params.get("score_prioridad_alta", 70),
            "score_minimo_alerta": params.get("score_minimo_alerta", 40),
            "error": None
        }


# ==============================================================================
# Excepción, Trazabilidad JSONL y Resiliencia en Modo Degradado (Paso 7)
# ==============================================================================

class CentinelaTrazabilidadError(CentinelaError):
    """Error emitido en fallos del subsistema de trazabilidad y auditoría de la Capa 6."""
    pass


class GestorTrazabilidadCentinela:
    """
    Gestor determinista de trazabilidad JSONL y auditoría operativa del Centinela.
    Garantiza el registro estructurado de eventos en data/pipeline.jsonl (Regla 3).
    """
    def __init__(self, log_path: str = "data/pipeline.jsonl"):
        self.log_path = ruta_proyecto(log_path)
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)

    def registrar_evento(self, tipo_evento: str, payload: Dict[str, Any], estado: str = "INFO") -> None:
        """
        Registra de forma síncrona y determinista un evento en data/pipeline.jsonl.
        """
        evento = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "modulo": "centinela",
            "tipo_evento": tipo_evento,
            "estado": estado,
            "payload": payload
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[!] Error crítico en GestorTrazabilidadCentinela al escribir JSONL: {e}")

    def healthcheck_trazabilidad_centinela(self) -> Dict[str, Any]:
        """
        Autodiagnóstico determinista del subsistema de trazabilidad y permisos de disco (Regla 6).
        """
        directorio = os.path.dirname(os.path.abspath(self.log_path))
        permiso_escritura = os.access(directorio, os.W_OK)
        existe_fichero = os.path.exists(self.log_path)

        status = "OK" if permiso_escritura else "ERROR"
        error_msg = None if permiso_escritura else f"Sin permisos de escritura en {directorio}"

        return {
            "status": status,
            "log_path": self.log_path,
            "directorio_existe": os.path.exists(directorio),
            "permiso_escritura": permiso_escritura,
            "fichero_existe": existe_fichero,
            "error": error_msg
        }


def ejecutar_pipeline_centinela_resiliente(
    ingestor: IngestorBoletines,
    filtro: FiltroBoletinesReglas,
    analista: AnalistaBoletinesIA,
    evaluador: EvaluadorScoringCentinela,
    db_path: str = "data/licitaciones.db"
) -> Tuple[List[AlertaBoletinDTO], Dict[str, Any]]:
    """
    Orquestación resiliente completa del Centinela (Capas 6: Ingesta -> Filtro -> IA -> Scoring -> DB).
    Maneja excepciones ordenadamente y registra la trazabilidad en data/pipeline.jsonl.
    """
    trazabilidad = GestorTrazabilidadCentinela()
    trazabilidad.registrar_evento("boletin_pipeline_started", {"db_path": db_path})

    metricas_globales = {
        "ingresadas": 0,
        "aceptadas_filtro": 0,
        "analizadas_ia": 0,
        "alta_prioridad": 0,
        "guardadas_db": 0,
        "modo_degradado": False
    }

    try:
        # 1. Ingesta desde boletines oficiales (DOGC / BOPB)
        alertas_crudas = ingestor.ejecutar_ingesta_completa()
        metricas_globales["ingresadas"] = len(alertas_crudas)

        # 2. Filtrado por Reglas Duras
        alertas_filtradas, metricas_filtro = filtro.filtrar_lote_boletines(alertas_crudas)
        metricas_globales["aceptadas_filtro"] = metricas_filtro.get("aceptadas", 0)

        # 3. Análisis Cualitativo Semántico por IA (con Modo Degradado resiliente)
        alertas_analizadas = analista.analizar_lote_alertas(alertas_filtradas)
        metricas_globales["analizadas_ia"] = len(alertas_analizadas)

        # 4. Evaluador de Scoring Consolidado y Priorización
        alertas_priorizadas, metricas_scoring = evaluador.evaluar_lote(alertas_analizadas)
        metricas_globales["alta_prioridad"] = metricas_scoring.get("alta_prioridad", 0)

        # 5. Persistencia en SQLite v5 (boletines_alertas)
        try:
            from src.memoria import Memoria

            memoria_svc = Memoria(db_path=db_path)
            memoria_svc.setup_db()
            guardadas = 0

            for a in alertas_priorizadas:
                if a.estado_operativo != "DESCARTADA_POR_REGLAS":
                    memoria_svc.guardar_alerta_boletin(a)
                    guardadas += 1
            metricas_globales["guardadas_db"] = guardadas
        except Exception as e_db:
            print(f"[!] Modo Degradado (Persistencia DB Centinela): {e_db}")
            trazabilidad.registrar_evento("boletin_pipeline_degraded", {"error_db": str(e_db)}, estado="WARNING")
            metricas_globales["modo_degradado"] = True



        trazabilidad.registrar_evento("boletin_pipeline_completed", metricas_globales)
        return alertas_priorizadas, metricas_globales

    except Exception as e_global:
        print(f"[!] Error global en pipeline centinela: {e_global}")
        trazabilidad.registrar_evento("boletin_pipeline_degraded", {"error_fatal": str(e_global)}, estado="ERROR")
        metricas_globales["modo_degradado"] = True
        return [], metricas_globales


# ==============================================================================
# Excepción y Exportación de Reporting Comercial CSV (Paso 8)
# ==============================================================================

class CentinelaReportingError(CentinelaError):
    """Error emitido en fallos del generador de reportes CSV del centinela."""
    pass


def exportar_reporte_centinela_csv(
    db_path: str = "data/licitaciones.db",
    output_csv: str = "data/alertas_tempranas.csv"
) -> str:
    """
    Exporta las alertas de fase temprana guardadas en SQLite v5 (boletines_alertas)
    a un informe comercial CSV codificado en UTF-8 con BOM (utf-8-sig).
    Devuelve la ruta absoluta del archivo generado.
    """
    try:
        from src.memoria import Memoria

        memoria_svc = Memoria(db_path=db_path)
        alertas = memoria_svc.listar_alertas_tempranas(limite=500)

        output_csv = ruta_proyecto(output_csv)
        os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)

        fieldnames = [
            "id_alerta",
            "fuente",
            "num_boletin",
            "fecha_publicacion",
            "organo_emisor",
            "municipio",
            "pmp_dias",
            "titulo_anuncio",
            "categoria_fase_temprana",
            "score_temprano",
            "estado_operativo",
            "nivel_interes_ia",
            "resumen_ejecutivo_ia",
            "acciones_recomendadas",
            "url_anuncio"
        ]

        try:
            from src.pmp_service import PMPService
            pmp_svc = PMPService()
        except Exception:
            pmp_svc = None

        rows = []
        for a in alertas:
            pmp_val = pmp_svc.obtener_pmp(a.municipio or a.organo_emisor) if pmp_svc else 30
            interes_ia = a.dictamen_ia.nivel_interes if a.dictamen_ia else "N/A"
            resumen_ia = a.dictamen_ia.resumen_ejecutivo if a.dictamen_ia else ""
            cat_fase = a.dictamen_ia.categoria_fase_temprana if a.dictamen_ia and a.dictamen_ia.categoria_fase_temprana else "OTROS"
            acciones_str = "; ".join(a.dictamen_ia.acciones_recomendadas) if a.dictamen_ia and a.dictamen_ia.acciones_recomendadas else ""

            rows.append({
                "id_alerta": a.id_alerta,
                "fuente": a.fuente,
                "num_boletin": a.num_boletin,
                "fecha_publicacion": a.fecha_publicacion,
                "organo_emisor": a.organo_emisor,
                "municipio": a.municipio,
                "pmp_dias": pmp_val,
                "titulo_anuncio": a.titulo_anuncio,
                "categoria_fase_temprana": cat_fase,
                "score_temprano": a.score_temprano,
                "estado_operativo": a.estado_operativo,
                "nivel_interes_ia": interes_ia,
                "resumen_ejecutivo_ia": resumen_ia,
                "acciones_recomendadas": acciones_str,
                "url_anuncio": a.url_anuncio
            })


        with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

        log_evento_jsonl("boletin_report_generated", {
            "output_csv": output_csv,
            "total_registros": len(rows)
        })

        return os.path.abspath(output_csv)

    except Exception as e:
        raise CentinelaReportingError(f"Error al generar el reporte CSV del Centinela: {e}")


# ==============================================================================
# Excepción e Inspección CLI de Alertas (Paso 9)
# ==============================================================================

class CentinelaCLIError(CentinelaError):
    """Error emitido en fallos de la consola de comando e inspección del centinela."""
    pass


def cli_inspeccionar_alerta(id_alerta: str, db_path: str = "data/licitaciones.db") -> bool:
    """
    Muestra una ficha detallada e interactiva por consola de una alerta de boletín.
    """
    try:
        from src.memoria import Memoria

        memoria_svc = Memoria(db_path=db_path)
        alerta = memoria_svc.obtener_alerta_boletin(id_alerta)
        if not alerta:
            print(f"[-] No se encontró ninguna alerta de boletín con ID '{id_alerta}'.")
            return False

        try:
            from src.pmp_service import PMPService
            pmp_svc = PMPService()
            pmp_dias = pmp_svc.obtener_pmp(alerta.municipio or alerta.organo_emisor)
        except Exception:
            pmp_dias = 30

        print("=" * 100)
        print(f" FICHA DE INSPECCIÓN - CENTINELA DE BOLETINES (ID: {alerta.id_alerta[:16]}...) ".center(100, "="))
        print(f"Fuente: {alerta.fuente} | Nº Boletín: {alerta.num_boletin} | Fecha Pub: {alerta.fecha_publicacion}")
        print(f"Órgano Emisor: {alerta.organo_emisor}")
        print(f"Municipio: {alerta.municipio} (PMP Estimado Pagador: {pmp_dias} días)")
        print(f"Título: {alerta.titulo_anuncio}")
        print(f"URL: {alerta.url_anuncio}")
        print("-" * 100)
        print(f"Score Temprano: {alerta.score_temprano} pts | Estado Operativo: {alerta.estado_operativo}")
        print("Motivos Scoring:")
        for m in alerta.motivos_score:
            print(f"  • {m}")
        print("-" * 100)

        if alerta.dictamen_ia:
            print("DICTAMEN CUALITATIVO IA (Analista Centinela):")
            print(f"  • Nivel de Interés: {alerta.dictamen_ia.nivel_interes}")
            print(f"  • Categoría Fase Temprana: {alerta.dictamen_ia.categoria_fase_temprana}")
            print(f"  • Resumen Ejecutivo: {alerta.dictamen_ia.resumen_ejecutivo}")
            print("  • Acciones Recomendadas:")
            for acc in alerta.dictamen_ia.acciones_recomendadas:
                print(f"      - {acc}")
        else:
            print("DICTAMEN CUALITATIVO IA: Sin dictamen (Análisis IA diferido o sin proveedor LLM)")

        if alerta.notas_usuario:
            print(f"Notas del Usuario: {alerta.notas_usuario}")
        print("=" * 100)

        log_evento_jsonl("boletin_cli_inspected", {"id_alerta": id_alerta})
        return True
    except Exception as e:
        raise CentinelaCLIError(f"Error al inspeccionar alerta '{id_alerta}': {e}")


def cli_listar_alertas(
    estado: Optional[str] = None,
    fuente: Optional[str] = None,
    limite: int = 20,
    db_path: str = "data/licitaciones.db"
) -> None:
    """
    Renderiza una tabla ordenada por consola de las alertas tempranas registradas.
    """
    try:
        from src.memoria import Memoria

        memoria_svc = Memoria(db_path=db_path)
        alertas = memoria_svc.listar_alertas_tempranas(estado=estado, fuente=fuente, limite=limite)

        print("\n" + "=" * 110)
        print(f" LISTADO DE ALERTAS DE FASE TEMPRANA ({len(alertas)} encontradas) ".center(110, "="))
        col_fmt = "{:<16} | {:<6} | {:<12} | {:<22} | {:<6} | {:<8} | {:<25}"
        print(col_fmt.format("ID Alerta", "Fuente", "Fecha Pub.", "Órgano / Municipio", "Score", "Interés", "Título Anuncio"))
        print("-" * 110)

        for a in alertas:
            id_short = a.id_alerta[:16]
            fecha_short = a.fecha_publicacion[:10] if a.fecha_publicacion else "N/A"
            org_muni = (a.municipio or a.organo_emisor or "")[:22]
            interes = a.dictamen_ia.nivel_interes if a.dictamen_ia else "N/A"
            titulo_short = a.titulo_anuncio[:25]

            org_muni = "".join(c if ord(c) < 128 else "?" for c in org_muni)
            titulo_short = "".join(c if ord(c) < 128 else "?" for c in titulo_short)

            print(col_fmt.format(id_short, a.fuente, fecha_short, org_muni, f"{a.score_temprano}pts", interes, titulo_short))

        print("=" * 110 + "\n")
    except Exception as e:
        raise CentinelaCLIError(f"Error al listar alertas del centinela: {e}")


def cli_actualizar_estado_alerta(
    id_alerta: str,
    nuevo_estado: str,
    notas: Optional[str] = None,
    db_path: str = "data/licitaciones.db"
) -> bool:
    """
    Actualiza el estado operativo de una alerta desde la consola CLI.
    """
    try:
        from src.memoria import Memoria

        memoria_svc = Memoria(db_path=db_path)
        exito = memoria_svc.actualizar_estado_alerta_boletin(id_alerta, nuevo_estado, notas=notas)

        if exito:
            print(f"[+] Estado de la alerta '{id_alerta[:16]}...' actualizado a '{nuevo_estado.upper()}'.")
            log_evento_jsonl("boletin_cli_state_updated", {"id_alerta": id_alerta, "nuevo_estado": nuevo_estado})
        else:
            print(f"[-] No se pudo actualizar el estado de la alerta '{id_alerta}'.")

        return exito
    except Exception as e:
        raise CentinelaCLIError(f"Error al actualizar estado de la alerta '{id_alerta}': {e}")


def main_cli_centinela():
    """Punto de entrada independiente de consola CLI para el Centinela (python src/centinela.py)."""
    import argparse
    parser = argparse.ArgumentParser(description="Consola CLI e Inspección del Centinela de Boletines (Capa 6)")
    parser.add_argument("--inspeccionar", type=str, help="ID de la alerta de boletín a inspeccionar en detalle.")
    parser.add_argument("--listar", action="store_true", help="Lista las alertas tempranas por consola.")
    parser.add_argument("--estado-filtro", type=str, help="Filtra el listado por estado operativo.")
    parser.add_argument("--fuente-filtro", type=str, help="Filtra el listado por fuente (DOGC / BOPB).")
    parser.add_argument("--actualizar-estado", type=str, help="Nuevo estado operativo a asignar a la alerta.")
    parser.add_argument("--id-alerta", type=str, help="ID de la alerta objetivo para actualización de estado.")
    parser.add_argument("--notas", type=str, help="Notas adicionales del usuario al actualizar el estado.")
    parser.add_argument("--exportar-csv", type=str, nargs="?", const="data/alertas_tempranas.csv", help="Exporta el informe comercial CSV de alertas.")
    parser.add_argument("--db", type=str, default="data/licitaciones.db", help="Ruta de la base de datos SQLite.")

    args = parser.parse_args()

    if args.inspeccionar:
        cli_inspeccionar_alerta(args.inspeccionar, db_path=args.db)
    elif args.actualizar_estado and args.id_alerta:
        cli_actualizar_estado_alerta(args.id_alerta, args.actualizar_estado, notas=args.notas, db_path=args.db)
    elif args.exportar_csv:
        csv_out = exportar_reporte_centinela_csv(db_path=args.db, output_csv=args.exportar_csv)
        print(f"[+] Informe comercial CSV del Centinela generado en: {csv_out}")
    else:
        cli_listar_alertas(estado=args.estado_filtro, fuente=args.fuente_filtro, db_path=args.db)

if __name__ == "__main__":
    main_cli_centinela()








