"""Cierre de la Capa 9 — Paso 10: el ciclo de vida completo, de extremo a extremo.

Los Pasos 4 a 9 ya tienen sus regresiones, y aquí no se repiten. Lo que se prueba en este
fichero es **lo que sólo se ve mirando la capa entera**: que las tres operaciones encadenan,
que el resultado no depende de cuántas veces se ejecuten, y que lo ocurrido puede
reconstruirse después sin más evidencia que la que el sistema dejó por escrito.

Está organizado en torno a las siete propiedades que la Regla 10 exige para dar una capa por
completada —determinista, idempotente, trazable, versionada, auditable, resiliente e
integrada al pipeline—, porque "la suite pasa" no es lo mismo que "la capa está terminada".
"""

import json
import os

import pytest

from src.depurador import Depurador
from src.main import ejecutar_fase_depurador
from src.memoria import Memoria, entrada_log_cambio_estado
from src.retencion import PoliticaArchivado, PoliticaEliminacion, PoliticaRetencion

#: Vencido hace mucho más de los 60 días de archivado y de los 180 de retención documental.
FECHA_LIMITE_ANTIGUA = "2024-01-15T23:59:00Z"
FECHA_INGESTA_ANTIGUA = "2024-01-01T09:00:00Z"


@pytest.fixture
def politica():
    """Equivalente a la política real del proyecto (v1.2.0), fijada para no depender de ella."""
    return PoliticaRetencion(
        version="1.2.0",
        documentos_dias=180,
        backups_dias=7,
        archivado=PoliticaArchivado(
            dias_tras_fecha_limite=60,
            estados_archivables=("nueva", "descartada", "estudiando", "adjudicada", "perdida"),
            archivar_expediente_con_todos_sus_lotes=True,
        ),
        eliminacion=PoliticaEliminacion(dias_archivado_minimo=365),
    )


@pytest.fixture
def base(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    return memoria


def sembrar(memoria, tmp_path, exp_id, estado="Nueva", con_fichero=True, **campos):
    """Un expediente vivo, con su lote y —si procede— un pliego real en disco."""
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta, fecha_limite) "
                "VALUES (?, ?, 'Ajuntament', ?, ?);",
                (exp_id, f"Servicio de limpieza {exp_id}", FECHA_INGESTA_ANTIGUA, FECHA_LIMITE_ANTIGUA),
            )
            columnas = ", ".join(campos)
            marcadores = ", ".join("?" for _ in campos)
            conn.execute(
                f"INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo"
                f"{', ' + columnas if columnas else ''}) VALUES (?, 1, 'Lote unico', ?"
                f"{', ' + marcadores if marcadores else ''});",
                (exp_id, estado, *campos.values()),
            )

    ruta = None
    if con_fichero:
        carpeta = tmp_path / "documents" / exp_id
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = str(carpeta / "PCA.pdf")
        with open(ruta, "wb") as fichero:
            fichero.write(b"%PDF-1.4 " + b"x" * 5000)
        with memoria.conectar() as conn:
            with conn:
                conn.execute(
                    "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, "
                    "estado, local_path, texto_extraido, updated_at) VALUES (?, 'PCA.pdf', "
                    "?, 'PCA', ?, 'PROCESADO', ?, 'texto completo del pliego', ?);",
                    (exp_id, f"http://example.invalid/{exp_id}.pdf", f"h-{exp_id}", ruta,
                     FECHA_INGESTA_ANTIGUA),
                )
    return ruta


def estado_de(memoria, exp_id):
    """Foto del ciclo de vida de un expediente: dónde está y qué conserva."""
    with memoria.conectar() as conn:
        expediente = conn.execute(
            "SELECT deleted_at FROM expedientes WHERE id = ?;", (exp_id,)
        ).fetchone()
        if expediente is None:
            return {"ciclo": "ELIMINADO"}
        documento = conn.execute(
            "SELECT estado, local_path, texto_extraido FROM documentos WHERE expediente_id = ?;",
            (exp_id,),
        ).fetchone()
    return {
        "ciclo": "ARCHIVADO" if expediente[0] else "VIVO",
        "documento": documento[0] if documento else None,
        "fichero": documento[1] if documento else None,
        "texto": documento[2] if documento else None,
    }


