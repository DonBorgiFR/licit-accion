# 📡 Ecosistema Automático de Licitaciones (bfr_incoop)

> **Estado del producto: Beta 0.2 (2026-08-06).** Las Capas 1–8 están implementadas y se
> encuentran en estabilización antes de abrir las Capas 9 y 10. El sistema no contiene datos
> operativos reales versionados: los datos locales se usan exclusivamente para pruebas. No debe
> tomarse una decisión de licitación sin verificar el pliego y las fuentes oficiales.
>
> **Remediación pre-Capa 9**: los Bloques 1 (cimientos de infraestructura) y 2 (coherencia de
> negocio LCSP) están cerrados, con la suite en **173/173** y sin ningún hallazgo de auditoría abierto. Queda pendiente abrir la
> Capa 9: ninguno. El Cockpit compila limpio con `tsc -b` en modo estricto y su bundle está al día.
>
> **Repositorio**: https://github.com/DonBorgiFR/licit-accion · **Estado detallado por capas,
> hallazgos y decisiones**: [`.agents/`](.agents/) — `AGENTS.md` es el punto de entrada.

## 🎯 Objetivo del Proyecto

Construir un **sistema automatizado de inteligencia de licitaciones** que permita a **Incoop** detectar, filtrar y analizar oportunidades de contratación pública de forma sistemática, reduciendo drásticamente el tiempo de prospección y mejorando la tasa de acierto en la selección de licitaciones a las que presentarse.

### El problema que resuelve

Las plataformas oficiales de contratación pública en España (PCSP estatal y PSCP autonómica en Catalunya) publican **miles de licitaciones al año**. Para una empresa como Incoop, el proceso actual de prospección es:

1. **Manual y reactivo**: alguien revisa periódicamente los portales buscando oportunidades.
2. **Propenso a errores de omisión**: se pierden licitaciones por no revisar a tiempo o por volumen.
3. **Costoso en tiempo**: leer pliegos completos de licitaciones que finalmente no encajan consume horas de perfiles cualificados.
4. **Sin memoria histórica**: no existe un registro estructurado de qué se ha revisado, qué se ha descartado y por qué.

Este ecosistema transforma ese proceso artesanal en un **pipeline automatizado** que va desde la extracción de datos crudos hasta la notificación inteligente al equipo.

### Marco regulatorio

El sistema opera sobre licitaciones regidas por la **Ley 9/2017, de 8 de noviembre, de Contratos del Sector Público (LCSP)**, que transpone las Directivas europeas 2014/23/UE y 2014/24/UE. Los datos se obtienen exclusivamente de fuentes públicas oficiales (feeds RSS/Atom de los perfiles de contratante), cumpliendo con el principio de **publicidad y transparencia** recogido en el artículo 63 de la LCSP.

---

## 🔭 Alcance General del Ecosistema

### Qué incluye (IN scope)

| Área | Descripción |
|------|-------------|
| **Fuentes de datos** | Feeds RSS/Atom de la PSCP (Generalitat de Catalunya) y PCSP (Estado) |
| **Tipos de contrato** | Contratos de servicios y consultoría alineados con el perfil de Incoop |
| **Análisis** | Extracción de metadatos, filtrado por reglas de negocio, lectura automatizada de pliegos y análisis semántico con IA |
| **Persistencia** | Base de datos local con historial de licitaciones y su estado operativo |
| **Notificación** | Alertas automáticas al equipo con las oportunidades viables detectadas |
| **Entorno** | Sistema local *local-first* compuesto por un pipeline Python de línea de comandos, una micro-API REST (FastAPI) y un Cockpit visual en navegador (React SPA), todo ejecutándose en el equipo del usuario |

### Qué NO incluye (OUT of scope)

- ❌ **Presentación automatizada de ofertas**: el sistema informa y recomienda, pero la decisión y preparación de la oferta es humana.
- ❌ **Scraping de portales web**: solo se consumen fuentes de datos estructuradas (RSS/Atom), no se hace crawling de páginas HTML.
- ❌ **Cobertura de todas las CCAA**: en la primera versión, el alcance geográfico se limita a Catalunya (PSCP) y Estado (PCSP).
- ❌ **Aplicación web publicada o app móvil**: el Cockpit visual (Capa 8) es una SPA React que se sirve **en local** contra la API de la Capa 7; no se despliega en Internet, no es multiusuario y no hay versión móvil.
- ❌ **Licitaciones de otros poderes adjudicadores**: municipios, universidades o entes con plataformas propias fuera de PSCP/PCSP quedan fuera inicialmente.

---

## 🖥️ Requisitos del Sistema

> **Principio rector**: la herramienta debe funcionar en **cualquier PC del equipo**, no sólo en el del desarrollador. Por eso ningún requisito de hardware especializado puede ser obligatorio.

| Componente | Requisito / Configuración | Propósito en el Ecosistema |
|---|---|---|
| **Proveedor IA** | **Google Gemini API** (`GEMINI_API_KEY` en entorno) | **Proveedor preferente y único requerido.** Aporta `responseSchema` OpenAPI, que fuerza la estructura de la respuesta y es lo que garantiza que el dictamen jurídico sea explotable. |
| **GPU Dedicada** *(opcional)* | NVIDIA GeForce RTX 5070 (12 GB VRAM) | **No es requisito.** Sólo se usa si se activa el proveedor local Ollama. |
| **Servidor IA Local** *(opcional)* | Ollama en `http://localhost:11434` | Proveedor alternativo **desactivado por defecto**. Ver nota abajo. |
| **Motor OCR** | **Tesseract OCR v5+** (`cat+spa`) | Motor de extracción diferida para PDFs escaneados y fallback de visión. |
| **Entorno Python** | Python 3.10+ en entorno virtual (`venv` / `uv`) | Ejecución determinista del pipeline y suite de pruebas unitarias. |
| **Base de Datos** | **SQLite 3.35+** en modo WAL (Write-Ahead Logging) | Persistencia local ligera con bloqueo seguro transaccional (`licitaciones.db.lock`). |

> [!IMPORTANT]
> **Decisión de arquitectura — Gemini como proveedor preferente (sustituye al enfoque Local-First original)**
>
> El diseño inicial situaba Ollama (`llama3.1:8b` sobre RTX 5070) como proveedor preferente. Se revierte por dos motivos:
>
> 1. **Portabilidad**: la herramienta está destinada a varios equipos de la cooperativa que no disponen de GPU dedicada. Un requisito de hardware no replicable convierte la herramienta en no distribuible.
> 2. **Garantía de esquema**: Gemini acepta `responseSchema` (OpenAPI) y **fuerza** la estructura de la respuesta. Ollama sólo ofrece `format: json`, que garantiza JSON sintácticamente válido pero **no** la forma correcta — precisamente el fallo que producía dictámenes vacíos dados por buenos.
>
> Ollama **no se elimina**: se conserva tras la interfaz abstracta `LLMProvider` y puede activarse en `config/analista_config.yaml` en equipos con GPU. Simplemente deja de ser obligatorio y deja de ser el preferente.

---

## ▶️ Cómo Ejecutar el Sistema

> Se recomienda lanzar los comandos desde la raíz del proyecto, pero desde el 2026-08-06 **ya no es obligatorio**: `config/` y `data/` se resuelven contra la raíz del repositorio, no contra el directorio de trabajo (ver hallazgo H-18). Antes, ejecutar desde otra carpeta cargaba el perfil comercial vacío y puntuaba distinto sin avisar.

### 1. Pipeline de captación (Capas 1 a 6)

```bash
python run.py
```

Opciones útiles: `--dry-run` (no escribe en base de datos), `--skip-centinela` (omite boletines DOGC/BOPB), `--batch-size N`.

Equivale a `python -m src.main`. **No** debe ejecutarse como `python src/main.py`: esa forma rompe la resolución del paquete `src`.

### 2. Pasarela API (Capa 7)

```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

Documentación interactiva en `http://127.0.0.1:8000/docs`.

### 3. Cockpit Visual (Capa 8)

```bash
cd frontend && npm run dev
```

Disponible en `http://localhost:5173`. Requiere la API de la Capa 7 en marcha.

### 4. Suite de pruebas

```bash
python -m pytest tests/ -q
```

---

## 🏢 Perfil de Negocio de Incoop (Configuración del Radar)

> Esta sección define los parámetros que alimentan la Capa 2 (El Filtro) y la Capa 5 (El Analista). Cualquier cambio en la estrategia comercial de la cooperativa debe reflejarse aquí y en el fichero `config/perfil_incoop.yaml`.

### Identidad

**Incoop, SCCL** es una cooperativa de treball i de consum sense ànim de lucre con más de 28 años de experiencia, dedicada a generar, diseñar, gestionar y desarrollar **proyectos y servicios educativos, culturales y sociales** en Catalunya. Facturación anual estimada: **~11M €** (2023).

### Sectores de actividad y códigos CPV (Calibración Consolidada)

| Sector | Ejemplos de servicio | Códigos CPV calibrados (Core & Familias) |
|---|---|---|
| **Servicios educativos y de formación** | Escoles bressol, ludotecas, casals d'estiu, extraescolars, formación de adultos | 80000000, 80100000, 80110000, 80200000, 80300000, 80400000, 85312110 |
| **Servicios sociales y atención a las personas** | Casals de gent gran, atenció domiciliària, centres oberts, atención a la dependencia | 85300000, 85310000, 85311000, 85312000, 85312100, 85320000 |
| **Servicios comunitarios y asociativos** | Gestión de casals de joves, dinamización comunitaria, entidades sociales y cooperativas | 98000000, 98100000, 98130000, 98300000, 75200000 |
| **Servicios culturales y equipamientos** | Gestión de centres cívics, bibliotecas, museos, dinamización cultural y eventos | 92000000, 92500000, 92510000, 92520000, 79952000 |
| **Restauración colectiva** | Menjadors escolars, càtering social y comedores comunitarios | 55520000, 55523100, 55524000 |
| **Mantenimiento de equipamientos** | Limpieza y mantenimiento de centros públicos gestionados por Incoop | 90910000, 50700000 |
| **Consultoría y asistencia técnica local** | Asesoramiento a entidades sociales, cooperativas y apoyo administrativo | 79400000, 75120000, 75130000, 85312300 |

> **Nota de Calibración**: Los códigos CPV han sido revisados e incorporados al catálogo en `config/perfil_incoop.yaml`. El motor `src/filtro.py` los evalúa mediante prefijos de 3 y 5 dígitos (con **+40 pts** para coincidencia Core y **+30 pts** para fallbacks de división social/comunitaria).

> [!TIP]
> **📌 Espíritu Colectivo de Incoop y Calibración Continua de CPVs y PMP**:
> Como cooperativa de iniciativa social y sin ánimo de lucro con más de 28 años de trayectoria, la selección de CPVs refleja fielmente la misión de **Incoop**: la transformación social a través de proyectos educativos, de atención a las personas, culturales y de dinamización comunitaria. Los CPVs definidos maximizan la bonificación comercial (+40 pts) en los pilares estratégicos de la cooperativa. Asimismo, el sistema mantiene activos los penalizadores de Periodo Medio de Pago (PMP) e indicadores de morosidad para proteger el *working capital* de Incoop ante administraciones locales con retrasos recurrentes en el cobro.

### Parámetros de filtrado (Capa 2)

| Parámetro | Valor | Justificación |
|---|---|---|
| **Presupuesto mínimo** | 35.000 € | Se reduce el umbral duro para capturar contratos simplificados de rápida preparación, penalizándolos con -15 pts en el scoring si son inferiores a 100.000 € (priorizando los de gran volumen pero manteniendo visibles los pequeños de alta afinidad) |
| **Presupuesto máximo** | 2.000.000 € | Incoop factura ~11M €; contratos superiores a 2M € pueden requerir UTE o superar la capacidad operativa de la cooperativa |
| **Ámbito geográfico** | Catalunya (PSCP) + Estado (PCSP) | **Foco Operativo Preferente**: Prioridad máxima en Barcelona, Barcelonès y Corona Metropolitana / Alrededores (+35 pts en scoring); cobertura general en el resto de Catalunya (+20 pts) sin descartes duros para no limitar oportunidades estratégicas |
| **Procedimientos LCSP** | Abierto (Art. 156) + Abierto Simplificado y Súper Simplificado (Art. 159) | Son los procedimientos donde las cooperativas de iniciativa social y Pymes compiten en igualdad de condiciones |

