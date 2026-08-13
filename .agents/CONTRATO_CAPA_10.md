# Contrato de Servicio — Capa 10: El Lanzador y Despertador

**Versión:** 1.0.0 · **Estado:** 🟢 **validado por dirección el 2026-08-13.**

Corresponde al **Paso 1** de la Capa 10 (Reglas 1 y 2). Rige todo lo que venga después: léelo antes
de tocar `src/lanzador.py`.

---

## Propósito

Convertir un ecosistema que hoy exige tres comandos y una terminal en algo que se usa con un doble
clic y se ejecuta solo cada mañana. **La capa no añade inteligencia de negocio: añade que la
inteligencia que ya existe llegue a usarse.**

Su competencia es el *arranque, la supervisión y el apagado* de procesos que ya existen. No lee
pliegos, no puntúa, no purga y no decide nada de negocio. Cuando esta capa toma una decisión, es
siempre sobre **si algo debe ejecutarse**, jamás sobre qué debe concluir.

---

## Principio rector: silencioso no es mudo

Es la tensión central de la capa y la que genera todos sus defectos posibles. Se ocultan las
consolas porque nadie quiere ver una terminal, y **ocultar la consola es exactamente cómo se pierde
un aviso**. Es la Convención C2 aplicada al sistema operativo: un fallo que no se distingue de un
éxito no es un fallo gestionado, es un fallo escondido.

De ahí el corolario que gobierna toda la capa:

> **El canal de un aviso no lo elige la gravedad del fallo, sino hasta dónde llegó el arranque.**

Un mismo error —pongamos, la política de retención ilegible— se comunica de forma distinta según el
momento: si ocurre antes de que FastAPI sirva el Cockpit, no existe la pantalla donde avisar y hace
falta un diálogo nativo del sistema; si ocurre después, la pantalla ya existe y un diálogo sería
redundante y molesto. Ningún canal sobra, y ninguno debe usarse donde haría daño.

### El punto ciego, y por qué su solución es la causa del siguiente fallo

Si el healthcheck falla —falta una dependencia, el `.yaml` está corrupto, el puerto lo ocupa otra
aplicación—, FastAPI **nunca llega a levantarse**, así que *no existe la pantalla donde avisar*. El
usuario haría doble clic y no pasaría absolutamente nada: la sensación de que el botón está roto.

Pero un diálogo nativo es, a su vez, **la forma de colgar el despertador**. Una tarea programada con
*"ejecutar tanto si el usuario ha iniciado sesión como si no"* corre en la **Session 0**, un entorno
sin escritorio interactivo: un cuadro de diálogo allí espera para siempre a un usuario que no existe
y deja un proceso zombi cada noche.

**La solución de un problema es la causa del otro**, así que ninguna de las dos puede diseñarse sin
la otra. Las concilia la invariante central de este contrato (sección D).

---

## Máquina de estados (Regla 2)

### A. Ciclo de vida del lanzador

```
                      healthcheck OK           servidor responde a /health
   DETENIDO ──▶ COMPROBANDO ──────────▶ ARRANCANDO ──────────────────────▶ OPERATIVO
      ▲              │                      │                                  │
      │              │                      │                                  │ (fin de trabajo
      │              ▼                      ▼                                  ▼   o cierre)
      │          DEGRADADO ◀────────────────┴──────────────────────────  DETENIENDO
      │              │                                                         │
      └──────────────┴─────────────────────────────────────────────────────────┘
                   (siempre con código de salida ≠ 0)      (sólo apaga lo que él encendió)
```

| Estado | Significado | Cómo se sale |
|---|---|---|
| `DETENIDO` | Nada en marcha. Estado inicial y final. | Invocación (doble clic o tarea programada). |
| `COMPROBANDO` | Ejecutando el healthcheck de arranque en frío. **Todavía no se ha tocado nada.** | A `ARRANCANDO` si es satisfactorio; a `DEGRADADO` si no. |
| `ARRANCANDO` | Levantando o reutilizando la API, esperando a que `/health` conteste. | A `OPERATIVO` cuando contesta; a `DEGRADADO` si vence el tope. |
| `OPERATIVO` | La API responde. Aquí se abre el Cockpit y/o se ejecuta el pipeline. | A `DETENIENDO` al terminar el trabajo del modo. |
| `DETENIENDO` | Apagado ordenado en tres niveles, verificando cada uno. | A `DETENIDO` con código 0; a `DEGRADADO` si queda algo vivo. |
| `DEGRADADO` | Salida honesta desde cualquier estado. **No es un estado de reposo: es una terminación.** | Siempre a `DETENIDO`, **siempre con código ≠ 0** y con evento en JSONL. |

