# Contrato de Servicio — Capa 9: El Histórico y Depurador

**Versión:** 1.0.0 · **Estado:** redactado el 2026-08-07, **pendiente de validación de dirección**.
Corresponde al **Paso 1** de la Capa 9 (Reglas 1 y 2). Ningún paso posterior se implementa hasta
que este contrato quede validado.

---

## Propósito

Gobernar el ciclo de vida del dato distinguiendo dos naturalezas con destinos opuestos: el **peso
documental**, que pierde valor con el tiempo y es purgable, y la **memoria comercial**, que lo gana
y es intocable. El Depurador libera disco y ordena el histórico **sin poder destruir** lo que la
cooperativa ha aprendido licitando.

---

## Principio rector: dos dimensiones ortogonales

El error más fácil de cometer en esta capa es mezclar dos cosas que hoy conviven en la misma fila:

| Dimensión | Columna | Quién la escribe | ¿La toca la Capa 9? |
|---|---|---|---|
| **Estado comercial** — dónde está la oportunidad en el embudo | `lotes.estado_operativo` | La persona, desde el Cockpit; y el Radar al detectar ausencias en el feed | **NUNCA** |
| **Estado de ciclo de vida** — cuánto rastro físico conserva | `deleted_at`, `documentos.estado` | El Depurador | Sí, es su competencia |

**El Depurador no escribe jamás en `estado_operativo`.** No es su columna. Un expediente adjudicado
sigue adjudicado después de purgarse; lo que pierde son sus PDFs, no su condición de negocio.

> Hoy estas dos dimensiones están **entrelazadas**: el Radar escribe `estado_operativo='inactiva'`
> y `deleted_at` en la misma sentencia (`memoria.py:1102`). No es un defecto —ambas cosas son
> ciertas a la vez cuando una licitación desaparece del feed—, pero el contrato las separa
> conceptualmente para que el Depurador no herede esa confusión.

---

## Máquina de estados (Regla 2)

### A. Ciclo de vida del expediente

```
              (caduca / ausente del feed)            (previsualizar + confirmar)
   VIVO ──────────────────────────────────▶ ARCHIVADO ──────────────────────────▶ ELIMINADO
     ▲                                          │                                   (terminal)
     └──────────────────────────────────────────┘
                  (rescate manual, nunca automático)
```

| Estado | Representación | Significado |
|---|---|---|
| `VIVO` | `deleted_at IS NULL` | Operativo. Aparece en el Funnel y en los KPIs. |
| `ARCHIVADO` | `deleted_at IS NOT NULL` | Fuera del canal principal. **Sigue en la base y sigue contando** en los KPIs históricos. |
| `ELIMINADO` | la fila ya no existe | Reservado a lo que nunca llegó a ser negocio. **Terminal.** |

### B. Ciclo de vida del documento

```
DETECTADO → DESCARGANDO → DESCARGADO → PROCESADO → PURGADO
                    └──▶ ERROR_DESCARGA ──┘   (terminal salvo nueva descarga)
                    └──▶ OCR_PENDIENTE ───┘
```

`PURGADO` significa que el fichero se borró del disco y `texto_extraido` se vació. **La fila del
documento permanece**, con su URL, su hash y su rastro: se sabe qué hubo y por qué ya no está.

### C. Transiciones prohibidas

Son la parte sustantiva de este contrato. Cada una impide un daño concreto:

1. **`VIVO → ELIMINADO` directo.** Hay que pasar por `ARCHIVADO`. Impide borrar algo que está en
   juego ahora mismo.
2. **`ARCHIVADO → ELIMINADO` si algún lote invirtió negocio o criterio humano.** Es la invariante
   central; se detalla abajo.
3. **`ELIMINADO → cualquier cosa.`** Terminal. La reversión sólo existe restaurando una copia.
4. **Cualquier transición que altere `estado_operativo`.** No es competencia del Depurador.
5. **`PURGADO → PROCESADO` sin una descarga nueva.** El texto no reaparece por sí solo; volver a
   tenerlo es trabajo del Lector, no del Depurador.
6. **Cualquier purga sin copia de seguridad previa correcta.** Ver Modo Degradado.
7. **`ARCHIVADO → VIVO` automático.** El rescate existe, pero lo pide una persona. Si un criterio
   automático archivó algo y otro criterio automático pudiera desarchivarlo, el sistema oscilaría
   sin que nadie se entere. *(Mismo razonamiento que el Paso D5 aplicó al Centinela.)*

