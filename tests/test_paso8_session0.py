"""Capa 10, Paso 8 · La herramienta que verifica la Session 0.

**Esto es una prueba de la prueba**, y esa es toda su razón de ser. La verificación de la
Session 0 no la puede hacer la suite —hace falta cerrar sesión de verdad—, así que lo único que
se puede sujetar aquí es que **la herramienta que la hace no mienta**: que la tarea de prueba sea
igual que la de verdad, que el detector de procesos detecte, y que un veredicto verde signifique
algo.

La lección que hay detrás está escrita en `src/proceso.py` desde el Paso 6: **una prueba mal
montada mide su propio andamiaje**. Aquí se cometió otra vez y se corrigió — ver
`test_el_detector_no_se_encuentra_a_si_mismo`.
"""

import os
import subprocess
import sys
import time
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import registrar_despertador as despertador  # noqa: E402
from tools import verificar_session0 as verificar  # noqa: E402


# =====================================================================
# 1. LA TAREA DE PRUEBA TIENE QUE SER LA DE VERDAD
# =====================================================================

def _xml_real():
    return despertador._construir_xml(hora="06:30", ejecutar_si_se_perdio=True, tope_minutos=60)


def _xml_prueba():
    return despertador._construir_xml(
        hora="06:30", ejecutar_si_se_perdio=True, tope_minutos=60,
        una_sola_vez=datetime(2026, 8, 25, 17, 30, 0),
        nota="[PRUEBA]",
    )


@pytest.mark.parametrize("fragmento", [
    "<LogonType>S4U</LogonType>",
    "-m src.lanzador --modo pipeline",
    "<StartWhenAvailable>true</StartWhenAvailable>",
])
def test_la_tarea_de_prueba_conserva_lo_que_se_esta_probando(fragmento):
    """Si la de prueba se construyera aparte, se parecería a la de verdad **hoy**.

    Y dejaría de parecérsele el día que alguien cambiara una de las dos, sin que nadie se
    enterara: seguiríamos ejecutando una verificación en verde sobre otra cosa.
    """
    assert fragmento in _xml_real()
    assert fragmento in _xml_prueba()


def test_la_tarea_de_prueba_se_dispara_una_sola_vez():
    """Una prueba que se repitiera cada día sería un despertador dado de alta de tapadillo."""
    prueba = _xml_prueba()

    assert "<TimeTrigger>" in prueba
    assert "2026-08-25T17:30:00" in prueba
    assert "ScheduleByDay" not in prueba, "la tarea de prueba quedó como diaria"


def test_la_tarea_de_verdad_sigue_siendo_diaria():
    """La otra cara: el refactor no puede haber convertido el despertador en algo de una vez."""
    real = _xml_real()

    assert "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>" in real
    assert "<TimeTrigger>" not in real


def test_la_tarea_de_prueba_se_anuncia_como_tal():
    """Quien la vea en el Programador dentro de un mes tiene que saber que puede borrarla."""
    assert "[PRUEBA]" in _xml_prueba()
    assert "[PRUEBA]" not in _xml_real()


def test_las_dos_tareas_tienen_nombres_distintos():
    """Verificar no puede dejar el despertador dado de alta como efecto colateral: darlo de
    alta es una decisión, y se toma aparte."""
    assert verificar.NOMBRE_PRUEBA != despertador.NOMBRE_TAREA


# =====================================================================
# 2. EL DETECTOR DE PROCESOS, QUE ES DONDE VIVE EL VEREDICTO
# =====================================================================

@pytest.mark.skipif(os.name != "nt", reason="la Session 0 y Win32_Process son de Windows")
def test_el_detector_encuentra_un_proceso_del_lanzador():
    """**Lo más importante de este fichero.** Un detector que no detecta daría siempre
    'ninguno', es decir, un ✅ eterno: la verificación entera sería un falso verde.

    Se comprueba con un proceso **real**, no con una lista simulada, porque lo que puede
    fallar es justamente la consulta al sistema.
    """
    senuelo = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(20)  # src.lanzador --modo pipeline"]
    )
    try:
        for _ in range(20):
            if senuelo.pid in verificar._procesos_del_lanzador():
                break
            time.sleep(0.5)
        assert senuelo.pid in verificar._procesos_del_lanzador(), (
            "el detector no ve un proceso del lanzador: el veredicto sería siempre verde"
        )
    finally:
        senuelo.kill()
        senuelo.wait()


