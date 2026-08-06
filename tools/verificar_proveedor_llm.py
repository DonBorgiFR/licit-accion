# -*- coding: utf-8 -*-
"""
tools/verificar_proveedor_llm.py — Diagnóstico del proveedor LLM contra la API real.

NO forma parte de la suite de pruebas: consume cuota real de la API. Se ejecuta a mano
cuando se cambia de modelo, se renueva la clave o el Analista empieza a degradarse.

Uso (desde la raíz del proyecto, con GEMINI_API_KEY en el entorno):

    python tools/verificar_proveedor_llm.py

Qué comprueba:
  1. Que la clave existe y tiene forma razonable — sin imprimirla nunca.
  2. Qué modelos admite realmente la cuenta (ListModels).
  3. Que el modelo configurado en config/analista_config.yaml responde.
  4. Que la respuesta supera el parseo ESTRICTO del DTO (contrato del Paso C1).
  5. El consumo real de tokens, para estimar coste por pliego.

Contexto: en la auditoría del 2026-07-27 este diagnóstico reveló que el modelo entonces
configurado (`gemini-2.0-flash`) devolvía HTTP 429 de forma sistemática — es decir, el
pipeline habría degradado el 100 % de los análisis en producción.
"""
import os
import sys
import time
import json
import re
import urllib.request
import urllib.error

sys.path.insert(0, os.getcwd())

try:
    import yaml
except ImportError:
    yaml = None

from src.analista import GeminiProvider, AnalisisSemanticoDTO, GestorPromptsLCSP

PLIEGO_MUESTRA = """
CLÀUSULA 21. SUBROGACIÓ DEL PERSONAL.
D'acord amb l'article 130 de la LCSP, l'empresa adjudicatària resta obligada a subrogar-se
en els contractes laborals del personal adscrit. La plantilla actual és de 22 treballadors/es
enquadrats en el Conveni Col·lectiu del Lleure Educatiu i Sociocultural de Catalunya.
S'adjunta com a Annex IV la relació de personal amb categoria professional, tipus de
contracte, jornada i antiguitat. El cost salarial anual estimat ascendeix a 612.000,00 euros.

CLÀUSULA 22. REVISIÓ DE PREUS.
De conformitat amb l'article 103 de la LCSP, no procedeix la revisió de preus.

CLÀUSULA 14. CRITERIS D'ADJUDICACIÓ.
A) Criteris avaluables mitjançant fórmules automàtiques: 55 punts.
B) Criteris subjectes a judici de valor: 45 punts.
"""

ESPERADO = {
    "num_trabajadores": 22,
    "coste_estimado_anual": 612000.0,
    "desglose_salarial_completo": True,
    "revision_permitida": False,
    "peso_formulas": 55,
    "peso_juicio_valor": 45,
    "riesgo": "ALTO",  # 22 trabajadores CON desglose -> tramo 21-40
}


