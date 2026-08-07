# Dosier de Auditoría Técnica — bfr_incoop

**Fecha**: 2026-07-27 · **Alcance**: Capas 1 a 8 · **Estado del sistema al iniciar**: 130/134 pruebas en verde

> Este documento registra **hallazgos con evidencia reproducible**. No repite lo que ya está en
> el `README.md` (diseño) ni en `AGENTS.md` (reglas y estado). Su función es que ningún agente ni
> persona tenga que volver a descubrir estos problemas desde cero.
>
> **Convención**: cada hallazgo indica cómo se reprodujo. Si un hallazgo se marca como cerrado,
> se indica la prueba de regresión que impide que vuelva.

---

## Cómo se auditó

No se revisó sólo leyendo código: cada hallazgo se **reprodujo ejecutando** el sistema. Varios
defectos graves eran invisibles en lectura estática porque estaban enmascarados por bloques
`except Exception` amplios. Los tests tampoco los detectaban porque ejercitaban rutas distintas
de las de producción (otra raíz de importación, dependencias inyectadas en vez de las reales).

**Lección transversal**: en este proyecto, *"los tests pasan"* no ha sido garantía de que el
sistema funcione. Ver reglas C1–C6 en `AGENTS.md`.

---

## Cuadro de estado (actualizado el 2026-08-06)

| Hallazgo | Estado | Cerrado en |
|---|---|---|
| H-01 · No había forma correcta de arrancar el pipeline | 🟢 Cerrado | Paso B |
| H-02 · Un fallo del LLM se guardaba como análisis válido | 🟢 Cerrado | Paso C1 |
| H-03 · Una fila imperfecta tumbaba el funnel entero | 🟢 Cerrado | Paso C3 |
| H-04 · Hueco en la matriz de riesgo de subrogación | 🟢 Cerrado | Paso C2 |
| H-05 · La IA del Centinela nunca ha funcionado | 🟢 Cerrado | Pasos C2 y D2 |
| H-06 · El modelo LLM configurado y la cuenta actual | 🟢 Cerrado | Paso D6 |
| H-07 · Concurrencia SQLite: la API devolvía 503 | 🟢 Cerrado | Bloque 1 y Paso D1 |
| H-08 · KPIs aritméticamente imposibles | 🟢 Cerrado | Bloque 2 |
| H-09 · Escalas de scoring incompatibles | 🟢 Cerrado | Bloque 2 |
| H-10 · La detección ignoraba las negaciones | 🟢 Cerrado | Bloque 2 |
| H-11 · Doble penalización del mismo riesgo | 🟢 Cerrado | Bloque 2 |
| H-12 · Faltaban 3 de las 6 cláusulas críticas | 🟢 Cerrado | Bloque 2 |
| H-13 · El Cockpit no gestionaba estado por lote | 🟢 Cerrado | Bloque 2 — verificado en el bundle |
| H-14 · Higiene del proyecto | 🟢 Cerrado | Bloque 1 y repositorio Git |
| H-15 · El cerrojo huérfano no se reclamaba en Windows | 🟢 Cerrado | Paso D1 |
| H-16 · Un dictamen degradado decidía como si fuera real | 🟢 Cerrado | Paso D2 |
| H-17 · La suite de pruebas llamaba a la API real | 🟢 Cerrado | Paso D2 |
| H-18 · El resultado comercial dependía del directorio de trabajo | 🟢 Cerrado | Paso D3 |
| H-19 · La herramienta de diagnóstico probaba el modelo equivocado | 🟢 Cerrado | Paso D6 |
| H-20 · Las alertas descartadas desaparecían sin dejar rastro | 🟢 Cerrado | Paso D5 |
| H-21 · El KPI de cabecera contaba los expedientes archivados | 🟢 Cerrado | Paso D8 |
| H-22 · El Funnel listaba 29 expedientes archivados como filas fantasma | 🟢 Cerrado | Paso D8 |
| H-23 · La tabla afirmaba cláusulas que nadie había leído | 🟢 Cerrado | Paso D8 |
| H-24 · Un clon limpio del repositorio no podía arrancar | 🟢 Cerrado | Paso D10 |
| H-25 · La suite escribía en el `data/` real y seguía llamando a Gemini | 🟢 Cerrado | Paso D10 |
| H-26 · El sector `social` es inalcanzable: lo eclipsa `educativo` | 🟢 Cerrado | Paso D11 |
| H-27 · El estado archivado se escribe con dos grafías distintas | 🟢 Cerrado | Capa 9, Paso 3 |
| H-28 · El registro de respaldo del Lector escribía contra el directorio de trabajo | 🟢 Cerrado | Capa 9, Paso 2 |
| H-29 · El Cockpit anunciaba una versión de esquema codificada a mano | 🟢 Cerrado | Capa 9, Paso 3 |

**No queda ningún hallazgo abierto**: los 29 catalogados están cerrados con prueba de regresión
o verificación reproducible. Suite: **225/225**.

> **H-26 se cerró antes de la primera ejecución real, y esa era toda la urgencia.** No afectaba al
> score ni al orden de prioridad, pero `sector_detectado` se persiste en la base
> (`memoria.py:999`). Con la base vacía costó una tarde; con datos dentro habría obligado a
> recalcular el sector de todo lo capturado.

> ⚠️ **Aviso sobre la verificación de hermeticidad**: durante un tiempo se dio por buena una suite
> "hermética" comprobada bloqueando la red con excepciones. Era un falso verde — ver H-25. El
> método válido registra los intentos sin impedirlos.

> **H-21, H-22 y H-23 no salieron de leer código ni de la suite en verde: salieron de abrir el
> Cockpit contra la base de datos real.** Los tres afectaban a lo que el usuario ve en pantalla y
> ninguno rompía nada. Conviene repetir ese arranque en vivo al cerrar cada capa.

---

## Hallazgos CERRADOS

### H-01 · No existía ninguna forma correcta de arrancar el pipeline 🟢 CERRADO (Paso B)

Coexistían dos raíces de importación: `from memoria import ...` y `from src.memoria import ...`.
Python las trata como **dos módulos distintos**, con clases distintas.

```
python src/main.py    ->  Capa 6 muere: ModuleNotFoundError: No module named 'src'
python -m src.main    ->  ModuleNotFoundError: No module named 'radar'
```

El primero no se veía: `src/main.py` lo capturaba como `[!] Advertencia al ejecutar Capa 6`.
En la práctica, **el CSV comercial del Centinela nunca se generó en producción**.

Los tests no lo detectaban porque `pytest` añade la raíz al `sys.path` y ahí `src.` sí resuelve:
las pruebas ejercitaban una raíz distinta de la de producción.

**Cerrado con**: `src/__init__.py`, `run.py` como punto de entrada único, eliminación de 35
imports planos y 10 bloques `try/except ModuleNotFoundError` en `src/` y `tests/`.
**Regla que lo impide**: `AGENTS.md` → Convención C1.

---

### H-02 · Un fallo del LLM se guardaba como análisis válido 🟢 CERRADO (Paso C1)

`AnalisisSemanticoDTO.from_json()` capturaba toda excepción y devolvía un **DTO por defecto**,
que se marcaba `estado_analisis: "COMPLETADO"` y se retornaba **sin probar el proveedor de
respaldo**.

Efecto en pantalla: el Cockpit mostraba *"Subrogación: No · Revisión de precios: No"* sobre un
pliego que el sistema nunca llegó a leer. No es una degradación silenciosa: es **la fabricación
de un dictamen jurídico favorable**.

Agravantes encontrados:
- El Recalibrador detectaba el modo degradado buscando la palabra `"degradado"` dentro del
  resumen ejecutivo — texto libre generado por el LLM.
- El frontend no mencionaba `estado_analisis` en ninguna parte: un dictamen real y uno
  inventado se veían idénticos.

**Cerrado con**: campo explícito `modo_degradado` (esquema DTO v2), `from_json(estricto=...)`
que valida la **forma** del esquema y no sólo que sea JSON, y aviso visible en ficha y tabla.
**Regresión**: `tests/test_analista_llm.py` → `test_respuesta_json_valida_pero_esquema_invalido_activa_fallback`.
**Regla que lo impide**: Convenciones C2 y C3.

---

### H-03 · Una fila imperfecta tumbaba la página entera del funnel 🟢 CERRADO (Paso C3)

El DDL declara columnas con `DEFAULT` pero **sin `NOT NULL`** (`organo`, `fuente`, `titulo_lote`,
`pbl`, `estado_operativo`...). Un `DEFAULT` de SQLite sólo actúa si la columna se omite en el
INSERT: no impide guardar un NULL explícito. Pydantic rechaza `None` aunque el campo tenga valor
por defecto, porque el defecto sólo aplica si la clave está **ausente**.