### D. La invariante central: qué bloquea la eliminación

Un expediente **sólo puede eliminarse físicamente** si **ninguno** de sus lotes alcanzó jamás uno
de estos estados:

| Estado alcanzado | Por qué bloquea |
|---|---|
| `Presentada` | Se invirtieron horas en preparar una oferta. Ese coste es el numerador del CAC. |
| `Adjudicada` | Es la memoria de lo ganado: adjudicatario, importe, garantía retenida. |
| `Perdida` | **Se aprende más de esto que de lo ganado.** Es el denominador del win-rate. |
| `Estudiando` | Alguien dedicó tiempo a evaluarla; consta como esfuerzo aunque no cristalizara. |
| `Descartada` | Una persona la rechazó explícitamente. Borrarla permitiría que el pipeline la volviera a capturar y a mostrar, resucitando lo que alguien ya decidió. *(Criterio del Paso D5.)* |

Es decir, sólo es eliminable lo que **nunca salió** de `Nueva`, `Inactiva` o
`Anulada_Administracion`: oportunidades que entraron por el feed, caducaron y a las que nadie
llegó a mirar. Ni negocio ni criterio humano invertidos.

**El estado no basta: se comprueba el histórico.** Un lote puede estar hoy en `Inactiva` habiendo
pasado por `Presentada`. Por eso la comprobación no mira el estado actual sino el rastro completo
en `expedientes.log_cambios` y en los campos comerciales (`importe_adjudicacion`,
`horas_internas_invertidas`, `costes_externos`, `importe_garantia_retenida`): **si alguno tiene
valor, hubo negocio.**

---

## Contrato de las tres operaciones (Regla 1)

### Operación 1 — Archivar

| | |
|---|---|
| **Entrada** | Política de retención vigente; opcionalmente una lista explícita de expedientes. |
| **Salida** | Recuento de expedientes y lotes archivados, con sus motivos. |
| **Precondición** | Base accesible; política válida y legible. |
| **Postcondición** | Los archivados tienen `deleted_at` y `deleted_reason`; salen del canal principal y **siguen contando en los KPIs históricos**. |
| **Efectos de lado** | Escritura en `lotes`/`expedientes` y evento JSONL. Ningún fichero se toca. |
| **Idempotencia** | Reejecutar no altera un `deleted_at` ya existente ni lo cuenta dos veces. |
| **Estado resultante** | `ARCHIVADO` |

### Operación 2 — Purgar peso documental

| | |
|---|---|
| **Entrada** | Política de retención (retención documental: **180 días**). |
| **Salida** | Documentos purgados, bytes liberados, copias rotadas. |
| **Precondición** | Permiso de escritura y borrado en `data/documents/`. |
| **Postcondición** | Ficheros eliminados del disco, `texto_extraido` vaciado, `documentos.estado='PURGADO'`. **Ninguna fila de `lotes` se modifica.** |
| **Efectos de lado** | Borrado de ficheros, escritura en `documentos` y en la tabla `purgas`, evento JSONL. |
| **Idempotencia** | Un documento ya `PURGADO` se salta sin error y sin contar. |
| **Estado resultante** | Documento `PURGADO`; expediente **inalterado** |

### Operación 3 — Eliminar físicamente

| | |
|---|---|
| **Entrada** | Lista explícita de expedientes **y confirmación explícita**. Nunca se deduce. |
| **Salida** | Eliminados, y —igual de importante— **los bloqueados con su motivo**. |
| **Precondición** | Estado `ARCHIVADO`; invariante de memoria comercial superada; **copia de seguridad previa correcta**. |
| **Postcondición** | Filas eliminadas en orden hoja→raíz: `documentos` → `analisis_semantico` → `lotes` → `expedientes`. Ningún huérfano. |
| **Efectos de lado** | Borrado en 4 tablas, copia de seguridad, registro en `purgas`, eventos JSONL. |
| **Idempotencia** | Un expediente inexistente se salta sin error. |
| **Estado resultante** | `ELIMINADO` (terminal) o **bloqueado**, nunca a medias |

**Atomicidad**: la eliminación va en una única transacción. Si una restricción `ON DELETE RESTRICT`
la interrumpe, se revierte entera. Nunca queda un expediente sin lotes ni un lote sin expediente.

> **Las claves foráneas no se desactivan.** `PRAGMA foreign_keys=OFF` está **prohibido** en esta
> capa: el `RESTRICT` es la red que impide dejar huérfanos, no un obstáculo a rodear. Si bloquea
> una eliminación, la respuesta correcta es detenerse e informar.

