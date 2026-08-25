"""
tools/reconciliar_h54.py — Devolver a la base la verdad sobre los pliegos que ya no tiene.

**Qué repara.** El 2026-08-12, H-36 —purgar sobre una copia de la base borraba los ficheros de
producción— se llevó 63 pliegos de `data/documents/`. H-36 se cerró impidiendo que vuelva a
ocurrir (`_fichero_es_mio()`), y dirección decidió no recuperar los PDF. **Pero nadie reconcilió
la base**: trece días después, 63 filas seguían diciendo `PROCESADO` con su `local_path` intacto,
apuntando a ficheros que no existen. Eso es H-54.

**Qué NO hace.** No busca ficheros, no borra ninguno y no toca el disco: para cuando esto se
ejecuta, los ficheros llevan trece días fuera. Lo único que hace es que las filas dejen de
mentir.

**Por qué mide en vez de fiarse de una lista.** No lleva 63 identificadores escritos a mano: se
selecciona por la condición que define el defecto —una fila con `local_path` que no existe en
disco—, así que si alguien lo ejecuta dos veces la segunda no encuentra nada, y si el daño fuera
mayor de lo catalogado lo cubriría igual. Una lista fija habría fosilizado una medición del
2026-08-25.

**Por qué en dos tiempos y con copia previa.** Es la doctrina de la Capa 9 y no se relaja porque
la operación parezca pequeña: se mira antes de decidir, la confirmación es explícita y no tiene
valor por defecto, y **si la copia de seguridad falla no se ejecuta nada** (Regla 5).

**Decisión de dirección del 2026-08-25**: se marcan `PURGADO` **por el libro**, es decir, vaciando
también `texto_extraido`, que es una postcondición declarada del contrato de la Capa 9. Se pierden
~3 MB de texto. Se aceptó sabiéndolo: los 10 expedientes afectados ya están archivados, los 10
análisis semánticos viven en `analisis_semantico` y sobreviven, y sigue vigente la decisión del
2026-08-17 de que hasta la demo los datos son material de prueba. La alternativa —un `PURGADO`
que conservara el texto— habría producido filas que no se parecen a las que produce una purga
real, relajando una invariante del contrato desde una herramienta auxiliar.

Uso:

    python tools/reconciliar_h54.py                        # previsualiza; no toca nada
    python tools/reconciliar_h54.py --ejecutar --confirmar # escribe, con copia previa
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.memoria import Memoria  # noqa: E402
from src.retencion import cargar_politica  # noqa: E402


#: El estado terminal al que van los documentos cuyo peso ya no está. Vive en la máquina de
#: estados de la Capa 9, no se inventa aquí.
ESTADO_PURGADO = "PURGADO"


def localizar_desalineados(db: Memoria):
    """Documentos que dicen tener un fichero que no está en disco.

    Es la condición que define H-54, y se comprueba contra el sistema de ficheros en vez de
    contra una lista: medir el efecto, no fiarse de lo que se anotó una vez.
    """
    sql = """
    SELECT id, expediente_id, titulo, local_path, mida_bytes,
           LENGTH(COALESCE(texto_extraido, '')) AS chars
    FROM documentos
    WHERE local_path IS NOT NULL AND estado <> ?;
    """
    with db.conectar() as conn:
        filas = conn.execute(sql, (ESTADO_PURGADO,)).fetchall()

    desalineados = []
    for fila in filas:
        doc_id, exp_id, titulo, ruta, bytes_declarados, chars = fila
        if not os.path.exists(ruta):
            desalineados.append({
                "id": doc_id,
                "expediente_id": exp_id,
                "titulo": titulo,
                "local_path": ruta,
                "mida_bytes": bytes_declarados or 0,
                "chars": chars or 0,
            })
    return desalineados


def informar(desalineados) -> None:
    print()
    print("=" * 78)
    print("H-54 · Filas que dicen tener un pliego que no está en disco")
    print("=" * 78)

    if not desalineados:
        print("  Ninguna. La base y el disco dicen lo mismo.")
        return

    expedientes = sorted({d["expediente_id"] for d in desalineados})
    print(f"  Documentos desalineados : {len(desalineados)}")
    print(f"  Expedientes afectados   : {len(expedientes)}")
    print(f"  Bytes que declaran tener: {sum(d['mida_bytes'] for d in desalineados):,}")
    print(f"  Texto que se vaciará    : {sum(d['chars'] for d in desalineados):,} caracteres")
    print()
    print("  Los primeros, para reconocerlos:")
    for d in desalineados[:8]:
        print(f"    id {d['id']:>4} | {d['expediente_id'][:26]:<26} | {os.path.basename(d['local_path'])[:44]}")
    if len(desalineados) > 8:
        print(f"    ... y {len(desalineados) - 8} más")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcilia las filas que H-36 dejó desalineadas (H-54).")
    parser.add_argument("--ejecutar", action="store_true",
                        help="Escribe en la base. Sin esto sólo previsualiza.")
    parser.add_argument("--confirmar", action="store_true",
                        help="Confirmación explícita. Obligatoria junto a --ejecutar.")
    args = parser.parse_args()

    db = Memoria()
    politica = cargar_politica()
    version_politica = politica.version

    desalineados = localizar_desalineados(db)
    informar(desalineados)

    if not desalineados:
        return 0

    if not args.ejecutar:
        print()
        print("  Previsualización: no se ha tocado nada.")
        print("  Para ejecutarlo:  python tools/reconciliar_h54.py --ejecutar --confirmar")
        return 0

    # La confirmación no tiene valor por defecto: un `--ejecutar` a solas es "olvidé el resto",
    # no "sí, adelante".
    if not args.confirmar:
        print()
        print("  [!] Falta --confirmar. No se ha tocado nada.")
        return 2

    # Regla 5: si la copia falla, la operación no se ejecuta.
    print()
    print("  [~] Copia de seguridad previa...")
    try:
        backup = db.realizar_backup(run_id=0)
    except Exception as e:
        print(f"  [!] La copia de seguridad falló: {e}")
        print("  [!] No se ha tocado la base.")
        return 3
    print(f"  [+] Copia creada: {os.path.basename(backup)}")

    doc_ids = [d["id"] for d in desalineados]
    bytes_perdidos = sum(d["mida_bytes"] for d in desalineados)
    chars = sum(d["chars"] for d in desalineados)

    detalle = (
        f"Reconciliacion H-54: {len(doc_ids)} documentos que H-36 borro del disco el "
        f"2026-08-12 y que la base seguia declarando como PROCESADO. "
        f"bytes_ya_perdidos={bytes_perdidos} texto_vaciado_chars={chars}. "
        f"Esta operacion no libera espacio en disco: lo hizo H-36 hace trece dias."
    )

    # El hecho y su rastro, en la misma transacción: si una de las dos escrituras no llega,
    # no llega ninguna.
    with db.db_lock():
        with db.conectar() as conn:
            with conn:
                actualizados = db.marcar_documentos_como_purgados(doc_ids, conn=conn)
                db.registrar_purga(
                    tipo="DOCUMENTAL",
                    solicitada_por="reconciliacion_h54",
                    version_politica=version_politica,
                    resultado="COMPLETADA",
                    documentos_purgados=actualizados,
                    # Cero a propósito: esta operación no libera un solo byte hoy. Los bytes
                    # se fueron el 2026-08-12 y constan en el detalle. Contarlos aquí seria
                    # apuntarse una liberación que no ha ocurrido.
                    bytes_liberados=0,
                    backup_asociado=backup,
                    detalle=detalle,
                    conn=conn,
                )

    db.registrar_log_json(
        run_id=0,
        action="DEPURADOR_RECONCILIACION_H54",
        reason=detalle,
        updated_by="reconciliacion_h54",
    )

    print(f"  [+] {actualizados} documentos reconciliados a {ESTADO_PURGADO}.")

    # Medir el efecto, no dar por bueno que se ejecutó.
    restantes = localizar_desalineados(db)
    print(f"  [+] Comprobación posterior: quedan {len(restantes)} filas desalineadas.")
    return 0 if not restantes else 4


if __name__ == "__main__":
    raise SystemExit(main())
