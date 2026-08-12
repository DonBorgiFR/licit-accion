"""Eliminación física — Capa 9, Paso 6.

La única operación de la capa capaz de destruir registros, y la única cuyos fallos no se
pueden reparar mirando el código: cuando se descubren, el dato ya no está.

Lo que estas pruebas protegen, por orden de gravedad de lo que impiden:

1. **Que la memoria comercial sea indestructible.** Un lote que alcanzó alguna vez
   `Presentada`, `Adjudicada`, `Perdida`, `Estudiando` o `Descartada` hace que su expediente
   sea ineliminable para siempre — y "alguna vez" incluye lo que ya no se ve en el estado
   actual, porque `soft_delete_obsoletos()` lo reescribe cada vez que una licitación
   desaparece del feed.
2. **Que nada se borre sin que una persona lo pida** sobre una lista concreta, tras
   previsualizarlo y con una copia de seguridad correcta detrás.
3. **Que no queden huérfanos.** La cascada va hoja→raíz con las claves foráneas activas.
"""

import json
import os

import pytest

from src.depurador import (
    CAMPOS_COMERCIALES,
    ESTADOS_QUE_BLOQUEAN_ELIMINACION,
    MOTIVO_CUARENTENA,
    MOTIVO_MEMORIA_COMERCIAL,
    MOTIVO_NO_ARCHIVADO,
    TIPO_ELIMINACION,
    ConfirmacionRequerida,
    CopiaSeguridadFallida,
    Depurador,
)
from src.memoria import Memoria, entrada_log_cambio_estado
from src.retencion import PoliticaEliminacion, PoliticaRetencion

#: Archivado hace mucho más de la cuarentena de 365 días.
ARCHIVADO_ANTIGUO = "2024-01-10T09:00:00Z"
#: Archivado ayer: dentro de cuarentena.
ARCHIVADO_RECIENTE = "2026-08-11T09:00:00Z"


@pytest.fixture
def politica():
    return PoliticaRetencion(
        version="1.2.0",
        documentos_dias=180,
        backups_dias=7,
        eliminacion=PoliticaEliminacion(dias_archivado_minimo=365),
    )


@pytest.fixture
def base(tmp_path):
    memoria = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    memoria.setup_db()
    return memoria


def sembrar(memoria, exp_id="EXP-1", deleted_at=ARCHIVADO_ANTIGUO, estado_lote="Nueva",
            log_cambios="", **campos_lote):
    """Un expediente archivado con un único lote. Por defecto, eliminable."""
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO expedientes (id, titulo, organo, fecha_ingesta, fecha_limite, "
                "deleted_at, deleted_reason, log_cambios) VALUES (?, 'Limpieza', 'Ajuntament', "
                "'2024-01-01T09:00:00Z', '2024-01-05T23:59:00Z', ?, 'archivado automático', ?);",
                (exp_id, deleted_at, log_cambios),
            )
            columnas = ", ".join(campos_lote)
            marcadores = ", ".join("?" for _ in campos_lote)
            conn.execute(
                f"INSERT INTO lotes (expediente_id, lote_numero, titulo_lote, estado_operativo, "
                f"deleted_at{', ' + columnas if columnas else ''}) "
                f"VALUES (?, 1, 'Lote unico', ?, ?{', ' + marcadores if marcadores else ''});",
                (exp_id, estado_lote, deleted_at, *campos_lote.values()),
            )


def sembrar_documento(memoria, exp_id="EXP-1", local_path=None, hash_doc="h1"):
    with memoria.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO documentos (expediente_id, titulo, url, tipo, hash_documento, "
                "estado, local_path, texto_extraido, updated_at) VALUES (?, 'PCA.pdf', "
                "'http://example.invalid/p.pdf', 'PCA', ?, 'PROCESADO', ?, 'texto', "
                "'2024-01-01T09:00:00Z');",
                (exp_id, hash_doc, local_path),
            )


