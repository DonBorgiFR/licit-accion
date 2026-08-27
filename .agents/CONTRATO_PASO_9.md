# Contrato de Servicio — Capa 10, Paso 9: La Voz del Proceso Silencioso

**Versión:** 1.2.0 · **Redactado:** 2026-08-27 · **Estado:** 🟢 **validado por dirección el 2026-08-27**,
corregido el mismo día al abrir los bloques 9.C y 9.D.

> **Qué cambia en la v1.2.0 y por qué** *(2026-08-27, al escribir el bloque 9.D)*. Dos cosas,
> las dos nacidas de escribir el código que debía obedecer al documento:
>
> 1. **Estado nuevo `DESCONOCIDA`** en la máquina de la sección E.1. La tabla agotaba `RUNNING`,
>    `COMPLETED` y `FAILED`, y un valor inesperado no tenía dónde caer. Las dos salidas fáciles
>    eran malas: `FALLIDA` afirma una avería que no consta, `COMPLETADA` afirma lo contrario.
> 2. **El diagnóstico lee el rastro junto a la base que acaba de consultar**, no en
>    `ruta_datos()`. En producción son el mismo sitio, pero pueden divergir si `DB_PATH_INCOOP`
>    apunta a otro lado — y entonces se juzgaría una base con el rastro de otra. Es la familia de
>    H-28: resolver una ruta contra el sitio equivocado. **Lo destapó una prueba del endpoint**,
>    que falló por esto y no por lo que pretendía comprobar.

> **Qué cambia en la v1.1.0 y por qué** *(2026-08-27, al abrir el bloque 9.C)*. Una sola cosa, y
> nace de medir el código que debía obedecer al documento — no de releerlo:
>
> **`run_id` deja de ser obligatorio y `null` pasa a ser un valor legítimo**, con el significado
> *«el escritor no sabe a qué corrida pertenece»*. **No es lo mismo que `0`**, que significa
> *«evento del lanzador fuera de una corrida»*.
>
> **El motivo, medido**: `src/centinela.py` **no tiene ninguna noción de `run_id`** —cero
> apariciones en todo el módulo—, así que sus 105 eventos de la gramática D no pueden declarar
> una corrida. Las dos alternativas eran peores: **escribir `0`** sería afirmar que un evento
> ocurrido dentro de la corrida 16 estaba fuera de ella, es decir mentir con un dato estructurado;
> y **atravesar la Capa 6 para enhebrar el `run_id`** sería reformar una capa cerrada para
> conseguir lo que la ventana temporal del lector ya resuelve — que es, además, exactamente como
> se atribuyó a mano el evento que acotó H-41.
>
> Es la Convención C6 otra vez: lo que no se pudo medir no se rellena con un valor que parezca
> bueno. **Se retira la promesa del documento con su motivo**, tal como manda su sección J.

Corresponde al **Paso 9** de la Capa 10 (Reglas 1, 2 y 8). Se subordina al
[`CONTRATO_CAPA_10.md`](CONTRATO_CAPA_10.md) v1.3.0, que sigue rigiendo: este documento **no
corrige ni una línea de aquél**, lo desarrolla en el único punto que dejó abierto —el tercero de
sus cuatro canales— y en los defectos que la propia capa se asignó, H-39 y H-45/H-46.

> **Por qué existe este contrato y no basta con el de la capa.** El contrato de la Capa 10 declara
> `pipeline.jsonl` como el canal que sirve *«siempre, para el diagnóstico: reconstruir después qué
> ocurrió»*. Ese canal **no cumple hoy lo que se promete de él**, y arreglarlo obliga a decidir qué
> forma tiene un evento — una decisión de diseño que atraviesa cinco capas ya cerradas. Eso no cabe
> en una nota al pie.

---

## Propósito

Que un sistema que se ejecuta solo, de madrugada y sin consola **pueda contar lo que le pasó**. La
capa entera se construyó sobre una tensión declarada en su contrato —*silencioso no es mudo*— y
este paso es el que la resuelve del lado del que escucha.

**Qué NO es este paso:**

* **No añade notificaciones.** Sigue vigente la decisión del 2026-08-12: *«la Capa 10 arranca, no
  avisa»*. El canal por el que el sistema habla es el Cockpit, que ya existe.
* **No reabre el motor.** No toca scoring, perfil comercial, LCSP ni el ciclo de vida del dato.
* **No reescribe el rastro histórico.** Ver la sección D.

---

## A · Decisiones de dirección, tomadas el 2026-08-27

