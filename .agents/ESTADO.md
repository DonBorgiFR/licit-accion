# Estado del Proyecto — Ecosistema Automático de Licitaciones

> **Este fichero es el que cambia.** Aquí vive todo lo volátil: dónde estamos, qué toca ahora,
> qué se cerró y qué queda pendiente. Las reglas de trabajo y las convenciones técnicas —que
> apenas cambian— viven en [`AGENTS.md`](AGENTS.md), y los hallazgos con su evidencia en
> [`AUDITORIA_2026-07-27.md`](AUDITORIA_2026-07-27.md).
>
> **Por qué están separados** *(2026-08-13)*: hasta hoy convivían en un solo fichero de 59 KB, y
> esa mezcla producía deriva. En una sola revisión aparecieron tres recuentos distintos de
> hallazgos, un párrafo duplicado y la historia de una capa cerrada colgando del titular de la
> siguiente. No fue mala suerte: lo que nunca cambia y lo que cambia cada paso no pueden
> mantenerse a la vez en la misma página. **Al cerrar un paso se actualiza este fichero, no
> `AGENTS.md`.**

---

## ▶️ Para retomar (sesión del 2026-08-18)

La sesión cerró el **Paso 7 de la Capa 10**, y con él **el sistema pasa a usarse con un doble
clic**. El contrato sube a **v1.2.0**. **La tarea siguiente es el Paso 8**, el despertador — que
arrastra una cuestión abierta de dirección, abajo.

**Lo que ya se puede hacer con el sistema, y antes no:**

* **Abrirlo con un icono del escritorio**, sin consola y sin escribir un comando.
* Verlo en una **ventana de aplicación** —sin barra de direcciones ni pestañas—, con los datos de
  ayer al instante mientras la prospección del día ocurre por debajo.
* **Saber si hay una prospección en marcha** y cuándo ha terminado, mirando la cabecera.
* **Cerrar la ventana y que el equipo quede como estaba**: el servidor se apaga solo, de forma
  ordenada, y sólo si lo encendió esa misma invocación.

**Lo que todavía no**: la tarea programada (Paso 8), el aviso en pantalla de una corrida fallida
(Paso 9) y el cierre con `MANUAL.md` (Paso 10).

> 🔑 **Lo más transferible de la sesión: el Paso 7 empezó descubriendo que faltaba una pieza que
> ningún paso tenía asignada.** Los Pasos 2 a 6 dejaron cinco piezas excelentes —comprobar,
> configurar, servir, prospectar, apagar— y **nadie las recorría**: no existía el orquestador, de
> modo que el `.vbs` del Paso 7 no tenía a qué llamar. No estaba oculto —la tabla de artefactos del
> README decía *"falta el orquestador"*— pero ningún paso lo reclamaba como suyo. **Un plan por
> pasos puede dejar huecos entre los pasos**, y el sitio donde se ven es el primer paso que intenta
> usar el conjunto.

> ⚠️ **Tres defectos encontrados arrancando la aplicación, y ninguno lo habría visto la suite.**
> Es la cuarta vez que ocurre —H-21/22/23 en el Paso D8, H-38 al escribir la configuración, H-40 al
> implementar el cerrojo—, y los tres llevaban latentes desde una capa anterior:
>
> * **H-42 · La API perdía la conexión al cambiar de hilo.** El Cockpit se pintaba a cero con 48
>   expedientes en la base. **Medido: 16 de 40 peticiones concurrentes devolvían 500**; tras
>   repararlo, 80 de 80 correctas. La causa no era SQLite sino FastAPI: `get_db()` es un generador
>   síncrono, así que el framework abre la conexión en un hilo del threadpool y ejecuta el endpoint
>   en otro. Latente desde la Capa 7; salió al añadir un tercer sondeo a la pantalla.
> * **H-43 · Un `RUNNING` no dice si hay alguien prospectando.** El indicador nuevo anunciaba una
>   corrida viva sobre la que murió el día anterior. Se repara publicando el juicio que ya existía
>   —`motivo_ejecucion_huerfana()`, el del cerrojo del Paso 6— en vez de inventar otro.
> * **H-44 · El lanzador informaba de una avería inexistente al cerrar.** Dos dobles clics
>   terminaron con código 40 sobre un servidor que sí había muerto. Preguntaba al sistema por PID
>   teniendo el objeto del hijo; ahora pregunta con `poll()`, que es exacto.

> 🔬 **Y una medición que conviene no perder: el nivel 2 del apagado no existe sin consola.** Bajo
> `pythonw.exe` —el `.vbs`, es decir, **el caso normal**— `CTRL_BREAK_EVENT` falla con WinError 6.
> El Paso 5 lo midió con consola y acertó; lo que no se había medido es el escenario para el que
> existe la capa. La escalera real del doble clic tiene **dos** peldaños: el endpoint y
> `TerminateProcess`. **Medir en el entorno de la prueba no es medir en el de producción.**

> ⚠️ **En qué estado queda la base, para que nadie se asuste al abrirla.**
>
> **63 expedientes**, de los cuales **15 vivos y 48 archivados** *(rectificado el 2026-08-19: la
> nota decía 19 y 44, escritos antes de que la corrida 6 del 18-08 a las 08:49 archivara cuatro
> más)*.
>
> ❌ **Y la explicación que seguía era falsa, conviene no arrastrarla.** Decía que la caída de PBL
> de 20,7 M€ a 5,9 M€ **no era un defecto**, sino el Depurador archivando por plazo vencido. **No
> era eso.** Se archivaron **45 lotes con la fecha límite todavía por llegar**, por valor de
> **19.986.870,63 €**, porque desaparecieron del feed y nadie miró el calendario. Es **H-48**, y
> con él **H-49**: los dos están medidos en el dosier. La cifra de 5,9 M€ es correcta; lo que
> estaba mal era darla por buena.
>
> **La corrida huérfana id 4 ya no existe como tal**: la reclamó su dueño legítimo —
> `iniciar_ejecucion()`— al arrancar la corrida 5, y quedó cerrada como `FAILED`. Es el diseño del
> Paso 6 funcionando sobre datos reales sin que nadie tocara la fila a mano.
>
> 🐛 **H-41 sigue abierto pero se comportó**: la corrida real de esta sesión —154,55 s, 36
> documentos, 5 análisis— terminó `COMPLETED` sin reventar. No demuestra que esté arreglado, porque
> no se ha tocado nada: demuestra que **no es sistemático**.

> 📋 **La Capa 11 existe en el README, y NO es una tarea.** El 2026-08-13 se anotó un apunte de
> alcance sobre el despliegue en servidor —VPS, Docker, `cron` y Basic Auth— para pasar de una
> instalación por PC a un sistema compartido. **No está diseñada ni pautada, y no se abre hasta
> cerrar la Capa 10** (Regla 11). Lo que sí conviene leer antes de tocar nada de la 10 son los
> **cuatro compromisos que esa capa obligaría a revisar** —la seguridad basada en `127.0.0.1`, las
> rutas absolutas de los documentos, el alcance del cerrojo y por qué `es_sesion_interactiva()` ya
> está preparada—, porque afectan a decisiones que se están tomando ahora. **Se añade un quinto
> desde hoy**: el juicio `duenyo_vivo` de H-43 sólo vale preguntado desde la máquina que ejecuta el
> pipeline.

---

## 📍 Dónde estamos

**Estado en una línea**: **Capas 1 a 9 completadas y validadas**, con la suite en **518/518**. **H-48 y H-49 quedaron cerrados el 2026-08-19** —el archivado prematuro y el identificador duplicado—, así que **la tarea activa vuelve a ser el Bloque 3 — Identidad y foco**; la **Capa 10** sigue en pausa tras su Paso 7. El esquema de base de datos vigente es **v8** y la política de retención, **v1.2.0**. De **48 hallazgos catalogados, 44 están cerrados**; quedan abiertos **H-39** (Paso 9 de la Capa 10), **H-41** (crash nativo, sin asignar) y **H-45/46/47** de la revisión del 18-08. **H-48 y H-49 se cerraron el 2026-08-19.** De la **Capa 10** —el Lanzador— quedan cerrados los **Pasos 1 a 7** (1-5 el 2026-08-13, el 6 el 2026-08-17 y el 7 el 2026-08-18) y **espera el Paso 8**; el sistema ya se usa con un doble clic.

**Control de versiones**: el proyecto vive en **https://github.com/DonBorgiFR/licit-accion** desde el 2026-08-06. Antes de esa fecha no había historial: cualquier estado anterior sólo existe en las actas de este directorio.

**Verificación antes de dar nada por bueno:**

```bash
python -m pytest tests/ -q          # debe dar 518/518
```

**Punto de entrada del pipeline**: `python run.py` desde la raíz. **Nunca** `python src/main.py`.

### ✅ Cerrado el 2026-08-19: reparar H-48 y H-49 (referencia, ya no es tarea)

> **Contrato validado**: [`CONTRATO_REPARACION_FEED.md`](CONTRATO_REPARACION_FEED.md) v1.0.0.
> **Léelo antes de tocar `soft_delete_obsoletos()` o el identificador del Radar.**

**De dónde sale.** Preparando el Bloque 3 se midió que de los 15 expedientes vivos sólo 4 tenían el
pliego leído. Dirección preguntó **por qué**, y la respuesta no estaba en el Analista: **las tres
fuentes son ventanas de publicaciones recientes** —la catalana pide las 100 últimas; los ATOM no
siguen paginación— y el sistema leía «salir de la ventana» como «ha expirado». Resultado medido:
**45 lotes archivados con el plazo abierto, 19.986.870,63 € de PBL**, y las dos oportunidades de
82 puntos invisibles mientras el Funnel enseñaba 71 como máximo.

* **Paso 1** 🟢 — contrato, validado por dirección el 2026-08-19.
* **Paso 2** 🟢 — **H-48 reparado el 2026-08-19.** La rama `Nueva` de `soft_delete_obsoletos()`
  consulta la fecha límite; nuevo `clasificar_plazo()` con tres valores —abierto, vencido,
  ilegible— porque *"no se pudo leer"* no es *"venció"*; la función devuelve resumen y emite
  `RADAR_AUSENCIA_IGNORADA_PLAZO_ABIERTO`, `RADAR_AUSENCIA_SIN_FECHA_LIMITE` y
  `RADAR_OBSOLESCENCIA_RESUMEN`. **23 regresiones nuevas** en `tests/test_h48_ausencia_feed.py`.
  Suite **487/487**. **Medido sobre copia de la base real: el código viejo habría archivado los 15
  lotes vivos —Funnel a cero en la corrida siguiente—; el nuevo archiva 2**, los de plazo vencido.
* **Paso 3** ❌ — **descartado por dirección.** El rescate de los 45 lotes archivados se implementó
  con 11 regresiones en verde y **se retiró entero**; `depurador.py` quedó byte a byte como estaba.
* **Paso 4** 🟢 — **H-49 cerrado.** `resolver_id_canonico()` reconoce la licitación por el código
  de publicación que la fuente catalana pone en el enlace, idéntico en las dos grafías. **Sin
  cambiar la clave primaria ni migrar nada**: el dato ya estaba en `link`. 14 regresiones en
  `tests/test_h49_id_duplicado.py`.
* **Paso 5** 🟢 — **corrida real id 7** (46,47 s, sin incidencias). Suite **501/501**.