def existe(memoria, tabla, exp_id="EXP-1"):
    columna = "id" if tabla == "expedientes" else "expediente_id"
    with memoria.conectar() as conn:
        return conn.execute(
            f"SELECT COUNT(*) FROM {tabla} WHERE {columna} = ?;", (exp_id,)
        ).fetchone()[0]


# --------------------------------------------------------------------------------------
# La invariante: la memoria comercial es indestructible
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("estado", ESTADOS_QUE_BLOQUEAN_ELIMINACION)
def test_ningun_estado_con_negocio_invertido_puede_eliminarse(base, politica, estado):
    """Los cinco estados del contrato, uno por uno. Ninguno admite excepción."""
    sembrar(base, estado_lote=estado.capitalize())

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 0
    assert [b.motivo for b in resultado.bloqueados] == [MOTIVO_MEMORIA_COMERCIAL]
    assert existe(base, "expedientes") == 1


def test_un_lote_que_paso_por_presentada_bloquea_aunque_hoy_figure_caducado(base, politica):
    """El escenario que el propio contrato pone como ejemplo, y que ocurre de verdad.

    `soft_delete_obsoletos()` reescribe el estado a `Inactiva` cuando la licitación
    desaparece del feed. Mirando sólo el estado actual, un expediente al que Incoop presentó
    oferta sería indistinguible de una `Nueva` que nadie miró — y por tanto eliminable.
    El histórico de estados (H-31) es la única evidencia que queda.
    """
    historico = "\n".join([
        entrada_log_cambio_estado(1, "nueva", "presentada", autor="user"),
        entrada_log_cambio_estado(1, "presentada", "inactiva", autor="radar"),
    ])
    sembrar(base, estado_lote="Inactiva", log_cambios=historico)

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 0
    assert resultado.bloqueados[0].motivo == MOTIVO_MEMORIA_COMERCIAL
    assert "presentada" in resultado.bloqueados[0].detalle_motivo
    assert existe(base, "expedientes") == 1


@pytest.mark.parametrize("campo,valor", [
    ("importe_adjudicacion", 145000.0),
    ("dinero_en_la_mesa", 8000.0),
    ("horas_internas_invertidas", 37),
    ("costes_externos", 1200.0),
    ("importe_garantia_retenida", 7250.0),
    ("empresa_adjudicataria", "Incoop SCCL"),
])
def test_cualquier_campo_comercial_con_valor_bloquea(base, politica, campo, valor):
    """El dinero y las horas no mienten aunque el estado y el histórico se hayan perdido."""
    sembrar(base, estado_lote="Nueva", **{campo: valor})

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 0
    assert resultado.bloqueados[0].motivo == MOTIVO_MEMORIA_COMERCIAL
    assert campo in resultado.bloqueados[0].detalle_motivo


def test_los_seis_campos_comerciales_estan_vigilados():
    """Si alguien añade un campo comercial al esquema, esta prueba obliga a mirarlo aquí.

    Un campo nuevo que no entre en la invariante sería memoria comercial sin proteger, y el
    fallo sólo se vería cuando el dato ya no existiera.
    """
    assert set(CAMPOS_COMERCIALES) == {
        "importe_adjudicacion", "dinero_en_la_mesa", "horas_internas_invertidas",
        "costes_externos", "importe_garantia_retenida", "empresa_adjudicataria",
    }


# --------------------------------------------------------------------------------------
# Transiciones prohibidas del contrato
# --------------------------------------------------------------------------------------

def test_un_expediente_vivo_no_puede_eliminarse(base, politica):
    """Transición prohibida nº 1: `VIVO → ELIMINADO` directo. Hay que pasar por archivado."""
    sembrar(base, deleted_at=None)

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.bloqueados[0].motivo == MOTIVO_NO_ARCHIVADO
    assert existe(base, "expedientes") == 1


