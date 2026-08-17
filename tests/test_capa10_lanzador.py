"""Capa 10, Pasos 2 y 3 — el healthcheck, la invariante de la sesión y la configuración.

Lo que se prueba aquí no es que el módulo importe, sino **lo que de verdad puede romperse**
en esta capa, que son cuatro cosas y ninguna es obvia:

1. **Que sin sesión interactiva no se invoque un solo elemento de interfaz gráfica.** Es la
   invariante central del contrato. Su fallo no se manifiesta como una excepción sino como
   una tarea nocturna que no termina nunca, de madrugada y sin nadie mirando: exactamente
   la clase de defecto que ninguna prueba encuentra por accidente.

2. **Que el cerrojo distinga un proceso vivo de un huérfano** (H-37). La reparación consiste
   en usar el cerrojo bueno, así que la regresión debe comprobar las dos direcciones: que un
   huérfano ya no bloquea *y* que uno vivo sigue bloqueando. Reparar sólo la primera mitad
   convertiría una protección en un adorno.

3. **Que comprobar no modifique nada.** El healthcheck corre antes de decidir si se arranca;
   si crea el directorio de datos por el camino, deja de ser un diagnóstico y pasa a ser una
   instalación a medias.

4. **Que una configuración incoherente detenga el arranque en vez de degradarlo** (Paso 3), y
   que el puerto configurable no rompa el Cockpit en silencio (H-38). Este último es el
   defecto más incómodo de la familia: las pantallas cargan, el sistema parece vivo y no hay
   ni un dato.
"""

import json
import os
import socket
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest

import yaml

from src.lanzador import (
    CONFIGURACION_INVALIDA,
    ERROR_NO_PREVISTO,
    ConfiguracionLanzadorInvalida,
    EstadoCerrojo,
    EstadoPuerto,
    HEALTHCHECK_INSATISFACTORIO,
    PIPELINE_FALLIDO,
    PIPELINE_OMITIDO,
    PUERTO_OCUPADO_AJENO,
    avisar_fallo_fatal,
    cargar_configuracion,
    comprobar_arranque,
    comunicar_fallo_fatal,
    ejecutar_healthcheck,
    es_sesion_interactiva,
    estado_del_puerto,
    inspeccionar_cerrojo,
    prospectar,
    registrar_evento_lanzador,
)
from src.memoria import Memoria
from src.proceso import instante_creacion_proceso

PID_MUERTO = 999999
TTL_DB_LOCK = 600.0


# ==============================================================================
# 1. La invariante central: ninguna llamada gráfica sin sesión interactiva
# ==============================================================================

def test_sin_sesion_interactiva_no_se_invoca_ni_un_elemento_grafico():
    """**La prueba que más importa de la capa.**

    Si esto falla, la tarea programada de madrugada abre un diálogo en la Session 0 y se
    queda esperando para siempre a un usuario que no existe.
    """
    user32 = MagicMock()
    with patch("src.lanzador.es_sesion_interactiva", return_value=False), \
         patch("ctypes.windll.user32", user32):
        mostrado = avisar_fallo_fatal("Título", "Mensaje de fallo fatal")

    assert mostrado is False
    user32.MessageBoxW.assert_not_called()


def test_con_sesion_interactiva_si_se_muestra_el_dialogo():
    """La otra mitad: suprimir siempre el diálogo también rompería el contrato, porque el
    fallo previo al Cockpit se quedaría sin ningún canal visible."""
    user32 = MagicMock()
    with patch("src.lanzador.es_sesion_interactiva", return_value=True), \
         patch("ctypes.windll.user32", user32):
        mostrado = avisar_fallo_fatal("Título", "Mensaje")

    assert mostrado is True
    user32.MessageBoxW.assert_called_once()


def test_ante_la_duda_es_sesion_interactiva_dice_que_no():
    """El valor por defecto seguro es `False`, por la asimetría del daño: un diálogo de más
    cuelga el proceso; uno de menos deja intactos el registro y el código de salida."""
    with patch("ctypes.windll.kernel32.ProcessIdToSessionId", side_effect=OSError("sin API")):
        assert es_sesion_interactiva() is False

    # La llamada "funciona" pero devuelve 0 (fallo según la convención de la API de Windows).
    with patch("ctypes.windll.kernel32.ProcessIdToSessionId", return_value=0):
        assert es_sesion_interactiva() is False


def test_la_omision_del_dialogo_deja_rastro(tmp_path):
    """Sin `LANZADOR_GUI_OMITIDA`, "no salió ningún diálogo en Session 0" es indistinguible
    de "no hubo ningún fallo del que avisar"."""
    db_path = str(tmp_path / "licitaciones.db")
    diagnostico = ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(),
        ruta_bundle=str(tmp_path / "no_existe"), db_path=db_path,
    )
    assert not diagnostico.satisfactorio  # falta el bundle

    with patch("src.lanzador.es_sesion_interactiva", return_value=False):
        with patch("src.lanzador._ruta_base", return_value=db_path):
            codigo = comunicar_fallo_fatal(diagnostico)

    assert codigo == HEALTHCHECK_INSATISFACTORIO
    acciones = _acciones_registradas(tmp_path / "pipeline.jsonl")
    assert "LANZADOR_GUI_OMITIDA" in acciones
    assert "LANZADOR_HEALTHCHECK_FALLIDO" in acciones


def _bundle_valido(tmp_path):
    bundle = tmp_path / "dist"
    bundle.mkdir(exist_ok=True)
    (bundle / "index.html").write_text("<html></html>", encoding="utf-8")
    return str(bundle)