# =======================================================================================
# El ciclo completo, en una sola narración
# =======================================================================================

def test_el_ciclo_de_vida_completo_de_una_licitacion_que_nadie_miro(base, politica, tmp_path):
    """VIVO → ARCHIVADO → documento PURGADO → ELIMINADO, comprobando cada postcondición.

    Es el recorrido que justifica la capa entera: una oportunidad entra por el feed, caduca
    sin que nadie llegue a mirarla, sale del canal principal, pierde su peso en disco y
    finalmente desaparece. En ningún momento se toca su estado comercial.
    """
    ruta_pdf = sembrar(base, tmp_path, "EXP-CICLO")
    depurador = Depurador(memoria=base, politica=politica)

    assert estado_de(base, "EXP-CICLO")["ciclo"] == "VIVO"

    # 1. Archivar: sale del canal principal, pero no se toca ni un fichero.
    depurador.archivar()
    foto = estado_de(base, "EXP-CICLO")
    assert foto["ciclo"] == "ARCHIVADO"
    assert os.path.exists(ruta_pdf), "Archivar no borra: es la operación reversible"
    assert foto["texto"], "Y tampoco vacía el texto"

    # 2. Purgar peso documental: el fichero y el texto se van, la fila se queda.
    depurador.purgar_documentos()
    foto = estado_de(base, "EXP-CICLO")
    assert foto["ciclo"] == "ARCHIVADO", "Purgar el peso no cambia el ciclo del expediente"
    assert foto["documento"] == "PURGADO"
    assert not os.path.exists(ruta_pdf)
    assert foto["texto"] is None
    with base.conectar() as conn:
        url = conn.execute(
            "SELECT url FROM documentos WHERE expediente_id='EXP-CICLO';"
        ).fetchone()[0]
    assert url, "Se sabe qué hubo y de dónde vino, aunque ya no esté"

    # 3. Eliminar: sólo posible porque nadie invirtió nada. Cuarentena ya cumplida.
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE expedientes SET deleted_at = '2024-06-01T09:00:00Z' WHERE id='EXP-CICLO';"
            )
    resultado = depurador.eliminar_expedientes(["EXP-CICLO"], confirmado=True)

    assert resultado.expedientes_eliminados == 1
    assert estado_de(base, "EXP-CICLO")["ciclo"] == "ELIMINADO"
    with base.conectar() as conn:
        huerfanos = conn.execute(
            "SELECT (SELECT COUNT(*) FROM lotes WHERE expediente_id='EXP-CICLO') + "
            "(SELECT COUNT(*) FROM documentos WHERE expediente_id='EXP-CICLO');"
        ).fetchone()[0]
    assert huerfanos == 0, "La cascada hoja→raíz no deja nada suelto"


def test_la_memoria_comercial_atraviesa_el_ciclo_entero_sin_un_rasguno(base, politica, tmp_path):
    """La promesa central de la capa, sometida a las tres operaciones seguidas.

    Un contrato adjudicado pierde sus pliegos y sale del canal principal, pero conserva
    íntegro todo lo que la cooperativa aprendió ganándolo — y **no puede eliminarse jamás**.
    """
    ruta_pdf = sembrar(
        base, tmp_path, "EXP-GANADO", estado="Adjudicada",
        importe_adjudicacion=145000.0, horas_internas_invertidas=37,
        costes_externos=1200.0, importe_garantia_retenida=7250.0,
        empresa_adjudicataria="Incoop SCCL",
    )
    depurador = Depurador(memoria=base, politica=politica)

    depurador.archivar()
    depurador.purgar_documentos()
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE expedientes SET deleted_at='2024-06-01T09:00:00Z' WHERE id='EXP-GANADO';"
            )
    resultado = depurador.eliminar_expedientes(["EXP-GANADO"], confirmado=True)

    assert not os.path.exists(ruta_pdf), "El peso sí se libera"
    assert resultado.expedientes_eliminados == 0
    assert resultado.bloqueados[0].motivo == "memoria_comercial"

    with base.conectar() as conn:
        fila = conn.execute(
            "SELECT estado_operativo, importe_adjudicacion, horas_internas_invertidas, "
            "costes_externos, importe_garantia_retenida, empresa_adjudicataria "
            "FROM lotes WHERE expediente_id='EXP-GANADO';"
        ).fetchone()
    assert fila == ("Adjudicada", 145000.0, 37, 1200.0, 7250.0, "Incoop SCCL")