```
GET /api/v1/licitaciones/EXP-DEMO-1
503 -> "Input should be a valid string [input_value=None]"
```

Como la validación vivía dentro de una comprensión de lista envuelta en `try/except`, **un solo
registro dejaba al equipo sin ver ninguna licitación**.

**Cerrado con**: tolerancia a NULL acotada a las columnas que el DDL permite vacías, y validación
fila a fila con auditoría de descartes. Verificado que `id` nulo y los tipos incorrectos se
siguen rechazando: la validación se estrechó, **no** se debilitó.
**Regresión**: `tests/test_api_tolerancia_nulos.py` (3 pruebas).

---

### H-04 · La matriz de riesgo de subrogación tenía un hueco 🟢 CERRADO (Paso C2, parcial)

Descubierto **sólo al probar contra la API real**: dos modelos clasificaban el mismo pliego con
riesgo distinto (`ALTO` frente a `MEDIO`). No era culpa de los modelos — la matriz v1 no cubría
el caso *"más de 15 trabajadores CON desglose salarial"*:

| Regla v1 | ¿Aplica a 22 trab. con desglose? |
|---|---|
| CRÍTICO: sin desglose **o** coste > 60 % PBL | No (hay desglose; 612.000/1.150.000 = 53 %) |
| ALTO: > 15 trabajadores **sin** desglose | No (sí hay desglose) |
| MEDIO: **entre 1 y 15** | No (son 22) |
| BAJO: sin subrogación | No |

Ninguna regla aplicaba, así que cada modelo improvisaba. `ALTO` resta −15 puntos y `MEDIO` no
resta nada: **el mismo pliego obtenía puntuaciones comerciales distintas según qué modelo
respondiera**, incompatible con la Regla 10 (determinista y auditable).

Se detectaron además dos reglas **inevaluables** que invitaban a alucinar:
- El criterio del 60 % del PBL exigía un presupuesto que no se inyecta en el prompt.
- Una regla de Periodo Medio de Pago pedía evaluar algo que el pliego nunca contiene, y que la
  Capa 2 ya calcula de forma determinista desde `config/pmp_ayuntamientos.csv`.

Y el ejemplo *few-shot* enseñaba el error contrario: marcaba `desglose_salarial_completo: true`
a partir de un texto que sólo daba un coste agregado, desactivando la condición de CRÍTICO.

**Cerrado con**: matriz v2 de siete tramos exhaustivos (`config/prompts_lcsp.yaml`), regla
anti-alucinación explícita, criterio del PBL condicionado a que conste en el texto, PMP retirado
del prompt de pliegos, y tres ejemplos *few-shot* corregidos.
**Verificación**: `python tools/verificar_matriz_subrogacion.py` → **5/5 deterministas** con dos
modelos de familias distintas.
**Regresión**: `tests/test_blindaje_ecosistema.py` → `test_prompts_lcsp_matriz_cuantitativa`
(guarda invariantes, no cadenas literales).

---

## Hallazgos que estaban abiertos el 2026-07-27

> Se conserva el diagnóstico original íntegro —es la evidencia de cómo se reprodujo cada uno— y se
> añade al final de cada hallazgo cómo se cerró. Sólo H-06 sigue abierto.

### H-05 · La IA del Centinela nunca ha funcionado 🟢 CERRADO (Pasos C2 y D2)

`AnalistaBoletinesIA._inicializar_proveedor_llm()` en `src/centinela.py` tiene **tres fallos
encadenados**:

1. Importaba con la raíz de paquete equivocada *(corregido en el Paso B)*.
2. Invoca `proveedor_llm_factory()`, función **que no existe** en `src/analista.py`.
3. El consumidor llama a `.generar_texto(prompt)`, método **ausente** de la interfaz
   `LLMProvider`, que expone `consultar(sistema, usuario, timeout)`.

Un `except Exception` amplio absorbía los tres y devolvía `None`.

```
[!] Advertencia al inicializar proveedor LLM en centinela: No module named 'analista'
proveedor_llm resultante = None
```

**Efecto real**: el 100 % de los boletines DOGC/BOPB se ha procesado sin capa semántica, con
`dictamen_ia_json` vacío. El Paso 5 de la Capa 6, marcado como completado y validado, **nunca se
ha ejecutado**.

**Por qué no lo detectaron las pruebas**: los tests inyectan siempre un proveedor simulado por el
parámetro `proveedor_llm=`, sorteando la factoría real. Ver Convención C4.

**Cómo se cerró**: el Paso C2 creó `proveedor_llm_factory()` y corrigió la llamada a `.consultar()`,
con `tests/test_centinela_llm_factory.py` ejercitando la factoría sin inyección (Convención C4).

**Pero la reparación destapó dos defectos más**, porque hasta entonces el fallo estaba enmascarado:
al empezar a construirse un proveedor real, la suite pasó a llamar a la API (H-17) y el dictamen
degradado empezó a decidir como si fuera un veredicto real (H-16). Ambos cerrados en el Paso D2.
Es el patrón de este proyecto: reparar un `except` amplio revela lo que llevaba años tapando.

---

### H-06 · El modelo LLM configurado no funciona con la cuenta actual 🟢 CERRADO (Paso D6)

Verificado contra la API real el 2026-07-27, en dos ejecuciones separadas:

| Modelo | Resultado | Tiempo | Tokens | Exactitud |
|---|---|---|---|---|
| `gemini-2.0-flash` *(el configurado)* | **429 Too Many Requests** | — | — | — |
| `gemini-2.0-flash-lite` | **429 Too Many Requests** | — | — | — |
| `gemini-3.5-flash` | error sin identificar | — | — | — |
| `gemini-3.1-flash-lite` | OK | 2,4 s | 1522 + 551 | **6/6** |
| `gemini-3.6-flash` | OK | 16,5 s | 1522 + 347 | **6/6** |

Si hoy se lanzara el pipeline, el proveedor preferente daría 429 y —gracias al Paso C1— todos los
pliegos quedarían correctamente marcados `DEGRADADO`. Antes del Paso C1 se habrían guardado como
análisis completos con todos los riesgos a `False`.

**Recomendación pendiente de aplicar**: `gemini-3.1-flash-lite` como preferente y `gemini-3.6-flash`
como respaldo — misma exactitud, 7× más rápido, tarifa menor, y familias distintas para que una
incidencia de cuota no arrastre a ambas. **Versiones fijadas, nunca alias tipo `-latest`**: un
alias cambia el modelo bajo los pies y con él los dictámenes (Regla 4).

**Salvedad honesta**: es una muestra de un solo pliego. Antes de fijarlo conviene pasar un lote
real y comparar.

**Diagnóstico reproducible**: `python tools/verificar_proveedor_llm.py`

**Cómo se cerró (2026-08-06)**: verificado contra la API real, con la herramienta de diagnóstico
previamente corregida (ver H-19, que es la razón por la que este hallazgo parecía no cerrarse nunca).

| Comprobación | Resultado |
|---|---|
| `gemini-3.1-flash-lite` (preferente) | OK en 1,9 s · 3142 + 477 tokens |
| Exactitud de la extracción | **7/7 campos correctos** |
| `gemini-3.6-flash` (respaldo) | OK en 13,1 s |
| Matriz de subrogación entre ambos modelos | **5/5 determinista** |

Queda cubierta la salvedad original: ya no es una muestra de un solo pliego evaluada por un solo
modelo, sino cinco casos que recorren todos los tramos de la matriz, coincidentes entre dos familias
de modelo distintas. La `GEMINI_API_KEY` vive en las variables de entorno del equipo, no en un
fichero `.env`.

---

### H-07 · Concurrencia SQLite: la API devuelve 503 bajo escritura del pipeline 🟢 CERRADO (Bloque 1 y Paso D1)

Reproducido con un escritor externo manteniendo una transacción 8 s:

```
busy_timeout = 5000 ms  (valor por defecto, nunca configurado explícitamente)
journal_mode = wal      synchronous = 2      foreign_keys = 1
>>> La API falla tras 5,4 s: OperationalError :: database is locked  ->  HTTP 503
```

Tres problemas:
1. `sqlite3.connect()` en `src/memoria.py` no fija `timeout=`. WAL resuelve lector↔escritor, no
   escritor↔escritor. El Lector descarga con `ThreadPoolExecutor(max_workers=6)`.
