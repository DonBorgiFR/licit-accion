# Contrato de Servicio — Bloque 3: Identidad y Foco

**Versión**: v1.0.0 · **Redactado**: 2026-08-19 · **Estado**: 🟢 **CERRADO el 2026-08-19**, sus siete pasos
**Origen**: revisión funcional con dirección del 2026-08-18 · **Precede a**: Capa 10, Paso 8

> **Qué persigue este bloque.** Nueve capas se han invertido en que el motor sea honesto; ninguna
> en que el resultado sea reconocible para quien lo usa. Dirección lo dijo así: *"con todo el
> proyectazo que nos hemos mandado, que se vea tan mediocre me disgusta"*. Detrás de esa frase hay
> cuatro cosas medibles, no una impresión.
>
> **Lo que este bloque NO es**: rehacer la Capa 8. El Cockpit funciona y sus datos son correctos.
> Y **no reabre el motor**: scoring, perfil comercial y fuentes se quedan como están.

---

## A · Decisiones ya tomadas, que no se vuelven a plantear

| Asunto | Decisión | Cuándo |
|---|---|---|
| Fondo | **Oscuro en toda la pantalla**, no sólo la cabecera | 2026-08-19 |
| Paleta | Los cinco colores de la marca en **tres capas**: marca, semántica y neutros | 2026-08-19 |
| Ámbito | **Se filtra en pantalla**, Catalunya por defecto, interruptor para el resto. No se toca la ingesta ni el scoring | 2026-08-18 |
| Alcance del interruptor | Gobierna **el Funnel y los KPIs a la vez** | 2026-08-19 |
| Título | Párrafo → primera frase → tope **200**, **sin cortar palabras** | 2026-08-19 |
| Logo | `Incoop-logo.png` (letras negras) para fondo claro e informes; el de letras blancas para la cabecera oscura | 2026-08-19 |

**La medición que sostiene el fondo oscuro**, para que nadie la repita: extraídos los cinco colores
exactos del logotipo, sobre blanco **sólo 2 de 5** superan el umbral de contraste 3:1 que la norma
exige a un elemento gráfico; sobre `#0E0D14`, **los 5**. La cabecera blanca no es que quedara sosa:
**obligaba a no usar la marca**, y por eso acabó allí un icono genérico de edificio en un degradado
índigo que no sale de ninguna parte.

| | Cian `#26B8DB` | Violeta `#6056A2` | Amarillo `#FFD932` | Rojo `#CF4C39` | Verde `#5ABA5A` |
|---|---|---|---|---|---|
| Sobre blanco | ✗ 2,34 | ✓ 6,27 | ✗ 1,38 | ✓ 4,42 | ✗ 2,44 |
| Sobre `#0E0D14` | ✓ 8,25 | ✓ 3,08 | ✓ 14,01 | ✓ 4,37 | ✓ 7,92 |

---

## B · El título legible (Regla 4)

**Dos problemas distintos con el mismo síntoma**, y confundirlos lleva a arreglar el que no es:

* **De presentación**: la tabla recorta a dos líneas en una columna estrecha.
* **De datos**: la fuente vuelca el anuncio entero en el campo. El título más largo mide **1.663
  caracteres** y su título real son las primeras veinte palabras.

### La regla

Se aplican en orden y se para en el primero que deja algo legible:

1. **Cortar en el primer salto de párrafo.** Separa el título del cuerpo del anuncio.
2. **Cortar en la primera frase**, exigiendo punto + espacio + mayúscula y un mínimo de 30
   caracteres para no partir por una abreviatura.
3. **Tope de 200 caracteres en frontera de palabra**, con puntos suspensivos.

**Por qué 200 y no 120**, medido sobre los 63 expedientes ya aplicados párrafo y frase:

| Tope | Llegan enteros |
|---|---|
| 120 | 27 de 63 · 43 % |
| 160 | 37 de 63 · 59 % |
| **200** | **48 de 63 · 76 %** |
| 240 | 52 de 63 · 83 % |

Con 120 se recortaría el 57 %, y muchos de esos **ya eran títulos correctos**: los de 125-135
caracteres son títulos de licitación normales y completos. Con 200 el tope sólo alcanza a los
quince desbocados, que es su oficio. **Comprobado: 0 palabras partidas.**

