# Apuntes para el Paso 10 — Cierre de la Capa 10 y del ecosistema

**Escritos el 2026-08-27**, al cerrar el Paso 9, por quien acababa de recorrerlo entero.

> **Qué es este documento y qué no.** **No es un plan** —el plan lo hará quien abra el paso, con
> dirección, y la Regla 8 exige que se valide antes de codificar—. Es lo que sabe hoy quien tiene
> el contexto fresco y mañana ya no estará: qué queda hecho de verdad, qué decisiones habrá que
> tomar, qué trampas hay puestas y qué **no** debe prometer el manual.
>
> **Léelo después de [`ESTADO.md`](ESTADO.md) y [`AGENTS.md`](AGENTS.md), no en su lugar.**

---

## A · Qué pide el Paso 10, y cuánto está ya hecho

El README lo define en tres piezas. **Una está casi entera y las otras dos no existen.**

| Pieza | Estado real |
|---|---|
| `tests/test_capa10_lanzador.py` con regresiones del arranque, reutilización y apagado | 🟡 **128 pruebas ya escritas** (Pasos 2 a 7). Falta lo **E2E**, no el fichero |
| **Verificación en vivo del doble clic** *(la que de verdad cierra la capa)* | 🔴 Sin hacer |
| **`MANUAL.md`**, el manual de operación | 🔴 No existe |

> 🔑 **Comprobado el 2026-08-27, y ahorra medio paso: las CINCO regresiones que el README pide
> para el Paso 10 ya existen entre las 128.** No hay que escribirlas; hay que **verificar que
> siguen cubriendo lo que el README dice** y, si acaso, completar los huecos.

| Lo que pide el README | Prueba que ya existe |
|---|---|
| Un healthcheck insatisfactorio impide arrancar | `test_el_espacio_insuficiente_impide_arrancar` |
| Una API viva se reutiliza en vez de duplicarse | `test_una_api_propia_viva_se_reutiliza_y_no_se_apaga_al_terminar` |
| El pipeline no se lanza con el cerrojo tomado | `test_una_corrida_viva_omite_la_prospeccion_con_codigo_propio` |
| El apagado no toca procesos ajenos ni confunde un PID reciclado | `test_el_apagado_no_toca_un_servidor_que_el_lanzador_no_encendio` · `test_un_pid_reciclado_no_se_confunde_con_el_nuestro` |
| **Sin sesión interactiva, ni un elemento gráfico** | `test_sin_sesion_interactiva_no_se_invoca_ni_un_elemento_grafico` |

**La consecuencia para planificar el paso es grande**: el trabajo real del Paso 10 **no son las
pruebas**, son **el manual y la verificación en vivo del doble clic**. Quien lo abra debería
confirmar esta tabla en cinco minutos y dedicar el paso a lo que de verdad falta.

---

## B · Las decisiones de dirección que habrá que plantear antes de escribir el manual

Ninguna es técnica y las cuatro cambian el documento entero. **Plantéalas al principio, con sus
alternativas, como se hizo con las tres del Paso 9** — funcionó.

**B.1 · ¿Para quién se escribe, exactamente?** El README dice *«para quien usa el sistema, que es
el lector para el que este proyecto todavía no ha escrito nada»*. Son **3 o 4 personas de la
cooperativa**. Falta saber si se asume que abren una terminal o no: **cambia radicalmente el
manual**. Si no la abren, medio contenido actual del proyecto no les sirve y hay que traducirlo a
«haz doble clic aquí y mira esto».

**B.2 · ¿En qué idioma?** La cooperativa es catalana, la documentación del proyecto está en
castellano y las fuentes oficiales publican en catalán. Nadie lo ha decidido nunca porque hasta
ahora no había un documento dirigido a personas de fuera del proyecto.

**B.3 · ¿Qué dice el manual del DOGC?** Está desactivado y **no por avería**: ya no publica en
formato consultable *(H-45, decisión del 2026-08-27)*. Hay que decidir si el manual lo presenta
como *«una fuente menos, definitivo»* o como *«apagada, pendiente de que la repongan»*. Lo
primero es más honesto; lo segundo, más esperanzado. No es lo mismo para quien lee.

