# Contrato de Servicio — Reparación del ciclo de vida ante feeds de ventana móvil

**Versión**: v1.0.0 · **Redactado**: 2026-08-19 · **Estado**: 🟢 **completado el 2026-08-19** (el Paso 3 se descartó, ver apartado F)
**Repara**: H-48 y H-49 · **Precede a**: Bloque 3 — Identidad y foco

> **Por qué existe este documento y no se parchea y ya.** Los dos defectos que repara no rompen
> nada: **deciden mal en silencio** y esconden 19.986.870,63 € en oportunidades con el plazo
> abierto, incluidas las dos mejor puntuadas de la base. Tocan `src/memoria.py` y `src/radar.py`,
> que pertenecen a **capas cerradas y validadas**, así que la Regla 14 exige decir por adelantado
> qué cambia, qué no cambia y cómo se comprueba que no se ha roto nada.

---

## A · La premisa equivocada, que es lo único que hay que entender

El sistema trata **la ausencia de una licitación en el feed** como prueba de que ha terminado. El
motivo que escribe en la base lo dice con todas las letras: *"Ausente en el feed de licitaciones
**vigentes**"*.

**Ninguna de las tres fuentes publica un censo de licitaciones vigentes.** Las tres son ventanas
de publicaciones recientes:

| Fuente | Qué devuelve realmente |
|---|---|
| `PSCP Catalunya API` | `$order: data_publicacio_anunci DESC`, `$limit: 100` — las **100 publicaciones más recientes** (`src/radar.py:357`) |
| `PCSP Estatal` | Una sola página ATOM; `fetch_feed()` **no sigue la paginación** (`src/radar.py:90`) |
| `CCAA Agregadas` | Igual que la anterior |

Una licitación sale de la ventana **por antigüedad de publicación**, no por haber terminado. Su
ausencia no es información sobre su vigencia, y el sistema la usa como si lo fuera.

> **Corolario incómodo pero necesario**: con estas fuentes **no se puede detectar una anulación**
> a partir de la ausencia, porque es indistinguible de la rotación de la ventana. El sistema no
> debe afirmar lo que no puede medir *(Convención C6)*.

---

## B · Alcance: qué se toca y qué no

**Se repara:**

1. La rama `Nueva` de `Memoria.soft_delete_obsoletos()` (`src/memoria.py:1610`), que archiva sin
   consultar la fecha límite.
2. La normalización del identificador de expediente en `Radar._normalize_socrata_item()`
   (`src/radar.py:385`).
3. ~~Los **45 lotes ya archivados por error**~~ — **descartado el 2026-08-19**, ver apartado F.

**NO se toca, y es deliberado:**

* **La rama de *posible anulación*** (lotes que no están en `Nueva`). Medido: de los 48 lotes
  archivados por ausencia, **los 48 salieron de la rama `Nueva`**; esa rama **no se ha disparado
  ni una vez**. Reparar sólo `Nueva` corrige el **100 % del daño medido**, y así el contrato de la
  Capa 9 —que cita literalmente el escenario `Presentada → Anulada_Administracion`— queda intacto,
  con su prueba `test_el_radar_deja_constancia_del_estado_que_pisa` pasando sin cambios.
* **La paginación de los feeds.** Que las fuentes sean ventanas es un hecho a respetar, no un
  defecto a corregir aquí. Ampliar la captura es otra conversación, con su propio coste.
* **El scoring, el perfil comercial y la política de retención.** Ni una línea.
* **El Depurador.** Ya archiva por fecha límite, que es el criterio correcto, y está validado.

---

## C · Máquina de estados (Regla 2)

Estado de un lote **ausente del feed** en la corrida actual, en función de su estado operativo y
de su fecha límite:

| Estado operativo | Fecha límite | HOY (defectuoso) | CONTRATADO |
|---|---|---|---|
| `Nueva` | **abierta** | ❌ `Inactiva` *(expirado)* | ✅ **sin cambio de estado** + evento |
| `Nueva` | vencida | `Inactiva` *(expirado)* | ✅ **igual**: `Inactiva` *(expirado)* |
| `Nueva` | ilegible o ausente | `Inactiva` *(expirado)* | ✅ **sin cambio de estado** + evento |
| No `Nueva`, no archivado | abierta | `Anulada_Administracion` + alerta | ✅ **igual** *(sin tocar)* |
| No `Nueva`, no archivado | vencida | sin cambio | ✅ **igual** |
| Ya archivado | cualquiera | sin cambio | ✅ **igual** |

**Transiciones prohibidas:**

1. `Nueva` **con plazo abierto** → `Inactiva` por ausencia del feed. **Es el defecto H-48.**
2. `Nueva` **sin fecha límite legible** → `Inactiva`. Ante la duda no se archiva: el daño es
   asimétrico y está medido en 19,99 M€ frente al coste de mostrar de más una licitación muerta.
3. Cualquier transición que el Radar escriba sobre un estado que no sea `Nueva`, más allá de la
   rama de anulación ya existente.