### Dónde vive

> ⚠️ **Cambio respecto a lo que recomendé el 2026-08-19 por la mañana.** Propuse **persistir** el
> título derivado en una columna nueva con esquema v9, migración y backfill. **Retiro esa
> recomendación**: se deriva **al leer**, desde una única función compartida.
>
> Los dos motivos que la miden: *(1)* la regla **se va a tener que afinar** cuando dirección la vea
> sobre datos reales, y con columna persistida cada retoque exige rebackfillar los 63 —con
> derivación al leer, un retoque es un cambio de código y ya—; *(2)* **no hay nada que la columna
> aporte**: la búsqueda del Funnel debe seguir operando sobre el título completo *(se encuentra una
> licitación por una palabra del cuerpo, que es lo deseable)*, y derivar 200 caracteres para las
> filas de una página es coste despreciable. Una migración de esquema por un dato que nadie
> consultaría desde la base es pagar por nada. **La versión se declara igual** (`VERSION_TITULO`),
> que es lo que la Regla 4 pide.

* **Función**: `titulo_legible(titulo: str) -> str` en `src/`, punto único.
* **Consumidores**: el esquema de la API (campo nuevo `titulo_corto`, junto al `titulo` completo,
  que **no se toca**) y el informe CSV del Analista.
* **Postcondición**: el campo `titulo` original **nunca se modifica**. El texto completo sigue
  íntegro en la base y visible en la ficha de detalle.
* **Versionado**: `VERSION_TITULO = "1.0.0"`.

---

## C · Las tres capas de color

El diagnóstico de dirección —*"todo pesa lo mismo, así que nada destaca"*— **no se arregla añadiendo
color: se arregla quitándolo.** Hoy cada dato de la tabla viaja dentro de una píldora de color, así
que ninguna destaca.

| Capa | Colores | Oficio | Prohibido |
|---|---|---|---|
| **Marca** | Los cinco pétalos | Identidad —cabecera, logotipo— y **categoría**: fuente, sector | Significar «bien» o «mal» |
| **Semántica** | Tres, y deliberadamente más apagados que la marca | Alarma, atención, conforme. **Sólo cuando algo exige actuar** | Usar un tono de la marca |
| **Neutros** | Escala sesgada hacia el violeta de la marca | El 90 % de la pantalla; carga la jerarquía con tamaño, peso y tono | Ser un gris de fábrica |

**Por qué la semántica no puede reutilizar la marca**: el rojo teja es un pétalo del logotipo *y*
sería el color de riesgo. Un aviso de subrogación crítica y un distintivo de categoría pintados del
mismo color hacen que la pantalla mienta sobre qué es urgente.

> 🔑 **Y lo que al medirlo resultó no bastar: separarlas por tono es imposible.** Los semánticos
> quedan a **1-5 grados de tono** de los pétalos —rojo alarma contra rojo teja, ámbar contra
> amarillo—, así que como puntos de color serían indistinguibles por mucho que se elijan bien. Rojo
> es rojo. **Lo que las separa es la forma, y esa es la regla del sistema:**
>
> * Un **punto** de color significa siempre **categoría**.
> * Un **estado** lleva siempre **palabra**, y nunca es un punto suelto.
>
> Lo que no lleva texto al lado no es una advertencia. Queda escrito en la cabecera de
> `frontend/src/index.css`, que es donde lo verá quien vaya a añadir un color.

---

## D · La jerarquía de la tabla

**El cambio que más resuelve del bloque, y no cuesta ni un dato nuevo.** Hoy la columna principal es
el identificador del expediente en negrita y el título va debajo, pequeño y recortado a dos líneas.
Pero el identificador que manda la fuente puede ser `CONTR 2026 0000156087`. **Se está destacando lo
ilegible y escondiendo lo legible.**

1. El **título** sube a primera línea y a cuerpo de titular.
2. El **identificador** baja a pie de línea, en tipo monoespaciada pequeña.
3. El **score** se lee como magnitud —cifra grande y barra— en neutro, y el acento se reserva a la
   prioridad **Alta**. *(Precisado al implementarlo: el contrato decía «sólo se pinta el que
   encabeza», pero encabezar la página es un accidente de lo que hay en pantalla. `prioridad` es un
   juicio que el Filtro ya emite, así que destacar por ella dice algo del negocio y no del listado.)*
   Antes el score pintaba verde sobre 70, ámbar sobre 45 y rojo por debajo: **eso mentía**, porque
   un 40 no es un peligro sino una oportunidad que encaja poco.
