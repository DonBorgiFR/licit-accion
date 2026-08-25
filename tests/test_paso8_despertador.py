"""Capa 10, Paso 8 · La herramienta que da de alta el despertador.

**Lo que estas pruebas NO pueden comprobar, y hay que decirlo**: que una corrida en la Session 0
termine sola y no deje proceso vivo. Eso exige una sesión cerrada de verdad y es la verificación
que cierra el paso; aquí no cabe.

**Lo que sí sujetan** es todo lo que puede romperse en silencio al construir la tarea, que es
donde vive el riesgo real: una orden que apunte al `.vbs` colgaría la Session 0 para siempre; una
que use `python src/lanzador.py` no arrancaría nunca (C1, y fue H-50); y una que ignore
`ejecutar_si_se_perdio` daría un lunes sin las oportunidades del viernes sin decir por qué.

Ninguna de las tres da la cara: las tres fallan de madrugada, sin nadie mirando, y dejan sólo un
código de salida que nadie revisa.
"""

import os
import sys

import pytest

from src import PROJECT_ROOT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import registrar_despertador as despertador  # noqa: E402


# =====================================================================
# ANDAMIAJE
# =====================================================================

def xml(hora="06:30", recuperar=True, tope=60, sin_sesion=False):
    return despertador._construir_xml(
        hora=hora, ejecutar_si_se_perdio=recuperar, tope_minutos=tope, sin_sesion=sin_sesion
    )


class SchtasksFalso:
    """Sustituto de la llamada al Programador: recuerda qué se le pidió, sin tocar el sistema."""

    def __init__(self, existe=False, codigo=0):
        self.existe = existe
        self.codigo = codigo
        self.llamadas = []

    def __call__(self, argumentos):
        self.llamadas.append(argumentos)
        if argumentos[0] == "/Query":
            return (0 if self.existe else 1), "salida de prueba"
        return self.codigo, "salida de prueba"


@pytest.fixture
def config():
    from src.lanzador import cargar_configuracion
    return cargar_configuracion()


# =====================================================================
# 1. LA ORDEN QUE SE VA A EJECUTAR DE MADRUGADA
# =====================================================================

def _lo_que_se_ejecuta(generado):
    """La orden real: `<Command>` y `<Arguments>`, no el documento entero.

    Se mira sólo esto a propósito. La descripción de la tarea **sí** menciona el `.vbs`, para
    avisar a quien la abra desde el Programador de que no lo ponga ahí, y comprobarlo sobre el
    XML completo confundiría ese aviso con el defecto que previene.
    """
    import re

    comando = re.search(r"<Command>(.*?)</Command>", generado, re.S).group(1)
    argumentos = re.search(r"<Arguments>(.*?)</Arguments>", generado, re.S).group(1)
    return f"{comando} {argumentos}"


def test_la_tarea_no_invoca_jamas_el_vbs():
    """La invariante central del Paso 7 vista desde el atajo que parecía cómodo.

    `Incoop.vbs` contiene un `MsgBox` para el caso de que Python no arranque. En la Session 0
    —sin escritorio— ese diálogo espera a un usuario que no existe, **para siempre**. El
    síntoma no es un error: es una tarea que no termina nunca.
    """
    orden = _lo_que_se_ejecuta(xml()).lower()

    assert ".vbs" not in orden
    assert "wscript" not in orden
    assert "cscript" not in orden


def test_la_tarea_invoca_el_modulo_y_no_el_fichero():
    """C1, y fue H-50: `python src/lanzador.py` muere con ModuleNotFoundError."""
    orden = _lo_que_se_ejecuta(xml())

    assert "-m src.lanzador --modo pipeline" in orden
    assert "src/lanzador.py" not in orden
    assert "src\\lanzador.py" not in orden


def test_la_tarea_arranca_desde_la_raiz_del_proyecto():
    """`-m src.lanzador` sólo resuelve desde la raíz. Sin esto, la orden anterior no basta."""
    generado = xml()

    assert f"<WorkingDirectory>{PROJECT_ROOT}</WorkingDirectory>" in generado


def test_el_interprete_depende_de_si_hay_alguien_delante(monkeypatch, tmp_path):
    """Con la sesión abierta, `pythonw`: `python.exe` plantaría una consola negra delante de
    quien esté trabajando, a las 06:30 o al encender, y el Programador no sabe ocultar la
    ventana de una acción.

    Sin sesión no hay a quién molestar, y a cambio un proceso **con** consola puede recibir
    `CTRL_BREAK_EVENT` —el nivel 2 de la escalera que detiene un pipeline colgado—, que es la
    diferencia entre una corrida cerrada limpiamente y una fila `RUNNING` fantasma.
    """
    falso_pythonw = tmp_path / "pythonw.exe"
    falso_python = tmp_path / "python.exe"
    falso_pythonw.write_bytes(b"")
    falso_python.write_bytes(b"")

    monkeypatch.setattr(sys, "executable", str(falso_python))
    assert despertador._interprete(sin_sesion=False) == str(falso_pythonw)

    monkeypatch.setattr(sys, "executable", str(falso_pythonw))
    assert despertador._interprete(sin_sesion=True) == str(falso_python)


def test_la_tarea_normal_no_abre_una_consola_en_la_cara_de_nadie():
    """La comprobación de arriba, pero sobre el XML que de verdad se registra."""
    orden = _lo_que_se_ejecuta(xml()).lower()

    assert "pythonw.exe" in orden
    assert "\\python.exe" not in orden


# =====================================================================
# 2. QUE LA TAREA OBEDEZCA A LA CONFIGURACIÓN, Y NO AL REVÉS
# =====================================================================

