"""H-58 · `DESCARGANDO` deja de ser un agujero.

`DESCARGANDO` es una **marca de paso**: se escribe justo antes de bajar el fichero y debería
durar segundos. Lo que no era cierto es que alguien volviera a por él. Auditado el vocabulario
entero de `documentos.estado` el 2026-08-27, era **el único estado transitorio que ninguna
consulta de recogida miraba** — los otros tres que nadie recoge (`PROCESADO`, `PURGADO`,
`OMITIDO_FORMATO_NO_PDF`) son finales de camino, y eso sí es correcto.

Es la forma exacta de H-33 y de H-53 cara B, la tercera vez que este proyecto la pisa. Y es la
peor de las tres, porque ocurría **mientras la corrida se declaraba `COMPLETED` con 0 errores**:
seis pliegos reales —el PCA, el PPT, el quadre, la memòria— se quedaron dentro sin que nada lo
dijera.

El defecto tenía dos capas y estas pruebas fijan las dos:

* **El disparador** — `_path_for_document()` troceaba el expediente por el carácter 4 sin
  comprobar que el trozo fuera un nombre legal. `"HCA 006/2026"` daba la carpeta `"HCA "`, con
  espacio final, y Windows no puede crearla: `makedirs` lanzaba `WinError 3`.
* **El amplificador** — esa excepción escapaba del hilo, el `Future` que nadie recogía se la
  tragaba, y el documento se quedaba en `DESCARGANDO` para siempre.

Ninguna de las dos habría bastado sola: sin el disparador no se varaba nadie, y sin el
amplificador el fallo se habría visto el primer día.
"""

import os
import sqlite3

import pytest

from src.lector import Lector, _sanear_componente_ruta
from src.memoria import Memoria


# =====================================================================
# ANDAMIAJE
# =====================================================================

@pytest.fixture
def base(tmp_path):
    db = Memoria(db_path=str(tmp_path / "licitaciones.db"))
    db.setup_db()
    return db


def sembrar(base, doc_id, estado, intentos=0, exp_id="EXP-1"):
    with base.conectar() as conn:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO expedientes (id, titulo, fecha_ingesta) "
                "VALUES (?, 'Expediente de prueba', '2026-08-27T07:00:00Z');",
                (exp_id,),
            )
            conn.execute(
                "INSERT INTO documentos (id, expediente_id, titulo, url, tipo, hash_documento, "
                "estado, intentos, updated_at) "
                "VALUES (?, ?, ?, ?, 'PCA', ?, ?, ?, '2026-08-27T07:15:42Z');",
                (doc_id, exp_id, f"Pliego {doc_id}", f"https://ejemplo/{doc_id}.pdf",
                 f"hash-{doc_id}", estado, intentos),
            )


def estado_de(base, doc_id):
    with base.conectar() as conn:
        return conn.execute("SELECT estado FROM documentos WHERE id = ?;", (doc_id,)).fetchone()[0]


# =====================================================================
# 1 · LA RECOGIDA: un documento varado vuelve a la cola
# =====================================================================

def test_un_documento_varado_en_descargando_vuelve_a_la_cola(base):
    """**La regresión central.** Si alguien retira `DESCARGANDO` de la consulta, cae aquí."""
    sembrar(base, 1, "DESCARGANDO")

    pendientes = base.obtener_documentos_pendientes()

    assert [d["id"] for d in pendientes] == [1]


def test_el_varado_se_recoge_junto_a_los_de_siempre_y_sin_desplazarlos(base):
    """Recoger los varados no puede costar dejar de recoger lo que ya se recogía."""
    sembrar(base, 1, "DETECTADO")
    sembrar(base, 2, "ERROR_DESCARGA", intentos=1)
    sembrar(base, 3, "DESCARGANDO")

    recogidos = {d["id"] for d in base.obtener_documentos_pendientes()}

    assert recogidos == {1, 2, 3}