> 🔑 **Lo más transferible del Paso 2, y va en la línea de lo que este proyecto lleva encontrando:
> el dato que evitaba el defecto ya estaba en la consulta.** `SELECT id, fecha_limite …` lo traía,
> el bucle lo desempaquetaba, y **la rama que decidía no lo miraba** — mientras la rama hermana, la
> de posible anulación, sí. La cautela existía, estaba escrita y funcionaba: se aplicaba a la
> población que no la necesitaba. Medir de qué rama salió cada archivado (48 de 48 de la rama
> `Nueva`, la hermana **nunca disparada**) es lo que permitió reparar el 100 % del daño sin tocar
> el contrato de la Capa 9.

> 🔑 **La lección del Paso 3, y es de método, no de código: un plan validado no exime de volver a
> preguntarse para qué sirve cada paso.** El rescate se escribió en el contrato con el hallazgo
> recién hecho y **la cifra de 19,99 M€ delante**, tratada como negocio perdido cuando en una beta
> son **datos de prueba** perdidos. Contradecía de frente la decisión del 2026-08-17 —*hasta la
> demo los datos son material de prueba*— y aun así se implementó, porque estaba en el plan. Lo
> paró dirección preguntando **para qué**. **Una cifra grande es justo lo que anestesia esa
> pregunta.** Dato que sí quedó: consultada la fuente, sólo **2 de los 45** seguían en su ventana
> de 100 — lo que había que arreglar era dejar de perderlas, no recuperar las perdidas.

> ⚠️ **La trampa que H-49 tendía, y que sólo se vio midiendo.** El contrato mandaba *"colapsar
> espacios repetidos"* en el identificador. Aplicado a las dos grafías reales deja
> `EXPEDIENT 214 2026…`, que **sigue sin coincidir** con `EXPEDIENT214 2026…`: **0 duplicados
> detectados sobre los 63 de la base.** Implementarlo habría cerrado el hallazgo con una
> protección que no protege y que además parecería auditada. Hay una regresión dedicada a que
> nadie reintente esa vía.

> ⚠️ **Una regresión existente cambió de resultado, y no era falsa alarma.**
> `test_el_radar_escribe_la_grafia_canonica` sembraba un expediente **sin fecha límite**, y bajo el
> contrato nuevo eso significa «no archivar», así que dejaba de alcanzar la rama que escribe. **Lo
> que la prueba comprueba —la grafía canónica— no cambió**; lo que cambió es qué hace falta para
> llegar hasta ella, y se le añadió un plazo vencido al montaje. La comprobación previa del
> contrato dio por buenas cuatro pruebas tras leer tres: **la cuarta era ésta**.

---

### ⏭️ Tarea activa: Bloque 3 — Identidad y foco (contrato validado el 2026-08-19)

> **Contrato**: [`CONTRATO_BLOQUE_3.md`](CONTRATO_BLOQUE_3.md) v1.0.0, con las seis decisiones de
> dirección ya tomadas y la medición de contraste que sostiene el fondo oscuro. **Léelo antes de
> tocar el frontend.**

* **Paso 1** 🟢 — contrato, validado el 2026-08-19.
* **Paso 2** 🟢 — **el título legible, hecho el 2026-08-19.** `titulo_legible()` vive en
  `src/__init__.py` y la sirven la API —campo computado `titulo_corto`, junto al `titulo` íntegro
  que **no se toca**— y el informe CSV del Analista. Sobre los 68 títulos reales: **máximo 1.663 →
  200**, ninguno por encima del tope, **47 enteros** y **0 palabras partidas**. 17 regresiones en
  `tests/test_bloque3_titulo.py`. Suite **518/518**.
* **Paso 3** 🟢 — **paleta y fondo oscuro, hecho el 2026-08-19.** Las tres capas viven en
  `frontend/src/index.css` como tokens de `@theme`; **463 clases migradas** con un mapa explícito
  —lo que no estaba en el mapa se reportó para revisarlo a mano, no se dejó pasar—; la cabecera
  lleva el isotipo de Incoop y el nombre compuesto **con texto, no con imagen**. Verificado en el
  navegador contra la aplicación real: **0 fallos de contraste** en las cuatro pantallas y en la
  ficha de detalle, 0 errores de consola y ningún fondo claro superviviente.

> ⚠️ **Tres defectos que sólo aparecieron mirando la pantalla, y ninguno lo habría visto la suite.**
> Es la quinta vez en el proyecto.
>
> * **El texto blanco sobre los botones de color era ilegible.** Medido: blanco sobre el cian da
>   **2,34** y sobre la alarma **3,08**, los dos por debajo del 4,5 que exige el texto; la tinta
>   oscura da 8,25 y 6,28. **Un botón de acento sobre fondo oscuro lleva letra oscura**, que es
>   contraintuitivo hasta que se mide. Lo habría introducido yo al migrar.
> * **`ink-faint` se quedaba corto.** Daba 4,17 sobre el fondo pero **3,53 sobre las tarjetas**, y
>   ahí es donde vive: son pies de KPI de 11-12 px. El error fue elegir el valor contra el fondo y
>   no contra **la superficie más clara en la que aparece**. Corregido a `#8A87A0`.
> * **Mi propio script generó 18 clases inválidas.** Donde el original ya traía opacidad
>   (`bg-indigo-50/40`) el mapa añadió la suya y salió `bg-acento/10/40`, que Tailwind no reconoce:
>   esos fondos simplemente **no se pintaban**. Compilaba sin una queja.

> 🔑 **La regla del sistema de color, que salió de una medición y no del diseño previo.** Separar la
> capa de marca de la semántica **por tono es imposible**: quedan a 1-5 grados —rojo alarma contra
> rojo teja, ámbar contra amarillo—, así que como puntos de color serían indistinguibles. Rojo es
> rojo. Lo que las separa es **la forma**: un punto de color significa siempre categoría; un estado
> lleva siempre palabra y nunca es un punto suelto. **Lo que no lleva texto al lado no es una
> advertencia.** Está escrito en la cabecera de `index.css`, que es donde lo verá quien añada color.

* **Paso 4** 🟢 — **jerarquía de la tabla, hecha el 2026-08-19.** La columna del identificador
  desaparece y su ancho pasa al título, que sube a primera línea y a tipo de titular; el id y la
  fuente bajan a pie de fila en monoespaciada pequeña; el **sector se pinta por fin** —se calculaba,
  se persistía y se servía desde la Capa 5 sin que ninguna pantalla lo mostrara—; y el score pasa de
  píldora de color a **magnitud**. Verificado en vivo: 6 columnas en vez de 7, título a 15 px en tres
  líneas con el texto íntegro en el tooltip, y **0 fallos de contraste**.

> 🔑 **El score estaba mintiendo, y nadie lo había mirado así.** Pintaba verde por encima de 70,
> ámbar por encima de 45 y rojo por debajo. Pero **un 40 no es un peligro**: es una oportunidad que
> encaja poco. El rojo decía «cuidado» donde sólo había «esto no es lo tuyo», y de paso metía una
> píldora de color en cada fila —el *"todo pesa lo mismo"* de dirección, fabricado por la propia
> tabla—. Ahora la cifra se lee por tamaño, la barra por longitud, y el acento se reserva a la
> prioridad **Alta**, que es un juicio que el Filtro ya emite y no un umbral inventado en pantalla.

> ⚠️ **Dos cosas que sólo se vieron mirando, y una de ellas es un dato sucio.** *(1)* Los
> separadores `·` de la línea de metadatos quedaron a **1,23** de contraste: no fallan como texto
> —son decoración— pero **tampoco separaban**, y la línea se leía corrida. Token propio a 2,64.
> *(2)* La base trae **`Consultoria` y `Consultoría` como sectores distintos**, el mismo con y sin
> tilde: es la familia de H-27 en el vocabulario de sectores. La tabla **unifica lo que pinta**,
> pero el dato sigue sucio y su arreglo es del Filtro, no de la pantalla.

* **Paso 5** ⬜ — el ámbito: parámetro, KPIs e interruptor. **Es la tarea siguiente.**
* **Paso 6** ⬜ — el análisis visible, con sus tres estados.
* **Paso 7** ⬜ — cierre: suite, C7 con la aplicación arrancada y documentos.

> 🔑 **La decisión del Paso 2 que conviene no revisar: el título derivado NO se persiste.** Se
> recomendó al principio guardarlo en columna con esquema v9 y backfill, y **se retiró antes de
> implementarlo**. Dos motivos medidos: la regla se va a afinar cuando dirección la vea sobre datos
> reales —y con columna, cada retoque obliga a rebackfillar—, y la búsqueda del Funnel debe seguir
> operando sobre el título completo, para encontrar una licitación por una palabra de su cuerpo.
> Migrar el esquema por un dato que nadie consultaría desde la base es pagar por nada. La versión
> se declara igual (`VERSION_TITULO`), que es lo que la Regla 4 pide.

> ⚠️ **Una prueba que pasaba por el motivo equivocado, detectada al escribirla.** La regresión de
> las abreviaturas en versales —`S.A.`, `U.T.E.`— llevaba minúscula detrás del punto, así que la
> regla de frase no habría disparado **de todos modos** y la cautela no se ejercitaba. Con
> mayúscula detrás sí. Se le añadió además su contraria, para que endurecer la cautela no pueda
> desactivar la regla sin que nada se ponga rojo.

---

### 📕 Referencia del Bloque 3: las cuatro carencias (decisión de dirección del 2026-08-18)

> **La Capa 10 queda abierta y en pausa, con el Paso 8 esperando.** No es un salto de capa
> encubierto: el doble clic ya funciona de extremo a extremo y la capa no queda a medias en nada
> que impida usarla. Lo que se antepone es lo que dirección detectó **mirando el sistema
> terminado**, que es la primera vez que alguien lo mira como usuario y no como proyecto.

**El problema, dicho por dirección:** *"con todo el proyectazo que nos hemos mandado, que se vea
tan mediocre me disgusta y desmotiva"*. Y detrás de esa frase hay cuatro cosas concretas, no una
impresión:

1. **El sistema no se parece a Incoop.** La cabecera lleva un icono genérico de edificio en una
   caja con degradado donde debería ir el logo — que ni siquiera vive dentro del frontend: está en
   la raíz del proyecto. La iconografía es la librería estándar sin criterio propio y la jerarquía
   visual es de plantilla: todo pesa lo mismo, así que nada destaca. **Y los títulos de las
   licitaciones no se pueden leer**: la tabla los recorta a dos líneas —mediana de 135 caracteres,
   10 de 15 por encima de 80— y, sobre todo, **la fuente vuelca el anuncio entero en el campo**:
   el más largo de la base mide **1.663 caracteres**. Lo segundo no lo arregla ningún ancho de
   columna; hace falta derivar un título legible y conservar el texto completo aparte.
2. **El Funnel ofrece lo que no es su negocio** (H-47). Ver la reparación decidida abajo.
3. **El análisis semántico no se ve.** El motor funciona y está integrado en el pipeline desde la
   Capa 5 —**33 análisis completados y 176 documentos con texto extraído** en la base de hoy—,
   pero el trabajo queda enterrado en la ficha de detalle. Dirección llegó a creer que había que
   ejecutarlo a mano con un `.py`: eso es la herramienta de inspección, no el motor.
4. **El Centinela y la purga engañan** (H-45 y H-46), cada uno a su manera.

**Alcance del bloque**: identidad visual y jerarquía de la información, el filtro de ámbito, y
hacer visible el análisis que ya se hace. **No incluye** H-45 ni H-46, que siguen encajando mejor
en el Paso 9 de la Capa 10 —son el mismo problema: el sistema sabe cosas que no cuenta—.