Las tres se plantearon con sus alternativas antes de redactar una línea de este documento.

| # | Asunto | Decisión |
|---|---|---|
| **D1** | Alcance | **H-45 y H-46 entran en el Paso 9.** Son el mismo defecto que el paso combate —el sistema sabe cosas que no cuenta— y el README ya los tenía apuntados aquí sin asignar |
| **D2** | Hasta dónde llega H-39 | **Lector canónico + unificación de los escritores.** El lector sigue entendiendo las cuatro gramáticas antiguas para no perder rastro ya escrito. **Autoriza expresamente tocar código de las Capas 3, 4, 5, 6 y 7, cerradas** (Regla 14) |
| **D3** | Qué dice el distintivo | **Estado + motivo leído del rastro.** El estado sale de la tabla `ejecuciones`; el motivo, de `pipeline.jsonl` a través del lector canónico, servido por un endpoint nuevo |

**Descartado de entrada, y consta**: reescribir el fichero histórico a un solo esquema. Destruiría
rastro, y H-55 avisa de que hay líneas que **no son líneas**: reescribir obligaría a decidir qué
hacer con ellas, y cualquier decisión ahí es pérdida de evidencia.

---

## B · El terreno, medido el 2026-08-27

Todo lo que sigue está medido sobre `data/pipeline.jsonl` real, **4.768 líneas, de las que 4.754
son legibles**, no deducido del código. Todas las cifras son **posteriores a la corrida 16** del
2026-08-27 y suman entre sí; ver la advertencia al final de esta sección.

### B.1 · H-39 está catalogado por debajo: no son dos gramáticas, son cuatro

| Gramática | Líneas | Punto de escritura |
|---|---|---|
| **A** — `action` / `run_id` / `updated_by` | 2.306 | [`memoria.py:1983`](../src/memoria.py), [`lanzador.py:1598`](../src/lanzador.py), [`lector.py:153`](../src/lector.py) *(caída sin BD)* |
| **B** — `tipo_evento` / `modulo` / `estado` / `payload` | 1.965 | [`api/dependencies.py:89`](../src/api/dependencies.py) (1.938), [`centinela.py:1159`](../src/centinela.py) (27) |
| **C** — `event` / claves sueltas | 378 | [`analista.py:1080`](../src/analista.py) |
| **D** — `componente` / `evento` / `detalles` | 105 | [`centinela.py:312`](../src/centinela.py) |
| *(ilegibles)* | 14 | — |
| **Total** | **4.768** | |

**El Centinela escribe él solo en dos gramáticas distintas**, y ninguno de los **siete** puntos
de escritura sabe de la existencia de los otros seis.

> 🔑 **La prueba de que el daño no es teórico ya ocurrió.** El evento que localizó la muerte del
> pipeline en H-41 —`boletin_fetch_started`— pertenece a la gramática **D**, la de 105 líneas de
> 4.768. Un lector que sólo hablara `action` —la mayoritaria— habría descartado en silencio justo
> la línea que resolvió aquella investigación, y habría presentado un relato incompleto como si
> fuera completo. Es lo que el dosier de H-39 anticipó, cumplido antes de repararlo.

### B.2 · Dos formatos de fecha, y ningún estado en el 59 % del fichero

| Hecho medido | Cifra |
|---|---|
| Líneas con `...Z`, sin microsegundos | 2.789 |
| Líneas con `...+00:00`, con microsegundos | 1.965 |
| Líneas **sin ningún campo de estado** (gramáticas A, C y D) | **2.789 de 4.754 legibles** |
| Valores de `estado` existentes (sólo gramática B) | `INFO` 1.871 · `ERROR` 63 · `WARNING` 31 |
| **Eventos cuyo único indicio de fallo es su propio nombre** | **8 nombres distintos, 67 líneas** |
| Nombres de evento distintos en todo el fichero | 84 |

> ⚠️ **Cómo se corrigió esta sección, porque la lección vale más que las cifras.** La primera
> redacción de este contrato mezclaba dos mediciones: las gramáticas contadas **antes** de que
> terminara la corrida 16 (fichero de 4.591 líneas) y el total contado **después** (4.768). El
> cuadro parecía correcto y no sumaba. Lo destapó el bloque 9.B al ejecutar el lector contra el
> fichero real, no releyendo el documento. **De ahí sale la comprobación de conservación** que
> `tools/verificar_rastro_real.py` hace ahora la primera: *totales = traducidas + ilegibles*. Un
> recuento que no suma es lo único que delata dos mediciones fundidas, y es exactamente la deriva
> que `ESTADO.md` describe como motivo de haber separado reglas y estado.

