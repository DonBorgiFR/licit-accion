# Plan del bloque 10.B.3 — El cerrojo del rastro (H-55, y la propuesta de meter H-60 dentro)

> **Estado**: 🟢 **VALIDADO POR DIRECCIÓN el 2026-09-01**, con sus cuatro decisiones de la
> sección 5 y con **H-60 dentro del bloque** *(sección 9)*. El contrato queda en **v1.3.0**.
>
> **Rige por encima de este plan**: [`CONTRATO_PASO_10.md`](CONTRATO_PASO_10.md) **v1.3.0**,
> **Operaciones 5 y 7**. Si algo de aquí lo contradice, manda el contrato.
>
> **Evidencia**: [`AUDITORIA_2026-07-27.md`](AUDITORIA_2026-07-27.md), hallazgos **H-55**
> *(con la ampliación medida el 2026-09-01)* y **H-60**.

---

## 1. Qué es esto, en una frase

Que `data/pipeline.jsonl` **deje de perder eventos** cuando varios hilos escriben a la vez — que
es siempre que alguien tiene el Cockpit abierto.

## 2. Por qué el bloque ya no es el que estaba escrito

El contrato lo describe como *«18 líneas rotas de 6.354, y creciendo»*: un fichero con agujeros
visibles. **Medido el 2026-09-01, el enunciado se queda corto y en la dirección peor.**

Ejercitando `registrar_evento()` contra un fichero temporal, con una barrera para que los hilos
arranquen a la vez:

| Escenario | Eventos emitidos | Líneas en el fichero | Partidas | **Perdidos** | |
|---|---|---|---|---|---|
| **1 hilo** *(control)* | 960 | 960 | 0 | **0** | el escritor, solo, es correcto |
| 16 hilos, vuelta 1 | 960 | 914 | 0 | **46** | 4,8 % |
| 16 hilos, vuelta 2 | 960 | 909 | 2 | **53** | 5,5 % |
| 16 hilos, vuelta 3 | 960 | 906 | 2 | **56** | 5,8 % |
| 4 hilos | 240 | 237 | 0 | **3** | 1,2 % |

Los perdidos se cuentan **por identidad**, no por resta: cada evento lleva su `(hilo, nº)` y se
comprueba cuáles no aparecen.

> 🔑 **Las líneas partidas son la parte visible del defecto, y es la pequeña.** Una línea rota se
> ve leyendo el fichero; **un evento que nunca llegó a escribirse no deja hueco**. Por eso dos
> diagnósticos anteriores midieron el 0,26 % visible y no lo demás: no había nada que mirar. Es
> la forma que este dosier lleva catalogando desde H-21 —*no rompen, callan*— aplicada al fichero
> con el que se investiga todo lo demás.

**Y esto toca la Regla 3.** `src/rastro.py` se abre declarando *«ninguna línea desaparece en
silencio»*: es cierto para lo que llega al fichero y falso para lo que no llega. Un rastro que
pierde eventos bajo carga no es un registro determinista. **La reparación sigue siendo barata; ya
no es cosmética.**

## 3. Que la carrera es entre hilos y no entre procesos: ahora está medido

El contrato lo dedujo de que *todos los fragmentos son escrituras de la API*. Se le puede añadir
una comprobación independiente, hecha cruzando cada línea rota del fichero real con la tabla
`ejecuciones`:

| | |
|---|---|
| Líneas rotas con vecinos de componente `api` a ambos lados | **19 de 19** |
| Líneas rotas producidas **sin ninguna corrida activa** | **16 de 19** |

En esas 16 **no había un segundo proceso escribiendo**: el pipeline no estaba en marcha. La única
concurrencia posible era la de los hilos de la API. **El diagnóstico del contrato se sostiene, y
con él el tamaño de la reparación** — un cerrojo de módulo, no un cerrojo de fichero del sistema
operativo.

## 4. Lo que este bloque NO hace

* **No repara las 19 líneas ya rotas.** Borrarlas sería destruir rastro *(ya decidido en la
  Operación 5)*.
* **No recupera los eventos perdidos.** No hay forma de saber cuáles fueron: por eso el defecto
  no se veía.
* **No promete nada entre procesos.** El alcance declarado es intra-proceso, y la sección 5.4
  dice cómo se comprobará si esa apuesta era correcta.
* **No apaga el aviso ámbar del Cockpit.** Eso es H-60, y es la sección 9.