> 🔑 **Decisión de dirección del 2026-08-18 sobre el ámbito (H-47): se filtra en la pantalla, con
> Catalunya por defecto y un interruptor para ver el resto.** No se toca la ingesta ni el scoring.
> El motivo es que **no se pierde ni un dato y la decisión es reversible**: si algún día interesa
> mirar fuera de zona, sigue estando todo. Descartado filtrar al ingerir —dejaría fuera una
> oportunidad legítima sin que nadie llegara a verla— y descartado subir el umbral, que mezclaría
> el criterio de ámbito con el de calidad comercial.

> 📌 **El material de referencia del negocio, revisado con dirección el 2026-08-18**: la unidad
> compartida de servicios activos (`G:\Unitats compartides\SERVEIS ACTIUS`, **sólo lectura, es
> una carpeta sensible**) contiene los **63 servicios vivos** de Incoop. Son escoles bressol,
> llars d'infants, ludoteques, casals infantils i de barri, dinamització juvenil, acció
> comunitària, centres de dia i PFI, **todos en Catalunya**. Es la mejor evidencia disponible de
> qué debería estar persiguiendo el sistema, y con ella se puede por fin rehacer el cruce de CPVs
> que quedó aplazado el 2026-08-07 esperando datos reales.

**Al terminar el bloque se retoma la Capa 10 por el Paso 8**, con su cuestión abierta del tope de
duración intacta.

---

### ⏸️ En pausa: Capa 10 — El Lanzador y Despertador, Paso 8

**La Capa 9 quedó cerrada el 2026-08-12**, con sus diez pasos completados y verificada con una corrida real del pipeline. Su historia vive más abajo y en el README; no hace falta releerla.

**La Capa 10 ya está redactada y pautada en el `README.md`**, sección *"🚀 Capa 10: El Lanzador y Despertador"*: objetivo, doce consideraciones de diseño, los artefactos que produce y **los 10 pasos atómicos en cuatro fases**. No hay que rediseñarla.

**El Paso 1 está redactado el 2026-08-13** y vive en [`CONTRATO_CAPA_10.md`](CONTRATO_CAPA_10.md): máquina de estados, seis transiciones prohibidas, los tres modos de invocación, la invariante central, el mapa de códigos de salida y los eventos `LANZADOR_*`. **Rige todo lo que venga después: léelo antes de tocar `src/lanzador.py`.** Quedó **validado por dirección el 2026-08-13** y **corregido a la v1.1.0 el 2026-08-17**.

* **Paso 1** 🟢 — contrato y máquina de estados, validado el 2026-08-13, **v1.1.0 desde el 2026-08-17**. Vive en [`CONTRATO_CAPA_10.md`](CONTRATO_CAPA_10.md).
* **Paso 2** 🟢 — healthcheck de arranque en frío en `src/lanzador.py`, **cierra H-37**. Aquí vive `es_sesion_interactiva()`, el punto único de decisión que gobierna toda llamada gráfica de la capa. Verificado contra el entorno real y contra la API de verdad levantada.
* **Paso 3** 🟢 — `config/lanzador.yaml` **v1.0.0** y su lector estricto en `src/lanzador.py`, sin valores por defecto (código de salida 11, distinto del 10 del entorno). **Cierra H-38.** Verificado en vivo con la API y el Cockpit levantados.

* **Paso 4** 🟢 — el Cockpit servido por FastAPI. **La raíz `/` sirve la aplicación y el JSON de bienvenida vive ahora en `/api/v1/`**: es el cambio de contrato de la Capa 7 que el Paso 1 declaró por adelantado. **La máquina de destino ya sólo necesita Python.** Verificado en vivo con un solo proceso y sin Node: HTML, assets y llamadas de datos desde el 8000, 12 expedientes en pantalla, `/docs` viva y 0 errores de consola. **56 regresiones acumuladas** de la capa en `tests/test_capa10_lanzador.py`.

* **Paso 5** 🟢 — supervisor del servidor en `src/lanzador.py` y `POST /api/v1/admin/apagar`. **Medido, no supuesto**: `CTRL_BREAK_EVENT` apaga uvicorn en 0,3 s, `TerminateProcess` en 0,1 s y **`CTRL_C_EVENT` no hace nada** en un grupo `CREATE_NEW_PROCESS_GROUP`. Verificado de extremo a extremo con un servidor real: arranque en 1,41 s y **apagado por el nivel 1 en 0,65 s**. **Destapó H-39.**

* **Paso 6** 🟢 — ejecución del pipeline respetando el cerrojo (`inspeccionar_cerrojo()` y `prospectar()` en `src/lanzador.py`), nuevo `src/proceso.py` y **esquema v8**. **Cierra H-40** y corrigió el contrato a v1.1.0. Verificado en vivo: corrida viva → 30 en 0,001 s sin lanzar nada; corrida muerta → la siguiente arranca en **0,017 s** en vez de esperar seis horas. **71 regresiones acumuladas** de la capa en `tests/test_capa10_lanzador.py`, más 13 en `tests/test_migracion_v8.py`.

* **Paso 7** 🟢 — **el doble clic, completado el 2026-08-18.** Empezó descubriendo que **faltaba el orquestador y ningún paso lo tenía asignado**: `orquestar()` y `main()` recorren ahora la máquina de estados con `--modo {completo,pipeline,cockpit}`. Añade `Incoop.vbs` —sin lógica, en ASCII puro y con un solo diálogo—, `Incoop.ico`, `tools/crear_accesos_directos.py` y el indicador de prospección en la cabecera del Cockpit. **Cierra H-42, H-43 y H-44.** **116 regresiones acumuladas** de la capa en `tests/test_capa10_lanzador.py`. Verificado con el doble clic real: sin consola, ventana de aplicación, corrida de 154,55 s con 15 expedientes nuevos y apagado limpio al cerrar.

**La tarea activa es el Paso 8**: el despertador, es decir, la tarea programada de Windows que ejecuta el modo «sólo pipeline» de madrugada. **Antes de implementarlo hay que resolver la cuestión abierta del tope de duración** *(abajo, en "Pendiente de acción del usuario")*, y respetar lo que el Paso 7 deja fijado: **la tarea invoca Python directamente, nunca el `.vbs`**, porque su diálogo de arranque colgaría para siempre en la Session 0.

> 🔑 **Las cuatro decisiones del Paso 7 que ya no hay que volver a plantear.** *(1)* **El Cockpit se abre antes de prospectar**: al revés serían más de cuatro minutos de pantalla en blanco tras el doble clic. *(2)* **Se apaga sólo lo que encendió esta invocación**, aunque haya marca de un lanzador anterior. *(3)* **El navegador se abre con perfil propio**, y eso sostiene todo lo demás: medido, con una instancia previa del mismo perfil el proceso lanzado delega y muere en 0,2 s, y el lanzador lo leería como "han cerrado el Cockpit". *(4)* **Sin ventana propia que vigilar no se apaga**, y consta con `LANZADOR_APAGADO_DIFERIDO`: apagar sería cerrarle la pantalla a quien la está mirando.

> 🔑 **Lo que el Paso 6 enseñó, y es lo más transferible de la sesión: un contrato validado no es un contrato comprobado.** El Paso 1 se validó el 2026-08-13 y contenía **dos afirmaciones falsas** que nadie podía ver leyéndolo —sólo aparecieron al escribir el código que debía obedecerlas—. *(1)* La precondición nombraba `db_lock()`, el cerrojo de fichero, cuando el que abarca una corrida es el lógico de `ejecuciones`: **medido, el `.lock` existe el 0,09 % del tiempo de una corrida**, así que la protección habría acertado esa fracción de las veces. *(2)* Afirmaba que `main.py` devuelve `1` para todo fallo, cuando devuelve **`0` al reventar a mitad**, que es el fallo más frecuente. Por eso el Paso 6 **empezó corrigiendo el documento** y no escribiendo código: implementar fielmente un contrato equivocado produce una protección decorativa que además parece auditada.

> 🔑 **Por qué el resultado del pipeline se lee de la base y no de su código de salida.** `finalizar_ejecucion()` escribe `COMPLETED` o `FAILED` en la fila de la corrida, así que el lanzador anota el último `id` antes de invocar y consulta el estado al terminar. Es la doctrina de la casa —**medir el efecto, no dar por bueno que se ejecutó**— aplicada a los códigos de salida, y no toca una línea de la Capa 9. Sin ello el código `31` no se emitiría nunca en el caso más común.

> ⚠️ **El defecto que me pillé cometiendo, y que vale la pena no repetir**: `prospectar(db_path=X)` inspeccionaba el cerrojo de X y lanzaba un pipeline que escribía en la base **por defecto**. Apuntando a una copia, arrancó una prospección real contra producción. Corregido propagando `DB_PATH_INCOOP` al subproceso, con su regresión. **Un parámetro que sólo gobierna la mitad de una operación no es un parámetro: es una trampa esperando a que alguien se fíe de él.**

> ⚠️ **Cómo NO medir si un proceso sigue vivo** *(costó dos intentos)*. Mientras alguien conserve un handle abierto sobre un proceso, Windows mantiene su objeto-proceso aunque haya terminado, y `OpenProcess` sigue funcionando sobre él: **el mismo proceso que lo engendró lo ve vivo; otro lo ve muerto.** Y en este entorno un proceso nieto no sobrevive a la muerte de su lanzadera. Las dos formas en que el proyecto pregunta caen del lado bueno —comprobado también para el supervisor del Paso 5—, pero una prueba mal montada mide su propio andamiaje. Está anotado en `src/proceso.py`.

> 🔑 **Lo que el Paso 3 decidió y no hay que volver a plantear.** *(1)* **Qué hacer ante un puerto ocupado por un tercero no es configurable**: el contrato ya lo fijó —detenerse—, y dejar que un fichero de texto autorizara lo contrario sería relajar una invariante desde configuración. Tampoco lo es si reutilizar nuestra propia API viva, porque la alternativa a reutilizarla no es arrancar otra: es no arrancar. *(2)* **Con varios fallos a la vez manda el del entorno, no el del puerto**: el código 20 sólo significa algo cuando el puerto es el único problema; el resumen, en cambio, no esconde ninguno.

> ⚠️ **El defecto que el Paso 3 destapó y por qué es el más incómodo de su familia** (H-38): el Cockpit compilado llevaba `http://127.0.0.1:8000/api/v1` incrustado. Mientras el puerto fue 8000 para todos, la URL absoluta funcionaba **por casualidad**; en cuanto el puerto se declara en un fichero, arrancar en otro habría servido las pantallas correctamente mientras todas las llamadas de datos iban al 8000. No rompe nada: miente en pantalla, como H-21, H-22 y H-23. La regresión mira **el bundle compilado y no el fuente**, porque es lo que se sirve y el fuente puede estar arreglado con `dist/` sin recompilar.

> 🔑 **Las dos decisiones del Paso 2 que rigen el resto de la capa.** La primera: **`es_sesion_interactiva()` contesta `False` ante la duda**, porque el daño es asimétrico —un diálogo de más cuelga la tarea nocturna para siempre y de forma invisible; uno de menos sólo pierde el aviso gráfico, y quedan el registro y el código de salida—. La segunda: **comprobar no modifica nada, ni siquiera el registro**. Instanciar `Memoria()` crea el directorio de datos (H-24) y escribir en `pipeline.jsonl` también, así que el healthcheck es puro y quien decide dejar rastro es el llamador. Crear cosas es competencia de `ARRANCANDO`, no de `COMPROBANDO`.

