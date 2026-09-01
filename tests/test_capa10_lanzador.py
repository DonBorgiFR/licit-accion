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
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest

import yaml

from src.lanzador import (
    APAGADO_INCOMPLETO,
    CONFIGURACION_INVALIDA,
    ERROR_NO_PREVISTO,
    EXITO,
    NOMBRE_PERFIL_COCKPIT,
    SERVIDOR_NO_RESPONDE,
    ApagadoIncompleto,
    AperturaCockpit,
    ConfiguracionLanzadorInvalida,
    EstadoCerrojo,
    EstadoPuerto,
    HEALTHCHECK_INSATISFACTORIO,
    ModoApertura,
    ModoInvocacion,
    PIPELINE_AGOTADO,
    PIPELINE_FALLIDO,
    PIPELINE_OMITIDO,
    PUERTO_OCUPADO_AJENO,
    ServidorNoRespondio,
    _degradar,
    abrir_cockpit,
    avisar_fallo_fatal,
    cargar_configuracion,
    comprobar_arranque,
    comunicar_fallo_fatal,
    ejecutar_healthcheck,
    es_sesion_interactiva,
    estado_del_puerto,
    inspeccionar_cerrojo,
    localizar_navegador,
    main,
    orquestar,
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
    assert entradas[0].run_id == 0, "0 es el valor reservado para eventos fuera de una corrida"
    assert entradas[0].componente == "lanzador"
    assert entradas[0].evento == "LANZADOR_INICIADO"


# ==============================================================================
# 6. Configuración versionada (Paso 3) — sin valores por defecto
# ==============================================================================

def _config_valida():
    return {
        "lanzador": {
            "version": "1.1.0",
            "servidor": {
                "host": "127.0.0.1", "puerto": 8000,
                "espera_api_segundos": 30, "espacio_minimo_mb": 200,
            },
            "cockpit": {"ruta_bundle": "frontend/dist", "abrir_navegador": True},
            "apagado": {"gracia_endpoint_segundos": 10, "gracia_senal_segundos": 10},
            # `duracion_maxima_minutos` es obligatorio desde el Paso 8, como todo en este
            # fichero: no hay valores por defecto. Que añadirlo tumbara 23 pruebas de golpe
            # no es una molestia del diseño, es el diseño funcionando — la misma señal que
            # recibiría quien actualizara el código sin actualizar su configuración.
            "despertador": {
                "hora": "06:30",
                "ejecutar_si_se_perdio": True,
                "duracion_maxima_minutos": 60,
            },
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
    """Los eventos del rastro, leídos por la única puerta que hay desde el Paso 9.

    Antes abría el fichero y leía `entrada["action"]` a mano, que es la gramática que el
    lanzador escribía él solo. Desde el bloque 9.C **todos los escritores hablan el mismo
    idioma**, así que la comprobación pasa por `leer_rastro()` — y de paso estas pruebas dejan
    de ser un octavo lector del fichero con criterio propio, que es como nació H-39.
    """
    from src.rastro import leer_rastro

    return leer_rastro(ruta=str(ruta)).eventos


def _acciones_registradas(ruta):
    return [entrada.evento for entrada in _entradas_registradas(ruta)]


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


# --- El tope de duración: que un cuelgue se note (Paso 8) -------------------------------
#
# La cuestión que bloqueó este paso desde el 2026-08-17. Mientras el pipeline lo lanzaba una
# persona, un cuelgue se veía: la consola dejaba de avanzar. Desde el despertador corre de
# madrugada y sin nadie mirando, y un pipeline colgado sigue VIVO — así que el cerrojo haría
# lo correcto, código 30, noche tras noche, y el sistema no parecería averiado sino vacío de
# oportunidades. Es la familia de H-21: no rompe, calla.

def _pipeline_que_no_termina():
    """Un pipeline que se queda dormido. Subproceso real, no un simulacro de reloj.

    Medir el tope contra un `time.sleep` parcheado comprobaría la aritmética; lo que hace
    falta comprobar es que **el proceso se muere**, y para eso tiene que haber un proceso.
    """
    return [sys.executable, "-c", "import time; time.sleep(300)"]


def test_un_pipeline_que_no_acaba_se_detiene_con_su_propio_codigo(tmp_path):
    """El `32` y no el `31`: 'no acababa' y 'reventó' piden reacciones distintas."""
    db_path = _base_lista(tmp_path)

    codigo = prospectar(
        db_path=db_path,
        comando=_pipeline_que_no_termina(),
        tope_segundos=2,
        gracia_segundos=2,
    )

    assert codigo == PIPELINE_AGOTADO
    assert codigo != PIPELINE_FALLIDO, "un cuelgue se está contando como un fallo del pipeline"


def test_el_pipeline_colgado_queda_muerto_de_verdad(tmp_path):
    """Lo que importa no es el código que devolvemos, es que no quede un proceso vivo.

    Un tope que devuelve `32` y deja el pipeline corriendo sería peor que no tener tope:
    añadiría una mentira al problema que ya había.
    """
    db_path = _base_lista(tmp_path)
    procesos = []
    popen_real = subprocess.Popen

    def espiar(*args, **kwargs):
        proceso = popen_real(*args, **kwargs)
        procesos.append(proceso)
        return proceso

    with patch("src.lanzador.subprocess.Popen", side_effect=espiar):
        prospectar(
            db_path=db_path,
            comando=_pipeline_que_no_termina(),
            tope_segundos=2,
            gracia_segundos=2,
        )

    assert len(procesos) == 1
    assert procesos[0].poll() is not None, "el pipeline sigue vivo después de 'detenerlo'"


def test_el_agotamiento_queda_registrado_con_su_evento(tmp_path):
    """Convención C2: nada ocurre en silencio, y menos algo que mata un proceso."""
    db_path = _base_lista(tmp_path)

    prospectar(
        db_path=db_path,
        comando=_pipeline_que_no_termina(),
        tope_segundos=2,
        gracia_segundos=2,
    )

    acciones = _acciones_registradas(tmp_path / "pipeline.jsonl")
    assert "LANZADOR_PIPELINE_AGOTADO" in acciones
    assert "LANZADOR_PIPELINE_FALLIDO" not in acciones, "se registró además como fallo"


def test_un_pipeline_que_acaba_a_tiempo_no_se_toca(tmp_path):
    """El tope no puede convertirse en una guillotina para corridas legítimas."""
    db_path = _base_lista(tmp_path)

    codigo = prospectar(
        db_path=db_path,
        comando=_pipeline_simulado(db_path, "COMPLETED"),
        tope_segundos=120,
    )

    assert codigo == EXITO
    assert "LANZADOR_PIPELINE_AGOTADO" not in _acciones_registradas(tmp_path / "pipeline.jsonl")


def test_sin_tope_se_espera_indefinidamente(tmp_path):
    """`None` es esperar sin plazo, y es lo correcto para el modo con alguien delante.

    Ponerle un tope a quien está mirando la pantalla sería inventarle un plazo (Regla 4).
    """
    db_path = _base_lista(tmp_path)

    codigo = prospectar(db_path=db_path, comando=_pipeline_simulado(db_path, "COMPLETED"))

    assert codigo == EXITO


# --- El tope, en la configuración ------------------------------------------------------

def test_sin_tope_declarado_no_se_arranca(tmp_path):
    """Como todo en este fichero: no hay valores por defecto. Un plazo inventado aquí sería
    repetir lo que hizo que los 90 días de retención vivieran codificados a fuego."""
    ruta = _escribir_config(tmp_path, lambda c: c["despertador"].pop("duracion_maxima_minutos"))

    with pytest.raises(ConfiguracionLanzadorInvalida, match="duracion_maxima_minutos"):
        cargar_configuracion(ruta)


@pytest.mark.parametrize("valor", [0, -5, "60", 60.5, True, None])
def test_un_tope_que_no_es_un_entero_positivo_se_rechaza(tmp_path, valor):
    """El `0` es el peligroso: significaría 'mata el pipeline antes de empezar', y un
    descuido lo convertiría en un sistema que no prospecta nunca sin decir por qué."""
    ruta = _escribir_config(
        tmp_path, lambda c: c["despertador"].update({"duracion_maxima_minutos": valor})
    )

    with pytest.raises(ConfiguracionLanzadorInvalida):
        cargar_configuracion(ruta)


def test_el_tope_se_convierte_a_segundos_en_un_solo_sitio(tmp_path):
    """Minutos porque es la unidad en la que una persona piensa un plazo nocturno; segundos
    porque es la que entiende quien espera a un proceso. La conversión vive en un sitio."""
    config = cargar_configuracion(_escribir_config(tmp_path))

    assert config.despertador.duracion_maxima_minutos == 60
    assert config.despertador.duracion_maxima_segundos() == 3600


# --- La ruta real, sin inyectar (Convención C4) -----------------------------------------

def test_el_pipeline_se_invoca_por_run_py_y_nunca_por_src_main(tmp_path):
    """C1: `python src/main.py` cargaba el mismo fichero como dos objetos-módulo distintos y
    mataba la Capa 6 en silencio (H-01). El lanzador es un invocador nuevo, así que la
    convención hay que sujetarla también aquí: sin esta prueba, nada impide que alguien
    "simplifique" la orden apuntando al módulo."""
    db_path = _base_lista(tmp_path)

    # Se vigila `Popen` y no `run` desde el Paso 8: el pipeline ya no se lanza y se espera en
    # una sola llamada, porque hay que poder mirarle el reloj y detenerlo. Lo que esta prueba
    # sujeta no es cuál de las dos se usa, sino **qué orden se construye**.
    with patch("src.lanzador.subprocess.Popen") as lanzamiento:
        proceso = MagicMock()
        proceso.wait.return_value = 0
        proceso.returncode = 0
        lanzamiento.return_value = proceso
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


# ==============================================================================
# 6. Paso 7 — el orquestador, la ventana y el doble clic
# ==============================================================================
#
# Aquí se prueban tres cosas que no se prueban solas:
#
# · **Que el modo del despertador no toca una sola pieza gráfica.** Es la invariante central
#   vista desde el orquestador, y su fallo no se manifiesta como excepción sino como un
#   proceso que no termina nunca, de madrugada y sin nadie mirando.
#
# · **Que sólo se apaga lo que encendió esta invocación**, y que el apagado espera a que se
#   cierre la ventana en vez de adivinar cuándo ha terminado el trabajo.
#
# · **Que al modo «sólo pipeline» no se le exige lo que no usa.** Un bundle sin compilar o un
#   puerto ocupado por un tercero no pueden costar una noche entera sin prospectar: la
#   prospección habla con SQLite y no necesita ni pantalla ni puerto.


def _config_orquestar(tmp_path, transformar=None, puerto=None):
    """Configuración válida con puerto propio: ninguna prueba se acerca al 8000 real."""
    elegido = puerto or _puerto_libre()

    def ajustar(lanzador):
        lanzador["servidor"]["puerto"] = elegido
        if transformar:
            transformar(lanzador)

    return _escribir_config(tmp_path, ajustar), elegido


def _registro(tmp_path):
    return str(tmp_path / "pipeline.jsonl")


# --- El healthcheck manda, y lo que no se usa no se exige ------------------------------

def test_un_healthcheck_insatisfactorio_no_arranca_absolutamente_nada(tmp_path):
    """Transición prohibida nº 1. Arrancar sobre un entorno que no cumple cambia un
    diagnóstico preciso por un fallo confuso diez segundos después."""
    ruta_config, _ = _config_orquestar(tmp_path, lambda l: l["servidor"].update({"puerto": 70000}))
    db = str(tmp_path / "licitaciones.db")

    with patch("src.lanzador.arrancar_servidor") as arrancar, \
         patch("src.lanzador.abrir_cockpit") as abrir, \
         patch("src.lanzador.prospectar") as prospectar_falso, \
         patch("src.lanzador.es_sesion_interactiva", return_value=False):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == CONFIGURACION_INVALIDA
    arrancar.assert_not_called()
    abrir.assert_not_called()
    prospectar_falso.assert_not_called()

    acciones = _acciones_registradas(_registro(tmp_path))
    assert "LANZADOR_HEALTHCHECK_FALLIDO" in acciones
    assert "LANZADOR_DEGRADADO" in acciones
    assert "LANZADOR_INICIADO" not in acciones


def test_al_modo_pipeline_no_se_le_exige_bundle_ni_puerto(tmp_path):
    """**La noche que no se prospectó por culpa de una pantalla que nadie iba a mirar.**

    Prospectar no sirve el Cockpit ni abre puerto: exigirle un bundle compilado o un puerto
    libre convertiría un requisito ajeno en una avería nocturna, y el Programador de tareas
    registraría un 10 o un 20 incomprensibles.
    """
    db = _base_lista(tmp_path)
    inexistente = str(tmp_path / "bundle_que_no_existe")

    with _servidor_ajeno() as puerto_ocupado:
        ruta_config, _ = _config_orquestar(
            tmp_path,
            lambda l: l["cockpit"].update({"ruta_bundle": inexistente}),
            puerto=puerto_ocupado,
        )
        with patch("src.lanzador.prospectar", return_value=EXITO) as prospectar_falso, \
             patch("src.lanzador.arrancar_servidor") as arrancar:
            codigo = orquestar(ModoInvocacion.PIPELINE, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    prospectar_falso.assert_called_once()
    arrancar.assert_not_called()


def test_al_modo_completo_si_se_le_exige_el_bundle(tmp_path):
    """La otra mitad: sin Cockpit compilado, el modo que lo sirve no puede arrancar. Si sólo
    se relajara la exigencia, el doble clic abriría una ventana sobre un 503."""
    db = _base_lista(tmp_path)
    inexistente = str(tmp_path / "bundle_que_no_existe")
    ruta_config, _ = _config_orquestar(
        tmp_path, lambda l: l["cockpit"].update({"ruta_bundle": inexistente})
    )

    with patch("src.lanzador.arrancar_servidor") as arrancar, \
         patch("src.lanzador.es_sesion_interactiva", return_value=False):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == HEALTHCHECK_INSATISFACTORIO
    arrancar.assert_not_called()


# --- El puerto: reutilizar, detenerse, y no matar lo ajeno -----------------------------

def test_un_puerto_ocupado_por_un_tercero_detiene_el_arranque_y_consta(tmp_path):
    db = _base_lista(tmp_path)
    with _servidor_ajeno() as puerto:
        ruta_config, _ = _config_orquestar(tmp_path, puerto=puerto)
        with patch("src.lanzador.arrancar_servidor") as arrancar, \
             patch("src.lanzador.es_sesion_interactiva", return_value=False):
            codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == PUERTO_OCUPADO_AJENO
    arrancar.assert_not_called()
    assert "LANZADOR_PUERTO_OCUPADO_AJENO" in _acciones_registradas(_registro(tmp_path))


def test_una_api_propia_viva_se_reutiliza_y_no_se_apaga_al_terminar(tmp_path):
    """Transición prohibida nº 4. Si la API ya estaba —alguien la lanzó a mano para
    desarrollar—, esta invocación la usa pero **no la mata**."""
    db = _base_lista(tmp_path)
    with _servidor_health("ok", 200) as puerto:
        ruta_config, _ = _config_orquestar(tmp_path, puerto=puerto)
        with patch("src.lanzador.arrancar_servidor") as arrancar, \
             patch("src.lanzador.apagar_servidor") as apagar, \
             patch("src.lanzador.abrir_cockpit",
                   return_value=AperturaCockpit(ModoApertura.OMITIDA_SIN_ESCRITORIO)), \
             patch("src.lanzador.prospectar", return_value=EXITO):
            codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    arrancar.assert_not_called()
    apagar.assert_not_called()
    assert "LANZADOR_PUERTO_REUTILIZADO" in _acciones_registradas(_registro(tmp_path))


def test_si_la_api_propia_no_responde_a_tiempo_no_se_abre_nada(tmp_path):
    """Se informa en vez de abrir un navegador sobre nada (Operación 2 del contrato)."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor", side_effect=ServidorNoRespondio("no contestó")), \
         patch("src.lanzador.abrir_cockpit") as abrir, \
         patch("src.lanzador.prospectar") as prospectar_falso:
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == SERVIDOR_NO_RESPONDE
    abrir.assert_not_called()
    prospectar_falso.assert_not_called()
    assert "LANZADOR_DEGRADADO" in _acciones_registradas(_registro(tmp_path))


# --- El modo del despertador no toca nada gráfico ---------------------------------------

def test_el_modo_pipeline_no_levanta_servidor_ni_abre_ventana(tmp_path):
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor") as arrancar, \
         patch("src.lanzador.apagar_servidor") as apagar, \
         patch("src.lanzador.abrir_cockpit") as abrir, \
         patch("src.lanzador.prospectar", return_value=EXITO) as prospectar_falso:
        codigo = orquestar(ModoInvocacion.PIPELINE, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    arrancar.assert_not_called()
    apagar.assert_not_called()
    abrir.assert_not_called()
    prospectar_falso.assert_called_once()


def test_el_modo_cockpit_no_prospecta(tmp_path):
    """Abrir la pantalla no puede disparar un proceso que archiva y purga ficheros."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor"), \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.OMITIDA_SIN_ESCRITORIO)), \
         patch("src.lanzador.prospectar") as prospectar_falso:
        codigo = orquestar(ModoInvocacion.COCKPIT, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    prospectar_falso.assert_not_called()


# --- La apertura del Cockpit -------------------------------------------------------------

def test_sin_sesion_interactiva_no_se_abre_el_cockpit_y_queda_la_huella(tmp_path):
    """Sin `LANZADOR_GUI_OMITIDA`, "no salió ninguna ventana en Session 0" es
    indistinguible de "no hubo nada que abrir"."""
    ruta_config, _ = _config_orquestar(tmp_path)
    config = cargar_configuracion(ruta_config)
    db = str(tmp_path / "licitaciones.db")

    with patch("src.lanzador.es_sesion_interactiva", return_value=False), \
         patch("subprocess.Popen") as popen:
        apertura = abrir_cockpit(config, db_path=db)

    assert apertura.modo is ModoApertura.OMITIDA_SIN_ESCRITORIO
    assert apertura.hay_ventana_vigilable is False
    popen.assert_not_called()
    assert "LANZADOR_GUI_OMITIDA" in _acciones_registradas(_registro(tmp_path))


def test_la_preferencia_de_no_abrir_no_se_disfraza_de_invariante(tmp_path):
    """`abrir_navegador: false` es una preferencia declarada, no la invariante actuando. Si
    emitiera el mismo evento, `LANZADOR_GUI_OMITIDA` dejaría de servir para auditarla."""
    ruta_config, _ = _config_orquestar(
        tmp_path, lambda l: l["cockpit"].update({"abrir_navegador": False})
    )
    config = cargar_configuracion(ruta_config)
    db = str(tmp_path / "licitaciones.db")

    with patch("src.lanzador.es_sesion_interactiva", return_value=True), \
         patch("subprocess.Popen") as popen:
        apertura = abrir_cockpit(config, db_path=db)

    assert apertura.modo is ModoApertura.OMITIDA_POR_CONFIGURACION
    popen.assert_not_called()
    assert "LANZADOR_GUI_OMITIDA" not in _acciones_registradas(_registro(tmp_path))


def test_el_cockpit_se_abre_en_modo_aplicacion_y_con_perfil_propio(tmp_path):
    """El perfil propio es lo que hace fiable el apagado: **medido el 2026-08-18**, con una
    instancia previa del mismo perfil el proceso nuevo delega y muere en 0,2 s, y el
    lanzador lo leería como que han cerrado el Cockpit."""
    ruta_config, puerto = _config_orquestar(tmp_path)
    config = cargar_configuracion(ruta_config)
    db = str(tmp_path / "licitaciones.db")

    with patch("src.lanzador.es_sesion_interactiva", return_value=True), \
         patch("subprocess.Popen") as popen:
        apertura = abrir_cockpit(config, db_path=db, localizador=lambda: r"C:\falso\chrome.exe")

    assert apertura.modo is ModoApertura.APLICACION
    assert apertura.hay_ventana_vigilable is True
    orden = popen.call_args[0][0]
    assert orden[0] == r"C:\falso\chrome.exe"
    assert f"--app=http://127.0.0.1:{puerto}/" in orden
    assert any(a.startswith("--user-data-dir=") and NOMBRE_PERFIL_COCKPIT in a for a in orden)


def test_sin_chrome_ni_edge_se_abre_igual_en_el_navegador_por_defecto(tmp_path):
    """Degradar la apariencia es aceptable; no abrir nada, no."""
    ruta_config, puerto = _config_orquestar(tmp_path)
    config = cargar_configuracion(ruta_config)
    db = str(tmp_path / "licitaciones.db")

    with patch("src.lanzador.es_sesion_interactiva", return_value=True), \
         patch("webbrowser.open") as abrir_por_defecto:
        apertura = abrir_cockpit(config, db_path=db, localizador=lambda: None)

    assert apertura.modo is ModoApertura.NAVEGADOR_POR_DEFECTO
    assert apertura.hay_ventana_vigilable is False
    assert apertura.hay_ventana_sin_vigilar is True
    abrir_por_defecto.assert_called_once_with(f"http://127.0.0.1:{puerto}/")


def test_el_localizador_real_no_inventa_navegadores(tmp_path):
    """Convención C4: la ruta real, sin inyectar. O devuelve un ejecutable que existe, o
    devuelve `None`; lo que no puede es devolver una ruta imaginaria."""
    ruta = localizar_navegador()
    assert ruta is None or os.path.isfile(ruta)


# --- El apagado: sólo lo mío, y sin interrumpir nada -------------------------------------

def test_se_espera_a_que_se_cierre_la_ventana_antes_de_apagar(tmp_path):
    """El trabajo del modo completo lo termina una persona cerrando una ventana, no un
    plazo. Y el orden importa: apagar antes de esperar dejaría el Cockpit muerto en
    pantalla."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)
    sucesos = []

    ventana = MagicMock()
    ventana.wait.side_effect = lambda: sucesos.append("ventana_cerrada")

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor",
               side_effect=lambda *a, **k: sucesos.append("apagado")), \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.APLICACION, ventana)), \
         patch("src.lanzador.prospectar",
               side_effect=lambda *a, **k: sucesos.append("prospeccion") or EXITO):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    # La prospección termina antes de que el apagado pueda tocar nada: el pipeline borra
    # ficheros antes de tocar la base, así que matarlo a mitad deja el fichero fuera y la
    # fila sin marcar.
    assert sucesos == ["prospeccion", "ventana_cerrada", "apagado"]


def test_una_ventana_que_no_podemos_vigilar_no_se_apaga_a_ciegas(tmp_path):
    """Con el navegador por defecto hay ventana abierta y ningún proceso al que esperar.
    Apagar sería cerrarle el Cockpit en las narices a quien lo está mirando."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor") as apagar, \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.NAVEGADOR_POR_DEFECTO,
                                            detalle="no se encontró Chrome ni Edge")), \
         patch("src.lanzador.prospectar", return_value=EXITO):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    apagar.assert_not_called()
    assert "LANZADOR_APAGADO_DIFERIDO" in _acciones_registradas(_registro(tmp_path))