## 5. Lo que falta decidir, con recomendación

### 5.1 · Dónde vive el cerrojo — **recomendación: un `threading.Lock` de módulo en `src/rastro.py`**

Y basta con uno, porque el Paso 9 dejó el terreno preparado: **los siete escritores del proyecto
delegan ya en `registrar_evento()`** *(bloque 9.C)*. Comprobado uno a uno — `analista.py`,
`api/dependencies.py`, `centinela.py`, `lanzador.py`, `lector.py`, `memoria.py` y el propio
`rastro.py`. Un cerrojo ahí cubre a **todos** los hilos del proceso sin tocar a ninguno de ellos.

**El cerrojo va alrededor del `open`+`write`+`close`, no de la función entera**, y eso no es
detalle de estilo: `registrar_evento()` valida el evento **antes** de escribir y lanza
`EventoInvalido`, que `registrar_evento_tolerante()` captura para **volver a llamar** al escritor
con un evento de rechazo. Si el cerrojo abarcase la validación, esa segunda llamada intentaría
tomar un cerrojo que su propia pila ya tiene y **el proceso se quedaría clavado**. Ciñéndolo a la
escritura, la validación ocurre fuera y no hay reentrada posible.

### 5.2 · La rotación del fichero — **recomendación: que tome el mismo cerrojo**

`rotar_log_si_excede_tamano()` *(`src/api/dependencies.py:44-70`)* renombra `pipeline.jsonl` al
llegar a 10 MB, **desde el pool de hilos y justo antes de escribir**. Medido hoy:

```
os.rename() con el fichero abierto por otro hilo
  -> PermissionError: el proceso no tiene acceso al archivo porque está siendo utilizado por otro
```

Y ese error **lo traga un `except Exception` que sólo imprime** *(`dependencies.py:70-71`)*: es
la Convención C2 incumplida dentro de la propia rotación. Consecuencia: con el Cockpit abierto, la
rotación **fallará en silencio** y el fichero seguirá creciendo.

> 📏 **No es urgente pero llegará**: hoy `pipeline.jsonl` va por **2,1 MB** de los 10 que
> disparan la rotación. Se propone resolverlo ahora porque **es el mismo cerrojo y el mismo
> fichero**; volver dentro de tres meses a este sitio costaría el doble.

**Coste**: exportar el contexto desde `src/rastro.py` y usarlo en el gestor de la API. **Dos
ficheros tocados en vez de uno.** *(Esto es lo que obliga a subir el contrato a v1.3.0: la
Operación 5 dice «dónde: `src/rastro.py`».)*

### 5.3 · Qué hacer cuando el cerrojo esté tomado — **recomendación: contarlo, NO escribir un evento**

La sección G del contrato declara un evento `rastro_escritura_contendida` con estado `INFO`.
**Se propone no emitirlo**, por dos razones:

1. **Sería escribir en el rastro un evento sobre el hecho de escribir en el rastro.** Es
   exactamente la autorreferencia que acaba de producir **H-60**, y aquí sale más cara: ocurre
   dentro del único punto de escritura del proyecto.
2. **Bajo contención, el evento se emitiría precisamente cuando más carga hay**, añadiendo
   escrituras al fichero que se está intentando proteger.

**Alternativa propuesta**: un contador de módulo (`escrituras_contendidas`) que la regresión
comprueba y que cualquier herramienta de `tools/` puede leer. Si dirección prefiere conservar el
evento, la forma segura es emitirlo **una sola vez por proceso y fuera del cerrojo**.

### 5.4 · El alcance, y cómo se comprobará que la apuesta era correcta

Se mantuvo **intra-proceso**, con la evidencia de la sección 3, y se dejó escrito el criterio que
lo refutaría:

> **Si tras la reparación el contador de líneas rotas vuelve a subir, la carrera también es entre
> procesos** y hace falta un cerrojo de fichero del sistema operativo (`msvcrt.locking`). La
> medición está disponible: `python tools/verificar_rastro_real.py`.