> ⚠️ **Lección de método del Paso 2, barata de aprender aquí y cara más adelante**: la evidencia inicial de H-37 incluía un tercer caso —cerrojo de 0 bytes recién creado— que **no era un defecto**, aunque diera el mismo síntoma. Respetarlo es correcto: puede pertenecer a un proceso vivo que aún no ha escrito su payload. La medición confirmaba la conclusión pero no el razonamiento, porque el resultado era el mismo por dos motivos distintos y sólo uno era un fallo. **Medir el efecto no basta si no se comprueba también la causa.**

**Tres decisiones de dirección ya tomadas el 2026-08-12** que la redacción respeta y que no hay que volver a plantear:
* **La capa arranca, no avisa.** Nada de notificaciones activas: el canal por el que el sistema habla es el Cockpit, que ya existe. El nombre "Despertador" se refiere a despertar el ecosistema, no a avisar a una persona.
* **La ejecución automática se apoya en el Programador de tareas de Windows**, no en un servicio residente propio. Programar es configuración, no código.
* **La máquina de destino sólo necesita Python** — ✅ **hecho en el Paso 4**: FastAPI sirve `frontend/dist/` como estáticos. Cambió el contrato de la Capa 7, como estaba previsto: la raíz `/` ya no devuelve el JSON de bienvenida sino el Cockpit, y el JSON vive en `/api/v1/`.

> 🔑 **La restricción transversal de la capa, y la que más fácil sería pasar por alto**: ocultar la consola obliga a avisar de los fallos fatales con un diálogo nativo del sistema, porque un healthcheck que falla ocurre **antes** de que exista el Cockpit donde avisar. Pero ese mismo diálogo, lanzado desde la tarea programada nocturna, corre en la **Session 0** —sin escritorio— y deja un proceso colgado esperando a un usuario que no existe. **La solución de un problema es la causa del otro.** Por eso una única función, `es_sesion_interactiva()`, decide consultando el identificador de sesión del proceso —no el modo de invocación, que es una intención y puede venir equivocada—, y **toda** llamada a interfaz gráfica pasa por ella. La prueba que lo cierra no es que la tarea se registre, sino que una corrida sin escritorio **termina sola y no deja proceso vivo**.

> ⚠️ **Lo que la Capa 9 deja avisado para la 10**: el pipeline ya no es sólo prospección. Cada corrida **archiva y purga** —`main.ejecutar_fase_depurador()`—, es decir, **borra ficheros del disco**. Un lanzador que ejecute el pipeline dos veces a la vez, o que lo mate a mitad, opera sobre un proceso que destruye peso documental. El cerrojo de fichero con TTL y verificación de PID (Paso D1) es ahora una pieza crítica, no una precaución.

### 📕 Historia cerrada de la Capa 9 (referencia, no tarea)

> Todo lo que sigue hasta el final de esta sección describe la **Capa 9, ya cerrada**. Se conserva porque sus lecciones y decisiones rigen lo que venga después, pero **ninguno de estos pasos es la tarea activa**: la tarea activa es el Paso 1 de la Capa 10, arriba.

* **Paso 1** 🟢 — contrato de servicio y máquina de estados, validado por dirección. Vive en [`CONTRATO_CAPA_9.md`](CONTRATO_CAPA_9.md) y **rige todo lo que venga después**: léelo antes de tocar el Depurador.
* **Paso 2** 🟢 — política de retención versionada en `config/retencion.yaml`, leída por `src/retencion.py`. Hoy en **v1.2.0**, con los bloques `archivado` (Paso 4) y `eliminacion` (Paso 6).
* **Paso 3** 🟢 — esquema **v6**: ciclo de vida en `expedientes`, `version_scoring` en `lotes`, métricas en `ejecuciones` y tabla `purgas`.
* **Paso 4** 🟢 — motor de archivado en `src/depurador.py`, verificado en vivo con la API y el Cockpit levantados. **Cierra H-30, H-31 y H-32.**
* **Paso 5** 🟢 — motor de purga documental en `src/depurador.py`. **Cierra H-33 y H-34.** No fue consolidación sino reparación: ninguna de las dos piezas que había hacía su trabajo.
* **Paso 6** 🟢 — motor de eliminación física, con la invariante de memoria comercial apoyada en tres fuentes y una cuarentena de 365 días archivado. **Nunca se dispara sola.**
* **Paso 7** 🟢 — router administrativo de lectura en `src/api/routers/admin.py`. Cuatro endpoints que no mutan nada: es la mitad honesta de la purga en dos tiempos.
* **Paso 8** 🟢 — router de mutación, el rescate `ARCHIVADO → VIVO` y el **esquema v7** (`rescatado_at`), que es lo que hace que un rescate sobreviva a la corrida siguiente.
* **Paso 9** 🟢 — pantalla de administración en el Cockpit, con la purga en dos tiempos y lo protegido a la vista.
* **Paso 10** 🟢 — **cierre de capa el 2026-08-12**: auditoría de contrato, suite E2E de las siete propiedades de la Regla 10 y verificación con corrida real. **Cierra H-35 y H-36.**

> 🔑 **La lección del Paso 5, que vale para todo lo que queda**: el aviso de este dosier —*"antes de escribir código nuevo, comprobar qué hace ya el código viejo"*— era literal. La purga se ejecutaba en cada corrida, no fallaba nunca y **no liberaba un solo byte**, porque seleccionaba documentos por un estado que sólo tienen antes de procesarse. Y el mismo vocabulario partido dejaba al Analista IA sin recibir ni un pliego. Dos capas dadas por operativas trabajando en vacío, en verde y sin una sola excepción. **Que un módulo se ejecute no es prueba de que haga algo: hay que medir su efecto.**

> 🔑 **Principio que salió de este paso y que rige el resto de la capa**: `deleted_at` gobierna **la visibilidad en el canal principal, no la editabilidad**. Un lote archivado se sigue pudiendo editar —registrar el importe de una adjudicación, sus garantías, sus costes—; simplemente no aparece en el Funnel salvo que se pidan las archivadas. Filtrar por `deleted_at` en una consulta de escritura es, a partir de ahora, un defecto. Y **editar no desarchiva**: el rescate `ARCHIVADO → VIVO` es explícito y vive en el Paso 8; si la edición desarchivara, la corrida siguiente volvería a archivar y el lote oscilaría solo.

**Cuatro decisiones de dirección ya tomadas** que el contrato respeta, y que no hay que volver a plantear:
* **La memoria comercial no se purga jamás.** Todo lote que llegó a `Presentada`, `Adjudicada` o `Perdida` es intocable. Se purga el peso documental, nunca el registro de negocio.
* **Retención documental de 180 días**, configurable y versionada, sustituyendo los 90 codificados a fuego.
* **Archivado a los 60 días de la fecha límite**, sin que `Presentada` sea archivable jamás: una oferta entregada y sin resolver es lo más vivo del embudo. El código rechaza `Presentada` en `estados_archivables` aunque se declare en el fichero.
* **Los bloqueos se resuelven quitando el bloqueo, no recortando la política** *(2026-08-07)*. Ante H-32 se planteó reducir los estados archivables a los que nadie edita; la dirección eligió lo contrario: arreglar la causa para que se puedan archivar los cinco sin congelar nada. De ahí sale el principio del recuadro anterior.

**Los Pasos 7 y 8** exponen el motor por la Pasarela API, y el 9 le da pantalla. Nada de eso puede relajar las precondiciones del Paso 6: la eliminación **exige confirmación explícita en el cuerpo de la petición**, y un endpoint que la dé por supuesta rompe el contrato. La previsualización es de lectura, pero **no es anónima**: emite `DEPURADOR_PURGA_PREVISUALIZADA` porque consta quién miró.

> ⚠️ **Aviso heredado del Paso 5, que se planteó como "consolidar, no escribir" y resultó ser lo contrario.** Se daba por hecho que `lector.ejecutar_purga_obsoletos()` y `memoria.rotar_backups()` "ya funcionaban y sólo les faltaba gobierno". No funcionaban: una no alcanzaba ningún documento con peso y la otra devolvía `None`, haciendo que el pipeline anunciara un fallo de backup inexistente. **Antes de dar por bueno lo que hay, medir su efecto sobre una base sembrada.**

Bloque 1 — Cimientos 🟢 y Bloque 2 — Coherencia LCSP 🟢 están cerrados. El detalle está más abajo, en "Pasos completados"; el contrato del Bloque 2 vive en [`CONTRATO_BLOQUE_2.md`](CONTRATO_BLOQUE_2.md).

**Node.js sigue haciendo falta para desarrollar, no para usar.** La versión 24.19.0 LTS quedó instalada el 2026-08-06 y `npm run build` se ejecuta limpio, con `tsc -b` en modo estricto sin errores. La Capa 10 se apoya en esto: el bundle compilado es lo que FastAPI servirá, de modo que la máquina de destino no necesitará Node.

**Aviso para no repetir un diagnóstico equivocado**: durante un tiempo se dio por hecho que `frontend/dist/` estaba desfasado, deduciéndolo de su fecha de modificación. Era falso. Al recompilar, Vite generó **exactamente los mismos nombres de fichero** (`index-B6BIdKdG.js`, `index-BKUbaev-.css`), y esos nombres son un hash del contenido: el bundle ya estaba al día. El proyecto vive en OneDrive, así que lo más probable es que se compilara en otra máquina. **La fecha de un artefacto no dice de qué fuente salió: compruébese el contenido.**

**Decisiones ya tomadas que no hay que volver a discutir**: ver la tabla de decisiones al final del dosier de auditoría.

### ⚠️ Pendiente de acción del usuario

**Una sola cuestión abierta, y no bloquea el Paso 7:**

* **Si el pipeline debe tener un tope de duración**, ahora que lo va a lanzar una tarea
  nocturna sin consola. **No se ha inventado ningún plazo** porque la Regla 4 lo prohíbe.
  **El enunciado completo está anotado donde toca resolverlo**: en el `README.md`, dentro del
  **Paso 8** de la Capa 10, con las cuatro cosas que hay que decidir y por qué; y su ausencia
  queda explicada en el bloque `despertador` de `config/lanzador.yaml`, que es donde alguien
  buscará el parámetro. **No hace falta traerlo aquí ni resolverlo antes de tiempo.**

  > Lo único que conviene no perder de vista al llegar: un pipeline **colgado** sigue vivo, de
  > modo que el cerrojo del Paso 6 haría lo correcto —código 30— **noche tras noche**, y el
  > sistema no parecería averiado sino simplemente vacío de oportunidades. Y la red que hay hoy
  > —la reapropiación a las 6 h— **no mata nada**: sólo deja arrancar a la corrida siguiente, de
  > modo que a las 6 h habría dos pipelines a la vez sobre una base que purga ficheros.

**Resueltas el 2026-08-17:**

* **Los 48 expedientes de la base son material de prueba, no un activo** *(decisión de
  dirección)*. Se conservan tal cual. Ver el recuadro de abajo, que acota hasta cuándo.
* **La corrida `RUNNING` sin cerrar** (id 4) se deja como está a propósito: la reclamará sola
  la prospección siguiente, y forzarla a mano es la transición prohibida nº 3.

