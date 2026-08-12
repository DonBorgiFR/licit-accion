"""Purga documental — Capa 9, Paso 5.

Fija lo que el Paso 5 tuvo que reparar antes de poder consolidar nada, porque el motor que
había se ejecutaba en cada corrida sin liberar jamás un byte:

* **H-33 — el vocabulario de estados documentales estaba partido en dos.** El Lector escribía
  `TEXTO_EXTRAIDO` al terminar de extraer; el DDL, el contrato de la capa, el Analista y la
  purga hablaban de `PROCESADO`. Nadie leía lo que el Lector escribía. Consecuencia doble: el
  Analista IA no recibía ni un pliego, y la purga sólo alcanzaba documentos descargados y
  nunca procesados — justo los que no pesan.
* **H-34 — `rotar_backups()` no devolvía su recuento.** El `if purgados > 0` del pipeline
  lanzaba un `TypeError` que un `except` amplio presentaba como un fallo del backup.

La primera prueba de este fichero es la que habría cazado H-33: recorre el Lector **real**
sobre un PDF **real** y no siembra ningún estado a mano (Convención C4). Las pruebas que
sembraban el estado pasaban en verde sobre una población que en producción es de paso.
"""

import json
import os

import pytest

from src.depurador import TIPO_PURGA_DOCUMENTAL, Depurador
from src.lector import Lector
from src.memoria import Memoria
from src.retencion import PoliticaRetencion

TEXTO_PLIEGO = (
    "Pliego de clausulas administrativas particulares para el servicio de limpieza "
    "viaria del municipio. Presupuesto base de licitacion: 145.000 euros. Plazo de "
    "ejecucion: veinticuatro meses, con subrogacion del personal adscrito al servicio."
)


# --------------------------------------------------------------------------------------
# Utilidades de siembra
# --------------------------------------------------------------------------------------

@pytest.fixture
def politica():
    """Política equivalente a la vigente (v1.1.0): 180 días de pliegos, 7 de copias."""
    return PoliticaRetencion(version="1.1.0", documentos_dias=180, backups_dias=7)


@pytest.fixture
def base(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    return memoria


def crear_pdf(ruta, texto=TEXTO_PLIEGO):
    """Un PDF de verdad, con texto nativo suficiente para no confundirse con un escaneado."""
    import fitz

    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    documento.save(str(ruta))
    documento.close()
    return str(ruta)


def sembrar_expediente(memoria, exp_id="EXP-1", fecha_limite=None,
                       fecha_ingesta="2026-01-15T09:00:00Z", estado_lote="Nueva", **campos_lote):
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta, fecha_limite) "
                "VALUES (?, 'Limpieza viaria', 'Ajuntament', ?, ?);",
                (exp_id, fecha_ingesta, fecha_limite),
            )
            columnas = ", ".join(campos_lote)
            marcadores = ", ".join("?" for _ in campos_lote)
            sql = (
                f"INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo"
                f"{', ' + columnas if columnas else ''}) "
                f"VALUES (?, 1, 'Lote unico', ?{', ' + marcadores if marcadores else ''});"
            )
            conn.execute(sql, (exp_id, estado_lote, *campos_lote.values()))


def sembrar_documento(memoria, exp_id="EXP-1", titulo="PCA.pdf", estado="PROCESADO",
                      local_path=None, texto="texto del pliego", hash_doc="h1"):
    with memoria.conectar() as conn:
        with conn:
            cursor = conn.execute(
                "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, "
                "estado, local_path, texto_extraido, updated_at) "
                "VALUES (?, ?, 'http://example.invalid/p.pdf', 'PCA', ?, ?, ?, ?, "
                "'2026-01-15T09:00:00Z');",
                (exp_id, titulo, hash_doc, estado, local_path, texto),
            )
            return cursor.lastrowid


def estado_documento(memoria, doc_id):
    with memoria.conectar() as conn:
        fila = conn.execute(
            "SELECT estado, local_path, texto_extraido FROM documentos WHERE id = ?;",
            (doc_id,),
        ).fetchone()
    return {"estado": fila[0], "local_path": fila[1], "texto_extraido": fila[2]}


# --------------------------------------------------------------------------------------
# H-33 · La ruta real, sin sembrar estados a mano (Convención C4)
# --------------------------------------------------------------------------------------

