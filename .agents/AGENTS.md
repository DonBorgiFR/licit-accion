# Reglas de Desarrollo del Proyecto: Ecosistema de Licitaciones

Este archivo define las directrices obligatorias de colaboración y desarrollo para el diseño e implementación del **Ecosistema Automático de Licitaciones (bfr_incoop)**.

---

## 🚦 EMPIEZA AQUÍ (para cualquier agente o persona que retome el proyecto)

> El proyecto se desarrolla en sesiones sucesivas y **con agentes de IA distintos** (Antigravity, Claude Code y otros). Este bloque es el punto de entrada único: léelo antes de tocar nada.

**Orden de lectura obligatorio:**

1. **Este archivo** — reglas de trabajo, convenciones técnicas y estado por capas.
2. **`.agents/AUDITORIA_2026-07-27.md`** — hallazgos con evidencia reproducible. **No vuelvas a diagnosticar lo que ya está ahí**: cada hallazgo indica cómo se reprodujo y si está abierto o cerrado.
3. **`README.md`** — diseño funcional, marco LCSP y detalle de cada capa.

**Estado en una línea**: Capas 1-8 construidas; remediación pre-Capa 9 cerrada (H-01 a H-25), suite en verde y Cockpit compilado y **verificado arrancándolo contra la base real**. **La Capa 9 está lista para abrirse**, pero queda **un hallazgo abierto, H-26**, detectado el 2026-08-07 al revisar la cobertura de CPVs: conviene resolverlo **antes de la primera ejecución real**, porque escribe un dato erróneo en la base.

**Control de versiones**: el proyecto vive en **https://github.com/DonBorgiFR/licit-accion** desde el 2026-08-06. Antes de esa fecha no había historial: cualquier estado anterior sólo existe en las actas de este directorio.

**Verificación antes de dar nada por bueno:**

```bash
python -m pytest tests/ -q          # debe dar 175/175
```

**Punto de entrada del pipeline**: `python run.py` desde la raíz. **Nunca** `python src/main.py`.

### ⏭️ Siguiente tarea concreta: abrir la Capa 9

Bloque 1 — Cimientos 🟢 y Bloque 2 — Coherencia LCSP 🟢 están cerrados. El detalle está más abajo, en "Pasos completados"; el contrato del Bloque 2 vive en [`CONTRATO_BLOQUE_2.md`](CONTRATO_BLOQUE_2.md).

**Nada bloquea la Capa 9.** Node.js 24.19.0 LTS quedó instalado el 2026-08-06 y `npm run build` se ejecuta limpio, con `tsc -b` en modo estricto sin errores.

**Aviso para no repetir un diagnóstico equivocado**: durante un tiempo se dio por hecho que `frontend/dist/` estaba desfasado, deduciéndolo de su fecha de modificación. Era falso. Al recompilar, Vite generó **exactamente los mismos nombres de fichero** (`index-B6BIdKdG.js`, `index-BKUbaev-.css`), y esos nombres son un hash del contenido: el bundle ya estaba al día. El proyecto vive en OneDrive, así que lo más probable es que se compilara en otra máquina. **La fecha de un artefacto no dice de qué fuente salió: compruébese el contenido.**

**Decisiones ya tomadas que no hay que volver a discutir**: ver la tabla de decisiones al final del dosier de auditoría.

### ⚠️ Pendiente de acción del usuario

**Nada que decidir; queda ejecutar la corrección de H-26** (el sector `social` es inalcanzable). La
cuestión de negocio se resolvió el 2026-08-07: `85312110` **se queda en `educativo`**, porque en su
base es una guardería. Eso descarta la vía barata de reclasificar el CPV y obliga a corregir el
algoritmo: **código completo primero, prefijo después, con un orden de prelación explícito entre
sectores** para los empates. Medido, ese criterio acierta 8 de 9 casos frente a 1 de 9 hoy; las dos
alternativas que parecían obvias se quedan en 5 de 9. Detalle y medición en el dosier.

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

### 🔧 Herramientas de verificación manual

No forman parte de la suite porque consumen cuota real de la API. Requieren `GEMINI_API_KEY` en el entorno.

```bash
python tools/verificar_proveedor_llm.py         # ¿responde el modelo configurado? ¿cuántos tokens gasta?
python tools/verificar_matriz_subrogacion.py    # ¿dos modelos distintos coinciden? (debe dar 5/5)
```

---

## 🎯 Enfoque de Desarrollo por Capas (Bottom-Up)

1. **Desarrollo Estrictamente Secuencial**:
   - El sistema se construirá de forma estrictamente secuencial, de la Capa 1 a la Capa 10.
   - **No se saltará de capa** ni se diseñará o codificará nada de una capa superior sin haber validado completamente la capa anterior con el usuario.
   - Las discusiones, preguntas y planes se centrarán **únicamente** en la capa activa en la que se esté trabajando. Está prohibido solicitar decisiones sobre capas futuras antes de llegar a ellas.

