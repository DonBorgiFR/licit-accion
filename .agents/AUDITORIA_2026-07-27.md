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
sistema funcione. Ver reglas C1–C4 en `AGENTS.md`.

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

## Hallazgos ABIERTOS

### H-05 · La IA del Centinela nunca ha funcionado 🔴 ABIERTO — prioridad alta

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

**Pendiente**: reparar en el Paso C2. Debe añadirse una prueba que ejercite la factoría **sin**
inyección.

---

### H-06 · El modelo LLM configurado no funciona con la cuenta actual 🔴 ABIERTO — prioridad alta

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

---

### H-07 · Concurrencia SQLite: la API devuelve 503 bajo escritura del pipeline 🟠 ABIERTO — Bloque 1

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

---

### H-08 · Los KPIs del dashboard son aritméticamente imposibles 🟠 ABIERTO — Bloque 2

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

---

### H-09 · Escalas de scoring incompatibles entre capas 🟠 ABIERTO — Bloque 2

`src/filtro.py` no acota el resultado: medido **165 puntos** en un caso favorable realista, y
puede ser negativo. Pero `RecalibradorScoring` trunca a `[0, 100]`, sus umbrales
(`umbral_recomendada: 65`) asumen esa escala, y el esquema de la API declara `score_total` como
0-100. Dos licitaciones de 110 y 165 puntos brutos se muestran ambas como 100.

---

### H-10 · La detección de subrogación ignora las negaciones 🟠 ABIERTO — Bloque 2

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

### H-11 · Doble penalización del mismo riesgo 🟠 ABIERTO — Bloque 2

La Capa 2 resta −20 por subrogación. La Capa 5 recalibra **partiendo de ese score ya penalizado**
y vuelve a restar −15/−25. Un contrato con subrogación crítica acumula −45 por un único hecho.

---

### H-12 · Faltan 3 de las 6 cláusulas críticas del README 🟠 ABIERTO — Bloque 2

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

---

### H-13 · El Cockpit no puede gestionar el estado por lote 🟠 ABIERTO — Bloque 2

`TransicionEstadoLicitacion` no lleva `lote_numero`, así que la API siempre muta el lote 1.
Pero `useApiMutations.ts` aplica optimistamente el nuevo estado a **todos** los lotes: el usuario
ve cambiar los cinco, el backend cambia uno, y el refresco revierte la vista. Anula el modelo 1:N
que el README describe como razón de ser de la Capa 3.

El *rollback* tampoco es atómico pese a la documentación: `onMutate` guarda copia del detalle pero
no de las listas paginadas que también modifica.

---

### H-14 · Higiene del proyecto 🟠 ABIERTO — Bloque 1

- `requirements.txt` no declara `fastapi`, `uvicorn`, `pydantic`, `starlette`, `httpx` ni `pytest`.
  Un clon del repositorio no arranca las Capas 7 y 8.
- No hay `.gitignore` ni gestión de `.env`. **Ya hay una `GEMINI_API_KEY` en el entorno del
  equipo**: si el proyecto se convierte en repositorio git, esto pasa a ser urgente.
- TypeScript **no tiene `strict` activado** en ningún `tsconfig*.json`. Toda la anotación
  `?: X | null` del espejo de tipos es decorativa: el compilador no la verifica.
- El middleware de trazabilidad hace E/S de fichero **síncrona** dentro de un `async def`,
  bloqueando el bucle de eventos en cada petición. La rotación de logs no está sincronizada.

---

## Registro de decisiones tomadas

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-07-27 | **Gemini pasa a proveedor preferente; Ollama a opcional** | La herramienta debe funcionar en cualquier PC de la cooperativa. Además Ollama sólo garantiza JSON válido (`format: json`), no la forma correcta — era el proveedor con más probabilidad de fabricar un dictamen vacío. Ollama **no se elimina**: queda tras la interfaz `LLMProvider`, activable en equipos con GPU. |
| 2026-07-27 | **Resiliencia por reintentos, no por segundo proveedor** | Al retirar Ollama se pierde la redundancia. Se sustituye por reintentos con espera exponencial diferenciando 429 / 5xx / red, antes de diferir el pliego. |
| 2026-07-27 | **El riesgo de subrogación se ordena por trazabilidad del coste, no por tamaño de plantilla** | Sin la relación del Art. 130.1 es imposible presupuestar el coste laboral heredado. Ofertar a ciegas sobre la partida que más pesa en la estructura de Incoop es peor riesgo que una plantilla grande pero conocida. *Umbrales pendientes de validación final por el usuario.* |
| 2026-07-27 | **La integridad se exige al escribir, no al leer** | En la frontera de lectura, un dato incompleto se degrada a su valor por defecto; nunca rompe la pantalla. |