def test_un_varado_que_agoto_los_intentos_no_se_recoge(base):
    """El agujero no se cambia por un bucle: el tope de 3 rige también para los varados.

    Sin esta prueba, un documento que hiciera morir la descarga de forma reproducible
    volvería a intentarse en todas las corridas para siempre.
    """
    sembrar(base, 1, "DESCARGANDO", intentos=3)

    assert base.obtener_documentos_pendientes() == []


def test_los_estados_terminales_siguen_sin_recogerse(base):
    """La invariante no dice *«recógelo todo»*: dice *«todo transitorio tiene consumidor»*.

    `PROCESADO`, `PURGADO` y `OMITIDO_FORMATO_NO_PDF` son finales de camino y deben seguir
    fuera de la cola. Una reparación que los arrastrara reprocesaría el archivo entero.
    """
    for i, estado in enumerate(("PROCESADO", "PURGADO", "OMITIDO_FORMATO_NO_PDF"), start=1):
        sembrar(base, i, estado)

    assert base.obtener_documentos_pendientes() == []


def test_la_consulta_declara_el_estado_de_cada_documento(base):
    """Sin `estado` en la fila, un rescate es indistinguible de un documento nuevo."""
    sembrar(base, 1, "DESCARGANDO")

    (doc,) = base.obtener_documentos_pendientes()

    assert doc["estado"] == "DESCARGANDO"


# =====================================================================
# 2 · EL DISPARADOR: componentes de ruta que Windows no admite
# =====================================================================

@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("HCA ", "HCA"),        # el caso real: "HCA 006/2026" troceado por el carácter 4
        ("EXP.", "EXP"),        # un punto final vale lo mismo que un espacio en Windows
        ("  ", "MISC"),         # todo espacios: no queda nombre, se usa el respaldo
        ("", "MISC"),           # vacío
        ("CON", "_CON"),        # nombre de dispositivo reservado
        ("LPT1", "_LPT1"),      # idem, con número
        ("con.txt", "_con.txt"),  # Windows reserva también la forma con extensión
        ("HCA 006_2026", "HCA 006_2026"),  # lo normal no se toca
    ],
)
def test_el_saneador_devuelve_nombres_que_windows_admite(entrada, esperado):
    assert _sanear_componente_ruta(entrada) == esperado


def test_un_expediente_con_espacio_en_la_cuarta_posicion_produce_una_ruta_creable(base, tmp_path):
    """El caso exacto que varó los 6 pliegos, reproducido de punta a punta.

    Antes de la reparación `os.makedirs` lanzaba `FileNotFoundError [WinError 3]` sobre la
    carpeta `"HCA "`. **No era el límite de 260 caracteres**: la ruta medía 111. Era el
    espacio final, y el experimento de control lo confirmó — quitándolo, `makedirs` pasaba.
    """
    lector = Lector(db_memoria=base, run_id=58)

    final_path, temp_path = lector._path_for_document(
        expediente_id="HCA 006/2026",
        lote_numero=1,
        titulo="05. (PCA) PLEC CLÀUSULES ADMINISTRATIVES PARTICULARS",
        tipo="PCA",
        sha_short="abcd1234",
    )

    assert os.path.isdir(os.path.dirname(final_path))
    for componente in os.path.dirname(final_path).split(os.sep):
        assert componente == componente.rstrip(". "), f"componente ilegal en Windows: {componente!r}"
    assert temp_path.endswith(".part")


# =====================================================================
# 3 · EL AMPLIFICADOR: ninguna salida deja el documento varado
# =====================================================================

class _DescargaQueRevienta(Lector):
    """Un Lector cuyo camino de descarga muere después de marcar `DESCARGANDO`.

    Reproduce la secuencia medida en la corrida 17: el estado se escribe, se emite
    `doc_download_started`, y a continuación salta una excepción — que es exactamente lo
    que hacía `_path_for_document` con el expediente `"HCA 006/2026"`.
    """

    def _descargar_documento_hilo(self, doc, domain_semaphores):
        self.db.actualizar_estado_documento(doc["id"], "DESCARGANDO")
        raise FileNotFoundError("[WinError 3] El sistema no puede encontrar la ruta especificada")