### Exclusiones automáticas (palabras clave negativas)

El sistema descartará automáticamente las licitaciones cuyo objeto o tipo de contrato coincida con:

| Exclusión | Tipo de contrato LCSP | Razón |
|---|---|---|
| **Obras y construcción** | Contrato de obras | Incoop gestiona servicios, no construye |
| **Suministros de bienes** | Contrato de suministros | Mobiliario, equipos informáticos, material — no es el core |
| **Ingeniería y arquitectura** | Servicios técnicos | Fuera del perfil competencial |
| **Desarrollo de software / TIC** | Servicios tecnológicos | No es una tecnológica |
| **Seguridad privada y vigilancia** | Servicios de seguridad | Requiere habilitación específica |
| **Servicios sanitarios clínicos** | Servicios sanitarios | Hospitales, ambulancias — fuera del ámbito social/educativo |

### Cláusulas críticas para el análisis de pliegos (Capa 5)

Cuando el Analista IA lea un pliego, deberá extraer y evaluar estas cláusulas por su impacto directo en la decisión de presentarse:

| Cláusula | Artículo LCSP | Por qué importa a Incoop |
|---|---|---|
| **Subrogación de personal** | Art. 130 | Determina el coste real de personal heredado; puede convertir un contrato rentable en deficitario si la plantilla tiene mucha antigüedad |
| **Revisión de precios** | Art. 103 | En contratos plurianuales (2-4 años), si no hay revisión por IPC o convenio colectivo, la inflación erosiona el margen año a año |
| **Garantía definitiva** | Art. 107-108 | Por la Paradoxa de Caixa de Incoop (solo ~38k € de caixa líquida en 2023), saber si se puede usar seguro de caución vs. depósito en efectivo es crítico |
| **Peso precio vs. calidad** | Art. 145 | Si el precio pesa más del 60% en la adjudicación, la licitación se convierte en una guerra de precios donde Incoop tiene desventaja frente a grandes empresas |
| **Penalidades y resolución** | Art. 192-194 | Penalidades desproporcionadas o cláusulas de resolución agresivas elevan el riesgo contractual |
| **Cláusulas sociales** | Art. 202 | **Ventaja competitiva**: como cooperativa de iniciativa social, Incoop puede capitalizar criterios de inserción laboral, igualdad y economía social que otras empresas no cumplen de forma natural |

---

## 🛤️ Principios de Diseño para la Adaptabilidad

Este proyecto no es una herramienta puntual: es un **sistema operativo de negocio** que debe funcionar de forma continuada y sobrevivir al cambio. Los siguientes principios identifican los puntos más vulnerables y las estrategias para que el sistema se adapte sin romperse.

### Puntos vulnerables y estrategias

| Punto vulnerable | Por qué cambia | Estrategia de adaptabilidad |
|---|---|---|
| **URLs y esquemas de los feeds RSS** | Las plataformas públicas actualizan sus APIs sin previo aviso ni changelog | Las URLs y las reglas de parseo se almacenan en un fichero de configuración externo (`config/fuentes.yaml`), nunca hardcoded. Un **healthcheck** al inicio de cada ejecución verifica que cada feed responde y contiene la estructura esperada, alertando si algo ha cambiado |
| **Perfil de negocio de Incoop** | Los sectores objetivo, los CPVs y los umbrales económicos evolucionan con la estrategia comercial de la cooperativa | El perfil se define en un fichero independiente (`config/perfil_incoop.yaml`) que cualquier persona del equipo puede editar sin tocar código. El sistema lee ese perfil en cada ejecución |
| **Formato de los PDFs de pliegos** | Cada órgano de contratación genera PDFs con estructuras distintas; algunos son escaneos (imagen), otros texto nativo | La Capa 4 (Lector) se diseña con un **patrón adaptador**: primero intenta extracción de texto directo (rápido y fiable); si detecta páginas sin texto, escala a OCR. Ambas rutas son intercambiables |
| **Modelos de IA para análisis semántico** | Los modelos evolucionan rápidamente (GPT → Claude → Gemini → modelos locales); hoy el mejor puede no ser el mejor mañana | La Capa 5 (Analista) se comunica con la IA a través de una **interfaz abstracta** (un contrato de entrada/salida). Cambiar de modelo significa cambiar una sola configuración, no reescribir la lógica |
| **Nuevas fuentes de datos** | Mañana Incoop puede querer vigilar otras CCAA, o la UE, o plataformas sectoriales | Cada fuente es un **módulo independiente** que cumple un contrato común (devolver una lista normalizada de licitaciones). Añadir una fuente nueva es crear un nuevo módulo, no modificar los existentes |

### Regla general

> **Lo que es probable que cambie vive en ficheros de configuración. Lo que es posible que cambie vive detrás de una interfaz abstracta. Lo que no va a cambiar es lo único que se puede poner en el código directamente.**

---

## 🗺️ Mapa de Ruta por Capas (Roadmap)

El desarrollo sigue una metodología estrictamente secuencial (**bottom-up**): cada capa se diseña, implementa y valida antes de pasar a la siguiente. Esto permite construir sobre cimientos probados y ajustar el rumbo en cada etapa.

```mermaid
graph TD
    C1[Capa 1: El Radar<br/>Extracción de Datos Crudos] --> C2[Capa 2: El Filtro<br/>Reglas Duras y Solvencia]
    C2 --> C3[Capa 3: La Memoria<br/>SQLite y Trazabilidad]
    C3 --> C4[Capa 4: El Lector Documental<br/>Descarga y OCR de Pliegos]
    C4 --> C5[Capa 5: El Analista IA<br/>Cláusulas y Semáforos]
    C5 --> C6[Capa 6: El Centinela de Boletines<br/>DOGC/BOPB - Fase Temprana]
    C6 --> C7[Capa 7: La Pasarela API<br/>Micro-API REST FastAPI]
    C7 --> C8[Capa 8: El Cockpit Visual<br/>SPA React + Vite + Tailwind]
    C8 --> C85[Capa 8.5: Cimientos de Infraestructura<br/>Concurrencia, Locks y Entorno]
    C85 --> B2[Bloque 2: Coherencia de Negocio LCSP<br/>Escala única, cláusulas y estado por lote]
    B2 --> C9[Capa 9: El Histórico y Depurador<br/>Archivo y Purga de Datos]
    C9 --> C10[Capa 10: El Lanzador y Despertador<br/>Silent Launcher VBS y Alertas]

    style C3 fill:#2d6a4f,stroke:#1b4332,color:#d8f3dc
    style C8 fill:#1b4332,stroke:#0f2c1e,color:#d8f3dc
```

> **¿Por qué esta secuencia ampliada?** 
> 1. **La Memoria (Capa 3)** almacena la información estructurada de inmediato tras el filtro rápido para no reprocesar.
> 2. **El Centinela de Boletines (Capa 6)** monitoriza aprobaciones iniciales en boletines oficiales para el canal proactivo, capturando proyectos en fase temprana (antes de la licitación formal) y reutilizando el motor LLM de la Capa 5.
> 3. **La Pasarela API (Capa 7)** actúa como la frontera tecnológica: expone SQLite mediante una micro-API REST local (FastAPI + Pydantic v2) que el navegador consume, y recoge las decisiones tomadas en la UI para reinyectarlas en el motor de persistencia. *(Nota: el diseño original planteaba un exportador a fichero estático `dashboard_data.js`; se sustituyó por una API REST para permitir mutaciones transaccionales desde la UI, imposibles con un fichero plano.)*
> 4. **El Cockpit (Capa 8)** proporciona la cara humana del sistema mediante una SPA local-first premium (React + Vite + Tailwind + TanStack).
> 5. **El Histórico e Historial (Capa 9)** nos permite depurar el sistema, agrupar ejecuciones anteriores y dotar a la cooperativa del botón de "Borrar/Purgar" para limpiar registros antiguos sin comprometer la integridad.
> 6. **El Lanzador Silencioso (Capa 10)** elimina la necesidad de consolas o comandos al envolver la ejecución en un script VBS silencioso que se ejecuta al hacer doble clic.

---

## 📡 Capa 1: El Radar (Extracción y Normalización de Datos Crudos)
* **Estado actual**: 🟢 Completado y Validado (100%).

### 🎯 Objetivo
Conectarse de forma automática, estructurada y resiliente a las fuentes públicas de contratación estatal y autonómica para descargar, normalizar y consolidar en un formato común los metadatos básicos de las licitaciones vigentes.

### 🔍 Alcance e Implementación Técnica
El Radar está implementado en [src/radar.py](src/radar.py) y cuenta con los siguientes componentes:

1. **Gestión de Múltiples Fuentes (Configuración Externa)**:
   * Las URLs y estados de conexión se configuran de forma externa en [config/fuentes.yaml](config/fuentes.yaml).
   * **PCSP Estatal**: Descarga del feed XML Atom oficial `sindicacion_643` (Licitaciones de Perfiles del Contratante completos).
   * **CCAA Agregadas**: Descarga del feed XML Atom oficial `sindicacion_1044` (Comunidades Autónomas Agregadas).
   * **API de Datos Abiertos de Catalunya (Socrata)**: Consulta nativa JSON SoQL al dataset `ybgg-dgi6` de la Generalitat de Catalunya, permitiendo lecturas eficientes de los lotes publicados.

2. **Motor de Normalización Unificada**:
   * Convierte y estandariza las estructuras heterogéneas de datos (árbol XML del estándar europeo UBL/CODICE y diccionarios JSON de Socrata) en un esquema interno uniforme:
     * **Identificación**: Número de expediente, Título, Órgano de Contratación.
     * **Financiero**: PBL (Importe base sin IVA) y VEC (Valor estimado con prórrogas) por separado.
     * **Geográfico**: Mapeo de códigos territoriales NUTS y nombres planos de municipio (Localidad a través de `<cbc:CityName>` en XML y `lloc_execucio` en Socrata).
     * **Operativo y Riesgos**: CPVs, tipo de procedimiento, detección preliminar de subrogación de personal, detección de revisión de tarifas, tramitación urgente y loteado de expedientes.

3. **Resiliencia de Conexión**:
   * Control estricto de excepciones de red con límites de tiempo (*timeouts* de 15 segundos). Si el servidor de datos abiertos de Cataluña o del Estado sufre una caída de servicio o lentitud en la carga, el sistema captura el error y continúa procesando el resto de fuentes disponibles de forma parcial y limpia.

### 🛠️ Ficheros Creados
*   [src/radar.py](src/radar.py): Motor de descarga y parseo de XML/JSON.
*   [config/fuentes.yaml](config/fuentes.yaml): Listado de plataformas y endpoints.

---

## 🧹 Capa 2: El Filtro (Sistema de Scoring y Calibración Financiera)
* **Estado actual**: 🟢 Completado y Validado (100%).

### 🎯 Objetivo
Limpiar el ruido e identificar oportunidades de alta viabilidad comercial para Incoop mediante reglas duras de descarte inmediato y un sistema de scoring financiero y operativo adaptativo.

### 🔍 Alcance e Implementación Técnica
El motor desarrollado en `src/filtro.py` evalúa cada licitación bajo dos fases:

1. **Filtros Duros (Descarte Inmediato)**:
   * **Presupuesto**: Excluye licitaciones por debajo de **35.000 €** (simplificados de muy bajo margen) o superiores a **2.000.000 €** (exceso de capacidad).
   * **Tipos de Contrato**: Excluye Obras, Suministros, TIC, Seguridad o Sanitario.
   * **Palabras Negativas**: Descarte inmediato ante objetos incompatibles (ej. *construcción*, *suministro*, *software*).