> 🚨 **SALTÓ, en la primera corrida real** *(corrida 24, 2026-09-01)*. Dos roturas nuevas —líneas
> 9595 y 10346— con la firma contraria a las 19 históricas: un evento del pipeline encajado entre
> dos del servidor. Medido a continuación en banco aislado, **con el cerrojo de módulo puesto**:
> dos procesos de cuatro hilos pierden entre el **1,3 % y el 5,5 %** de los eventos, sin una sola
> línea rota.
>
> **Se añadió el cerrojo de fichero** *(contrato v1.4.0)*: `pipeline.jsonl.lock`, byte 0, con
> `msvcrt.locking` en Windows y `fcntl.flock` fuera. Resultado: **2, 3 y 5 procesos → 0 perdidos y
> 0 roturas**, y **0,556 ms por evento** frente a los 0,59 que ya costaba el cerrojo de módulo
> solo: el cerrojo de fichero **no añade coste medible**.
>
> 📌 **Esta sección es el mayor rendimiento del plan.** La apuesta intra-proceso estaba bien
> razonada, apoyada en evidencia real, y estaba mal. Lo que la corrigió en horas fue haber escrito
> **antes de codificar** qué medición la refutaría.

## 6. Las pruebas, y una trampa medida que hay que esquivar

### 6.1 · La trampa: una regresión que sólo mire la parseabilidad daría verde sobre el defecto entero

Con el defecto vivo, el banco de 16 hilos deja **906 líneas de 960 y todas parsean**. El contrato
pide *«N hilos → N líneas parseables»*: **hay que contar N**, no comprobar que lo que haya parsee.

### 6.2 · Las regresiones que se proponen

| | Qué afirma | Por qué |
|---|---|---|
| **R1** | N hilos × M eventos dejan **exactamente N×M líneas** | El recuento es lo que caza la pérdida |
| **R2** | **Cada evento aparece una vez**, identificado por su payload | Un recuento correcto con un duplicado y una pérdida también sumaría bien |
| **R3** | Las N×M líneas parsean, y `lineas_ilegibles` da **0** | Lo que el contrato pide literalmente |
| **R4** | Un solo hilo sigue funcionando igual | El control; y protege de arreglar la concurrencia rompiendo el caso normal |
| **R5** | Rotar bajo carga no pierde el fichero ni eventos | Antes fallaba en silencio |
| **R6** | **Dos procesos de verdad** no pierden ni parten eventos | Lo añadió la corrida 24 al refutar el alcance. Usa `subprocess`: simularlo con hilos daría un verde que no significa nada |

**Todas offline y en directorio temporal** *(Convenciones C5)*. **Ninguna necesita red, base de
datos ni cuota.**

### 6.3 · Validación por mutación, no por reversión

Es doctrina del proyecto, y aquí sale gratis: **el código actual ya es el mutante**. Las
regresiones se escriben **primero** y se las ve caer contra el código de hoy —con el número de
pérdidas que se espera, no con un error cualquiera— y sólo después se añade el cerrojo.

> ⚠️ **Riesgo declarado: una prueba de concurrencia intermitente es peor que no tenerla.** El
> banco de 16 hilos × 60 eventos perdió eventos **en las tres vueltas** y en las dos mediciones
> posteriores, así que la caída del mutante es fiable. Lo que hay que vigilar es lo contrario:
> que la versión reparada pase **siempre**. Medido con el cerrojo puesto: **0 perdidos, 0 rotas**.
> Si apareciera un solo falso rojo, la prueba se recorta a un banco más pequeño antes de aceptarla
> en la suite.

## 7. Lo que cuesta en rendimiento, medido

| | Tiempo | Perdidos | Rotas |
|---|---|---|---|
| 960 eventos, 16 hilos, **sin cerrojo** | 253 ms | **41** | 1 |
| 960 eventos, 16 hilos, **con cerrojo de módulo** | 570 ms | **0** | 0 |
| 960 eventos, 16 hilos, **con los dos cerrojos** | 533 ms | **0** | 0 |

**+0,33 ms por evento** en el peor caso de contención que se puede construir. La propia API
registra latencias de **10 a 25 ms** por petición HTTP en el rastro real, así que el sobrecoste
queda por debajo del ruido. **Y no bloquea el bucle de eventos**: el middleware ya delega la
escritura a un hilo *(`src/api/middleware.py:39-43`)*, que es justo el motivo de que existiera la
carrera.

## 8. Orden de ejecución

