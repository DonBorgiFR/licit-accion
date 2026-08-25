# Plan del Paso 8 — El Despertador (Capa 10)

> **Estado**: ✅ **Validado por dirección el 2026-08-25.** Con las dos decisiones tomadas:
> **tope de 60 minutos**, y **H-53 se repara antes** de abrir el paso.
> **Rige por encima de este plan**: [`CONTRATO_CAPA_10.md`](CONTRATO_CAPA_10.md) v1.2.0. Si algo de
> aquí lo contradice, manda el contrato.
> **De dónde sale el enunciado**: `README.md`, sección *"Paso 8 — El Despertador: Tarea Programada
> de Windows"*. Este documento no lo reinventa: lo convierte en pasos ejecutables.

---

## 1. Qué es esto, en una frase

Que el pipeline se ejecute **solo, de madrugada**, sin que nadie haga doble clic — y que si un día
se queda colgado, **se note y se corte**, en vez de dejar el sistema mudo noche tras noche.

## 2. Qué NO hace este paso

* **No avisa a nadie.** *(Decisión de dirección del 2026-08-12.)* El canal por el que el sistema
  habla es el Cockpit. "Despertador" es despertar al ecosistema, no a una persona.
* **No abre el navegador ni levanta la API.** Prospectar no las necesita, y en un entorno sin
  escritorio serían un puerto que vigilar y un proceso que apagar.
* **No toca `main.py` ni ninguna capa cerrada.** El lanzador envuelve; no modifica lo envuelto
  (Regla 14).

## 3. Decisiones ya tomadas — no se vuelven a plantear

| Decisión | Dónde vive | Cuándo se tomó |
|---|---|---|
| La ejecución automática se apoya en el Programador de tareas de Windows, no en un servicio propio | README, Consideraciones | 2026-08-12 |
| La tarea se da de alta **desde una herramienta del proyecto**, no a mano por la interfaz | README, artefactos | 2026-08-12 |
| Hora del despertador: **06:30** | `config/lanzador.yaml` | ya escrito |
| Si el equipo estaba apagado, se ejecuta al arrancar (`ejecutar_si_se_perdio: true`) | `config/lanzador.yaml` | ya escrito |
| La tarea invoca **Python directamente, nunca `Incoop.vbs`** | README + Paso 7 | 2026-08-18 |
| El modo *sólo pipeline* no hace **ni una** llamada gráfica | `CONTRATO_CAPA_10.md` §B | 2026-08-13 |
| **La tarea se da de alta en un solo equipo: `AROMAN`** | `ESTADO.md` | 2026-08-25 |

## 4. Lo que falta decidir, con recomendación

### 4.1 · El tope de duración — **recomendación: 60 minutos**

La Regla 4 prohíbe inventar plazos. **Esto no es inventado: sale de medir las 9 corridas reales que
hay en la base.**

| Corrida | Duración | Documentos | Segundos por documento |
|---|---|---|---|
| id 7 (19-08) | 47 s | 2 | 23,5 |
| id 9 (19-08) | 151 s | 30 | 5,0 |
| id 5 (18-08) | 155 s | 36 | 4,3 |
| id 3 (12-08) | 255 s | 63 | 4,0 |
| **id 12 (25-08)** | **487 s (8,1 min)** | 59 | 8,3 |

**La corrida más larga jamás observada son 8,1 minutos.** 60 minutos son **7,4 veces** eso, así que
deja sitio de sobra para una jornada con mucha más ingesta, que es lo que el README pide —margen
para el día malo, no para la media—.

**Y encaja con lo que ya existe**: la reapropiación del cerrojo son **6 horas**. Con un tope de 60
minutos, un cuelgue se corta **la misma noche** y a la mañana siguiente el sistema está sano. Sin
tope, el cerrojo lo tomaría un proceso **vivo**, el lanzador devolvería `30` —*"no prospecto, hay
una corrida en marcha"*— y **eso se repetiría cada noche**: el sistema no parecería averiado,
parecería que ya no hay oportunidades.