2. **Filtros Blandos (Sistema de Scoring Ponderado)**:
   * **Presencia Histórica Directa**: **+40 pts** si el municipio, barrio o distrito ya es territorio operativo de Incoop (tiene prioridad sobre el resto de criterios geográficos).
   * **Afinidad Territorial**: **+35 pts** por Barcelona y corona metropolitana; **+20 pts** por el resto de Catalunya. Se resuelve primero por código NUTS y, si no está informado, por nombre de municipio.
   * **Órgano de Contratación Afín**: **+20 pts**.
   * **Afinidad de Actividad (CPV)**: **+40 pts** por CPV Core del catálogo sectorial; en su defecto, por división: **+30** social (853) y comunitario (98), **+25** educación (80), cultural (92) y comedores (555), **+20** administración (75) y limpieza/mantenimiento (909/507), **+10** consultoría (79).
   * **Procedimiento**: **+10 pts** si es Abierto o Simplificado; **−15 pts** en caso contrario.
   * **Palabras de Interés**: **+25 pts** por palabra núcleo (ej. *escola bressol*, *casal*) y **+10 pts** por palabra secundaria.
   * **Penalización de Contratos Pequeños**: **−15 pts** si el presupuesto base es inferior a **100.000 €**.

> [!TIP]
> **Contrato de scoring v2 — escala canónica 0–100**
> Las señales ponderadas internas se normalizan contra el máximo bruto declarado en
> `config/perfil_incoop.yaml`; `score_total`, API, Cockpit y Recalibrador sólo intercambian un
> entero entre 0 y 100. Los umbrales de prioridad son **65** (alta) y **40** (media). El score
> bruto se conserva en el resultado del filtro para auditoría, pero nunca se persiste ni presenta
> como puntuación comercial.

3. **Inteligencia Financiera y Operativa Avanzada**:
   * **Semáforo de Tesorería (PMP)**: Cruza el órgano de contratación con el Periodo Medio de Pago de Hacienda en [config/pmp_ayuntamientos.csv](config/pmp_ayuntamientos.csv). Suma **+10 pts** si el ayuntamiento paga en ≤ 30 días y resta **-20 pts** si paga en ≥ 60 días.
   * **Ratio de Prórrogas (VEC vs PBL)**: Premia con **+15 pts** si el Valor Estimado del Contrato con prórrogas duplica al Presupuesto Base de Licitación inicial (VEC/PBL ≥ 2.0).
    * **Subrogación de Personal y Revisión de Precios**: El feed sólo genera una **señal de lectura**. No resta ni suma puntos: la Capa 5 decide una única vez sobre evidencia del pliego, evitando tanto negaciones mal interpretadas como doble penalización.
   * **Urgencia e Importe Restante**: Resta **-15 pts** si el expediente es urgente o quedan menos de 5 días para presentar la solvencia técnica en licitaciones de gran volumen (≥ 200.000 €).
   * **División en Lotes**: Suma **+10 pts** si el contrato se divide en lotes independientes, lo que permite licitar de forma parcial y mitigar el riesgo.
   * **Estimación de Retención de Avales**: Proyecta automáticamente un inmovilizado financiero del **5% del PBL** para anticipar el coste financiero de la garantía definitiva.

### 🛠️ Ficheros Creados
*   [src/filtro.py](src/filtro.py): Motor del Filtro y Scoring.
*   [config/pmp_ayuntamientos.csv](config/pmp_ayuntamientos.csv): Base de datos local de periodos medios de pago.
*   [config/perfil_incoop.yaml](config/perfil_incoop.yaml): Parámetros, umbrales y palabras clave de negocio.

---

## 💾 Capa 3: La Memoria (Registro, Persistencia y Trazabilidad Analítica)
* **Estado actual**: 🟢 Completada.

### 🎯 Objetivo
Persistir de forma estructurada en una base de datos local SQLite (`data/licitaciones.db`) las licitaciones y lotes detectados por el radar, garantizando el control de duplicados, la trazabilidad del scoring y el almacenamiento de variables críticas para Control de Gestión (CAC, PMP, competencia e inmovilizado).

### 🔍 Consideraciones Críticas de Diseño e Inteligencia de Negocio
Para alcanzar el nivel de robustez analítico que buscamos como Controller, el modelo de datos responde a estas cinco dimensiones críticas atajando vulnerabilidades técnicas de SQLite:

1. **Gestión Multilote (Relación $1:N$)**:
   * *El reto*: Las licitaciones públicas se dividen frecuentemente en lotes independientes (p. ej. *Lote 1: Casal Distrito 1*, *Lote 2: Casal Distrito 2*). El estado de estudio, los CPVs específicos y el scoring comercial deben ir a nivel de lote.
   * *La solución*: Estructurar la base de datos en dos tablas: `expedientes` (datos comunes del anuncio) y `lotes` (datos específicos de presupuesto, subrogación, scoring, costes y estado comercial).

2. **Inteligencia Competitiva (Cierre de Círculo en Post-Licitación)**:
   * *El reto*: Si Incoop pierde un concurso, necesitamos registrar de forma estructurada contra quién se ha perdido y a qué precio, para alimentar en el futuro las horquillas de "Baja Temeraria" y auditar el comportamiento de la competencia.
   * *La solución*: Añadir en `lotes` campos para guardar la `empresa_adjudicataria`, el `importe_adjudicacion` y la métrica de `dinero_en_la_mesa` (diferencia monetaria entre la oferta de Incoop y la ganadora).

3. **Gestión de Rectificaciones (El Chivato de Cambios con Diagnóstico)**:
   * *El reto*: La administración suele modificar importes (VEC) o aplazar fechas límites tras la publicación original. Si el equipo técnico estudia un pliego y el radar actualiza los datos en silencio, se provocan fallos humanos por asimetría de información.
   * *La solución*: El radar comparará los datos entrantes con el registro original de SQLite. Si detecta variaciones en la fecha límite o en el VEC tras haber sido clasificada por el usuario, activará `alerta_modificacion = True` en `expedientes` y concatenará en `log_cambios` el historial de lo que cambió exactamente (p. ej. `"[2026-07-11] VEC modificado de 150.000 a 140.000 €; Fecha límite pospuesta al 2026-07-28"`).

4. **El Coste de Adquisición (CAC Público) y Blindaje contra Borrados Físicos (Soft Delete)**:
   * *El reto*: Si una administración anula o retira una licitación y el radar aplica un `ON DELETE CASCADE`, se destruirán los lotes asociados y el histórico de `horas_internas_invertidas` y `costes_externos` que el equipo ya invirtió.
   * *La solución*: Eliminar el borrado en cascada. Se implementará un **Soft Delete** (borrado lógico). Si una licitación desaparece del feed XML, se mantendrán los lotes en la base de datos marcando su estado como `'Anulada_Administracion'` o `'Inactiva'`.

5. **Control de Garantías y Retornos de Capital (Working Capital)**:
   * *El reto*: Las garantías definitivas (5% del PBL) inmovilizan recursos de tesorería durante la vida del contrato.
   * *La solución*: Guardar en `lotes` el `importe_garantia_retenida` depositado y la `fecha_devolucion_garantia` estimada al terminar la ejecución para emitir alertas automatizadas de reclamación de avales.

### 🗄️ Modelo de Datos Propuesto (Esquema Relacional)

```mermaid
erDiagram
    EXPEDIENTES ||--o{ LOTES : contiene
    METADATA ||--|| EXPEDIENTES : versiona
    EJECUCIONES {
        integer id PK "Autoincrementable"
        string start_time "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        string end_time "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        string estado "RUNNING, COMPLETED, FAILED"
    }
    METADATA {
        integer version "Número de versión del esquema actual (p. ej. 2)"
    }
    EXPEDIENTES {
        string id PK "Número de expediente"
        string titulo "Título general del anuncio"
        string organo "Órgano de contratación"
        string localidad "Municipio de ejecución"
        string nuts "Código NUTS territorial"
        string procedimiento "Tipo de procedimiento"
        boolean urgente "Tramitación urgente"
        string fuente "Portal de origen (PSCP/PCSP)"
        string link "URL oficial de la ficha"
        string fecha_publicacion "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        string fecha_limite "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        string fecha_ingesta "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        boolean alerta_modificacion "Flag de modificación post-ingesta"
        string log_cambios "Historial de modificaciones del pliego"
        string last_seen_feed "ISO 8601 UTC de la última ingesta"
        string feed_hash "Hash SHA256 del contenido público"
    }
    LOTES {
        integer id PK "Autoincrementable"
        string expediente_id FK "Relación con Expedientes (ON DELETE RESTRICT)"
        integer lote_numero "Número de lote dentro del anuncio"
        string titulo_lote "Descripción específica del lote"
        string cpvs "Códigos CPV asociados"
        real pbl "Importe base de licitación sin IVA"
        real vec "Valor estimado del contrato con prórrogas"
        real garantia_definitiva "Estimado del 5% del PBL (aval)"
        boolean subrogacion "Obligación de subrogación de personal"
        boolean revision_precios "Cláusula de revisión de precios"
        integer dias_restantes "Días disponibles para presentar"
        integer score_total "Puntuación de scoring obtenida"
        string motivos_scoring "Desglose de motivos sumados/restados"
        string sector "Sector detectado (Restauración, Educación, etc.)"
        string prioridad "Prioridad asignada (Baja, Media, Alta)"
        integer pmp_dias "PMP del municipio para control de tesorería"
        real ratio_prorrogas "Ratio de prórrogas VEC/PBL"
        string estado_operativo "Estado comercial (Nueva, Estudiando, Anulada_Administracion, etc.)"
        string notas_usuario "Notas internas del equipo de Incoop"
        string empresa_adjudicataria "Competencia adjudicataria (post-licitación)"
        real importe_adjudicacion "Importe de cierre (post-licitación)"
        real dinero_en_la_mesa "Diferencia de oferta económica"
        integer horas_internas_invertidas "Horas consumidas por el equipo"
        real costes_externos "Gastos externos asociados a la oferta"
        real importe_garantia_retenida "Aval real depositado en caja"
        string fecha_devolucion_garantia "ISO 8601 UTC (YYYY-MM-DD)"
        string deleted_at "ISO 8601 UTC de soft delete"
        string deleted_reason "Motivo del soft delete"
        string updated_by "radar o user"
        string updated_at "ISO 8601 UTC del último cambio"
    }
```

### 🛣️ Plan de Ejecución Detallado (10 Pasos para el Controller)

#### **Fase 1: Arquitectura y Modelado (El Cimiento)**
1. **Definición estricta del esquema DDL y Control de Migración (`metadata`)** 🟢 (Completado y Validado):
   * Escribir el DDL de SQL puro integrado en Python (`src/memoria.py`).
   * Definir los tipos de datos exactos (`TEXT`, `REAL`, `INTEGER`, `BOOLEAN`).
   * Establecer restricciones duras: clave primaria en `expedientes.id`, relación `FOREIGN KEY(expediente_id) REFERENCES expedientes(id) ON DELETE RESTRICT` (impidiendo borrados en cascada físicos para proteger el CAC), clave única compuesta `UNIQUE(expediente_id, lote_numero)` para evitar duplicación de lotes específicos, y estados por defecto (`estado_operativo = 'Nueva'`).
   * **Control de Versión de Esquema (Evitar Migration Hell)**: Crear una tabla de una sola columna y fila llamada `metadata` con el campo `version` (INTEGER). Si en el futuro es necesario añadir o alterar columnas (ej. *riesgo_sindical*), el script comparará esta versión y ejecutará automáticamente sentencias `ALTER TABLE` sin dañar los registros persistidos.
   * **Casteo Estricto de Fechas en UTC**: Para evitar el desfase por husos horarios y horario de verano/invierno (que podría falsear plazos límite críticos por 2 horas), todas las fechas se guardarán estrictamente en formato ISO 8601 UTC terminando en "Z" (`YYYY-MM-DDTHH:MM:SSZ`) como tipo `TEXT`. La conversión a hora local se hará exclusivamente en la capa de presentación (Visualizador o dashboards).
2. **Inicializador Automático de la BD (`setup_db`)** 🟢 (Completado y Validado):
   * Crear la función de comprobación en `src/memoria.py`. Si `data/licitaciones.db` no existe, la genera y crea la tabla `metadata` estableciendo la versión inicial `1`. Si ya existe, compara la versión guardada y ejecuta las migraciones correspondientes si difiere del código actual.