def test_sin_ninguna_ventana_abierta_el_servidor_se_apaga_en_cuanto_acaba(tmp_path):
    """Nadie mirando, nada que esperar: el ciclo se cierra y el equipo queda como estaba."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor") as apagar, \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.OMITIDA_SIN_ESCRITORIO)), \
         patch("src.lanzador.prospectar", return_value=EXITO):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == EXITO
    apagar.assert_called_once()


def test_un_apagado_incompleto_sale_con_su_propio_codigo(tmp_path):
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor", side_effect=ApagadoIncompleto("sigue vivo")), \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.OMITIDA_SIN_ESCRITORIO)), \
         patch("src.lanzador.prospectar", return_value=EXITO):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == APAGADO_INCOMPLETO


# --- Los códigos de salida dicen la verdad ----------------------------------------------

def test_ninguna_terminacion_degradada_puede_salir_con_cero(tmp_path):
    """Transición prohibida nº 5, comprobada sobre la función que la implementa: aunque se
    la llame con un cero, no hay forma de salir de `DEGRADADO` con éxito."""
    db = str(tmp_path / "licitaciones.db")
    assert _degradar(EXITO, "una causa cualquiera", db) == ERROR_NO_PREVISTO
    assert _degradar(PIPELINE_FALLIDO, "otra causa", db) == PIPELINE_FALLIDO
    assert "LANZADOR_DEGRADADO" in _acciones_registradas(_registro(tmp_path))


def test_la_omision_deliberada_no_es_una_degradacion(tmp_path):
    """El `30` no es una avería: es la protección funcionando. Registrarlo como degradado
    confundiría "no prospecté porque ya había una corrida" con "no pude prospectar"."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)

    with patch("src.lanzador.prospectar", return_value=PIPELINE_OMITIDO):
        codigo = orquestar(ModoInvocacion.PIPELINE, ruta_config=ruta_config, db_path=db)

    assert codigo == PIPELINE_OMITIDO
    assert "LANZADOR_DEGRADADO" not in _acciones_registradas(_registro(tmp_path))


