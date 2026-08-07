import os
import re
import yaml
import unicodedata
from datetime import datetime
from typing import List, Dict, Any

from src import ruta_proyecto

class Filtro:
    def __init__(self, config_dir: str = "config"):
        # Ver Radar.__init__: la misma licitación puntuaba 71 desde la raíz y 47 desde
        # otro directorio porque el perfil de Incoop no llegaba a cargarse.
        self.config_dir = ruta_proyecto(config_dir)
        self.perfil = self._load_yaml("perfil_incoop.yaml").get("perfil", {})

        # Contrato de scoring v2. La capa 2 publica exclusivamente la escala canónica
        # [0, 100]; las ponderaciones internas sólo sirven para explicar el resultado.
        scoring = self.perfil.get("scoring", {})
        # Versión del contrato de scoring, publicada en cada evaluación y persistida junto
        # al lote (esquema v6). Hasta ahora se declaraba en el perfil pero no la leía nadie:
        # dos generaciones de puntuación podían convivir en la misma tabla sin nada que las
        # distinguiera, que es por lo que hubo que tirar los datos de la beta (Paso D10).
        self.version_scoring = str(scoring.get("version", "desconocida"))
        self.maximo_score_bruto = float(scoring.get("maximo_bruto", 170.0))
        self.umbral_alta = float(scoring.get("umbral_alta", 65.0))
        self.umbral_media = float(scoring.get("umbral_media", 40.0))
        
        # Parámetros del presupuesto
        presupuesto = self.perfil.get("presupuesto", {})
        self.min_presupuesto = presupuesto.get("minimo", 100000.00)
        self.max_presupuesto = presupuesto.get("maximo", 2000000.00)
        
        # Filtros duros
        self.exclusiones = self.perfil.get("exclusiones", [])
        
        # Cargar parámetros de Scoring
        self.palabras_alerta = self.perfil.get("palabras_alerta", [])
        self.organos_afines = self.perfil.get("organos_afines", [])
        self.palabras_positivas_nucleo = self.perfil.get("palabras_positivas_nucleo", [])
        self.palabras_positivas_secundarias = self.perfil.get("palabras_positivas_secundarias", [])
        
        geo = self.perfil.get("geografia_catalunya", {})
        self.provincias_prefijos = geo.get("provincias_prefijos", [])
        self.nuts_barcelona = geo.get("nuts_barcelona_metropolita", ["ES511"])
        self.nuts_resto_catalunya = geo.get("nuts_resto_catalunya", ["ES51", "ES512", "ES513", "ES514"])
        self.ciudades_barcelona = geo.get("ciudades_barcelona_alrededores", [])
        self.ciudades_resto = geo.get("ciudades_resto_catalunya", [])
        # Retrocompatibilidad
        self.nuts_catalunya = self.nuts_barcelona + self.nuts_resto_catalunya
        self.ciudades_clave = self.ciudades_barcelona + self.ciudades_resto
        
        # Presencia Histórica y Operativa Directa de Incoop (+40 pts)
        presencia = self.perfil.get("presencia_historica_incoop", {})
        self.municipios_historicos = presencia.get("municipios", [])
        self.barrios_barcelona = presencia.get("barrios_distritos_barcelona", [])
        self.comarcas_core = presencia.get("comarcas_core", [])
        self.loc_historicas_norm = [
            self._normalizar_texto(loc) for loc in (self.municipios_historicos + self.barrios_barcelona) if loc
        ]
        
        # Mapas de sectorización por CPV, en tres niveles de especificidad decreciente.
        #
        # Antes existía un único conjunto por sector que mezclaba prefijos de 3 y 5 dígitos,
        # y la asignación se quedaba con el primer sector del YAML que casara cualquiera de
        # los dos. Consecuencia (H-26): "educativo" contiene "85312110" —guarderías escolares
        # sociales—, cuyo prefijo 853 es la rama de asistencia social del CPV, así que se
        # llevaba los siete CPVs del sector "social" y ese sector no se asignaba jamás.
        # No alteraba el score, pero sí el sector que se persiste en la base de datos.
        sectores_cpv = self.perfil.get("sectores_cpv", {})
        self.cpv_exacto: Dict[str, List[str]] = {}
        self.cpv_prefijo5: Dict[str, List[str]] = {}
        self.cpv_prefijo3: Dict[str, List[str]] = {}
        for sector, cpv_list in sectores_cpv.items():
            for cpv in cpv_list:
                s = str(cpv).strip()
                for indice, clave in ((self.cpv_exacto, s),
                                      (self.cpv_prefijo5, s[:5]),
                                      (self.cpv_prefijo3, s[:3])):
                    reclamantes = indice.setdefault(clave, [])
                    if sector not in reclamantes:
                        reclamantes.append(sector)

        # Prelación explícita entre sectores para los empates dentro de un mismo nivel.
        # Sin ella el desempate lo decidía el orden en que estuvieran escritas las claves de
        # sectores_cpv: un criterio que nadie eligió y que no se ve al leer el fichero.
        # Un sector no declarado en la prelación se ordena detrás, en el orden del YAML.
        prelacion = self.perfil.get("prelacion_sectores", [])
        self.prelacion_sectores = [s for s in prelacion if s in sectores_cpv]
        self.prelacion_sectores += [s for s in sectores_cpv if s not in self.prelacion_sectores]

        # Códigos de procedimientos admisibles (CODICE)
        self.procedimientos_preferentes = {'1', '9', '100'}

        # Cargar base de datos PMP
        self.pmp_map = self._load_pmp("pmp_ayuntamientos.csv")

    def _load_pmp(self, filename: str) -> Dict[str, int]:
        path = os.path.join(self.config_dir, filename)
        pmp_map = {}
        if not os.path.exists(path):
            return pmp_map
        try:
            with open(path, "r", encoding="utf-8") as f:
                next(f) # Saltar cabecera
                for line in f:
                    parts = line.strip().split(";")
                    if len(parts) >= 2:
                        pmp_map[parts[0].lower().strip()] = int(parts[1].strip())
            return pmp_map
        except Exception as e:
            print(f"Error cargando PMP {filename}: {e}")
            return pmp_map

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

    def _resolver_sector_cpv(self, cpv: str):
        """Determina a qué sector del perfil pertenece un CPV.

        Devuelve la tupla ``(sector, via)``, o ``(None, None)`` si el CPV no pertenece al
        perfil —en cuyo caso el scoring cae a la red de seguridad por división—. ``via``
        explica cómo se resolvió y viaja hasta la lista de motivos: un sector asignado debe
        poder justificarse sin releer el código.

        Se consulta de más específico a menos —código completo, prefijo de 5 y prefijo de
        3— y **un código completo gana siempre a un prefijo**, aunque ese prefijo pertenezca
        a un sector más prioritario. La prelación sólo desempata entre sectores que casan en
        el mismo nivel; jamás asciende un sector de un nivel menos específico.
        """
        if not cpv:
            return None, None
        for indice, clave, via in ((self.cpv_exacto, cpv, "código completo"),
                                   (self.cpv_prefijo5, cpv[:5], "prefijo de 5"),
                                   (self.cpv_prefijo3, cpv[:3], "prefijo de 3")):
            reclamantes = indice.get(clave)
            if not reclamantes:
                continue
            if len(reclamantes) == 1:
                return reclamantes[0], via
            ganador = min(reclamantes, key=self.prelacion_sectores.index)
            return ganador, f"{via} + prelación"
        return None, None

    def filtrar(self, licitacion: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evalúa una licitación mediante filtros duros (descarte inmediato) y blandos (scoring).
        Devuelve un diccionario con el resultado del análisis.
        """
        titulo_norm = self._normalizar_texto(licitacion.get("titulo", ""))
        organo_norm = self._normalizar_texto(licitacion.get("organo", ""))
        importe = licitacion.get("importe", 0.0)
        vec = licitacion.get("vec", 0.0)
        tipo_codigo = licitacion.get("tipo_contrato_codigo")
        estado = licitacion.get("estado", "")
        cpvs = licitacion.get("cpvs", [])
        fecha_limite_str = licitacion.get("fecha_limite", "N/A")
        proc_codigo = licitacion.get("procedimiento_codigo")
        subentity_code = licitacion.get("country_subentity_code")
        
        subrogacion_detectada = licitacion.get("subrogacion_detectada", False)
        revision_precios_detectada = licitacion.get("revision_precios_detectada", False)
        urgente = licitacion.get("urgente", False)
        loteado = licitacion.get("loteado", False)

        resultado = {
            "apta": False,
            "prioridad": "Descartada",
            "score": 0,
            "score_bruto": 0.0,
            "version_scoring": self.version_scoring,
            "motivos": [],
            "sector_detectado": "Servicios Generales",
            "garantia_estimada": 0.0,
            "pmp_detectado": 30,
            "ratio_prorrogas": 1.0,
            "subrogacion_detectada": subrogacion_detectada,
            "revision_precios_detectada": revision_precios_detectada,
            "urgente": urgente,
            "loteado": loteado,
            "dias_restantes": 99
        }

        # -------------------------------------------------------------
        # FASE 1: FILTROS DUROS (DESCARTE INMEDIATO)
        # -------------------------------------------------------------

        # 1. Estado de publicación activo (PUB)
        if estado and estado != "PUB":
            resultado["motivos"].append(f"Estado inactivo ({estado})")
            return resultado

        # 2. Fecha Límite Vigente
        if fecha_limite_str and fecha_limite_str != "N/A":
            try:
                fecha_clean = fecha_limite_str.split(".")[0]
                if len(fecha_clean) > 10:
                    fecha_limite_dt = datetime.strptime(fecha_clean, "%Y-%m-%d %H:%M:%S")
                else:
                    fecha_limite_dt = datetime.strptime(fecha_clean, "%Y-%m-%d")
                
                if fecha_limite_dt < datetime.now():
                    resultado["motivos"].append("Plazo expirado")
                    return resultado
            except Exception:
                pass

        # 3. Tipo de Contrato admisible (Servicios/Concesión Servicios)
        if tipo_codigo in ['1', '3', '21']:
            resultado["motivos"].append(f"Tipo de contrato no apto ({tipo_codigo})")
            return resultado
            
        # 4. Exclusión de Obras camufladas por CPV
        for cpv in cpvs:
            if str(cpv).startswith("45"):
                resultado["motivos"].append("CPV de Construcción (45)")
                return resultado

        # 5. Importe en rango de Incoop
        if importe < self.min_presupuesto or importe > self.max_presupuesto:
            resultado["motivos"].append(f"Importe {importe:,.2f} fuera de rango")
            return resultado

        # 6. Exclusiones evidentes por palabras clave (Duras)
        for excl in self.exclusiones:
            excl_norm = self._normalizar_texto(excl)
            if excl_norm and (excl_norm in titulo_norm or excl_norm in organo_norm):
                resultado["motivos"].append(f"Palabra excluida '{excl}'")
                return resultado

        # -------------------------------------------------------------
        # FASE 2: SISTEMA DE SCORING (FILTRO BLANDO Y PUNTUACIÓN)
        # -------------------------------------------------------------
        score = 0
        motivos = []
        sector_detectado = "Servicios Generales"

        # A. Criterio Geográfico (Presencia Histórica Directa +40 vs Foco Barcelona/Corona +35 vs Resto Catalunya +20)
        es_catalunya = False
        localidad_norm = self._normalizar_texto(licitacion.get("localidad", ""))

        # 0. Prioridad Máxima: Presencia Histórica y Operativa Directa de Incoop (+40 pts)
        for loc_norm in self.loc_historicas_norm:
            if loc_norm and (loc_norm in titulo_norm or loc_norm in organo_norm or loc_norm in localidad_norm):
                score += 40
                motivos.append(f"Presencia Histórica/Operativa Directa Incoop ({loc_norm}) +40")
                es_catalunya = True
                break

        if not es_catalunya and subentity_code:
            # 1. Comprobar NUTS Barcelona y Área Metropolitana (Prioridad Alta +35)
            for nuts in self.nuts_barcelona:
                if subentity_code.startswith(nuts):
                    score += 35
                    motivos.append(f"Geografía Núcleo Barcelona/Alrededores ({subentity_code}) +35")
                    es_catalunya = True
                    break
            
            # 2. Comprobar NUTS Resto de Catalunya (Prioridad General +20)
            if not es_catalunya:
                for nuts in self.nuts_resto_catalunya:
                    if subentity_code.startswith(nuts):
                        score += 20
                        motivos.append(f"Geografía Catalunya General NUTS ({subentity_code}) +20")
                        es_catalunya = True
                        break
        
        if not es_catalunya:
            # 3. Comprobar indicios de ciudades de Barcelona y Alrededores (+35)
            for ciudad in self.ciudades_barcelona:
                ciudad_norm = self._normalizar_texto(ciudad)
                if ciudad_norm and (ciudad_norm in titulo_norm or ciudad_norm in organo_norm or ciudad_norm in localidad_norm):
                    score += 35
                    motivos.append(f"Municipio Núcleo Barcelona/Alrededores ({ciudad}) +35")
                    es_catalunya = True
                    break
            
            # 4. Comprobar indicios de ciudades en el Resto de Catalunya (+20)
            if not es_catalunya:
                for ciudad in self.ciudades_resto:
                    ciudad_norm = self._normalizar_texto(ciudad)
                    if ciudad_norm and (ciudad_norm in titulo_norm or ciudad_norm in organo_norm or ciudad_norm in localidad_norm):
                        score += 20
                        motivos.append(f"Municipio Catalunya General ({ciudad}) +20")
                        es_catalunya = True
                        break


        # B. Criterio de Órgano de Contratación Afín
        for org in self.organos_afines:
            org_norm = self._normalizar_texto(org)
            if org_norm and org_norm in organo_norm:
                score += 20
                motivos.append(f"Órgano Afín ({org}) +20")
                break

        # C. Criterio de CPVs (Jerarquía y Sectorización)
        cpv_detectado = False
        for cpv in cpvs:
            sector, via = self._resolver_sector_cpv(str(cpv).strip())
            if sector:
                score += 40
                motivos.append(f"CPV Core Sector {sector.capitalize()} +40 (por {via})")
                sector_detectado = sector.capitalize()
                cpv_detectado = True
                break

        if not cpv_detectado:
            # Red de seguridad por división para los CPVs que no figuran en el perfil.
            # No hay rama para 853*: toda esa familia casa siempre por el índice de arriba
            # —"social" declara 85300000..85320000 y "educativo" el 85312110—, así que la
            # regla que existió aquí era código inalcanzable. Ver H-26.
            for cpv in cpvs:
                cpv_str = str(cpv).strip()
                if cpv_str.startswith("98"):
                    score += 30
                    motivos.append("División Comunitario/Asociativo (98) +30")
                    sector_detectado = "Comunitario_asociativo"
                    break
                elif cpv_str.startswith("80"):
                    score += 25
                    motivos.append("División Educación (80) +25")
                    sector_detectado = "Educativo"
                    break
                elif cpv_str.startswith("92"):
                    score += 25
                    motivos.append("División Cultural (92) +25")
                    sector_detectado = "Cultural"
                    break
                elif cpv_str.startswith("555"):
                    score += 25
                    motivos.append("División Comedores (555) +25")
                    sector_detectado = "Restauración"
                    break
                elif cpv_str.startswith("75"):
                    score += 20
                    motivos.append("División Admin. Pública/Comunidad (75) +20")
                    sector_detectado = "Consultoría"
                    break
                elif cpv_str.startswith("909") or cpv_str.startswith("507"):
                    score += 20
                    motivos.append("División Limpieza/Mant. +20")
                    sector_detectado = "Mantenimiento"
                    break
                elif cpv_str.startswith("79"):
                    score += 10
                    motivos.append("División Consultoría (79) +10")
                    sector_detectado = "Consultoría"
                    break

        # D. Criterio de Procedimiento
        if proc_codigo:
            if proc_codigo in self.procedimientos_preferentes:
                score += 10
                motivos.append("Procedimiento Preferente (Abierto/Simplif.) +10")
            else:
                score -= 15
                motivos.append(f"Procedimiento no preferente ({proc_codigo}) -15")

        # E. Palabras Clave Positivas (Título)
        for palabra in self.palabras_positivas_nucleo:
            pal_norm = self._normalizar_texto(palabra)
            if pal_norm in titulo_norm:
                score += 25
                motivos.append(f"Palabra Núcleo ({palabra}) +25")
                break

        for palabra in self.palabras_positivas_secundarias:
            pal_norm = self._normalizar_texto(palabra)
            if pal_norm in titulo_norm:
                score += 10
                motivos.append(f"Palabra Secundaria ({palabra}) +10")
                break

        # F. Penalizaciones por palabras de advertencia (Alertas)
        for pal_alerta in self.palabras_alerta:
            alerta_norm = self._normalizar_texto(pal_alerta)
            if alerta_norm in titulo_norm:
                score -= 25
                motivos.append(f"Alerta: '{pal_alerta}' -25")

        # G. Si la fecha límite no es confiable
        if fecha_limite_str == "N/A":
            score -= 10
            motivos.append("Fecha límite no definida -10")

        # H. Penalización por contrato menor de 100k (Procedimiento Simplificado)
        if importe < 100000.00:
            score -= 15
            motivos.append("Presupuesto menor de 100k EUR (Procedimiento Simplificado) -15")

        # I. Criterio de Liquidez del Órgano de Contratación (PMP)
        pmp_detectado = 30
        for ciudad, dias in self.pmp_map.items():
            if ciudad in organo_norm:
                pmp_detectado = dias
                break
                
        if pmp_detectado <= 30:
            score += 10
            motivos.append(f"Excelente rapidez de pago del Ayuntamiento ({pmp_detectado} días) +10")
        elif pmp_detectado >= 60:
            score -= 20
            motivos.append(f"Alerta: Ayuntamiento con pagos tardíos ({pmp_detectado} días) -20")

        # J. Criterio de Ratio de Prórrogas (VEC vs PBL)
        ratio_prorrogas = 1.0
        if importe > 0.0 and vec > 0.0:
            ratio_prorrogas = vec / importe
            if ratio_prorrogas >= 2.0:
                score += 15
                motivos.append(f"Contrato de larga duración / Prórrogas a largo plazo (Ratio {ratio_prorrogas:.1f}) +15")
                
        # K. Estimación de Inmovilizado por Garantía Definitiva
        garantia_estimada = importe * 0.05

        # L/M. Las menciones del feed son sólo señales de priorización documental. No se
        # penalizan: un título no permite saber si hay subrogación real ni si una revisión
        # de precios es aplicable. Esas consecuencias se calculan una única vez, con el
        # pliego, en RecalibradorScoring (Capa 5).
        if subrogacion_detectada:
            motivos.append("[SEÑAL] Posible subrogación: pendiente de verificación en pliego (sin ajuste)")
        if ratio_prorrogas >= 2.0 and not revision_precios_detectada:
            motivos.append("[SEÑAL] Revisión de precios no localizada en el feed (sin ajuste)")
            
        # N. Urgencia y Tiempo de Preparación
        dias_restantes = 99
        if fecha_limite_str and fecha_limite_str != "N/A":
            try:
                from datetime import datetime
                clean_date = fecha_limite_str.strip()
                if " " in clean_date:
                    limite_dt = datetime.strptime(clean_date.split(".")[0], "%Y-%m-%d %H:%M:%S")
                else:
                    limite_dt = datetime.strptime(clean_date, "%Y-%m-%d")
                
                delta = limite_dt - datetime.now()
                dias_restantes = delta.days
            except Exception:
                pass
                
        if urgente or (dias_restantes != 99 and dias_restantes < 5):
            if importe >= 200000.00:
                score -= 15
                motivos.append("[ALERTA] Plazo critico para tramitacion urgente / pocos dias restantes (-15)")
                
        # O. Contrato Loteado
        if loteado:
            score += 10
            motivos.append("Contrato dividido en lotes (Oportunidad de oferta parcial) (+10)")

        # -------------------------------------------------------------
        # CLASIFICACIÓN FINAL POR UMBRALES
        # -------------------------------------------------------------
        score_bruto = float(score)
        score_normalizado = round(
            max(0.0, min(100.0, (score_bruto / self.maximo_score_bruto) * 100.0))
        )
        resultado["score"] = int(score_normalizado)
        resultado["score_bruto"] = score_bruto
        resultado["motivos"] = motivos
        resultado["sector_detectado"] = sector_detectado
        resultado["garantia_estimada"] = garantia_estimada
        resultado["pmp_detectado"] = pmp_detectado
        resultado["ratio_prorrogas"] = ratio_prorrogas
        resultado["dias_restantes"] = dias_restantes

        if score_normalizado >= self.umbral_alta:
            resultado["apta"] = True
            resultado["prioridad"] = "Alta"
        elif score_normalizado >= self.umbral_media:
            resultado["apta"] = True
            resultado["prioridad"] = "Media"
        else:
            resultado["apta"] = False
            resultado["prioridad"] = "Descartada"

        return resultado