2. **El lock de fichero no tiene TTL ni PID**: si el proceso muere por corte de luz o *kill*, el
   `.lock` queda huérfano y bloquea el sistema de forma **permanente**, sin recuperación.
3. **El lock depende del directorio de trabajo**: `Memoria()` se instancia con ruta relativa en
   cada petición. Si API y pipeline arrancan desde directorios distintos —justo lo que hará el
   lanzador VBS de la Capa 10— apuntan a ficheros `.lock` **diferentes** y la exclusión mutua
   desaparece.

**Cómo se cerró**: el Bloque 1 fijó `busy_timeout=30000`, WAL, TTL+PID en el cerrojo y ruta
absoluta para la BD (`tests/test_concurrencia_sqlite.py`, `tests/test_file_lock.py`).

**Ojo**: el punto 2 no quedó realmente resuelto hasta el Paso D1. La limpieza de huérfanos existía
pero **no se ejecutaba nunca en Windows** (ver H-15), así que entre el Bloque 1 y el 2026-08-06 el
bloqueo permanente por cierre abrupto seguía siendo posible pese a figurar como cerrado. Lección:
una protección declarada no es una protección verificada en la plataforma de destino.

El punto 3 (rutas dependientes del directorio de trabajo) resultó ser mucho más grave de lo que
sugería este diagnóstico, que sólo contemplaba la pérdida de exclusión mutua entre cerrojos.
Afectaba también al perfil comercial y, con él, a la puntuación. Ver H-18, cerrado en el Paso D3.

---

### H-08 · Los KPIs del dashboard son aritméticamente imposibles 🟢 CERRADO (Bloque 2)

`obtener_resumen_kpis()` cuenta ganadas/perdidas sobre `lotes WHERE deleted_at IS NULL`, pero lee
`win_rate` de `vista_win_rate`, que **no filtra los soft-deleted** y usa otro denominador.
Demostrado con 5 lotes:

```
Cockpit:  ganadas = 2   perdidas = 3   win_rate = 50,0 %
          -> 2/(2+3) = 40 %, no 50 %
vista_win_rate (interno): perdidas = 4   <- población distinta
```

Además, un lote con `estado='Adjudicada'` y `empresa_adjudicataria='Clece SA'` entra en **las dos
ramas** del `COUNT(CASE...)`, y un lote registrado sólo por inteligencia competitiva (nunca
presentado) computa como derrota.

**Cómo se cerró**: todas las métricas de conversión salen ahora de `vista_win_rate`, que filtra
`deleted_at IS NULL`. Una sola consulta, una sola población.

---

### H-09 · Escalas de scoring incompatibles entre capas 🟢 CERRADO (Bloque 2)

`src/filtro.py` no acota el resultado: medido **165 puntos** en un caso favorable realista, y
puede ser negativo. Pero `RecalibradorScoring` trunca a `[0, 100]`, sus umbrales
(`umbral_recomendada: 65`) asumen esa escala, y el esquema de la API declara `score_total` como
0-100. Dos licitaciones de 110 y 165 puntos brutos se muestran ambas como 100.

**Cómo se cerró**: `score` es ahora el valor canónico en `[0, 100]` y `score_bruto` conserva la
escala interna para trazabilidad. Regresión en `tests/test_bloque2_coherencia.py`.

---

### H-10 · La detección de subrogación ignora las negaciones 🟢 CERRADO (Bloque 2)

`src/radar.py` marca el flag con `if "subrogac" in title.lower()`. Verificado:

```
"NO PROCEDEIX LA SUBROGACIÓ DE PERSONAL"   -> detectada = True  -> −20 pts
"No existe obligación de subrogación"       -> detectada = True  -> −20 pts
"(sin subrogación)"                         -> detectada = True  -> −20 pts
```

Un pliego que declara expresamente que **no hay** subrogación se penaliza igual que uno con
plantilla pesada. Idéntico problema con `"revisio"`, que engancha *"revisión de oficio"*.

**Nota**: tras el Paso C2 la Capa 5 **sí** interpreta bien las negaciones (`detectada=False`
verificado contra la API real). La contradicción entre Capa 1 y Capa 5 sigue abierta.

---

### H-11 · Doble penalización del mismo riesgo 🟢 CERRADO (Bloque 2)

La Capa 2 resta −20 por subrogación. La Capa 5 recalibra **partiendo de ese score ya penalizado**
y vuelve a restar −15/−25. Un contrato con subrogación crítica acumula −45 por un único hecho.

**Cómo se cerró**: la señal textual preliminar del Radar ya no mueve el score; la subrogación se
ajusta una sola vez, a partir de la clasificación semántica del pliego. Además, el `ajuste_score`
que propone el LLM se conserva como información pero **no se aplica**: el scoring comercial es
determinista y configurado. Regresión en `tests/test_bloque2_coherencia.py`.

---

### H-12 · Faltan 3 de las 6 cláusulas críticas del README 🟢 CERRADO (Bloque 2)

No existen ni en el DTO, ni en el prompt, ni en la tabla `analisis_semantico`:

| Cláusula | Artículo | Estado |
|---|---|---|
| Subrogación | 130 | ✅ |
| Revisión de precios | 103 | ⚠️ booleano plano, sin distinguir si cubre costes laborales |
| **Garantía definitiva** (aval vs. caución) | 107-108 | ❌ ausente |
| Peso precio/calidad | 145 | ⚠️ signo invertido respecto al README |
| **Penalidades y resolución** | 192-194 | ❌ ausente |
| **Cláusulas sociales** | 202 | ❌ ausente |

Las dos ausencias más caras son las que el README marca como críticas: la garantía definitiva por
la *Paradoxa de Caixa* (~38.000 € líquidos) y las cláusulas sociales, descritas como **la** ventaja
competitiva de Incoop como cooperativa de iniciativa social.

**Sobre el Art. 145**: el README afirma que si el precio pesa más del 60 % la licitación se vuelve
*"una guerra de precios donde Incoop tiene desventaja"*. El código hace lo contrario: penaliza
−10 el predominio del juicio de valor y bonifica +5 el predominio del precio. Puede defenderse por
coste procedimental (el Art. 146.2 exige comité de expertos cuando el juicio de valor domina),
**pero entonces debe documentarse así**. Requiere decisión del usuario.

**Cómo se cerró**: el DTO sube a v3 con `GarantiaDefinitivaDTO` (arts. 107-108), `PenalidadesDTO`
(arts. 192-194) y `ClausulasSocialesDTO` (art. 202). Si un dato no consta, se representa como
`null` o `false`; nunca se deduce por conocimiento externo. Regresión en
`tests/test_bloque2_coherencia.py::test_dto_v3_preserva_las_seis_clausulas_criticas`.

**Decisión del Art. 145 (2026-08-06)**: se alinea con el README. Un peso de precio/fórmulas
superior al 60 % penaliza −10 pts; el predominio del juicio de valor **no** recibe penalización
automática, porque puede ser precisamente la ventaja competitiva de la cooperativa. El signo
invertido queda corregido.

---

### H-13 · El Cockpit no puede gestionar el estado por lote 🟢 CERRADO (Bloque 2)

`TransicionEstadoLicitacion` no lleva `lote_numero`, así que la API siempre muta el lote 1.
Pero `useApiMutations.ts` aplica optimistamente el nuevo estado a **todos** los lotes: el usuario
ve cambiar los cinco, el backend cambia uno, y el refresco revierte la vista. Anula el modelo 1:N
que el README describe como razón de ser de la Capa 3.

El *rollback* tampoco es atómico pese a la documentación: `onMutate` guarda copia del detalle pero
no de las listas paginadas que también modifica.

**Cómo se cerró**: `lote_numero` recorre ahora el contrato completo — `TransicionEstadoLicitacion`
en `src/api/schemas.py`, el endpoint de mutación en `src/api/routers/licitaciones.py`, y en el
frontend `useApiMutations.ts`, `DetailDrawer.tsx` y `LicitacionesTable.tsx`, que actualizan de
forma optimista **sólo** el lote afectado.

**Verificado en la pantalla el 2026-08-06**: recompilado con Node.js 24.19.0, el bundle contiene
`lote_numero`. Se había supuesto desfasado por la fecha de `frontend/dist/`, pero Vite generó los
mismos nombres de fichero que ya existían y esos nombres son un hash del contenido: el bundle ya
estaba al día. **La fecha de un artefacto no acredita de qué fuente salió.**

---

### H-14 · Higiene del proyecto 🟢 CERRADO (Bloque 1 y repositorio Git)