> 🔑 **Aquí está por qué H-39 es la precondición de H-45, y no su vecino.** Para que el Cockpit diga
> *«no pude mirar»* en vez de *«no hay alertas»*, hoy tendría que **olfatear la subcadena `degraded`
> dentro del nombre del evento**. Eso es exactamente lo que prohíbe la **Convención C3**: *el modo
> degradado se afirma con datos, nunca con heurísticas de texto*. **No existe el valor `DEGRADADO`
> en ninguna parte del vocabulario actual.** Sin esquema canónico, la honestidad de la pantalla sólo
> se puede construir incumpliendo una convención.

### B.3 · H-55 sigue rompiendo, y su mecanismo no cuadra con lo medido

De **11 líneas partidas** catalogadas el 2026-08-25 se ha pasado a **14**: 44, 1699, 1711, 2708,
2807, 2809, 3196, 3274, 3276, 4070, 4073, 4468, **4579 y 4586**. Las dos últimas son del
**2026-08-26**, posteriores al catálogo: **el fichero no se rompió una vez, se sigue rompiendo.**

Y el mecanismo que el dosier propone —*OneDrive reconciliando un fichero de sólo-añadir entre dos
equipos*— **no explica lo medido**:

* **Las 14 son fragmentos de escrituras de la API**, sin una sola excepción.
* Cada una está en el **mismo segundo y la misma máquina** que su línea vecina completa.
* La línea 4073 **empieza correctamente y se corta a media clave** (`{"timestamp": "…", "modu`).
  Eso es un escritor interrumpido, no dos copias de un fichero fundidas.
* Y hay un candidato con nombre: [`api/middleware.py:43`](../src/api/middleware.py) escribe en el
  rastro **desde el pool de hilos, en cada petición HTTP**.

**Este contrato no cierra H-55 ni afirma su causa.** Lo que declara es la consecuencia operativa,
que es más fuerte que la del dosier: *cualquier lector de `pipeline.jsonl` tiene que tolerar líneas
rotas, y no como deuda histórica sino como condición permanente*. La corrección del mecanismo se
anota en el Paso 10 o en una medición propia, según decida dirección.

### B.4 · H-45 está vivo hoy, y la pantalla lo pinta en verde

| Hecho medido el 2026-08-27 | Cifra |
|---|---|
| Descargas de boletín degradadas / intentadas | **26 de 27** |
| Filas en `boletines_alertas` | **0** |
| Último fallo del DOGC | **hoy, 07:29:06** — `HTTP 404` tras 3 reintentos |
| Último fallo del BOPB | `HTTP 500` en `https://bop.diba.cat/rss` |

> ⚠️ **La evidencia nueva, y es la que mejor justifica el paso entero.** La corrida **id 16** de
> esta mañana (05:28:07–05:29:10 UTC) consta **`COMPLETED` con `errores = 0`**, y **dentro de ella
> el Centinela no pudo consultar ninguna de sus dos fuentes oficiales**. Con el código de hoy,
> `ProspeccionIndicator` pinta sobre esa corrida un distintivo **verde: «Datos al día»**.
>
> **Es H-45 y el distintivo de fallo vistos como lo que son: un solo defecto en dos pantallas.** El
> canal Centinela dice *«no hay alertas»* y la cabecera dice *«al día»*, y las dos afirmaciones son
> falsas por el mismo motivo: nadie transporta la degradación hasta donde se mira.

### B.5 · H-46 sigue exactamente igual

[`AdminPanel.tsx:97`](../frontend/src/components/AdminPanel.tsx) envía `confirmar: true` de un solo
clic para la purga documental, mientras su vecina de la misma pantalla —la eliminación de
expedientes— exige previsualizar. **La previsualización documental ya la sirve la API** en
`GET /api/v1/admin/purga/previsualizacion`. La mitad honesta existe y la pantalla no la usa.

---

## C · El esquema canónico de evento (Regla 4)

**Versión del esquema: `1`.** Superconjunto de las cuatro gramáticas; no pierde ningún campo.

```json
{
  "esquema": 1,
  "timestamp": "2026-08-27T05:29:06Z",
  "run_id": 16,
  "componente": "centinela",
  "evento": "boletin_fetch_degraded",
  "estado": "DEGRADADO",
  "datos": { "fuente": "DOGC", "error": "HTTP 404 tras 3 reintentos" }
}
```

