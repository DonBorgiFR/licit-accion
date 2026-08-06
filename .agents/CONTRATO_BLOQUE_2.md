# Contrato de Servicio — Bloque 2: Coherencia de Negocio LCSP

**Versión:** 1.0.0 · **Estado:** implementado en beta tras validación de dirección de proyecto el 2026-08-06.

## Propósito

Evitar que una oportunidad sea recomendada, descartada o presentada con una puntuación
incompatible entre capas. El Radar aporta señales preliminares; el Analista IA sólo completa
datos que consten en el pliego; y el Cockpit conserva el estado del lote exacto que el usuario
ha decidido gestionar.

## Contrato de puntuación

**Entrada:** señales normalizadas del Radar/Filtro y, cuando exista, un `AnalisisSemanticoDTO`.

**Salida:**

* `score_total`: entero canónico en `[0, 100]`, calculado a partir de la escala bruta declarada
  en `config/perfil_incoop.yaml`.
* `score_recalibrado`: valor en `[0, 100]` con ajustes semánticos trazables.
* `motivos`: explicación determinista de cada suma, resta o ausencia deliberada de ajuste.

**Reglas invariantes:**

1. La señal textual preliminar de subrogación o revisión de precios no modifica el score.
2. La subrogación sólo se ajusta una vez, a partir de la clasificación semántica del pliego.
3. `dictamen.ajuste_score` emitido por un LLM se conserva como información, pero no se aplica:
   las decisiones de puntuación son deterministas y configuradas.
4. Si el análisis está degradado, se preserva el score cuantitativo sin inferir riesgos.
5. Un peso de precio/fórmulas superior al 60 % es una señal negativa para Incoop conforme al
   README; el predominio de juicio de valor no recibe penalización automática.

## Contrato de cláusulas críticas

Además de subrogación, revisión y criterios, el DTO v3 incorpora garantía definitiva (arts.
107–108), penalidades/resolución (arts. 192–194) y cláusulas sociales (art. 202). Si no consta
un dato, se representa como `null` o `false`; nunca se deduce por conocimiento externo.

## Contrato de mutación por lote

**Entrada:** `expediente_id`, `lote_numero`, `nuevo_estado`, `notas`.

**Precondición:** existe exactamente un lote activo con esa pareja `(expediente_id, lote_numero)`.

**Postcondición:** sólo ese lote cambia de estado/notas, la API devuelve el expediente actualizado
y el Cockpit actualiza y puede revertir únicamente el lote afectado.

## Máquina de estados

`RADAR_NORMALIZADO → FILTRO_CUANTITATIVO → PENDIENTE_ANALISIS → ANALIZADO`

* `ANALIZADO → RECALIBRADO` cuando el DTO es válido.
* `PENDIENTE_ANALISIS → ANALISIS_DIFERIDO` cuando falla el proveedor; no hay inferencia.
* `RECALIBRADO → NUEVA | ESTUDIANDO | PRESENTADA | ADJUDICADA | PERDIDA | DESCARTADA` sólo
  mediante una mutación dirigida al lote.

Transiciones prohibidas: un dictamen degradado no puede convertirse en recomendación automática;
una mutación de lote no puede actualizar los demás lotes del expediente.

## Trazabilidad y regresión

Las correcciones deben conservar eventos JSONL de análisis y mutación. Las pruebas cubren escala
canónica, negaciones, ausencia de doble penalización, Art. 145, cláusulas v3, KPI con misma
población y actualización por lote.