def test_la_cuarentena_impide_archivar_y_borrar_el_mismo_dia(base, politica):
    """Decisión de dirección (2026-08-12): 365 días archivado antes de poder eliminar.

    Impide la secuencia con la que se destruye algo por error — archivar y borrar seguido—
    sin depender de que quien confirma se dé cuenta a tiempo.
    """
    sembrar(base, deleted_at=ARCHIVADO_RECIENTE)

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.bloqueados[0].motivo == MOTIVO_CUARENTENA
    assert existe(base, "expedientes") == 1


def test_sin_confirmacion_explicita_no_se_elimina_nada(base, politica):
    """`ConfirmacionRequerida` (HTTP 400). No hay botón que borre a ciegas."""
    sembrar(base)

    with pytest.raises(ConfirmacionRequerida):
        Depurador(memoria=base, politica=politica).eliminar_expedientes(["EXP-1"])

    assert existe(base, "expedientes") == 1


def test_sin_bloque_de_politica_no_se_elimina_nada(base):
    """Sin criterio declarado no se borra: no se inventan plazos (lección de H-18)."""
    sembrar(base)
    politica_sin_eliminacion = PoliticaRetencion(
        version="1.1.0", documentos_dias=180, backups_dias=7
    )

    resultado = Depurador(memoria=base, politica=politica_sin_eliminacion).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.ejecutado is False
    assert "politica_sin_bloque_eliminacion" in resultado.motivo_degradacion
    assert existe(base, "expedientes") == 1


def test_si_falla_la_copia_de_seguridad_no_se_elimina_nada(base, politica, monkeypatch):
    """`CopiaSeguridadFallida` (HTTP 503). Purgar sin red no es una degradación aceptable."""
    sembrar(base)

    def backup_roto(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(Memoria, "realizar_backup", backup_roto)

    with pytest.raises(CopiaSeguridadFallida):
        Depurador(memoria=base, politica=politica).eliminar_expedientes(
            ["EXP-1"], confirmado=True
        )

    assert existe(base, "expedientes") == 1
    assert existe(base, "lotes") == 1


# --------------------------------------------------------------------------------------
# El camino feliz: lo que nunca llegó a ser negocio sí se va
# --------------------------------------------------------------------------------------

def test_lo_que_nadie_miro_nunca_se_elimina_de_hoja_a_raiz(base, politica, tmp_path):
    """Una `Nueva` que caducó, se archivó y cumplió cuarentena. Sin huérfanos y con copia."""
    # Bajo `documents/`, que es donde el Lector deja los pliegos y el único sitio del que el
    # Depurador acepta borrar desde H-36.
    carpeta = tmp_path / "documents"
    carpeta.mkdir(exist_ok=True)
    ruta_pdf = str(carpeta / "pliego.pdf")
    with open(ruta_pdf, "wb") as fichero:
        fichero.write(b"%PDF-1.4 contenido de prueba")
    sembrar(base)
    sembrar_documento(base, local_path=ruta_pdf)

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True, solicitado_por="usuario"
    )

    assert resultado.expedientes_eliminados == 1
    assert resultado.lotes_eliminados == 1
    assert resultado.documentos_eliminados == 1
    assert resultado.bytes_liberados > 0
    assert not os.path.exists(ruta_pdf), "El fichero se borra antes que su fila, o queda huérfano"
    for tabla in ("expedientes", "lotes", "documentos"):
        assert existe(base, tabla) == 0
    assert resultado.backup_asociado and os.path.exists(resultado.backup_asociado)


def test_lo_bloqueado_no_impide_eliminar_lo_eliminable(base, politica):
    """El contrato pide las dos salidas a la vez: lo eliminado y lo protegido con su motivo."""
    sembrar(base, exp_id="EXP-BORRABLE")
    sembrar(base, exp_id="EXP-ADJUDICADO", estado_lote="Adjudicada",
            importe_adjudicacion=145000.0)

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-BORRABLE", "EXP-ADJUDICADO"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 1
    assert [b.expediente_id for b in resultado.bloqueados] == ["EXP-ADJUDICADO"]
    assert existe(base, "expedientes", "EXP-BORRABLE") == 0
    assert existe(base, "expedientes", "EXP-ADJUDICADO") == 1