def test_el_win_rate_sobrevive_a_una_purga_total(base, politica, tmp_path):
    """H-30 visto desde el cierre de capa: archivar y purgar no pueden vaciar el indicador.

    Es la comprobación que la Convención C7 exige y que ningún test unitario cubre: que
    después de pasar el Depurador entero, las vistas analíticas siguen contando lo mismo.
    """
    sembrar(base, tmp_path, "EXP-WIN", estado="Adjudicada", importe_adjudicacion=90000.0)
    sembrar(base, tmp_path, "EXP-LOSE", estado="Perdida")

    def win_rate():
        with base.conectar() as conn:
            return conn.execute(
                "SELECT SUM(ganadas), SUM(perdidas) FROM vista_win_rate;"
            ).fetchone()

    antes = win_rate()
    depurador = Depurador(memoria=base, politica=politica)
    depurador.archivar()
    depurador.purgar_documentos()

    assert win_rate() == antes, (
        "Archivar y purgar gobiernan qué se ve y cuánto pesa, nunca qué ocurrió"
    )
    assert antes == (1, 1), "Y la población de partida es la que se espera"


# =======================================================================================
# Las siete propiedades de la Regla 10
# =======================================================================================

def test_el_ciclo_entero_es_idempotente(base, politica, tmp_path):
    """Ejecutar la fase completa dos veces no cambia nada ni cuenta doble.

    Es lo que hace seguro que el pipeline corra a diario: la segunda pasada del martes no
    puede deshacer ni duplicar lo que hizo la del lunes.
    """
    sembrar(base, tmp_path, "EXP-IDEM")

    primera_arch, primera_purga = ejecutar_fase_depurador(base, politica, ejecucion_id=1)
    segunda_arch, segunda_purga = ejecutar_fase_depurador(base, politica, ejecucion_id=2)

    assert (primera_arch.lotes_archivados, primera_purga.documentos_purgados) == (1, 1)
    assert (segunda_arch.lotes_archivados, segunda_purga.documentos_purgados) == (0, 0)
    assert segunda_arch.ejecutado and segunda_purga.ejecutado, (
        "No encontrar nada que hacer es un éxito, no una degradación"
    )

    with base.conectar() as conn:
        filas_purgas = conn.execute("SELECT COUNT(*) FROM purgas;").fetchone()[0]
        borrado = conn.execute(
            "SELECT deleted_at FROM lotes WHERE expediente_id='EXP-IDEM';"
        ).fetchone()[0]
    assert filas_purgas == 2, "Sólo se audita lo que realmente ocurrió: archivado y purga"
    assert borrado, "Y el deleted_at original no se reescribe"


def test_la_fase_del_depurador_corre_aunque_la_corrida_no_ingiera_nada(base, politica, tmp_path):
    """Regresión de H-35, detectado en la auditoría de este mismo paso.

    La purga documental vivía anidada dentro del bloque de ingesta: sólo se ejecutaba los
    días en que el feed traía oportunidades nuevas y además el bootstrap del Lector tenía
    éxito. El mecanismo que impide que el disco crezca sin límite quedaba condicionado a
    algo que no tiene nada que ver con él, y un día tranquilo no purgaba nada.

    Esta prueba invoca la fase tal y como la invoca el pipeline —sin ingesta previa, sin
    Lector, sin feed— y exige que las dos operaciones ocurran igual.
    """
    ruta_pdf = sembrar(base, tmp_path, "EXP-DIA-TRANQUILO")

    res_arch, res_purga = ejecutar_fase_depurador(base, politica, ejecucion_id=1)

    assert res_arch.lotes_archivados == 1
    assert res_purga.documentos_purgados == 1
    assert not os.path.exists(ruta_pdf), "Sin ingesta nueva, el disco se libera igual"