| | Paso | Verificación |
|---|---|---|
| 1 | Escribir R1–R4 y **verlas caer** contra el código actual | Caen por pérdida de eventos, con la cifra esperada |
| 2 | Añadir el cerrojo de módulo en `src/rastro.py` *(5.1)* | R1–R4 en verde |
| 3 | *(Si se acepta 5.2)* Exportar el contexto y usarlo en la rotación | R5 en verde |
| 4 | **Suite completa** | De **742/742** a 742+N, **sin una sola regresión ajena tocada** |
| 5 | Refrescar la base de `tools/verificar_rastro_real.py` | Hoy declara `lineas: 4768, ilegibles: 14`; lo real es **7.344 y 19** |
| 6 | **Corrida real** con el Cockpit abierto y mirándolo | El contador de rotas **no sube**: sigue en 19 |
| 7 | **Arrancar la aplicación contra la base real** *(C7)* | Cockpit sin errores de consola |
| 8 | Anotar en `ESTADO.md` y cerrar H-55 en la auditoría | Con la prueba de regresión que lo impide volver |

**El paso 6 es el que de verdad cierra el bloque**, y es el único que no se puede acelerar: hay
que esperar a una prospección de verdad.

## 9. H-60 entra en este bloque *(decidido el 2026-09-01)*

**H-60 no se cierra al reparar H-55.** Las 19 líneas rotas se quedan, `rastro_degradado` seguirá
valiendo `True` para siempre, la API seguirá emitiendo `RASTRO_LEIDO_DEGRADADO` en cada consulta y
**el distintivo del Cockpit seguirá en ámbar todos los días pase lo que pase**.

**A favor de meterlo en este bloque**: es el mismo fichero, el mismo asunto y **una tarde de
trabajo**; y cerrar el 10.B.3 sin él deja el bloque técnicamente correcto y **operativamente
inútil**, porque quien mira la pantalla seguirá viendo el mismo aviso que hoy.

**En contra**: son dos defectos distintos y la Regla 11 pide no mezclar; H-60 tiene **tres
caminos posibles** *(sección «Qué hay que decidir» de su ficha en la auditoría)* y ninguno es
evidente.

> 📌 **Decidido por dirección el 2026-09-01: sí, dentro del 10.B.3, como Operación 7**, con el
> camino **B** de su ficha —que el aviso del rastro **no se escriba en el rastro**: el dato ya
> viaja en la respuesta, en `rastro_lineas_ilegibles`— más el matiz del camino **A**, para que el
> día que la API emita cualquier otra degradación no vuelva a atribuirse a la corrida. Recogido
> en el contrato como **Operación 7**.

## 10. Ficheros que se tocan

| Fichero | Qué cambia | ¿Capa cerrada? |
|---|---|---|
| `src/rastro.py` | El cerrojo de módulo y el contexto exportado | No: es del Paso 9, y este bloque es su continuación |
| `src/api/dependencies.py` *(sólo si 5.2)* | La rotación toma el cerrojo | Toca la Capa 7. **Es el motivo de subir el contrato a v1.3.0** |
| `src/api/routers/admin.py` *(sólo si 9)* | Deja de emitir el evento | Ídem |
| `src/diagnostico.py` *(sólo si 9, matiz A)* | El criterio de qué entra en `degradaciones` | Es del Paso 9 |
| `tests/test_paso10_rastro_concurrente.py` | **Nuevo.** R1–R5 | — |
| `tools/verificar_rastro_real.py` | La base medida, hoy de hace tres semanas | — |

**No se toca**: `src/memoria.py`, `src/lector.py`, `src/centinela.py`, `src/lanzador.py`,
`src/analista.py` ni el frontend. Los cinco primeros ya delegan en el escritor y **no se enteran
del cambio**; el Cockpit pinta lo que se le sirve.

## 11. Riesgos

| | Riesgo | Mitigación |
|---|---|---|
| **R-a** | Una prueba de concurrencia intermitente contamina la suite | Medido: el mutante cae en 5 de 5 vueltas y el reparado sale limpio. Si aparece un falso rojo, se recorta el banco *(6.3)* |
| **R-b** | La carrera también es entre procesos y el cerrojo no basta | Criterio de refutación escrito y medible *(5.4)*. **No se declara cerrado H-55 hasta el paso 6 del orden de ejecución** |
| **R-c** | Serializar las escrituras degrada la API | Medido: +0,33 ms/evento sobre latencias de 10–25 ms *(sección 7)* |
| **R-d** | Tocar `dependencies.py` rompe la Capa 7 | La firma no cambia; sólo se envuelve el `os.rename`. La suite entera es la red |
| **R-e** | El cerrojo se toma dos veces en la misma pila y clava el proceso | Se ciñe a la escritura, dejando fuera la validación que provoca la reentrada *(5.1)* |