---

## Errores tipados

| Error | Cuándo | HTTP |
|---|---|---|
| `PurgaBloqueadaPorMemoriaComercial` | Se intentó eliminar un expediente con negocio o criterio humano invertido. | `409` |
| `PurgaBloqueadaPorIntegridad` | Una FK `RESTRICT` detuvo el borrado. Indica un caso no previsto: **es un defecto, no un uso normal**. | `409` |
| `CopiaSeguridadFallida` | No se pudo crear la copia previa. **La purga no se ejecuta.** | `503` |
| `PoliticaRetencionInvalida` | `config/retencion.yaml` ausente, ilegible o con plazos incoherentes. | `503` |
| `ConfirmacionRequerida` | Se pidió una eliminación sin confirmación explícita. | `400` |

Ningún error se degrada a un valor por defecto silencioso *(Convención C2)*. Un fallo de purga es
distinguible de una purga que no encontró nada que borrar.

---

## Modo Degradado (Regla 5)

El Depurador **se detiene**; no improvisa. Si no puede crear la copia previa, si el disco está
lleno, si falta la política o si la base está bloqueada por otro proceso, **no purga**: registra
`DEPURADOR_MODO_DEGRADADO` con la causa y devuelve `503`.

Purgar es irreversible. **En caso de duda, la degradación correcta es no hacer nada** — al revés
que en las capas de lectura, donde lo correcto era seguir con datos parciales.

---

## Eventos JSONL (Regla 3)

| Evento | Cuándo |
|---|---|
| `DEPURADOR_ARCHIVADO` | Cierre del archivado, con recuentos y motivos. |
| `DEPURADOR_PURGA_PREVISUALIZADA` | Alguien consultó qué se borraría. No altera nada, **pero consta quién miró**. |
| `DEPURADOR_PURGA_INICIADA` | Con la versión de política y la copia de seguridad asociada. |
| `DEPURADOR_PURGA_COMPLETADA` | Con documentos purgados y bytes liberados. |
| `DEPURADOR_PURGA_ABORTADA` | Con la causa. |
| `DEPURADOR_ELIMINACION_BLOQUEADA` | Qué expediente y qué invariante lo impidió. |
| `DEPURADOR_BACKUP_CREADO` | Ruta y tamaño. |
| `DEPURADOR_MODO_DEGRADADO` | Causa concreta de la degradación. |

---

## Versionado (Regla 4)

* **Contrato**: `1.0.0` (este documento).
* **Política de retención**: versionada en `config/retencion.yaml`. Cada purga registra bajo qué
  versión se ejecutó, para que un cambio de criterio no reescriba la historia de lo ya purgado.
* **Esquema de base de datos**: sube a **v6**.

---

## Defecto detectado al redactar este contrato

### H-27 · El estado archivado se escribe con dos grafías distintas 🔴 ABIERTO

`EstadoLicitacionEnum` declara `"Inactiva"` y `"Anulada_Administracion"` (`schemas.py:75-76`),
mientras el Radar escribe `'inactiva'` y `'anulada_administracion'` en minúsculas
(`memoria.py:1102` y `1112`). Dos grafías del mismo estado en la misma columna.

**Hoy no rompe nada** porque `LoteSchema.estado_operativo` está tipado como `str` y el Radar
compara en minúsculas (`estado_op.lower()`). El sistema es coherente por accidente.

**Por qué importa ahora**: el Depurador tiene que seleccionar lo archivado, y un
`WHERE estado_operativo = 'Inactiva'` no devolvería **ninguna fila**. La invariante de memoria
comercial depende de comparar estados con exactitud.

**Cierre previsto**: Paso 3, junto a la migración a v6 — normalizar los valores existentes y
unificar la escritura contra el enum. Hasta entonces, **toda comparación de estado en la Capa 9
se hace normalizada**, nunca contra el literal.

---

## Criterios de aceptación del Paso 1

Este paso se considera cerrado cuando la dirección valide:

1. La separación entre estado comercial y estado de ciclo de vida, y que el Depurador no escriba
   jamás en `estado_operativo`.
2. La lista de estados que bloquean la eliminación, **incluido `Descartada`**: borrar lo que una
   persona rechazó permitiría al pipeline resucitarlo.
3. Que el rescate `ARCHIVADO → VIVO` exista pero sea siempre manual.
4. Que en caso de duda el Depurador no haga nada, en lugar de purgar parcialmente.