**`DEGRADADO` no significa "el sistema funciona a medias".** Significa *"esta invocación no pudo
completar lo que prometía y lo está diciendo"*. Es el estado que impide que esta capa convierta el
ecosistema en una caja negra silenciosa.

### B. Los tres modos de invocación

Cada modo es un contrato distinto sobre qué estados recorre y qué le está permitido hacer:

| Modo | Recorrido | Servidor | Pipeline | Navegador | Quién lo invoca |
|---|---|---|---|---|---|
| **completo** | Todos | Arranca o reutiliza | Sí | **Sí** | `Incoop.vbs` (doble clic) |
| **sólo pipeline** | Todos menos apertura | **No arranca servidor** | Sí | **Nunca** | Tarea programada (madrugada) |
| **sólo Cockpit** | Todos | Arranca o reutiliza | **No** | **Sí** | Acceso directo secundario |

**El modo *sólo pipeline* no levanta la API.** Prospectar no la necesita —`run.py` habla con SQLite
directamente—, y levantar un servidor que nadie va a consultar sólo añade un puerto que vigilar y un
proceso que apagar en un entorno sin escritorio. Es también el modo que corre en Session 0, de modo
que **no ejecuta una sola llamada gráfica**, ni de error ni de apertura.

### C. Transiciones prohibidas

Son la parte sustantiva de este contrato. Cada una impide un daño concreto:

1. **`COMPROBANDO → ARRANCANDO` sin healthcheck satisfactorio.** Arrancar sobre un entorno que no
   cumple es cambiar un diagnóstico preciso por un fallo confuso diez segundos después.
2. **Ejecutar el pipeline con el cerrojo tomado y vivo.** Desde la Capa 9 el pipeline **borra
   ficheros del disco**: dos corridas simultáneas no son un desperdicio, son dos procesos
   destruyendo peso documental a la vez. Ante un cerrojo vivo la respuesta correcta es no arrancar
   y decirlo.
3. **Forzar o borrar un cerrojo huérfano por cuenta propia.** Existe `db_lock()`, que sabe
   reclamarlo por PID y TTL. Un lanzador que fuerce cerrojos anula la protección que la Capa 9
   necesita. *(Ver H-37: hoy esa reclamación no siempre llega a actuar.)*
4. **Apagar un proceso que el lanzador no encendió.** Si encuentra una API que ya estaba corriendo
   —alguien la lanzó a mano para desarrollar—, la usa pero **no la mata al terminar**.
5. **Terminar en `DEGRADADO` con código de salida `0`.** Un lanzador que siempre devuelve `0` deja
   ciego al Programador de tareas que lo invoca, y esa es la única señal que verá quien revise por
   qué una noche no se prospectó.
6. **Cualquier llamada a interfaz gráfica sin pasar por `es_sesion_interactiva()`.** Es la
   invariante central; se detalla abajo.

### D. La invariante central: ninguna llamada gráfica sin comprobar la sesión

**Toda llamada a interfaz gráfica —sin excepción— pasa por `es_sesion_interactiva()`.** Aplica
tanto al diálogo nativo de error como a la apertura del navegador, que son las dos únicas que esta
capa realiza.

Y esa función **decide consultando el identificador de sesión del proceso**, nunca el modo de
invocación. La distinción es el corazón del asunto:

| Fuente de la decisión | Qué es | Por qué no sirve / sí sirve |
|---|---|---|
| El modo de invocación (`--modo pipeline`) | Una **intención declarada** | ❌ Puede llegar equivocada por un defecto, por un acceso directo mal cableado o porque alguien registró la tarea a mano con el modo que no era. Una intención no es un hecho. |
| El identificador de sesión del proceso | Un **hecho del sistema operativo** | ✅ La Session 0 lo es con independencia de lo que el invocador creyera estar pidiendo. |

**Por qué se declara como invariante y no como buena práctica**: es lo único de esta capa que puede
auditarse recorriendo el código con una lista en la mano, que es exactamente cómo el Paso 10 de la
Capa 9 encontró sus tres huecos. Si hay una sola llamada gráfica que no pase por ahí, la tarea
nocturna dejará un proceso colgado; y el síntoma —un proceso que no acaba nunca— sólo aparece de
madrugada, en un entorno sin nadie mirando.