- `requirements.txt` no declara `fastapi`, `uvicorn`, `pydantic`, `starlette`, `httpx` ni `pytest`.
  Un clon del repositorio no arranca las Capas 7 y 8.
- No hay `.gitignore` ni gestión de `.env`. **Ya hay una `GEMINI_API_KEY` en el entorno del
  equipo**: si el proyecto se convierte en repositorio git, esto pasa a ser urgente.
- TypeScript **no tiene `strict` activado** en ningún `tsconfig*.json`. Toda la anotación
  `?: X | null` del espejo de tipos es decorativa: el compilador no la verifica.
- El middleware de trazabilidad hace E/S de fichero **síncrona** dentro de un `async def`,
  bloqueando el bucle de eventos en cada petición. La rotación de logs no está sincronizada.

**Cómo se cerró**: `requirements.txt` declara las dependencias de las Capas 7 y 8; existen
`.gitignore` y `.env.example`; `strict` activado en TypeScript; y el proyecto se versiona desde el
2026-08-06 en https://github.com/DonBorgiFR/licit-accion. La `GEMINI_API_KEY` vive en variables de
entorno del sistema, nunca en un fichero del repositorio.

**Trampa del `.gitignore` que costó descubrir**: los patrones de empaquetado de Python deben ir
anclados con `/` a la raíz. Sin la barra inicial, `lib/` casa con **cualquier** carpeta llamada
`lib` a cualquier profundidad, y excluía `frontend/src/lib/` (`api-client.ts`, `react-query.ts`,
`utils.ts`): un clon limpio no habría podido compilar el Cockpit, con un error desconcertante.
No revertir ese anclaje.

**Queda pendiente** (menor, no bloqueante): la E/S síncrona del middleware dentro de `async def`.

---

## Hallazgos posteriores — 2026-08-06

> Los tres salieron al reparar defectos anteriores, no de una auditoría nueva. Es el patrón
> recurrente del proyecto: un `except Exception` amplio no elimina un defecto, lo aplaza.

### H-15 · El cerrojo huérfano no se reclamaba nunca en Windows 🟢 CERRADO (Paso D1)

El Bloque 1 declaró cerrada la protección TTL+PID contra bloqueos permanentes. **No funcionaba en
la plataforma de destino.** Dos defectos independientes en `db_lock`:

1. El `os.remove(lock_path)` se ejecutaba **dentro** del `with open(lock_path)`. Windows no permite
   borrar un fichero con un handle abierto. Un `except Exception: pass` silenciaba el error y el
   bucle reintentaba lo mismo hasta agotar el timeout.

```
PermissionError [WinError 32] El proceso no tiene acceso al archivo
porque está siendo utilizado por otro proceso
-> RuntimeError: No se pudo adquirir el lock ... tras 2.0s
```

2. Un cerrojo de **0 bytes** bloqueaba para siempre. El fichero se crea antes de escribir el
   payload; si el proceso muere en ese hueco, queda sin `pid` ni `created_at`, y el código exigía
   contenido legible para evaluar la caducidad. Ningún test lo cubría. Reproducido con TTL de 1 s:
   seguía bloqueado.

**Efecto real**: un corte de luz o un cierre abrupto dejaba el sistema inutilizable hasta que
alguien borrara un fichero oculto a mano — exactamente lo que el Bloque 1 debía evitar.

**Cómo se cerró**: la lectura vive en `_motivo_lock_huerfano()`, que decide con el fichero ya
cerrado; el borrado ocurre después. Un cerrojo ilegible caduca por la fecha de modificación del
propio fichero, **nunca de inmediato**: uno reciente puede ser un proceso sano que todavía no ha
terminado de escribirlo. La reclamación emite `DB_LOCK_HUERFANO_RECLAMADO` en `data/pipeline.jsonl`,
porque borrar el cerrojo de otro proceso es destructivo y era invisible.

**Regresión**: `tests/test_file_lock.py`, 6 casos (los 2 que ya existían más ilegible-reciente e
ilegible-antiguo).

---

### H-16 · Un dictamen degradado del Centinela decidía como si fuera real 🟢 CERRADO (Paso D2)

`DictamenCentinelaDTO.from_dict` aceptaba un `{}` y devolvía un dictamen aparentemente válido:

```python
nivel_interes = str(data.get("nivel_interes", "NULO"))   # inventa el veredicto
resumen_ejecutivo = str(data.get("resumen_ejecutivo", ""))
```

El evaluador restaba entonces **−30 pts** y la alerta se descartaba, sin nada que distinguiera ese
descarte de un juicio real de la IA. Y el fallback por error de conexión hacía lo simétrico:
declaraba `"MEDIO"` y **regalaba +15 pts** a un análisis que nunca ocurrió.

Es el mismo defecto que H-02, ya cerrado en la Capa 5 por el Paso C1 — **la Capa 6 nunca recibió
esa corrección**.

**Efecto real**: como la IA del Centinela jamás funcionó (H-05), el bonus fantasma de +15 se aplicó
a **todas** las alertas procesadas. En el e2e, una alerta de Badalona con +40 de reglas duras y
−25 por su PMP de 78 días quedaba en 30, justo el `score_minimo_alerta`. Se guardaba **sólo** por
los 15 puntos de un análisis inexistente.

**Cómo se cerró**: esquema v2 con `modo_degradado`; `from_json(estricto=True)` valida la forma;
nuevo `nivel_interes="DESCONOCIDO"` que no es sinónimo de `"NULO"`; y el evaluador conserva el
score de reglas duras sin inferir interés ni desinterés. Ver Convención C6.

**Decisión de negocio (2026-08-06)**: la alerta cuyo análisis falla **llega al Cockpit marcada**,
no desaparece (Convención C3).

**Regresión**: `tests/test_centinela_analista.py` y `tests/test_centinela_scoring.py`.

---

### H-17 · La suite de pruebas llamaba a la API real de Gemini 🟢 CERRADO (Paso D2)

Tras reparar la factoría en el Paso C2, `AnalistaBoletinesIA(proveedor_llm=None)` dejó de
significar "sin LLM": el constructor pasó a fabricar un `GeminiProvider` real. Como hay una
`GEMINI_API_KEY` en las variables de entorno del equipo, **la suite empezó a salir a la red en cada
ejecución**: gastaba cuota, tardaba más y su resultado dependía de lo que contestara el modelo ese
día. Una prueba no reproducible no es una red de seguridad.

Fue la causa directa del fallo intermitente de `tests/test_capa6_e2e.py`.

**Cómo se cerró**: nuevo parámetro `autoinicializar_proveedor=False`. Ver Convenciones C4 y C5.

**Diagnóstico reproducible**: ejecutar la suite con un `sitecustomize.py` en el `PYTHONPATH` que
intercepte `socket.connect` y `socket.getaddrinfo` y permita sólo `127.0.0.1` (el `TestClient` de
FastAPI usa tráfico local legítimo). Debe seguir dando 159/159.

---

### H-18 · El resultado comercial dependía del directorio de trabajo 🟢 CERRADO (Paso D3)

El Bloque 1 hizo absoluta la ruta de la base de datos, pero `config/` y `data/` seguían
resolviéndose contra el directorio de trabajo en Radar, Filtro, Lector, PMPService, Analista,
Centinela y los reportes. Figuraba como "salvedad menor" pendiente para la Capa 10.

**No era menor: no fallaba, decidía distinto.** Al no encontrar `config/perfil_incoop.yaml`, el
perfil comercial se cargaba **vacío** y el sistema continuaba en silencio con los valores por
defecto. Reproducido con la misma licitación:

```
Perfil cargado desde la raíz    : 11 claves   ->  SCORE = 71
Perfil cargado desde otra carpeta:  0 claves   ->  SCORE = 47
```

Con `umbral_recomendada` en 65, esos 24 puntos son la diferencia entre **recomendar y descartar**.
Y es exactamente el escenario de la Capa 10: el lanzador VBS arranca con un directorio de trabajo
arbitrario. De haberse abierto la Capa 10 sin resolver esto, el sistema habría puntuado mal
**todas** las licitaciones sin emitir un solo error.

**Cómo se cerró**: `PROJECT_ROOT` y `ruta_proyecto()` se centralizan en `src/__init__.py` (antes
`PROJECT_ROOT` vivía en `src/memoria.py`, del que tenía que importarlo la API). Toda ruta relativa
se ancla a la raíz del proyecto en el punto donde se asigna; las absolutas se respetan intactas,
de modo que las pruebas siguen pudiendo inyectar rutas temporales.