#### **Fase 2: Desarrollo del Motor DAO (`src/memoria.py`)**
3. **Conexiones Concurrentes (PRAGMA WAL) y Claves Foráneas** 🟢 (Completado y Validado):
   * Programar la conexión SQLite implementando context managers robustos (`with sqlite3.connect(...) as conn:`).
   * **WAL (Write-Ahead Logging)**: Ejecutar obligatoriamente `PRAGMA journal_mode=WAL;` y `PRAGMA foreign_keys=ON;` al abrir la conexión. WAL permite lecturas concurrentes simultáneas (p. ej. desde tableros de Power BI) mientras Python realiza escrituras masivas, previniendo el error de colapso `database is locked`. Garantizar la liberación segura llamando explícitamente a `.close()`.
4. **Lógica de Ingesta y Control de Duplicados (UPSERT)** 🟢 (Completado y Validado):
   * Diseñar el método `upsert_oportunidad()`.
   * Utilizar sentencias `INSERT INTO ... ON CONFLICT DO UPDATE` tanto para la cabecera del expediente como para cada uno de sus lotes asociados.
5. **Motor de Detección de Rectificaciones (El Chivato de Cambios)** 🟢 (Completado y Validado):
   * Programar la comparación lógica antes del UPDATE. Si el radar detecta que la `fecha_limite` o el `vec` entrantes difieren de los registros guardados en base de datos, y el estado operativo del lote **ya no es** `'Nueva'`, marcará automáticamente `alerta_modificacion = True` en `expedientes` y concatenará en `log_cambios` el desglose del cambio (ej. `"[2026-07-11 13:50 UTC] Fecha límite pospuesta al 2026-07-28 (era 2026-07-20)"`).
6. **Aislamiento y Blindaje de Variables Manuales (Soft Delete)** 🟢 (Completado y Validado):
   * Diseñar métodos transaccionales separados para la edición de variables de usuario (`actualizar_estado_lote()`, `registrar_horas_CAC()`).
   * Garantizar que la ingesta diaria del radar (Paso 4) **nunca** sobrescriba las columnas manuales (`horas_internas_invertidas`, `costes_externos`, `estado_operativo`, `notas_usuario`, `empresa_adjudicataria`, etc.). El trabajo técnico del equipo está blindado contra las actualizaciones del feed público.
   * Si una licitación de interés deja de venir en el feed público, el radar marcará su estado operativo como `'Anulada_Administracion'` o `'Inactiva'`, evitando borrar el registro para proteger el cálculo histórico del CAC.

#### **Fase 3: Integración en el Pipeline Core (`src/main.py`)**
7. **Inyección en el Bucle Principal** 🟢 (Completado y Validado):
   * Modificar `src/main.py` para instanciar la base de datos y hacer que cada licitación filtrada y puntuada en la Capa 2 sea enviada directamente a la persistencia SQLite, en lugar de únicamente reportarse por la consola.
8. **Transacciones Masivas en Lote (Batch Ingest)** 🟢 (Completado y Validado):
   * Optimizar la velocidad de escritura englobando las inserciones de ejecuciones masivas bajo una sola transacción (`conn.execute("BEGIN TRANSACTION")` o procesamiento en lote), aplicando `ROLLBACK` en caso de excepciones y un solo `COMMIT` al final del radar.

#### **Fase 4: Explotación y Mantenimiento del Controller**
9. **Creación de Vistas Analíticas (SQL Views)** 🟢 (Completado y Validado):
   * Implementar vistas pre-calculadas nativas en SQLite para simplificar los informes y los futuros dashboards de Power BI:
     * `vista_win_rate`: Ratio de licitaciones ganadas frente a presentadas y perdidas de Incoop.
     * `vista_analisis_CAC`: CAC acumulado (horas * tarifa interna configurable + costes externos) comparado con el retorno adjudicado.
     * `vista_garantias_activas`: Suma agregada del capital inmovilizado por avales vigentes y fecha aproximada de su vencimiento y retorno a caja.
     * `vista_garantias_por_mes`: Proyección agregada mensual del retorno de avales (Working Capital).
10. **Backup Transaccional en Caliente (SQLite Backup API)** 🟢 (Completado y Validado):
    * En el modo WAL, realizar copias del archivo físico de la BD principal usando comandos del sistema operativo (`shutil.copy`) genera archivos corruptos debido a la asincronía del fichero `-wal` activo.
    * *La solución*: Utilizar la API nativa `sqlite3.Connection.backup()`. Python instanciará una conexión temporal exclusiva al archivo de destino fechado (ej. `data/backups/licitaciones_20260711_135000.db.bak`), volcará de manera segura y atómica las páginas de memoria de la base de datos de origen, y cerrará la conexión limpia sin interferir con las operaciones concurrentes de Power BI. Retener únicamente los últimos 7 días de copia para no consumir almacenamiento innecesariamente.

### 🛠️ Herramientas y Código a Crear
*   `src/memoria.py`: Conectores, esquema DDL con tabla de control de versión, UPSERT transaccional, backups atómicos y vistas SQL.
*   `data/licitaciones.db`: Archivo de base de datos relacional SQLite local.
*   `data/backups/`: Directorio de backups atómicos con políticas de retención de 7 días.

---

## 📄 Capa 4: El Lector Documental (Descarga y Lectura de Pliegos)
* **Estado actual**: 🟢 Completada.

### 🎯 Objetivo
Descargar los archivos PDF de Pliegos de Cláusulas Administrativas (PCA), Pliegos de Prescripciones Técnicas (PPT) y anexos de las licitaciones de interés, extraer su contenido textual utilizando un pipeline híbrido (lectura nativa PyMuPDF + OCR Tesseract) y catalogarlos en una tabla documental estructurada en base de datos.

### 🔍 Alcance
- Extracción de enlaces de pliegos (XML de la PCSP y scraping HTML controlado para la PSCP).
- Descarga controlada con políticas de cortesía (throttling), timeout y reintentos.
- Pipeline de extracción de texto mediante un patrón adaptador (PyMuPDF para PDFs digitales y Tesseract para escaneados).
- Persistencia relacional en la tabla `documentos` (esquema v3) y guardado del PDF original en disco.
- Coexistencia del modo Dry-Run en descargas y OCR.

### 🛣️ Paso a Paso
- **Paso 1: Inicialización del Entorno Documental (Bootstrap)**: 🟢 Completado y Validado.
  - Validación e instalación de dependencias en `requirements.txt`.
  - Implementación del bootstrap y detección resiliente de Tesseract OCR en `src/lector.py`.
  - Creación física y test de escritura en carpetas locales (`data/documents/`).
- **Paso 2: Ingestión de URLs desde el Radar (XML + HTML)**: 🟢 Completado y Validado.
  - Parseo de referencias adicionales en `src/radar.py`.
  - Scraping controlado de enlaces y extracción de hashes de documentos para Catalunya (PSCP).
  - Creación y migración de la tabla `documentos` en SQLite (esquema v3).
- **Paso 3: Descargador Multihilo Resiliente (PDF Nativo)**: 🟢 Completado y Validado.
  - Priorización de colas, semáforos de cortesía por dominio y descarga multihilo concurrente.
  - Descargas por streaming a temporal `.part`, firmas mágicas `%PDF-` e integridad SHA256.
  - Deduplicación física cruzada en disco, traslado atómico y sidecars JSON de metadatos.
- **Paso 3.5: Robustez y Mitigación de Riesgos de Descarga**: 🟢 Completado y Validado.
  - Context manager de file lock cross-process (`licitaciones.db.lock`) para prevenir colisiones en disco.
  - Pre-deduplicación de feed para evitar descargas duplicadas de red (bypass completo a 0 ms).
  - Backpressure dinámica por host mediante cooldown colectivo compartido en el pool de hilos.
  - Job de purga física de PDFs y sidecars para expedientes inactivos o expirados (>90 días).
  - Generación de reportes de métricas CSV acumulativos y logs estructurados de auditoría.
- **Paso 4: Motor de Extracción de Texto Nativo (PyMuPDF / FitZ)**: 🟢 Completado y Validado.
  - Extracción vectorial multipágina con PyMuPDF (`fitz`), limpieza de texto y normalización de espacios.
  - Autodetector de idiomas integrado (`langdetect`) con soporte para castellano (`es`), catalán (`ca`) e inglés (`en`).
  - Detección de densidad de texto por página (<50 chars/pág) y etiquetado automático `OCR_REQUERIDO` para páginas escaneadas.
  - Persistencia en SQLite (`texto_extraido`, `metodo_extraccion`, `idioma`, `version_reglas`) y trazabilidad JSONL (`doc_text_extracted_native`, `doc_ocr_flagged`).
- **Paso 5: Motor de OCR Diferido para PDFs Escaneados (Tesseract OCR / Arquitectura Híbrida VLM)**: 🟢 Completado y Validado.
  - Conversión de páginas PDF escaneadas a imágenes de alta resolución mediante PyMuPDF / Pillow.
  - Invocación de Tesseract OCR multilingüe (`cat+spa`) para documentos marcados como `OCR_REQUERIDO`.
  - Hoja de ruta para inferencia con modelos de visión-lenguaje locales (VLM como `Qwen2.5-VL` / `Llama-3.2-Vision`) ejecutándose sobre la GPU NVIDIA RTX 5070 para parseo estructurado de tablas complejas de solvencia y presupuesto, conservando Tesseract como fallback de velocidad.
  - Modo degradado estructurado (`OCR_DIFERIDO`) para conservación de texto vectorial nativo previo si Tesseract o el VLM no estuvieran disponibles.
  - Registro de eventos JSONL (`doc_ocr_started`, `doc_ocr_succeeded`, `doc_ocr_degraded`, `doc_ocr_batch_completed`).

---

## 🧠 Capa 5: El Analista IA (Extracción Semántica)
* **Estado actual**: 🟢 Completada y Validada (Pasos 1 al 10 completados y verificados con suite E2E).

### 🎯 Objetivo
Analizar semánticamente mediante modelos de lenguaje (LLMs locales o API Cloud) el contenido textual de pliegos (PCA y PPT) procesados en la Capa 4. El motor extrae de forma estructurada (JSON Schema) cláusulas clave de riesgo y oportunidad contractual regidas por la Ley de Contratos del Sector Público (LCSP): obligación de subrogación de personal (Art. 130 LCSP), cláusulas de revisión de tarifas e inflación (Art. 103 LCSP), desglose de criterios de adjudicación (juicio de valor vs. fórmulas automáticas), solvencia técnica exigida y penalizaciones.

### 🔍 Alcance
- **Segmentación Heurística (Smart LCSP Chunking)**: Localizar fragmentos relevantes del pliego mediante expresiones regulares para no enviar páginas irrelevantes al LLM, reduciendo tokens y optimizando la latencia.
- **Extracción Estructurada Determinista**: Obligar al LLM a emitir exclusivamente objetos JSON validados por esquemas de tipos.
- **Patrón Proveedor Adaptativo (interfaz abstracta `LLMProvider`)**:
  - **Proveedor Preferente (Cloud con Structured Outputs)**: Integración con la API oficial de **Google Gemini** forzando `responseSchema` de OpenAPI en `generationConfig` para garantizar la indemnidad estructural del DTO. Es el único proveedor requerido y funciona en cualquier equipo.
  - **Proveedor Opcional (Local con gestión de VRAM)**: Integración con **Ollama** (`localhost:11434`) para equipos con GPU dedicada. **Desactivado por defecto** por no ser replicable fuera del equipo de desarrollo y por no ofrecer garantía de esquema en la respuesta.
- **Recalibración del Scoring de Oportunidad**: Recombinar la puntuación cuantitativa del Filtro (Capa 2) con los hallazgos cualitativos del Analista IA (Capa 5) para asignar el dictamen comercial final en SQLite (`RECOMENDADA`, `REVISAR_RIESGO`, `DESCARTADA_POR_RIESGO`).
- **Modo Degradado Resiliente**: Si no hay conexión a internet ni servidor LLM activo, el sistema pasa el estado a `ANALISIS_DIFERIDO` en SQLite conservando la puntuación cuantitativa previa sin bloquear el pipeline.

### 🛣️ Paso a Paso para el Controller (10 Pasos de Implementación)

