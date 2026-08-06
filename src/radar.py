import os
import re
import yaml
import requests
import feedparser
import xml.etree.ElementTree as ET
import unicodedata
import time
from typing import List, Dict, Any

from src import ruta_proyecto

class Radar:
    def __init__(self, config_dir: str = "config"):
        # Resuelto contra la raíz del proyecto: si se resolviera contra el directorio
        # de trabajo, el perfil comercial no se cargaría al ejecutar desde otra carpeta
        # y el Radar seguiría adelante con los valores por defecto, en silencio.
        self.config_dir = ruta_proyecto(config_dir)
        self.fuentes = self._load_yaml("fuentes.yaml").get("fuentes", [])
        self.perfil = self._load_yaml("perfil_incoop.yaml").get("perfil", {})
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        self.namespaces = {
            'atom': 'http://www.w3.org/2005/Atom',
            'cbc': 'urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2',
            'cac': 'urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2',
            'cac-place-ext': 'urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2',
            'cbc-place-ext': 'urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2'
        }
        
        # Mapa de estados para normalizar texto a códigos CODICE de 3 letras
        self.map_estados = {
            'evaluacion': 'EV',
            'adjudicada': 'ADJ',
            'resuelta': 'RES',
            'publicada': 'PUB',
            'licitacion': 'PUB',
            'anuncio': 'PUB',
            'formalizada': 'ADJ'
        }

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.config_dir, filename)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return {}

    def _normalizar_texto(self, texto: str) -> str:
        if not texto:
            return ""
        texto = texto.lower()
        texto = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if unicodedata.category(c) != "Mn"
        )
        return texto

    def _detectar_subrogacion_preliminar(self, texto: str) -> bool:
        """Detecta una posible subrogación sin confundir una negación con una obligación."""
        normalizado = self._normalizar_texto(texto)
        negaciones = (
            r"\b(?:sin|sense)\s+(?:obligacion\s+de\s+)?subrogac",
            r"\bno\s+procede(?:ix)?\s+(?:la\s+)?subrogac",
            r"\bno\s+existe\s+(?:ninguna\s+)?obligacion\s+de\s+subrogac",
        )
        if any(re.search(patron, normalizado) for patron in negaciones):
            return False
        return "subrogac" in normalizado

    def _detectar_revision_precios_preliminar(self, texto: str) -> bool:
        """Detecta sólo la cláusula relevante, no cualquier mención a una revisión."""
        normalizado = self._normalizar_texto(texto)
        clausula = r"revision\s+de\s+(?:precios|preus)"
        if re.search(r"\b(?:sin|sense)\s+" + clausula, normalizado):
            return False
        if re.search(r"\bno\s+(?:se\s+)?(?:admite|procede|contempla)\s+" + clausula, normalizado):
            return False
        return bool(re.search(clausula, normalizado))

    def fetch_feed(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = source.get("nombre", "Desconocida")
        url = source.get("url")
        if not url:
            print(f"[-] [{name}] URL no configurada.")
            return []

        safe_name = "".join(c if ord(c) < 128 else "?" for c in name)
        print(f"[~] Conectando a {safe_name}...")
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"[!] [{safe_name}] Error HTTP {response.status_code}")
                return []
            
            print(f"[+] [{safe_name}] Descargados {len(response.content)} bytes.")
            
            # Parse XML con ElementTree
            root_xml = ET.fromstring(response.content)
            xml_entry_map = {}
            for xml_entry in root_xml.findall('atom:entry', self.namespaces):
                link_node = xml_entry.find('atom:link', self.namespaces)
                href = link_node.attrib.get('href') if link_node is not None else None
                if href:
                    xml_entry_map[href] = xml_entry
                else:
                    id_node = xml_entry.find('atom:id', self.namespaces)
                    if id_node is not None and id_node.text:
                        xml_entry_map[id_node.text.strip()] = xml_entry

            # Parse con feedparser
            feed = feedparser.parse(response.content)
            print(f"[*] [{safe_name}] Parseadas {len(feed.entries)} licitaciones.")
            
            normalized_entries = []
            for entry in feed.entries:
                link = entry.get("link", "")
                entry_id = entry.get("id", "")
                xml_entry = xml_entry_map.get(link) or xml_entry_map.get(entry_id)
                
                normalized = self._normalize_entry(entry, name, xml_entry)
                if normalized:
                    normalized_entries.append(normalized)
            
            return normalized_entries

        except requests.RequestException as e:
            print(f"[!] [{safe_name}] Error de conexion: {e}")
            return []
        except Exception as e:
            print(f"[!] [{safe_name}] Error inesperado parseando feed: {e}")
            return []

    def _normalize_entry(self, entry: Any, source_name: str, xml_entry: Any) -> Dict[str, Any]:
        summary = entry.get("summary", "")
        title = entry.get("title", "")
        
        # 1. Extraer ID del expediente
        expediente = entry.get("cbc_contractfolderid")
        if not expediente:
            id_match = re.search(r"Id licitaci[oó]n:\s*([^;]+)", summary)
            if id_match:
                expediente = id_match.group(1).strip()
            else:
                expediente = entry.get("id", "").split("/")[-1]
        
        # 2. Extraer Órgano
        organo = "N/A"
        organo_match = re.search(r"[OÓ]rgano de Contrataci[oó]n:\s*([^;]+)", summary)
        if organo_match:
            organo = organo_match.group(1).strip()
        else:
            cbc_name = entry.get("cbc_name")
            if isinstance(cbc_name, str):
                organo = cbc_name

        # 3. Extraer Importe (PBL) y Valor Estimado (VEC)
        importe = 0.0
        vec = 0.0
        importe_extraido = False
        vec_extraido = False
        
        if xml_entry is not None:
            # PBL (Presupuesto Base sin IVA)
            tax_node = xml_entry.find('.//cbc:TaxExclusiveAmount', self.namespaces)
            if tax_node is not None and tax_node.text:
                try:
                    importe = float(tax_node.text.strip())
                    importe_extraido = True
                except ValueError:
                    pass
            
            # VEC (Valor Estimado del Contrato con prórrogas)
            est_node = xml_entry.find('.//cbc:EstimatedOverallContractAmount', self.namespaces)
            if est_node is not None and est_node.text:
                try:
                    vec = float(est_node.text.strip())
                    vec_extraido = True
                except ValueError:
                    pass

        # Fallback a regex sobre el summary en formato español o inglés
        if not importe_extraido:
            importe_match = re.search(r"Importe:\s*([\d\.,]+)", summary)
            if importe_match:
                try:
                    val_str = importe_match.group(1)
                    if "," in val_str and "." in val_str:
                        if val_str.rfind(".") < val_str.rfind(","):
                            val_str = val_str.replace(".", "").replace(",", ".")
                    elif "," in val_str:
                        val_str = val_str.replace(",", ".")
                    importe = float(val_str)
                    importe_extraido = True
                except ValueError:
                    importe = 0.0

        # Lógica de fallback mutuo
        if not vec_extraido:
            vec = importe
        if not importe_extraido:
            importe = vec

        # 4. Extraer Estado (Prioridad XML -> Fallback a regex con mapeo)
        estado = "N/A"
        estado_extraido = False
        
        if xml_entry is not None:
            status_node = xml_entry.find('.//cbc-place-ext:ContractFolderStatusCode', self.namespaces)
            if status_node is not None and status_node.text:
                estado = status_node.text.strip()
                estado_extraido = True

        if not estado_extraido:
            estado_match = re.search(r"Estado:\s*([^;]+)", summary)
            if estado_match:
                estado_raw = estado_match.group(1).strip()
                estado_norm = self._normalizar_texto(estado_raw)
                estado = self.map_estados.get(estado_norm, estado_raw)

        # 5. Fechas
        fecha_publicacion = entry.get("updated", "")
        fecha_limite = "N/A"
        end_date = entry.get("cbc_enddate")
        end_time = entry.get("cbc_endtime")
        if end_date:
            fecha_limite = end_date
            if end_time:
                fecha_limite += f" {end_time}"

        # 6. Enlace
        link = entry.get("link", "")

        # --- EXTRACCIÓN XML DIRECTO ---
        tipo_contrato_codigo = None
        cpvs = []
        procedimiento_codigo = None
        country_subentity_code = None
        localidad = "N/A"
        
        if xml_entry is not None:
            type_node = xml_entry.find('.//cbc:TypeCode', self.namespaces)
            if type_node is not None and type_node.text:
                tipo_contrato_codigo = type_node.text.strip()
                
            for cpv_node in xml_entry.findall('.//cbc:ItemClassificationCode', self.namespaces):
                if cpv_node.text:
                    cpvs.append(cpv_node.text.strip())

            proc_node = xml_entry.find('.//cbc:ProcedureCode', self.namespaces)
            if proc_node is not None and proc_node.text:
                procedimiento_codigo = proc_node.text.strip()

            subentity_node = xml_entry.find('.//cbc:CountrySubentityCode', self.namespaces)
            if subentity_node is not None and subentity_node.text:
                country_subentity_code = subentity_node.text.strip()

            city_node = xml_entry.find('.//cbc:CityName', self.namespaces)
            if city_node is not None and city_node.text:
                localidad = city_node.text.strip()

        # Detección de Subrogación y Revisión de precios en Título y Resumen
        texto_preliminar = f"{title}\n{summary}"
        subrogacion_detectada = self._detectar_subrogacion_preliminar(texto_preliminar)
        revision_precios_detectada = self._detectar_revision_precios_preliminar(texto_preliminar)

        # Urgencia (Tramitación)
        urgente = False
        if xml_entry is not None:
            urgency_node = xml_entry.find('.//cbc:UrgencyCode', self.namespaces)
            if urgency_node is not None and urgency_node.text:
                if urgency_node.text.strip() in ['2', '3']:
                    urgente = True
                
        # Loteado
        loteado = False
        if xml_entry is not None:
            lot_nodes = xml_entry.findall('.//cac:ProcurementProjectLot', self.namespaces)
            if len(lot_nodes) > 1:
                loteado = True

        # Extracción de documentos adicionales del XML
        documentos = []
        if xml_entry is not None:
            for doc_ref in xml_entry.findall('.//cac:AdditionalDocumentReference', self.namespaces):
                id_node = doc_ref.find('cbc:ID', self.namespaces)
                uri_node = doc_ref.find('.//cbc:URI', self.namespaces)
                
                if uri_node is not None and uri_node.text:
                    url_doc = uri_node.text.strip()
                    titulo_doc = id_node.text.strip() if id_node is not None and id_node.text else "Documento Adicional"
                    
                    titulo_low = titulo_doc.lower()
                    if "administrativ" in titulo_low or "pca" in titulo_low:
                        tipo_doc = "PCA"
                    elif "tecnic" in titulo_low or "ppt" in titulo_low or "prescripci" in titulo_low:
                        tipo_doc = "PPT"
                    elif any(kw in titulo_low for kw in ["anex", "model", "declaraci", "compromis"]):
                        tipo_doc = "Anexo"
                    else:
                        tipo_doc = "Otro"
                        
                    import hashlib
                    payload = f"{titulo_doc}|{url_doc}"
                    doc_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                    
                    documentos.append({
                        "titulo": titulo_doc,
                        "url": url_doc,
                        "tipo": tipo_doc,
                        "hash": doc_hash
                    })

        return {
            "id": expediente,
            "titulo": title,
            "organo": organo,
            "importe": importe,
            "estado": estado,
            "fecha_publicacion": fecha_publicacion,
            "fecha_limite": fecha_limite,
            "link": link,
            "fuente": source_name,
            "tipo_contrato_codigo": tipo_contrato_codigo,
            "cpvs": cpvs,
            "procedimiento_codigo": procedimiento_codigo,
            "country_subentity_code": country_subentity_code,
            "localidad": localidad,
            "vec": vec,
            "subrogacion_detectada": subrogacion_detectada,
            "revision_precios_detectada": revision_precios_detectada,
            "urgente": urgente,
            "loteado": loteado,
            "documentos": documentos
        }

    def fetch_socrata_api(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = source.get("nombre", "Desconocida")
        url = source.get("url")
        if not url:
            print(f"[-] [{name}] URL no configurada.")
            return []

        safe_name = "".join(c if ord(c) < 128 else "?" for c in name)
        print(f"[~] Conectando a la API de {safe_name}...")
        
        # Consulta de las últimas 100 licitaciones en fase de "Anunci de licitació"
        params = {
            "$where": "fase_publicacio='Anunci de licitació'",
            "$order": "data_publicacio_anunci DESC",
            "$limit": 100
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            if response.status_code != 200:
                print(f"[!] [{safe_name}] Error HTTP {response.status_code}")
                return []
            
            data = response.json()
            print(f"[+] [{safe_name}] Descargadas {len(data)} licitaciones por API.")
            
            normalized_entries = []
            for item in data:
                normalized = self._normalize_socrata_item(item, name)
                if normalized:
                    normalized_entries.append(normalized)
            
            return normalized_entries
        except Exception as e:
            print(f"[!] [{safe_name}] Error conectando/parseando API Socrata: {e}")
            return []

    def _normalize_socrata_item(self, item: Dict[str, Any], source_name: str) -> Dict[str, Any]:
        # ID expediente
        expediente = item.get("codi_expedient", "N/A")
        
        # Titulo / Objeto
        titulo = item.get("denominacio") or item.get("objecte_contracte") or "N/A"
        
        # Órgano de contratación (nom_departament_ens si existe, si no nom_organ)
        organo = item.get("nom_departament_ens") or item.get("nom_organ") or "N/A"
        
        # Importe base sin IVA (PBL)
        importe_str = item.get("pressupost_licitacio_sense_1") or item.get("pressupost_licitacio_sense") or "0"
        try:
            importe = float(importe_str)
        except ValueError:
            importe = 0.0
            
        # Valor Estimado del Contrato (VEC)
        vec_str = item.get("valor_estimat_contracte") or "0"
        try:
            vec = float(vec_str)
        except ValueError:
            vec = 0.0
            
        # Fallback mutuo
        if vec == 0.0:
            vec = importe
        if importe == 0.0:
            importe = vec
            
        # Estado (fase_publicacio es 'Anunci de licitació', lo normalizamos a 'PUB')
        fase = item.get("fase_publicacio", "")
        estado = "N/A"
        if fase == "Anunci de licitació":
            estado = "PUB"
            
        # Fechas (Socrata fecha: '2026-07-10T14:15:00.000')
        fecha_pub_raw = item.get("data_publicacio_anunci", "")
        fecha_publicacion = fecha_pub_raw.replace("T", " ").split(".")[0] if fecha_pub_raw else ""
        
        fecha_limite_raw = item.get("termini_presentacio_ofertes", "")
        fecha_limite = fecha_limite_raw.replace("T", " ").split(".")[0] if fecha_limite_raw else "N/A"
        
        # Enlace
        enllac_obj = item.get("enllac_publicacio")
        link = ""
        if isinstance(enllac_obj, dict):
            link = enllac_obj.get("url", "")
            
        # Mapeo de Tipo de Contrato (en catalán a código CODICE)
        # 1 = Suministros, 2 = Servicios, 3 = Obras, 21 = Concesión de Obras, 22 = Concesión de Servicios
        # En el filtro, se descartan 1, 3, 21. Se admiten 2 (Servicios) y 22 (Concesión Servicios)
        tipus_contracte = item.get("tipus_contracte", "")
        tipo_contrato_codigo = "1" # Por defecto descarte (Suministros)
        if tipus_contracte == "Serveis":
            tipo_contrato_codigo = "2" # Apto (Servicios)
        elif tipus_contracte == "Concessió de serveis":
            tipo_contrato_codigo = "22" # Apto (Concesión Servicios)
        elif tipus_contracte == "Obres":
            tipo_contrato_codigo = "3"
        
        # CPVs (Socrata: 'codi_cpv' ej '71356200-0')
        cpvs = []
        cpv_raw = item.get("codi_cpv")
        if cpv_raw:
            cpv_clean = cpv_raw.split("-")[0].strip()
            cpvs.append(cpv_clean)
            
        # Mapeo de Procedimiento (1 = Abierto, 9 = Abierto Simplificado, 100 = Abierto Súper Simplificado)
        procediment = item.get("procediment", "")
        procedimiento_codigo = "N/A"
        if procediment == "Obert":
            procedimiento_codigo = "1"
        elif procediment == "Obert simplificat":
            procedimiento_codigo = "9"
        elif procediment == "Obert simplificat abreujat":
            procedimiento_codigo = "100"
            
        # NUTS Geográfico
        country_subentity_code = item.get("codi_nuts", "")
        
        # Localidad
        localidad = item.get("lloc_execucio") or "Cataluña"
        
        # Detección de Subrogación y Revisión en textos
        subrogacion_detectada = False
        for text in [titulo, item.get("objecte_contracte", ""), item.get("nom_organ", "")]:
            if text and "subrogac" in text.lower():
                subrogacion_detectada = True
                break
                
        revision_precios_detectada = False
        for text in [titulo, item.get("objecte_contracte", "")]:
            if text and "revisio" in text.lower():
                revision_precios_detectada = True
                break

        # Urgencia
        urgente = False
        tramitacio = item.get("tramitacio", "")
        if tramitacio and "urgent" in tramitacio.lower():
            urgente = True
            
        # Loteado
        loteado = False
        lots = item.get("lots_licitacio")
        if lots and "si" in lots.lower():
            loteado = True
        elif item.get("pressupost_licitacio_sense") and item.get("pressupost_licitacio_sense_1"):
            try:
                lot_imp = float(item.get("pressupost_licitacio_sense"))
                exp_imp = float(item.get("pressupost_licitacio_sense_1"))
                if lot_imp != exp_imp:
                    loteado = True
            except ValueError:
                pass
        
        # Obtener documentos asociados de Catalunya
        documentos = self._fetch_documentos_catalunya(link)
        
        return {
            "id": expediente,
            "titulo": titulo,
            "organo": organo,
            "importe": importe,
            "estado": estado,
            "fecha_publicacion": fecha_publicacion,
            "fecha_limite": fecha_limite,
            "link": link,
            "fuente": source_name,
            "tipo_contrato_codigo": tipo_contrato_codigo,
            "cpvs": cpvs,
            "procedimiento_codigo": procedimiento_codigo,
            "country_subentity_code": country_subentity_code,
            "localidad": localidad,
            "vec": vec,
            "subrogacion_detectada": subrogacion_detectada,
            "revision_precios_detectada": revision_precios_detectada,
            "urgente": urgente,
            "loteado": loteado,
            "documentos": documentos
        }

    def _fetch_documentos_catalunya(self, link: str) -> List[Dict[str, Any]]:
        """
        Consulta la API de detalles de la PSCP de Catalunya para obtener y resolver
        los documentos adjuntos de la licitación de forma robusta con reintentos exponenciales.
        """
        if not link:
            return []
            
        # Extraer UUID e idDoc del enlace
        # Formatos posibles: detall-publicacio/UUID/ID_DOC
        match = re.search(r"detall-publicacio/([a-f0-9\-]+)/(\d+)", link)
        if not match:
            return []
            
        uuid, id_doc = match.groups()
        api_url = f"https://contractaciopublica.cat/portal-api/detall-publicacio-expedient/{uuid}/{id_doc}"
        
        documentos = []
        max_reintentos = 3
        backoff = 1.0
        
        for intento in range(max_reintentos):
            try:
                response = requests.get(api_url, headers=self.headers, timeout=15)
                
                # Manejar limitación de tasa (429)
                if response.status_code == 429:
                    print(f"[!] [radar] Límite de tasa (429) al consultar {uuid}. Esperando {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                    
                if response.status_code == 200:
                    data = response.json()
                    dades_pub = data.get("dades", {}).get("publicacio", {}).get("dadesPublicacio", {})
                    
                    # 1. Plecs Administrativos (PCA)
                    pca_list = dades_pub.get("plecsDeClausulesAdministratives", {}).get("docs", []) or []
                    for doc in pca_list:
                        if doc.get("id") and doc.get("hash"):
                            documentos.append({
                                "titulo": doc.get("titol", "Plec de clàusules administratives"),
                                "url": f"https://contractaciopublica.cat/portal-api/descarrega-document/{doc['id']}/{doc['hash']}",
                                "tipo": "PCA",
                                "hash": doc["hash"]
                            })
                            
                    # 2. Plecs Tècnics (PPT)
                    ppt_list = dades_pub.get("plecsDePrescripcionsTecniques", {}).get("docs", []) or []
                    for doc in ppt_list:
                        if doc.get("id") and doc.get("hash"):
                            documentos.append({
                                "titulo": doc.get("titol", "Plec de prescripcions tècniques"),
                                "url": f"https://contractaciopublica.cat/portal-api/descarrega-document/{doc['id']}/{doc['hash']}",
                                "tipo": "PPT",
                                "hash": doc["hash"]
                            })
                            
                    # 3. Altres Documents (Anexos)
                    altres_list = dades_pub.get("altresDocuments", {}).get("docs", []) or []
                    for doc in altres_list:
                        if doc.get("id") and doc.get("hash"):
                            documentos.append({
                                "titulo": doc.get("titol", "Annex"),
                                "url": f"https://contractaciopublica.cat/portal-api/descarrega-document/{doc['id']}/{doc['hash']}",
                                "tipo": "Anexo",
                                "hash": doc["hash"]
                            })
                            
                    # 4. Memòria Justificativa (Otros)
                    memoria_list = dades_pub.get("memoriaJustificativaContracte", {}).get("docs", []) or []
                    for doc in memoria_list:
                        if doc.get("id") and doc.get("hash"):
                            documentos.append({
                                "titulo": doc.get("titol", "Memòria justificativa"),
                                "url": f"https://contractaciopublica.cat/portal-api/descarrega-document/{doc['id']}/{doc['hash']}",
                                "tipo": "Otro",
                                "hash": doc["hash"]
                            })

                    # 5. Documents Aprovació (Otros)
                    aprovacio_list = dades_pub.get("documentsAprovacio", {}).get("docs", []) or []
                    for doc in aprovacio_list:
                        if doc.get("id") and doc.get("hash"):
                            documentos.append({
                                "titulo": doc.get("titol", "Document d'aprovació"),
                                "url": f"https://contractaciopublica.cat/portal-api/descarrega-document/{doc['id']}/{doc['hash']}",
                                "tipo": "Otro",
                                "hash": doc["hash"]
                            })
                            
                    return documentos
                else:
                    print(f"[!] [radar] Error HTTP {response.status_code} al consultar detalles de Catalunya para {uuid}.")
                    break
                    
            except requests.RequestException as e:
                print(f"[!] [radar] Error de red en intento {intento+1} al consultar detalles para {uuid}: {e}")
                if intento < max_reintentos - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    
        return []

    def ejecutar(self) -> List[Dict[str, Any]]:
        todas_licitaciones = []
        for fuente in self.fuentes:
            if fuente.get("activo", True):
                url = fuente.get("url", "")
                if url.endswith(".json"):
                    licitaciones = self.fetch_socrata_api(fuente)
                else:
                    licitaciones = self.fetch_feed(fuente)
                todas_licitaciones.extend(licitaciones)
        
        todas_licitaciones.sort(key=lambda x: x.get("fecha_publicacion", ""), reverse=True)
        return todas_licitaciones