**Regresión**: `tests/test_rutas_proyecto.py`, 4 casos. El central compara la puntuación de la
misma licitación desde la raíz y desde una carpeta ajena: deben coincidir.

---

### H-19 · La herramienta de diagnóstico probaba un modelo que ya no se usaba 🟢 CERRADO (Paso D6)

`tools/verificar_proveedor_llm.py` existe para responder a H-06. Leía el modelo así:

```python
modelo_cfg = "gemini-2.0-flash"                              # valor por defecto codificado
modelo_cfg = (cfg.get("gemini") or {}).get("modelo", modelo_cfg)
```

Pero la clave del fichero es **`modelo_principal`**, no `modelo`. La búsqueda fallaba en silencio,
caía al valor codificado y la herramienta probaba `gemini-2.0-flash` — justamente el modelo que
H-06 había descartado en julio. Cada ejecución del diagnóstico devolvía un 429 rotundo y un
mensaje alarmante (*"en producción esto degradaría el 100 % de los análisis"*) sobre un modelo que
el sistema ya no usaba. **El hallazgo H-06 se mantuvo abierto por culpa de su propio diagnóstico.**

Es el mismo patrón que H-18: una lectura de configuración que parece funcionar, falla sin ruido y
sigue adelante con un valor por defecto.

**Cómo se cerró**: la herramienta replica ahora exactamente la lectura de `proveedor_llm_factory()`
(`modelo_principal` con reserva a `modelo`), usa `ruta_proyecto()` y prueba además el modelo de
respaldo, que es la única red de seguridad cuando el principal agota cuota y hasta ahora no se
comprobaba nunca.

**Lección**: una herramienta de diagnóstico que no comparte la lectura de configuración con el
código que diagnostica no diagnostica el sistema, sino a sí misma.

---

### H-20 · Las alertas descartadas desaparecían sin dejar rastro 🟢 CERRADO (Paso D5)

Si el score final de una alerta no alcanzaba `score_minimo_alerta` (30), el pipeline **no la
escribía en la base de datos**:

```python
if a.estado_operativo != "DESCARTADA_POR_REGLAS":
    memoria_svc.guardar_alerta_boletin(a)
```

No quedaba registro de qué se descartó ni por qué, cada ejecución la reprocesaba desde cero, y si
se ajustaba un umbral o cambiaban los PMP no había nada que reevaluar.

**Decisión de negocio (2026-08-06)**: se persisten todas, y las consultas de listado excluyen las
descartadas del canal principal salvo que se pidan por su estado explícito o con
`incluir_descartadas=True`. Se guardan para auditar, no para ocupar la pantalla.

**Dos defectos latentes que sólo afloraron al empezar a persistirlas**:

1. `DESCARTADA_POR_REGLAS` **no figuraba en `ESTADOS_BOLETIN_VALIDOS`**. El evaluador llevaba
   emitiendo un estado que el propio DTO rechaza con `BoletinDTOValidationError`. Nunca explotó
   porque esas filas jamás se escribían ni se reconstruían desde la base de datos. Se promueve a
   estado canónico —también en el esquema de la API y en el espejo de tipos del frontend— en vez
   de fusionarlo con `DESCARTADA_TEMPRANA`: **no son lo mismo**. Uno es "lo descartó la máquina" y
   el otro "lo rechacé yo", y esa distinción es justo la que permite reevaluar sólo lo primero.

2. El UPSERT preservaba `CONVERTIDA_A_LICITACION` y `EN_ESTUDIO_PROACTIVO`, pero **no**
   `DESCARTADA_TEMPRANA`: una reejecución del pipeline pisaba el descarte decidido por una
   persona y lo devolvía a su estado de reglas, sin dejar rastro. Añadido al blindaje.

**Regresión**: `tests/test_capa6_e2e.py` — la alerta descartada se guarda pero no aparece en
ninguna de las dos consultas de listado, y un descarte manual sobrevive a una reejecución.

---

## Hallazgos del arranque en vivo — 2026-08-06

> Los tres salieron de **abrir el Cockpit contra la base de datos real**, con la suite en verde y
> los 20 hallazgos anteriores cerrados. Ninguno rompía nada: los tres mentían en pantalla.

### H-21 · El KPI de cabecera contaba los expedientes archivados 🟢 CERRADO (Paso D8)

La misma tarjeta del panel anunciaba **"51 Expedientes"** sobre un desglose que sumaba **22 lotes**.

`total_expedientes` hacía `SELECT COUNT(*) FROM expedientes`, sin filtro alguno, mientras el resto
del panel filtraba `deleted_at IS NULL`. La tabla `expedientes` **no tiene `deleted_at`**: el
archivado lógico vive en `lotes`, así que un expediente cuyos lotes están todos archivados es un
expediente archivado. En la base de trabajo, 29 de los 51 estaban en esa situación.

Es el mismo defecto de poblaciones mezcladas que H-08, en el contador que se le escapó a aquella
corrección.

**Cerrado con**: `SELECT COUNT(DISTINCT expediente_id) FROM lotes WHERE deleted_at IS NULL`.
**Regresión**: `tests/test_bloque2_coherencia.py::test_los_kpis_de_cabecera_y_de_desglose_cuentan_la_misma_poblacion`.

---

### H-22 · El Funnel listaba los expedientes archivados como filas fantasma 🟢 CERRADO (Paso D8)

Más grave que el anterior, porque afecta a **la tabla con la que se decide a qué concurso
presentarse**. La API devolvía `total: 51`.

`listar_expedientes_paginados()` usa una subconsulta de lotes que sí filtra `deleted_at IS NULL`,
pero la unía con **`LEFT JOIN`**: los expedientes sin ningún lote vivo pasaban igualmente, con
todos los campos de la subconsulta a `NULL`. Se pintaban como filas de **"0 € y 0 pts"**, y una de
ellas arrastraba un `score_total` de **115** — de la escala anterior al Bloque 2, fuera del rango
canónico 0-100.

```
API /licitaciones -> total: 51   (22 vivos + 29 archivados)
   29 filas sin ningún lote, mostradas como 0 € / 0 pts
   una de ellas con score 115, de la escala antigua
```

**Cerrado con**: `JOIN` interno en lugar de `LEFT JOIN`, en la consulta de recuento y en la de
datos. Verificado en vivo: `total` pasa de 51 a 22, cero filas sin lotes, score máximo 85.
**Regresión**: `tests/test_bloque2_coherencia.py::test_el_funnel_no_lista_expedientes_archivados`.

---

### H-23 · La tabla afirmaba cláusulas que nadie había leído 🟢 CERRADO (Paso D8)

Dos defectos encadenados en la columna "Cláusulas & Riesgo" de `LicitacionesTable.tsx`, ambos de
la familia de H-02 pero **en el sentido contrario al que cubrió el Paso C1**.

**1. La ausencia total de análisis no se distinguía.** El distintivo *"Pliego sin analizar"* sólo
aparecía cuando existía un análisis degradado o incompleto:

```tsx
const analisisDegradado = Boolean(
  lic.analisis_semantico?.modo_degradado || ...
);   // analisis_semantico === null  ->  false
```

Con `analisis_semantico` a `null` —el pliego nunca se analizó— no salía aviso alguno y la fila
mostraba *"Sin Subrog. · Sin Revisión"*, derivado de un rastreo de palabras clave del título, con
el mismo aspecto que una lectura verificada del documento. En la base de trabajo eran **21 de 22
lotes**: el caso abrumadoramente mayoritario en cuanto el Radar puebla la base.

**2. Cuando el análisis existía, la tabla lo contradecía.** Los indicadores leían
`lotePrincipal.subrogacion`, la señal preliminar del Radar, en vez del resultado del análisis. El
único expediente analizado de la base (`2026/000030702`) tenía:

| Fuente | Subrogación | Revisión de precios |
|---|---|---|
| Análisis semántico (pliego leído, `COMPLETADO`) | **sí**, riesgo BAJO | **sí**, permitida |
| `lotes.subrogacion` / `lotes.revision_precios` | `NULL` | `NULL` |
| **Lo que mostraba la tabla** | **"Sin Subrog."** | **"Sin Revisión"** |

No era una ausencia inventada por falta de datos: era **contradecir un análisis real que existía**.
Un falso negativo en subrogación es el riesgo más caro del negocio de Incoop.

**Cerrado con**: la lectura del pliego manda sobre la señal preliminar; sin análisis se muestra
*"Subrogación: sin datos"* / *"Revisión: sin datos"* en vez de afirmar una ausencia, y la fila
lleva el distintivo *"Pliego sin analizar"*. Verificado en vivo en ambos sentidos: las 21 filas sin
análisis avisan, y la analizada muestra *"Subrogación · Revisión Precios"*.
**Regla que lo impide**: Convención C3.

