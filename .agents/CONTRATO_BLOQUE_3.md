# Contrato de Servicio — Bloque 3: Identidad y Foco

**Versión**: v1.0.0 · **Redactado**: 2026-08-19 · **Estado**: 🟢 validado el 2026-08-19 · **Pasos 2, 3 y 4 hechos**, Paso 5 es la tarea siguiente
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

---

## G · Plan de ejecución en 7 pasos

| Paso | Qué hace | Cómo se verifica |
|---|---|---|
| **1** | Este contrato | Validación de dirección |
| **2** | 🟢 **Hecho el 2026-08-19.** `titulo_legible()` en `src/__init__.py`, campo computado `titulo_corto` en la API junto al `titulo` íntegro, y el informe CSV usando la misma función | **518/518** (17 regresiones nuevas). Sobre los 68 títulos reales: máximo **1.663 → 200**, ninguno por encima del tope, **47 llegan enteros** y **0 palabras partidas**. Comprobado también contra la API levantada |
| **3** | 🟢 **Hecho el 2026-08-19.** Paleta de tres capas en `index.css` (`@theme`), **463 clases migradas** por mapa explícito, cabecera con el isotipo, y App en fondo `#0E0D14` | Navegador real: **0 fallos de contraste** en las cuatro pantallas y en la ficha, 0 errores de consola, ningún fondo claro superviviente. Suite **518/518** |
| **4** | 🟢 **Hecho el 2026-08-19.** La columna de identificador desaparece y su ancho pasa al título; el id baja a pie de fila; el score se lee como magnitud con el acento reservado a la prioridad **Alta**; el sector se pinta por fin | Navegador real: 6 columnas en vez de 7, título a 15 px en 3 líneas con el completo en el tooltip, **0 fallos de contraste**. Suite **518/518** |
| **5** | El ámbito: parámetro, KPIs e interruptor | Suite + comprobado contra la base real |
| **6** | El análisis visible, con sus tres estados | Navegador real sobre expedientes con y sin análisis |
| **7** | Cierre: suite completa, C7 con la aplicación arrancada, documentos al día | 501/501 más lo nuevo |

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
