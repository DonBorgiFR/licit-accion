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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest

import yaml

from src.lanzador import (
    CONFIGURACION_INVALIDA,
    ERROR_NO_PREVISTO,
    ConfiguracionLanzadorInvalida,
    EstadoPuerto,
    HEALTHCHECK_INSATISFACTORIO,
    PUERTO_OCUPADO_AJENO,
    avisar_fallo_fatal,
    cargar_configuracion,
    comprobar_arranque,
    comunicar_fallo_fatal,
    ejecutar_healthcheck,
    es_sesion_interactiva,
    estado_del_puerto,
    registrar_evento_lanzador,
)
from src.memoria import Memoria

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