def test_el_puerto_ajeno_tiene_codigo_de_salida_propio(tmp_path):
    """No es lo mismo "me falta una dependencia" que "alguien ocupa mi puerto": quien revise
    por qué no arrancó necesita distinguirlos sin abrir el registro.

    El entorno está **entero** salvo el puerto, que es cuando ese código significa algo.
    """
    with _servidor_ajeno() as puerto:
        diagnostico = ejecutar_healthcheck(
            host="127.0.0.1", puerto=puerto,
            ruta_bundle=_bundle_valido(tmp_path), db_path=str(tmp_path / "x.db"),
        )
        with patch("src.lanzador.es_sesion_interactiva", return_value=False), \
             patch("src.lanzador._ruta_base", return_value=str(tmp_path / "x.db")):
            codigo = comunicar_fallo_fatal(diagnostico)

    assert codigo == PUERTO_OCUPADO_AJENO


def test_con_varios_fallos_manda_el_del_entorno_no_el_del_puerto(tmp_path):
    """**Semántica que conviene dejar fijada**, porque con varios fallos un único código es
    por fuerza una simplificación.

    Si además del puerto falta el bundle, el código honesto es el 10: el entorno no está
    preparado, y liberar el puerto no lo arreglaría. El detalle de *todos* los fallos viaja
    en el resumen, que es lo que se muestra y se registra.
    """
    with _servidor_ajeno() as puerto:
        diagnostico = ejecutar_healthcheck(
            host="127.0.0.1", puerto=puerto,
            ruta_bundle=str(tmp_path / "sin_compilar"), db_path=str(tmp_path / "x.db"),
        )

    assert diagnostico.codigo_salida == HEALTHCHECK_INSATISFACTORIO
    assert len(diagnostico.fallos) == 2
    resumen = diagnostico.resumen()
    assert "Cockpit compilado" in resumen and "Puerto" in resumen, \
        "un único código simplifica, pero el resumen no puede esconder ningún fallo"


def test_comunicar_un_fallo_con_diagnostico_correcto_nunca_devuelve_cero(tmp_path):
    """Transición prohibida nº 5 del contrato: terminar en `DEGRADADO` con código 0. Si se
    pide comunicar un fallo que no existe, ha ocurrido algo no previsto — y eso tiene su
    propio código, el 1."""
    diagnostico = ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(),
        ruta_bundle=_bundle_valido(tmp_path), db_path=str(tmp_path / "x.db"),
    )
    assert diagnostico.satisfactorio

    with patch("src.lanzador.es_sesion_interactiva", return_value=False), \
         patch("src.lanzador._ruta_base", return_value=str(tmp_path / "x.db")):
        codigo = comunicar_fallo_fatal(diagnostico)

    assert codigo != 0
    assert codigo == ERROR_NO_PREVISTO


# ==============================================================================
# 2. H-37 — el cerrojo distingue un huérfano de un proceso vivo
# ==============================================================================

def _sembrar_cerrojo(db_path, contenido, antiguedad_seg=0.0):
    ruta = db_path + ".lock"
    with open(ruta, "w", encoding="utf-8") as fichero:
        if contenido is not None:
            fichero.write(contenido)
    if antiguedad_seg:
        import time
        instante = time.time() - antiguedad_seg
        os.utime(ruta, (instante, instante))
    return ruta


def test_h37_un_cerrojo_huerfano_ya_no_tumba_el_arranque(tmp_path):
    """**Regresión de H-37.** Antes de la reparación esto moría a los 5 s con un
    `RuntimeError`, porque `setup_db()` usaba un cerrojo propio que no sabía reclamar
    huérfanos — mientras `db_lock()`, sobre el mismo fichero, lo reclamaba en 0,0 s.

    Es el escenario que la propia Capa 10 activa: el apagado de nivel 3 (`TerminateProcess`)
    deja exactamente este cerrojo abandonado, y la corrida nocturna siguiente lo encuentra.
    """
    import time
    db_path = str(tmp_path / "licitaciones.db")
    _sembrar_cerrojo(db_path, json.dumps({"pid": PID_MUERTO, "created_at": time.time()}))

    Memoria(db_path=db_path).setup_db(timeout_cerrojo=10.0)

    assert os.path.exists(db_path), "la base debe haberse creado pese al cerrojo huérfano"


def test_h37_un_cerrojo_de_proceso_vivo_sigue_bloqueando(tmp_path):
    """La otra mitad de la reparación. Reparar sólo la primera convertiría la protección en
    un adorno: desde la Capa 9 el pipeline borra ficheros del disco, así que dos corridas
    simultáneas no son un desperdicio sino dos procesos destruyendo peso documental a la vez.
    """
    import time
    db_path = str(tmp_path / "licitaciones.db")
    _sembrar_cerrojo(db_path, json.dumps({"pid": os.getpid(), "created_at": time.time()}))

    with pytest.raises(RuntimeError):
        Memoria(db_path=db_path).setup_db(timeout_cerrojo=2.0)


def test_h37_un_cerrojo_ilegible_caduca_por_su_fecha(tmp_path):
    """Un cerrojo de 0 bytes —proceso muerto entre crear el fichero y escribir el payload—
    **no es huérfano por ser ilegible, sino por ser viejo**: recién creado puede pertenecer a
    un proceso que aún no ha escrito su contenido, y respetarlo es lo correcto. Caduca por su
    fecha de modificación una vez superado el TTL (lección del Paso D1)."""
    db_path = str(tmp_path / "licitaciones.db")

    _sembrar_cerrojo(db_path, "", antiguedad_seg=TTL_DB_LOCK + 60)
    Memoria(db_path=db_path).setup_db(timeout_cerrojo=10.0)
    assert os.path.exists(db_path)

    os.remove(db_path)
    _sembrar_cerrojo(db_path, "")
    with pytest.raises(RuntimeError):
        Memoria(db_path=db_path).setup_db(timeout_cerrojo=2.0)


# ==============================================================================
# 3. Comprobar no modifica nada
# ==============================================================================