> 🔑 **Hasta la demo, los datos son material de prueba** *(decisión de dirección, 2026-08-17)*.
> Mientras el proyecto sea una beta, **lo valioso es detectar defectos, no conservar
> registros**: se puede ejecutar el pipeline real contra fuentes públicas cuantas veces haga
> falta para ejercitar el ecosistema, y perder datos por el camino es aceptable **siempre que
> se sepa por qué se perdieron**. Lo que no es aceptable es un fallo que no se controla.
>
> ⚠️ **Esta decisión tiene fecha de caducidad y no es una licencia permanente.** Deja de valer
> **en cuanto el sistema entre en demo o en uso operativo**, y para entonces la idea es
> precisamente haber atajado ya los problemas que hoy pueden costarnos datos. Un agente que lea
> esto después de esa fecha está leyendo una regla vencida: la doctrina por defecto del
> proyecto —la memoria comercial no se purga jamás, la purga se previsualiza antes de
> ejecutarse— **sigue implementada y no se ha relajado ni una línea**. Lo que cambia es sólo
> cuánto duele perder la base de pruebas, no lo que el código tiene permitido hacer.

**Siete hallazgos abiertos** *(tres de la revisión funcional del 2026-08-18 y **dos nuevos del
2026-08-19**, estos últimos los más graves de todos; su evidencia completa está en el dosier)*:

* 🟡 **H-48 · Se archivan como expiradas licitaciones con el plazo todavía abierto** — **causa
  reparada el 2026-08-19 (Paso 2); queda el rescate de lo ya archivado (Paso 3).**
  `soft_delete_obsoletos()` marca `Inactiva` todo lote **`Nueva`** ausente del feed **sin mirar la
  fecha límite** — aunque la consulta sí trae el dato y la rama hermana sí lo consulta. **Medido:
  45 lotes con plazo abierto archivados, 19.986.870,63 € de PBL, y las dos mejores oportunidades
  de la base (82 puntos) invisibles** mientras el Funnel enseña como máximo 71. Castiga sobre todo
  a `PSCP Catalunya API`, cuyos **16 expedientes están archivados los 16** — justo la fuente 100 %
  catalana y la única con cobertura documental completa. **Es la causa de que sólo 4 de los 15
  vivos tengan pliego**, y por tanto de que el análisis semántico "no se vea".
* 🔥 **H-49 · El mismo expediente entra dos veces porque su identificador no se normaliza.** En la
  fuente catalana el `id` sale tal cual de `codi_expedient`, texto libre. La misma licitación
  —mismo UUID de publicación, misma ingesta al segundo— entró como `EXPEDIENT214 2026…` y
  `EXPEDIENT  214 2026…`. **La copia con los 11 pliegos y el título corto quedó archivada; la que
  sobrevive tiene 0 documentos y el título de 1.663 caracteres** que motivó media reparación del
  Bloque 3. El peor título de la base y la falta de pliegos son **el mismo defecto**.

* **H-45 · El Centinela no está vacío: está ciego.** Las dos fuentes oficiales devuelven error
  —DOGC **404**, BOPB **500**— y llevan así desde antes de hoy. El pipeline degrada correctamente
  y lo registra; **la pantalla no distingue "no hay alertas" de "no he podido mirar"**. Dos
  reparaciones distintas: actualizar las URLs en `config/fuentes.yaml` *(fuera del código)* y
  hacer visible la degradación *(hermano del distintivo del Paso 9)*.
* **H-46 · La purga documental se ejecuta con un solo clic**, mientras la eliminación de
  expedientes —en la misma pantalla— exige previsualizar primero. La previsualización de la purga
  documental **ya existe y la API ya la sirve**: la pantalla no la usa.
* **H-47 · El Funnel se llena de licitaciones fuera de ámbito.** De 15 expedientes vivos, **3 son
  catalanes y 3 de Madrid** *(eran 19 al anotarlo el 18-08)*. **H-48 lo agrava**: la fuente catalana
  se archiva entera en cada corrida, así que el desequilibrio es peor de lo que este recuento sugiere. El perfil comercial está bien —premia la geografía con +40/+35/+20—
  pero **la geografía suma puntos y no descarta nada**, y dos de las tres fuentes son estatales.
  Decisión de dirección pendiente: filtrar en pantalla, filtrar al ingerir o subir el umbral.

**Dos hallazgos abiertos de antes:**

* **H-39**, con sitio y fecha asignados. `data/pipeline.jsonl` mezcla dos esquemas de evento
  incompatibles desde la Capa 7 —el pipeline y el lanzador escriben `action`, la API escribe
  `tipo_evento`—. **No bloqueó el Paso 6** y se repara en el **Paso 9**, que es donde se decide
  qué canal dice qué. No hace falta adelantarlo.
* **H-41, sin asignar**: el pipeline revienta con `0xC0000005` sobre datos reales, muriendo sin
  ejecutar su `finally`. **No pertenece a la Capa 10**, que arranca procesos y no lee pliegos.
  Procede decidir si se abre como tarea propia o se atiende en el Paso 10. Lo primero que hará
  falta es **registrar qué fichero se va a procesar antes de abrirlo**: un crash nativo no deja
  traza en Python, así que el rastro hay que escribirlo por adelantado. **El 2026-08-18 no se
  reprodujo** en una corrida real de 154,55 s con 36 documentos: no está arreglado —no se ha
  tocado nada—, pero consta que **no es sistemático**.

**Sigue vigente y sin tocar la nota de alcance sobre `db_lock()`**: su `created_at` es la fecha
del cerrojo y no la del proceso propietario. Lo que el Paso 6 endureció es el cerrojo de
**ejecución**, que es otro. Sin un defecto reproducible que lo exija, no se toca.

~~Y una **inconsistencia latente, hoy inocua**~~ **— cerrada el 2026-08-12 dentro del Paso 8.** `Memoria.actualizar_estado_lote()` guardaba el estado
en minúsculas, mientras el selector del Cockpit ofrece los valores capitalizados del enum. Un lote
guardado como `'perdida'` se pintaría en la interfaz como *"Nueva"*, porque el `<select>` no
encuentra la opción y cae en la primera. **No afecta hoy**: ningún código de producción llama a ese
método —la vía real del Cockpit es `mutar_estado_lote_transaccional()`, que respeta la grafía del
enum—, y sólo aparece con datos escritos a mano. Es la misma familia que H-27; conviene cerrarlo
antes de que alguien cablee ese método a una CLI.

Queda **una cuestión de diseño abierta, sin urgencia**: el Cockpit no muestra el sector en ninguna
pantalla —`sector` sólo existe en `frontend/src/types/api.ts`, sin componente que lo pinte—. El
dato se calcula, se persiste y se sirve, pero nadie lo ve. Procede decidir si debe verse o si su
destino es el reporting de capas posteriores.

Las decisiones de negocio anteriores se resolvieron el 2026-08-06 y constan en la tabla de
decisiones del dosier: matriz de subrogación, bonificación de la subrogación acotada, rastro de las
alertas descartadas y validación del proveedor LLM.

### 📊 Cobertura de CPVs: pregunta resuelta el 2026-08-07

Quedó aplazada el 31-07-2026 con este enunciado: de los CPVs capturados en la base, muy pocos
coincidían con el perfil de Incoop. Dos hipótesis opuestas, y hasta ahora sin separar: **o el
perfil se ha quedado corto, o las fuentes traen licitaciones fuera de ámbito.**

**Resuelta a favor de la segunda, con matices.** El cruce se rehízo sobre `CPVs_Incoop.xlsx`, que
es la única evidencia superviviente al borrado de la beta (101 CPVs distintos, 174 apariciones en
51 expedientes de julio).

*Primero, el enunciado estaba mal planteado.* Contaba **coincidencias exactas** (5 de 101), pero el
Filtro **no compara el CPV completo**: indexa por los 3 y 5 primeros dígitos para capturar CPVs
hermanos. Medido como puntúa de verdad:

| Cómo puntúa | CPVs distintos | Apariciones |
|---|---|---|
| Core (+40) | 23 | 30 |
| División (+25) | 6 | 9 |
| División (+10) | 19 | 38 |
| **Sin puntuación** | **53** | **97** |

*Segundo, lo que no puntúa mayoritariamente no debe puntuar.* De las 97 apariciones sin puntuar,
**70 (el 72 %) pertenecen a divisiones que el propio perfil ya excluye por texto**:

| División | Apariciones | ¿Debe puntuar? |
|---|---|---|
| 72 · Servicios TI | 27 | No — `exclusiones` ya contiene "software puro" |
| 71 · Arquitectura e ingeniería | 15 | No — `exclusiones` contiene "ingeniería" y "arquitectura" |
| 15 · Alimentación y bebidas | 14 | No — es suministro, no servicio |
| 22 · Imprenta | 14 | No — es suministro |
| 24, 44, 51, 60, 73 | 12 | No — químicos, construcción, instalación, transporte, I+D |

El sistema no tiene un agujero de cobertura: está ignorando correctamente lo que no es su negocio.
El ruido viene de las fuentes, no del perfil.

**Candidatos reales a incorporar** (16 apariciones, a validar comercialmente):

| CPV | Qué es | Apariciones |
|---|---|---|
| `77310000` | Jardinería y mantenimiento de zonas verdes | 5 |
| `55320000`, `55321000`, `55300000` | Servir comidas y restauración (hoy sólo puntúa `555*`) | 5 |
| `85143000`, `85144000` | Ambulancia y servicios de hospital — **probablemente fuera de ámbito** | 3 |
| `90513000`, `90700000`, `90714600` | Residuos y medio ambiente (hoy sólo puntúa `909*`) | 3 |

**No se ha tocado `config/perfil_incoop.yaml`.** La muestra es pequeña (dos semanas de julio) y los
datos que la produjeron ya no existen. Procede **rehacer este cruce tras la primera ejecución
real**, sobre datos vivos, y decidir entonces. `77310000` es el primer candidato: la jardinería sí
parece ámbito de Incoop y aparece con la misma frecuencia que CPVs que sí puntúan.

---

## 🛠️ Estado Actual del Desarrollo

### Capas Completadas y Validadas
* **Capa 1** - El Radar (Extracción de Datos Crudos): 🟢 Completada.
* **Capa 2** - El Filtro (Scoring y Calibración Financiera): 🟢 Completada.
* **Capa 3** - La Memoria (Registro, Persistencia y Trazabilidad Analítica): 🟢 Completada.
* **Capa 4** - El Lector Documental (Descarga y OCR de Pliegos): 🟢 Completada.
  * Paso 1 — Inicialización del Entorno Documental (Bootstrap): 🟢 Completado.
  * Paso 2 — Ingestión de URLs desde el Radar (XML + HTML): 🟢 Completado.
  * Paso 3 — Descargador Multihilo Resiliente (PDF Nativo): 🟢 Completado.
  * Paso 4 — Motor de Extracción de Texto Nativo (PyMuPDF): 🟢 Completado.
  * Paso 5 — Motor de OCR Diferido para PDFs Escaneados (Tesseract): 🟢 Completado.
* **Capa 5** - El Analista IA (Extracción Semántica): 🟢 Completada y Validada.
  * Paso 1 — Definición del Esquema DTO (`AnalisisSemanticoDTO`): 🟢 Completado.
  * Paso 2 — Migración de Base de Datos a Esquema v4 (`src/memoria.py`): 🟢 Completado.
  * Paso 3 — Cliente/Adaptador del Proveedor LLM (`src/analista.py`): 🟢 Completado.
  * Paso 4 — Motor de Segmentación Inteligente / Smart LCSP Chunking (`src/analista.py`): 🟢 Completado.
  * Paso 5 — Ingeniería de Prompts Especializados LCSP (`src/analista.py`): 🟢 Completado.
  * Paso 6 — Algoritmo de Recalibración del Scoring (`src/analista.py`): 🟢 Completado.
  * Paso 7 — Trazabilidad JSONL y Resiliencia en Modo Degradado (`src/analista.py`): 🟢 Completado.
  * Paso 8 — Orquestación en Pipeline Principal (`src/main.py`) y Reporting Comercial: 🟢 Completado.
  * Paso 9 — Consola de Comando CLI e Inspección de Análisis (`src/analista.py` / CLI): 🟢 Completado.
  * Paso 10 — Pruebas de Integración E2E y Cierre de Capa 5: 🟢 Completado.