| Campo | Obligatorio | Qué unifica | Regla |
|---|---|---|---|
| `esquema` | sí | *nuevo* | Entero. **Es lo que hace el fichero autodescriptivo**: sin él, distinguir una línea canónica de una histórica vuelve a ser adivinar |
| `timestamp` | sí | los dos formatos actuales | **Un solo formato**: ISO-8601 UTC con `Z` y sin microsegundos |
| `run_id` | **no** *(v1.1.0)* | `run_id` | Entero o `null`. **`0` = evento fuera de una corrida**, convención ya adoptada por el lanzador; **`null` = el escritor no lo sabe**, que es el caso del Centinela entero. `9999` sigue reservado al `--dry-run`. Los tres son distintos y ninguno se sustituye por otro |
| `componente` | sí | `updated_by` · `modulo` · `componente` | Vocabulario cerrado: `radar`, `lector`, `analista`, `centinela`, `depurador`, `memoria`, `api`, `lanzador` |
| `evento` | sí | `action` · `tipo_evento` · `event` · `evento` | El nombre se conserva **tal cual está hoy**: renombrarlos rompería cualquier búsqueda sobre el histórico |
| `estado` | **sí, explícito** | `estado` (sólo existía en B) | `INFO` · `WARNING` · `ERROR` · `DEGRADADO` · `DESCONOCIDO` |
| `datos` | sí (puede ir vacío) | `payload` · `detalles` · claves sueltas de C · `expediente_id`/`reason`/`duration_ms` de A | Objeto. Nunca claves sueltas en la raíz |

**`estado` no tiene valor por defecto.** Es argumento obligatorio en el escritor: un punto de
llamada que se lo dejara olvidado estaría **declarando éxito por descuido**, que es la familia de la
Convención C2. Cuesta explicitarlo en los sitios de llamada y esa es justamente la intención.

**`DEGRADADO` es el valor que hoy no existe** y sin el cual H-45 no se puede reparar sin incumplir
C3. **`DESCONOCIDO` no es sinónimo de `INFO`**, exactamente por el motivo de la Convención C6: lo
que no se pudo medir no puntúa en ninguna dirección.

---

## D · Qué se hace con las 4.768 líneas ya escritas

**No se reescriben.** El lector las traduce al vuelo con esta tabla, que es una **traducción
declarada, no una inferencia**:

| Gramática | → `componente` | → `evento` | → `datos` |
|---|---|---|---|
| **A** | `updated_by` | `action` | `{expediente_id, reason, duration_ms}` presentes |
| **B** | `modulo` | `tipo_evento` | `payload` |
| **C** | `"analista"` | `event` | todas las claves salvo `timestamp` y `event` |
| **D** | `componente` | `evento` | `detalles` |

Para el campo `estado`, que **no existe en 2.803 líneas**, rige lo siguiente:

1. Gramática **B**: se conserva su `estado` real.
2. Gramáticas **A, C y D**: se resuelve contra un **catálogo declarado de nombres de evento**,
   cerrado y versionado, que vive en este contrato y en el código que lo implementa.
3. **Todo nombre que no esté en el catálogo se traduce a `DESCONOCIDO`.** No se deriva, no se
   supone y no se mira dentro de la cadena.

**El catálogo histórico completo — 8 nombres, 67 líneas:**

| Nombre de evento | → `estado` |
|---|---|
| `boletin_fetch_degraded` | `DEGRADADO` |
| `doc_ocr_degraded` | `DEGRADADO` |
| `LANZADOR_DEGRADADO` | `DEGRADADO` |
| `doc_download_failed` | `ERROR` |
| `API_KPIS_FAILED` | `ERROR` |
| `API_LICITACIONES_LIST_FAILED` | `ERROR` |
| `LANZADOR_APAGADO_INCOMPLETO` | `ERROR` |
| `LANZADOR_CERROJO_EJECUCION_HUERFANO` | `WARNING` |

> 🔑 **Por qué un catálogo no incumple la Convención C3, y una heurística sí.** C3 prohíbe afirmar
> el modo degradado *«inspeccionando cadenas de texto libre»*. Un nombre de evento **no es texto
> libre**: es un vocabulario cerrado de 84 valores que emite nuestro propio código, y el catálogo
> compara **nombres completos contra una lista declarada**, no subcadenas. La diferencia práctica es
> que `buscar("degrad")` clasificaría mañana un evento que nadie ha revisado, y el catálogo **dirá
> `DESCONOCIDO`** — que es admitir que no lo sabe. **El catálogo no crece después de la
> unificación**: a partir de ahí el estado lo declara quien escribe.