def test_el_healthcheck_no_crea_el_directorio_de_datos(tmp_path):
    """`Memoria.__init__` crea el directorio de datos (reparación de H-24), así que la
    comprobación no puede instanciarla. Crear cosas es competencia de `ARRANCANDO`."""
    inexistente = tmp_path / "todavia_no" / "licitaciones.db"

    ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(), db_path=str(inexistente),
    )

    assert not inexistente.parent.exists(), "comprobar no puede crear el directorio de datos"
    assert not inexistente.exists()


def test_una_base_inexistente_no_es_un_fallo(tmp_path):
    """Es una instalación nueva, no una avería. Confundirlas es el diagnóstico confuso que
    esta capa existe para evitar (H-24: un clon limpio no arrancaba y el síntoma no decía
    por qué)."""
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.html").write_text("<html></html>", encoding="utf-8")

    diagnostico = ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(),
        ruta_bundle=str(bundle), db_path=str(tmp_path / "no_existe.db"),
    )

    assert diagnostico.satisfactorio, diagnostico.resumen()
    assert any("Base de datos" == aviso.nombre for aviso in diagnostico.avisos)


def test_un_bundle_ausente_da_diagnostico_y_remedio(tmp_path):
    """Es el primer síntoma que verá quien clone el repositorio sin compilar, y merece algo
    mejor que un 404 desnudo."""
    diagnostico = ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(),
        ruta_bundle=str(tmp_path / "sin_compilar"), db_path=str(tmp_path / "x.db"),
    )

    assert not diagnostico.satisfactorio
    fallo = next(c for c in diagnostico.fallos if c.nombre == "Cockpit compilado")
    assert fallo.remedio and "npm run build" in fallo.remedio
    assert "npm run build" in diagnostico.resumen()


def test_el_espacio_insuficiente_impide_arrancar(tmp_path):
    diagnostico = ejecutar_healthcheck(
        host="127.0.0.1", puerto=_puerto_libre(),
        espacio_minimo_mb=10 ** 9, db_path=str(tmp_path / "x.db"),
    )
    assert not diagnostico.satisfactorio
    assert any(c.nombre == "Espacio en disco" for c in diagnostico.fallos)


# ==============================================================================
# 4. Los tres estados del puerto
# ==============================================================================

def test_puerto_libre():
    estado, _ = estado_del_puerto("127.0.0.1", _puerto_libre())
    assert estado is EstadoPuerto.LIBRE


def test_puerto_ocupado_por_un_tercero():
    """Algo que contesta no es algo nuestro: es el error clásico de estos lanzadores."""
    with _servidor_ajeno() as puerto:
        estado, detalle = estado_del_puerto("127.0.0.1", puerto)
    assert estado is EstadoPuerto.AJENO
    assert detalle


def test_nuestra_api_se_reconoce_por_la_forma_de_la_respuesta():
    with _servidor_health(status="OK", codigo=200) as puerto:
        estado, detalle = estado_del_puerto("127.0.0.1", puerto)
    assert estado is EstadoPuerto.NUESTRA_API
    assert "status=OK" in (detalle or "")


def test_nuestra_api_degradada_sigue_siendo_nuestra():
    """Nuestro `/health` contesta **503** cuando el diagnóstico falla. Decidir por el código
    de estado la daría por ajena y el lanzador levantaría una segunda instancia contra la
    misma base. Por eso se comprueba la forma, no el código."""
    with _servidor_health(status="ERROR", codigo=503) as puerto:
        estado, _ = estado_del_puerto("127.0.0.1", puerto)
    assert estado is EstadoPuerto.NUESTRA_API


# ==============================================================================
# 5. Registro
# ==============================================================================

def test_el_evento_del_lanzador_usa_run_id_reservado_y_su_autor(tmp_path):
    db_path = str(tmp_path / "licitaciones.db")
    registrar_evento_lanzador("LANZADOR_INICIADO", motivo="modo=completo", db_path=db_path)

    entradas = _entradas_registradas(tmp_path / "pipeline.jsonl")
    assert len(entradas) == 1
    assert entradas[0]["run_id"] == 0, "0 es el valor reservado para eventos fuera de una corrida"
    assert entradas[0]["updated_by"] == "lanzador"
    assert entradas[0]["action"] == "LANZADOR_INICIADO"


# ==============================================================================
# 6. Configuración versionada (Paso 3) — sin valores por defecto
# ==============================================================================

def _config_valida():
    return {
        "lanzador": {
            "version": "1.0.0",
            "servidor": {
                "host": "127.0.0.1", "puerto": 8000,
                "espera_api_segundos": 30, "espacio_minimo_mb": 200,
            },
            "cockpit": {"ruta_bundle": "frontend/dist", "abrir_navegador": True},
            "apagado": {"gracia_endpoint_segundos": 10, "gracia_senal_segundos": 10},
            "despertador": {"hora": "06:30", "ejecutar_si_se_perdio": True},
        }
    }


def _escribir_config(tmp_path, transformar=None):
    datos = _config_valida()
    if transformar:
        transformar(datos["lanzador"])
    ruta = tmp_path / "lanzador.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return str(ruta)


def test_la_configuracion_real_del_proyecto_es_valida():
    """La que se distribuye tiene que cargar. Un fichero de ejemplo que no valida es una
    trampa para quien clone el repositorio."""
    config = cargar_configuracion()
    assert config.version
    assert config.servidor.puerto == 8000
    assert config.despertador.hora == "06:30"


def test_sin_fichero_no_se_arranca_con_valores_por_defecto(tmp_path):
    """La doctrina de `src/retencion.py` y la lección de H-18: un fichero ausente no puede
    degradarse a un comportamiento distinto que nadie ha pedido."""
    with pytest.raises(ConfiguracionLanzadorInvalida):
        cargar_configuracion(str(tmp_path / "no_existe.yaml"))