def test_una_excepcion_en_el_hilo_no_deja_el_documento_en_descargando(base):
    """**La postcondición del contrato**: ninguna salida deja `DESCARGANDO` puesto."""
    sembrar(base, 1, "DETECTADO")
    lector = _DescargaQueRevienta(db_memoria=base, run_id=58)

    with pytest.raises(FileNotFoundError):
        lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 0}, {})

    assert estado_de(base, 1) == "ERROR_DESCARGA"


def test_el_documento_soltado_conserva_el_motivo_por_el_que_se_varo(base):
    """Un estado que cambia sin decir por qué es la Convención C2 a medias."""
    sembrar(base, 1, "DETECTADO")
    lector = _DescargaQueRevienta(db_memoria=base, run_id=58)

    with pytest.raises(FileNotFoundError):
        lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 0}, {})

    with base.conectar() as conn:
        detalle = conn.execute("SELECT error_detalle FROM documentos WHERE id = 1;").fetchone()[0]

    assert "VARADO_RECUPERADO" in detalle
    assert "WinError 3" in detalle


def test_soltar_un_varado_incrementa_los_intentos(base):
    """Sin incrementar, el tope de 3 no llegaría a aplicarse nunca y el bucle sería eterno."""
    sembrar(base, 1, "DESCARGANDO", intentos=1)
    lector = _DescargaQueRevienta(db_memoria=base, run_id=58)

    with pytest.raises(FileNotFoundError):
        lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 1}, {})

    with base.conectar() as conn:
        intentos = conn.execute("SELECT intentos FROM documentos WHERE id = 1;").fetchone()[0]

    assert intentos == 2


def test_la_red_de_seguridad_relanza_para_que_el_orquestador_se_entere(base):
    """Tragarse la excepción aquí sería repetir el defecto una capa más arriba.

    La red suelta el documento, pero **no silencia el fallo**: lo relanza para que el
    orquestador lo recoja del `Future` y lo registre.
    """
    sembrar(base, 1, "DETECTADO")
    lector = _DescargaQueRevienta(db_memoria=base, run_id=58)

    with pytest.raises(FileNotFoundError):
        lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 0}, {})


def test_una_salida_limpia_no_toca_el_estado_que_el_camino_dejo(base):
    """La red no debe reescribir lo que el camino ya resolvió bien."""
    sembrar(base, 1, "DETECTADO")

    class _DescargaQueTermina(Lector):
        def _descargar_documento_hilo(self, doc, domain_semaphores):
            self.db.actualizar_estado_documento(doc["id"], "DESCARGANDO")
            self.db.actualizar_estado_documento(doc["id"], "DESCARGADO")

    lector = _DescargaQueTermina(db_memoria=base, run_id=58)
    lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 0}, {})

    assert estado_de(base, 1) == "DESCARGADO"


def test_un_return_silencioso_que_deje_el_estado_puesto_tambien_se_caza(base):
    """La comprobación pregunta por el hecho, no por el síntoma.

    Una excepción no es la única forma de varar un documento: un `return` añadido sin mover
    el estado tendría el mismo efecto y no lanzaría nada. Es el modo exacto en que este
    defecto podría volver mañana, y por eso la red mira la base y no el `except`.
    """
    sembrar(base, 1, "DETECTADO")

    class _DescargaQueSeVaSinDecirNada(Lector):
        def _descargar_documento_hilo(self, doc, domain_semaphores):
            self.db.actualizar_estado_documento(doc["id"], "DESCARGANDO")
            return

    lector = _DescargaQueSeVaSinDecirNada(db_memoria=base, run_id=58)
    lector._descargar_con_red_de_seguridad({"id": 1, "expediente_id": "EXP-1", "intentos": 0}, {})

    assert estado_de(base, 1) == "ERROR_DESCARGA"