def test_el_lector_deja_el_documento_en_el_estado_que_el_resto_del_sistema_lee(base, tmp_path):
    """Es la prueba que faltaba, y la que habría cazado H-33 el primer día.

    No afirma sobre un estado sembrado: hace pasar un PDF real por el Lector real y mira
    dónde acaba. Mientras el Lector escribió `TEXTO_EXTRAIDO`, la extracción funcionaba
    perfectamente y no servía para nada, porque ninguna consulta del sistema lee ese valor.
    """
    ruta_pdf = crear_pdf(tmp_path / "pliego.pdf")
    sembrar_expediente(base)
    doc_id = sembrar_documento(base, estado="DESCARGADO", local_path=ruta_pdf, texto=None)

    Lector(db_memoria=base, run_id=1).procesar_extraccion_texto_lote()

    resultado = estado_documento(base, doc_id)
    assert resultado["estado"] == "PROCESADO", (
        "El Lector debe dejar el documento en el estado que declaran el DDL, el contrato de "
        "la Capa 9 y las consultas del Analista"
    )
    assert TEXTO_PLIEGO.split()[0] in resultado["texto_extraido"]


def test_el_analista_encuentra_el_pliego_que_el_lector_acaba_de_procesar(base, tmp_path):
    """La otra mitad de H-33: que la Capa 5 reciba trabajo.

    `listar_expedientes_pendientes_analisis()` busca documentos en `PROCESADO`. Con el
    vocabulario partido devolvía la lista vacía siempre y `obtener_datos_completos_expediente()`
    entregaba al LLM una cadena vacía: el Analista IA no llegó a ver un solo pliego.
    """
    ruta_pdf = crear_pdf(tmp_path / "pliego.pdf")
    sembrar_expediente(base)
    sembrar_documento(base, estado="DESCARGADO", local_path=ruta_pdf, texto=None)

    Lector(db_memoria=base, run_id=1).procesar_extraccion_texto_lote()

    pendientes = base.listar_expedientes_pendientes_analisis()
    assert [e["id"] for e in pendientes] == ["EXP-1"]

    datos = base.obtener_datos_completos_expediente("EXP-1")
    assert "limpieza" in datos["texto_pliego"].lower(), (
        "El texto que se manda al LLM debe ser el del pliego, no la cadena vacía"
    )


def test_una_base_con_el_estado_huerfano_se_normaliza_al_arrancar(base):
    """Bases escritas por otra máquina pueden arrastrar el estado huérfano ya en v6.

    Esa rama no vuelve a pasar por la migración, así que la normalización va en el arranque
    y es idempotente. El proyecto vive en OneDrive: es la lección del bundle de Vite, cuya
    fecha no decía de qué fuente salió.
    """
    sembrar_expediente(base)
    doc_id = sembrar_documento(base, estado="TEXTO_EXTRAIDO", local_path="/tmp/x.pdf")

    base.setup_db()

    assert estado_documento(base, doc_id)["estado"] == "PROCESADO"


# --------------------------------------------------------------------------------------
# Operación 2 del contrato — la purga libera peso y nada más
# --------------------------------------------------------------------------------------

def test_la_purga_borra_el_fichero_vacia_el_texto_y_conserva_la_fila(base, politica, tmp_path):
    """Postcondición del contrato. La fila **permanece**: se sabe qué hubo y por qué no está."""
    ruta_pdf = crear_pdf(tmp_path / "viejo.pdf")
    sembrar_expediente(base, fecha_limite="2026-01-20T23:59:00Z")
    doc_id = sembrar_documento(base, local_path=ruta_pdf, texto=TEXTO_PLIEGO)

    resultado = Depurador(memoria=base, politica=politica).purgar_documentos()

    assert resultado.ejecutado
    assert resultado.documentos_purgados == 1
    assert resultado.ficheros_borrados == 1
    assert resultado.bytes_liberados > 0, "bytes_liberados es postcondición, no adorno"
    assert not os.path.exists(ruta_pdf)

    fila = estado_documento(base, doc_id)
    assert fila["estado"] == "PURGADO"
    assert fila["local_path"] is None
    assert fila["texto_extraido"] is None, (
        "El texto es la mitad del peso que esta operación existe para liberar"
    )

    with base.conectar() as conn:
        url, hash_doc = conn.execute(
            "SELECT url, hash_documento FROM documentos WHERE id = ?;", (doc_id,)
        ).fetchone()
    assert url and hash_doc, "La fila conserva su rastro: qué hubo y de dónde vino"