def main() -> int:
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        print("[-] GEMINI_API_KEY no está definida en el entorno.")
        print("    En Windows:  setx GEMINI_API_KEY \"tu-clave\"   (y reabre la terminal)")
        return 1

    ocultar = lambda t: str(t).replace(clave, "<CLAVE-OCULTA>")

    print("=" * 78)
    print(" 1. FORMA DE LA CLAVE (no se muestra su contenido)")
    print("=" * 78)
    print(f"  longitud                 : {len(clave)}")
    print(f"  espacios al inicio/fin   : {clave != clave.strip()}")
    print(f"  comillas envolventes     : {clave[0] in chr(34) + chr(39) or clave[-1] in chr(34) + chr(39)}")
    print(f"  sólo caracteres de URL   : {bool(re.fullmatch(r'[A-Za-z0-9_\-]+', clave))}")

    print()
    print("=" * 78)
    print(" 2. MODELOS DISPONIBLES EN LA CUENTA")
    print("=" * 78)
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + clave
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode())
        modelos = sorted(
            m["name"].replace("models/", "")
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        )
        print(f"  clave VÁLIDA — {len(modelos)} modelos admiten generateContent")
        for n in modelos:
            print("    -", n)
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {ocultar(e.read().decode()[:300])}")
        return 1
    except Exception as e:
        print("  fallo de red:", ocultar(e))
        return 1

    # Modelo configurado en el proyecto.
    #
    # Esta lectura debe replicar EXACTAMENTE la de proveedor_llm_factory(), o el diagnóstico
    # informa sobre un modelo que el sistema no usa. Ocurrió: se leía la clave `modelo`, que
    # no existe en el fichero, la búsqueda caía en silencio al valor por defecto codificado
    # `gemini-2.0-flash`, y la herramienta llevaba desde julio confirmando un fallo 429 de un
    # modelo ya sustituido. Por eso el hallazgo H-06 parecía no cerrarse nunca.
    from src import ruta_proyecto

    cfg_path = ruta_proyecto("config/analista_config.yaml")
    modelo_cfg = "gemini-3.1-flash-lite"
    modelo_respaldo = None
    if yaml and os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        gemini_cfg = cfg.get("gemini") or {}
        modelo_cfg = gemini_cfg.get("modelo_principal") or gemini_cfg.get("modelo", modelo_cfg)
        modelo_respaldo = gemini_cfg.get("modelo_respaldo")

    print()
    print("=" * 78)
    print(f" 3. PRUEBA REAL SOBRE EL MODELO CONFIGURADO: {modelo_cfg}")
    print("=" * 78)
    if modelo_cfg not in modelos:
        print(f"  [!] AVISO: '{modelo_cfg}' no figura entre los modelos disponibles.")

    gestor = GestorPromptsLCSP()
    p_sys, p_usr, version = gestor.construir_prompt(
        texto_segmentado=PLIEGO_MUESTRA, idioma="ca", expediente_id="DIAGNOSTICO"
    )
    print(f"  versión de prompts: {version}")

    try:
        t0 = time.perf_counter()
        res = GeminiProvider(modelo=modelo_cfg, usar_schema=True).consultar(p_sys, p_usr, timeout=120)
        elapsed = time.perf_counter() - t0
    except Exception as e:
        msg = ocultar(e)
        print(f"  [-] FALLO: {msg[:200]}")
        if "429" in msg:
            print("      -> Cuota agotada o modelo sin cuota disponible en esta cuenta.")
            print("         En producción esto degradaría el 100 % de los análisis.")
        return 1

    try:
        dto = AnalisisSemanticoDTO.from_json(res["raw_response"], estricto=True)
    except Exception as e:
        print(f"  [-] Respuesta recibida pero RECHAZADA por el parseo estricto: {ocultar(e)[:200]}")
        return 1

    pt, ct = res["prompt_tokens"], res["completion_tokens"]
    print(f"  [+] OK en {elapsed:.1f}s | tokens: {pt} entrada + {ct} salida = {pt + ct}")

    print()
    print("=" * 78)
    print(" 4. EXACTITUD DE LA EXTRACCIÓN")
    print("=" * 78)
    comprobaciones = [
        ("num_trabajadores", dto.subrogacion.num_trabajadores, ESPERADO["num_trabajadores"]),
        ("coste_anual", dto.subrogacion.coste_estimado_anual, ESPERADO["coste_estimado_anual"]),
        ("desglose_completo", dto.subrogacion.desglose_salarial_completo, ESPERADO["desglose_salarial_completo"]),
        ("riesgo_subrogacion", dto.subrogacion.riesgo_evaluado, ESPERADO["riesgo"]),
        ("revision_permitida", dto.revision_precios.permitida, ESPERADO["revision_permitida"]),
        ("peso_formulas", dto.criterios.peso_precio_formulas, ESPERADO["peso_formulas"]),
        ("peso_juicio_valor", dto.criterios.peso_juicio_valor, ESPERADO["peso_juicio_valor"]),
    ]
    aciertos = 0
    for nombre, obtenido, esperado in comprobaciones:
        ok = obtenido == esperado
        aciertos += ok
        print(f"  {'OK ' if ok else 'MAL'} {nombre:22} obtenido={obtenido!r:30} esperado={esperado!r}")

    print(f"\n  Resultado: {aciertos}/{len(comprobaciones)} campos correctos")
    print(f"  modo_degradado = {dto.modo_degradado} (debe ser False)")

    # El modelo de respaldo es la única red que queda cuando el principal agota cuota. Si no
    # se comprueba, la resiliencia configurada es una suposición.
    if modelo_respaldo:
        print()
        print("=" * 78)
        print(f" 4b. MODELO DE RESPALDO: {modelo_respaldo}")
        print("=" * 78)
        try:
            t0 = time.perf_counter()
            res_b = GeminiProvider(modelo=modelo_respaldo, usar_schema=True).consultar(p_sys, p_usr, timeout=120)
            elapsed_b = time.perf_counter() - t0
            AnalisisSemanticoDTO.from_json(res_b["raw_response"], estricto=True)
            print(f"  [+] OK en {elapsed_b:.1f}s | tokens: {res_b['prompt_tokens']} + {res_b['completion_tokens']}")
        except Exception as e:
            print(f"  [-] FALLO del respaldo: {ocultar(e)[:200]}")
            print("      -> Sin red de seguridad: si el principal agota cuota, todo se degrada.")

    print()
    print("=" * 78)
    print(" 5. ESTIMACIÓN DE COSTE")
    print("=" * 78)
    print(f"  Este fragmento de prueba: {pt} tokens de entrada.")
    print("  Un pliego real, con el chunker limitando a 15.000 caracteres, ronda")
    print("  los 5.000-6.000 tokens de entrada y ~400 de salida.")
    print("  Consulta la tarifa vigente del modelo en Google AI Studio.")

    return 0 if aciertos == len(comprobaciones) else 1


if __name__ == "__main__":
    sys.exit(main())