1. **Paso 1: Definición del Esquema DTO (`AnalisisSemanticoDTO`)** 🟢 (Completado y Validado):
   - Definición e implementación de estructuras inmutables en Python ([src/analista.py](src/analista.py)): `SubrogacionDTO`, `RevisionPreciosDTO`, `CriteriosAdjudicacionDTO`, `DictamenIA` y `AnalisisSemanticoDTO`.
   - Métodos `.to_dict()`, `.to_json()`, `.from_dict()` y `.from_json(estricto=...)`.
   - **Contrato de parseo dual (esquema DTO v2)**: `from_json(estricto=True)` se usa para las respuestas del LLM y **eleva `ValidationError`** si el JSON es ilegible o le faltan los bloques obligatorios, de modo que el orquestador conmute de proveedor. `from_json(estricto=False)` se usa sólo para relecturas desde SQLite, donde un registro histórico corrupto debe degradarse en lugar de impedir la lectura del expediente.
   - Campo explícito `modo_degradado: bool`, única fuente de verdad sobre si el dictamen procede de una lectura real del pliego.
2. **Paso 2: Migración de Base de Datos a Esquema v4 (`src/memoria.py`)** 🟢 (Completado y Validado):
   - Definición del DDL para la tabla `analisis_semantico` relacional vinculada a `expedientes(id)` (1:1), almacenamiento de DTOs en JSON, métricas de consumo LLM y columnas normalizadas para consultas SQL eficientes.
   - Elevación del esquema a `ESQUEMA_VERSION = 4` con respaldo automático `.mig_backup` e indemnidad transaccional.
   - Implementación de métodos DAO `guardar_analisis_semantico()`, `obtener_analisis_semantico()`, `obtener_analisis_semantico_raw()`, `listar_expedientes_pendientes_analisis()` y autodiagnóstico `healthcheck_memoria()`.
   - Trazabilidad JSONL en `data/pipeline.jsonl` y suite de pruebas unitarias en `tests/test_memoria_v4.py`.
3. **Paso 3: Cliente / Adaptador del Proveedor LLM (`src/analista.py`)** 🟢 (Completado y Validado):
   - Configuración externalizada en `config/analista_config.yaml`.
   - Interfaz abstracta `LLMProvider` e implementación de conectores `OllamaProvider` (`localhost:11434`, GPU local RTX 5070 con VRAM `num_ctx: 16384`) y `GeminiProvider` (`gemini-2.0-flash` con `responseSchema` OpenAPI).
   - Orquestador `AnalistaIA` con cadena de resiliencia **Gemini → (Ollama si está activado) → Modo Degradado** (`DEGRADADO`), autodiagnóstico `healthcheck_analista()`, trazabilidad JSONL y suite de tests con mocks en `tests/test_analista_llm.py`.
   - **Un fallo de esquema cuenta como fallo del proveedor**: una respuesta con JSON válido pero forma incorrecta activa el siguiente proveedor de la cadena. Nunca se persiste como análisis `COMPLETADO`. La traza JSONL distingue `tipo_fallo: ESQUEMA_INVALIDO` de `TRANSPORTE`.
4. **Paso 4: Motor de Segmentación Inteligente (Smart LCSP Chunking)** 🟢 (Completado y Validado):
   - Implementación de `SmartLCSPChunker` en `src/analista.py` con regex bilingües (Art. 130 subrogación, Art. 103 revisión precios, Art. 145 criterios).
   - Extracción de ventanas de contexto (1.200 chars), fusión de intervalos superpuestos y reducción del consumo de tokens en un 80-90%.
   - Inyección en `AnalistaIA.analizar_pliego()`, trazabilidad JSONL (`SMART_CHUNKING_COMPLETED`) y suite de tests unitarios en `tests/test_smart_chunker.py`.
5. **Paso 5: Ingeniería de Prompts Especializados LCSP (Castellano y Catalán)** 🟢 (Completado y Validado):
   - Externalización de plantillas en `config/prompts_lcsp.yaml` con ejemplos **Few-Shot** bilingües y guardrails de cero alucinación.
   - Implementación de `GestorPromptsLCSP` en `src/analista.py` con adaptación bilingüe e inyección en `AnalistaIA.analizar_pliego()`.
   - Trazabilidad JSONL (`PROMPT_GENERATED`), autodiagnóstico `healthcheck_prompts()` y suite de tests unitarios en `tests/test_prompts_lcsp.py`.
6. **Paso 6: Algoritmo de Recalibración del Scoring (Capa 2 + Capa 5)** 🟢 (Completado y Validado):
   - Implementación de `RecalibradorScoring` en `src/analista.py` para la hibridación determinista entre el score cuantitativo de Capa 2 y los dictámenes cualitativos de Capa 5.
   - Evaluación de vetos por subrogación crítica de personal (Art. 130 LCSP), penalización/bonificación por revisión de precios (Art. 103 LCSP) y criterios de adjudicación (Art. 145 LCSP).
   - Modo degradado indemnne (`ajuste_semantico = 0`), trazabilidad JSONL (`SCORE_RECALIBRATED`) y suite de tests unitarios en `tests/test_recalibrador_scoring.py`.
7. **Paso 7: Trazabilidad JSONL y Resiliencia en Modo Degradado (Reglas 3 y 5)** 🟢 (Completado y Validado):
   - Orquestación unificada en `AnalistaIA.procesar_expediente()` que emite la secuencia de 6 eventos JSONL estándar (`doc_analysis_started`, `SMART_CHUNKING_COMPLETED`, `PROMPT_GENERATED`, `LLM_REQUEST_START/SUCCESS`, `SCORE_RECALIBRATED`, `doc_analysis_completed/degraded`).
   - Manejo transparente del estado `ANALISIS_DIFERIDO` en fallos totales de red/IA, preservando el score cuantitativo inicial y permitiendo reintentos.
   - Audibilidad del log writer en `healthcheck_analista()` y suite de tests unitarios en `tests/test_analista_trazabilidad.py`.
8. **Paso 8: Orquestación en Pipeline Principal (`src/main.py`) y Reporting Comercial** 🟢 (Completado y Validado):
   - Acoplamiento del procesamiento por lotes `analista.procesar_lote_pendientes()` en el punto de entrada diario `src/main.py`.
   - Generación automática del informe comercial en CSV `data/reports/analisis_semantico_summary.csv` (UTF-8 con BOM, delimitador `;` para Excel).
   - Registro del evento JSONL `SEMANTIC_BATCH_COMPLETED` y suite de tests de integración en `tests/test_analista_main.py`.
9. **Paso 9: Consola de Comando CLI e Inspección de Análisis (`src/analista.py` / CLI)** 🟢 (Completado y Validado):
   - Implementación de la consola de comando CLI independiente `python src/analista.py` con parseador de argumentos `argparse`.
   - Comandos para autodiagnóstico de conectores LLM (`--healthcheck`), inspección visual de dictámenes en terminal (`--inspeccionar <EXP_ID>`), re-análisis individual (`--reanalizar <EXP_ID>`), procesamiento manual por lotes (`--procesar-lote`) y generación aislada de reportes CSV (`--reporte-csv`).
   - Suite de pruebas unitarias en `tests/test_analista_cli.py`.
10. **Paso 10: Pruebas de Integración E2E y Cierre Oficial de Capa 5** 🟢 (Completado y Validado):
    - Suite de integración E2E en `tests/test_capa5_e2e.py` que audita los 4 escenarios críticos (Veto por subrogación, Bonificación por revisión, Fallo diferido de IA y Generación de CSV).
    - Cierre oficial de la Capa 5 y activación de la Capa 6 en la hoja de ruta del proyecto.

### 💻 Guía de Uso del CLI del Analista IA (`src/analista.py`)

El módulo `src/analista.py` incluye una consola de comandos interactiva que permite auditar y gestionar el análisis semántico de forma independiente al pipeline general:

```powershell
# 1. Autodiagnóstico de proveedores LLM (Ollama, Gemini API, prompts y permisos de log)
python src/analista.py --healthcheck

# 2. Inspeccionar en consola el dictamen cualitativo completo de una licitación
python src/analista.py --inspeccionar "2024/00123"

# 3. Forzar el re-análisis semántico de una licitación concreta
python src/analista.py --reanalizar "2024/00123"

# 4. Procesar en lote manualmente las licitaciones pendientes (con límite de 20)
python src/analista.py --procesar-lote --limite 20

# 5. Generar o actualizar el informe comercial CSV de análisis semántico
python src/analista.py --reporte-csv
```

### 🛠️ Herramientas y Código Desarrollado
- `src/analista.py`: Motor del Analista IA, conectores LLM (`OllamaProvider`, `GeminiProvider`), Smart Chunker, Prompts LCSP, Recalibrador y CLI.
- `config/analista_config.yaml`: Fichero de configuración de umbrales, VRAM local de Ollama (`num_ctx: 16384`) y respuesta estructurada OpenAPI en Gemini API.
- `config/prompts_lcsp.yaml`: Plantillas de prompts especializados LCSP bilingües con ejemplos Few-Shot.
- `src/memoria.py`: Migración a esquema v4 de SQLite y DAO del analista.
- `src/main.py`: Inyección del análisis semántico en la ejecución diaria del pipeline.

---

## 📡 Capa 6: El Centinela de Boletines (DOGC/BOPB - Fase Temprana)
* **Estado actual**: 🟢 Completada y Validada (100%).

---

### 🔍 Consideraciones Críticas de Diseño e Inteligencia de Negocio

En el ámbito de la contratación y gestión pública en Catalunya, la publicación de un anuncio de licitación en la PSCP o en la PCSP (Capa 1) representa la **fase reactiva final** del procedimiento (Art. 135 LCSP). Sin embargo, meses antes de que se aprueben los pliegos y se inicie el plazo de presentación de ofertas (generalmente de 15 a 30 días), los entes locales y autonómicos tramitan y publican actos administrativos obligatorios en los boletines oficiales que revelan de forma anticipada la futura contratación:

1. **Aprobación Inicial de Presupuestos y Plantillas Municipales** (*BOPB / DOGC*):
   * *Oportunidad*: La aprobación de presupuestos anuales de ayuntamientos y consejos comarcales publica partidas detalladas para nuevos equipamientos (escuelas infantiles, casales de jóvenes, centros cívicos) o incrementos de partida para servicios sociales y culturales.
   * *Beneficio*: Incoop anticipa qué ayuntamientos dispondrán de liquidez y qué servicios saldrán a concurso en los siguientes dos trimestres.

2. **Planes Estratégicos de Subvenciones (PES) y Convocatorias de Concurrencia** (*DOGC / BOPB*):
   * *Oportunidad*: Publicación obligatoria de los PES donde se consignan las subvenciones nominativas o de concurrencia para entidades del tercer sector y cooperativas de iniciativa social.
   * *Beneficio*: Identificación de proyectos sociales financiables que no siguen la vía de la licitación formal pero encajan al 100% en la misión de Incoop.

3. **Consultas Preliminares del Mercado (Art. 115 LCSP)** (*DOGC / BOPB / Perfiles*):
   * *Oportunidad*: El órgano de contratación convoca al sector para diseñar los pliegos o estudiar la viabilidad económica y técnica de un servicio.
   * *Beneficio*: Incoop puede participar activamente en la consulta, orientando las cláusulas técnicas y haciendo valer sus especificidades cooperativas de iniciativa social antes de que el concurso se cierre.

4. **Encargos a Medios Propios y Convenios de Colaboración** (*DOGC*):
   * *Oportunidad*: Anuncios de formalización de convenios o encargos a empresas públicas.
   * *Beneficio*: Permite detectar si un servicio se ha internalizado o encomendado a un medio propio, o si existen oportunidades de subcontratación autorizadas.

5. **El Canal Proactivo de Networking (EspaiTRES)**:
   * *La ventaja competitiva*: Contar con esta información en fase temprana activa el protocolo interno de *Networking y Prospección Comercial* de Incoop. El equipo técnico puede establecer contacto con los departamentos municipales, evaluar alianzas en UTE con entidades locales y planificar el inmovilizado financiero (*working capital*) con meses de antelación.

---

### 🗄️ Modelo de Datos y Relación de Fase Temprana (Tabla `boletines_alertas` - Esquema v5)