4. El **sector** aparece por fin: se calcula, se persiste y se sirve desde la Capa 5, y **no lo
   pinta ninguna pantalla**. Cierra la cuestión de diseño que `ESTADO.md` tenía abierta.

---

## E · El ámbito (H-47)

* **Criterio**: `nuts LIKE 'ES51%'`. **Medido: `nuts` está poblado en 63 de 63**, sin un solo nulo —
  frente a `localidad`, que trae `N/A` en la mitad de las filas.
* **API**: parámetro nuevo `ambito` en `/licitaciones`, siguiendo la convención de
  `incluir_archivadas`. Y en los KPIs, que se calculan en `Memoria.obtener_resumen_kpis()`.
* **El Centinela no lo lleva**: DOGC y BOPB ya son catalanes de origen.

> 🔑 **Dónde vive el «por defecto», y por qué no en la API.** El parámetro llega a la API **sin
> valor por defecto**: sin pedirlo, la API devuelve todo. Quien decide mostrar sólo Catalunya es la
> pantalla, con el interruptor puesto de inicio. Es lo contrario que `incluir_archivadas`, y a
> propósito: lo archivado es un **concepto de negocio** —qué está en el canal principal—, mientras
> el ámbito es una **preferencia de quien mira**. Una API que esconde por gusto propio acaba
> produciendo la clase de sorpresa que este proyecto lleva cuatro capas persiguiendo.

> ⚠️ **Precisado al implementarlo (2026-08-19): qué KPIs obedecen, y qué pasa con un ámbito mal
> escrito.** El contrato decía «y en los KPIs» sin decir cuáles. **Obedecen todos los que salen de
> un expediente**, win rate y avales incluidos: dejar la memoria comercial global mientras el
> volumen licitado baja a la fracción catalana sería mezclar dos poblaciones en la misma pantalla,
> que es H-08 y H-21 otra vez. Como `vista_win_rate` es un agregado global sin `expediente_id`, la
> consulta filtrada y la vista **comparten ahora la constante `SQL_COLUMNAS_WIN_RATE`**, para que
> no existan dos definiciones de «ganada». Y el vocabulario de ámbitos es **cerrado**: un valor no
> reconocido devuelve **400**, nunca la población entera bajo el rótulo equivocado (Convención C2).
>
> Dos datos que sólo aparecieron al medir: **`ES51` existe en la base sin el quinto dígito** (4
> expedientes), así que el criterio tiene que ser un prefijo y no una igualdad contra las cuatro
> provincias — familia de H-49; y **`nuts` está poblado en 74 de 74** filas, confirmado.

**Efecto que conviene ver escrito**: con el filtro puesto, el Funnel enseñará una fracción de lo
que hay. **Es lo correcto y era el objetivo** — pasar de parecer lleno y ajeno a parecer pertinente.

---

## F · El análisis semántico visible

Funciona desde la Capa 5 y queda enterrado en la ficha de detalle. Tanto, que dirección llegó a
creer que había que ejecutarlo a mano con un `.py` — eso es la herramienta de inspección, no el
motor.

**Tres estados a la vista en la tabla**, y ni uno más:

| Estado | Qué significa |
|---|---|
| **Pliego leído** | Hay análisis completo. Los riesgos que muestra la fila son de verdad |
| **Sin analizar** | No hay pliego o no se ha procesado. **La fila no afirma ausencia de riesgos** |
| **Lectura degradada** | Se intentó y el dictamen no es fiable (contrato de Modo Degradado, Paso C1) |

> ⚠️ **Lo que esto va a destapar, y hay que decirlo antes de hacerlo.** De los expedientes vivos, la
> mayoría no tiene el pliego leído — porque el pliego depende de que la fuente traiga sus enlaces, y
> sólo la fuente catalana lo hace de forma fiable (16 de 16, frente al 63 % del PCSP y el 25 % de
> las CCAA). Hacerlo visible mostrará *"sin analizar"* en muchas filas. **Es honesto y es
> deseable**: hoy esas filas callan, que es peor. Pero no es un fallo del bloque, es su hallazgo.