* **Capa 6** - El Centinela de Boletines (DOGC/BOPB - Fase Temprana): 🟢 Operativa. El defecto del Paso 5 quedó cerrado el 2026-08-06.
  * Paso 1 — Definición del Esquema DTO (`AlertaBoletinDTO`) y Contrato de Servicio: 🟢 Completado.
  * Paso 2 — Migración de Base de Datos a Esquema v5 (`boletines_alertas`): 🟢 Completado.
  * Paso 3 — Cliente / Ingestor Resiliente de Fuentes Oficiales (DOGC y BOPB): 🟢 Completado.
  * Paso 4 — Motor de Segmentación y Filtrado por Reglas Duras de Fase Temprana: 🟢 Completado.
  * Paso 5 — Integración del Analista IA para Clasificación Semántica de Boletines: 🟢 Completado tras dos reparaciones. La factoría de proveedor LLM nunca había funcionado (H-05): invocaba `proveedor_llm_factory()`, inexistente, y el consumidor llamaba a `.generar_texto()`, ausente de la interfaz `LLMProvider`; **todos** los boletines se procesaron sin capa semántica. Reparado en el Paso C2. Al hacerlo afloró un segundo defecto (H-16): el dictamen degradado se presentaba como veredicto y alteraba el score. Cerrado el 2026-08-06 con el contrato honesto de Modo Degradado.
  * Paso 6 — Algoritmo de Scoring y Priorización Temprana (`EvaluadorScoringCentinela`): 🟢 Completado.
  * Paso 7 — Trazabilidad JSONL y Resiliencia en Modo Degradado (`GestorTrazabilidadCentinela`): 🟢 Completado.
  * Paso 8 — Orquestación en Pipeline Principal (`src/main.py`) y Reporting CSV: 🟢 Completado.
  * Paso 9 — Consola de Comando CLI e Inspección de Centinela (`src/centinela.py`): 🟢 Completado.
  * Paso 10 — Pruebas de Integración E2E y Cierre de Capa 6 (`tests/test_capa6_e2e.py`): 🟢 Completado.

* **Capa 7** - La Pasarela API (FastAPI REST Micro-API): 🟢 Completada y Validada.
  * Paso 1 — Inicialización del Entorno y Dependencias Core (`src/api/dependencies.py`): 🟢 Completado y Validado.
  * Paso 2 — Modelado de Esquemas Base con Pydantic v2 (`src/api/schemas.py`): 🟢 Completado y Validado.
  * Paso 3 — Endpoint de Autodiagnóstico y Salud (`/api/v1/health`): 🟢 Completado y Validado.
  * Paso 4 — Router Analítico de KPIs (`/api/v1/kpis`): 🟢 Completado y Validado.
  * Paso 5 — Router del Funnel Reactivo PSCP (`/api/v1/licitaciones`): 🟢 Completado y Validado.
  * Paso 6 — Router del Canal Proactivo Centinela (`/api/v1/alertas-tempranas`): 🟢 Completado y Validado.
  * Paso 7 — Endpoint de Mutación de Licitaciones (`PUT /api/v1/licitaciones/{id}/estado`): 🟢 Completado y Validado.
  * Paso 8 — Endpoint de Mutación del Centinela (`PUT /api/v1/alertas-tempranas/{id}/estado`): 🟢 Completado y Validado.
  * Paso 9 — Middleware de Seguridad, CORS y Trazabilidad JSONL: 🟢 Completado y Validado.
  * Paso 10 — Suite de Pruebas de Integración y Cierre Oficial de Capa 7 (`tests/test_capa7_api.py`): 🟢 Completado y Validado.
* **Capa 8** - El Cockpit Visual (React + Vite + Tailwind CSS + TanStack Table + TanStack Query): 🟢 Completada y Validada (100%).
  * Paso 1 — Inicialización del Proyecto Frontend (Vite + React + TypeScript + Tailwind CSS): 🟢 Completado y Validado.
  * Paso 2 — Espejo de Tipos TypeScript (`src/types/api.ts`) y Cliente API HTTP: 🟢 Completado y Validado.
  * Paso 3 — Configuración de TanStack Query v5 y Mutaciones Optimistas: 🟢 Completado y Validado.
  * Paso 4 — Sistema de Diseño, Paleta de Colores y Componentes UI Base: 🟢 Completado y Validado.
  * Paso 5 — Header, Navegación Principal e Indicador Sensor `/health`: 🟢 Completado y Validado.
  * Paso 6 — Dashboard Analítico de KPIs y Tesorería: 🟢 Completado y Validado.
  * Paso 7 — Tabla Ejecutiva del Funnel Reactivo PSCP (TanStack Table Server-Side): 🟢 Completado y Validado.
  * Paso 8 — Canal Proactivo Centinela (Oportunidades Fase Temprana DOGC/BOPB): 🟢 Completado y Validado.
  * Paso 9 — Modal / Drawer de Detalle Completo y Mutación Transaccional: 🟢 Completado y Validado.
  * Paso 10 — Suite de Pruebas Frontend, Build de Producción y Cierre Oficial de Capa 8: 🟢 Completado y Validado.
* **Capa 9** - El Histórico y Depurador (Archivo y Purga de Datos): 🟢 **Completada y Validada el 2026-08-12.** Los diez pasos cerrados, verificada con una corrida real del pipeline.
  * Paso 1 — Contrato de Servicio y Máquina de Estados del Ciclo de Vida: 🟢 **Completado y validado el 2026-08-07.** Vive en [`CONTRATO_CAPA_9.md`](CONTRATO_CAPA_9.md). Destapó H-27.
  * Paso 2 — Política de Retención Versionada (`config/retencion.yaml`): 🟢 **Completado el 2026-08-07.** Los plazos dejan de estar codificados a fuego en `main.py`. Nuevo `src/retencion.py` como único punto de lectura, que **no aplica valores por defecto**: si la política falta o es incoherente lanza `PoliticaRetencionInvalida` y no se purga nada. 19 regresiones en `tests/test_retencion_politica.py`. Verificadas en vivo las dos ramas del cableado real de `main.py`.
  * Paso 3 — Migración a Esquema v6 (`src/memoria.py`): 🟢 **Completado el 2026-08-07.** Ciclo de vida a nivel de expediente, `version_scoring` en `lotes` (y poblado de verdad: Filtro → upsert → SQLite), métricas en `ejecuciones` y tabla `purgas`. **Cierra H-27** y destapó H-29. 9 regresiones en `tests/test_migracion_v6.py`, con DDL de v5 escrito a mano para que la migración se pruebe de verdad.
  * Paso 4 — Motor de Archivado (`src/depurador.py`): 🟢 **Completado el 2026-08-07.** Archivado a los 60 días de la fecha límite —o de la ingesta, si el feed no trajo fecha legible—, con cascada al expediente cuando ninguno de sus lotes sigue vivo. No toca `estado_operativo` ni un solo fichero, y es idempotente por construcción (todo `UPDATE` filtra `deleted_at IS NULL`). Parámetros en el bloque `archivado` de `config/retencion.yaml` (política **v1.1.0**), que rechaza `Presentada` aunque se declare. Auditoría en la tabla `purgas` y eventos `DEPURADOR_ARCHIVADO` / `DEPURADOR_MODO_DEGRADADO`. Pobladas por fin las métricas de `ejecuciones`. **Cierra H-30, H-31 y H-32.** 41 regresiones en `tests/test_capa9_archivado.py`. Verificado en vivo con la API y el Cockpit levantados contra base sembrada: Funnel de 3 filas por defecto y 7 con *"Incluir archivadas"*, y edición de un lote archivado desde la tabla que persiste sin desarchivarlo.
  * Paso 5 — Motor de Purga Documental (`src/depurador.py`): 🟢 **Completado el 2026-08-12.** `purgar_documentos()` y `rotar_copias()`, con medición real de bytes liberados, vaciado de `texto_extraido`, fila en `purgas` y los eventos `DEPURADOR_PURGA_INICIADA` / `COMPLETADA` / `ABORTADA`. La selección deja de mirar `estado_operativo`: lo que hace purgable a un documento es haber cumplido su plazo —contado desde la fecha límite, con caída a la ingesta— y tener peso que liberar. Un fichero que no se puede borrar **no** se marca como purgado, para que no quede huérfano en disco. La purga sale del Lector: gobernar el ciclo de vida es competencia exclusiva del Depurador. **Cierra H-33 y H-34.** 14 regresiones en `tests/test_capa9_purga_documental.py`, la primera de ellas recorriendo el Lector real sobre un PDF real sin sembrar estados (C4). Verificado en vivo contra base sembrada con ficheros en disco: 4 ficheros y 1.832 bytes liberados, el pliego dentro de plazo intacto y la memoria comercial del expediente adjudicado sin un solo campo movido.
  * Paso 6 — Motor de Eliminación Física con Orden de Integridad (`src/depurador.py`): 🟢 **Completado el 2026-08-12.** `previsualizar_eliminacion()` y `eliminar_expedientes()`, con los cuatro errores tipados del contrato. **La invariante de memoria comercial mira tres fuentes y basta una para bloquear**: el estado actual del lote, los seis campos comerciales y el histórico `log_cambios` del Paso 4 —sin este último, un lote que pasó por `Presentada` y hoy figura `Inactiva` sería indistinguible de una `Nueva` que nadie miró—. Cascada hoja→raíz en una sola transacción con las claves foráneas **activas**; los ficheros se borran antes que sus filas. Nueva cuarentena de **365 días archivado** en el bloque `eliminacion` de `config/retencion.yaml` (política **v1.2.0**). **No se cablea al pipeline**: `run.py` no puede borrar un expediente ni queriendo. 24 regresiones en `tests/test_capa9_eliminacion.py`. Verificado en vivo contra la política real: 3 expedientes bloqueados por tres motivos distintos, 1 eliminado, cero huérfanos, copia previa creada — y comprobado que SQLite **impide de verdad** borrar la raíz antes que las hojas, de modo que el orden no funciona por casualidad.
  * Paso 7 — Router Administrativo de Lectura (`src/api/routers/admin.py`): 🟢 **Completado el 2026-08-12.** `/almacenamiento`, `/retencion`, `/purga/previsualizacion` e `/ejecuciones`, todos GET y ninguno con efectos. La previsualización **no altera nada pero no es anónima**: emite `DEPURADOR_PURGA_PREVISUALIZADA`. Una política ilegible devuelve **503, nunca un listado vacío**: "no hay nada que purgar" y "no he podido leer el criterio" no pueden parecerse en pantalla. Nuevos `medir_almacenamiento()`, `directorio_documentos()` y `Depurador.previsualizar_purga_documental()`, más `Memoria.listar_ejecuciones()`. 11 regresiones en `tests/test_capa9_admin_api.py`. **Verificado levantando la API real** y consultando los cuatro endpoints por HTTP.

  > 🔎 **Dos coherencias por accidente detectadas y unificadas aquí**: los pliegos y el registro JSONL del Depurador viven **junto a la base** (`dirname(db_path)`), no en `ruta_datos()` — coinciden sólo mientras la base esté en `data/`. `directorio_documentos()` es ahora el único sitio que lo decide. Y la política guarda los estados normalizados en minúsculas (H-27), de modo que servirlos tal cual habría pintado *"nueva"* junto a los *"Nueva"* del Funnel; la grafía visible sale del enum, no de un `.capitalize()` que se comería la mayúscula de `Anulada_Administracion`.
  * Paso 8 — Router Administrativo de Mutación: 🟢 **Completado el 2026-08-12.** `POST /purga` (documental o eliminación), `POST /backup` y `POST /expedientes/rescatar`. **La confirmación viaja en el cuerpo y no tiene valor por defecto**: un campo con `= True` convertiría "olvidé enviarlo" en "sí, adelante". Errores tipados traducidos: 400 sin confirmación o sin lista explícita, 409 por integridad, 503 si falla la copia previa o la política. Que todo quede bloqueado **no es un 409**: es la invariante funcionando, y el cliente necesita ver el motivo de cada expediente. **Esquema v7**: nueva columna `rescatado_at` en `lotes` y `expedientes`. 8 regresiones nuevas en `tests/test_capa9_admin_api.py`. Verificado en vivo con la API real, incluida la migración v6→v7 de la base.

  > 🔑 **Por qué el rescate necesitó una migración**: sin marca, la corrida siguiente volvía a archivar el lote —la fecha límite sigue vencida— y quien lo rescató vería su decisión deshecha sola. Es la transición prohibida nº 7 vista desde el otro lado, y el mismo criterio que el Paso D5 fijó para el Centinela: **una reejecución del pipeline no puede pisar lo que decidió una persona.** Se resolvió con una columna y no con una entrada en `log_cambios` por la Convención C3: una protección que dependa de analizar texto libre es una protección que un día deja de encontrar lo que busca.
  * Paso 9 — Pantalla de Administración en el Cockpit (`frontend/src/components/AdminPanel.tsx`): 🟢 **Completado el 2026-08-12.** Ocupación en disco con la base **marcada como no purgable**, política vigente, historial de prospecciones y purga en dos tiempos. **El botón de eliminar nace deshabilitado y sólo se activa tras previsualizar**: una purga lanzable sin haber mirado es una purga a ciegas con pasos extra. **Lo protegido se pinta con el mismo peso visual que lo eliminable**, y no escondido en un desplegable: la garantía de que la memoria comercial no está en riesgo tiene que poder comprobarse con los ojos. La previsualización **no se lanza sola al abrir la pantalla**, porque su registro de auditoría debe corresponder a que alguien la pidiera. `tsc -b` limpio en modo estricto y `npm run build` correcto. **Verificado en vivo pilotando el navegador** contra la API y una base sembrada: previsualización con 1 eliminable y 3 protegidos por dos motivos distintos, confirmación ejecutada, copia previa creada y las cifras de disco actualizándose sin un solo error de consola. Los datos de verificación se retiraron después.
  * Paso 10 — Suite E2E, Verificación en Vivo y Cierre de Capa 9: 🟢 **Completado el 2026-08-12.** Empezó por una **auditoría de contrato** —los 8 eventos JSONL, los 5 errores tipados y las 7 transiciones prohibidas, uno a uno— que destapó **H-35** (la purga documental sólo corría los días con ingesta nueva) y **dos capacidades declaradas que no existían**: un error tipado que nadie lanzaba y una entrada opcional que `archivar()` no acepta, ambas retiradas del contrato con su motivo. `tests/test_capa9_e2e.py` con 11 pruebas organizadas por las siete propiedades de la Regla 10. **Verificado con una corrida real del pipeline**: 12 expedientes, 88 documentos detectados, 63 descargados y leídos, **10 análisis del LLM** y 0 errores, con las cifras de la pantalla comparadas una a una contra la consulta directa. Y **H-36**, descubierto cometiéndolo: purgar sobre una copia de la base borra los ficheros del original.

  > 🔑 **Las dos lecciones del cierre.** La primera: *un contrato que promete lo que no hay es peor que uno más corto* — tres de los huecos no eran errores de código sino promesas sin implementar, y sólo aparecen recorriendo el documento con una lista en la mano. La segunda, más cara: **la precaución razonable puede ser la que activa el daño**. Copiar la base para probar sin riesgo es lo que borró 63 pliegos de producción, porque la copia conserva las rutas absolutas del original. Ahora el Depurador sólo borra ficheros bajo su propio directorio documental.

  > ⚠️ **Este recuadro decía que el Paso 5 era "consolidar, no escribir", porque las dos piezas de purga "ya funcionaban y sólo les faltaba gobierno". Era falso, y se conserva como advertencia.** `lector.ejecutar_purga_obsoletos()` no alcanzaba ningún documento con peso (H-33) y `memoria.rotar_backups()` devolvía `None`, haciendo que el pipeline anunciase un fallo de backup inexistente (H-34). Las dos se ejecutaban en cada corrida sin fallar nunca. **Que un módulo se ejecute no prueba que haga algo: hay que medir su efecto sobre una base sembrada antes de darlo por bueno.**