@pytest.mark.parametrize("mutacion, motivo", [
    (lambda c: c["servidor"].__setitem__("puerto", 80), "puerto privilegiado"),
    (lambda c: c["servidor"].__setitem__("puerto", 99999), "puerto inexistente"),
    (lambda c: c["servidor"].__setitem__("puerto", "8000"), "puerto como texto"),
    (lambda c: c["servidor"].__setitem__("puerto", True), "booleano colándose como entero"),
    (lambda c: c["servidor"].pop("host"), "falta el host"),
    (lambda c: c["despertador"].__setitem__("hora", "25:70"), "hora imposible"),
    (lambda c: c["despertador"].__setitem__("hora", "6:30"), "hora sin cero inicial"),
    (lambda c: c["cockpit"].__setitem__("abrir_navegador", "si"), "booleano deducido"),
    (lambda c: c.pop("version"), "sin versión no hay rastro reconstruible"),
    (lambda c: c.pop("apagado"), "falta un bloque entero"),
])
def test_una_configuracion_incoherente_se_rechaza(tmp_path, mutacion, motivo):
    """Cada caso es una forma real de equivocarse escribiendo YAML a mano.

    El de `True` como puerto no es rebuscado: `bool` es subclase de `int` en Python, así
    que una validación ingenua lo aceptaría como el puerto 1.
    """
    ruta = _escribir_config(tmp_path, mutacion)
    with pytest.raises(ConfiguracionLanzadorInvalida):
        cargar_configuracion(ruta)


def test_una_configuracion_ilegible_da_codigo_de_salida_propio(tmp_path):
    """`11` y no `10`: "no he podido leer el criterio" y "el entorno no cumple" son cosas
    distintas, y quien revise por qué no arrancó necesita distinguirlas."""
    ruta = tmp_path / "lanzador.yaml"
    ruta.write_text("lanzador: [esto no es un mapa", encoding="utf-8")

    config, diagnostico = comprobar_arranque(ruta_config=str(ruta), db_path=str(tmp_path / "x.db"))

    assert config is None
    assert not diagnostico.satisfactorio
    assert diagnostico.codigo_salida == CONFIGURACION_INVALIDA


def test_el_arranque_comprueba_el_puerto_que_declara_el_fichero(tmp_path):
    """Comprobar el 8000 porque es el de siempre, cuando el fichero declara otro, sería
    diagnosticar un sistema distinto del que se va a arrancar."""
    puerto = _puerto_libre()
    with _servidor_ajeno() as ocupado:
        ruta = _escribir_config(tmp_path, lambda c: c["servidor"].__setitem__("puerto", ocupado))
        _, diagnostico = comprobar_arranque(ruta_config=ruta, db_path=str(tmp_path / "x.db"))

        assert diagnostico.estado_puerto is EstadoPuerto.AJENO
        assert diagnostico.codigo_salida == PUERTO_OCUPADO_AJENO
    assert puerto != ocupado


def test_la_ruta_del_bundle_se_ancla_a_la_raiz_no_al_directorio_de_trabajo(tmp_path):
    """Lección de H-18, y la razón de que el acceso directo del Paso 7 no necesite fijar el
    directorio de trabajo: el de un acceso directo no es el que uno cree."""
    ruta = _escribir_config(tmp_path, lambda c: c["cockpit"].__setitem__("ruta_bundle", "frontend/dist"))
    config = cargar_configuracion(ruta)

    absoluta = config.ruta_bundle_absoluta()
    assert os.path.isabs(absoluta)
    assert os.path.isfile(os.path.join(absoluta, "index.html")), \
        "debe resolver al bundle real del proyecto, no a uno relativo al cwd"


def test_h38_el_cliente_del_cockpit_no_fija_ningun_puerto():
    """**Regresión de H-38, sobre el fuente.** `BASE_URL` llevaba
    `http://127.0.0.1:8000/api/v1` a fuego, de modo que desde el momento en que el puerto es
    configurable, arrancar en otro habría servido las pantallas correctamente mientras
    **todas** las llamadas de datos iban al 8000: el sistema parece vivo y no hay ni un dato.

    Esta mitad se comprueba siempre, porque el fuente está versionado.
    """
    from src import ruta_proyecto

    ruta = ruta_proyecto(os.path.join("frontend", "src", "lib", "api-client.ts"))
    with open(ruta, "r", encoding="utf-8") as fichero:
        contenido = fichero.read()

    codigo = "\n".join(
        linea for linea in contenido.splitlines()
        if not linea.lstrip().startswith("//")
    )
    assert "127.0.0.1:8000" not in codigo, \
        "la URL base vuelve a fijar un puerto; debe ser relativa al propio origen"
    assert "'/api/v1'" in codigo


def test_h38_el_bundle_compilado_tampoco_lo_lleva():
    """**La otra mitad, sobre lo que de verdad se sirve.**

    Se comprueba aparte porque `frontend/dist/` **no está versionado**: en un clon limpio no
    existe, y exigirlo convertiría una regresión en un fallo por no haber compilado. Pero
    cuando existe hay que mirarlo, porque el fuente puede estar arreglado y el bundle no —y
    lo que llega al navegador es el bundle—.
    """
    import glob
    from src import ruta_proyecto

    javascript = glob.glob(ruta_proyecto(os.path.join("frontend", "dist", "assets", "*.js")))
    if not javascript:
        pytest.skip("no hay bundle compilado; ejecutar «npm run build» dentro de frontend/")

    for fichero in javascript:
        with open(fichero, "r", encoding="utf-8") as f:
            contenido = f.read()
        assert "127.0.0.1:8000" not in contenido, (
            f"{os.path.basename(fichero)} lleva el puerto incrustado; "
            "recompilar con «npm run build» tras arreglar la URL base"
        )
        assert "/api/v1" in contenido, "el cliente debe seguir apuntando a la API por ruta relativa"