**Qué se hace al vencerlo: matarlo**, con la misma escalera de apagado del Paso 5 (`CTRL_BREAK` →
tiempo de gracia → `TerminateProcess`). El riesgo conocido es que el pipeline **borra ficheros
antes de tocar la base**, así que una interrupción a mitad de purga deja el fichero fuera y la fila
sin marcar. **Ese daño ya tiene reparación construida y probada**: es exactamente la forma de H-54,
y `tools/reconciliar_h54.py` la deshace midiendo contra el disco. Era un riesgo abstracto en agosto;
hoy es un riesgo con herramienta.

**Dónde vive el número**: `config/lanzador.yaml`, bloque `despertador`, subiendo la configuración a
**v1.1.0**. En ningún otro sitio.

### 4.2 · El OCR — **deja de ser un bloqueo si se repara H-53 antes**

Tesseract no está instalado en `AROMAN`, así que hoy un pliego escaneado no se puede leer. Eso, por
sí solo, no impide programar nada: el sistema ya tiene modo degradado y sigue.

**Lo que sí era grave es otra cosa**: `OCR_DIFERIDO` es un estado del que no se sale
(`obtener_documentos_para_ocr()` sólo mira `OCR_REQUERIDO`), de modo que instalar Tesseract mañana
**no recuperaría ni uno** de los pliegos que hubieran caído ahí. Eso convierte una carencia
reversible en una pérdida permanente.

**Recomendación**: reparar esa media línea **como hallazgo propio y antes del Paso 8** —es H-53,
está catalogado y es reproducible, así que Regla 14 lo permite—. Con eso, instalar Tesseract pasa a
ser una tarea de mantenimiento que se puede hacer cualquier día, y el Paso 8 deja de depender de
ello. **Hoy son 2 documentos de 268.**

---

## 5. Los pasos, en orden

### 8.1 · El tope, en la configuración

* `config/lanzador.yaml` → `despertador.duracion_maxima_minutos: 60`, versión de configuración a
  **v1.1.0**, y el comentario que hoy explica su ausencia pasa a explicar **de dónde sale el
  número** — las 9 corridas medidas.
* Su lector estricto en `src/lanzador.py`, sin valor por defecto: si falta o no es un entero
  positivo, **código 11** y no arranca. Misma doctrina que el resto del fichero.

### 8.2 · El tope, aplicado

* `prospectar()` vigila el subproceso del pipeline con el tope. Al vencer: **escalera de apagado
  del Paso 5** —`CTRL_BREAK_EVENT`, tiempo de gracia, `TerminateProcess`—, que ya está construida y
  medida.
* **Código de salida nuevo: `32` — *"el pipeline agotó su tope y fue detenido"*.** Está libre en el
  mapa del contrato y pertenece a la familia `3x`, la del pipeline. **No se reutiliza el `31`**: no
  es lo mismo *"reventó"* que *"no acababa"*, y el Programador de tareas es el único que va a leer
  esto.
* Evento `LANZADOR_PIPELINE_AGOTADO` con la duración real y el nivel de apagado que hizo falta.
* **Implica corregir el contrato a v1.3.0** (mapa de códigos). El contrato se corrige **antes** de
  escribir el código que lo obedece — es la lección del Paso 6.

### 8.3 · La herramienta del despertador

`tools/registrar_despertador.py`, con el modelo de `tools/crear_accesos_directos.py`:

```bash
python tools/registrar_despertador.py --estado   # ¿está dada de alta? ¿a qué hora? ¿cuándo corrió?
python tools/registrar_despertador.py --alta
python tools/registrar_despertador.py --baja
```

* **Idempotente**: dar de alta dos veces no crea dos tareas; dar de baja lo que no existe no es un
  error.
* Invoca **`python src/lanzador.py --modo pipeline`**, con rutas absolutas y `Start in` en la raíz
  del proyecto — **nunca `Incoop.vbs`**, cuyo diálogo colgaría en la Session 0 para siempre.