---

## Hallazgos del borrado de la beta — 2026-08-06

> Salieron de **vaciar los datos de prueba y arrancar desde cero absoluto**, a petición de la
> dirección del proyecto. Ninguno era visible mientras hubiera datos en disco.

### H-24 · Un clon limpio del repositorio no podía arrancar 🟢 CERRADO (Paso D10)

`data/` está excluida de Git, así que en un clon nuevo no existe. `setup_db()` adquiere el cerrojo
de migración **antes** de abrir la primera conexión, y era `conectar()` quien creaba el directorio:

```
FileNotFoundError: [Errno 2] No such file or directory:
   '...fr_incoop\data\licitaciones.db.lock'
```

Cualquiera que clonara el repositorio y ejecutara `python run.py` se topaba con esto. No se había
detectado nunca porque en el equipo de desarrollo `data/` llevaba existiendo desde julio.

**Cerrado con**: `Memoria.__init__` garantiza su directorio de almacenamiento en cuanto se
construye el objeto, no al conectar.
**Regresión**: `tests/test_rutas_proyecto.py::test_el_sistema_arranca_en_una_instalacion_nueva`.

---

### H-25 · La suite escribía en el `data/` real y seguía llamando a Gemini 🟢 CERRADO (Paso D10)

Dos fugas, y la segunda invalida una verificación que se había dado por buena.

**1. Escritura en el directorio de datos del proyecto.** Ejecutar las pruebas creaba
`data/licitaciones.db`, volcaba `data/pipeline.jsonl` y generaba informes CSV en la carpeta de
trabajo. Con datos reales dentro, **ejecutar los tests habría tocado la base de producción**.
El origen estaba repartido: las rutas por defecto de `memoria`, `analista`, `centinela`, `lector`
y `api/dependencies` apuntaban a `<raíz>/data`.

**2. La suite seguía llamando a la API real de Gemini**, pese a haberse declarado hermética en el
Paso D2. `tests/test_centinela_trazabilidad.py` instanciaba `AnalistaBoletinesIA()` sin desactivar
el proveedor.

**Por qué no se detectó**: la comprobación de hermeticidad **bloqueaba la red lanzando una
excepción**. El `except Exception` amplio de `analizar_alerta` la capturaba y la convertía en
"modo degradado", así que la prueba pasaba y la suite parecía limpia. Es exactamente el defecto
que persiguen las Convenciones C2 y C6, aplicado a la propia herramienta de verificación.

```
Método defectuoso (bloquea):   175/175 en verde  ->  conclusión falsa
Método correcto (registra):    175/175 en verde  ->  "generativelanguage.googleapis.com"
```

**Cerrado con**: nueva función `ruta_datos()` en `src/__init__.py`, que centraliza el directorio de
datos y admite reubicación mediante `DATA_DIR_INCOOP`; `tests/conftest.py` lo redirige a un
directorio temporal **al importarse, no en un fixture** —`src/api/dependencies.py` crea su gestor
de trazabilidad como singleton de módulo y ya crea la carpeta al importar, antes de que corra
ningún fixture—; y `autoinicializar_proveedor=False` en las dos instancias que faltaban.

**Verificado**: borrando `data/`, la suite da 175/175, no contacta ningún dominio externo y
**`data/` no llega a crearse**. Ver Convención C5 para el método de comprobación.

---

## Hallazgo de la revisión de cobertura CPV — 2026-08-07

> Salió de retomar la pregunta aplazada el 31-07-2026 sobre el solapamiento entre el perfil de CPVs
> de Incoop y los CPVs realmente capturados. La pregunta de cobertura se resolvió (ver `AGENTS.md`);
> por el camino apareció este defecto, que no tiene que ver con la cobertura sino con el reparto por
> sectores.

### H-26 · El sector `social` es inalcanzable: lo eclipsa `educativo` 🟢 CERRADO (Paso D11)

**Toda la familia `853*` —asistencia social, el núcleo del negocio de Incoop— se etiqueta como
`Educativo`.** El sector `social` no se asigna nunca, por ninguna vía.

**Causa.** `Filtro.__init__` (`src/filtro.py:57-66`) indexa cada CPV del perfil por sus **3 y 5
primeros dígitos**. El sector `educativo` contiene `85312110` ("Guarderías escolares sociales"),
cuyo prefijo de 3 dígitos es `853`. Ese `853` entra en el conjunto de `educativo`. Después, el
bucle de asignación (`src/filtro.py:265-277`) recorre los sectores **en el orden del YAML** y corta
en la primera coincidencia. Como `educativo` es la primera clave de `sectores_cpv`, se lleva todos
los `853*` antes de que `social` llegue a consultarse.

Los prefijos de 3 dígitos resultantes muestran la colisión:

```
educativo                ['800', '801', '802', '803', '804', '853']   <- se lleva 853
social                   ['853']                                      <- nunca se alcanza
consultoria              ['751', '794', '853']                         <- nunca se alcanza por 853
```

**Reproducción**:

```python
from src.filtro import Filtro
f = Filtro()
f.filtrar({'titulo':'Servicio generico','organo':'Ajuntament de Terrassa','importe':100000,
           'vec':100000,'cpvs':['85300000'],'estado':'PUB','procedimiento_codigo':'1',
           'tipo_contrato_codigo':'2','fecha_limite':'2026-12-31',
           'country_subentity_code':'ES511'})['sector_detectado']
# -> 'Educativo'   (85300000 = Servicios de asistencia social general)
```

Verificado sobre los cinco CPVs sociales del perfil: `85300000`, `85312000`, `85312100`,
`85312300` y `85320000` devuelven todos `Educativo`, con score 65 en los cinco casos.

**Efecto colateral: una regla muerta.** La red de seguridad por división
`elif cpv_str.startswith("853"): sector_detectado = "Social"` (`src/filtro.py:282-286`) es
**inalcanzable**: cualquier `853*` ya casó como core en `educativo` y el bucle no llega a esa rama.

**Qué NO rompe.** El score es idéntico (+40 por cualquiera de los dos sectores), así que la
puntuación, el orden de prioridad y el umbral de recomendación no se ven afectados. Por eso ni la
suite ni el arranque en vivo del Paso D8 lo detectaron: no hay ninguna cifra incorrecta.

**Qué sí rompe.** `sector_detectado` se propaga a `main.py:82` y se **persiste** como columna
`sector` en la base (`memoria.py:999` y `memoria.py:1414`), desde donde alimenta a la API y al
Cockpit. Cualquier lectura por sector —"cuántas licitaciones sociales estamos detectando"— dirá
cero sociales y contará como educativas licitaciones de centros de día y atención domiciliaria.

**Por qué importa el momento.** La base está vacía. Corregirlo ahora no cuesta nada; corregirlo
después de la primera ejecución real obliga a recalcular el sector de todo lo capturado.

**La colisión no es sólo de 3 dígitos.** El prefijo de **5** también está compartido, y esto
descarta las correcciones aparentemente obvias:

```
853   -> ['consultoria', 'educativo', 'social']
85312 -> ['consultoria', 'educativo', 'social']     <- 85312110 (educativo) vs 85312000/100/300 (social)
```

**Vías de corrección, medidas** (ninguna implementada). Contrastadas sobre los 7 CPVs del sector
`social`, el CPV fronterizo `85312110` y `85322000` —hermano detectado en la beta que no figura en
el perfil—, tomando como esperado la clasificación del propio `perfil_incoop.yaml`:

| Criterio | Aciertos | Por qué falla |
|---|---|---|
| Como está hoy | 1/9 | El orden del YAML decide; `educativo` se lleva todo `853*` |
| Indexar sólo por 5 dígitos | 5/9 | `85312` está compartido: sigue fallando toda la familia `85312*` |
| Gana el prefijo más largo | 5/9 | Empata en 5 dígitos para `85312*`; mismo fallo |
| **Código exacto primero, luego 5, luego 3** | **8/9** | Sólo falla el hermano no listado (`85322000`) |

Reproducible con el prototipo de análisis usado el 2026-08-07, que no toca `src/`: compara los
cuatro criterios sobre esos nueve CPVs leyendo el perfil real.

**Recomendación**: resolver por **código completo primero** y caer al prefijo sólo si no hay
coincidencia exacta, **más un orden de prelación explícito entre sectores** para los empates. Con
ese criterio los siete CPVs sociales van a `social` y `85312110` se queda en `educativo`.