4. Rescatar un lote cuyo plazo **ya venció** — eso no es reparar, es desarchivar basura.

---

## D · Contrato de `soft_delete_obsoletos()` (Regla 1)

* **Input**: `ejecucion_start_utc: str` (ISO-8601 UTC). Sin cambios.
* **Output**: `None`. **Cambia**: pasa a devolver un resumen `{revisados, expirados, ignorados_plazo_abierto, ignorados_sin_fecha, anulaciones}` para que la corrida pueda informar (Regla 7). *(El quinto contador se añadió al implementar el Paso 2: la máquina de estados ya distinguía «sin fecha legible» de «plazo abierto», y contarlos juntos habría escondido el caso raro dentro del normal.)*
* **Precondición**: la base es accesible y la corrida está registrada. Sin cambios.
* **Postcondición**: ningún lote `Nueva` con fecha límite posterior a la fecha actual queda con
  `deleted_at` escrito por esta función.
* **Side-effects**: escrituras en `lotes` y `expedientes.log_cambios` **sólo** en los casos que la
  tabla de C autoriza; eventos en `data/pipeline.jsonl`.
* **Errores tipados**: sin errores nuevos. Un `fecha_limite` ilegible **no es un error**: es el
  caso 3 de la tabla y se resuelve no archivando.
* **Versionado**: `VERSION_OBSOLESCENCIA = "1.0.0"`, estampada en el evento de resumen.
  *(Corregido al implementar el Paso 2: el contrato decía "junto a las demás versiones de la
  corrida", lo que implicaba columna en `ejecuciones` y por tanto esquema v9. No procede. Este
  barrido no persiste un artefacto por fila cuya lectura dependa de la versión —que es lo que
  justifica `version_scoring` en `lotes`—: sólo decide, y el histórico de sus decisiones es el
  JSONL. Migrar el esquema para esto habría sido pagar una migración por un dato que nadie
  consultaría desde la base.)*

**Eventos JSONL nuevos** (Regla 3):

| Evento | Cuándo |
|---|---|
| `RADAR_AUSENCIA_IGNORADA_PLAZO_ABIERTO` | Un lote `Nueva` ausente del feed conserva su estado porque su plazo sigue abierto. Lleva `expediente_id`, `fecha_limite` y días restantes. |
| `RADAR_AUSENCIA_SIN_FECHA_LIMITE` | Un lote `Nueva` ausente sin fecha legible. Hoy no debería emitirse nunca: `fecha_limite` es legible en 63 de 63. |
| `RADAR_OBSOLESCENCIA_RESUMEN` | Cierre del barrido, con la versión de la política y los cinco contadores del Output. |

---

## E · Contrato de la normalización del identificador (H-49)

* **Regla**: antes de usarse como clave, el identificador colapsa espacios repetidos y recorta los
  extremos. **No** se cambia mayúsculas/minúsculas ni se eliminan signos: sería una normalización
  más agresiva de lo que la evidencia sostiene.
* **Evidencia que la justifica**: `"EXPEDIENT  214 2026 - CONTRACTACIÓ SERVEI"` y
  `"EXPEDIENT214 2026 - CONTRACTACIÓ SERVEI"` son la misma licitación —mismo UUID de publicación
  `f7bb55cd-…`, ingeridas en el mismo segundo— y entraron como dos expedientes.
* **Versionado**: `version_normalizacion_id = "1.0.0"`.

> ⚠️ **Lo que este contrato NO autoriza**: cambiar la clave primaria de los expedientes ya
> ingeridos, ni fusionar los duplicados existentes. **Colapsar dos filas en una es irreversible y
> arrastra documentos, lotes y análisis.** Queda como paso propio, y sólo si dirección lo pide tras
> ver cuántos duplicados hay de verdad. La normalización sólo evita duplicados **nuevos**.

---

## F · El rescate de los 45 — ❌ **DESCARTADO por dirección el 2026-08-19**

**No se hace.** Se llegó a implementar y a probar (11 regresiones en verde) y **se retiró entero**:
`src/depurador.py` vuelve a estar byte a byte como estaba.

**El motivo, y es el bueno.** Dirección preguntó para qué queríamos recuperar datos de licitaciones
públicas que están en internet, y la pregunta correcta no era *"¿se pueden recuperar?"* sino
**"¿le sirven hoy a alguien?"**. No. El sistema es una beta, la demo no ha ocurrido, y nadie va a
presentar una oferta porque la vea en el Funnel. Choca de frente con la decisión del **2026-08-17**,
tomada por la propia dirección: *hasta la demo los datos son material de prueba, no un activo, y
perderlos es aceptable siempre que se sepa por qué*. Se sabe por qué: era H-48.

> 🔑 **Cómo se llegó a proponer algo que contradecía una decisión vigente.** El Paso 3 se escribió
> en este contrato con el hallazgo recién hecho y **la cifra de 19,99 M€ delante**. Esa cifra se
> trató como negocio perdido cuando en una beta son **datos de prueba** perdidos. Después el paso
> se ejecutó porque estaba en el plan, sin volver a contrastarlo contra la decisión que lo
> desautorizaba. **Un plan validado no exime de volver a preguntarse para qué sirve cada paso**, y
> una cifra grande es justo lo que anestesia esa pregunta.