2. **Validación Conjunta**:
   - Cada capa requiere una validación práctica del script o componente por parte del usuario.
   - Una vez que la capa activa funcione correctamente y cumpla los objetivos, el agente y el usuario acordarán el paso a la siguiente capa.

3. **Perfil del Usuario y Comunicación**:
   - El usuario es un gestor/ingeniero sénior que no programa habitualmente pero entiende de sistemas y negocio.
   - Las explicaciones deben ser conceptuales, detallando el *cómo* y el *por qué* de las decisiones técnicas y de negocio (LCSP).
   - Se evitará el código excesivamente denso sin comentarios y se explicarán los obstáculos encontrados para resolverlos en equipo.

4. **Implementación Paso a Paso dentro de cada Capa**:
   - Cada capa se descompone en pasos definidos en el README.md del proyecto.
   - Se presentará un plan de implementación detallado para cada paso antes de codificar.
   - El usuario valida cada paso antes de avanzar al siguiente.

---

## 🛑 Reglas Obligatorias de Rigor Operativo (Las 14 Reglas)

### 1. Desarrollo por Capas con Contratos Obligatorios
Antes de implementar cualquier paso o capa, el agente debe entregar un Contrato de Servicio que defina detalladamente: Inputs, Outputs, Precondiciones, Postcondiciones, Side-effects, Errores tipados, Estados resultantes, Eventos JSONL y el Versionado del paso. **Sin contrato, no se implementa.**

### 2. Máquinas de Estado en Cada Paso
Cada paso de procesamiento documental debe formalizarse a través de una máquina de estados explícita con estados válidos, transiciones permitidas, transiciones prohibidas, eventos disparadores y estado final esperado. **Sin máquina de estados, no se implementa.**

### 3. Trazabilidad JSONL Obligatoria
Cada paso del pipeline debe registrar de forma determinista y estructurada eventos de inicio, fin, decisiones, errores y métricas operativas en `data/pipeline.jsonl`. **Sin trazabilidad, el paso no se considera completado.**

### 4. Versionado Obligatorio
Todo cambio o criterio operativo de clasificación, extracción o esquema debe ser versionado explícitamente y centralizado en un archivo de configuración si procede, etiquetando el histórico en base de datos. **Sin versionado, no se implementa.**

### 5. Modo Degradado Obligatorio
Cada paso del pipeline documental debe definir con precisión su comportamiento en "modo degradado" (como OCR diferido por falta de binarios externos o fallback de scraping HTML por fallos de API), registrando eventos de degradación. **Sin modo degradado, no se implementa.**

### 6. Healthcheck Obligatorio Antes de Ejecutar
Antes de procesar, cada módulo ejecutará un autodiagnóstico validando dependencias críticas, binarios externos, permisos de lectura/escritura en disco y conectividad de BD, generando un objeto resumido de estado. **Sin healthcheck satisfactorio, no se ejecuta.**

### 7. Reporting Determinista Obligatorio
Al culminar la ejecución, cada paso debe presentar un resumen final claro del procesamiento, incluyendo métricas cuantitativas, estados resultantes de documentos y diagnósticos de errores. **Sin reporting, no se aprueba el paso.**

### 8. Plan Detallado Obligatorio Antes de Codificar
Cualquier tarea de desarrollo requiere la entrega previa de un plan de implementación técnico exhaustivo que describa la arquitectura, contratos, riesgos y mitigaciones del paso. **Sin plan detallado, no se implementa.**

### 9. Validación del Usuario en Cada Paso
El agente no avanzará de paso ni escribirá código funcional sin recibir una validación conceptual, operativa y técnica explícita del paso o plan anterior por parte del usuario. **Sin validación, no se avanza.**

### 10. Cada Capa Debe Ser Operativa, No Solo Funcional
Una capa se considera completada únicamente si es determinista, idempotente, trazable, versionada, auditable, resiliente y se encuentra totalmente integrada al pipeline de ejecución. **Si funciona pero no es operativa, no se aprueba.**

### 11. Prohibido saltar capas o pedir decisiones futuras
Todas las discusiones y desarrollos deben restringirse únicamente a la capa activa o al paso activo, evitando mezclar conceptos o solicitar decisiones de diseño sobre capas superiores. **La violación conlleva el rechazo del paso.**

### 12. Prohibido improvisar lógica no alineada con el README
Cualquier lógica de negocio, modelo de datos o principio de adaptabilidad debe respetar estrictamente el diseño del proyecto recogido en el `README.md`. Modificaciones extraordinarias requieren justificación y aprobación previa.