```mermaid
erDiagram
    BOLETINES_ALERTAS ||--o| EXPEDIENTES : "se convierte en (opcional)"
    BOLETINES_ALERTAS {
        string id_alerta PK "Hash SHA256 (fuente + num_boletin + titulo)"
        string fuente "DOGC o BOPB"
        string num_boletin "Número / Referencia del boletín oficial"
        string fecha_publicacion "ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)"
        string organo_emisor "Ayuntamiento, Diputación o Consejería"
        string municipio "Municipio de ejecución"
        string titulo_anuncio "Título del anuncio o disposición"
        string seccion_boletin "Sección oficial (Administración Local, Anuncios, etc.)"
        string url_anuncio "URL de la disposición oficial"
        string url_pdf "URL del PDF del boletín"
        string texto_sumario "Texto extractado del anuncio"
        integer score_temprano "Puntuación de viabilidad temprana (0-100)"
        string motivos_score "Desglose JSON/Texto de la puntuación"
        string categoria_fase_temprana "PRESUPUESTO, SUBVENCION, CONVENIO, CONSULTA_PRELIMINAR"
        string dictamen_ia_json "DTO DictamenCentinelaDTO serializado en JSON"
        string estado_operativo "NUEVA_FASE_TEMPRANA, EN_ESTUDIO_PROACTIVO, CONVERTIDA, DESCARTADA"
        string expediente_licitacion_vinculado FK "ID de expediente en PSCP/PCSP (Capa 3)"
        string notas_usuario "Notas internas de seguimiento proactivo"
        string fecha_ingesta "ISO 8601 UTC"
        string updated_at "ISO 8601 UTC"
    }
```

---

### 🛣️ Plan de Ejecución Detallado (10 Pasos de la Capa 6)

#### **Fase 1: Arquitectura, Modelado DTO y Persistencia v5**
1. **Paso 1 — Definición del Esquema DTO (`AlertaBoletinDTO`) y Contrato de Servicio**: 🟢 Completado y Validado.
   - Creación de las clases inmutables `DictamenCentinelaDTO` y `AlertaBoletinDTO` en `src/centinela.py`.
   - Mapeo determinista con serialización/deserialización defensiva y hashing SHA256.
2. **Paso 2 — Migración de Base de Datos SQLite a Esquema v5 (`src/memoria.py`)**: 🟢 Completado y Validado.
   - DDL de la tabla `boletines_alertas` con clave primaria `id_alerta` (SHA256) y vista `vista_alertas_tempranas`.
   - Elevación del esquema a `ESQUEMA_VERSION = 5` con 5 métodos DAO asociados.

#### **Fase 2: Motor de Ingesta, Filtrado y Clasificación con IA (`src/centinela.py`)**
3. **Paso 3 — Cliente / Ingestor Resiliente de Fuentes Oficiales (DOGC y BOPB)**: 🟢 Completado y Validado.
   - `IngestorBoletines` con parseo XML Atom/RSS, reintentos exponenciales, normalización de fechas UTC y deduplicación.
4. **Paso 4 — Motor de Segmentación y Filtrado por Reglas Duras de Fase Temprana**: 🟢 Completado y Validado.
   - `FiltroBoletinesReglas` con veto de palabras prohibidas, desestimación por contexto negativo (*"no incluye obras"*) y scoring por 5 categorías LCSP.
5. **Paso 5 — Integración del Analista IA para Clasificación Semántica de Boletines**: 🟢 Completado y Validado.
   - `AnalistaBoletinesIA` integrado con `proveedor_llm_factory()` y consulta estructurada al modelo de IA preferente (`gemini-3.1-flash-lite`), con fallback resiliente y degradado seguro. Servido con prompt especializado bilingüe en `config/prompts_lcsp.yaml`.

#### **Fase 3: Scoring Consolidado, Trazabilidad, Orquestación y Blindaje**
6. **Paso 6 — Algoritmo de Scoring y Priorización Temprana (`EvaluadorScoringCentinela`)**: 🟢 Completado y Validado.
   - Consolidación del score base de reglas duras con la cualificación IA (+30 pts ALTO, +15 pts MEDIO, -30 pts NULO) y penalización de caja por Periodo Medio de Pago (PMP) de ayuntamientos vía `PMPService` (`src/pmp_service.py`).
7. **Paso 7 — Trazabilidad JSONL y Resiliencia en Modo Degradado (`GestorTrazabilidadCentinela`)**: 🟢 Completado y Validado.
   - Registros append-only deterministas en `data/pipeline.jsonl` y orquestación resiliente `ejecutar_pipeline_centinela_resiliente`.
8. **Paso 8 — Orquestación en Pipeline Principal (`src/main.py`) y Reporting CSV**: 🟢 Completado y Validado.
   - Integración de flags CLI (`--skip-centinela`, `--csv-centinela`) en `src/main.py` y función `exportar_reporte_centinela_csv` (UTF-8 con BOM `utf-8-sig`).

#### **Fase 4: Consola CLI, Inspección y Pruebas E2E**
9. **Paso 9 — Consola de Comando CLI e Inspección del Centinela (`src/centinela.py`)**: 🟢 Completado y Validado.
   - CLI interactivo con `--inspeccionar <ID>`, `--listar`, `--actualizar-estado`, `--notas`, `--exportar-csv`.
10. **Paso 10 — Pruebas de Integración E2E y Cierre Oficial de Capa 6**: 🟢 Completado y Validado.
    - Suite de integración E2E en `tests/test_capa6_e2e.py` y `tests/test_centinela_llm_factory.py` que audita la ingesta DOGC/BOPB, factoría LLM real sin inyección (Convención C4), filtrado con veto negativo, scoring con PMP, cualificación LLM, trazabilidad JSONL, reporte CSV y vinculación con expedientes PSCP.
    - Cierre oficial de la Capa 6 y validación de la Pasarela API (Capa 7).

---

### 🛡️ Plan de Blindaje y Mejora Arquitectónica Incorporado (Capa 6)

A raíz del análisis continuo de riesgos del ecosistema, se han integrado 5 mejoras arquitectónicas estructurales en la Capa 6:

1. **Gestión del Riesgo Financiero por PMP (`src/pmp_service.py`)**:
   - Módulo independiente que carga `config/pmp_ayuntamientos.csv` y normaliza con reglas *fuzzy* los nombres de municipios de Catalunya (*Barcelona*, *Ajuntament de Badalona*, *Girona...*).
   - Penalización de caja en el scoring financiero: $PMP > 60$ días ($-25$ pts, Riesgo ALTO); $PMP > 90$ días ($-45$ pts, Riesgo CRÍTICO y descarte preventivo).
   - Inyección automática del PMP real en el prompt de la IA.

2. **Filtro de Veto con Análisis de Contexto Negativo**:
   - `FiltroBoletinesReglas` desestima la penalización de veto si la palabra clave va precedida por expresiones negativas (*"no incluye obras"*, *"excloses"*, *"excepto"*, *"sense perjudici"*), evitando falsos positivos.

3. **Matriz de Decisión Cuantitativa en YAML (`config/prompts_lcsp.yaml`)**:
   - Inclusión de reglas numéricas explícitas de evaluación de riesgo (Subrogación $>60\%$ del PBL $\rightarrow$ CRÍTICO; $PMP > 90$ días $\rightarrow$ CRÍTICO) para eliminar la subjetividad del LLM ("Cero Alucinación").