def test_la_memoria_comercial_sobrevive_a_una_purga_total(base, politica, tmp_path):
    """La invariante central de la capa, vista desde el Paso 5.

    Purgar libera **peso documental**, nunca registro de negocio. Un contrato adjudicado
    conserva su adjudicatario, su importe, sus horas y su garantía después de perder sus PDFs.
    """
    ruta_pdf = crear_pdf(tmp_path / "adjudicado.pdf")
    sembrar_expediente(
        base,
        fecha_limite="2026-01-20T23:59:00Z",
        estado_lote="Adjudicada",
        importe_adjudicacion=145000.0,
        horas_internas_invertidas=37,
        costes_externos=1200.0,
        importe_garantia_retenida=7250.0,
        empresa_adjudicataria="Incoop SCCL",
    )
    sembrar_documento(base, local_path=ruta_pdf)

    Depurador(memoria=base, politica=politica).purgar_documentos()

    with base.conectar() as conn:
        fila = conn.execute(
            "SELECT estado_operativo, importe_adjudicacion, horas_internas_invertidas, "
            "costes_externos, importe_garantia_retenida, empresa_adjudicataria, deleted_at "
            "FROM lotes WHERE expediente_id = 'EXP-1';"
        ).fetchone()

    assert fila == ("Adjudicada", 145000.0, 37, 1200.0, 7250.0, "Incoop SCCL", None), (
        "Ni un solo campo comercial puede moverse, y el Depurador no escribe en "
        "estado_operativo ni archiva de rebote"
    )
    assert not os.path.exists(ruta_pdf), "El peso sí se libera"


def test_purgar_dos_veces_no_cuenta_dos_veces(base, politica, tmp_path):
    """Idempotencia (Regla 10). Un documento ya `PURGADO` se salta sin error y sin contar."""
    sembrar_expediente(base, fecha_limite="2026-01-20T23:59:00Z")
    sembrar_documento(base, local_path=crear_pdf(tmp_path / "uno.pdf"))
    depurador = Depurador(memoria=base, politica=politica)

    primera = depurador.purgar_documentos()
    segunda = depurador.purgar_documentos()

    assert primera.documentos_purgados == 1
    assert segunda.documentos_purgados == 0
    assert segunda.bytes_liberados == 0
    assert segunda.ejecutado, "No encontrar nada que purgar es un éxito, no una degradación"


def test_el_plazo_se_cuenta_desde_la_fecha_limite_y_cae_a_la_ingesta(base, politica, tmp_path):
    """Decisión de dirección (2026-08-12): mismo ancla que el motor de archivado.

    Contar desde la ingesta purgaría antes y podría borrar el pliego de un concurso todavía
    abierto: la ingesta siempre precede a la fecha límite.
    """
    # Ingesta antigua, pero con el plazo de presentación aún reciente: no se purga.
    sembrar_expediente(base, exp_id="EXP-VIVO", fecha_ingesta="2026-01-15T09:00:00Z",
                       fecha_limite="2026-08-01T23:59:00Z")
    doc_vivo = sembrar_documento(base, exp_id="EXP-VIVO", local_path=crear_pdf(tmp_path / "vivo.pdf"))

    # Sin fecha límite legible se cae a la ingesta, que sí ha vencido.
    sembrar_expediente(base, exp_id="EXP-SIN-FECHA", fecha_ingesta="2025-06-01T09:00:00Z",
                       fecha_limite="N/A")
    doc_sin_fecha = sembrar_documento(base, exp_id="EXP-SIN-FECHA",
                                      local_path=crear_pdf(tmp_path / "sinfecha.pdf"))

    Depurador(memoria=base, politica=politica).purgar_documentos()

    assert estado_documento(base, doc_vivo)["estado"] == "PROCESADO", (
        "Un concurso cuyo plazo venció hace menos de 180 días conserva su pliego"
    )
    assert estado_documento(base, doc_sin_fecha)["estado"] == "PURGADO"


# --------------------------------------------------------------------------------------
# Modo degradado: en caso de duda, no hacer nada (Regla 5)
# --------------------------------------------------------------------------------------

def test_sin_politica_no_se_borra_ni_un_fichero(base, tmp_path):
    """Purgar es irreversible: la degradación correcta es detenerse, no aplicar un plazo propio."""
    ruta_pdf = crear_pdf(tmp_path / "intacto.pdf")
    sembrar_expediente(base, fecha_limite="2020-01-01T00:00:00Z")
    doc_id = sembrar_documento(base, local_path=ruta_pdf)

    resultado = Depurador(memoria=base, politica=None).purgar_documentos()

    assert resultado.ejecutado is False
    assert "politica_retencion_ausente" in resultado.motivo_degradacion
    assert os.path.exists(ruta_pdf)
    assert estado_documento(base, doc_id)["estado"] == "PROCESADO"


