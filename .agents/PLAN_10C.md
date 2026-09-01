# Plan del bloque 10.C — Cero terminal

> **Estado**: 🟢 **VALIDADO Y EJECUTADO el 2026-09-01.** Dirección confirmó las dos decisiones
> abiertas: el instalador **instala preguntando antes** *(5.2)* y lo que se ve va en **castellano**
> *(5.6)*. Suite **754 → 773**, y los dos envoltorios verificados con doble clic real.
>
> **Rige por encima de este plan**: [`CONTRATO_PASO_10.md`](CONTRATO_PASO_10.md) v1.4.0, sección I,
> bloque **10.C**; y la decisión de dirección **A.1 · Lector: cero terminal**.
>
> **De dónde sale el enunciado**: *«Envoltorio de doble clic para el despertador y para preparar un
> equipo nuevo»*, más la **Consideración 12** del README — *«la instalación en un equipo nuevo
> forma parte de la capa»*.

---

## 1. Qué es esto, en una frase

Que **dar de alta el despertador** y **dejar listo un PC nuevo** dejen de ser comandos, porque el
manual que viene después no puede mencionar una terminal.

## 2. Por qué el bloque existe, y por qué no es cosmético

La decisión A.1 dice que el `MANUAL.md` **no menciona una línea de comandos**. Hoy hay dos cosas
que sólo se pueden hacer escribiendo:

```bash
python tools/registrar_despertador.py --alta
pip install -r requirements.txt
```

El propio contrato lo advierte: dirección tomó el compromiso duro *«sabiendo que obliga a más
trabajo»*, porque **sin estos dos envoltorios la decisión sería un recorte del alcance
disfrazado** — un manual que no menciona la terminal, sobre un sistema que la necesita.

## 3. Lo que ya existe y no se rehace

| | |
|---|---|
| `Incoop.vbs` | 🟢 Paso 7. **La doctrina del bloque ya está fijada aquí**: el `.vbs` no tiene lógica —*«VBScript no se puede probar con la suite, así que todo lo que pueda romperse vive en Python»*—, sólo abre la puerta con `pythonw.exe` y la ventana oculta |
| `tools/crear_accesos_directos.py` | 🟢 Paso 7. Alta y baja idempotentes en escritorio y menú de inicio, con `Incoop.ico` a siete tamaños |
| `tools/registrar_despertador.py` | 🟢 Paso 8. `--alta`, `--baja`, y sin argumentos **informa del estado sin tocar nada** |
| `ejecutar_healthcheck()` *(`src/lanzador.py`)* | 🟢 Paso 3. Comprueba Python, dependencias, configuración, base, espacio, bundle y puerto — **y cada comprobación trae su `remedio`** |
| `frontend/dist/` | 🟢 Compilado y versionado. **Un equipo nuevo no necesita Node.js**, sólo Python |

> 🔑 **El healthcheck es el mayor hallazgo de este reconocimiento.** El instalador no tiene que
> inventar qué comprobar ni cómo explicarlo: `Comprobacion` ya lleva `nombre`, `ok`, `detalle` y
> **`remedio`**, y ese campo nació exactamente para esto — *«el arranque en frío es el momento en
> que más falta hace un diagnóstico claro y el único en que no hay nadie experto delante»*.

## 4. Lo que este bloque NO hace

* **No instala Python.** Es lo único que la persona tiene que hacer antes, y el `MsgBox` de
  `Incoop.vbs` ya lo explica cuando falta.
* **No instala Tesseract** *(ver decisión 5.5)*.
* **No compila el frontend.** El bundle viene hecho.
* **No toca `src/lanzador.py` ni el despertador.** Los envuelve; no modifica lo envuelto *(Regla 14)*.
* **No es la verificación en vivo.** Eso es el bloque **10.E**, y va después a propósito.

## 5. Lo que falta decidir, con recomendación

### 5.1 · Cómo se ve un instalador sin terminal — **recomendación: una ventana de Python (tkinter)**

Tres caminos, y el problema que los separa es que **`pip install` tarda minutos**:

| | Qué se ve | Por qué no |
|---|---|---|
| **A · Ventana de tkinter** ✅ | Los pasos, uno a uno, con su resultado; al final el veredicto del healthcheck con sus remedios | — |
| **B · Oculto + un `MsgBox` al final** | Nada durante varios minutos, y luego un cartel | **Parece colgado.** Y quien cree que algo se ha colgado, lo mata |
| **C · Consola visible** | La salida de `pip`, en negro | Contradice A.1 en espíritu: el manual tendría que explicar una consola |