**La prueba que cierra la capa no es que la tarea programada se registre**, sino que una corrida sin
escritorio **termina sola y no deja proceso vivo**.

### E. La identidad de un proceso no es su número

El fichero `data/lanzador.pid` guarda **el PID y el instante de creación del proceso**, no el PID a
secas.

Windows recicla los identificadores. Con el número solo, *"apago sólo lo mío"* puede acabar matando
algo inocente que heredó el número, y la reclamación de cerrojos huérfanos puede ver *"el PID sigue
vivo"* sobre un proceso que ya murió, respetar un cerrojo muerto y dejar a la corrida siguiente
esperando a que venza el TTL. Es la familia de H-15 vista desde el lanzador, y el fallo real de un
cierre brusco: **no es corrupción de datos, es un plantón de diez minutos.**

> **Nota de alcance**: el mismo endurecimiento le falta hoy a `db_lock()`, cuyo `created_at` es la
> fecha del cerrojo y no la del proceso propietario. **Queda declarado aquí y no se repara en esta
> capa**: tocar el cerrojo de la Capa 9 desde la 10 sin un defecto reproducible que lo exija sería
> justo lo que la Regla 14 prohíbe. Si el Paso 5 produce evidencia de que causa daño real, se abre
> como hallazgo con su propia reparación.

---

## Contrato de las operaciones (Regla 1)

### Operación 1 — Comprobar (healthcheck de arranque en frío)

| | |
|---|---|
| **Entradas** | `config/lanzador.yaml`; el entorno de la máquina. |
| **Salidas** | Objeto de diagnóstico con el resultado de cada comprobación y, si falla, **qué falta y cómo resolverlo**. |
| **Precondiciones** | Ninguna. Es lo primero que ocurre, y debe poder ejecutarse en una máquina recién clonada. |
| **Postcondiciones** | No ha modificado nada. **Es una operación de sólo lectura sobre el sistema.** |
| **Side-effects** | Evento JSONL. Diálogo nativo **si y sólo si** falla y hay sesión interactiva. |
| **Errores** | `ConfiguracionLanzadorInvalida`, `HealthcheckInsatisfactorio`, `PuertoOcupadoPorTercero` |

Comprueba: intérprete y versión de Python, dependencias importables, ficheros de configuración
legibles, base accesible y migrable, espacio libre en disco y existencia de `frontend/dist/`.

**Distingue tres estados del puerto**, que es donde se equivocan estos lanzadores:

| Estado del puerto | Cómo se determina | Respuesta |
|---|---|---|
| Libre | Nadie escucha | Arrancar servidor propio |
| Ocupado por **nuestra** API viva | Responde a `/api/v1/health` con la forma esperada | **Reutilizar**, y no apagarla al terminar |
| Ocupado por **otra cosa** | Escucha pero no es nuestro `/health` | **Detenerse.** Ni pelearse por el puerto ni elegir otro en silencio |

**Reutilizar es más seguro que arrancar**: un lanzador que arranca a ciegas acaba dejando instancias
duplicadas que se pisan en la misma base.

### Operación 2 — Servir (arrancar, esperar y reutilizar)

| | |
|---|---|
| **Entradas** | Puerto, host y tope de espera, de `config/lanzador.yaml`. |
| **Salidas** | Estado `OPERATIVO` y, si arrancó servidor propio, `data/lanzador.pid`. |
| **Precondiciones** | Healthcheck satisfactorio. **Sin él no se arranca nada** (transición prohibida nº 1). |
| **Postcondiciones** | `/api/v1/health` responde, **comprobado**, no supuesto. |
| **Side-effects** | Proceso `uvicorn` en grupo propio; fichero PID con PID + instante de creación. |
| **Errores** | `ServidorNoRespondio` |

**Se espera consultando `/health` hasta que conteste**, con un tope declarado en configuración,
nunca durmiendo un tiempo fijo. El error clásico de estos lanzadores es `sleep 5` y abrir el
navegador: en un equipo lento la pantalla sale en blanco y parece que el sistema no funciona. Si no
contesta dentro del tope, **se informa en vez de abrir un navegador sobre nada**.

### Operación 3 — Prospectar (ejecutar el pipeline respetando el cerrojo)