---

## E · Máquina de estados (Regla 2)

### E.1 · El diagnóstico de la última prospección

Es el estado que el sistema afirma sobre sí mismo, y lo que gobierna el canal 3 del contrato de la
capa. **Ninguno se decide mirando una sola fuente**: el estado sale de `ejecuciones`, el motivo del
rastro.

| Estado | Cómo se determina | Qué se cuenta |
|---|---|---|
| `SIN_PROSPECCIONES` | 0 filas en `ejecuciones` | Que todavía no consta ninguna |
| `EN_CURSO` | `RUNNING` + dueño vivo | Que hay trabajo en marcha |
| `INTERRUMPIDA_POR_TOPE` | `RUNNING` + dueño muerto + `LANZADOR_PIPELINE_AGOTADO` de esa corrida | **Que se cortó por agotar su tope**, no que reventó |
| `INTERRUMPIDA` | `RUNNING` + dueño muerto, sin ese evento | Que murió, y **el último evento que llegó a escribir** |
| `SIN_CERRAR` | `RUNNING` + dueño desconocido (`null`) | Que no se puede afirmar si vive. Fila anterior al esquema v8 |
| `FALLIDA` | `FAILED` | Que falló, con su motivo |
| `COMPLETADA_CON_DEGRADACION` | `COMPLETED` + ≥1 evento `DEGRADADO` en la corrida | **Que terminó, y qué no pudo hacer** |
| `COMPLETADA` | `COMPLETED` + 0 eventos `DEGRADADO` | Que está al día |
| `DESCONOCIDA` *(v1.2.0)* | La fila dice cualquier otra cosa | **Que no se sabe interpretar el estado** |

> **`DESCONOCIDA` se añade en el bloque 9.D**, al escribir la máquina de estados. La tabla
> original agotaba `RUNNING`, `COMPLETED` y `FAILED`, que es lo que `finalizar_ejecucion()`
> escribe hoy — pero un valor inesperado tenía que ir a alguna parte, y las dos salidas fáciles
> eran malas: mandarlo a `FALLIDA` **afirma una avería** sobre algo que no se entiende, y
> mandarlo a `COMPLETADA` afirma lo contrario. La Convención C6 lo prohíbe en las dos
> direcciones. El `ProspeccionIndicator` ya tenía de hecho una rama para este caso desde el Paso
> 7; lo que faltaba era nombrarla.

> **`COMPLETADA_CON_DEGRADACION` es el estado que este paso añade, y es el que faltaba.** Es
> literalmente el estado de la corrida 16 de hoy, que el sistema pinta como `COMPLETADA`. Los cinco
> primeros ya los distingue el `ProspeccionIndicator` desde el Paso 7; el que no existía es el que
> separa *«terminó»* de *«terminó pudiendo hacerlo todo»*.

### E.2 · Transiciones prohibidas

Cada una corresponde a un daño concreto, medido o ya ocurrido.

1. **Pintar `COMPLETADA` sobre una corrida con eventos `DEGRADADO`.** Es lo que ocurre hoy con la
   corrida 16. Un verde sobre una corrida ciega es peor que un dato ausente: induce a decidir.
2. **Descartar una línea ilegible sin contarla.** Es H-39 en su forma peor —*«presenta un relato
   incompleto como si fuera completo»*—, y con 14 líneas rotas vivas no es hipotético.
3. **Derivar `estado` inspeccionando subcadenas del nombre del evento.** Convención C3.
4. **Que el endpoint de diagnóstico falle porque el rastro está roto.** El canal de diagnóstico no
   puede tumbar aquello que diagnostica: degrada y lo declara.
5. **Un canal vacío que no distinga «no hay» de «no pude mirar».** H-45, en cualquier pantalla.
6. **Una operación destructiva sin previsualización previa.** H-46, y el criterio ya fijado el
   2026-08-07: *la purga se ejecuta en dos tiempos y nunca a ciegas*.

---

## F · Contrato de las operaciones (Regla 1)

### Operación 1 — Leer el rastro