def test_una_prospeccion_fallida_no_le_cierra_el_cockpit_a_nadie(tmp_path):
    """Decisión de dirección del 2026-08-13: negarle a alguien los datos de ayer porque la
    prospección de hoy falló convierte un fallo parcial en una avería total."""
    db = _base_lista(tmp_path)
    ruta_config, _ = _config_orquestar(tmp_path)
    ventana = MagicMock()

    with patch("src.lanzador.arrancar_servidor"), \
         patch("src.lanzador.apagar_servidor"), \
         patch("src.lanzador.abrir_cockpit",
               return_value=AperturaCockpit(ModoApertura.APLICACION, ventana)) as abrir, \
         patch("src.lanzador.prospectar", return_value=PIPELINE_FALLIDO):
        codigo = orquestar(ModoInvocacion.COMPLETO, ruta_config=ruta_config, db_path=db)

    assert codigo == PIPELINE_FALLIDO
    abrir.assert_called_once()
    ventana.wait.assert_called_once()


# --- La consola de mando ------------------------------------------------------------------

def test_la_cli_ofrece_exactamente_los_tres_modos_del_contrato():
    with patch("src.lanzador.orquestar", return_value=EXITO) as orquestado:
        for modo in ("completo", "pipeline", "cockpit"):
            assert main(["--modo", modo]) == EXITO
            assert orquestado.call_args[0][0] is ModoInvocacion(modo)

    with pytest.raises(SystemExit):
        main(["--modo", "inventado"])