def test_la_hora_sale_de_la_configuracion():
    """La hora no se pregunta ni se codifica: vive en `config/lanzador.yaml`."""
    assert "<StartBoundary>2026-01-01T03:15:00</StartBoundary>" in xml(hora="03:15")


@pytest.mark.parametrize("recuperar,esperado", [(True, "true"), (False, "false")])
def test_ejecutar_si_se_perdio_llega_a_la_tarea(recuperar, esperado):
    """Es la razón de registrar por XML: los modificadores de `schtasks` no saben ponerlo.

    Sin esto, un fin de semana con el equipo apagado sería un lunes sin las oportunidades del
    viernes — y la tarea constaría como correctamente registrada.
    """
    assert f"<StartWhenAvailable>{esperado}</StartWhenAvailable>" in xml(recuperar=recuperar)


def test_la_tarea_nunca_guarda_una_contrasena():
    """Ni en el modo normal ni en el que necesitaría un administrador.

    `Password` obligaría a teclear la contraseña de Windows dentro de una herramienta del
    proyecto, y eso no se hace aquí ni con permiso: si algún día hiciera falta, lo concede un
    administrador desde fuera.
    """
    assert "Password" not in xml()
    assert "Password" not in xml(sin_sesion=True)


def test_por_defecto_la_tarea_corre_dentro_de_la_sesion():
    """Decisión del 2026-08-25, tomada con la medición delante: con `S4U` el Programador
    responde `Acceso denegado` en este equipo, porque la cuenta no es administradora.

    Y resultó ser una simplificación: toda la dificultad del paso —la Session 0, el diálogo
    que espera a un usuario que no existe— venía exclusivamente de `S4U`.
    """
    assert "<LogonType>InteractiveToken</LogonType>" in xml()
    assert "<LogonType>S4U</LogonType>" in xml(sin_sesion=True)


def test_una_ejecucion_perdida_se_recupera_al_entrar():
    """Es lo que amortigua lo que se pierde al no correr sin sesión: un día sin prospectar se
    convierte en una prospección al encender el equipo por la mañana."""
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml()


def test_el_programador_corta_mas_tarde_que_nuestro_propio_tope():
    """Dos mecanismos distintos, y el que debe actuar primero es el que sabe explicarse.

    El tope del lanzador detiene el pipeline y **deja constancia**: evento y código 32. El del
    Programador mata la tarea entera sin contar nada. Si el segundo llegara antes, perderíamos
    el diagnóstico justo en el caso que existe para diagnosticar.
    """
    import re

    for tope in (30, 60, 90, 240):
        generado = xml(tope=tope)
        minutos = int(re.search(r"<ExecutionTimeLimit>PT(\d+)M</ExecutionTimeLimit>", generado).group(1))
        assert minutos > tope, f"con un tope de {tope} min el Programador cortaría antes"


def test_la_tarea_dice_en_que_equipo_se_dio_de_alta():
    """La decisión del 2026-08-25 es *un solo PC, y que conste cuál*.

    Un acta no impide que alguien la dé de alta en el otro equipo; la descripción de la propia
    tarea sí lo delata, y se lee desde el Programador sin abrir el repositorio.
    """
    import platform

    assert platform.node() in xml()


# =====================================================================
# 3. ALTA Y BAJA IDEMPOTENTES
# =====================================================================

def test_dar_de_alta_dos_veces_no_crea_dos_tareas(config, monkeypatch):
    """Dos tareas nocturnas prospectando sobre la misma base es justo lo que el cerrojo
    existe para que no pase — y no hay que llegar a probarlo."""
    falso = SchtasksFalso(existe=True)
    monkeypatch.setattr(despertador, "_schtasks", falso)

    assert despertador.dar_de_alta(config) == 0

    creaciones = [c for c in falso.llamadas if c[0] == "/Create"]
    assert len(creaciones) == 1
    assert "/F" in creaciones[0], "sin /F, registrar dos veces falla o duplica"


def test_dar_de_baja_lo_que_no_existe_no_es_un_error(config, monkeypatch):
    """Es el estado que se pedía. Un código de error aquí convertiría 'ya está' en 'algo va mal'."""
    falso = SchtasksFalso(existe=False)
    monkeypatch.setattr(despertador, "_schtasks", falso)

    assert despertador.dar_de_baja() == 0
    assert not [c for c in falso.llamadas if c[0] == "/Delete"]


def test_dar_de_baja_retira_la_tarea(config, monkeypatch):
    falso = SchtasksFalso(existe=True)
    monkeypatch.setattr(despertador, "_schtasks", falso)

    assert despertador.dar_de_baja() == 0

    borrados = [c for c in falso.llamadas if c[0] == "/Delete"]
    assert len(borrados) == 1
    assert despertador.NOMBRE_TAREA in borrados[0]


def test_si_el_programador_rechaza_el_alta_se_dice_y_se_sale_con_error(config, monkeypatch, capsys):
    """El fallo previsible es S4U no permitido. Lo que no puede pasar es que la herramienta
    diga que la dio de alta cuando no lo hizo: sería una tarea nocturna imaginaria."""
    monkeypatch.setattr(despertador, "_schtasks", SchtasksFalso(existe=False, codigo=1))

    assert despertador.dar_de_alta(config) == 1

    salida = capsys.readouterr().out
    assert "rechazó el alta" in salida
    assert "contraseña" in salida.lower(), "no se explica el remedio, que no pasa por esta herramienta"


def test_el_estado_no_toca_nada(config, monkeypatch):
    """Mirar no modifica. Es la doctrina del Paso 2 y de la purga en dos tiempos."""
    falso = SchtasksFalso(existe=True)
    monkeypatch.setattr(despertador, "_schtasks", falso)

    despertador.informar_estado(config)

    assert all(c[0] == "/Query" for c in falso.llamadas), "el modo estado escribió algo"