| | |
|---|---|
| **Dónde** | `src/rastro.py` *(módulo nuevo)* |
| **Entrada** | Ruta *(por defecto `ruta_datos("pipeline.jsonl")`)*, y filtros opcionales `run_id`, `desde`, `hasta`, `tope` |
| **Salida** | `ResultadoRastro`: `eventos`, `lineas_totales`, `lineas_ilegibles`, `numeros_ilegibles`, `gramaticas`, `existe`, `degradado` |
| **Precondiciones** | **Ninguna.** El fichero puede no existir |
| **Postcondiciones** | **No escribe nada y no crea ningún directorio.** Función de lectura pura |
| **Errores** | Fichero ausente → resultado vacío con `existe=False`, **sin excepción**. Ilegible por permisos → `RastroIlegible` |

> **Por qué la lectura no puede tener efectos**, y es la lección del Paso 2 de esta misma capa:
> `ejecutar_healthcheck()` se dejó deliberadamente fuera del registro porque *escribir el registro
> crea el directorio de datos*. Un lector de diagnóstico que modificara lo que examina es la misma
> trampa.

**La invariante del lector**: *ninguna línea desaparece en silencio.* Una línea que no parsea suma
en `lineas_ilegibles`, su número queda anotado, y `degradado` pasa a `True`. **El lector declara su
propia degradación con un campo estructurado**, igual que exige C3 a todo lo demás.

### Operación 2 — Escribir un evento canónico

| | |
|---|---|
| **Dónde** | `src/rastro.py`, y los **siete** puntos de escritura actuales delegan en él |
| **Entrada** | `componente`, `evento`, `estado` *(obligatorio)*, `datos`, `run_id` |
| **Postcondiciones** | Una línea, un idioma, un formato de fecha, con `"esquema": 1` |
| **Errores** | Un fallo de escritura **avisa por `stderr` y no tumba al llamador**, como ya hace `registrar_evento_lanzador()`: que falle la auditoría no puede detener el trabajo, pero tampoco puede pasar desapercibido |

**Los SIETE puntos que se migran** *(corregido de seis en la v1.1.0)*, todos a la misma función:

| Módulo | Punto | Capa |
|---|---|---|
| `memoria.py:1983` | `registrar_log_json()` | 3 |
| `lector.py:153` | `registrar_log_JSONL()` *(y su caída sin BD)* | 4 |
| `analista.py:1080` | `registrar_log_jsonl()` | 5 |
| `centinela.py:312` | `log_evento_jsonl()` | 6 |
| `centinela.py:1159` | `GestorTrazabilidadCentinela` | 6 |
| `api/dependencies.py:89` | `GestorTrazabilidadAPI` | 7 |
| **`lanzador.py:1598`** | **`registrar_evento_lanzador()`** | **10** |

> ⚠️ **Eran siete y este documento contó seis, y el que faltaba era el peor de todos.** La
> sección B.1 sí lo listaba —el lanzador aparece bajo la gramática A junto a `memoria` y
> `lector`—, pero la tabla de migración lo perdió por el camino. Dejarlo fuera habría producido
> el resultado más absurdo posible: **la capa que declara `pipeline.jsonl` canal de diagnóstico,
> hablando ella sola un idioma que su propio lector tendría que seguir traduciendo.** Se detectó
> al ir a declarar los estados de los puntos de llamada, no releyendo el contrato — igual que las
> cifras de la sección B.

**Las firmas públicas no cambian.** Cada función conserva sus parámetros actuales y traduce por
dentro. Es lo que permite migrar y revertir **un escritor cada vez** sin dejar el rastro a medio
idioma, y lo que acota el riesgo de tocar cinco capas cerradas (Regla 14).

> 📏 **La cobertura real de `estado` tras el 9.C, medida y sin disimular.** La corrida 17 del
> 2026-08-27 escribió **650 líneas, las 650 canónicas**, y de ellas **sólo 13 declaran su estado**
> — las dos degradaciones del Centinela y once eventos informativos. **Las otras 637 dicen
> `DESCONOCIDO`.**
>
> **Eso es correcto y a la vez mejorable, y conviene no confundir las dos cosas.** Es correcto
> porque `DESCONOCIDO` significa *«el punto de llamada no lo ha declarado»*, que es la verdad; lo
> incorrecto habría sido darles `INFO` por defecto, que es declarar éxito por descuido. Y es
> mejorable porque **el riesgo residual del paso vive justo ahí**: un evento de fallo que se
> añada mañana sin declarar su estado será invisible para la pantalla, y el catálogo no lo
> cubrirá porque el catálogo sólo mira hacia atrás.
>
> **La cifra a batir es 13/650**, y se sube declarando `estado` en los puntos de llamada, no
> tocando el lector.

### Operación 3 — Servir el diagnóstico