def test_sin_argumentos_el_doble_clic_hace_el_modo_completo():
    with patch("src.lanzador.orquestar", return_value=EXITO) as orquestado:
        main([])
    assert orquestado.call_args[0][0] is ModoInvocacion.COMPLETO


def test_un_error_no_previsto_sale_con_uno_y_deja_constancia(tmp_path):
    """El `1` está reservado a lo que el contrato no anticipó, y eso es información."""
    with patch("src.lanzador.orquestar", side_effect=RuntimeError("algo inesperado")), \
         patch("src.lanzador.es_sesion_interactiva", return_value=False), \
         patch("src.lanzador.registrar_evento_lanzador") as registrado:
        codigo = main(["--modo", "pipeline"])

    assert codigo == ERROR_NO_PREVISTO
    acciones = [llamada[0][0] for llamada in registrado.call_args_list]
    assert "LANZADOR_DEGRADADO" in acciones
    assert "LANZADOR_GUI_OMITIDA" in acciones


# --- La auditoría de la invariante, con la lista en la mano -------------------------------

def test_ninguna_llamada_grafica_vive_fuera_de_las_dos_funciones_que_comprueban_la_sesion():
    """**La prueba que el contrato pedía y no existía.**

    La invariante central dice que *toda* llamada gráfica pasa por `es_sesion_interactiva()`,
    y añade que su virtud es poder auditarse recorriendo el código con una lista en la mano.
    Esto es esa lista, automatizada: si alguien añade mañana un diálogo o una ventana en
    cualquier otro punto del módulo, la prueba lo señala. Sin ella, el fallo sólo aparecería
    de madrugada, en la Session 0, como un proceso que no termina nunca.
    """
    import ast

    fuente = open(os.path.join("src", "lanzador.py"), encoding="utf-8").read()
    arbol = ast.parse(fuente)

    funciones = [n for n in ast.walk(arbol)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def dueña_de(numero_linea):
        candidatas = [f for f in funciones if f.lineno <= numero_linea <= (f.end_lineno or f.lineno)]
        return min(candidatas, key=lambda f: (f.end_lineno or f.lineno) - f.lineno).name if candidatas else None

    permitidas = {
        "MessageBoxW": "avisar_fallo_fatal",   # el diálogo nativo de fallo fatal
        "webbrowser": "abrir_cockpit",         # la caída al navegador por defecto
        "--app=": "abrir_cockpit",             # la ventana en modo aplicación
    }

    for numero, linea in enumerate(fuente.splitlines(), start=1):
        if linea.lstrip().startswith("#") or ":" == linea.strip()[:1]:
            continue  # los comentarios documentan la invariante, no la ejercen
        for marca, funcion_permitida in permitidas.items():
            if marca in linea:
                assert dueña_de(numero) == funcion_permitida, (
                    f"llamada gráfica «{marca}» en la línea {numero}, dentro de "
                    f"«{dueña_de(numero)}»: la invariante central exige que viva en "
                    f"«{funcion_permitida}», que es la que comprueba la sesión"
                )

    # Y las dos funciones permitidas comprueban de verdad la sesión, en vez de confiar en
    # que el llamador lo haya hecho por ellas.
    for nombre in ("avisar_fallo_fatal", "abrir_cockpit"):
        cuerpo = next(f for f in funciones if f.name == nombre)
        texto = ast.get_source_segment(fuente, cuerpo) or ""
        assert "es_sesion_interactiva()" in texto, (
            f"«{nombre}» realiza llamadas gráficas sin consultar la sesión"
        )


# ==============================================================================
# 7. Paso 7 — la lanzadera silenciosa y los accesos directos
# ==============================================================================
#
# `Incoop.vbs` **no se puede probar con la suite**: VBScript no se ejecuta desde pytest y su
# comportamiento depende del intérprete de Windows. Lo que sí se puede comprobar —y es donde
# de verdad se rompería— es que el fichero siga siendo una puerta y no se haya llenado de
# lógica, que no lleve rutas absolutas grabadas y que no contenga más de un diálogo. Un
# segundo `MsgBox` que alguien añada con buena intención es un proceso colgado para siempre
# la noche en que el despertador lo invoque por error.

RUTA_LANZADERA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "Incoop.vbs")