| | |
|---|---|
| **Entradas** | Modo de invocación. |
| **Salidas** | Código de salida del pipeline, traducido al mapa de esta capa. |
| **Precondiciones** | **El cerrojo no está tomado por un proceso vivo.** Se comprueba antes de lanzar. |
| **Postcondiciones** | El pipeline terminó, o no se lanzó y consta por qué. |
| **Side-effects** | Los del pipeline (escribe en BD, descarga, **archiva y purga ficheros**). |
| **Errores** | `CerrojoTomadoPorProcesoVivo` |

**El lanzador traduce códigos de salida; no modifica el pipeline** *(decisión de dirección,
2026-08-13)*. Hoy `src/main.py` devuelve `1` para todo fallo, de modo que *"no prospecté porque
había un cerrojo vivo"* y *"reventé"* son indistinguibles para el Programador de tareas. La capa lo
resuelve **envolviendo**: comprueba el cerrojo antes de invocar y emite su propio código, dejando la
Capa 9 intacta. Cambiar los códigos de `main.py` sería modificar una capa cerrada y validada desde
otra, que es lo que la Regla 14 prohíbe.

**Si el cerrojo está huérfano, no lo borra**: deja que lo reclame la lógica que ya existe y sabe
hacerlo bien (transición prohibida nº 3).

**Matar el proceso a mitad tiene consecuencias asimétricas**, y el lanzador debe saberlo: el
archivado y la eliminación son transaccionales y revierten solos; la purga documental borra ficheros
**antes** de tocar la base, de modo que una interrupción deja el fichero fuera y la fila sin marcar.
Es la dirección recuperable a propósito —la corrida siguiente lo termina—, pero **el lanzador no
debe reintentar a ciegas ni suponer que un proceso muerto no hizo nada**.

### Operación 4 — Detener (apagado ordenado en tres niveles)

| | |
|---|---|
| **Entradas** | `data/lanzador.pid`. |
| **Salidas** | Confirmación de que el proceso desapareció, y del estado del cerrojo. |
| **Precondiciones** | **El proceso a apagar es el que este lanzador encendió**, verificado por PID **e instante de creación**. |
| **Postcondiciones** | Proceso terminado y fichero PID retirado. |
| **Side-effects** | Evento JSONL indicando **en qué nivel** se consiguió. |
| **Errores** | `ApagadoIncompleto` |

**Se verifica en cada nivel** — nunca se envía la señal y se da por hecho que funcionó: se sondea
hasta que el proceso desaparece o vence el plazo.

| Nivel | Mecanismo | Qué garantiza |
|---|---|---|
| 1 | `POST /api/v1/admin/apagar` | El único que termina las peticiones en curso, devuelve el cerrojo y ejecuta el `lifespan`. Y **el único que funciona sin consola**, que es justo el caso del `.vbs`. |
| 2 | `CTRL_BREAK_EVENT` al grupo | Cierre por señal. `CTRL_C_EVENT` **no** sirve: queda deshabilitado en un grupo creado con `CREATE_NEW_PROCESS_GROUP`, y enviarlo sin aislar el grupo nos mataría también a nosotros. |
| 3 | `TerminateProcess` | Último recurso, sólo agotado el tiempo de gracia. |

**El endpoint de apagado escucha sólo en `127.0.0.1` y exige el testigo** que el lanzador guardó en
su fichero PID. Sin él, cualquier página abierta en el navegador podría apagar el servidor.

**Se comprueba el cerrojo después de apagar**, no se supone liberado. Si quedó huérfano se registra:
la reclamación por PID y TTL es la red que lo recoge, y conviene saber cuándo actúa.

> **Lo que se mide en el Paso 5 y no se da por supuesto**: que uvicorn atienda `SIGBREAK` en Windows
> con la limpieza que promete.

---

## Errores tipados

| Error | Cuándo | Código de salida |
|---|---|---|
| `ConfiguracionLanzadorInvalida` | `config/lanzador.yaml` ausente, ilegible o incoherente | `11` |
| `HealthcheckInsatisfactorio` | Falta una dependencia crítica del entorno | `10` |
| `PuertoOcupadoPorTercero` | El puerto responde, pero no es nuestra API | `20` |
| `ServidorNoRespondio` | `/health` no contestó dentro del tope declarado | `21` |
| `CerrojoTomadoPorProcesoVivo` | Otra corrida está en marcha | `30` |
| `ApagadoIncompleto` | Agotados los tres niveles, el proceso sigue vivo | `40` |