4. **Smart Chunker Híbrido con Solapamiento (`SmartLCSPChunker`)**:
   - Ampliación del diccionario de sinónimos LCSP en catalán y castellano (*asunción de trabajadores*, *clàusula d'absorció*, *art 130*) y solapamiento (*overlap*) de 300 caracteres entre fragmentos contiguos.

5. **Matching Inteligente Centinela $\leftrightarrow$ PSCP y Reporting Comercial**:
   - Vinculación determinista mediante `vincular_alerta_a_expediente()` entre publicaciones oficiales previas y expedientes formales de la PSCP.
   - Exportación de `data/alertas_tempranas.csv` en UTF-8 con BOM (`utf-8-sig`) para compatibilidad directa con Excel.

---

### 🛠️ Herramientas y Código Desarrollado
- `src/centinela.py`: Motor del Centinela, conectores DOGC/BOPB, DTOs, scoring temprano, trazabilidad, exportador CSV y CLI interactivo.
- `src/pmp_service.py`: Servicio de consulta PMP con normalización *fuzzy* de municipios de Catalunya y evaluación de riesgo financiero de tesorería.
- `config/centinela_config.yaml`: Parámetros, exclusiones, keywords y umbrales de fase temprana.
- `config/pmp_ayuntamientos.csv`: Base de datos de Periodo Medio de Pago a Proveedores por ayuntamiento/municipio.
- `config/prompts_lcsp.yaml`: Plantilla especializada bilingüe `centinela_boletines` con matriz de decisión cuantitativa Cero Alucinación.
- `src/memoria.py`: Migración a esquema v5 de SQLite (tabla `boletines_alertas`, vista `vista_alertas_tempranas` y 5 DAO methods).
- `src/main.py`: Inyección del Centinela de Boletines en el pipeline principal.
- `data/alertas_tempranas.csv`: Reporte comercial proactivo de fase temprana.




---

## 🔌 Capa 7: La Pasarela API (FastAPI REST Micro-API)
* **Estado actual**: 🟢 Implementada y validada en beta. Expone lectura paginada, healthcheck y mutaciones transaccionales locales.

### 🎯 Objetivo
Construir una **micro-API local RESTful de alto rendimiento en Python utilizando FastAPI y Uvicorn** que conecte directamente la interfaz de usuario de grado empresarial (Capa 8) con la base de datos de persistencia **SQLite v5** (`licitaciones.db` en modo WAL). 

Esta capa sustituye cualquier exportación a ficheros estáticos (`dashboard_data.js` o parches JSON), garantizando una arquitectura distribuida local-first, con consultas optimizadas y mutaciones transaccionales en tiempo real.

---

### 🔍 Consideraciones Críticas de Diseño e Inteligencia de Negocio

1. **Aislamiento Local-First y Alta Concurrencia (SQLite WAL)**:
   - La API se ejecutará de forma local en `http://127.0.0.1:8000`.
   - La base de datos SQLite v5 funcionará en modo **WAL (Write-Ahead Logging)**, permitiendo que el pipeline de scraping en segundo plano (Radar / Centinela) escriba sin bloquear las lecturas o mutaciones del usuario en la interfaz visual.

2. **Tipado Estricto con Pydantic v2 y OpenAPI 3.1**:
   - Todos los objetos de entrada y salida serán validados en tiempo de ejecución mediante esquemas inmutables de **Pydantic v2**.
   - Generación automática de especificación **OpenAPI (Swagger UI)** accesible en `/docs` para auditoría interactiva de desarrollador.

3. **CORS Restrictivo y Middleware Defensivo**:
   - `CORSMiddleware` configurado explícitamente para permitir peticiones procedentes únicamente del servidor de desarrollo del Cockpit Visual en React (`http://localhost:5173`).
   - Manejador global de excepciones con respuestas de error estandarizadas (`APIErrorResponse`) evitando la fuga de trazas internas.

4. **Trazabilidad Determinista JSONL (Regla 3)**:
   - Toda llamada a la API que altere el estado de una licitación (*Pasar a Estudio*, *Descartar*, *Notas*) registrará de forma determinista un evento de auditoría en `data/pipeline.jsonl` con el usuario, timestamp UTC e ID del expediente.

---

### 🗄️ Arquitectura de la Pasarela API y Flujo de Datos

```mermaid
graph TD
    UI[Frontend React + Vite<br/>Capa 8 - Cockpit Visual] <-->|HTTP REST / JSON| API[FastAPI Micro-API<br/>src/api/main.py]
    API <-->|Pydantic v2 Schemas| ROUTERS[Routers RESTful<br/>Licitaciones / Centinela / KPIs]
    ROUTERS <-->|DAO Methods| MEMORIA[Memoria DAO<br/>src/memoria.py]
    MEMORIA <-->|Lecturas/Escrituras WAL| DB[(SQLite v5 DB<br/>licitaciones.db)]
    ROUTERS -->|Audit Events| LOG[Pipeline JSONL<br/>data/pipeline.jsonl]
```

---

### 📜 Especificación del Contrato RESTful (Endpoints Core API)

| Método | Endpoint | Descripción | Parámetros Query / Body | Respuesta HTTP |
|---|---|---|---|---|
| **GET** | `/api/v1/licitaciones` | Listado paginado y filtrable del Funnel PSCP/PCSP. | `page`, `limit`, `search`, `min_score`, `pmp_max`, `subrogacion_critica`, `estado` | `200 OK` (`PaginatedResponse[LicitacionSchema]`) |
| **GET** | `/api/v1/licitaciones/{id}` | Detalle completo de un expediente y su dictamen IA. | `id` (Path) | `200 OK` (`LicitacionSchema`) / `404 Not Found` |
| **PUT** | `/api/v1/licitaciones/{id}/estado` | Mutación transaccional del estado del expediente. | Body: `{ "nuevo_estado": "EN_ESTUDIO", "notas": "..." }` | `200 OK` (`LicitacionSchema`) / `400 Bad Request` |
| **GET** | `/api/v1/alertas-tempranas` | Listado paginado del Centinela (DOGC/BOPB). | `page`, `limit`, `search`, `fuente`, `min_score`, `estado` | `200 OK` (`PaginatedResponse[AlertaBoletinSchema]`) |
| **PUT** | `/api/v1/alertas-tempranas/{id}/estado` | Mutación de estado de alerta del Centinela. | Body: `{ "nuevo_estado": "EN_ESTUDIO_PROACTIVO", "notas": "..." }` | `200 OK` (`AlertaBoletinSchema`) |
| **GET** | `/api/v1/kpis` | Resumen global de métricas del Funnel comercial. | N/A | `200 OK` (`KPISummarySchema`) |
| **GET** | `/api/v1/health` | Healthcheck y autodiagnóstico de la API y SQLite. | N/A | `200 OK` (`HealthResponseSchema`) |

---

### 🛣️ Plan de Ejecución Detallado (10 Pasos Atómicos de la Capa 7)

#### **Fase 1: Infraestructura Base y Modelado de Datos**
1. **Paso 1 — Inicialización del Entorno y Dependencias Core (`src/api/dependencies.py`)**: 🟢 Completado y Validado.
   - Configuración del esqueleto del paquete `src/api/` e inyector de dependencias (`get_db`) para la gestión transaccional de conexiones SQLite v5 (modo WAL).
2. **Paso 2 — Modelado de Esquemas Base con Pydantic v2 (`src/api/schemas.py`)**: 🟢 Completado y Validado.
   - Definición inmutable de los DTOs de lectura (`LicitacionSchema`, `AlertaBoletinSchema`, `KPISummarySchema`), mutación (`TransicionEstadoSchema`) y errores (`APIErrorResponse`).
3. **Paso 3 — Endpoint de Autodiagnóstico y Salud (`/api/v1/health`)**: 🟢 Completado y Validado.
   - Router inicial `src/api/routers/health.py` para validar conectividad, versión del esquema v5 y lectura/escritura en SQLite WAL.

#### **Fase 2: Construcción de Motores de Lectura (Queries)**
4. **Paso 4 — Router Analítico de KPIs (`/api/v1/kpis`)**: 🟢 Completado y Validado.
   - Endpoint `GET /api/v1/kpis` que serializa agregaciones financieras, funnel de conversión e inmovilizado desde vistas SQL.
5. **Paso 5 — Router del Funnel Reactivo PSCP (`/api/v1/licitaciones`)**: 🟢 Completado y Validado.
   - Endpoint `GET /api/v1/licitaciones` y `GET /api/v1/licitaciones/{id}` con paginación nativa y filtrado por score, PMP y subrogación.
6. **Paso 6 — Router del Canal Proactivo Centinela (`/api/v1/alertas-tempranas`)**: 🟢 Completado y Validado.
   - Endpoint `GET /api/v1/alertas-tempranas` y `GET /api/v1/alertas-tempranas/{id_alerta}` para servir datos de DOGC/BOPB.

#### **Fase 3: Motor Transaccional y Escritura (Mutations)**
7. **Paso 7 — Endpoint de Mutación de Licitaciones (`PUT /api/v1/licitaciones/{id}/estado`)**: 🟢 Completado y Validado.
   - Lógica de escritura para capturar transiciones de estado (*Estudiando*, *Presentada*, *Adjudicada*, *Descartada*) y notas manuales en SQLite v5.
8. **Paso 8 — Endpoint de Mutación del Centinela (`PUT /api/v1/alertas-tempranas/{id}/estado`)**: 🟢 Completado y Validado.
   - Lógica de mutación para gestionar el ciclo proactivo y notas de networking sobre boletines.

#### **Fase 4: Blindaje, Trazabilidad y Cierre Oficial**
9. **Paso 9 — Middleware de Seguridad, CORS y Trazabilidad JSONL**: 🟢 Completado y Validado.
   - Restricción CORS para `http://localhost:5173`, `GlobalExceptionHandler` y conexión de peticiones API con `data/pipeline.jsonl`.
10. **Paso 10 — Suite de Pruebas de Integración y Cierre Oficial de Capa 7**: 🟢 Completado y Validado.
    - Suite de pruebas de API con `TestClient` en `tests/test_capa7_api.py`, verificación de Swagger `/docs` y cierre formal de la Capa 7.


---

### 🛠️ Herramientas y Código a Crear
- `src/api/__init__.py`: Inicializador del paquete de la API.
- `src/api/main.py`: Servidor de aplicación FastAPI, routers, CORS y handlers de excepción.
- `src/api/schemas.py`: DTOs de Pydantic v2 para validación inmutable de request/response.
- `src/api/dependencies.py`: Inyección de dependencias de conexión a SQLite v5.
- `src/api/routers/licitaciones.py`: Endpoints RESTful de licitaciones formales PSCP.
- `src/api/routers/centinela.py`: Endpoints RESTful de alertas tempranas DOGC/BOPB.
- `src/api/routers/kpis.py`: Endpoints RESTful de KPIs y resumen analítico del Funnel.
- `tests/test_capa7_api.py`: Suite de integración de endpoints con `TestClient`.


---

## 🎨 Capa 8: El Cockpit Visual (React + Vite + Tailwind CSS + TanStack Table + TanStack Query)
* **Estado actual**: 🟢 Completada y Validada (100%).

### 🎯 Objetivo
Construir un **Dashboard de grado empresarial (Enterprise SaaS)** utilizando React 18+, TypeScript, Vite, Tailwind CSS, TanStack Table (v8) y TanStack Query (v5). Conecta en tiempo real la interfaz gráfica con la Pasarela API RESTful de la Capa 7 (FastAPI/SQLite WAL), garantizando legibilidad ejecutiva, mutaciones optimistas sin latencia, Smart Polling para ingesta en segundo plano y cero cuellos de botella en el cliente.

### 🏛️ Principios Arquitectónicos Obligatorios (Las 8 Reglas del Frontend)

1. **Puerto Estricto de Vite & CORS**:
   - `frontend/vite.config.ts` forzará `server: { port: 5173, strictPort: true }` para coincidir de forma estricta con las políticas de `CORSMiddleware` del servidor FastAPI (`http://localhost:5173`).
2. **Paginación y Filtrado Server-Side (TanStack Table)**:
   - Configuración en modo Server-Side (`manualPagination: true`, `manualSorting: true`, `manualFiltering: true`) delegando las consultas paginadas (`page`, `limit`, `search`, `min_score`, `pmp_max`) a la API de la Capa 7 y SQLite v5 en lugar de procesar arrays en memoria en el navegador.
3. **Sincronización en Tiempo Real por Smart Polling**:
   - Para refrescar los expedientes y boletines insertados por el Radar (Capa 1) y Centinela (Capa 6) en segundo plano sin refrescos manuales (F5), se configura `refetchInterval: 30000` (30 segundos) en las consultas de TanStack Query, restringido a ventanas enfocadas (`refetchIntervalInBackground: false`).
4. **Mutaciones Optimistas y Gestión de Caché (TanStack Query v5)**:
   - Implementación de `useQuery` y `useMutation` con actualización optimista instantánea (`onMutate`) al cambiar estados operativos o guardar notas manuales.
5. **Mecanismo de Rollback Visual y Toasts Destructivos**:
   - En caso de error en el backend (`HTTP 500/503/400`), la mutación optimista ejecuta `onError` restaurando el snapshot previo de la caché (`queryClient.setQueryData(queryKey, context.previousData)`) y disparando un Toast destructivo (rojo) notificando la causa del error capturada de `APIErrorResponse.detail`.
6. **Carga Diferida y Renderizado Asíncrono de Detalle (Suspense + Skeletons)**:
   - El Drawer de detalle se abre de forma **instantánea** al hacer clic en cualquier fila de la tabla, mostrando estructuras pulsantes (*Skeletons*) mientras TanStack Query resuelve asíncronamente `GET /api/v1/licitaciones/{id}` o `GET /api/v1/alertas-tempranas/{id}` sin causar bloqueos del hilo principal (*layout thrashing*).
7. **Sincronización Estricta de Tipos (TypeScript Espejo DTO)**:
   - Archivo de definición `src/types/api.ts` que refleja 1-a-1 los esquemas inmutables de Pydantic v2 (`src/api/schemas.py`).
8. **Legibilidad Visual Ejecutiva & Tipografía Tabular**:
   - Tema oscuro nativo/slate con acentos de color contextuales, tipografía moderna e importes monetarios (PBL, VEC, avales) formateados con cifras tabulares (`font-mono tabular-nums`) para prevenir saltos de layout al actualizar datos.

---

### 🗺️ Plan de Desarrollo Paso a Paso — Capa 8

#### **Fase 1: Inicialización del Entorno y Contrato de Tipos**
1. **Paso 1 — Inicialización del Proyecto Frontend (Vite + React + TypeScript + Tailwind CSS)**: 🟢 Completado y Validado.
   - Creación del proyecto frontend en `frontend/`, configuración de `vite.config.ts` con puerto estricto 5173, alias `@/` e integración de Tailwind CSS v4 y lucide-react.
2. **Paso 2 — Espejo de Tipos TypeScript y Cliente API HTTP**: 🟢 Completado y Validado.
   - Creación de `src/types/api.ts` (espejo DTO de Pydantic v2) y `src/lib/api-client.ts` (cliente fetch con inyección de cabecera `X-Request-ID`).
3. **Paso 3 — Configuración de TanStack Query v5, Smart Polling y Rollback Optimista**: 🟢 Completado y Validado.
   - Creación de `src/lib/react-query.ts` con `refetchInterval: 30000`, custom hooks de consulta (`useKPIs`, `useLicitaciones`, `useAlertasTempranas`) y mutación (`useMutateEstadoLicitacion`, `useMutateEstadoAlerta`) con patrón atómico `onMutate` -> `onError` (rollback + Toast destructivo) -> `onSettled`.

#### **Fase 2: Sistema de Diseño y Componentes Base**
4. **Paso 4 — Sistema de Diseño, Paleta de Colores y Componentes UI Base**: 🟢 Completado y Validado.
   - Tokens CSS para tema claro estilizado (Light SaaS Theme), componentes UI (`Badge`, `Button`, `Card`, `Input`, `Select`, `Modal`, `Drawer`, `Skeleton`, `Toast / Toaster`).
5. **Paso 5 — Header, Navegación Principal e Indicador Health**: 🟢 Completado y Validado.
   - Barra de navegación superior con selector de vista, resumen rápido y sensor de estado en tiempo real del servidor API (`/api/v1/health` cada 15s).

#### **Fase 3: Motores de Visualización y Tablas Server-Side**
6. **Paso 6 — Dashboard Analítico de KPIs y Tesorería**: 🟢 Completado y Validado.
   - Panel visual consumiendo `GET /api/v1/kpis` con Smart Polling (Tarjetas de Expedientes Totales, Lotes, Funnel de Conversión, Win-Rate, Avales Retenidos y Alertas Tempranas).
7. **Paso 7 — Tabla Ejecutiva del Funnel Reactivo PSCP (TanStack Table Server-Side)**: 🟢 Completado y Validado.
   - Tabla interactiva para `GET /api/v1/licitaciones` en modo Server-Side con paginación nativa, barra de búsqueda global, filtros por score, PMP y subrogación.
8. **Paso 8 — Canal Proactivo Centinela (Oportunidades Fase Temprana DOGC/BOPB)**: 🟢 Completado y Validado.
   - Tabla interactiva para `GET /api/v1/alertas-tempranas` en modo Server-Side con filtros por fuente oficial (DOGC/BOPB), categoría LCSP y score proactivo.

#### **Fase 4: Detalle Profundo, Render Diferido y Cierre Oficial**
9. **Paso 9 — Modal / Drawer de Detalle Completo con Render Diferido y Mutaciones**: 🟢 Completado y Validado.
   - Vista detallada de expediente y alerta con apertura instantánea y Skeletons de carga, renderizado del dictamen cualitativo IA (`analisis_semantico`), selector de cambio de estado y notas internas con mutación optimista.
10. **Paso 10 — Build de Producción y cierre beta de Capa 8**: 🟢 Compilado y verificado el 2026-08-06 con Node.js 24.19.0 LTS. `tsc -b` pasa en modo estricto sin errores.
     - Hay validación de tipos (`tsc --noEmit`) y compilación `npm run build`; no existe todavía una suite React independiente.
     - El bundle contiene la mutación por lote, el campo `modo_degradado` y el distintivo *"Pliego sin analizar"*. Se había supuesto desfasado por su fecha de modificación, pero al recompilar Vite generó los mismos nombres de fichero —que son un hash del contenido—, de modo que ya estaba al día.

---

## 🏗️ Capa 8.5: Cimientos de Infraestructura y Concurrencia (Bloque 1 Remediación)
* **Estado actual**: 🟢 Cerrada: WAL, `busy_timeout` de 30 s, cerrojo con PID/TTL, rutas ancladas a la raíz del proyecto, dependencias declaradas y TypeScript estricto. La ejecución desatendida de la Capa 10 ya **no** necesita fijar el directorio de trabajo.
* **Correcciones posteriores (2026-08-06)**: la Iteración 3 (aislamiento con `BASE_DIR`) estaba **incompleta**. Sólo la base de datos usaba ruta absoluta; `config/` y `data/` seguían resolviéndose contra el directorio de trabajo, de modo que ejecutar desde otra carpeta cargaba el perfil comercial **vacío** y puntuaba distinto sin avisar (71 frente a 47 en la misma licitación). Cerrado con `ruta_proyecto()` en `src/__init__.py`; ver hallazgo H-18. Además, la limpieza de cerrojos huérfanos **no llegaba a ejecutarse en Windows** — el `os.remove()` se hacía con el fichero aún abierto y el error quedaba silenciado. Un cierre abrupto seguía dejando el sistema bloqueado de forma permanente, pese a figurar como resuelto. Ver hallazgo H-15.

### 🎯 Objetivo
Reforzar la estabilidad operativa y la concurrencia del sistema local-first antes de abrir las Capas 9 y 10. Esta capa asegura un acceso multihilo/multiproceso libre de bloqueos en SQLite, la gestión resiliente de cerrojos de proceso (`.lock`) con tiempo de vida (TTL) e ID de proceso (PID), el aislamiento mediante rutas absolutas resueltas dinámicamente respecto a la raíz del repositorio, la formalización del entorno (`requirements.txt`, `.gitignore`, `.env.example`) y la activación del tipado estricto (`strict: true`) en el frontend TypeScript.

---

### 🔍 Alcance e Implementación Técnica

1. **Concurrencia SQLite de alto rendimiento (`busy_timeout` de 30s)**:
   - Configuración de `PRAGMA busy_timeout = 30000;` tanto en la capa DAO (`src/memoria.py`) como en la Pasarela API (`src/api/dependencies.py`). Previene excepciones `sqlite3.OperationalError: database is locked` e interrupciones `HTTP 503` en la API cuando coinciden escrituras en lote del pipeline con peticiones de la interfaz gráfica.

2. **Gestión Resiliente de Cerrojos (`licitaciones.db.lock` con TTL y PID)**:
   - Refactorización de la gestión del cerrojo de fichero (`GestorConcurrencia` en `src/memoria.py` / `src/utils.py`). El archivo `.lock` guardará un payload JSON con `pid` y `created_at` (timestamp UTC). Incorpora limpieza automática de locks "huérfanos" producidos por cierres abruptos (verificando si el PID sigue vivo en el SO o si han transcurrido más de 10 minutos).

3. **Aislamiento de Rutas Absolutas (`BASE_DIR`)**:
   - Garantizar que las rutas a la base de datos `data/licitaciones.db`, cerrojos `.lock` y registros `.jsonl` se calculen dinámicamente desde la raíz del proyecto (`BASE_DIR = Path(__file__).resolve().parent.parent`). Esto es un requisito crítico para que el script VBS silencioso (Capa 10) pueda invocar el pipeline con un directorio de trabajo arbitrario sin perder la referencia a la BD.

4. **Formalización del Entorno y Tipado Estricto Frontend**:
   - Creación de `requirements.txt` explicitando dependencias exactas (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`, `pymupdf`, `pytz`, `pyyaml`...).
   - Creación de `.gitignore` para blindar archivos locales (`licitaciones.db*`, `*.lock`, `data/pipeline.jsonl`, `venv/`, `node_modules/`, `.env`).
   - Plantilla `.env.example` con la variable obligatoria `GEMINI_API_KEY`.
   - Activación de `"strict": true` en `frontend/tsconfig.json` y `frontend/tsconfig.node.json`, solucionando cualquier advertencia de tipado en React/TypeScript.

---

### 🛣️ Plan de Desarrollo en 4 Iteraciones

#### **Iteración 1 — Resiliencia Concurrente SQLite (`busy_timeout = 30000ms`)**
- **Paso 8.5.1**: Actualización de la inicialización de conexiones SQLite en `src/memoria.py` y `src/api/dependencies.py` inyectando `PRAGMA busy_timeout = 30000;`. Creación de prueba de estrés concurrente en `tests/test_concurrencia_sqlite.py`.

#### **Iteración 2 — Cerrojo de Fichero Seguro con TTL y PID**
- **Paso 8.5.2**: Refactorización del lock en `src/memoria.py` (o `src/utils.py`) registrando `{"pid": ..., "created_at": ...}`. Implementación del chequeo de PID activo con `os.kill(pid, 0)` (o `psutil` si estuviera disponible) y caducidad por TTL (600s). Prueba unitaria de recuperación tras fallo en `tests/test_file_lock.py`.

#### **Iteración 3 — Aislamiento con Rutas Absolutas (`BASE_DIR`)**
- **Paso 8.5.3**: Estandarización de `BASE_DIR` en la configuración global y en `src/memoria.py`. Verificación de que la ejecución desatendida desde cualquier carpeta funcional (ej. `python run.py` desde un subdirectorio o ruta arbitraria) ubique y escriba la BD correctamente.

#### **Iteración 4 — Entorno, Dependencias y Frontend Strict (`requirements.txt`, `.gitignore`, `tsconfig.json`)**
- **Paso 8.5.4**: Creación de `requirements.txt`, `.gitignore`, `.env.example`, y activación de `"strict": true` en el frontend, ejecutando `npm run build` y `pytest` para verificar no regresión.

---

## ⚖️ Bloque 2: Coherencia de Negocio LCSP (Remediación)
* **Estado actual**: 🟢 Implementado el 2026-08-06. Contrato de servicio completo en [`.agents/CONTRATO_BLOQUE_2.md`](.agents/CONTRATO_BLOQUE_2.md).

### 🎯 Objetivo
Evitar que una oportunidad sea recomendada, descartada o presentada con una puntuación incompatible entre capas. El Radar aporta señales preliminares; el Analista IA sólo completa datos que consten en el pliego; y el Cockpit conserva el estado del lote exacto que el usuario ha decidido gestionar.

### 🔍 Correcciones aplicadas

1. **Escala de puntuación única**: `score_total` es un entero canónico en `[0, 100]`. La escala interna se conserva aparte en `score_bruto` para trazabilidad. Antes la Capa 2 llegaba a 165 puntos mientras la Capa 5 y la API asumían 0-100, y dos licitaciones muy distintas se mostraban ambas como 100.

2. **Cada riesgo cuenta una sola vez**: la señal textual preliminar del Radar ya no modifica la puntuación. La subrogación se ajusta **una única vez**, a partir de la clasificación semántica del pliego. Antes un contrato con subrogación crítica acumulaba −45 puntos por un solo hecho.

3. **Las negaciones se respetan**: *"No procedeix la subrogació de personal"* dejaba de penalizar. La detección por subcadena marcaba el riesgo incluso cuando el pliego lo negaba explícitamente.

4. **El LLM informa, no puntúa**: el `ajuste_score` que propone el modelo se conserva como información trazable pero **no se aplica**. Las decisiones de puntuación son deterministas y están configuradas en `config/`.

5. **Art. 145 alineado con este README**: un peso de precio/fórmulas superior al 60 % penaliza −10 puntos, por la guerra de precios que describe la sección de scoring. El predominio del juicio de valor **no** se penaliza: puede ser precisamente la ventaja competitiva de la cooperativa. Antes el código hacía justo lo contrario.

6. **Las seis cláusulas críticas**: el DTO sube a v3 e incorpora garantía definitiva (arts. 107-108), penalidades y resolución (arts. 192-194) y cláusulas sociales (art. 202). Si un dato no consta, se representa como `null` o `false`; nunca se deduce por conocimiento externo.

7. **Mutación por lote**: `lote_numero` recorre el contrato completo, de la API al Cockpit. Antes el backend mutaba siempre el lote 1 mientras el frontend actualizaba optimistamente todos, anulando el modelo 1:N que es la razón de ser de la Capa 3. *(Verificado en el bundle compilado el 2026-08-06.)*

8. **KPIs sobre una sola población**: el win rate y las métricas de conversión salen todos de `vista_win_rate`, filtrando lotes archivados. Antes el resumen y la vista analítica usaban denominadores distintos y el resultado era aritméticamente imposible.

9. **Lo que no se pudo medir, no puntúa**: un análisis degradado no altera la puntuación en ninguna dirección. No basta con no penalizar — bonificar también es inventar. La alerta llega al Cockpit **marcada**, no desaparece.

10. **La matriz de subrogación distingue el papeleo del riesgo real** *(criterio validado el 2026-08-06)*: la ausencia de la relación de personal del Art. 130.1 eleva el riesgo a ALTO pero ya no descarta, porque ese desglose suele obtenerse solicitándolo al órgano de contratación. El veto automático queda reservado a las plantillas de **más de 40 personas**, cuyo coste laboral compromete la estructura de la cooperativa aunque esté documentado. Y la subrogación de 1 a 5 personas con desglose completo recibe una bonificación intermedia de +2 puntos: es un riesgo acotado y presupuestable, no equiparable al de 20 personas.

11. **Nada se descarta en silencio** *(criterio validado el 2026-08-06)*: las alertas del Centinela que no alcanzan el umbral se guardan con sus motivos, fuera del canal principal, para poder auditarlas y reevaluarlas si cambian los umbrales o los PMP. El descarte automático (`DESCARTADA_POR_REGLAS`) y el decidido por una persona (`DESCARTADA_TEMPRANA`) son estados distintos, y una reejecución del pipeline nunca pisa el segundo.

---

## 💾 Capa 9: El Histórico y Depurador (Archivo y Purga de Datos)
* **Estado actual**: 💤 Pendiente de iniciar. Bloqueada únicamente por la recompilación del Cockpit.

### 🎯 Objetivo
Administrar el ciclo de vida completo de los datos históricos, facilitando la auditoría de prospecciones anteriores y permitiendo limpiezas selectivas o totales de la base de datos local mediante endpoints dedicados de administración en la API.

---

## 🚀 Capa 10: El Lanzador y Despertador (Silent Launcher VBS y Servicio Local)
* **Estado actual**: 🛠️ En planificación / Inicialización.

### 🎯 Objetivo
Garantizar la ejecución autónoma y ergonómica del ecosistema. Inicia el servidor FastAPI en segundo plano (`uvicorn`), ejecuta el pipeline del Radar y despliega el Cockpit Visual en el navegador sin mostrar consolas de terminal.


---

## 🧘 Pensaments de l'Antigravity
*Trazar un mapa no es predecir el futuro, sino dotar de orden al presente. Al estructurar este README con secciones en blanco preparadas para ser completadas, creamos el esqueleto sobre el cual depositaremos el conocimiento operativo que iremos ganando. Cada capa tendrá su momento de discusión, sus dudas y su código, y solo cuando el radar de la terminal esté emitiendo datos estables, nos sentaremos a detallar cómo limpiar ese ruido. Así es como la complejidad se transforma en una artesanía paso a paso.*