def _fuente_lanzadera() -> str:
    with open(RUTA_LANZADERA, "rb") as fichero:
        crudo = fichero.read()
    # Se decodifica como ASCII estricto a propósito: ver la prueba de abajo.
    return crudo.decode("ascii")


def test_la_lanzadera_invoca_el_orquestador_y_nada_mas():
    """Toda la lógica vive en Python. Si esto empieza a crecer, la capa pierde su red."""
    fuente = _fuente_lanzadera()
    assert "-m src.lanzador --modo " in fuente
    assert "pythonw.exe" in fuente          # sin consola, no sólo con la ventana oculta
    assert "shell.CurrentDirectory = raiz"  in fuente

    codigo = [l for l in fuente.splitlines()
              if l.strip() and not l.strip().startswith("'")]
    assert len(codigo) < 40, "la lanzadera está acumulando lógica que debería vivir en Python"


def test_la_lanzadera_no_lleva_ninguna_ruta_absoluta_grabada():
    """Lección de H-18: el directorio de trabajo de un acceso directo no es el que uno cree,
    y una ruta grabada a fuego convierte una copia del proyecto en una copia rota."""
    fuente = _fuente_lanzadera()
    assert ":\\" not in fuente.replace("C:\\Windows", ""), "hay una ruta absoluta grabada"
    assert "WScript.ScriptFullName" in fuente, "la raíz debe deducirse del propio fichero"