| | |
|---|---|
| **Dónde** | `GET /api/v1/admin/prospeccion/diagnostico` *(endpoint nuevo — se añade, no se modifica ninguno)* |
| **Salida** | El estado de E.1, su motivo, el último evento con su hora, y las degradaciones de esa corrida |
| **Fuentes** | `ejecuciones` para el estado y el dueño; el lector de la Operación 1 para el motivo |
| **Modo degradado** | Si el rastro es ilegible, **responde igual** con el estado que da `ejecuciones` y `rastro_degradado: true`. Nunca 5xx por un log roto *(transición prohibida nº 4)* |

### Operación 4 — Contarlo donde se mira

Tres pantallas, un solo criterio: **un canal vacío tiene que decir por qué lo está.**

| Pantalla | Qué cambia | Cierra |
|---|---|---|
| `ProspeccionIndicator.tsx` | Gana `COMPLETADA_CON_DEGRADACION` y el motivo en los estados de fallo | El canal 3 del contrato de la capa |
| Canal Centinela | Distingue *«no hay alertas»* de *«la última consulta falló»*, con la fuente y el error | **H-45** *(cara pantalla)* |
| `AdminPanel.tsx` | La purga documental pasa a dos tiempos, con la previsualización que la API ya sirve | **H-46** |

Y fuera del código, `config/centinela_config.yaml` sube de versión con las direcciones vigentes de
los feeds — **H-45 cara configuración**. Localizarlas exige salir a la red y **se pedirá permiso
expresamente** cuando llegue el bloque 9.E.

---

## G · Errores tipados

| Error | Cuándo | Efecto |
|---|---|---|
| `RastroIlegible` | El fichero existe pero no se puede abrir | Lo captura quien llama; el endpoint degrada y lo declara |
| `EventoInvalido` | Falta un campo obligatorio, o `estado` no está en el vocabulario | **Al escribir.** Se rechaza en vez de escribir una línea a medias |
| `ComponenteDesconocido` | `componente` fuera del vocabulario cerrado | Igual: se rechaza |

**Ninguno de los tres detiene el pipeline.** Un fallo de auditoría no puede costar una prospección.

---

## H · Modo Degradado (Regla 5)

| Situación | Comportamiento | Por qué |
|---|---|---|
| **Líneas rotas en el rastro** | Se cuentan, se anotan sus números y el resultado se marca `degradado` | H-55 dice que las hay y que siguen apareciendo. Saltarlas calladamente es la transición prohibida nº 2 |
| **Rastro ausente** | Resultado vacío, `existe=False`, sin excepción | Un sistema recién instalado no tiene rastro, y eso no es una avería |
| **Rastro ilegible** | El endpoint responde con lo que sí sabe y declara `rastro_degradado` | Transición prohibida nº 4 |
| **Evento histórico sin estado catalogado** | `DESCONOCIDO` | Convención C6: lo que no se pudo medir no puntúa |
| **Fallo al escribir un evento** | Aviso por `stderr`, el llamador continúa | Ya es la conducta de `registrar_evento_lanzador()` |

---

## I · Eventos JSONL (Regla 3)

Este paso **no añade eventos nuevos al vocabulario del lanzador**: los 16 del contrato de la capa
siguen siendo los suyos. Lo que añade es que **todos los eventos del sistema, de todas las capas,
pasen a ser legibles por un programa**. La trazabilidad propia de este paso son dos eventos:

| Evento | Componente | Cuándo |
|---|---|---|
| `RASTRO_LEIDO_DEGRADADO` | `api` | Se sirvió un diagnóstico sobre un rastro con líneas ilegibles, con cuántas |
| `RASTRO_EVENTO_RECHAZADO` | el que intentó escribir | Se rechazó un evento inválido, con el motivo |

---

## J · Versionado (Regla 4)

| Qué | Dónde | Valor |
|---|---|---|
| Esquema de evento | `src/rastro.py` **y estampado en cada línea** (`"esquema": 1`) | `1` |
| Catálogo histórico de estados | Sección D de este contrato y el código que lo implementa | Cerrado, 8 nombres |
| Configuración del Centinela | `config/centinela_config.yaml` | sube a **v1.1.0** en el bloque 9.E |
| Este contrato | Su cabecera | v1.0.0 |

**Si un bloque descubre que este documento promete algo que no existe, se retira del contrato con su
motivo** — lección del Paso 10 de la Capa 9, y las tres veces que en el Bloque 3 un contrato
validado resultó estar equivocado al escribir el código que debía obedecerlo.

