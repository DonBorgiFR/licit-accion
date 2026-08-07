import argparse
import sys
import time
from datetime import datetime, timezone
from src.radar import Radar
from src.filtro import Filtro
from src.memoria import Memoria
from src.lector import Lector
from src.retencion import PoliticaRetencionInvalida, cargar_politica

def print_header(title: str):
    print("=" * 115)
    print(f" {title.center(113)} ")
    print("=" * 115)

def main():
    # Parseador de argumentos de línea de comandos
    parser = argparse.ArgumentParser(description="Pipeline de Licitaciones Incoop - Capa 6: Centinela Integrado")
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta todo el pipeline sin escribir en la base de datos ni registrar logs.")
    parser.add_argument("--batch-size", type=int, default=200, help="Tamaño de lote para transacciones en BD (por defecto 200).")
    parser.add_argument("--skip-centinela", action="store_true", help="Deshabilita la ingesta y análisis de boletines oficiales (DOGC/BOPB).")
    parser.add_argument("--csv-centinela", type=str, default="data/alertas_tempranas.csv", help="Ruta de exportación del reporte comercial del Centinela.")
    args = parser.parse_args()


    print_header("RADAR DE LICITACIONES - CAPA 3: PIPELINE DE PERSISTENCIA INTEGRADO")
    if args.dry_run:
        print("[DRY RUN ACTIVO] No se realizarán escrituras físicas ni registros de ejecución en SQLite.")

    # 1. Iniciar módulo de Persistencia (La Memoria)
    db = Memoria()
    try:
        db.setup_db()
    except Exception as e:
        print(f"[-] Error crítico al inicializar la base de datos: {e}")
        sys.exit(1)

    # 2. Adquirir lock lógico de ejecución (omitido en Dry Run)
    ejecucion_id = 9999
    ejecucion_start_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if not args.dry_run:
        try:
            ejecucion_id = db.iniciar_ejecucion()
            db.registrar_log_json(run_id=ejecucion_id, action="run_start")
            print(f"[+] Lock de ejecución adquirido (ID: {ejecucion_id}).")
        except RuntimeError as e:
            print(f"[-] {e}")
            sys.exit(1)

    # 2.bis Política de retención (Capa 9, Paso 2). Se lee una sola vez por ejecución.
    #
    # Si falta o es incoherente, `politica` queda a None y **no se purga nada**: ni
    # documentos ni copias. Es la degradación segura para una operación irreversible, y
    # el contrario de la que aplican las capas de lectura. Nunca se recurre a un plazo
    # por defecto: fue así como H-18 cambió decisiones comerciales en silencio.
    politica = None
    try:
        politica = cargar_politica()
        print(f"[+] Política de retención v{politica.version}: "
              f"documentos {politica.documentos_dias} días, copias {politica.backups_dias} días.")
    except PoliticaRetencionInvalida as e_pol:
        print(f"[!] MODO DEGRADADO — no se purgará nada en esta ejecución: {e_pol}")
        if not args.dry_run:
            db.registrar_log_json(
                run_id=ejecucion_id,
                action="DEPURADOR_MODO_DEGRADADO",
                reason=f"politica_retencion_invalida: {e_pol}",
                updated_by="depurador",
            )

    ejecucion_con_exito = False
    start_run_perf = time.perf_counter()

    try:
        # 3. Ingesta desde feeds públicos (El Radar)
        radar = Radar()
        if not radar.fuentes:
            print("[-] No se encontraron fuentes configuradas en config/fuentes.yaml")
            if not args.dry_run:
                db.registrar_log_json(run_id=ejecucion_id, action="run_failed", reason="no_sources_configured")
            sys.exit(1)
            
        print(f"Fuentes cargadas: {[f['nombre'] for f in radar.fuentes if f.get('activo', True)]}\n")
        licitaciones_crudas = radar.ejecutar()
        
        # 4. Evaluación de solvencia y scoring (El Filtro)
        filtro = Filtro()
        apta_alta = []
        apta_media = []
        oportunidades_ingesta = []

        for lic in licitaciones_crudas:
            evaluacion = filtro.filtrar(lic)
            if evaluacion["apta"]:
                # Preparar para la ingesta en lote
                oportunidades_ingesta.append((lic, evaluacion))
                
                # Cargar metadatos para la salida visual por terminal
                lic_eval = lic.copy()
                lic_eval["score"] = evaluacion["score"]
                lic_eval["motivos"] = evaluacion["motivos"]
                lic_eval["prioridad"] = evaluacion["prioridad"]
                lic_eval["sector"] = evaluacion["sector_detectado"]
                lic_eval["garantia_estimada"] = evaluacion["garantia_estimada"]
                lic_eval["pmp_detectado"] = evaluacion["pmp_detectado"]
                lic_eval["ratio_prorrogas"] = evaluacion["ratio_prorrogas"]
                lic_eval["subrogacion_detectada"] = evaluacion["subrogacion_detectada"]
                lic_eval["revision_precios_detectada"] = evaluacion["revision_precios_detectada"]
                lic_eval["urgente"] = evaluacion["urgente"]
                lic_eval["loteado"] = evaluacion["loteado"]
                lic_eval["dias_restantes"] = evaluacion["dias_restantes"]
                
                if evaluacion["prioridad"] == "Alta":
                    apta_alta.append(lic_eval)
                else:
                    apta_media.append(lic_eval)

        # 5. Ingesta Batch a la Base de Datos (omitido en Dry Run)
        if oportunidades_ingesta and not args.dry_run:
            print(f"[~] Ingestando {len(oportunidades_ingesta)} oportunidades en lotes (batch_size={args.batch_size})...")
            stats = db.upsert_oportunidades_batch(oportunidades_ingesta, run_id=ejecucion_id, batch_size=args.batch_size)
            print(f"[+] Ingesta completada: Hits (Bypass): {stats['hits']} | Misses (Escritos): {stats['misses']} | Errores: {stats['errores']}.")
            
            # Ingestar documentos asociados detectados
            doc_detectados_conteo = 0
            for lic, evaluacion in oportunidades_ingesta:
                exp_id = lic.get("id")
                docs = lic.get("documentos", [])
                for doc in docs:
                    insertado = db.registrar_documento_detectado(exp_id, doc)
                    if insertado:
                        doc_detectados_conteo += 1
                        db.registrar_log_json(
                            run_id=ejecucion_id,
                            action="doc_detected",
                            expediente_id=exp_id,
                            reason=f"Titulo: {doc['titulo']} | Tipo: {doc['tipo']} | Hash: {doc['hash'][:8]}..."
                        )
            if doc_detectados_conteo > 0:
                print(f"[+] Ingestados {doc_detectados_conteo} nuevos documentos en estado DETECTADO.")
                
            # Iniciar descarga resiliente de pliegos y anexos
            print("[~] Iniciando proceso de descarga de pliegos y anexos...")
            lector = Lector(db_memoria=db, run_id=ejecucion_id)
            if lector.ejecutar_bootstrap():
                lector.ejecutar_descargas()
                # Extracción de texto nativo con PyMuPDF (Paso 4)
                print("[~] Iniciando motor de extracción de texto nativo (PyMuPDF)...")
                lector.procesar_extraccion_texto_lote()
                # Motor de OCR diferido para PDFs escaneados (Paso 5)
                print("[~] Iniciando motor de OCR diferido (Tesseract OCR)...")
                lector.procesar_ocr_diferido_lote()
                # Purga automática del peso documental según la política versionada.
                # Sin política legible no se purga: ver la carga en el paso 2.bis.
                if politica:
                    print(f"[~] Purga de peso documental (retención de {politica.documentos_dias} "
                          f"días, política v{politica.version})...")
                    lector.ejecutar_purga_obsoletos(dias_retencion=politica.documentos_dias)
                else:
                    print("[~] Purga documental omitida: sin política de retención válida.")

                # Analista IA - Extracción Semántica y Recalibración (Capa 5 Paso 8)
                print("[~] Iniciando Analista IA (Extracción Semántica con LLM / Fallback)...")
                try:
                    from src.analista import AnalistaIA
                    analista = AnalistaIA()
                    hc_analista = analista.healthcheck_analista()
                    print(f"[+] Healthcheck Analista IA: {hc_analista['status']} (Ollama: {hc_analista['ollama_status']} | Gemini: {hc_analista['gemini_status']})")
                    
                    res_lote = analista.procesar_lote_pendientes(memoria=db, run_id=ejecucion_id)
                    print(f"[+] Lote Analista IA completado: Total pendientes: {res_lote['total_pendientes']} | Éxito: {res_lote['procesados_exito']} | Diferidos/Degradados: {res_lote['procesados_degradados']} | CSV: {res_lote['reporte_csv_path']}.")
                except Exception as e_an:
                    print(f"[!] Advertencia al procesar lote de Analista IA: {e_an}")
            else:
                print("[-] No se pudo inicializar el entorno documental para las descargas.")
        
        # 5.5 Ejecución de Capa 6: El Centinela de Boletines (DOGC/BOPB)
        if not args.skip_centinela and not args.dry_run:
            print("\n[~] Iniciando Capa 6: El Centinela de Boletines Oficiales (DOGC/BOPB)...")
            try:
                from src.centinela import (
                    IngestorBoletines,
                    FiltroBoletinesReglas,
                    AnalistaBoletinesIA,
                    EvaluadorScoringCentinela,
                    ejecutar_pipeline_centinela_resiliente,
                    exportar_reporte_centinela_csv
                )

                ing_cent = IngestorBoletines()
                fil_cent = FiltroBoletinesReglas()
                ana_cent = AnalistaBoletinesIA()
                eval_cent = EvaluadorScoringCentinela()

                alertas_cent, met_cent = ejecutar_pipeline_centinela_resiliente(
                    ingestor=ing_cent,
                    filtro=fil_cent,
                    analista=ana_cent,
                    evaluador=eval_cent,
                    db_path=db.db_path
                )

                csv_cent_path = exportar_reporte_centinela_csv(db_path=db.db_path, output_csv=args.csv_centinela)
                print(f"[+] Centinela completado: Ingresadas: {met_cent['ingresadas']} | Aceptadas: {met_cent['aceptadas_filtro']} | Alta Prio: {met_cent['alta_prioridad']} | CSV: {csv_cent_path}\n")
            except Exception as e_cent:
                print(f"[!] Advertencia al ejecutar Capa 6 (Centinela): {e_cent}")

        # 6. Soft Delete de expedientes obsoletos (omitido en Dry Run)

        if not args.dry_run:
            print("[~] Ejecutando Soft Delete de expedientes ausentes en el feed...")
            db.soft_delete_obsoletos(ejecucion_start_utc)
            print("[+] Proceso de Soft Delete finalizado.")

        # 7. Backup transaccional en caliente y rotación (omitido en Dry Run)
        if not args.dry_run:
            print("[~] Realizando copia de seguridad en caliente de la base de datos...")
            try:
                backup_file = db.realizar_backup(run_id=ejecucion_id)
                print(f"[+] Backup en caliente generado con éxito: {backup_file}")
                
                if politica:
                    purgados = db.rotar_backups(dias_retencion=politica.backups_dias)
                    if purgados > 0:
                        print(f"[+] Rotación de backups: Se han eliminado {purgados} copias obsoletas "
                              f"(retención de {politica.backups_dias} días, política v{politica.version}).")
                else:
                    print("[~] Rotación de copias omitida: sin política de retención válida.")
            except Exception as e_bak:
                print(f"[!] Advertencia: No se pudo completar el backup de seguridad: {e_bak}")

        # --- RENDER TERMINAL ---
        print("\n" + "=" * 115)
        print(f" RESUMEN DEL PIPELINE Y PERSISTENCIA ".center(115, "-"))
        print(f"Total de licitaciones crudas analizadas: {len(licitaciones_crudas)}")
        print(f"Licitaciones de PRIORIDAD ALTA (Aptas): {len(apta_alta)}")
        print(f"Licitaciones de PRIORIDAD MEDIA (Revisar): {len(apta_media)}")
        print("=" * 115 + "\n")

        col_format = "{:<16} | {:<5} | {:<12} | {:<22} | {:<14} | {:<32}"
        
        # Prioridad Alta
        if apta_alta:
            print(f" [APTA - PRIORIDAD ALTA (Core Incoop)] ".center(115, "*"))
            print(col_format.format("Expediente", "Score", "Sector", "Organo de Contratacion", "Importe base", "Titulo / Motivos"))
            print("-" * 115)
            for lic in apta_alta:
                exp = lic["id"][:16]
                score_str = f"{lic['score']} pts"
                sector = lic["sector"][:12]
                organo = lic["organo"][:22]
                importe_str = f"{lic['importe']:,.2f} EUR"
                titulo = lic["titulo"][:32]
                
                organo = "".join(c if ord(c) < 128 else "?" for c in organo)
                titulo = "".join(c if ord(c) < 128 else "?" for c in titulo)
                
                print(col_format.format(exp, score_str, sector, organo, importe_str, titulo))
                print(f"   -> Motivos: {', '.join(lic['motivos'])}")
                print(f"   -> Financiero: VEC: {lic.get('vec', 0.0):,.2f} EUR (Ratio VEC/PBL: {lic['ratio_prorrogas']:.1f}) | Aval (5%): {lic['garantia_estimada']:,.2f} EUR | PMP: {lic['pmp_detectado']} días")
                print(f"   -> Operativo:  Loteado: {'Sí' if lic['loteado'] else 'No'} | Urgente: {'Sí' if lic['urgente'] else 'No'} (Días rest.: {lic['dias_restantes'] if lic['dias_restantes'] != 99 else 'N/A'}) | Subrogación: {'SÍ ⚠️' if lic['subrogacion_detectada'] else 'No'} | Revisión Precios: {'Sí' if lic['revision_precios_detectada'] else 'No'}")
                print("-" * 115)
            print("\n")

        # Prioridad Media
        if apta_media:
            print(f" [REVISAR - PRIORIDAD MEDIA (Servicios afines)] ".center(115, "*"))
            print(col_format.format("Expediente", "Score", "Sector", "Organo de Contratacion", "Importe base", "Titulo / Motivos"))
            print("-" * 115)
            for lic in apta_media:
                exp = lic["id"][:16]
                score_str = f"{lic['score']} pts"
                sector = lic["sector"][:12]
                organo = lic["organo"][:22]
                importe_str = f"{lic['importe']:,.2f} EUR"
                titulo = lic["titulo"][:32]
                
                organo = "".join(c if ord(c) < 128 else "?" for c in organo)
                titulo = "".join(c if ord(c) < 128 else "?" for c in titulo)
                
                print(col_format.format(exp, score_str, sector, organo, importe_str, titulo))
                print(f"   -> Motivos: {', '.join(lic['motivos'])}")
                print(f"   -> Financiero: VEC: {lic.get('vec', 0.0):,.2f} EUR (Ratio VEC/PBL: {lic['ratio_prorrogas']:.1f}) | Aval (5%): {lic['garantia_estimada']:,.2f} EUR | PMP: {lic['pmp_detectado']} días")
                print(f"   -> Operativo:  Loteado: {'Sí' if lic['loteado'] else 'No'} | Urgente: {'Sí' if lic['urgente'] else 'No'} (Días rest.: {lic['dias_restantes'] if lic['dias_restantes'] != 99 else 'N/A'}) | Subrogación: {'SÍ ⚠️' if lic['subrogacion_detectada'] else 'No'} | Revisión Precios: {'Sí' if lic['revision_precios_detectada'] else 'No'}")
                print("-" * 115)
            print("\n")

        if not apta_alta and not apta_media:
            print("No se encontraron licitaciones aptas o a revisar en el dia de hoy.")

        ejecucion_con_exito = True

    except Exception as e:
        print(f"[-] Ocurrió un error inesperado durante el pipeline: {e}")
        ejecucion_con_exito = False

    finally:
        total_duration_ms = int((time.perf_counter() - start_run_perf) * 1000)
        
        # Liberar Lock y registrar fin (omitido en Dry Run)
        if not args.dry_run:
            db.registrar_log_json(
                run_id=ejecucion_id, action="run_end", 
                reason="success" if ejecucion_con_exito else "failed",
                duration_ms=total_duration_ms
            )
            db.finalizar_ejecucion(ejecucion_id, exito=ejecucion_con_exito)
            print(f"[+] Lock de ejecución liberado (ID: {ejecucion_id}).")

        print(f"\n[OK] Pipeline finalizado. Duración total: {total_duration_ms/1000:.2f} segundos.")

if __name__ == "__main__":
    main()