def test_la_lanzadera_tiene_un_solo_dialogo_y_solo_para_lo_que_python_no_puede_avisar():
    """El único fallo del que Python no puede avisar es no haber podido arrancar Python."""
    # Sólo el código: los comentarios explican por qué existe ese diálogo, y contarlos como
    # llamadas haría que documentar la decisión rompiera la prueba que la protege.
    codigo = [l for l in _fuente_lanzadera().splitlines() if not l.strip().startswith("'")]
    con_dialogo = [i for i, l in enumerate(codigo) if "MsgBox" in l]
    assert len(con_dialogo) == 1

    anteriores = [l for l in codigo[:con_dialogo[0]] if l.strip()]
    assert anteriores[-1].strip() == "If Err.Number <> 0 Then", (
        "el diálogo debe estar dentro de la comprobación de error del arranque"
    )


def test_la_lanzadera_es_ascii_puro():
    """Un `.vbs` en UTF-8 sin BOM enseña los acentos rotos en el `MsgBox`, y con BOM algunos
    motores de Windows se atragantan. En el único sitio donde el sistema habla antes de que
    exista Python, el texto tiene que leerse bien sí o sí."""
    _fuente_lanzadera()  # decodifica como ASCII estricto: si hay un acento, revienta aquí


def test_el_despertador_no_pasa_por_la_lanzadera():
    """El modo «sólo pipeline» corre en la Session 0, donde el `MsgBox` de la lanzadera
    esperaría para siempre. El Paso 8 invocará Python directamente, y esto lo deja fijado."""
    assert "pipeline" not in _fuente_lanzadera()


def test_no_existe_acceso_directo_para_el_modo_pipeline():
    """Un icono que dispara un proceso que archiva y purga ficheros **sin abrir nada en
    pantalla** es una escopeta cargada encima de la mesa."""
    from tools.crear_accesos_directos import ACCESOS

    assert {modo for _, modo, _ in ACCESOS} == {"completo", "cockpit"}