# ==============================================================================
# 7. El Cockpit servido por FastAPI (Paso 4)
# ==============================================================================

@pytest.fixture
def cliente_api():
    from fastapi.testclient import TestClient
    from src.api.main import app
    return TestClient(app)


def test_la_raiz_sirve_el_cockpit_y_ya_no_el_json(cliente_api):
    """**El cambio de contrato de la Capa 7**, declarado por adelantado en el contrato de la
    Capa 10 en vez de descubrirse."""
    respuesta = cliente_api.get("/")

    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert "<div id=\"root\">" in respuesta.text


def test_el_json_de_bienvenida_sigue_existiendo_bajo_api(cliente_api):
    """Trasladado, no eliminado: un cliente que lo usara debe poder seguir usándolo."""
    respuesta = cliente_api.get("/api/v1/")

    assert respuesta.status_code == 200
    assert respuesta.json()["app"] == "Incoop Licitaciones API"


@pytest.mark.parametrize("ruta", ["/docs", "/openapi.json", "/redoc", "/api/v1/health"])
def test_montar_el_cockpit_no_se_traga_la_api(cliente_api, ruta):
    """**La regresión que de verdad importa de este paso.**

    Starlette resuelve las rutas por orden de registro, así que montar los estáticos en `/`
    antes que los routers se tragaría la API entera sin avisar. El orden es la protección, y
    una protección que depende del orden de las líneas de un fichero necesita una prueba que
    lo sujete: nada en el código impide que alguien mueva el montaje veinte líneas arriba.
    """
    respuesta = cliente_api.get(ruta)
    assert respuesta.status_code != 404, f"{ruta} ha quedado tapada por los estáticos"


def test_una_ruta_inexistente_de_la_api_da_404_y_no_html(cliente_api):
    """Un reenvío en bloque al Cockpit convertiría una errata en un 200 con HTML: la
    aplicación contestaría que todo va bien mientras el cliente no recibe ni un dato. Es la
    familia de H-21, H-22 y H-23 — no rompe, miente."""
    respuesta = cliente_api.get("/api/v1/licitacionse")

    assert respuesta.status_code == 404
    assert "text/html" not in respuesta.headers.get("content-type", "")


def test_los_assets_del_cockpit_se_sirven(cliente_api):
    """Sin esto la raíz devolvería el HTML y la pantalla saldría en blanco: el `index.html`
    referencia `/assets/...` de forma absoluta."""
    import glob
    from src import ruta_proyecto

    activos = glob.glob(ruta_proyecto(os.path.join("frontend", "dist", "assets", "*.js")))
    if not activos:
        pytest.skip("no hay bundle compilado; ejecutar «npm run build» dentro de frontend/")

    respuesta = cliente_api.get(f"/assets/{os.path.basename(activos[0])}")
    assert respuesta.status_code == 200


def test_el_cockpit_servido_no_se_llama_frontend(cliente_api):
    """El `index.html` declaraba `<title>frontend</title>`, el título por defecto de Vite.
    Daba igual mientras lo servía un servidor de desarrollo; desde que FastAPI lo sirve como
    la aplicación de verdad, es lo que pone en la pestaña del navegador de la cooperativa."""
    respuesta = cliente_api.get("/")

    assert "<title>frontend</title>" not in respuesta.text
    assert "Incoop" in respuesta.text
    assert 'lang="es"' in respuesta.text


def test_sin_bundle_el_diagnostico_dice_que_compilar(monkeypatch):
    """Regresión pedida por el README: un bundle ausente debe dar un diagnóstico claro y no
    un 404 desnudo. Es el primer síntoma que verá quien clone el repositorio sin compilar."""
    import src.api.main as api_main

    monkeypatch.setattr(api_main, "_hay_bundle", lambda: False)
    from fastapi.testclient import TestClient

    with TestClient(api_main.app) as cliente:
        respuesta = cliente.get("/")

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["error_code"] == "COCKPIT_NO_COMPILADO"
    assert "npm run build" in cuerpo["message"]


# ==============================================================================
# 8. Supervisor del servidor (Paso 5) — sólo se apaga lo que se encendió
# ==============================================================================

def test_la_identidad_de_un_proceso_no_es_su_numero():
    """Windows recicla los PID. El instante de creación no, así que el par (pid, instante)
    es lo que identifica — y es lo que impide que "apago sólo lo mío" mate algo inocente que
    heredó el número."""
    from src.lanzador import es_nuestro_proceso, instante_creacion_proceso

    mio = os.getpid()
    instante = instante_creacion_proceso(mio)

    assert instante is not None
    assert instante_creacion_proceso(mio) == instante, "debe ser estable entre consultas"
    assert instante_creacion_proceso(PID_MUERTO) is None
    assert es_nuestro_proceso(mio, instante) is True


def test_un_pid_reciclado_no_se_confunde_con_el_nuestro():
    """**El defecto que este paso existe para evitar.** Mismo número, proceso distinto: la
    respuesta correcta es "no es el mío", y por tanto no se toca."""
    from src.lanzador import es_nuestro_proceso

    instante_falso = 1  # un instante que no puede ser el de ningún proceso vivo
    assert es_nuestro_proceso(os.getpid(), instante_falso) is False


def test_sin_instante_anotado_no_se_mata_nada():
    """Ante la duda, no. Misma asimetría que gobierna `es_sesion_interactiva()`: no apagar
    deja un proceso de más, visible y molesto; apagar el que no era tumba el trabajo de
    alguien."""
    from src.lanzador import es_nuestro_proceso

    assert es_nuestro_proceso(os.getpid(), None) is False


