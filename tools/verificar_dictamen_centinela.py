"""Verificación manual de H-56: ¿emite el Centinela un dictamen completo de verdad?

**Vive en `tools/` y no en la suite porque gasta cuota real** *(Convención C5)*. La suite
afirma sobre **la petición** —que se pide lo que se necesita—, que es donde vivía el defecto
y lo único comprobable sin salir a la red. Esto comprueba **la respuesta**, que es lo único
que no se puede afirmar sin llamar.

Qué se está verificando, en una frase: hasta el 2026-08-27 el proveedor obligaba a Gemini a
contestarle al Centinela con el esquema del analista de licitaciones, así que
`boletin_llm_succeeded` valía **0** desde el primer día del proyecto. Si esto pasa, deja de
valer 0.

Uso:
    python tools/verificar_dictamen_centinela.py

Requiere `GEMINI_API_KEY` en el entorno. Consume **una** llamada.
"""

import os
import sys

# La consola de Windows es cp1252: un solo carácter fuera de esa tabla aborta la impresión
# a media herramienta. Mismo blindaje que `verificar_rastro_real.py`.
sys.stdout.reconfigure(errors="replace")

# Anclaje de la raíz, como el resto de `tools/`. La Convención C1 prohíbe tocar `sys.path`
# en módulos y en pruebas; estos guiones se invocan sueltos y necesitan encontrar `src.`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analista import campos_obligatorios_de_esquema
from src.centinela import (
    ESQUEMA_OPENAPI_DICTAMEN_CENTINELA,
    AlertaBoletinDTO,
    AnalistaBoletinesIA,
    DictamenCentinelaDTO,
)

SEPARADOR = "=" * 72

ANUNCIO_DE_PRUEBA = AlertaBoletinDTO(
    fuente="BOPB",
    num_boletin="verificacion-h56",
    fecha_publicacion="2026-08-27T07:00:00Z",
    organo_emisor="Ajuntament de Terrassa",
    municipio="Terrassa",
    titulo_anuncio=(
        "Aprovació inicial del pressupost municipal 2027, amb dotació per al servei "
        "d'escoles bressol i atenció a la gent gran"
    ),
    seccion_boletin="Anuncis",
    texto_sumario=(
        "S'aprova inicialment el pressupost general per a l'exercici 2027, que inclou una "
        "partida per a la gestió del servei d'escoles bressol municipals i per al servei "
        "d'atenció domiciliària a la gent gran. Se sotmet a informació pública durant "
        "quinze dies."
    ),
    id_alerta="verificacion-h56",
)


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("[!] Falta GEMINI_API_KEY en el entorno. No se puede verificar.")
        return 2

    print(SEPARADOR)
    print("VERIFICACION DE H-56 - el dictamen del Centinela, contra el modelo real")
    print(SEPARADOR)

    # 1 · Lo que se pide. Es la mitad que la suite ya cubre; se imprime para que el
    #     informe se lea entero sin abrir el codigo.
    exigidos = set(DictamenCentinelaDTO.CAMPOS_OBLIGATORIOS)
    declarados = campos_obligatorios_de_esquema(ESQUEMA_OPENAPI_DICTAMEN_CENTINELA)
    print("\n[1] El esquema que se va a imponer")
    print(f"    obliga a devolver : {sorted(declarados)}")
    print(f"    el DTO exige      : {sorted(exigidos)}")
    print(f"    cubre lo exigido  : {'SI' if declarados >= exigidos else 'NO'}")
    if not declarados >= exigidos:
        print("\n[!] El esquema no cubre lo exigido. La llamada no se emite.")
        return 1

    # 2 · Lo que contesta. Esta es la mitad que solo se puede saber llamando.
    print("\n[2] Llamando al modelo (una peticion)...")
    analista = AnalistaBoletinesIA()
    if analista.proveedor_llm is None:
        print("[!] No se pudo construir el proveedor LLM.")
        return 1

    resultado = analista.analizar_alerta(ANUNCIO_DE_PRUEBA)
    dictamen = resultado.dictamen_ia

    print(f"\n    estado_operativo : {resultado.estado_operativo}")
    if dictamen is None:
        print("[!] No hay dictamen.")
        return 1

    print(f"    modo_degradado   : {dictamen.modo_degradado}")
    print(f"    nivel_interes    : {dictamen.nivel_interes}")
    print(f"    categoria        : {dictamen.categoria_fase_temprana}")
    print(f"    es_oportunidad   : {dictamen.es_oportunidad_temprana}")
    print(f"    resumen          : {dictamen.resumen_ejecutivo[:100]}")
    print(f"    acciones         : {dictamen.acciones_recomendadas}")
    print(f"    meses estimados  : {dictamen.estimacion_meses_hasta_licitacion}")

    print("\n" + SEPARADOR)
    ok = resultado.estado_operativo == "ANALIZADA_IA" and not dictamen.modo_degradado
    if ok:
        print("VEREDICTO: el Centinela emite un dictamen completo. H-56 reparado.")
        print("           `boletin_llm_succeeded` deja de valer 0 por primera vez.")
    else:
        print("VEREDICTO: sigue degradando. H-56 NO esta reparado.")
        print(f"           Resumen del fallo: {dictamen.resumen_ejecutivo[:200]}")
    print(SEPARADOR)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