def test_los_accesos_directos_se_crean_de_verdad_y_repetirlo_no_los_duplica(tmp_path):
    """Convención C4: se ejecuta `cscript` de verdad sobre una carpeta temporal, en vez de
    comprobar que generamos el texto que creemos. El fichero `.lnk` es binario y lo escribe
    Windows: o se crea o no se crea.

    ⚠️ **Eran 2 y son 3 desde el bloque 10.C**, y merece decirse por qué no es un parche. Lo que
    esta prueba protege es que los accesos **se creen de verdad y que repetirlo no los duplique**,
    no que sean exactamente dos para siempre. El tercero es el del despertador, que sólo va al
    menú de inicio *(decisión 5.4)* — y aquí se pasa una sola carpeta, que hace de menú.
    """
    from tools.crear_accesos_directos import ACCESOS, ACCESOS_SOLO_MENU, alta, baja, estado

    carpeta = str(tmp_path / "accesos")
    os.makedirs(carpeta)
    esperados = len(ACCESOS) + len(ACCESOS_SOLO_MENU)

    creados, _ = alta([carpeta])
    assert len(creados) == esperados
    assert all(os.path.isfile(ruta) for ruta in creados)

    alta([carpeta])  # idempotente: dar de alta dos veces no deja el doble de iconos
    assert len(os.listdir(carpeta)) == esperados
    assert all(existe for _, existe in estado([carpeta]))

    retirados = baja([carpeta])
    assert len(retirados) == esperados
    assert os.listdir(carpeta) == []


def test_cada_acceso_directo_invoca_su_propio_modo(tmp_path):
    """Que los dos iconos existan no basta: el secundario tiene que abrir el Cockpit **sin**
    prospectar, o serían el mismo botón pintado dos veces."""
    from tools.crear_accesos_directos import alta

    carpeta = str(tmp_path / "accesos")
    os.makedirs(carpeta)
    creados, _ = alta([carpeta])

    # Windows guarda las cadenas del `.lnk` en UTF-16: se lee el fichero real, no la orden
    # que creímos darle.
    contenidos = {}
    for ruta in creados:
        with open(ruta, "rb") as fichero:
            contenidos[os.path.basename(ruta)] = fichero.read()

    completo = contenidos["Incoop.lnk"]
    cockpit = contenidos["Incoop (solo Cockpit).lnk"]
    assert "completo".encode("utf-16-le") in completo
    assert "cockpit".encode("utf-16-le") in cockpit
    assert "completo".encode("utf-16-le") not in cockpit


def test_no_se_crea_un_acceso_directo_que_apunte_a_nada(tmp_path, monkeypatch):
    """Un acceso roto es peor que ninguno: el fallo aparece al hacer doble clic, que es el
    único momento en que no hay nadie experto delante."""
    import tools.crear_accesos_directos as accesos

    monkeypatch.setattr(accesos, "NOMBRE_LANZADERA", "Incoop_que_no_existe.vbs")
    with pytest.raises(FileNotFoundError):
        accesos.alta([str(tmp_path)])


def test_el_icono_se_genera_con_el_fondo_vaciado(tmp_path):
    """El logo de origen tiene fondo blanco opaco, que en el escritorio se vería como un
    azulejo blanco. Y un `.ico` de un solo tamaño lo reescala Windows, mal."""
    from PIL import Image

    from tools.crear_accesos_directos import TAMANOS_ICONO, generar_icono

    destino = str(tmp_path / "prueba.ico")
    generar_icono(destino=destino)

    with Image.open(destino) as icono:
        assert sorted(icono.info["sizes"]) == sorted(TAMANOS_ICONO)
        icono.size = (256, 256)
        esquina = icono.convert("RGBA").getpixel((0, 0))
    assert esquina[3] == 0, "la esquina debería ser transparente, no blanca"


# ==============================================================================
# 8. H-43 — Un `RUNNING` no dice si hay alguien prospectando
# ==============================================================================
#
# Descubierto el 2026-08-18 mirando la pantalla, no el código: el indicador nuevo anunciaba
# «Prospección en curso» sobre la corrida que quedó sin cerrar el 2026-08-17, cuyo proceso
# murió hace un día. La fila `RUNNING` se queda igual cuando una corrida muere a mitad, así
# que servir el estado a secas convierte un cadáver en un badge girando para siempre. Es la
# familia de H-21: no rompe nada, miente en pantalla.
#
# La reparación no añade criterio: publica el que ya existía en `motivo_ejecucion_huerfana()`,
# que es con el que el cerrojo de ejecución decide si puede arrancar (esquema v8, H-40). **Un
# solo juicio y no dos**, o el lanzador y la pantalla acabarían contando cosas distintas del
# mismo hecho.

def test_una_corrida_cuyo_dueno_murio_no_se_sirve_como_en_curso(tmp_path):
    db = _base_lista(tmp_path)
    _sembrar_corrida(db, estado="RUNNING", pid=PID_MUERTO, instante="123456789")

    items, _ = Memoria(db_path=db).listar_ejecuciones(1, 5)

    assert items[0]["estado"] == "RUNNING"
    assert items[0]["duenyo_vivo"] is False


def test_una_corrida_viva_si_se_sirve_como_en_curso(tmp_path):
    """La otra mitad. Sin ella, la reparación podría consistir en no decir nunca «en curso»,
    que taparía el defecto en vez de arreglarlo."""
    db = _base_lista(tmp_path)
    yo = os.getpid()
    _sembrar_corrida(db, estado="RUNNING", pid=yo, instante=str(instante_creacion_proceso(yo)))

    items, _ = Memoria(db_path=db).listar_ejecuciones(1, 5)

    assert items[0]["duenyo_vivo"] is True


def test_una_fila_sin_pid_no_afirma_nada(tmp_path):
    """Las corridas anteriores al esquema v8 no anotaban dueño. Decir «interrumpida» sobre
    ellas sería inventar, y decir «en curso» también: se responde *no se puede saber*."""
    db = _base_lista(tmp_path)
    _sembrar_corrida(db, estado="RUNNING", pid=None, instante=None)

    items, _ = Memoria(db_path=db).listar_ejecuciones(1, 5)

    assert items[0]["duenyo_vivo"] is None