---

## Códigos de salida (Regla 7 y Consideración 11)

**El código de salida es información, no un formalismo.** El Programador de tareas registra si la
tarea terminó bien o mal, y esa es la única señal que verá quien revise por qué una noche no se
prospectó.

| Código | Significado | ¿Es un fallo? |
|---|---|---|
| `0` | Completado según el modo invocado | No |
| `10` | Healthcheck insatisfactorio | Sí |
| `11` | Configuración ausente o incoherente | Sí |
| `20` | Puerto ocupado por un proceso ajeno | Sí |
| `21` | La API no respondió dentro del tope | Sí |
| `30` | **Pipeline omitido: cerrojo tomado y vivo** | **No, pero tampoco es éxito** |
| `31` | El pipeline terminó con error | Sí |
| `40` | Apagado incompleto: quedó proceso vivo | Sí |
| `1` | Error no previsto | Sí |

**Por qué `30` merece código propio y no `0`.** Omitir la prospección porque ya hay una corrida en
marcha es la conducta correcta, no una avería: el sistema está protegiendo la integridad de un
proceso destructivo. Pero devolver `0` haría que el Programador registrase una noche sana en la que
**no se prospectó nada**, y esa mentira sólo se descubre cuando alguien echa en falta las
oportunidades de tres semanas. Ni éxito ni avería: **omisión deliberada, y consta.**

**Por qué `1` queda reservado al error no previsto.** Todo lo que el contrato anticipa tiene su
número. Si aparece un `1`, es que ocurrió algo que este documento no contempló, y eso es
información valiosa por sí misma.

---

## Modo Degradado (Regla 5)

| Situación | Comportamiento | Por qué |
|---|---|---|
| **Pipeline falla, API sana** (modo completo) | **El Cockpit se abre igual**, con el distintivo del Paso 9 avisando de que la última corrida falló | *(Decisión de dirección, 2026-08-13.)* Negarle a alguien sus datos de ayer porque la prospección de hoy falló convierte un fallo parcial en una avería total. |
| **Chrome/Edge no encontrados** | Caída a `webbrowser.open()` | **Degradar la apariencia es aceptable; no abrir nada, no.** |
| **Cerrojo tomado y vivo** | No se lanza el pipeline; `LANZADOR_PIPELINE_OMITIDO` y código `30` | Es la protección funcionando. |
| **Sin sesión interactiva y fallo fatal** | **Jamás un diálogo.** Código de salida y registro | Un diálogo en Session 0 cuelga el proceso para siempre. |
| **Configuración ausente o incoherente** | **No se arranca con valores por defecto.** Se detiene y lo dice | Misma doctrina que `src/retencion.py`. Así fue como H-18 cambió decisiones comerciales en silencio. |

---

## Eventos JSONL (Regla 3)

Todos con `updated_by="lanzador"`, en `data/pipeline.jsonl` vía `Memoria.registrar_log_json()`.

| Evento | Cuándo |
|---|---|
| `LANZADOR_INICIADO` | Al invocar, con el modo y la versión de configuración |
| `LANZADOR_HEALTHCHECK_FALLIDO` | Comprobación insatisfactoria, con la causa |
| `LANZADOR_PUERTO_REUTILIZADO` | Se encontró nuestra API viva y se usó |
| `LANZADOR_PUERTO_OCUPADO_AJENO` | El puerto lo ocupa algo que no es nuestro |
| `LANZADOR_SERVIDOR_ARRANCADO` | Servidor propio en marcha y respondiendo, con el tiempo que tardó |
| `LANZADOR_SERVIDOR_NO_RESPONDE` | Venció el tope de espera |
| `LANZADOR_PIPELINE_OMITIDO` | Cerrojo tomado y vivo, con la causa |
| `LANZADOR_PIPELINE_FALLIDO` | El pipeline devolvió error |
| `LANZADOR_APAGADO` | Apagado conseguido, **indicando en qué nivel** |
| `LANZADOR_APAGADO_INCOMPLETO` | Agotados los tres niveles |
| `LANZADOR_CERROJO_HUERFANO_TRAS_APAGADO` | El cerrojo no quedó liberado |
| `LANZADOR_GUI_OMITIDA` | **Se suprimió una llamada gráfica por no haber sesión interactiva** |
| `LANZADOR_DEGRADADO` | Terminación en `DEGRADADO`, con causa y código |