**B.4 · ¿Qué dice el manual de lo que no funciona?** Hay **cinco hallazgos abiertos** (sección D),
y dos se le van a notar a quien use el sistema. Un manual que los calle es un manual que miente,
y es exactamente el defecto que la Capa 10 entera existe para combatir. Pero tampoco puede ser un
listado de averías que asuste. **Hay que decidir el tono y el sitio** — probablemente una sección
corta de *«lo que hoy no hace, y qué verás cuando pase»*.

---

## C · Lo que el manual tiene que contar, y que sólo se sabe midiendo

Está todo verificado sobre este equipo. **Que no se vuelva a deducir.**

### El despertador

* **Corre DENTRO de la sesión (`InteractiveToken`), no con la sesión cerrada.** Se diseñó sobre
  `S4U` y el Programador respondió `Acceso denegado`: la cuenta de este equipo es un usuario
  estándar. **Consecuencia práctica que el manual DEBE decir**: si el equipo está apagado o la
  sesión cerrada a la hora prevista, **esa noche no prospecta** — y lo recupera **en cuanto se
  entra**, por `StartWhenAvailable`. Es la pregunta nº 1 que hará cualquiera.
* **Está dada de alta en un solo equipo, y consta cuál: `AROMAN`.** Es deliberado *(mitigación de
  H-52)*. El otro equipo es `WIN-G87QEEBSUTH`.
* **Alta y baja**: `python tools/registrar_despertador.py`. Idempotente.
* **Tope de duración: 60 minutos.** Vive en `config/lanzador.yaml`. Al vencer, código `32`.

### Los códigos de salida

Ya están tabulados en [`CONTRATO_CAPA_10.md`](CONTRATO_CAPA_10.md), sección *Códigos de salida*.
**No los reinventes: tradúcelos.** El manual necesita la columna que el contrato no tiene —
**«¿qué hago yo si veo esto?»**. Los tres que verá una persona real:

| Código | Qué pasó | Qué hacer |
|---|---|---|
| `30` | No prospectó porque ya había otra corrida en marcha | Nada. Es la protección funcionando |
| `31` | El pipeline falló | Mirar el distintivo del Cockpit, que ya dice por qué *(Paso 9)* |
| `32` | Se colgó y se cortó al llegar al tope | Mirar **por qué no acababa**. Relacionado con H-41 |

### Duraciones reales, para que el manual no invente plazos

Las corridas medidas van de **36 s a 8,1 minutos**. Las tres de hoy: 63 s, 133 s y 44 s. Sirve
para escribir *«tarda un par de minutos»* sin mentir.

---

## D · Los cinco hallazgos abiertos, y cuáles se notan al usar

| Hallazgo | ¿Lo nota quien usa el sistema? |
|---|---|
| **H-56** · El análisis semántico del Centinela no ha funcionado nunca | **Sí.** Las alertas del canal Centinela **aparecen sin dictamen de IA**. El manual tiene que decirlo o parecerá que la pantalla está rota |
| **H-53 cara A** · Tesseract no está instalado | **Sí.** Un pliego escaneado no se lee. Se conserva y se recogerá solo el día que se instale |
| **H-55** · 14 líneas partidas en el registro, y sigue partiéndose | Poco. Sólo si alguien va a leer el registro |
| **H-41** · Crash nativo, **acotado**: ocurrió descargando el feed del DOGC | Raramente. Y **ojo**: el DOGC ya está desactivado, así que **conviene comprobar si H-41 sigue siendo reproducible** — puede que se haya caído solo |
| **H-52** · OneDrive como canal entre dos equipos | No, mientras el despertador siga en un solo equipo |

> 🔑 **H-41 merece una mirada antes de cerrar la capa.** Se localizó descargando el feed del DOGC,
> y ese feed ya no se descarga. Puede que el Paso 9 lo haya cerrado **de rebote**. Comprobarlo
> cuesta poco: mirar si vuelve a aparecer en corridas sucesivas. Sería una forma barata de bajar
> de cinco hallazgos abiertos a cuatro.

---

