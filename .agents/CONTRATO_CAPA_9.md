# Contrato de Servicio — Capa 9: El Histórico y Depurador

**Versión:** 1.1.0 · **Estado:** 🟢 **validado por dirección el 2026-08-07 · capa cerrada el 2026-08-12.**

> **v1.1.0 (2026-08-12, Paso 10)**: se retiran del contrato dos capacidades que nunca se
> implementaron —el error `PurgaBloqueadaPorMemoriaComercial` y la lista opcional de expedientes
> de la Operación 1— y se incorpora la cuarentena de la Operación 3. Un contrato que promete lo
> que no hay es peor que uno más corto: describe garantías que nadie sostiene.
Corresponde al **Paso 1** de la Capa 9 (Reglas 1 y 2). Los cuatro criterios de aceptación del final
del documento quedaron aprobados sin modificaciones.

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

### Corolario incorporado en el Paso 4: `deleted_at` no es un candado

Archivar gobierna **la visibilidad en el canal principal, no la editabilidad**. Un lote archivado
se sigue pudiendo consultar y editar: registrar el importe de una adjudicación, sus garantías o sus
costes. Simplemente no aparece en el Funnel salvo que se pidan expresamente las archivadas.

**Filtrar por `deleted_at` en una consulta de escritura es un defecto** (H-32). Lo era en la
mutación de estado, y hacía impracticable archivar cualquier estado que una persona necesite tocar:
como una adjudicación se resuelve mucho después de la fecha límite que provocó el archivado, el
registro de un contrato ganado quedaba congelado justo cuando toca completarlo.

**Editar no desarchiva.** Si lo hiciera, la corrida siguiente volvería a archivar —la fecha límite
sigue vencida— y el expediente entraría y saldría de la pantalla solo. Es la transición prohibida
nº 7 vista desde el otro lado. El rescate `ARCHIVADO → VIVO` sigue siendo explícito y vive en el
Paso 8.

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
| `Descartada` | Una persona la rechazó explícitamente. **Motivo de dirección (2026-08-07): evitar reprocesos.** Si se borrase, el pipeline volvería a capturarla y a presentarla, y el equipo comercial gastaría atención en mirar otra vez algo que ya descartó. El coste de conservar la fila es despreciable; el de volver a evaluarla, no. *(Coincide con el criterio del Paso D5 para el Centinela.)* |

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
| **Entrada** | Política de retención vigente. *(El contrato preveía además una lista explícita opcional de expedientes. **No se implementó y se retira en el Paso 10**: el archivado manual no se pide desde ninguna pantalla ni endpoint, y declarar una entrada que nadie acepta promete una capacidad inexistente. Si algún día hace falta archivar a mano, se añade entonces —con su plan y su prueba.)* |
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
| **Precondición** | Estado `ARCHIVADO`; **cuarentena cumplida** (`eliminacion.dias_archivado_minimo`, hoy 365 días — *dirección, 2026-08-12*); invariante de memoria comercial superada; **copia de seguridad previa correcta**. |
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
| ~~`PurgaBloqueadaPorMemoriaComercial`~~ | **Retirado en el Paso 10.** No es un error sino un resultado: la eliminación opera sobre listas, y la salida de la Operación 3 exige devolver *"los eliminados y —igual de importante— los bloqueados con su motivo"*. Una excepción no puede hacer las dos cosas. Cada expediente protegido vuelve en `bloqueados` con su motivo exacto. | — |
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
* **Esquema de base de datos**: **v7**. Subió a v6 con el ciclo de vida del dato (Paso 3) y a
  v7 con `rescatado_at` (Paso 8), que es lo que impide que el archivado automático deshaga un
  rescate pedido por una persona.

---

## Defecto detectado al redactar este contrato

### H-27 · El estado archivado se escribe con dos grafías distintas 🟢 CERRADO (Paso 3)

`EstadoLicitacionEnum` declara `"Inactiva"` y `"Anulada_Administracion"` (`schemas.py:75-76`),
mientras el Radar escribe `'inactiva'` y `'anulada_administracion'` en minúsculas
(`memoria.py:1102` y `1112`). Dos grafías del mismo estado en la misma columna.

**Hoy no rompe nada** porque `LoteSchema.estado_operativo` está tipado como `str` y el Radar
compara en minúsculas (`estado_op.lower()`). El sistema es coherente por accidente.

**Por qué importa ahora**: el Depurador tiene que seleccionar lo archivado, y un
`WHERE estado_operativo = 'Inactiva'` no devolvería **ninguna fila**. La invariante de memoria
comercial depende de comparar estados con exactitud.

**Cerrado en el Paso 3**, junto a la migración a v6: se normalizaron los valores existentes y se
unificó la escritura contra el enum. La regla que dejó tras de sí sigue vigente y es obligatoria:
**toda comparación de estado en la Capa 9 se hace normalizada** (`normalizar_estado_operativo()`),
nunca contra el literal. El motor de archivado del Paso 4 la aplica en su filtro de estados, y hay
una regresión que lo fija con las tres grafías a la vez.

---

## Criterios de aceptación del Paso 1 — 🟢 validados el 2026-08-07

1. 🟢 La separación entre estado comercial y estado de ciclo de vida, y que el Depurador no escriba
   jamás en `estado_operativo`.
2. 🟢 La lista de estados que bloquean la eliminación, **incluido `Descartada`**. Validado con un
   motivo adicional al previsto: **evitar reprocesos**. No se trata sólo de respetar la decisión de
   una persona, sino de no volver a gastar atención comercial en mirar lo mismo dos veces.
3. 🟢 Que el rescate `ARCHIVADO → VIVO` exista pero sea siempre manual.
4. 🟢 Que en caso de duda el Depurador no haga nada, en lugar de purgar parcialmente.

**Paso 1 cerrado.** Los Pasos 2 a 6 también lo están: política versionada, esquema v6 y **las tres
operaciones del contrato implementadas** —archivar, purgar peso documental y eliminar—. El estado
vigente de la capa vive en [`ESTADO.md`](ESTADO.md), no aquí — este documento es el contrato, y sólo
cambia cuando cambian sus reglas.

**Añadido el 2026-08-12 al implementar el Paso 6**: la cuarentena de la Operación 3 es una regla
nueva, no una relectura de las existentes. Un expediente archivado ayer no es eliminable hoy por
mucho que nunca fuera negocio, porque *archivar y borrar seguido* es la secuencia con la que se
destruye algo por error. El plazo vive en la política versionada y no en el código, de modo que
consta bajo qué criterio se ejecutó cada eliminación.