El caso que sigue fallando es el que fija el requisito del desempate: `85322000` no está en el
perfil, así que no hay código exacto y `853` empata entre `educativo`, `social` y `consultoria`.
Hoy ese empate lo resuelve el orden en que están escritas las claves del YAML, que no es un
criterio: debe ser una decisión declarada.

**Decisión de negocio ya tomada (2026-08-07)**: `85312110` ("Guarderías escolares sociales") **se
queda en `educativo`**. En su base es una guardería, próxima a las escoles bressol. Esto **descarta
la vía barata** de reclasificarlo: mover ese CPV a `social` haría desaparecer el síntoma —`educativo`
dejaría de reclamar `853`— pero al precio de etiquetar como social justo el CPV que no lo es, y
apoyándose en que `social` precede a `consultoria` en el fichero. La corrección tiene que estar en
el algoritmo, no en el dato.

**Defecto menor asociado**: `85312300` estaba **duplicado** en el perfil, en `social` y en
`consultoria`. Era inocuo porque `social` va primero, pero dejaba la asignación dependiendo del
orden. Retirado de `consultoria`.

**Cerrado con** (Paso D11):

* `config/perfil_incoop.yaml`: nueva clave `prelacion_sectores`, que declara el desempate que
  antes decidía el orden de las claves. `85312300` deja de estar duplicado.
* `src/filtro.py`: el conjunto único de prefijos se sustituye por tres índices —código completo,
  prefijo de 5 y prefijo de 3— y un método `_resolver_sector_cpv()` que los consulta de más
  específico a menos. La rama muerta `853* → Social` de la red por división queda retirada.
* El motivo registrado dice **por qué vía** se resolvió: `CPV Core Sector Social +40 (por código
  completo)` frente a `(por prefijo de 3 + prelación)`. Un sector asignado debe poder justificarse
  sin releer el código.

**Regresión**: `tests/test_sectorizacion_cpv.py`, 21 casos. Dos de ellos no afirman sobre ejemplos
elegidos a mano sino sobre el perfil entero —`test_ningun_cpv_del_perfil_queda_huerfano` exige que
todo CPV declarado resuelva al sector que lo declara, y `test_ningun_cpv_esta_declarado_en_dos_sectores`
impide reintroducir el duplicado—. La primera habría destapado H-26 el primer día.
`test_la_correccion_no_altera_el_score` fija el contrato del cambio: sólo se mueve el sector.

**Verificado en vivo** (Convención C7) sobre una base sembrada con seis expedientes de tres
sectores, recorriendo el camino real Filtro → `upsert_oportunidad` → SQLite → API:

```
SOC-001  85312000  Social      (por código completo)        79 pts
SOC-002  85312100  Social      (por código completo)        65 pts
SOC-003  85322000  Social      (por prefijo de 3 + prelación) 65 pts
EDU-001  85312110  Educativo   (por código completo)        79 pts
EDU-002  80110000  Educativo   (por código completo)        65 pts
CUL-001  92510000  Cultural    (por código completo)        71 pts
```

El Funnel del Cockpit muestra los seis expedientes sin filas fantasma y la consola queda limpia.
La base sembrada se eliminó al terminar: el proyecto vuelve al estado de instalación nueva.

> **Observación, no defecto**: el Cockpit **no muestra el sector en ninguna pantalla**. `sector`
> sólo aparece en `frontend/src/types/api.ts`, sin ningún componente que lo pinte. Por eso la
> Convención C7 no podía destapar H-26 aunque se hubiera arrancado la aplicación: el dato viaja
> desde el Filtro hasta la respuesta de la API y ahí se detiene. Conviene decidir si la
> sectorización debe verse en pantalla o si su destino es el reporting de capas posteriores.

---

## Hallazgo de la apertura de la Capa 9 — 2026-08-07

### H-27 · El estado archivado se escribe con dos grafías distintas 🟢 CERRADO (Capa 9, Paso 3)

`EstadoLicitacionEnum` declara `"Inactiva"` y `"Anulada_Administracion"` capitalizados
(`src/api/schemas.py:75-76`), mientras el Radar escribe `'inactiva'` y `'anulada_administracion'`
en minúsculas (`src/memoria.py:1102` y `1112`). **Dos grafías del mismo estado en la misma
columna.**

```
Declara el enum:   "Inactiva"   "Anulada_Administracion"
Escribe el Radar:  'inactiva'   'anulada_administracion'
```

**Por qué no ha roto nada.** `LoteSchema.estado_operativo` está tipado como `str` y no contra el
enum, así que la API no valida el valor; y el Radar compara siempre en minúsculas
(`estado_op.lower()`). Además el Cockpit no ofrece esos dos estados en su filtro de Funnel, de modo
que nadie ha consultado nunca por ellos. El sistema es **coherente por accidente**.

**Por qué importa a partir de ahora.** El Depurador de la Capa 9 tiene que seleccionar lo archivado
y comprobar por qué estados pasó cada lote. Un `WHERE estado_operativo = 'Inactiva'` no devolvería
**ninguna fila**, y la invariante que protege la memoria comercial depende de comparar estados con
exactitud: un falso negativo ahí significa borrar algo que no debía borrarse.

**No era tan latente como pareció al catalogarlo.** Al cablear el Paso 2 apareció que
`obtener_documentos_para_purga()` (`memoria.py`) filtraba con
`estado_operativo NOT IN ('inactiva', 'anulada_administracion')`: **ya había código productivo
dependiendo de la grafía accidental**. Normalizar sin tocar esa consulta habría dejado la purga
documental sin encontrar nada, en silencio y sin error.

**Cerrado con** (Capa 9, Paso 3):

* Constantes `ESTADO_INACTIVA` y `ESTADO_ANULADA_ADMINISTRACION` con la grafía canónica —la
  capitalizada, la que ya declaraba el enum y usan todos los demás estados—.
* El Radar escribe esas constantes en lugar de literales en minúsculas.
* La migración a v6 **normaliza las filas existentes**, con la copia preventiva ya tomada.
* `obtener_documentos_para_purga()` compara con `LOWER(...)`, de modo que es indiferente a la
  grafía almacenada y sigue funcionando también en bases migradas desde v5.

**Regresión**: `tests/test_migracion_v6.py`, tres pruebas — que la migración normaliza lo viejo,
que el Radar escribe la grafía canónica, y que la consulta de purga tolera ambas. La segunda
importa tanto como la primera: no basta con arreglar lo almacenado si se sigue escribiendo mal.

---

### H-29 · El Cockpit anunciaba una versión de esquema codificada a mano 🟢 CERRADO (Capa 9, Paso 3)

Al arrancar la aplicación tras migrar a v6 (Convención C7), el panel de KPIs seguía diciendo
*"Métricas consolidadas en tiempo real desde **SQLite v5** (WAL Mode)"* y el tooltip de
autodiagnóstico, *"Autodiagnóstico **SQLite v5**"*. La base era v6.

Tres literales en `frontend/src/`: `KPIDashboard.tsx`, `HealthIndicator.tsx` y `DetailDrawer.tsx`.
Ninguno rompía nada — es de la misma familia que H-21, H-22 y H-23: **la pantalla afirmaba algo
que no era cierto**. Y lo llamativo es dónde: el panel de *autodiagnóstico*, que es justamente
donde alguien va a mirar cuando sospecha que algo no cuadra.

**Cerrado con**: el autodiagnóstico lee `schema_version` del propio `/api/v1/health`, que ya lo
exponía y que el tipo TypeScript ya declaraba; en los otros dos el número era decorativo y se
retira, porque un dato que sólo puede volver a desfasarse no aporta nada.

**Verificado en vivo**: el tooltip muestra *"Autodiagnóstico SQLite v6"* leyéndolo de la API, y
`npm run build` compila limpio con `tsc -b` en modo estricto.

---

### H-28 · El registro de respaldo del Lector escribía contra el directorio de trabajo 🟢 CERRADO

`Lector.registrar_log_JSONL()` delega en la Capa 3, pero tiene una vía de respaldo para
cuando la base de datos no está disponible. Esa vía resolvía la ruta así:

```python
log_path = os.path.join("data", "pipeline.jsonl")   # relativa al directorio de trabajo
os.makedirs("data", exist_ok=True)
```

Es **el último resto de H-18**, que el Paso D3 dio por cerrado normalizando `config/` y
`data/` en todo el proyecto. Sobrevivió porque este bloque sólo se ejecuta cuando `self.db`
no está disponible, y en la práctica siempre lo está. `ruta_datos` ya estaba importado en el
mismo fichero (`lector.py:19`) y se usa correctamente en las otras cinco resoluciones de ruta:
era el único punto que no lo usaba.

