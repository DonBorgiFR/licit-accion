"""Preparar un equipo nuevo sin escribir un comando — Capa 10, Paso 10, bloque C.

Plan: `.agents/PLAN_10C.md`. Decisión de dirección **A.1 · cero terminal**.

**QUÉ SE PRUEBA AQUÍ Y QUÉ NO.** Ni el `.vbs` ni la ventana de tkinter se pueden ejercitar con
pytest, y por eso **ninguno de los dos lleva lógica**: es la misma doctrina con la que el Paso 7
dejó `Incoop.vbs` en tres líneas. Lo que se prueba es la capa de debajo — qué pasos hay, en qué
orden, qué reportan y qué veredicto sale.

**NINGUNA SALE A LA RED NI INSTALA NADA** *(Convención C5)*: el paso de `pip` recibe siempre un
doble que registra la orden sin ejecutarla, y los accesos directos también — si no, la suite
crearía iconos en el escritorio de quien la ejecute.

**LA PRUEBA QUE MÁS PROTEGE ES LA DE IDEMPOTENCIA.** Esta herramienta se va a ejecutar sobre
equipos ya preparados —por costumbre, por duda o por error— y no puede estropear ninguno.
"""

import os
import subprocess

import pytest

from tools import preparar_equipo
from tools.preparar_equipo import Informe, Resultado, preparar


def instalador_falso(registro):
    """Un `pip` que no instala nada y anota que se le llamó."""
    def instalar(requirements):
        registro.append(requirements)
        return subprocess.CompletedProcess(args=["pip"], returncode=0, stdout="", stderr="")
    return instalar


def preparar_sin_tocar_nada(**extra):
    """La invocación estándar de estas pruebas: pip y accesos directos, doblados."""
    registro = []
    informe = preparar(
        instalador=instalador_falso(registro),
        alta_accesos=lambda: None,
        **extra,
    )
    return informe, registro


# ==============================================================================
# R1 · Los pasos, en orden y con lo que cada uno reporta
# ==============================================================================


def test_los_pasos_se_ejecutan_en_orden(tmp_path):
    informe, registro = preparar_sin_tocar_nada()

    nombres = [r.nombre for r in informe.pasos]
    assert nombres == [
        "Python", "Dependencias", "Base de datos", "Pantalla del Cockpit",
        "Accesos directos", "Lectura de PDF escaneados (OCR)",
    ], "el orden importa: instalar dependencias antes de migrar la base, y migrar antes de comprobar"
    assert len(registro) == 1, "pip se invoca una vez, con el requirements del proyecto"
    assert registro[0].endswith("requirements.txt")


def test_el_despertador_solo_se_da_de_alta_si_se_pide():
    sin, _ = preparar_sin_tocar_nada()
    con, _ = preparar_sin_tocar_nada(con_despertador=True, alta_despertador=lambda: 0)

    assert "Despertador" not in [r.nombre for r in sin.pasos]
    assert con.pasos[-1].nombre == "Despertador"
    assert con.pasos[-1].ok


def test_cada_paso_dice_qué_pasó(tmp_path):
    informe, _ = preparar_sin_tocar_nada()

    for resultado in informe.pasos:
        assert resultado.nombre and resultado.detalle, (
            f"'{resultado.nombre}' no explica nada, y este informe es lo único que "
            "verá alguien sin experiencia delante"
        )


# ==============================================================================
# R2 · Idempotencia: la que protege de estropear un equipo que ya funcionaba
# ==============================================================================


def test_ejecutarlo_dos_veces_deja_el_mismo_estado():
    primero, _ = preparar_sin_tocar_nada()
    segundo, _ = preparar_sin_tocar_nada()

    assert [(r.nombre, r.ok) for r in primero.pasos] == [(r.nombre, r.ok) for r in segundo.pasos]
    assert primero.listo == segundo.listo


# ==============================================================================
# R3 · Un paso que falla no detiene a los siguientes, y no se traga el error
# ==============================================================================


def test_un_paso_que_falla_no_detiene_los_siguientes():
    """Un instalador que se para en el primer tropiezo obliga a ejecutarlo cinco veces para
    enterarse de cinco cosas."""
    def pip_roto(requirements):
        return subprocess.CompletedProcess(
            args=["pip"], returncode=1, stdout="", stderr="No matching distribution found",
        )

    informe = preparar(instalador=pip_roto, alta_accesos=lambda: None)

    nombres = [r.nombre for r in informe.pasos]
    assert "Dependencias" in nombres
    assert nombres[-1] == "Lectura de PDF escaneados (OCR)", "los siguientes se ejecutaron igual"

    dependencias = next(r for r in informe.pasos if r.nombre == "Dependencias")
    assert not dependencias.ok
    assert "No matching distribution found" in dependencias.detalle, "el motivo consta (C2)"
    assert dependencias.remedio, "y con qué hacer al respecto"
    assert not informe.listo


