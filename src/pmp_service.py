"""
src/pmp_service.py — Servicio de Consulta del Periodo Medio de Pago (PMP) por Municipio
Ecosistema Automático de Licitaciones (bfr_incoop)
"""

import os
import csv
import re
from typing import Dict, Any, Tuple

from src import ruta_proyecto

class PMPService:
    """
    Servicio de consulta y evaluación del Periodo Medio de Pago a Proveedores (PMP).
    Cruza datos con config/pmp_ayuntamientos.csv y calcula penalizaciones de riesgo financiero.
    """

    def __init__(self, csv_path: str = "config/pmp_ayuntamientos.csv"):
        self.csv_path = ruta_proyecto(csv_path)
        self.pmp_data: Dict[str, int] = {}
        self.default_pmp: int = 30
        self.cargar_datos()

    def _normalizar_nombre(self, texto: str) -> str:
        """
        Normaliza el nombre de un municipio u órgano de contratación para matching flexible.
        Ej: "Ajuntament de Badalona" -> "badalona"
        """
        if not texto:
            return ""
        
        txt = texto.lower().strip()
        # Eliminar prefijos institucionales comunes
        prefijos = [
            r"\bajuntament d'|\bajuntament de|\bajuntament del|\bajuntament de la|\bajuntament des|\bajuntament\b",
            r"\bayuntamiento de|\bayuntamiento del|\bayuntamiento de la|\bayuntamiento\b",
            r"\bconsorci d'|\bconsorci de|\bconsorci del|\bconsorci\b",
            r"\bdiputació de|\bdiputació del|\bdiputacio de|\bdiputacio\b",
            r"\bdiputación de|\bdiputación del|\bdiputacion\b",
            r"\bconsell comarcal d'|\bconsell comarcal de|\bconsell comarcal del|\bconsell comarcal\b"
        ]
        for pat in prefijos:
            txt = re.sub(pat, "", txt).strip()

        # Eliminar acentos y caracteres especiales
        replacements = {
            "à": "a", "á": "a", "è": "e", "é": "e", "í": "i", "ï": "i",
            "ò": "o", "ó": "o", "ú": "u", "ü": "u", "ç": "c"
        }
        for orig, dest in replacements.items():
            txt = txt.replace(orig, dest)

        # Limpiar espacios múltiples y puntuación
        txt = re.sub(r"[^\w\s]", "", txt)
        return re.sub(r"\s+", " ", txt).strip()

    def cargar_datos(self) -> None:
        """
        Carga el mapa de PMP desde el archivo CSV configurado.
        """
        if not os.path.exists(self.csv_path):
            self.pmp_data = {}
            return

        try:
            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=";")
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 2:
                        raw_nombre = row[0].strip()
                        try:
                            pmp_val = int(row[1].strip())
                        except ValueError:
                            continue

                        norm_nombre = self._normalizar_nombre(raw_nombre)
                        if norm_nombre == "default":
                            self.default_pmp = pmp_val
                        elif norm_nombre:
                            self.pmp_data[norm_nombre] = pmp_val
        except Exception as e:
            print(f"[!] Advertencia al cargar datos PMP desde {self.csv_path}: {e}")

    def obtener_pmp(self, municipio_u_organo: str) -> int:
        """
        Devuelve los días de PMP para un municipio u órgano emisor.
        """
        if not municipio_u_organo:
            return self.default_pmp

        norm = self._normalizar_nombre(municipio_u_organo)
        
        # Búsqueda exacta por coincidencia normalizada
        if norm in self.pmp_data:
            return self.pmp_data[norm]

        # Búsqueda parcial si el nombre contiene alguna clave del mapa
        for clave, pmp in self.pmp_data.items():
            if len(clave) > 3 and (clave in norm or norm in clave):
                return pmp

        return self.default_pmp

    def evaluar_riesgo_pmp(self, municipio_u_organo: str) -> Tuple[int, int, str]:
        """
        Calcula el PMP y la penalización de scoring financiero aplicable.
        Devuelve (pmp_dias, ajuste_score, clasificacion_riesgo).
        - <= 30 días: 0 pts (BAJO)
        - 31-60 días: -10 pts (MEDIO)
        - 61-90 días: -25 pts (ALTO)
        - > 90 días: -45 pts (CRITICO)
        """
        pmp_dias = self.obtener_pmp(municipio_u_organo)
        if pmp_dias <= 30:
            return (pmp_dias, 0, "BAJO")
        elif pmp_dias <= 60:
            return (pmp_dias, -10, "MEDIO")
        elif pmp_dias <= 90:
            return (pmp_dias, -25, "ALTO")
        else:
            return (pmp_dias, -45, "CRITICO")