def test_lo_ocurrido_se_reconstruye_leyendo_solo_la_auditoria(base, politica, tmp_path):
    """Auditable (Regla 10): la evidencia debe bastarse sola.

    Si para saber qué pasó hubiera que releer el código o preguntar a quien lo ejecutó, la
    capa no sería auditable. Aquí se reconstruye la corrida entera con lo que dejó escrito:
    la tabla `purgas` y `data/pipeline.jsonl`.
    """
    sembrar(base, tmp_path, "EXP-AUDIT")
    ejecutar_fase_depurador(base, politica, ejecucion_id=77)

    with base.conectar() as conn:
        registros = conn.execute(
            "SELECT tipo, solicitada_por, version_politica, resultado FROM purgas ORDER BY id;"
        ).fetchall()

    assert [r[0] for r in registros] == ["ARCHIVADO", "DOCUMENTAL"]
    assert all(r[1] == "pipeline" for r in registros), "Consta a petición de quién"
    assert all(r[2] == "1.2.0" for r in registros), "Y bajo qué versión de política"
    assert all(r[3] == "COMPLETADA" for r in registros)

    registro_jsonl = os.path.join(os.path.dirname(base.db_path), "pipeline.jsonl")
    with open(registro_jsonl, encoding="utf-8") as fichero:
        eventos = [json.loads(linea) for linea in fichero if linea.strip()]
    acciones = {e["action"] for e in eventos if str(e.get("action", "")).startswith("DEPURADOR")}

    assert {"DEPURADOR_ARCHIVADO", "DEPURADOR_PURGA_INICIADA", "DEPURADOR_PURGA_COMPLETADA"} <= acciones
    assert all(e["run_id"] == 77 for e in eventos if str(e.get("action", "")).startswith("DEPURADOR")), (
        "Cada evento queda atado a la corrida que lo produjo"
    )


def test_el_resultado_no_depende_del_orden_ni_del_momento_de_la_llamada(base, politica, tmp_path):
    """Determinista: dos bases idénticas, mismo reloj inyectado, mismo resultado.

    Sin reloj inyectable esta propiedad no sería comprobable, y una capa cuyo resultado no
    se puede reproducir no se puede auditar.
    """
    from datetime import datetime, timezone
    momento = datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc)

    sembrar(base, tmp_path, "EXP-DET-A")
    sembrar(base, tmp_path, "EXP-DET-B", estado="Estudiando")

    primera = Depurador(memoria=base, politica=politica).archivar(ahora=momento)

    with base.conectar() as conn:
        with conn:
            conn.execute("UPDATE lotes SET deleted_at = NULL, rescatado_at = NULL;")
            conn.execute("UPDATE expedientes SET deleted_at = NULL, rescatado_at = NULL;")

    segunda = Depurador(memoria=base, politica=politica).archivar(ahora=momento)

    assert primera.lotes_archivados == segunda.lotes_archivados == 2
    assert primera.corte_utc == segunda.corte_utc
    assert primera.por_motivo == segunda.por_motivo


def test_sin_politica_la_capa_entera_se_detiene_sin_hacer_daño(base, tmp_path):
    """Resiliente (Regla 5): en una operación irreversible, la degradación correcta es no actuar.

    Ninguna de las tres operaciones puede inventarse un plazo. Y las tres deben ser
    distinguibles de "no había nada que hacer", que es lo que la Convención C2 exige.
    """
    ruta_pdf = sembrar(base, tmp_path, "EXP-SIN-POLITICA")

    res_arch, res_purga = ejecutar_fase_depurador(base, politica=None, ejecucion_id=1)
    eliminacion = Depurador(memoria=base, politica=None).eliminar_expedientes(
        ["EXP-SIN-POLITICA"], confirmado=True
    )

    for resultado in (res_arch, res_purga, eliminacion):
        assert resultado.ejecutado is False
        assert "politica" in resultado.motivo_degradacion

    assert os.path.exists(ruta_pdf)
    assert estado_de(base, "EXP-SIN-POLITICA")["ciclo"] == "VIVO"
    with base.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM purgas;").fetchone()[0] == 0, (
            "Una operación que no se ejecuta no ensucia la auditoría con una fila vacía"
        )