def test_una_excepcion_de_un_paso_se_convierte_en_resultado_y_no_revienta():
    """`pip` que ni siquiera arranca. La herramienta no puede caerse: es el único canal que hay."""
    def pip_inexistente(requirements):
        raise OSError("no se encuentra el intérprete")

    informe = preparar(instalador=pip_inexistente, alta_accesos=lambda: None)

    dependencias = next(r for r in informe.pasos if r.nombre == "Dependencias")
    assert not dependencias.ok
    assert "no se encuentra el intérprete" in dependencias.detalle


def test_los_accesos_directos_no_son_criticos():
    """Sin iconos el sistema se sigue usando desde `Incoop.vbs`. Marcarlo como fallo mandaría a
    alguien a resolver lo que no impide trabajar."""
    def alta_rota():
        raise RuntimeError("Windows no devolvió las carpetas")

    informe = preparar(instalador=instalador_falso([]), alta_accesos=alta_rota)

    accesos = next(r for r in informe.pasos if r.nombre == "Accesos directos")
    assert not accesos.ok and not accesos.critico
    assert accesos in informe.avisos and accesos not in informe.fallos


# ==============================================================================
# R4 · El veredicto lo da el healthcheck, no el hecho de que no haya fallado nada
# ==============================================================================


def test_el_informe_incluye_como_quedo_el_equipo():
    """Terminar diciendo «listo» porque ningún paso ha fallado es la clase de afirmación que
    este proyecto lleva un mes desmontando."""
    informe, _ = preparar_sin_tocar_nada()

    assert informe.comprobaciones, "sin healthcheck final, el informe afirma sin comprobar"
    for comprobacion in informe.comprobaciones:
        assert comprobacion.nombre and comprobacion.detalle


def test_listo_es_falso_si_el_healthcheck_encuentra_un_fallo(monkeypatch):
    monkeypatch.setattr(
        preparar_equipo, "comprobar_como_quedo",
        lambda: [Resultado("Base de datos", False, "no se puede abrir", remedio="cerrar el Cockpit")],
    )

    informe, _ = preparar_sin_tocar_nada()

    assert not informe.listo, "los pasos fueron bien y el equipo no está listo: manda el healthcheck"
    assert len(informe.fallos) == 1


# ==============================================================================
# El informe que lee una persona
# ==============================================================================


def test_el_texto_del_informe_dice_el_remedio_de_lo_que_falla():
    informe = Informe(
        pasos=[Resultado("Dependencias", False, "pip falló", remedio="Comprobar la conexión")],
        comprobaciones=[Resultado("Python", True, "versión 3.12")],
    )

    texto = informe.texto()

    assert "Dependencias" in texto and "Comprobar la conexión" in texto
    assert "QUEDAN 1 COSA(S) POR RESOLVER" in texto


def test_un_aviso_no_impide_declarar_el_equipo_listo():
    """Tesseract ausente es el caso real: el OCR degrada y todo lo demás funciona."""
    informe = Informe(
        pasos=[Resultado("Lectura de PDF escaneados (OCR)", False, "no instalado",
                         remedio="opcional", critico=False)],
        comprobaciones=[Resultado("Python", True, "versión 3.12")],
    )

    assert informe.listo
    assert "LISTO, con 1 aviso" in informe.texto()


# ==============================================================================
# R5 · Sin tkinter no se prepara nada a espaldas de nadie
# ==============================================================================


def test_sin_ventana_no_se_toca_el_equipo_y_se_explica(tmp_path):
    """**Ajuste sobre el plan, decidido al escribir el código.**

    El plan decía *«sin tkinter, se escribe el informe»*, y eso habría significado **preparar el
    equipo sin poder preguntar** — justo lo que la decisión 5.2 prohíbe, porque descarga de
    internet y modifica la máquina. Lo que se escribe es el motivo y el remedio; el equipo no se
    toca.
    """
    from tools.preparar_equipo_ventana import SIN_VENTANA, escribir_aviso_sin_ventana

    destino = escribir_aviso_sin_ventana(str(tmp_path / "aviso.txt"))
    texto = open(destino, encoding="utf-8").read()

    assert "NO se ha hecho ningún cambio en el equipo" in texto
    assert "tcl/tk" in texto, "y dice qué reinstalar, que es el remedio"
    assert SIN_VENTANA == 2, "un código propio: no habla del equipo, habla de la ventana"