def test_el_detector_no_se_encuentra_a_si_mismo(monkeypatch):
    """Descubierto probando el propio detector, y es la trampa de `src/proceso.py` otra vez.

    Un proceso que menciona `src.lanzador` en su línea de órdenes —como el que hace la
    comprobación— se encontraría a sí mismo, y el veredicto sería un ❌ eterno sin que nada
    estuviera mal.

    ⚠️ **Y esta prueba nació vacía.** La primera versión era
    `assert os.getpid() not in _procesos_del_lanzador()`, que pasa siempre bajo pytest —la
    línea de órdenes de pytest no menciona `src.lanzador`, así que no hay nada que excluir—.
    Quitar la exclusión del código **no la hacía fallar**. Se detectó mutando, y la única
    forma de que ejercite algo es **forzar que el sistema devuelva nuestro propio PID**, que es
    justo la situación que la exclusión existe para resolver. La lección de `src/proceso.py`
    otra vez, y en el mismo día: una prueba mal montada mide su propio andamiaje.
    """
    yo = os.getpid()
    ajeno = yo + 1

    class RespuestaFalsa:
        stdout = f"{yo}\n{ajeno}\n"

    monkeypatch.setattr(verificar.subprocess, "run", lambda *a, **k: RespuestaFalsa())

    encontrados = verificar._procesos_del_lanzador()

    assert yo not in encontrados, "el detector se cuenta a sí mismo: el veredicto sería un ❌ eterno"
    assert ajeno in encontrados, "excluirse no puede significar excluirlo todo"


# =====================================================================
# 3. EL RASTRO, QUE HOY VIENE ROTO
# =====================================================================

def test_los_eventos_se_leen_aunque_el_rastro_tenga_lineas_partidas(tmp_path, monkeypatch):
    """H-55: `pipeline.jsonl` tiene 11 líneas partidas y borrarlas sería destruir rastro.

    Cualquier lector suyo tiene que tolerarlas. Si esta herramienta reventara al encontrarse
    una, el veredicto de la Session 0 se perdería por un defecto que no tiene nada que ver.
    """
    rastro = tmp_path / "pipeline.jsonl"
    rastro.write_text(
        '{"timestamp": "2026-08-25T06:30:00Z", "action": "LANZADOR_INICIADO"}\n'
        's": 69.11}}\n'
        '{"timestamp": "2026-08-25T06:34:00Z", "action": "LANZADOR_PIPELINE_COMPLETADO"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(verificar, "ruta_datos", lambda *p: str(rastro))

    eventos = verificar._eventos_del_lanzador()

    assert "LANZADOR_INICIADO" in eventos
    assert "LANZADOR_PIPELINE_COMPLETADO" in eventos


# =====================================================================
# 4. NO DAR UN VEREDICTO QUE NO SE TIENE
# =====================================================================

def test_sin_prueba_preparada_no_hay_veredicto(tmp_path, monkeypatch, capsys):
    """Un ✅ sobre una prueba que nunca se ejecutó sería la peor salida posible."""
    monkeypatch.setattr(verificar, "_ruta_testigo", lambda: str(tmp_path / "no_existe.json"))

    assert verificar.revisar() == 2
    assert "No hay ninguna prueba preparada" in capsys.readouterr().out


def test_no_se_puede_preparar_sin_tiempo_para_cerrar_sesion(capsys):
    """Con un minuto no da tiempo a cerrar sesión, y la tarea se dispararía con ella abierta:
    el proceso no iría a la Session 0 y la prueba pasaría **sin haber probado nada**."""
    assert verificar.main(["--preparar", "--minutos", "1"]) == 2
    assert "no da tiempo" in capsys.readouterr().out