> ✅ **Medido al implementarlo (2026-08-19), y sale mejor de lo previsto.** De los 24 expedientes
> vivos, **11 tienen el pliego leído y 13 no**; pero con el filtro de ámbito puesto —que es lo que
> el usuario ve al abrir— son **7 de 9**. La razón es la misma que anticipaba el aviso: la fuente
> catalana trae los pliegos y las estatales no, así que filtrar a Catalunya y ver el pliego leído
> resultan ser el mismo fenómeno visto por dos lados. **No hay ni una lectura degradada** en la
> base real, así que ese tercer estado se verificó sembrándolo en una **copia**.

> ⚠️ **Precisado al implementarlo: eran dos estados fundidos, no un distintivo que faltaba.** La
> pantalla manejaba «hay análisis» y «no hay análisis fiable», juntando *no se intentó* con *se
> intentó y salió mal* bajo la misma etiqueta —«Pliego sin analizar»—, que a la segunda le miente.
> Y el positivo no existía. Además la clasificación estaba escrita **dos veces** en el Cockpit, que
> no tiene suite: se traslada al servidor (`estado_lectura_pliego()`, campo computado
> `estado_lectura`) para que quede cubierta por regresiones. Un `estado_analisis` desconocido se
> clasifica como **degradado y nunca como leído** (C6); `PENDIENTE` es «sin analizar», porque es la
> cola con la que el pipeline selecciona trabajo y no un dictamen fallido.

> 🔑 **Y un hallazgo que este apartado dio por explicado y no lo estaba (H-50).** El contrato decía
> que *"dirección llegó a creer que había que ejecutarlo a mano con un `.py`"* como si fuera un
> malentendido. **Se lo estaba diciendo la ficha de detalle**, literalmente: *"Puedes ejecutar el
> motor en CLI con `python src/analista.py`"*. Y ese comando **no arranca** —rompe la Convención
> C1—. Una creencia equivocada del usuario puede ser un defecto del producto.

---

## G · Plan de ejecución en 7 pasos

| Paso | Qué hace | Cómo se verifica |
|---|---|---|
| **1** | Este contrato | Validación de dirección |
| **2** | 🟢 **Hecho el 2026-08-19.** `titulo_legible()` en `src/__init__.py`, campo computado `titulo_corto` en la API junto al `titulo` íntegro, y el informe CSV usando la misma función | **518/518** (17 regresiones nuevas). Sobre los 68 títulos reales: máximo **1.663 → 200**, ninguno por encima del tope, **47 llegan enteros** y **0 palabras partidas**. Comprobado también contra la API levantada |
| **3** | 🟢 **Hecho el 2026-08-19.** Paleta de tres capas en `index.css` (`@theme`), **463 clases migradas** por mapa explícito, cabecera con el isotipo, y App en fondo `#0E0D14` | Navegador real: **0 fallos de contraste** en las cuatro pantallas y en la ficha, 0 errores de consola, ningún fondo claro superviviente. Suite **518/518** |
| **4** | 🟢 **Hecho el 2026-08-19.** La columna de identificador desaparece y su ancho pasa al título; el id baja a pie de fila; el score se lee como magnitud con el acento reservado a la prioridad **Alta**; el sector se pinta por fin | Navegador real: 6 columnas en vez de 7, título a 15 px en 3 líneas con el completo en el tooltip, **0 fallos de contraste**. Suite **518/518** |
| **5** | 🟢 **Hecho el 2026-08-19. Cierra H-47.** Criterio único y versionado en `src/__init__.py` (`AMBITOS`, `clausula_ambito()`, `VERSION_AMBITO`), consumido por el Funnel y por los KPIs; parámetro `ambito` en `/licitaciones` y `/kpis`; interruptor en barra propia bajo la cabecera, fuera de las dos pestañas que gobierna | Suite **538/538** (20 regresiones nuevas). Contra la base real: **24 → 9 expedientes** y **7.294.613,49 € → 2.770.211,81 €**, con la cabecera cuadrando con su desglose en los dos estados. 0 errores de consola y 0 fallos de contraste en la barra nueva |
| **6** | 🟢 **Hecho el 2026-08-19. Cierra H-50.** `estado_lectura_pliego()` y `VERSION_LECTURA` en `src/__init__.py`, servidos como campo computado `estado_lectura`; el Cockpit los pinta encabezando la columna de Cláusulas & Riesgo y en la ficha, desde un componente único. Corregido el texto que recomendaba un comando roto | Navegador real con los **tres estados a la vez**: 7 «Pliego leído» y 2 «Sin analizar» de la base real, más una «Lectura degradada» sembrada en una copia, con su causa a la vista. 0 errores de consola, contraste 8,08 / 7,20 / 10,01. Suite **552/552** (14 regresiones nuevas) |
| **7** | 🟢 **Hecho el 2026-08-19. Cierra H-51.** Auditoría C7 sobre **las cuatro pantallas y la ficha**, no sólo sobre lo tocado; corregido el Total de ocupación en disco, que tenía un sumando invisible; documentos y acta al día | Suite **553/553**. **0 fallos de contraste** en las cuatro pantallas con el auditor rehecho, 0 errores de consola, 0 peticiones fallidas. Las cuatro promesas del apartado H, comprobadas una a una |