# ==============================================================================
# R6 · El despertador: no se afirma el resultado, se vuelve a mirar
# ==============================================================================


def estado_falso(activo):
    from tools.despertador_ventana import Estado
    return Estado(activo=activo, hora="06:30", equipo="AROMAN")


def test_activar_el_despertador_relee_el_estado():
    """La misma doctrina con la que el lanzador dejó de fiarse de los códigos de salida."""
    from tools.despertador_ventana import cambiar

    leidos = []

    def leer():
        leidos.append(1)
        return estado_falso(activo=True)

    consiguio, mensaje, estado = cambiar(True, alta=lambda: 0, baja=lambda: 0, leer=leer)

    assert consiguio and not mensaje
    assert estado.activo
    assert leidos, "el estado se comprobó después de actuar, no se dio por bueno"


def test_una_orden_que_dice_cero_y_no_cambia_nada_no_es_un_exito():
    """El caso que este proyecto lleva un mes persiguiendo: éxito declarado sin efecto."""
    from tools.despertador_ventana import cambiar

    consiguio, mensaje, estado = cambiar(
        True, alta=lambda: 0, baja=lambda: 0, leer=lambda: estado_falso(activo=False),
    )

    assert not consiguio, "devolvió 0 y la tarea sigue sin existir"
    assert "no ha cambiado" in mensaje
    assert not estado.activo, "y se informa del estado real, no del pretendido"


def test_si_el_programador_rechaza_el_cambio_se_dice_por_que():
    from tools.despertador_ventana import cambiar

    consiguio, mensaje, _ = cambiar(
        True, alta=lambda: 1, baja=lambda: 0, leer=lambda: estado_falso(activo=False),
    )

    assert not consiguio
    assert "permisos" in mensaje, "el remedio, no sólo el síntoma"


def test_una_excepcion_al_cambiar_no_tumba_la_ventana():
    from tools.despertador_ventana import cambiar

    def alta_rota():
        raise RuntimeError("schtasks no está")

    consiguio, mensaje, estado = cambiar(
        True, alta=alta_rota, baja=lambda: 0, leer=lambda: estado_falso(activo=False),
    )

    assert not consiguio
    assert "schtasks no está" in mensaje
    assert estado is not None, "y sigue habiendo un estado que enseñar"


# ==============================================================================
# El acceso del despertador: dónde va y a qué apunta
# ==============================================================================


def test_el_acceso_del_despertador_solo_va_al_menu_de_inicio():
    """Decisión 5.4: el escritorio es para lo que se usa cada día."""
    from tools.crear_accesos_directos import _rutas

    rutas = _rutas(["C:/Escritorio", "C:/Menu/Incoop"])
    despertador = [r for r in rutas if "Despertador" in r[0]]

    assert len(despertador) == 1
    assert despertador[0][0].startswith("C:/Menu/Incoop"), "no va al escritorio"
    assert despertador[0][1].endswith("Despertador.vbs"), "y apunta a su propio envoltorio"


def test_el_acceso_del_despertador_abre_su_envoltorio_y_no_el_de_incoop(tmp_path):
    """Se lee el `.lnk` real que escribe Windows, no la orden que creímos darle *(C4)*.

    Sin esta prueba, el acceso podría apuntar a `Incoop.vbs` —que es lo que hacían los tres
    hasta el bloque 10.C— y **abriría el Cockpit y prospectaría** en vez de enseñar el estado
    del despertador. Un icono que hace otra cosa es peor que un icono que falta.
    """
    from tools.crear_accesos_directos import alta

    carpeta = str(tmp_path / "accesos")
    os.makedirs(carpeta)
    creados, _ = alta([carpeta])

    ruta = next(r for r in creados if "Despertador" in os.path.basename(r))
    with open(ruta, "rb") as fichero:
        contenido = fichero.read()

    assert "Despertador.vbs".encode("utf-16-le") in contenido
    assert "completo".encode("utf-16-le") not in contenido, "no arranca una prospección"


def test_la_frase_del_estado_dice_lo_que_le_importa_a_una_persona():
    activo = estado_falso(activo=True).frase()
    inactivo = estado_falso(activo=False).frase()

    assert "ACTIVADA" in activo and "06:30" in activo and "AROMAN" in activo
    assert "no se pierde el día" in activo, "la duda real: qué pasa si el PC estaba apagado"
    assert "DESACTIVADA" in inactivo and "a mano" in inactivo