def test_una_corrida_terminada_no_habla_de_dueños(tmp_path):
    db = _base_lista(tmp_path)
    _sembrar_corrida(db, estado="COMPLETED", pid=PID_MUERTO, instante="123456789")

    items, _ = Memoria(db_path=db).listar_ejecuciones(1, 5)

    assert items[0]["duenyo_vivo"] is None


def test_el_endpoint_de_ejecuciones_publica_el_juicio(tmp_path, monkeypatch):
    """De nada sirve que la base lo sepa si el contrato de la API no lo transporta: el
    Cockpit lee JSON, no SQLite."""
    from fastapi.testclient import TestClient

    from src.api.main import app

    db = _base_lista(tmp_path)
    monkeypatch.setenv("DB_PATH_INCOOP", db)
    _sembrar_corrida(db, estado="RUNNING", pid=PID_MUERTO, instante="123456789")

    respuesta = TestClient(app).get("/api/v1/admin/ejecuciones?page=1&limit=5")

    assert respuesta.status_code == 200
    assert respuesta.json()["items"][0]["duenyo_vivo"] is False


# ==============================================================================
# 9. H-44 — Preguntar por PID cuando el hijo es tuyo
# ==============================================================================
#
# Descubierto el 2026-08-18 haciendo doble clic dos veces: las dos sesiones terminaron con
# `LANZADOR_APAGADO_INCOMPLETO` y código 40 sobre un servidor que **sí había muerto** —el
# puerto quedaba libre en dos segundos y el proceso ya no existía—. Un lanzador que informa
# de una avería inexistente al final de cada sesión enseña a no creerse sus códigos de
# salida, que es exactamente lo contrario de para lo que existen (Consideración 11).
#
# La reparación no cambia la escalera de apagado: cambia **a quién se le pregunta si el
# proceso murió**. `Popen.poll()` consulta el handle que el lanzador ya tiene sobre su hijo;
# `OpenProcess` puede seguir contestando sobre un difunto mientras alguien conserve un handle
# abierto, que es el aviso que `src/proceso.py` lleva anotado desde el Paso 6.
#
# De paso quedó medido que **el nivel 2 no existe sin consola**: lanzado desde el `.vbs` con
# `pythonw.exe`, `CTRL_BREAK_EVENT` falla con WinError 6. La escalera real del doble clic
# tiene dos peldaños, no tres.

def _marca_de_prueba(pid, instante="123456789"):
    from src.lanzador import MarcaServidor

    return MarcaServidor(pid=pid, instante_creacion=instante, host="127.0.0.1",
                         puerto=8000, testigo="x", iniciado_at="2026-08-18T00:00:00Z")


def test_el_supervisor_pregunta_al_hijo_propio_y_no_al_sistema(monkeypatch):
    """El caso exacto del falso 40: el hijo ya terminó y el sistema todavía dice que vive."""
    import src.lanzador as lanzador

    hijo = MagicMock()
    hijo.pid = 4321
    hijo.poll.return_value = 0  # ha terminado

    monkeypatch.setattr(lanzador, "_PROCESO_SERVIDOR", hijo)
    monkeypatch.setattr(lanzador, "es_nuestro_proceso", lambda *a, **k: True)

    assert lanzador._vive_el_servidor(_marca_de_prueba(4321)) is False


def test_mientras_el_hijo_no_ha_terminado_se_le_cree_igual(monkeypatch):
    """La otra mitad: si la reparación contestara siempre «muerto», el apagado dejaría de
    verificar nada y el nivel 1 parecería funcionar siempre."""
    import src.lanzador as lanzador

    hijo = MagicMock()
    hijo.pid = 4321
    hijo.poll.return_value = None  # sigue corriendo

    monkeypatch.setattr(lanzador, "_PROCESO_SERVIDOR", hijo)
    monkeypatch.setattr(lanzador, "es_nuestro_proceso", lambda *a, **k: False)

    assert lanzador._vive_el_servidor(_marca_de_prueba(4321)) is True


def test_de_un_servidor_que_no_engendramos_se_sigue_preguntando_por_pid(monkeypatch):
    """Cuando la marca la dejó otra invocación no hay hijo al que preguntar, y entonces el
    PID con su instante de creación es lo correcto: quien pregunta desde fuera sí ve morir."""
    import src.lanzador as lanzador

    ajeno = MagicMock()
    ajeno.pid = 1111
    ajeno.poll.return_value = 0

    monkeypatch.setattr(lanzador, "_PROCESO_SERVIDOR", ajeno)
    consultas = []
    monkeypatch.setattr(lanzador, "es_nuestro_proceso",
                        lambda pid, instante: consultas.append(pid) or True)

    assert lanzador._vive_el_servidor(_marca_de_prueba(2222)) is True
    assert consultas == [2222], "con otro PID debe caer a la comprobación del sistema"


def test_el_apagado_se_olvida_del_hijo_al_terminar(tmp_path, monkeypatch):
    """Sin esto, la marca de un servidor ya apagado seguiría contestando a la invocación
    siguiente dentro del mismo proceso."""
    import src.lanzador as lanzador

    hijo = MagicMock()
    hijo.pid = 777
    hijo.poll.return_value = 0
    monkeypatch.setattr(lanzador, "_PROCESO_SERVIDOR", hijo)

    marca = _marca_de_prueba(777)
    lanzador.escribir_marca_servidor(marca, str(tmp_path / "licitaciones.db"))
    config = cargar_configuracion(_escribir_config(tmp_path))

    nivel = lanzador.apagar_servidor(config, db_path=str(tmp_path / "licitaciones.db"))

    assert nivel == "ya_no_estaba"
    assert lanzador._PROCESO_SERVIDOR is hijo or lanzador._PROCESO_SERVIDOR is None
    assert not os.path.exists(str(tmp_path / "lanzador.pid"))