def test_un_fichero_que_no_se_puede_borrar_no_se_marca_como_purgado(
    base, politica, tmp_path, monkeypatch
):
    """Los cerrojos de fichero en Windows son reales (lección del Paso D1).

    Marcarlo `PURGADO` con el fichero todavía en disco lo sacaría de cualquier selección
    futura y dejaría el fichero huérfano para siempre. Se cuenta como error y se reintenta.
    """
    ruta_pdf = crear_pdf(tmp_path / "bloqueado.pdf")
    sembrar_expediente(base, fecha_limite="2026-01-20T23:59:00Z")
    doc_id = sembrar_documento(base, local_path=ruta_pdf)

    def remove_bloqueado(ruta, *args, **kwargs):
        raise PermissionError("El proceso no tiene acceso al archivo")

    monkeypatch.setattr(os, "remove", remove_bloqueado)
    resultado = Depurador(memoria=base, politica=politica).purgar_documentos()

    assert resultado.ejecutado
    assert resultado.errores_borrado == 1
    assert resultado.documentos_purgados == 0
    assert estado_documento(base, doc_id)["estado"] == "PROCESADO", (
        "Sin liberar el peso no hay purga que registrar"
    )


# --------------------------------------------------------------------------------------
# Auditoría: nada se purga en silencio
# --------------------------------------------------------------------------------------

def test_la_purga_deja_su_rastro_en_la_tabla_purgas(base, politica, tmp_path):
    """Regla 3 y punto 5 del diseño: bajo qué política, cuánto liberó y a petición de quién."""
    sembrar_expediente(base, fecha_limite="2026-01-20T23:59:00Z")
    sembrar_documento(base, local_path=crear_pdf(tmp_path / "auditado.pdf"))

    Depurador(memoria=base, politica=politica).purgar_documentos(solicitado_por="usuario")

    with base.conectar() as conn:
        fila = conn.execute(
            "SELECT tipo, solicitada_por, version_politica, documentos_purgados, "
            "bytes_liberados, resultado, detalle FROM purgas;"
        ).fetchone()

    assert fila[0] == TIPO_PURGA_DOCUMENTAL, "El tipo declarado en el DDL, no uno inventado"
    assert fila[1] == "usuario"
    assert fila[2] == "1.1.0"
    assert fila[3] == 1
    assert fila[4] > 0
    assert fila[5] == "COMPLETADA"
    assert json.loads(fila[6])["operacion"] == "documentos"


def test_una_purga_que_no_encuentra_nada_no_inventa_una_fila_de_auditoria(base, politica):
    """No encontrar nada que purgar no es una purga: la tabla `purgas` no debe engordar sola."""
    sembrar_expediente(base, fecha_limite="2026-08-01T23:59:00Z")
    sembrar_documento(base, local_path=None, texto=None)

    resultado = Depurador(memoria=base, politica=politica).purgar_documentos()

    with base.conectar() as conn:
        assert conn.execute("SELECT COUNT(*) FROM purgas;").fetchone()[0] == 0
    assert resultado.ejecutado and not resultado.hubo_cambios


# --------------------------------------------------------------------------------------
# H-34 · Rotación de copias
# --------------------------------------------------------------------------------------

def test_rotar_backups_devuelve_su_recuento(base):
    """H-34: devolvía `None` por su camino normal.

    El `if purgados > 0` del pipeline lanzaba un `TypeError` que un `except` amplio anunciaba
    como *"No se pudo completar el backup de seguridad"*, con el backup hecho y las copias
    rotadas. El mensaje era lo único falso.
    """
    base.realizar_backup(run_id=1)

    rotadas = base.rotar_backups(dias_retencion=7)

    assert isinstance(rotadas, int), "Un recuento, no None: el pipeline compara este valor"
    assert rotadas == 0, "Una copia recién creada no ha superado su plazo"


def test_la_rotacion_de_copias_retira_las_caducadas_y_lo_audita(base, politica, tmp_path):
    """Una copia con fecha vencida en el nombre se retira, y consta bajo qué política."""
    base.realizar_backup(run_id=1)
    directorio = os.path.join(os.path.dirname(base.db_path), "backups")
    caducada = os.path.join(directorio, "licitaciones_20250101_120000.db.bak")
    with open(caducada, "w", encoding="utf-8") as fichero:
        fichero.write("copia antigua")

    resultado = Depurador(memoria=base, politica=politica).rotar_copias()

    assert resultado.ejecutado
    assert resultado.copias_rotadas == 1
    assert not os.path.exists(caducada)

    with base.conectar() as conn:
        detalle = conn.execute(
            "SELECT detalle FROM purgas WHERE tipo = ?;", (TIPO_PURGA_DOCUMENTAL,)
        ).fetchone()[0]
    assert json.loads(detalle)["operacion"] == "rotacion_copias"


def test_sin_politica_no_se_rota_ninguna_copia(base):
    resultado = Depurador(memoria=base, politica=None).rotar_copias()

    assert resultado.ejecutado is False
    assert "politica_retencion_ausente" in resultado.motivo_degradacion