def test_el_apagado_no_toca_un_servidor_que_el_lanzador_no_encendio(tmp_path):
    """**Transición prohibida nº 4 del contrato.** Si alguien levantó la API a mano para
    desarrollar, se usa pero no se mata al terminar."""
    from src.lanzador import apagar_servidor, cargar_configuracion

    config = cargar_configuracion(_escribir_config(tmp_path))
    # No hay marca: no consta que hayamos arrancado nada.
    assert apagar_servidor(config, db_path=str(tmp_path / "x.db")) == "sin_marca"


def test_una_marca_de_un_proceso_ajeno_no_dispara_ningun_apagado(tmp_path):
    """La marca existe pero señala a un proceso que ya no es el nuestro —murió, y su número
    lo heredó otro—. Se retira la marca y no se mata a nadie."""
    from src.lanzador import (MarcaServidor, apagar_servidor, cargar_configuracion,
                              escribir_marca_servidor, ruta_marca_servidor)

    db_path = str(tmp_path / "x.db")
    config = cargar_configuracion(_escribir_config(tmp_path))
    escribir_marca_servidor(
        MarcaServidor(pid=os.getpid(), instante_creacion=1, host="127.0.0.1",
                      puerto=8000, testigo="t", iniciado_at="2026-08-13T00:00:00Z"),
        db_path=db_path,
    )

    assert apagar_servidor(config, db_path=db_path) == "ya_no_estaba"
    assert not os.path.exists(ruta_marca_servidor(db_path)), "la marca caduca debe retirarse"


def test_una_marca_ilegible_se_trata_como_ausente(tmp_path):
    """No es un error: significa que no consta que hayamos arrancado nada, y la conducta
    correcta ante eso es no apagar nada."""
    from src.lanzador import leer_marca_servidor, ruta_marca_servidor

    db_path = str(tmp_path / "x.db")
    ruta = ruta_marca_servidor(db_path)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fichero:
        fichero.write("{esto no es json")

    assert leer_marca_servidor(db_path) is None


def test_esperar_api_se_rinde_y_lo_dice(tmp_path):
    """Se espera consultando, no durmiendo; y si no contesta se informa en vez de abrir un
    navegador sobre nada."""
    from src.lanzador import esperar_api

    assert esperar_api("127.0.0.1", _puerto_libre(), tope_segundos=1) is None