## E · Trampas concretas, ya pisadas

**Del entorno:**

* **La consola de Windows es cp1252.** Un solo carácter fuera de esa tabla —una flecha `→`—
  aborta la impresión a media herramienta. `verificar_rastro_real.py` ya se blindó con
  `sys.stdout.reconfigure(errors="replace")`; cópialo.
* **El Cockpit hay que recompilarlo** (`cd frontend && npm run build`) para que la API sirva los
  cambios: FastAPI monta `frontend/dist/`, no el código fuente.
* **`npx tsc -b` caza los imports muertos.** Pásalo después de retirar cualquier cosa.

**Del código:**

* **En FastAPI el orden de las rutas manda.** `/fuentes` tuvo que declararse **antes** de
  `/{id_alerta:path}` o se la tragaba como identificador. Hay un comentario puesto en
  `src/api/routers/centinela.py` para que nadie la mueva.

**De las pruebas:**

* ⚠️ **Una prueba que hereda la configuración de producción puede pasar en verde sin ejercitar
  nada.** Ocurrió hoy: al desactivar el DOGC, `test_modo_degradado_fallo_red` siguió pasando —una
  fuente apagada no llega a fallar—. **Un falso verde es peor que un rojo.** Si una prueba depende
  de un `config/*.yaml`, que declare ella lo que necesita.

---

## F · Método: lo que funcionó en el Paso 9 y conviene repetir

1. **Medir antes de escribir el contrato, no después.** Las cifras del Paso 9 salieron de ejecutar
   cosas contra el fichero real. Dos veces el documento validado resultó estar equivocado y las
   dos lo destapó el código, no releerlo.
2. **Un recuento que no suma delata dos mediciones fundidas.** Es la comprobación más barata que
   existe contra la deriva de cifras, y cazó un error en un documento canónico.
3. **Validar una regresión nueva mutando, no revirtiendo.** Se mutó el lector para que saltara
   líneas rotas en silencio: cayeron exactamente 3 pruebas, con el síntoma correcto. Revertir no
   habría probado nada, porque el símbolo aún no existía.
4. **Mirar la pantalla encuentra lo que las pruebas no** *(Convención C7)*. **Dos de los cuatro
   defectos que reparó el Paso 9 salieron de ahí**: un KPI que decía `0` sobre una tabla con 5
   filas, y un aviso que repetía cinco veces el mismo mensaje. Ninguna prueba los habría cazado.
5. **Un bloque, una verificación, un commit.** Los cinco bloques del Paso 9 se cerraron así y
   permitió volver atrás sin perder nada.

---

## G · Lo que el Paso 10 NO debería hacer

* **No reabrir H-56.** Es tentador porque se ve en pantalla, pero es del motor de análisis, no del
  cierre de la capa. Anotarlo en el manual, sí; repararlo, otra tarea.
* **No escribir un manual que describa el sistema ideal.** Debe describir **el que hay**, con sus
  cinco hallazgos abiertos y su DOGC apagado. Un manual que promete lo que no hay es peor que uno
  más corto — es la lección del Paso 10 de la Capa 9, y está escrita en el contrato de ésta.
* **No dar la capa por cerrada sin ejecutar el `.vbs` de verdad.** La suite en verde no vale aquí:
  lo que hay que comprobar es que **no aparece ninguna consola**, que el Cockpit abre con datos y
  que la tarea dispara una corrida real. Es literalmente lo que dice la Convención C7.

---

## H · Estado de partida, para no tener que medirlo otra vez

| | |
|---|---|
| Suite | **688/688** |
| Hallazgos | **57 catalogados, 52 cerrados, 5 abiertos** |
| Esquema de base de datos | **v8** |
| Política de retención | **v1.2.0** |
| Configuración del Centinela | **v1.1.0** |
| Contrato de la Capa 10 | **v1.3.0** |
| Contrato del Paso 9 | **v1.2.0**, cerrado |
| Última corrida verificada | **id 18**, `COMPLETED`, 43,7 s |
| Alertas en el canal Centinela | **5** |
| Cockpit | `tsc -b` limpio y `dist/` al día |