**Medición que se conserva porque sí es útil saberla** *(consulta de sólo lectura a la fuente real,
2026-08-19)*: de los 45 expedientes, **sólo 2 siguen en la ventana de 100 de la fuente catalana**.
Los otros 43 **no volverán** ejecutando el pipeline: envejecieron fuera de la ventana. Es la
confirmación empírica de la causa raíz de H-48 — y la razón por la que la reparación del Paso 2
importaba y ésta no: **lo que había que arreglar era dejar de perderlas, no recuperar las perdidas.**

**Qué pasa entonces con el Funnel**: se llena solo. Desde el Paso 2 cada corrida conserva lo que
captura, y con datos frescos, que para diseñar el Bloque 3 valen más que estos.

**Si algún día hiciera falta** —por ejemplo antes de la demo, para enseñar un Funnel poblado—, este
apartado documenta exactamente qué había que hacer: deshacer `deleted_at`, `deleted_reason` y el
`estado_operativo` que el defecto pisó, **sin estampar `rescatado_at`** *(ver el aviso de abajo)*, y
con previsualización previa.

> ⚠️ **El hallazgo de implementarlo, que se conserva porque vale para cualquier reparación futura.**
> La primera versión de este apartado decía "reutilícese `Depurador.rescatar()`". **Era un error, y
> sólo se vio escribiendo el código que debía obedecerlo** —segunda vez en el proyecto, después del
> Paso 6 de la Capa 10—. `rescatar()` estampa `rescatado_at`, y las consultas del motor de archivado
> llevan `AND l.rescatado_at IS NULL` (`depurador.py:358, 377, 390`): esa marca **exime del
> archivado automático para siempre**. Existe para el rescate *comercial*, cuando una persona decide
> conservar a la vista algo ya caducado. Usarla para reparar un defecto habría dejado 45
> licitaciones **inmortales en el Funnel**, sin archivarse nunca al vencer su plazo de verdad:
> cambiar una mentira por otra.

## G · Plan de ejecución en 5 pasos

| Paso | Qué hace | Verificación |
|---|---|---|
| **1** | Este contrato, validado por dirección | — |
| **2** | 🟢 **Hecho el 2026-08-19.** H-48: la rama `Nueva` consulta la fecha límite; eventos y resumen | **487/487** (23 regresiones nuevas en `tests/test_h48_ausencia_feed.py`). Medido sobre copia de la base real: el código viejo habría archivado **los 15 lotes vivos** dejando el Funnel a cero; el nuevo archiva **2**, los de plazo vencido. |
| **3** | ❌ **Descartado por dirección el 2026-08-19.** Ver apartado F | Implementado y retirado; `depurador.py` intacto |
| **4** | 🟢 **Hecho el 2026-08-19.** H-49: `resolver_id_canonico()` por código de publicación. La normalización de espacios que este contrato proponía **no servía** —0 duplicados detectados sobre los 63 reales— y se descartó midiéndola | 14 regresiones en `tests/test_h49_id_duplicado.py`, una de ellas para que nadie reintente la vía descartada |
| **5** | 🟢 **Hecho el 2026-08-19.** Corrida real id 7 (46,47 s) y documentos al día | `Revisados 62 \| expirados 2 \| **conservados con plazo abierto 13**`. Suite **501/501** |

**Riesgo principal y su mitigación**: los Pasos 2 y 4 tocan capas cerradas. La mitigación es que
**ninguna prueba existente cambia de expectativa** —comprobado: las que citan `soft_delete_obsoletos()`
en `test_capa9_e2e.py` y `test_capa9_eliminacion.py` siembran el estado directamente y no la
invocan; la única que la invoca de verdad, `test_el_radar_deja_constancia_del_estado_que_pisa`,
ejercita la rama de anulación, que no se toca—. Si alguna regresión existente cambiara de
resultado, es señal de que el alcance se ha desbordado y hay que parar.

---

## H · Qué se esperaba ver, y qué se vio

| Se esperaba | Resultado real (corrida 7, 2026-08-19) |
|---|---|
| Que la fuente catalana deje de archivarse entera | ✅ **13 licitaciones conservadas** con plazo abierto que antes se habrían archivado |
| Las dos licitaciones de 82 puntos visibles | ❌ **No**, y es consecuencia de descartar el Paso 3: siguen archivadas por decisión |
| Más de 4 de 15 expedientes con pliego leído | 🟡 **Aún no**: el Funnel tiene 18 vivos y el efecto se acumula corrida a corrida, no de golpe |
| El Bloque 3 diseñándose contra un Funnel que dice la verdad | ✅ Lo que hay en pantalla ya es lo que hay de verdad |

**Lo que queda para quien siga**: el Funnel se llenará solo. Cada corrida conserva lo que captura,
así que el material realista para diseñar el Bloque 3 llega con los días, no con una reparación.