* **Capa 10** - El Lanzador y Despertador (Silent Launcher VBS y Tarea Programada): 🛠️ **Capa activa desde el 2026-08-12.** Redactada y pautada en el `README.md`. **Pasos 1 a 5 cerrados el 2026-08-13; Paso 6 el 2026-08-17; Paso 7 el 2026-08-18.** Tarea activa: el **Paso 8**. El detalle de cada paso vive arriba, en "Tarea activa".
  * Paso 1 — Contrato de Servicio y Máquina de Estados: 🟢 **v1.0.0 el 2026-08-13, v1.1.0 el 2026-08-17.** Destapó H-37.
  * Paso 2 — Healthcheck de Arranque en Frío y canal de fallo fatal: 🟢 **Cierra H-37.** Aquí vive `es_sesion_interactiva()`.
  * Paso 3 — Configuración versionada `config/lanzador.yaml` v1.0.0: 🟢 **Cierra H-38.**
  * Paso 4 — El Cockpit servido por FastAPI: 🟢 La máquina de destino ya sólo necesita Python.
  * Paso 5 — Supervisor del servidor: arrancar, reutilizar y apagar sin matar: 🟢 **Destapó H-39.**
  * Paso 6 — Ejecución del pipeline respetando el cerrojo: 🟢 **Completado el 2026-08-17.** Corrigió el contrato a v1.1.0, creó `src/proceso.py`, subió el esquema a **v8** y **cierra H-40**.
  * Paso 7 — Lanzador `.vbs`, modo aplicación y accesos directos: 🟢 **Completado el 2026-08-18.** Aportó el orquestador que faltaba, subió el contrato a **v1.2.0** y **cierra H-42, H-43 y H-44**.
  * Pasos 8 a 10 — Despertador, la voz del proceso silencioso y cierre de capa: 💤

---

## 🔧 Fase Activa: Auditoría Técnica y Remediación (pre-Capa 9)

> Auditoría integral realizada el **2026-07-27** sobre las Capas 1 a 8. Antes de abrir la Capa 9 se cierran los defectos bloqueantes detectados. Cada paso se valida con el usuario y se verifica con la suite completa antes de avanzar.
>
> 📄 **Evidencia y detalle de cada hallazgo: [`.agents/AUDITORIA_2026-07-27.md`](AUDITORIA_2026-07-27.md)** — la auditoría original catalogó 14 (H-01 a H-14); el dosier recoge hoy **los 36**, incluidos los que fueron apareciendo después al reparar, al arrancar la aplicación y al abrir la Capa 9. Cada uno con la forma de reproducirlo y la prueba de regresión que impide que vuelva. Consúltalo antes de rediagnosticar nada.

### Pasos completados

* **Paso A — Suite de pruebas en verde**: 🟢 Reparado `tests/test_centinela_cli.py` (faltaba `import os`). La suite pasa de 130/134 a **134/134**, recuperando la red de seguridad para el resto de la remediación.

* **Paso B — Unificación de la raíz de importación**: 🟢 Coexistían dos raíces (`from memoria import ...` y `from src.memoria import ...`), lo que cargaba el mismo fichero como **dos objetos-módulo distintos**. Consecuencia real: `python src/main.py` mataba la Capa 6 en silencio (`ModuleNotFoundError: No module named 'src'`, absorbido por un `except` amplio) y `python -m src.main` fallaba al arrancar. No existía ninguna forma correcta de ejecutar el pipeline.
  * Creado `src/__init__.py` y `run.py` como punto de entrada único.
  * Eliminados los 35 imports planos y los 10 bloques `try/except ModuleNotFoundError` en `src/` y `tests/`.

* **Paso C1 — Contrato honesto de Modo Degradado**: 🟢 Un fallo de parseo de la respuesta del LLM se persistía como análisis `COMPLETADO` con todos los campos de riesgo a `False`, y el Cockpit lo mostraba como *"Sin subrogación · Sin revisión de precios"* sobre un pliego que nunca se leyó.
  * `AnalisisSemanticoDTO` sube a **esquema v2** con campo explícito `modo_degradado`.
  * `from_json(estricto=True|False)`: valida la **forma** del esquema, no sólo que sea JSON. Un esquema inválido conmuta de proveedor en vez de darse por bueno.
  * El Recalibrador deja de inferir la degradación por heurística de cadena sobre el resumen ejecutivo.
  * Cockpit: aviso explícito en ficha, atenuación de las tarjetas de cláusulas y distintivo *"Pliego sin analizar"* en la tabla.
  * 3 pruebas de regresión nuevas. Suite: **137/137**.

* **Paso C3 — Robustez de la API ante datos imperfectos**: 🟢 El DDL declara con `DEFAULT` pero sin `NOT NULL` columnas que los esquemas Pydantic modelan como obligatorias (`organo`, `fuente`, `titulo_lote`, `pbl`, `estado_operativo`...). Un `DEFAULT` de SQLite no impide almacenar un NULL explícito, y Pydantic rechaza `None` aunque el campo tenga valor por defecto. Un único expediente con `organo` a NULL devolvía 503 en su ficha y **tumbaba la página entera del funnel**.
  * Tolerancia a NULL en la frontera de lectura mediante `model_validator(mode="before")` en `LicitacionSchema`, `LoteSchema` y `AlertaBoletinSchema`, acotada **exclusivamente** a las columnas que el DDL permite dejar vacías. Verificado que `id` nulo y los tipos incorrectos se siguen rechazando: la validación se ha estrechado, no debilitado.
  * Validación fila a fila en ambos listados: un registro corrupto se descarta, se audita en JSONL (`API_LICITACIONES_ROWS_SKIPPED`) y **no invalida el resto de la página**.
  * Criterio adoptado: la integridad se exige al escribir, no al leer. Un dato incompleto se degrada; nunca rompe la pantalla.
  * 3 pruebas de regresión nuevas en `tests/test_api_tolerancia_nulos.py`. Suite: **140/140**.

* **Paso C2 (parte 2 de 2) — Proveedores LLM, Centinela y Resiliencia**: 🟢 Reparada la factoría `proveedor_llm_factory()` en `src/analista.py`, actualizada la llamada `.consultar()` en `AnalistaBoletinesIA` (`src/centinela.py`) e implementados reintentos exponenciales con Gemini Lite/Flash fijados en `config/analista_config.yaml`. Añadida prueba unitaria real `tests/test_centinela_llm_factory.py` (Convención C4). Suite: **143/143**.