**Dos consecuencias, y la segunda es la grave**:

1. Lanzado desde otra carpeta, creaba un `data/` espurio donde no tocaba.
2. Al no pasar por `ruta_datos()`, **ignoraba `DATA_DIR_INCOOP`**. Durante la suite de
   pruebas habría escrito en el `data/` real del proyecto — exactamente lo que H-25 vino a
   impedir, y por la misma razón por la que `tests/conftest.py` redirige esa variable.

**Cerrado con**: `ruta_datos("pipeline.jsonl")` y `os.makedirs(os.path.dirname(log_path))`.

**Regresión**: `tests/test_rutas_proyecto.py::test_el_registro_de_respaldo_del_lector_no_escribe_contra_el_directorio_de_trabajo`,
que redirige `DATA_DIR_INCOOP`, se sitúa en un directorio de trabajo ajeno y exige las dos
cosas: que el registro aterrice en el directorio redirigido y que **no** aparezca un `data/`
en el directorio de trabajo. **Verificada contra el código anterior: falla.**

---

## Registro de decisiones tomadas

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-07-27 | **Gemini pasa a proveedor preferente; Ollama a opcional** | La herramienta debe funcionar en cualquier PC de la cooperativa. Además Ollama sólo garantiza JSON válido (`format: json`), no la forma correcta — era el proveedor con más probabilidad de fabricar un dictamen vacío. Ollama **no se elimina**: queda tras la interfaz `LLMProvider`, activable en equipos con GPU. |
| 2026-07-27 | **Resiliencia por reintentos, no por segundo proveedor** | Al retirar Ollama se pierde la redundancia. Se sustituye por reintentos con espera exponencial diferenciando 429 / 5xx / red, antes de diferir el pliego. |
| 2026-07-27 | **El riesgo de subrogación se ordena por trazabilidad del coste, no por tamaño de plantilla** | Sin la relación del Art. 130.1 es imposible presupuestar el coste laboral heredado. Ofertar a ciegas sobre la partida que más pesa en la estructura de Incoop es peor riesgo que una plantilla grande pero conocida. *Umbrales pendientes de validación final por el usuario.* |
| 2026-07-27 | **La integridad se exige al escribir, no al leer** | En la frontera de lectura, un dato incompleto se degrada a su valor por defecto; nunca rompe la pantalla. |
| 2026-08-06 | **Art. 145: el peso del precio por encima del 60 % es una señal negativa** | Se alinea con el README, que describe ese escenario como una guerra de precios desfavorable para Incoop. El predominio del juicio de valor **no** se penaliza: puede ser la ventaja competitiva de la cooperativa. Se descarta el criterio de menor carga procedimental del Art. 146.2. |
| 2026-08-06 | **El scoring comercial es determinista; el LLM informa, no puntúa** | El `ajuste_score` que propone el modelo se conserva como información trazable pero no se aplica. Aplicarlo junto a las reglas configuradas provocaba doble contabilidad del mismo hecho. |
| 2026-08-06 | **Lo que no se pudo medir, no puntúa** | Un análisis degradado no altera el score en ninguna dirección: bonificar también es inventar. La alerta llega al Cockpit marcada en vez de desaparecer. Ver Convención C6. |
| 2026-08-06 | **La suite de pruebas no sale a la red** | Una prueba que llama a un LLM real gasta cuota, tarda y depende de lo que conteste el modelo ese día. La verificación contra la API real vive en `tools/`. Ver Convención C5. |
| 2026-08-06 | **El proyecto se versiona en Git** | Hasta esa fecha no había historial ni forma de revertir. La herramienta contiene reglas comerciales sensibles y varios agentes de IA se turnan sobre ella. Repositorio: https://github.com/DonBorgiFR/licit-accion |
| 2026-08-06 | **La falta del desglose del Art. 130.1 eleva el riesgo a ALTO, pero no descarta** | Descartaba automáticamente cualquier licitación con subrogación cuyo pliego no aportara la relación de personal, fueran 2 trabajadores o 200. Muchos pliegos incumplen el Art. 130.1 y el desglose suele obtenerse solicitándolo al órgano de contratación: dejaba fuera concursos ganables. La decisión vuelve al analista humano. |
| 2026-08-06 | **El tamaño de plantilla determina el veto; la documentación, el nivel de riesgo** | Consecuencia obligada de la decisión anterior: como se aplica la primera regla que encaja, bajar la falta de desglose a ALTO sin reordenar la matriz habría dejado el peor caso puntuando mejor que el segundo peor. El único CRÍTICO es ahora el de más de 40 trabajadores. |
| 2026-08-06 | **La subrogación acotada y documentada recibe una bonificación intermedia (+2)** | De 1 a 5 personas con el desglose aportado es un riesgo real pero acotado y presupuestable. Antes sumaba 0, igual que el tramo MEDIO de 20 personas, porque la bonificación de +5 exigía que no hubiera subrogación ninguna. |
| 2026-08-06 | **Las alertas descartadas por reglas se guardan, fuera del canal principal** | Sin registro no hay auditoría ni reevaluación: al ajustar un umbral o cambiar los PMP no quedaba nada que revisar, y cada ejecución las reprocesaba desde cero. Se guardan para auditar, no para ocupar la pantalla. |
| 2026-08-06 | **El descarte automático y el manual son estados distintos** | `DESCARTADA_POR_REGLAS` y `DESCARTADA_TEMPRANA` no se fusionan. Si mañana se baja un umbral procede reevaluar lo que descartó la máquina; lo que rechazó una persona debe quedarse como está. |
| 2026-08-07 | **`85312110` se queda en el sector `educativo`** | "Guarderías escolares sociales" es en su base una guardería, próxima a las escoles bressol, aunque su código cuelgue de la rama de asistencia social. La clasificación del perfil ya era correcta. La consecuencia es que H-26 **no** puede corregirse moviendo el CPV: hacerlo eliminaría el síntoma etiquetando como social justo el único CPV de la familia que no lo es. |
| 2026-08-07 | **Lo descartado por una persona no se elimina nunca** | Un lote en `Descartada` bloquea la eliminación física del expediente igual que uno adjudicado. El motivo es **evitar reprocesos**: si se borrase, el pipeline volvería a capturarlo y a presentarlo, y el equipo comercial gastaría atención en reevaluar algo que ya descartó. El coste de conservar la fila es despreciable; el de mirarla dos veces, no. Coincide con el criterio que el Paso D5 fijó para el Centinela. |
| 2026-08-07 | **La memoria comercial no se purga jamás (Capa 9)** | Todo lote que alcanzó `Presentada`, `Adjudicada` o `Perdida` es intocable, con su adjudicatario, importe, horas internas, costes y garantías. Es la población de `vista_win_rate` y `vista_analisis_CAC`: borrarla no libera espacio relevante —son filas, no ficheros— y destruye la única serie histórica con la que la cooperativa puede saber si está mejorando. Lo purgable es el **peso documental**: PDFs, texto extraído y copias. |
| 2026-08-07 | **La retención documental sube a 180 días y deja de estar codificada a fuego** | Los 90 días actuales viven como literal en la llamada de `main.py` al Lector, invisibles y no versionados (incumple la Regla 4). Y se quedan cortos: el ciclo completo de una licitación —publicación, presentación, evaluación y adjudicación— los supera con frecuencia, de modo que la purga podía borrar el pliego de un concurso todavía sin resolver. Pasan a `config/retencion.yaml` con número de versión, registrado en cada purga. |
| 2026-08-07 | **La purga se ejecuta en dos tiempos y nunca a ciegas** | El disparador es mixto: el peso documental se purga solo por política en cada ejecución, pero archivar o eliminar expedientes exige que una persona lo pida desde el Cockpit **tras previsualizar exactamente qué va a desaparecer**. Toda purga manual crea copia de seguridad previa; si la copia falla, la purga no se ejecuta (Regla 5). |
| 2026-08-07 | **La sectorización por CPV se resuelve por código completo, no por orden del YAML** | Hoy gana el primer sector del diccionario que case un prefijo, así que la clasificación depende del orden en que estén escritas las claves — un criterio que nadie declaró y que nadie ve. Los prefijos de 3 **y de 5** dígitos están compartidos entre `educativo`, `social` y `consultoria`, de modo que ni "sólo 5 dígitos" ni "prefijo más largo" bastan (5/9 aciertos ambas). El código completo primero acierta 8/9; el empate restante exige una prelación entre sectores declarada explícitamente. |