* Marca *"ejecutar tanto si el usuario ha iniciado sesión como si no"*, que es lo correcto para una
  tarea nocturna **y** lo que lleva el proceso a la Session 0.
* Lee la hora de `config/lanzador.yaml`. No la pregunta ni la codifica.
* **Deja constancia de en qué equipo se dio de alta** (`hostname`), porque la decisión del
  2026-08-25 es *un solo PC y que conste cuál*, y un fichero de acta no impide que alguien la dé de
  alta en el otro.

### 8.4 · La verificación que de verdad cierra el paso

**No es que la tarea se registre.** Es que **una corrida en Session 0 termina sola y no deja proceso
vivo**, porque el síntoma de un diálogo esperando a nadie es exactamente un proceso que no acaba.

1. Dar de alta la tarea con una hora inmediata, y dejarla correr **con la sesión cerrada**.
2. Comprobar al volver: la tarea consta como terminada, **no hay ningún `python.exe` huérfano**, la
  corrida figura `COMPLETED` en `ejecuciones`, y el Cockpit muestra la prospección.
3. Comprobar el código de salida que registró el Programador, y que coincide con el estado real de
  la corrida en la base — no con lo que el proceso creyó devolver.
4. Repetir con el cerrojo tomado a propósito, para ver el `30`.
5. Provocar el tope con un valor pequeño y comprobar el `32` y que **no queda proceso vivo**.

### 8.5 · Regresiones

En `tests/test_capa10_lanzador.py`, sumando a las 116 que ya hay:

* La configuración sin `duracion_maxima_minutos` → código 11, no arranca.
* Un valor no entero o negativo → código 11.
* Pipeline que excede el tope → código **32**, evento emitido, **proceso muerto**.
* Pipeline que termina justo por debajo del tope → código normal, **no se mata**.
* La herramienta es idempotente: dos altas, una sola tarea.
* La herramienta **rechaza** construir un comando que apunte al `.vbs`.

**Y comprobar cada una mutando la reparación, no revirtiéndola** — la lección del 2026-08-25: sobre
código nuevo, revertir sólo da `AttributeError`, que no prueba nada sobre el defecto.

### 8.6 · Cierre

`ESTADO.md`, `README.md` (Paso 8 a 🟢 y la cuestión abierta a resuelta), y el contrato a v1.3.0.

---

## 6. Lo que puede salir mal, y qué haríamos

| Riesgo | Probabilidad | Qué haríamos |
|---|---|---|
| El Programador no acepta la tarea sin contraseña guardada | **Media** — es lo típico de *"tanto si ha iniciado sesión como si no"* | Es un límite de Windows, no del código. La herramienta lo detecta y **lo dice**, en vez de registrar una tarea que no correrá. Puede requerir que la des de alta tú con tus credenciales. |
| El proceso queda vivo en Session 0 pese a todo | Baja | Es el fallo que este paso existe para impedir. Si ocurre, el diagnóstico es una llamada gráfica que se escapó de `es_sesion_interactiva()`, y se busca ahí. |
| Matar el pipeline a mitad de purga deja base y disco desalineados | Baja | Es H-54, y ya tiene herramienta: `tools/reconciliar_h54.py`. |
| El crash de H-41 se lleva una corrida nocturna | **Ya ha pasado una vez** | Un crash **libera** el cerrojo —el proceso muere—, así que la noche siguiente prospecta. Es el caso benigno frente a un cuelgue. Y ahora la migaja de H-41 deja rastro. |

## 7. Lo que este paso NO resuelve, y consta

* **H-41 sigue abierto.** Está localizado —la descarga del feed del DOGC— pero no diagnosticado. El
  despertador no lo empeora: lo hace ocurrir sin nadie delante, que es justo por lo que el tope
  importa.
* **H-52 / H-55** siguen difereridos al final del proyecto. Dar de alta la tarea en un solo equipo
  es la mitigación acordada, no la reparación.
* **El OCR** no se resuelve aquí, sólo se deja de perder de forma irreversible *(ver 4.2)*.