def test_un_lote_con_oferta_presentada_sobrevive_al_ciclo_aunque_hoy_figure_caducado(
    base, politica, tmp_path
):
    """El caso que la capa existe para no equivocar, recorrido de principio a fin.

    `soft_delete_obsoletos()` reescribe el estado a `Inactiva` cuando la licitación
    desaparece del feed. Mirando sólo el estado actual, un concurso al que Incoop presentó
    oferta es indistinguible de una `Nueva` que nadie miró — y por tanto, eliminable.
    """
    historico = "\n".join([
        entrada_log_cambio_estado(1, "nueva", "presentada", autor="user"),
        entrada_log_cambio_estado(1, "presentada", "inactiva", autor="radar"),
    ])
    sembrar(base, tmp_path, "EXP-OFERTADO", estado="Inactiva")
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE expedientes SET log_cambios = ? WHERE id='EXP-OFERTADO';", (historico,)
            )

    ejecutar_fase_depurador(base, politica, ejecucion_id=1)
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "UPDATE expedientes SET deleted_at='2024-06-01T09:00:00Z' WHERE id='EXP-OFERTADO';"
            )
    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-OFERTADO"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 0
    assert "presentada" in resultado.bloqueados[0].detalle_motivo
    assert estado_de(base, "EXP-OFERTADO")["ciclo"] == "ARCHIVADO", "Sigue existiendo"


def test_un_documento_purgado_no_vuelve_a_procesarse_solo(base, politica, tmp_path):
    """Transición prohibida nº 5: `PURGADO → PROCESADO` sin una descarga nueva.

    El texto no reaparece por sí solo. Recuperarlo es trabajo del Lector, no del Depurador,
    y mientras nadie vuelva a descargarlo el documento no puede colarse en la cola de
    extracción como si tuviera fichero.
    """
    sembrar(base, tmp_path, "EXP-PURGADO")
    Depurador(memoria=base, politica=politica).purgar_documentos()

    pendientes = base.obtener_documentos_para_extraccion()
    analizables = base.listar_expedientes_pendientes_analisis()

    assert pendientes == [], "Sin fichero en disco no hay nada que extraer"
    assert [e["id"] for e in analizables] == [], (
        "Y un documento purgado no puede presentarse como pliego analizable"
    )


# =======================================================================================
# H-36 · El Depurador sólo borra sus propios ficheros
# =======================================================================================

def test_una_copia_de_la_base_no_puede_borrar_los_ficheros_del_original(
    base, politica, tmp_path
):
    """Descubierto borrando 63 pliegos de producción durante este mismo cierre de capa.

    Una copia de la base conserva las **rutas absolutas** de los ficheros originales. Purgar
    sobre la copia va a buscar los ficheros de producción y los borra. Es una trampa
    perfecta: copiar la base es exactamente lo que hace quien quiere probar el Depurador sin
    arriesgar nada, y es justo lo que lo vuelve destructivo.

    La invariante que lo cierra no depende de que nadie se acuerde: el Depurador sólo borra
    ficheros bajo **su propio** directorio documental. Si la ruta apunta fuera, no es suya.
    """
    import shutil

    # Un pliego que pertenece a la base "de producción".
    produccion = tmp_path / "produccion"
    produccion.mkdir()
    ruta_original = sembrar(base, produccion, "EXP-PRODUCCION")
    assert os.path.exists(ruta_original)

    # Una copia de esa base, en otro sitio, con las mismas rutas dentro.
    copia_dir = tmp_path / "copia"
    copia_dir.mkdir()
    copia = str(copia_dir / "licitaciones.db")
    shutil.copy(base.db_path, copia)

    resultado = Depurador(memoria=Memoria(db_path=copia), politica=politica).purgar_documentos()

    assert os.path.exists(ruta_original), (
        "La copia no puede borrar los ficheros de la base original"
    )
    assert resultado.errores_borrado == 1, "Y el rechazo se cuenta, no se silencia"
    assert resultado.documentos_purgados == 0, (
        "Sin liberar el peso no hay purga que registrar"
    )