### 13. Prohibido generar código sin contexto
El agente debe documentar y justificar las decisiones de diseño arquitectónicas y operativas de cada bloque de código, explicando los riesgos asociados y su encaje en el ecosistema.

### 14. Prohibido romper la integridad del ecosistema
El desarrollo debe garantizar de forma estricta la no regresión de las capas previamente validadas, la consistencia de la base de datos local SQLite y la compatibilidad futura con modelos de IA.

---

## 🔒 Convenciones Técnicas Obligatorias

Estas convenciones nacen de defectos reales detectados en la auditoría del 2026-07-27. No son preferencias de estilo: cada una corresponde a un fallo que llegó a producción sin ser detectado.

### C1. Raíz de importación única (`src.`)
Todo módulo interno se importa **siempre** de forma absoluta bajo el prefijo `src.` (`from src.memoria import Memoria`). Quedan prohibidos:
* Los imports planos (`from memoria import ...`).
* Los bloques `try: from src.x ... except ModuleNotFoundError: from x ...`.
* Las manipulaciones de `sys.path` en módulos o en pruebas.

**Por qué**: dos raíces conviviendo cargan el mismo fichero como dos objetos-módulo distintos, con clases distintas que fallan cualquier `isinstance`. Además ocultó durante toda la Capa 6 que el pipeline no arrancaba.

**Punto de entrada del pipeline**: `python run.py` (o `python -m src.main`) desde la raíz del proyecto. Nunca `python src/main.py`.

### C2. Prohibido el `except` amplio que silencia sin registrar
Un `except Exception` sólo es admisible si (a) registra el error con su tipo en `data/pipeline.jsonl` **y** (b) el estado resultante es distinguible del estado de éxito. Está prohibido degradar a un valor por defecto que el consumidor no pueda diferenciar de un resultado real.

**Por qué**: `except Exception: return None` en la factoría LLM del Centinela ocultó tres defectos encadenados durante toda una capa. Y un fallo de parseo se persistía como análisis `COMPLETADO` con los riesgos a `False`.

### C3. El Modo Degradado se afirma con datos, nunca con heurísticas de texto
El estado degradado se expresa mediante un campo estructurado (`modo_degradado: bool`, `estado_analisis`), jamás inspeccionando cadenas de texto libre generadas por un LLM. Todo estado degradado debe ser **visible en el Cockpit**: un dato poco fiable mostrado sin distintivo es peor que un dato ausente, porque induce a decidir sobre él.

### C4. Las pruebas ejercitan la ruta real, no sólo la inyectada
Si un componente tiene una factoría o una ruta de arranque por defecto, debe existir al menos una prueba que la ejercite **sin inyección de dependencias**.

**Por qué**: los tests del Centinela inyectaban siempre `proveedor_llm=` simulado, por lo que nunca tocaron la factoría real, que estaba rota desde el primer día.

**Matiz añadido el 2026-08-06**: "ejercitar la ruta real" no significa "salir a la red". Una vez reparada la factoría, `proveedor_llm=None` construía un `GeminiProvider` de verdad y la suite empezó a llamar a la API en cada ejecución. La prueba de la factoría verifica **qué proveedor construye**; la verificación contra la API real vive en `tools/`, fuera de la suite. Ver C5.

### C5. La suite de pruebas no sale a la red

Ninguna prueba puede depender de un servicio externo. Un componente con arranque automático debe ofrecer una vía explícita para desactivarlo (`autoinicializar_proveedor=False` en `AnalistaBoletinesIA`), no confiar en que pasar `None` baste.

**Por qué**: una prueba que llama a un LLM real gasta cuota del usuario, tarda, y su resultado depende de lo que conteste el modelo ese día. Deja de ser una red de seguridad y pasa a ser una fuente de ruido. Se detectó porque el e2e de la Capa 6 fallaba de forma intermitente tras reparar la factoría.

La suite tampoco puede escribir en el `data/` del proyecto. `tests/conftest.py` redirige `DATA_DIR_INCOOP` a un directorio temporal, y lo hace **al importarse el fichero, no dentro de un fixture**: `src/api/dependencies.py` crea su gestor de trazabilidad como singleton de módulo y ese constructor ya crea la carpeta de destino, lo que ocurre durante la recolección de pruebas, antes de que se ejecute ningún fixture.

**Cómo se comprueba — y cómo NO**: ⚠️ **bloquear la red lanzando una excepción no sirve**. Se intentó y dio un falso verde: un `except Exception` amplio en el analista convertía el bloqueo en "modo degradado" y las pruebas pasaban igual, mientras la suite seguía llamando a Gemini en cada ejecución. Es el mismo defecto que estas convenciones combaten, aplicado a su propia verificación.