**`LANZADOR_GUI_OMITIDA` es el evento más importante de la lista**, aunque parezca el más menor: es
el rastro auditable de que la invariante central actuó. Sin él, "no salió ningún diálogo en Session
0" es indistinguible de "no hubo ningún fallo del que avisar".

> **Convención de `run_id`**: `registrar_log_json()` exige un `run_id` entero, pero los eventos del
> lanzador ocurren **antes de que exista una ejecución de pipeline**. Se adopta `run_id=0` como
> valor reservado para "evento del lanzador fuera de una corrida". Cuando el evento sí corresponde a
> una corrida en marcha, se usa su `ejecucion_id` real. *(El valor `9999` ya está tomado por el
> `--dry-run` de `main.py`.)*

---

## Versionado (Regla 4)

**Ningún plazo ni puerto inventado.** Todo parámetro operativo —puerto, host, tope de espera, ruta
del bundle, comportamiento ante puerto ocupado, hora del despertador— vive en `config/lanzador.yaml`
con su campo `version`, y **no hay valores por defecto**: fichero ausente o incoherente significa no
arrancar. Misma doctrina que `config/retencion.yaml`.

El contrato se versiona en la cabecera de este documento. Si un paso posterior descubre que promete
algo que no existe, **se retira del contrato con su motivo** —lección del Paso 10 de la Capa 9: un
contrato que promete lo que no hay es peor que uno más corto.

---

## Cambio de contrato de la Capa 7 que esta capa introduce

Al servir el Cockpit desde FastAPI, **la raíz `/` deja de devolver el JSON de bienvenida y pasa a
servir la aplicación**. El JSON se conserva bajo `/api/v1/`.

Es un cambio visible para cualquier cliente de la API —hoy vive en [`src/api/main.py:132`](../src/api/main.py)—
y por eso **se declara aquí, no se descubre**. Lo implementa el Paso 4.

---

## Defecto detectado al redactar este contrato

### H-37 · `setup_db()` usa un cerrojo propio que no sabe reclamar huérfanos 🔴 ABIERTO

Hay **dos cerrojos distintos sobre el mismo fichero `.lock`**. `db_lock()`
([`src/memoria.py:644`](../src/memoria.py)) tiene TTL de 600 s, verificación de PID y reclamación de
huérfanos — todo el endurecimiento del Paso D1. Pero `setup_db()`
([`src/memoria.py:759`](../src/memoria.py)) se fabrica el suyo: **cinco intentos de un segundo y un
`RuntimeError`**, sin TTL, sin comprobar PID y sin reclamar nada.

Y `setup_db()` es **lo primero que hace `main()`** ([`src/main.py:89`](../src/main.py)).

**Por qué es la Capa 10 quien lo activa**: el apagado de nivel 3 es `TerminateProcess`. Si mata al
proceso dentro de la ventana del cerrojo, deja un `.lock` huérfano. A las 3 de la madrugada el
despertador arranca, `setup_db()` lo encuentra, espera cinco segundos, lanza `RuntimeError` y el
pipeline sale con código `1` **sin consola donde verlo**. La protección del Paso D1 existe y no
llega a actuar, porque quien pregunta primero es el cerrojo que no sabe reclamar.

**No es un defecto que esta capa introduzca: es uno que esta capa activa.**

**Reparación: dentro del Paso 2** *(decisión de dirección, 2026-08-13)*, donde vive el healthcheck
de arranque en frío — que es literalmente el sitio donde se comprueba que la base es accesible y
migrable.

---

## Criterios de aceptación del Paso 1

1. ✅ La máquina de estados declara sus seis estados, sus transiciones y su salida honesta.
2. ✅ Las seis transiciones prohibidas están enunciadas con el daño concreto que impiden.
3. ✅ La invariante central —ninguna llamada gráfica sin `es_sesion_interactiva()`— queda declarada
   de forma auditable, con el motivo de decidir por identificador de sesión y no por modo de
   invocación.
4. ✅ Los tres modos de invocación tienen contrato propio, y el del despertador declara que **no
   ejecuta una sola llamada gráfica**.
5. ✅ Existe un mapa de códigos de salida que distingue **omisión deliberada** de **avería**, con
   `1` reservado a lo no previsto.
6. ✅ El cambio de contrato de la Capa 7 se declara por adelantado.
7. ✅ El defecto detectado al redactar (H-37) queda catalogado con su evidencia y su paso de
   reparación.