* **Bloque 1 — Cimientos para Capas 9 y 10**: 🟢 `busy_timeout` de 30 s en SQLite (antes 5 s por defecto: la API devolvía 503 bajo escritura concurrente); modo WAL; TTL de 600 s y verificación de PID en el lock de fichero; ruta absoluta para la BD; `fastapi`/`uvicorn`/`pydantic` declarados en `requirements.txt`; `.gitignore`, `.env.example` y `strict` en TypeScript.
  * Normalización de rutas completada en el Paso D3 (ver abajo): ya no hace falta que el lanzador VBS de la Capa 10 fije el directorio de trabajo.

* **Bloque 2 — Coherencia de negocio LCSP**: 🟢 Implementado el 2026-08-06 y verificado con `tests/test_bloque2_coherencia.py` y `tests/test_recalibrador_scoring.py`. Escala canónica `[0, 100]` con `score_bruto` separado (H-09); la señal textual preliminar deja de mover el score y el `ajuste_score` del LLM se registra pero no se aplica, eliminando la doble penalización (H-11); detección que respeta las negaciones (H-10); DTO v3 con garantía definitiva (arts. 107-108), penalidades (arts. 192-194) y cláusulas sociales (art. 202) (H-12); `lote_numero` en el contrato de mutación, extremo a extremo (H-13); KPIs sobre una única población (H-08). **Art. 145 resuelto a favor del README**: un peso de precio/fórmulas superior al 60 % penaliza −10 pts; el predominio del juicio de valor no se penaliza.

* **Paso D1 — Cerrojo de fichero resiliente en Windows** (2026-08-06): 🟢 Dos bloqueos permanentes en `db_lock` (H-15). La reclamación de cerrojos huérfanos nunca se ejecutaba en Windows porque el `os.remove()` se hacía con el fichero aún abierto (`WinError 32`), silenciado por un `except` amplio: la protección TTL+PID del Bloque 1 no funcionaba en la plataforma de destino. Y un cerrojo de 0 bytes —proceso muerto entre crear el fichero y escribir el payload— no caducaba nunca. Ahora la lectura vive en `_motivo_lock_huerfano()`, que decide con el fichero cerrado, y un cerrojo ilegible caduca por su fecha de modificación. Emite `DB_LOCK_HUERFANO_RECLAMADO` en `data/pipeline.jsonl`. Suite: 156/156.

* **Paso D2 — Contrato honesto de Modo Degradado en el Centinela** (2026-08-06): 🟢 Aplica a la Capa 6 lo que el Paso C1 hizo en la Capa 5 (H-16). `DictamenCentinelaDTO` sube a esquema v2 con `modo_degradado`; `from_json(estricto=True)` valida la forma y un `{}` deja de deserializar como veredicto; nuevo `nivel_interes="DESCONOCIDO"`; el evaluador conserva el score de reglas duras sin inferir interés. La suite deja de llamar a Gemini (H-17) mediante `autoinicializar_proveedor=False`. Suite: **159/159**, verificada hermética.

* **Paso D3 — Toda ruta se ancla a la raíz del proyecto** (2026-08-06): 🟢 `config/` y `data/` se resolvían contra el directorio de trabajo (H-18). No fallaba: **decidía distinto**. Sin encontrar `config/perfil_incoop.yaml`, el perfil comercial se cargaba vacío y el sistema continuaba en silencio con los valores por defecto. Medido sobre la misma licitación: **71 puntos desde la raíz, 47 desde otra carpeta**, con el umbral de recomendación en 65. `PROJECT_ROOT` y `ruta_proyecto()` se centralizan en `src/__init__.py`; las rutas absolutas se respetan intactas para que las pruebas puedan seguir inyectando rutas temporales. Regresión en `tests/test_rutas_proyecto.py`. Suite: **163/163**.

* **Paso D4 — Criterios comerciales de subrogación** (2026-08-06): 🟢 Dos decisiones de negocio validadas por la dirección. La falta de la relación de personal del Art. 130.1 pasa de CRÍTICO a ALTO: elevaba el riesgo al máximo y descartaba automáticamente, cuando el desglose suele obtenerse pidiéndolo al órgano de contratación. Al bajarla hubo que **reordenar la matriz**, porque como se aplica la primera regla que encaja, el peor caso (200 trabajadores sin desglose) habría puntuado mejor que el segundo peor (41 documentados): ahora el tamaño determina el veto y la documentación determina el nivel. Y nueva bonificación `subrogacion_baja_documentada` (+2 pts) para la subrogación de 1 a 5 personas con desglose, que antes sumaba 0 igual que el tramo MEDIO. Actualizado el ejemplo *few-shot* que enseñaba la regla anterior.

* **Paso D5 — Rastro de las alertas descartadas y blindaje del criterio humano** (2026-08-06): 🟢 Las alertas que no alcanzan el umbral se persisten en vez de desaparecer (H-20); las consultas de listado las excluyen del canal principal salvo que se pidan expresamente. Al persistirlas afloraron dos defectos latentes: `DESCARTADA_POR_REGLAS` no figuraba en `ESTADOS_BOLETIN_VALIDOS` —el evaluador emitía un estado que su propio DTO rechazaba, invisible porque esas filas nunca se escribían— y el UPSERT no blindaba `DESCARTADA_TEMPRANA`, de modo que una reejecución del pipeline **pisaba el descarte decidido por una persona**. Los dos estados se mantienen distintos a propósito: si se baja un umbral procede reevaluar lo que descartó la máquina, nunca lo que rechazó alguien.

* **Paso D6 — H-06 cerrado, y la herramienta que lo mantenía abierto** (2026-08-06): 🟢 `tools/verificar_proveedor_llm.py` leía la clave `gemini.modelo`, **que no existe en el fichero de configuración**: la búsqueda caía en silencio a un valor codificado `gemini-2.0-flash` y la herramienta llevaba desde julio informando de un 429 sobre un modelo ya sustituido. Por eso H-06 parecía no cerrarse nunca (H-19). Corregida para replicar la lectura de `proveedor_llm_factory()` y ampliada para probar también el modelo de respaldo. Verificación real: `gemini-3.1-flash-lite` **7/7** campos correctos en 1,9 s, respaldo `gemini-3.6-flash` correcto, y matriz de subrogación **5/5 determinista** entre dos familias de modelo distintas.

* **Paso D7 — El middleware deja de bloquear el bucle de eventos** (2026-08-06): 🟢 `registrar_evento()` hacía E/S de fichero síncrona dentro de un `async def`: mientras se escribía en `pipeline.jsonl`, la API no podía atender ninguna otra petición. Delegado a un hilo con `run_in_threadpool`.

* **Paso D8 — Lo que sólo se ve arrancando la aplicación** (2026-08-06): 🟢 Tres defectos (H-21, H-22, H-23) detectados al levantar la API y el Cockpit contra la base de datos real, con la suite en verde y los 20 hallazgos anteriores ya cerrados. Ninguno rompía nada: los tres **mentían en pantalla**. El KPI de cabecera anunciaba "51 Expedientes" sobre un desglose de 22 lotes; el Funnel listaba los 29 expedientes archivados como filas fantasma de "0 € y 0 pts" por un `LEFT JOIN` que debía ser `JOIN`, una de ellas con un score de 115 de la escala antigua; y la columna de cláusulas afirmaba "Sin Subrog. · Sin Revisión" tanto en los 21 pliegos que nadie había analizado como —peor— en el único analizado, **contradiciendo un análisis que sí había encontrado ambas cosas**. Regresiones en `tests/test_bloque2_coherencia.py`. Suite: **173/173**.

* **Paso D9 — El Cockpit da acceso a lo descartado** (2026-08-06): 🟢 Nuevo filtro *"Descartada por Reglas (auditoría)"* en el canal Centinela: es el único acceso desde la interfaz a lo que el pipeline descartó por no alcanzar el umbral, y la vista que hay que revisar tras bajar un umbral o actualizar los PMP. El estado **no** se ofrece en el selector de cada fila —si descarta una persona, es `DESCARTADA_TEMPRANA`—, pero sí se muestra cuando la alerta ya lo tiene, o el selector saldría en blanco; desde ahí se rescata llevándola a un estado humano. Verificado en vivo contra una base sembrada: rescate de una alerta descartada a `EN_ESTUDIO_PROACTIVO`, que persiste. Suite: **174/174**.

* **Paso D10 — Borrado de la beta y lo que destapó** (2026-08-06): 🟢 Vaciados los datos de prueba a petición de la dirección. Arrancar desde cero absoluto reveló que **un clon limpio del repositorio no podía iniciar el sistema** (H-24): `data/` está excluida de Git y `setup_db()` creaba el cerrojo antes de que existiera el directorio. Y al comprobar que el estado limpio se mantenía, apareció que **la suite escribía en el `data/` real** —con datos dentro, habría tocado la base de producción— y que **seguía llamando a Gemini** pese a haberse declarado hermética en el Paso D2 (H-25). Nueva función `ruta_datos()` con reubicación por `DATA_DIR_INCOOP`, y `tests/conftest.py` que la redirige al importarse. Suite: **175/175**, sin contactar ningún dominio externo y sin crear `data/`.

* **Paso D11 — El sector que nunca se asignaba** (2026-08-07): 🟢 Apareció al retomar la pregunta aplazada sobre la cobertura de CPVs (H-26). Toda la familia `853*` —asistencia social, el núcleo del negocio— se etiquetaba como `Educativo`: el sector `educativo` declara `85312110` ("Guarderías escolares sociales"), cuyo prefijo de 3 dígitos es la rama social entera del CPV, y la asignación se quedaba con el primer sector del YAML que casara cualquier prefijo. **El sector `social` no se asignaba jamás.** No alteraba el score —+40 por cualquiera de los dos— y por eso ni la suite ni el arranque en vivo del Paso D8 lo vieron; alteraba `sector_detectado`, que se persiste. Las dos correcciones aparentemente obvias resultaron inservibles al medirlas: el prefijo de **5** dígitos también está compartido (`85312`), así que "sólo 5 dígitos" y "gana el prefijo más largo" se quedaban en 5 aciertos de 9 y seguían fallando los centros de día. La solución es resolver por **código completo primero**, cayendo al prefijo sólo si no hay coincidencia exacta, con una **prelación entre sectores declarada** en `perfil_incoop.yaml` para los empates. Verificado en vivo contra una base sembrada, recorriendo Filtro → SQLite → API. Suite: **196/196**.

### Pasos pendientes

De la remediación, ninguno. **48 hallazgos catalogados, 44 cerrados** con prueba de regresión o verificación reproducible. Los diez de H-27 a H-36 no salieron de la remediación sino de abrir la Capa 9, y se cerraron dentro de sus Pasos 3, 4, 5 y 10. Los cuatro últimos salieron de la Capa 10: **H-37** de redactar su contrato (cerrado en el Paso 2), **H-38** de escribir su configuración (Paso 3), **H-39** de verificar en vivo su supervisor (**abierto**, previsto para el Paso 9) y **H-40** de preparar su Paso 6 (cerrado allí mismo).

> **El patrón se repite y conviene tenerlo presente en lo que queda**: ninguno de estos cuatro apareció leyendo código ni con la suite en verde. Salieron de **escribir el contrato, escribir la configuración, arrancar la aplicación y ponerse a implementar**. Es la misma lección que dejaron H-21, H-22 y H-23 en el Paso D8.

**Los datos de la beta se borraron el 2026-08-06** a petición de la dirección del proyecto: la base, los documentos descargados, los registros y los informes. El sistema queda como una instalación nueva. Los registros de julio no eran información comercial —10 de 22 lotes tenían el plazo vencido y todos estaban puntuados con la lógica anterior al Bloque 2—, y conservarlos habría mezclado dos generaciones de puntuación en la misma tabla.