def test_el_endpoint_de_apagado_rechaza_lo_que_no_venga_de_la_maquina():
    """El Cockpit no tiene autenticación: si el apagado aceptara peticiones de la red, quien
    llegara al puerto podría tumbar el sistema."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    cliente = TestClient(app, client=("192.168.1.50", 50000))
    respuesta = cliente.post("/api/v1/admin/apagar", json={"testigo": "loquesea"})

    assert respuesta.status_code == 403


def test_el_endpoint_de_apagado_exige_marca_y_testigo(tmp_path, monkeypatch):
    """Sin marca no se apaga —este servidor no lo arrancó el lanzador— y con marca, el
    testigo tiene que coincidir: sin él, cualquier página abierta en el navegador podría
    apagar el servidor con un formulario."""
    from fastapi.testclient import TestClient
    import src.api.routers.admin as admin_router
    from src.lanzador import MarcaServidor
    from src.api.main import app

    cliente = TestClient(app, client=("127.0.0.1", 50000))

    monkeypatch.setattr(admin_router, "leer_marca_servidor", lambda *a, **k: None)
    assert cliente.post("/api/v1/admin/apagar", json={"testigo": "x"}).status_code == 409

    marca = MarcaServidor(pid=os.getpid(), instante_creacion=1, host="127.0.0.1",
                          puerto=8000, testigo="el-bueno", iniciado_at="")
    monkeypatch.setattr(admin_router, "leer_marca_servidor", lambda *a, **k: marca)
    assert cliente.post("/api/v1/admin/apagar", json={"testigo": "el-malo"}).status_code == 403


def test_el_testigo_no_tiene_valor_por_defecto():
    """Mismo criterio que la confirmación de purga del Paso 8 de la Capa 9: un campo con
    valor por defecto convierte "se me olvidó enviarlo" en "sí, adelante"."""
    from fastapi.testclient import TestClient
    from src.api.main import app

    cliente = TestClient(app, client=("127.0.0.1", 50000))
    assert cliente.post("/api/v1/admin/apagar", json={}).status_code == 422


# ==============================================================================
# Utilidades
# ==============================================================================

def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _entradas_registradas(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, "r", encoding="utf-8") as fichero:
        return [json.loads(linea) for linea in fichero if linea.strip()]


def _acciones_registradas(ruta):
    return [entrada["action"] for entrada in _entradas_registradas(ruta)]


class _ServidorDePrueba:
    """Servidor HTTP mínimo en un hilo, para ejercitar los tres estados del puerto."""

    def __init__(self, manejador):
        self.servidor = HTTPServer(("127.0.0.1", 0), manejador)
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def __enter__(self) -> int:
        self.hilo.start()
        return self.servidor.server_address[1]

    def __exit__(self, *_):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=5)


def _servidor_ajeno():
    class Ajeno(BaseHTTPRequestHandler):
        def do_GET(self):
            cuerpo = b"<html>Otra aplicacion cualquiera</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *_):
            pass

    return _ServidorDePrueba(Ajeno)


def _servidor_health(status: str, codigo: int):
    """Réplica de la forma real de `HealthResponseSchema`."""
    class Salud(BaseHTTPRequestHandler):
        def do_GET(self):
            cuerpo = json.dumps({
                "status": status,
                "timestamp": "2026-08-13T00:00:00Z",
                "db_path": "C:/ruta/licitaciones.db",
                "directorio_accesible": True,
                "wal_mode_active": True,
                "schema_version": 7,
                "query_test_ok": True,
                "error": None,
            }).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *_):
            pass

    return _ServidorDePrueba(Salud)


# ==============================================================================
# 5. Paso 6 — prospectar respetando el cerrojo
# ==============================================================================
#
# Dos defectos gobiernan esta sección, y los dos salieron de leer el código contra el
# contrato en vez de leer sólo el contrato:
#
# · **El cerrojo que decide es el de EJECUCIÓN, no el de fichero** (contrato v1.1.0,
#   sección F). `db_lock()` se toma y se suelta en cada escritura, así que una comprobación
#   basada en su fichero se ejecutaría siempre sin detectar casi nunca la corrida
#   concurrente que dice impedir.
#
# · **El resultado se lee de la base, no del código de salida del proceso** (H-40 y la
#   corrección del contrato): `main.py` sale con `0` cuando falla a mitad, que es el modo de
#   fallo más frecuente. Fiarse del código convertiría una prospección reventada en una
#   noche sana a ojos del Programador de tareas.

def _base_lista(tmp_path):
    """Una base real, migrada, sin ninguna corrida en marcha."""
    ruta = str(tmp_path / "licitaciones.db")
    Memoria(db_path=ruta).setup_db()
    return ruta


def _sembrar_corrida(db_path, estado="RUNNING", pid=None, instante="123456789"):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ejecuciones (start_time, estado, pid, pid_creado_en) VALUES (?, ?, ?, ?);",
            (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), estado, pid, instante),
        )


def _pipeline_simulado(ruta, estado, codigo=0):
    """Un pipeline de mentira que se comporta como el de verdad: escribe su fila y sale.

    Se invoca como **subproceso real** —no se sustituye `subprocess.run`— para que la prueba
    ejercite el lanzamiento de verdad, incluidos el volcado del registro y la lectura
    posterior de la base.
    """
    script = (
        "import sqlite3, sys\n"
        "ruta, estado, codigo = sys.argv[1], sys.argv[2], int(sys.argv[3])\n"
        "if estado != 'NINGUNA':\n"
        "    c = sqlite3.connect(ruta)\n"
        "    c.execute(\"INSERT INTO ejecuciones (start_time, estado) VALUES "
        "('2026-08-17T00:00:00Z', ?)\", (estado,))\n"
        "    c.commit(); c.close()\n"
        "print('pipeline simulado:', estado)\n"
        "sys.exit(codigo)\n"
    )
    return [sys.executable, "-c", script, ruta, estado, str(codigo)]


# --- El cerrojo decide, y decide el correcto -------------------------------------------

def test_una_corrida_viva_omite_la_prospeccion_con_codigo_propio(tmp_path):
    """Transición prohibida nº 2. El `30` no es una avería: es la protección funcionando.

    Pero tampoco puede ser un `0`, o el Programador registraría una noche sana en la que no
    se prospectó nada — y esa mentira sólo se descubre cuando alguien echa en falta las
    oportunidades de tres semanas.
    """
    db_path = _base_lista(tmp_path)
    _sembrar_corrida(db_path, pid=os.getpid(), instante=str(instante_creacion_proceso(os.getpid())))

    with patch("src.lanzador.subprocess.run") as lanzamiento:
        codigo = prospectar(db_path=db_path)

    assert codigo == PIPELINE_OMITIDO == 30
    lanzamiento.assert_not_called()  # lo que de verdad importa: no se lanzó nada
    assert "LANZADOR_PIPELINE_OMITIDO" in _acciones_registradas(tmp_path / "pipeline.jsonl")


def test_una_corrida_muerta_no_impide_prospectar_y_su_fila_no_se_toca(tmp_path):
    """Transición prohibida nº 3: el lanzador **detecta e informa**, nunca reclama.

    Quien sabe reclamar es `iniciar_ejecucion()`. Un lanzador que fuerce cerrojos anula la
    protección que la Capa 9 necesita, así que aquí se comprueba que la fila huérfana sigue
    exactamente como estaba después de que el lanzador la haya visto.
    """
    db_path = _base_lista(tmp_path)
    _sembrar_corrida(db_path, pid=PID_MUERTO)

    codigo = prospectar(db_path=db_path, comando=_pipeline_simulado(db_path, "COMPLETED"))

    assert codigo == 0
    with sqlite3.connect(db_path) as conn:
        estado = conn.execute("SELECT estado FROM ejecuciones ORDER BY id LIMIT 1;").fetchone()[0]
    assert estado == "RUNNING"  # intacta: el lanzador no la reclamó por su cuenta
    assert "LANZADOR_CERROJO_EJECUCION_HUERFANO" in _acciones_registradas(tmp_path / "pipeline.jsonl")


def test_el_cerrojo_de_fichero_es_diagnostico_y_no_criterio(tmp_path):
    """El defecto que la v1.1.0 del contrato corrigió **antes** de escribirse.

    Un `.lock` presente significa "hay una escritura en vuelo", no "hay una corrida en
    marcha": lo toma y lo suelta cada operación de escritura. Si gobernara la decisión, el
    Cockpit guardando el estado de un lote impediría prospectar.
    """
    db_path = _base_lista(tmp_path)
    open(db_path + ".lock", "w").close()

    diagnostico = inspeccionar_cerrojo(db_path=db_path)

    assert diagnostico.escritura_en_vuelo is True     # se ve...
    assert diagnostico.estado is EstadoCerrojo.LIBRE  # ...pero no decide
    assert diagnostico.puede_prospectar is True


# --- Comprobar no modifica nada ---------------------------------------------------------

def test_inspeccionar_no_crea_la_base_ni_el_directorio(tmp_path):
    """Misma doctrina que el healthcheck del Paso 2: instanciar `Memoria()` crearía el
    directorio de datos (H-24), y una comprobación previa no puede dejar una instalación a
    medias. Una base inexistente no es una avería: es una instalación nueva y nadie está
    prospectando."""
    inexistente = tmp_path / "sin_crear" / "licitaciones.db"

    diagnostico = inspeccionar_cerrojo(db_path=str(inexistente))

    assert diagnostico.estado is EstadoCerrojo.LIBRE
    assert not inexistente.exists()
    assert not inexistente.parent.exists()


def test_inspeccionar_no_escribe_en_una_base_existente(tmp_path):
    """Se abre en `mode=ro`, de modo que no puede crear ni siquiera los ficheros del WAL."""
    db_path = _base_lista(tmp_path)
    antes = os.path.getmtime(db_path)

    for _ in range(3):
        inspeccionar_cerrojo(db_path=db_path)

    assert os.path.getmtime(db_path) == antes


# --- La traducción del resultado --------------------------------------------------------

@pytest.mark.parametrize(
    "estado_corrida, codigo_proceso, esperado, motivo",
    [
        ("COMPLETED", 0, 0, "corrida completada: el único camino al éxito"),
        ("FAILED", 0, 31, "el caso que hoy pasaría por sano: sale con 0 sobre una corrida rota"),
        ("COMPLETED", 1, 31, "el código del proceso manda cuando es distinto de cero"),
        ("RUNNING", 0, 31, "salió sin cerrar su propia corrida"),
        ("NINGUNA", 0, 31, "terminó con 0 sin llegar a registrar nada"),
    ],
)
def test_el_resultado_se_lee_de_la_base_y_no_del_codigo_de_salida(
    tmp_path, estado_corrida, codigo_proceso, esperado, motivo
):
    db_path = _base_lista(tmp_path)

    codigo = prospectar(
        db_path=db_path,
        comando=_pipeline_simulado(db_path, estado_corrida, codigo_proceso),
    )

    assert codigo == esperado, motivo


def test_una_prospeccion_fallida_deja_dicho_que_fallo(tmp_path):
    db_path = _base_lista(tmp_path)

    prospectar(db_path=db_path, comando=_pipeline_simulado(db_path, "FAILED", 0))

    assert "LANZADOR_PIPELINE_FALLIDO" in _acciones_registradas(tmp_path / "pipeline.jsonl")


def test_lo_que_el_pipeline_imprime_no_se_pierde(tmp_path):
    """El `.vbs` del Paso 7 arranca sin consola y la tarea del Paso 8 corre en Session 0:
    sin volcado, todo lo que el pipeline dice por pantalla desaparecería."""
    db_path = _base_lista(tmp_path)

    prospectar(db_path=db_path, comando=_pipeline_simulado(db_path, "COMPLETED"))

    registros = list((tmp_path / "logs").glob("prospeccion_*.log"))
    assert registros, "no se escribió el registro de la prospección"
    assert "pipeline simulado" in registros[0].read_text(encoding="utf-8")


def test_un_pipeline_ininvocable_es_un_fallo_no_una_excepcion(tmp_path):
    """Un lanzador que revienta con una traza deja al Programador sin saber qué pasó, y en
    modo silencioso ni siquiera hay consola donde verla."""
    db_path = _base_lista(tmp_path)

    codigo = prospectar(db_path=db_path, comando=["no_existe_este_programa_xyz"])

    assert codigo == PIPELINE_FALLIDO == 31
    assert "LANZADOR_PIPELINE_FALLIDO" in _acciones_registradas(tmp_path / "pipeline.jsonl")


# --- La ruta real, sin inyectar (Convención C4) -----------------------------------------

def test_el_pipeline_se_invoca_por_run_py_y_nunca_por_src_main(tmp_path):
    """C1: `python src/main.py` cargaba el mismo fichero como dos objetos-módulo distintos y
    mataba la Capa 6 en silencio (H-01). El lanzador es un invocador nuevo, así que la
    convención hay que sujetarla también aquí: sin esta prueba, nada impide que alguien
    "simplifique" la orden apuntando al módulo."""
    db_path = _base_lista(tmp_path)

    with patch("src.lanzador.subprocess.run") as lanzamiento:
        lanzamiento.return_value = MagicMock(returncode=0)
        prospectar(db_path=db_path)

    orden = lanzamiento.call_args[0][0]
    assert orden[0] == sys.executable
    assert orden[1].endswith("run.py")
    assert "main.py" not in orden[1]


def test_el_pipeline_prospecta_sobre_la_misma_base_que_se_inspecciono(tmp_path):
    """Descubierto cometiéndolo, el 2026-08-17, durante la verificación en vivo.

    `prospectar(db_path=X)` inspeccionaba el cerrojo de X y lanzaba un pipeline que escribía
    en la base por defecto: apuntando a una copia se arrancó una prospección real contra
    producción. **Un parámetro que sólo gobierna la mitad de la operación no es un
    parámetro, es una trampa.**

    La prueba no comprueba la variable de entorno sino su efecto: el subproceso construye un
    `Memoria()` sin argumentos —como hace `main.py`— y anota contra qué fichero acabó
    hablando. Comprobar el mecanismo en vez del efecto habría dejado pasar el defecto.
    """
    db_path = _base_lista(tmp_path)
    testigo = tmp_path / "base_vista_por_el_pipeline.txt"
    script = (
        "import sys\n"
        f"sys.path.insert(0, r'{os.getcwd()}')\n"
        "from src.memoria import Memoria\n"
        f"open(r'{testigo}', 'w').write(Memoria().db_path)\n"
    )

    prospectar(db_path=db_path, comando=[sys.executable, "-c", script])

    assert os.path.normcase(testigo.read_text().strip()) == os.path.normcase(db_path)


def test_inspeccionar_funciona_sobre_la_ruta_por_defecto_sin_inyectar_nada():
    """C4: la ruta que se usa de verdad es la que nadie prueba. `db_path=None` resuelve
    contra `ruta_datos()`, que en la suite apunta al directorio temporal de `conftest.py`."""
    diagnostico = inspeccionar_cerrojo()

    assert isinstance(diagnostico.estado, EstadoCerrojo)
    assert diagnostico.detalle