def test_eliminar_un_expediente_inexistente_no_falla(base, politica):
    """Idempotencia del contrato: lo que ya no está se salta sin error y sin bloquear."""
    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-FANTASMA"], confirmado=True
    )

    assert resultado.ejecutado
    assert resultado.expedientes_eliminados == 0
    assert resultado.bloqueados == []


def test_la_alerta_del_centinela_sobrevive_perdiendo_su_vinculo(base, politica):
    """Su clave foránea es `ON DELETE SET NULL`: la alerta es información propia del
    Centinela, no del expediente, y no debe desaparecer con él ni impedir su borrado."""
    sembrar(base)
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT INTO boletines_alertas (id_alerta, fuente, num_boletin, "
                "fecha_publicacion, organo_emisor, titulo_anuncio, "
                "expediente_licitacion_vinculado, fecha_ingesta, updated_at) "
                "VALUES ('a1', 'DOGC', '9123', '2024-01-02T00:00:00Z', 'Ajuntament', "
                "'Anuncio previo de licitación', 'EXP-1', '2024-01-02T00:00:00Z', "
                "'2024-01-02T00:00:00Z');"
            )

    resultado = Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-1"], confirmado=True
    )

    assert resultado.expedientes_eliminados == 1
    with base.conectar() as conn:
        vinculo = conn.execute(
            "SELECT expediente_licitacion_vinculado FROM boletines_alertas WHERE id_alerta='a1';"
        ).fetchone()
    assert vinculo is not None, "La alerta sigue existiendo"
    assert vinculo[0] is None, "Y ha perdido el vínculo, sin arrastrar nada consigo"


# --------------------------------------------------------------------------------------
# Previsualización y auditoría
# --------------------------------------------------------------------------------------

def test_la_previsualizacion_no_altera_absolutamente_nada(base, politica):
    """Se enseña qué va a desaparecer antes de que nadie confirme. Mirar no borra."""
    sembrar(base, exp_id="EXP-BORRABLE")
    sembrar(base, exp_id="EXP-ADJUDICADO", estado_lote="Adjudicada")

    previa = Depurador(memoria=base, politica=politica).previsualizar_eliminacion()

    assert [e.expediente_id for e in previa.eliminables] == ["EXP-BORRABLE"]
    assert [b.expediente_id for b in previa.bloqueados] == ["EXP-ADJUDICADO"]
    assert existe(base, "expedientes", "EXP-BORRABLE") == 1
    assert existe(base, "expedientes", "EXP-ADJUDICADO") == 1


def test_la_eliminacion_deja_su_rastro_con_la_copia_asociada(base, politica):
    """Nada se purga en silencio: qué se borró, qué se protegió y con qué copia detrás."""
    sembrar(base, exp_id="EXP-BORRABLE")
    sembrar(base, exp_id="EXP-PERDIDO", estado_lote="Perdida")

    Depurador(memoria=base, politica=politica).eliminar_expedientes(
        ["EXP-BORRABLE", "EXP-PERDIDO"], confirmado=True, solicitado_por="usuario"
    )

    with base.conectar() as conn:
        fila = conn.execute(
            "SELECT tipo, solicitada_por, version_politica, expedientes_eliminados, "
            "bloqueados, backup_asociado, resultado, detalle FROM purgas;"
        ).fetchone()

    assert fila[0] == TIPO_ELIMINACION
    assert fila[1] == "usuario"
    assert fila[2] == "1.2.0"
    assert fila[3] == 1
    assert fila[4] == 1, "Los bloqueados se cuentan: bloquear mucho es una señal, no un fallo"
    assert fila[5], "La copia de seguridad queda asociada a la purga que protegió"
    assert fila[6] == "COMPLETADA"
    assert json.loads(fila[7])["bloqueados"][0]["expediente"] == "EXP-PERDIDO"