**El orden no es arbitrario**: el Paso 2 es el único que toca datos, y todo lo demás los muestra.
Los Pasos 3 a 6 son de pantalla y se verifican mirándola, no sólo con la suite — que es la lección
que este proyecto lleva repitiendo desde H-21.

**Riesgo principal**: el fondo oscuro toca los ocho componentes del Cockpit (2.725 líneas). La
mitigación es hacerlo **por tokens y no por componente** —se define la paleta una vez y los
componentes la consumen—, y verificar en el navegador tras cada paso. Si un paso obliga a rehacer
la lógica de un componente y no sólo su color, **el alcance se ha desbordado y hay que parar**.

---

## H · Qué se espera ver al terminar

* Que alguien que abra el Cockpit **reconozca a Incoop** antes de leer nada.
* Que **se puedan leer los títulos** de las licitaciones, y que en la ficha siga estando el texto
  completo.
* Que el Funnel enseñe **lo que es de su ámbito**, con el resto a un clic.
* Que el trabajo del Analista **se vea** — y que cuando no lo haya, se diga.

### ✅ Comprobado en el cierre (2026-08-19)

| Lo prometido | Cómo se comprobó |
|---|---|
| Reconocer a Incoop | Isotipo, marca compuesta con texto y las cinco tintas sobre `#0E0D14`. Ningún fondo claro superviviente: los tres que detecta el barrido son los puntos de sector de 6 px, que es su oficio |
| Leer los títulos | **188 caracteres en la tabla, 1.663 en el tooltip y en la ficha.** El campo `titulo` nunca se modificó |
| El Funnel de su ámbito | 9 de 24 con Catalunya puesta, y la cifra de cabecera cuadrando con su desglose en **los dos** estados del interruptor |
| Ver el trabajo del Analista | 7 «Pliego leído» y 2 «Sin analizar» sobre la base real; la «Lectura degradada» probada sembrándola en una **copia**, con su causa a la vista |

> ⚠️ **Lo que el cierre encontró, porque mirar la pantalla sigue siendo lo que encuentra cosas.**
> *(1)* **H-51**: el Total de ocupación en disco no cuadraba con su desglose —206,2 visibles bajo un
> total de 207,1—, porque los `registros_bytes` viajaban en la respuesta y no se pintaban.
> Reparado. *(2)* El acta daba la base en 68 expedientes y 18 vivos; son **74 y 24**. *(3)* El
> contraste del token separador se anotó en 2,64 y es **2,45**: se midió contra el fondo de página
> y el separador vive sobre la tarjeta — **el mismo error que el Paso 3 había documentado un paso
> antes** para `ink-faint`. Escribir la lección no basta para no repetirla.
>
> Y una cuarta, sobre las herramientas: el auditor de contraste dio un fallo imposible de 1,17
> sobre un texto perfectamente legible. **El defecto era del auditor**: Tailwind v4 devuelve los
> colores en `oklab` y el script los leía como RGB. Rehecho con conversión oklab→sRGB y composición
> por capas, las cuatro pantallas dan **0 fallos**. Una herramienta de verificación también es
> código sin revisar.