**tkinter está en la biblioteca estándar** y verificado en este equipo *(Tk 8.6, Python 3.12.10)*.
**Y respeta la doctrina del Paso 7**: el `.vbs` sigue siendo tres líneas, y lo que puede romperse
—los pasos, su orden, el veredicto— vive en Python, separado de la ventana para poder probarlo sin
abrir ninguna.

> ⚠️ **Con un respaldo declarado**: si `import tkinter` fallara —hay instalaciones de Python sin
> tcl/tk—, el instalador **no se cae**: escribe el informe en un fichero de texto, lo abre con el
> Bloc de notas y termina. Un instalador que no arranca porque no puede dibujarse a sí mismo sería
> el peor sitio posible para fallar.

### 5.2 · ¿El instalador instala, o sólo comprueba? — **recomendación: instala, pero pregunta antes**

Comprobar y decir *«te falta esto»* deja a la persona en el mismo sitio: sin terminal para
arreglarlo. **Instala.** Pero `pip install` descarga de internet y modifica el equipo, así que la
ventana **empieza enseñando lo que va a hacer y espera un clic**, no arranca sola.

### 5.3 · El despertador: **un solo envoltorio, no dos**

Dos iconos —*«Activar despertador»* y *«Desactivar despertador»*— invitan a equivocarse y no
contestan la pregunta que la persona tiene de verdad, que es **«¿está activo?»**. Se propone uno:

```
Despertador.vbs  ->  pythonw -m tools.despertador_ventana
```

que abre una ventana con **el estado actual** *(«Activo, todas las noches a las 06:30 en este
equipo»* / *«No está dado de alta»*) y un solo botón, el que proceda. La lógica sigue siendo la de
`tools/registrar_despertador.py`, sin tocarla.

### 5.4 · Dónde va cada icono

| Envoltorio | Escritorio | Menú de inicio | Raíz del proyecto |
|---|---|---|---|
| `Incoop` *(ya existe)* | ✅ | ✅ | ✅ |
| **`Preparar equipo`** | ❌ | ❌ | ✅ |
| **`Despertador`** | ❌ | ✅ | ✅ |

**Preparar un equipo se hace antes de que existan los accesos directos** —de hecho es quien los
crea—, así que sólo puede vivir en la carpeta del proyecto, junto a `Incoop.vbs`. Y **el escritorio
es para el uso diario**: llenarlo de iconos de una-sola-vez le quita valor al que sí se usa cada
día.

### 5.5 · Tesseract — **recomendación: detectar y explicar, nunca instalar en silencio**

El OCR necesita un binario que `pip` no puede traer. Instalarlo por nuestra cuenta significaría
descargar y ejecutar un instalador de terceros sin que nadie lo haya pedido. **Se comprueba y se
dice**: si falta, el informe final lo marca como aviso —no como fallo, porque el sistema arranca
igual y degrada— con la instrucción de qué instalar. **Es la lección de H-53**: el OCR llevaba
meses sin funcionar y nadie lo sabía porque nadie lo comprobaba.

### 5.6 · El idioma de lo que se ve

`MANUAL.md` va en catalán *(decisión D.2)*, y *«el resto sigue en castellano»*. Los nombres de los
iconos y los textos de las ventanas **no son documentos**, pero sí los lee la misma persona.
**Recomendación: castellano**, por coherencia con D.2 y con `Incoop.vbs`, que ya está así. *Si
dirección prefiere catalán en lo que se ve en pantalla, es el momento de decirlo: cambiarlo después
obliga a rehacer el manual.*

## 6. Los dos artefactos

### 6.1 · `Preparar equipo.vbs` → `tools/preparar_equipo.py`

Los pasos, en orden, **todos idempotentes** —volver a ejecutarlo no puede romper un equipo que ya
funcionaba—:

| | Paso | Qué hace si ya está |
|---|---|---|
| 1 | Comprobar el intérprete de Python | — |
| 2 | **Instalar las dependencias** de `requirements.txt` | `pip` no reinstala lo que ya está |
| 3 | Crear `data/` y **migrar la base al esquema vigente** | `setup_db()` ya es idempotente |
| 4 | Comprobar el bundle del Cockpit | — |
| 5 | **Crear los accesos directos** *(`crear_accesos_directos.alta()`)* | Ya es idempotente |
| 6 | Ofrecer dar de alta el despertador *(casilla, marcada por defecto)* | Ya es idempotente |
| 7 | **Ejecutar `ejecutar_healthcheck()` y mostrar el veredicto** con sus remedios | — |

> 🔑 **El paso 7 es el que hace honesto al bloque.** Sin él, el instalador diría *«listo»* porque
> no le ha fallado ningún paso, que es exactamente la clase de afirmación que este proyecto lleva
> un mes desmontando. Con él, dice **qué comprueba y qué le sale**.