El método correcto **registra los intentos sin impedirlos**, para que ningún `except` pueda ocultarlos:

```python
# sitecustomize.py en el PYTHONPATH — envuelve getaddrinfo SIN lanzar excepciones
import atexit, socket
_ext, _gai = set(), socket.getaddrinfo
def gai(host, *a, **k):
    if str(host) not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        _ext.add(str(host))
    return _gai(host, *a, **k)
socket.getaddrinfo = gai
atexit.register(lambda: print("EXTERNOS:", _ext or "(ninguno)"))
```

Comprobación completa: borrar `data/`, ejecutar la suite y verificar las tres cosas — que pasa entera, que no aparece ningún dominio externo, y que `data/` **no llega a crearse**.

### C6. Lo que no se pudo medir, no puntúa

Un análisis degradado no puede alterar un score en ninguna dirección. No basta con no penalizar: **bonificar también es inventar**. El estado degradado se transporta en un campo estructurado (`modo_degradado`) y, cuando el vocabulario del dominio pueda malinterpretarse, con un valor propio y distinguible (`nivel_interes="DESCONOCIDO"`, que **no** es sinónimo de `"NULO"`).

**Por qué**: en la Capa 6, un fallo de parseo se rellenaba con `NULO` y restaba −30 pts (la alerta desaparecía), mientras que un fallo de conexión declaraba `MEDIO` y sumaba +15 pts (la alerta subía de prioridad). Como la IA del Centinela nunca funcionó, ese bonus fantasma se aplicó a **todas** las alertas: era la diferencia entre superar el umbral y no superarlo.

### C7. Una capa no se cierra sin arrancar la aplicación contra la base real

La suite en verde y el código revisado no bastan. Antes de dar una capa por cerrada hay que levantar la API y el Cockpit contra `data/licitaciones.db` y **mirar la pantalla**, comparando cada cifra visible con la consulta directa a la base de datos.

```bash
python -m uvicorn src.api.main:app --port 8000
cd frontend && npm run dev          # http://localhost:5173
```

**Por qué**: con la suite en 171/171 y veinte hallazgos cerrados, arrancar la aplicación destapó otros tres en diez minutos (H-21, H-22, H-23). Los tres afectaban a lo que el usuario ve y ninguno rompía nada: un contador sobre una población distinta a su propio desglose, 29 filas fantasma en la tabla con la que se decide a qué concurso presentarse, y una columna de riesgo que contradecía el único análisis real de la base. Ningún test los habría detectado, porque todos afirmaban sobre datos sintéticos coherentes; el defecto estaba en la unión entre consulta, contrato y pantalla.

**Comprobación mínima**: que cada cifra de cabecera cuadre con su desglose, que ninguna fila salga a cero, y que lo que se afirma de un pliego proceda de haberlo leído.

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
* **Capa 9** - El Histórico y Depurador (Archivo y Purga de Datos): 💤
* **Capa 10** - El Lanzador y Despertador (Silent Launcher VBS y Servicio Local): 💤

---

## 🔧 Fase Activa: Auditoría Técnica y Remediación (pre-Capa 9)

> Auditoría integral realizada el **2026-07-27** sobre las Capas 1 a 8. Antes de abrir la Capa 9 se cierran los defectos bloqueantes detectados. Cada paso se valida con el usuario y se verifica con la suite completa antes de avanzar.
>
> 📄 **Evidencia y detalle de cada hallazgo: [`.agents/AUDITORIA_2026-07-27.md`](AUDITORIA_2026-07-27.md)** — 14 hallazgos catalogados (H-01 a H-14), con la forma de reproducirlos y la prueba de regresión que impide que vuelvan. Consúltalo antes de rediagnosticar nada.

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

### Pasos pendientes

La remediación previa a la Capa 9 está cerrada: 25 hallazgos catalogados (H-01 a H-25), 25 cerrados con prueba de regresión o verificación reproducible.

**Queda H-26**, posterior y ajeno a esa remediación: apareció el 2026-08-07 al retomar la pregunta aplazada sobre la cobertura de CPVs. El sector `social` es inalcanzable —lo eclipsa `educativo` por una colisión de prefijos de 3 dígitos— y `sector_detectado` se persiste en la base. **No bloquea la Capa 9**, pero sí conviene cerrarlo antes de la primera ejecución real. Pendiente de decidir la vía de corrección con el usuario.

**Los datos de la beta se borraron el 2026-08-06** a petición de la dirección del proyecto: la base, los documentos descargados, los registros y los informes. El sistema queda como una instalación nueva. Los registros de julio no eran información comercial —10 de 22 lotes tenían el plazo vencido y todos estaban puntuados con la lógica anterior al Bloque 2—, y conservarlos habría mezclado dos generaciones de puntuación en la misma tabla.





