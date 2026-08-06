# -*- coding: utf-8 -*-
"""
tools/verificar_matriz_subrogacion.py — Determinismo de la matriz de riesgo LCSP.

NO forma parte de la suite: consume cuota real. Se ejecuta a mano cada vez que se toca
la matriz de `config/prompts_lcsp.yaml` o se cambia de modelo LLM.

Uso (desde la raíz del proyecto, con GEMINI_API_KEY en el entorno):

    python tools/verificar_matriz_subrogacion.py

Qué verifica: que dos modelos DISTINTOS asignan el MISMO nivel de riesgo al mismo pliego.
Si discrepan, la matriz tiene un hueco y el sistema deja de ser determinista.

Contexto: la matriz v1 no cubría el caso "más de 15 trabajadores CON desglose salarial".
Cada modelo improvisaba (ALTO frente a MEDIO), lo que suponía 15 puntos de diferencia en
el scoring comercial del mismo expediente. La matriz v2 cierra los siete tramos y esta
herramienta es lo que impide que el hueco vuelva sin que nadie se entere.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

from src.analista import GeminiProvider, AnalisisSemanticoDTO, GestorPromptsLCSP

# Modelos de familias distintas: si ambos coinciden, la regla es del prompt, no del modelo.
MODELOS = ["gemini-3.1-flash-lite", "gemini-3.6-flash"]

# (nombre, texto, riesgo esperado, subrogación detectada esperada)
CASOS = [
    (
        "22 trabajadores CON desglose (tramo 21-40)",
        """CLÀUSULA 21. SUBROGACIÓ. La plantilla és de 22 treballadors/es del Conveni del
        Lleure Educatiu. S'adjunta Annex IV amb categoria professional, tipus de contracte,
        jornada i antiguitat. Cost salarial anual: 612.000,00 euros.
        CRITERIS: fórmules automàtiques 55 punts; judici de valor 45 punts.""",
        "ALTO", True,
    ),
    (
        "6 trabajadores SIN desglose (Art. 130.1 incumplido)",
        """CLÁUSULA 9. SUBROGACIÓN. Deberá subrogarse el personal adscrito, 6 trabajadores.
        El licitador recabará por sus medios la información laboral que precise.
        CRITERIOS: Precio 70, Memoria 30.""",
        "CRITICO", True,
    ),
    (
        "Negación explícita de subrogación",
        """CLÀUSULA 18. No procedeix la subrogació de personal en el present contracte.
        CRITERIS: Oferta econòmica 50, Projecte 50.""",
        "BAJO", False,
    ),
    (
        "3 trabajadores CON desglose (tramo 1-5)",
        """CLÁUSULA 7. SUBROGACIÓN. Plantilla de 3 trabajadores. Se adjunta Anexo II con
        categoría, jornada y antigüedad de cada uno. Convenio de Ocio Educativo.
        CRITERIOS: Precio 40, Proyecto 60.""",
        "BAJO", True,
    ),
    (
        "45 trabajadores CON desglose (por encima de 40)",
        """CLÁUSULA 11. SUBROGACIÓN. Plantilla de 45 trabajadores. Se adjunta Anexo V con
        categoría profesional, tipo de contrato, jornada y antigüedad.
        CRITERIOS: Precio 50, Proyecto 50.""",
        "CRITICO", True,
    ),
]


def main() -> int:
    clave = os.getenv("GEMINI_API_KEY")
    if not clave:
        print("[-] GEMINI_API_KEY no está definida en el entorno.")
        return 1
    ocultar = lambda t: str(t).replace(clave, "<CLAVE-OCULTA>")

    gestor = GestorPromptsLCSP()
    print(f"Versión de prompts cargada: {gestor.version}")
    print(f"Modelos comparados: {', '.join(MODELOS)}")
    print()
    print(f"{'caso':52} {'esperado':9} " + " ".join(f"{m:24}" for m in MODELOS) + "  veredicto")
    print("-" * 140)

    correctos = 0
    for nombre, texto, riesgo_esp, det_esp in CASOS:
        p_sys, p_usr, _ = gestor.construir_prompt(
            texto_segmentado=texto, idioma="ca", expediente_id="MATRIZ"
        )
        resultados = []
        for modelo in MODELOS:
            try:
                res = GeminiProvider(modelo=modelo, usar_schema=True).consultar(p_sys, p_usr, timeout=120)
                dto = AnalisisSemanticoDTO.from_json(res["raw_response"], estricto=True)
                resultados.append((dto.subrogacion.riesgo_evaluado, dto.subrogacion.detectada))
            except Exception as e:
                resultados.append((f"ERR:{ocultar(e)[:10]}", None))

        coinciden = len({r for r, _ in resultados}) == 1
        acierta = all(r == riesgo_esp and d == det_esp for r, d in resultados)
        correctos += 1 if (coinciden and acierta) else 0

        celdas = " ".join(f"{r:>8}/det={str(d):5}    " for r, d in resultados)
        veredicto = "OK" if (coinciden and acierta) else ("DISCREPAN" if not coinciden else "INCORRECTO")
        print(f"{nombre:52} {riesgo_esp:9} {celdas}  {veredicto}")

    print("-" * 140)
    print(f"Casos deterministas y correctos: {correctos}/{len(CASOS)}")
    if correctos != len(CASOS):
        print("\n[!] La matriz de config/prompts_lcsp.yaml tiene huecos o reglas ambiguas.")
        print("    Un mismo pliego puede recibir puntuaciones comerciales distintas.")
    return 0 if correctos == len(CASOS) else 1


if __name__ == "__main__":
    sys.exit(main())