### 6.2 · `Despertador.vbs` → `tools/despertador_ventana.py`

Lee el estado con la función que ya existe, lo enseña en una frase, y ofrece **el botón contrario
al estado actual**. Al terminar, vuelve a leer el estado y lo muestra: **no se afirma el resultado,
se comprueba** *(es medir el efecto en vez de dar por bueno que se ejecutó, la misma doctrina que
el lanzador aplica a los códigos de salida)*.

## 7. Las pruebas

**Ni el `.vbs` ni la ventana se prueban con pytest**, y por eso ninguno de los dos lleva lógica.
Lo que se prueba es la capa de debajo:

| | Qué afirma |
|---|---|
| **R1** | Los pasos se ejecutan **en orden** y cada uno reporta `ok`/`detalle`/`remedio` |
| **R2** | **Idempotencia**: dos ejecuciones seguidas dejan el mismo estado y ninguna falla |
| **R3** | Un paso que falla **no detiene los siguientes** ni se traga el error *(C2)*, y el veredicto final lo refleja |
| **R4** | El informe final **incluye el healthcheck**, no sólo los pasos propios |
| **R5** | Sin `tkinter`, **no se toca el equipo**: se escribe el motivo y el remedio, y se termina con un código distinguible |

> ⚠️ **La R5 cambió al escribirla, y el cambio importa.** El plan decía *«se escribe el informe»*,
> que habría significado **preparar el equipo sin poder preguntar** — justo lo que la decisión 5.2
> prohíbe, porque descarga de internet y modifica la máquina. Sin ventana no se hace nada: se
> explica por qué y cómo arreglarlo. *Otra vez el papel corregido al ir a obedecerlo.*
| **R6** | La ventana del despertador **relee el estado** después de actuar, en vez de afirmarlo |

**Ninguna sale a la red ni instala nada de verdad**: el paso de `pip` se ejercita con un doble que
registra la orden *(Convención C5)*.

## 8. La verificación que cierra el bloque

Del contrato: *«Ejecutarlos con doble clic, sin consola visible»*. En concreto:

1. **Doble clic en `Preparar equipo`** sobre este equipo —que ya está preparado— y comprobar que
   **no rompe nada** y termina diciendo la verdad.
2. **Doble clic en `Despertador`**, ver el estado real, y usar el botón: dar de baja y volver a dar
   de alta, comprobando con `schtasks` que la tarea existe y con la hora correcta.
3. **Ninguna consola negra** en ninguno de los dos.

> ⚠️ **Lo que este bloque NO puede verificar aquí, y hay que decirlo**: el arranque en frío de
> verdad —un equipo sin dependencias— no se puede probar en esta máquina sin romperla. Se verifica
> lo que sí se puede *(idempotencia y veredicto)*, y **el escenario limpio queda para el bloque
> 10.E**, con un entorno virtual desechable.

## 9. Orden de ejecución

| | Paso |
|---|---|
| 1 | `tools/preparar_equipo.py`: la lógica y sus regresiones R1-R5, sin ventana |
| 2 | La ventana de tkinter, delgada, y `Preparar equipo.vbs` |
| 3 | `tools/despertador_ventana.py` + R6 y `Despertador.vbs` |
| 4 | Añadir `Despertador` al menú de inicio en `crear_accesos_directos.py` |
| 5 | **Suite completa** y **doble clic de verdad** en los dos |
| 6 | README *(cómo opera)*, `ESTADO.md` y contrato |

## 10. Ficheros

| Fichero | Qué es |
|---|---|
| `tools/preparar_equipo.py` | **Nuevo.** Los pasos, el veredicto y el informe |
| `tools/despertador_ventana.py` | **Nuevo.** Estado y botón |
| `Preparar equipo.vbs` · `Despertador.vbs` | **Nuevos.** Tres líneas cada uno |
| `tests/test_paso10_preparar_equipo.py` | **Nuevo.** R1-R6 |
| `tools/crear_accesos_directos.py` | Una entrada más en `ACCESOS` *(sólo menú de inicio)* |

## 11. Riesgos

| | Riesgo | Mitigación |
|---|---|---|
| **R-a** | `pip install` sin red deja el equipo a medias | Cada paso reporta por separado; el healthcheck final dice qué falta y con qué remedio |
| **R-b** | Una ventana de tkinter que no se puede probar esconde defectos | La ventana **no decide nada**: pide los pasos a la capa de abajo y los pinta |
| **R-c** | Ejecutarlo en un equipo ya preparado lo estropea | La idempotencia es R2, y se verifica con doble clic sobre este mismo equipo |
| **R-d** | El instalador afirma *«listo»* sin comprobarlo | Es el paso 7: el veredicto sale del healthcheck, no de que no haya fallado nada |