---

## K · Los seis bloques, y por qué en ese orden

| | Bloque | Verificación que lo cierra |
|---|---|---|
| **9.A** | **Este contrato** | Validación de dirección. **No se codifica antes** (Reglas 8 y 9) |
| **9.B** | **El lector canónico** (`src/rastro.py`) | Contra el fichero **real**: debe reproducir las cifras de la sección B —4 gramáticas, 14 líneas rotas, 84 nombres— y encontrar el `boletin_fetch_started` de la corrida 16 |
| **9.C** | **Unificación de los siete escritores** | Suite entera + una corrida real: líneas nuevas en un solo idioma, y el lector sigue leyendo las 4.768 viejas |
| **9.D** | **El diagnóstico llega a la pantalla** | C7: mirar el Cockpit sobre una corrida degradada de verdad |
| **9.E** | **Las dos bocas mudas** (H-45 y H-46) | C7: el canal Centinela debe delatar sus 26 fallos, y la purga no debe poder lanzarse sin previsualizar |
| **9.F** | **Cierre** | Suite completa en verde y README / ESTADO / AUDITORÍA al día |

**El orden no es preferencia.** **B antes que C**: si los escritores cambian antes de que exista un
lector que entienda lo antiguo, el rastro queda medio migrado e ilegible justo mientras se trabaja
sobre él. **C antes que D**: el motivo que la pantalla enseña sale del `estado` estructurado que C
introduce; sin él, D sólo podría construirse violando C3. **E al final**: reutiliza el lector de B y
el patrón de distintivo de D — puesto antes, se construye dos veces.

---

## L · Lo que este contrato NO promete

* **No cierra H-55.** Tolera sus consecuencias y corrige su diagnóstico; no repara la causa.
* **No cierra H-41.** Hace más fácil investigarlo —el rastro pasa a ser legible por un programa—,
  que es distinto de resolverlo.
* **No afirma que el distintivo sepa diagnosticar el pasado más allá del catálogo de 8 nombres.**
  Sobre lo histórico no catalogado dirá `DESCONOCIDO`, y eso es una respuesta, no un fallo.
* **No añade notificaciones ni saca el sistema del Cockpit.**

---

## M · Detectado al redactar este contrato

Ninguno es un hallazgo nuevo: los tres primeros **corrigen fichas existentes**, que es lo que
corresponde cuando la evidencia contradice al dosier en vez de añadirle un caso.

1. **H-39 estaba catalogado por debajo.** Su ficha dice *«dos esquemas»*; son **cuatro**, y el
   Centinela escribe en dos de ellos. Se corrige en 9.F.
2. **H-55 tiene un mecanismo que no cuadra con la evidencia**, y **ha crecido de 11 a 14 líneas, dos
   de ellas posteriores a su catalogación**. Se corrige en 9.F.
3. **H-45 tiene una cara que su ficha no recoge**: además del canal Centinela vacío, el distintivo
   de cabecera pinta **verde** sobre una corrida degradada. Medido hoy sobre la corrida 16.
4. **Deriva documental menor**: el README anuncia `tools/programar_despertador.py` 💤 y el Paso 8
   entregó `tools/registrar_despertador.py`. Se corrige en 9.F.

---

## N · Criterios de aceptación del Paso 9

1. Existe un **esquema canónico de evento versionado**, con `estado` obligatorio y explícito, y con
   el valor `DEGRADADO` que hoy no existe en ninguna parte del vocabulario.
2. Existe **un lector** que entiende las cuatro gramáticas históricas y **cuenta** las líneas
   ilegibles en vez de saltarlas, declarando su propia degradación con un campo estructurado.
3. **Los siete puntos de escritura emiten el mismo idioma**, sin cambiar sus firmas públicas.
4. El **traslado del estado histórico se hace por catálogo declarado**, no por inspección de
   subcadenas, y lo no catalogado dice `DESCONOCIDO`.
5. El Cockpit distingue **`COMPLETADA` de `COMPLETADA_CON_DEGRADACION`**, y en los estados de fallo
   dice **por qué**.
6. El canal Centinela distingue *«no hay alertas»* de *«no pude mirar»*, y las direcciones de los
   feeds están vigentes y versionadas.
7. La purga documental **no se puede lanzar sin haber previsualizado**.
8. La suite pasa entera —**línea de partida: 623/623 el 2026-08-27**— y la verificación C7 se hace
   contra la base real, mirando la pantalla.
