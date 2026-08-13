# Reglas de Desarrollo del Proyecto: Ecosistema de Licitaciones

Este archivo define las directrices obligatorias de colaboración y desarrollo para el diseño e
implementación del **Ecosistema Automático de Licitaciones (bfr_incoop)**.

> **Aquí sólo hay reglas, y por eso este fichero casi no cambia.** El estado del proyecto —dónde
> estamos, qué toca ahora, qué se cerró— vive en [`ESTADO.md`](ESTADO.md). Si vas a anotar el
> resultado de un paso, va allí. *(Separados el 2026-08-13: tenerlo todo junto producía deriva,
> y en una sola revisión aparecieron tres recuentos distintos del mismo dato.)*

---

## 🚦 EMPIEZA AQUÍ (para cualquier agente o persona que retome el proyecto)

> El proyecto se desarrolla en sesiones sucesivas y **con agentes de IA distintos** (Antigravity,
> Claude Code y otros). El estado canónico **no vive en la conversación**: vive en `.agents/`.

**Orden de lectura obligatorio:**

1. **[`ESTADO.md`](ESTADO.md)** — dónde está el proyecto y cuál es la tarea activa.
2. **Este archivo** — las 14 Reglas de Rigor Operativo y las 7 Convenciones Técnicas. **Son de
   obligado cumplimiento**, no recomendaciones: cada convención nació de un defecto real que llegó
   a producción.
3. **[`AUDITORIA_2026-07-27.md`](AUDITORIA_2026-07-27.md)** — los hallazgos con su evidencia
   reproducible. **No rediagnostiques lo que ya está ahí.**
4. **[`../README.md`](../README.md)** — diseño funcional, marco LCSP y detalle de cada capa.

**Lo que no cambia nunca:**

* Punto de entrada del pipeline: `python run.py` desde la raíz. **Nunca** `python src/main.py`.
* Verificación antes de dar nada por bueno: `python -m pytest tests/ -q`.
* No se salta de capa, no se codifica sin plan validado por el usuario, y no se cierra una capa
  sin arrancar la aplicación contra la base real (Convención C7).

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


## 🔧 Herramientas de verificación manual

No forman parte de la suite porque consumen cuota real de la API. Requieren `GEMINI_API_KEY` en el entorno.

```bash
python tools/verificar_proveedor_llm.py         # ¿responde el modelo configurado? ¿cuántos tokens gasta?
python tools/verificar_matriz_subrogacion.py    # ¿dos modelos distintos coinciden? (debe dar 5/5)
```

---
