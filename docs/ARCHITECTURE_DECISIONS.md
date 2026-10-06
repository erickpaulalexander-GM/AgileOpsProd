# Architecture Decision Records

## ADR-001 Timeline independiente

El timeline se desarrolla como componente desacoplado.

Motivo:
- futuras integraciones Jira
- zoom
- nuevas torres
- SharePoint

Archivos propietarios:

```
web/components/timeline/
    timeline.css
    timeline.js
    timeline.md
```

## ADR-002 Timeline CSS Grid (no tables)

El Timeline se construye con CSS Grid y capas posicionadas, nunca con `<table>`.

Motivo:
- Resaltar barras desde KPIs
- Abrir drawer al clickear
- Marcar conflictos con triángulos
- Mantener scroll horizontal sin reescribir

Estructura de capas:

```
Timeline
├── Header (horas)
├── Grid (30 min)
├── Layer de barras
├── Layer de indicadores
└── Layer de selección
```

## ADR-003 Tema claro/oscuro via data-theme

Se usa `data-theme="light|dark"` en `<html>` para alternar temas sin duplicar HTML.

Motivo:
- SharePoint reduce el área útil
- Sin `position:fixed` en layout principal
- Variables CSS en `:root` + `[data-theme]`

## ADR-004 Minutos desde inicio de ventana

Internamente el Timeline usa minutos desde el inicio de la ventana, no horas decimales ni strings "HH:MM".

### Ejemplo

| Hora  | Minutos |
|-------|---------|
| 23:00 | 0       |
| 23:30 | 30      |
| 00:00 | 60      |
| 01:30 | 150     |

### Barra de ejemplo

```json
{
  "ticket": "247397",
  "start": 60,
  "duration": 30
}
```

### Fórmulas de posición

```
left   = start * 80 / 30     (px)
width  = duration * 80 / 30   (px)
```

### Por qué

- Cruces de medianoche: 23:30 → 00:30 se resuelven con aritmética simple
- Detección de solapamientos: `a.start < b.start + b.duration`
- Cálculo de posición: sin parsear strings "HH:MM"
- Duración: un solo campo `duration`, no `end - start`

### Reglas

- Python convierte todos los HH:MM a minutos antes de entregar al frontend
- El frontend nunca parsea "HH:MM" para posicionamiento
- `start` y `duration` son siempre enteros (minutos)

## ADR-005 Ventana dinámica anclada a la última actualización del Excel

La ventana sigue siendo de **8 horas fijas**, pero su **inicio es dinámico**:
se ancla a la **única referencia temporal del dashboard**, el `mtime` del Excel.

> **Corrección v1.1.3.** El ancla era `max(FECHA DE REGISTRO)`, lo que generaba
> una inconsistencia: la cabecera ya usaba el `mtime` mientras el Timeline usaba
> `FECHA DE REGISTRO`. A partir de v1.1.3 **todo el dashboard usa una única
> referencia temporal**: `meta.updatedAt = Path(excel_path).stat().st_mtime`.
> **No se creó un ADR nuevo**; esta es la versión corregida de ADR-005.

### Implementación

- Ancla = **`meta.updatedAt`** = `Path(excel_path).stat().st_mtime` (mtime del Excel).
- `windowStart = floor_to_hour(mtime)`, `windowEnd = windowStart + 8h`.
  Ejemplo: mtime `2026-09-11 05:08:09` → ventana `05:00 → 13:00`.
- Solo se incluyen barras cuyo **inicio de implementación** cae dentro de la ventana.
  Las barras fuera de ventana se descartan y se cuentan en `diagnostic_report.json`
  (`barsOutsideWindow`).
- La duración se recorta a 480 min para no salir de la grilla.

### Referencia temporal única (v1.1.3)

| Consumidor | Referencia |
|---|---|
| Cabecera `Actualización:` | `meta.updatedAt` (mtime) |
| Ventana del Timeline | `floor(mtime)` + 8 h |
| Reglas ("ahora") | `meta.updatedAt` (mtime) |
| Filtro de la tabla operativa | `FEC. HORA. FIN. IMPL >= meta.updatedAt` |

El "ahora" de las reglas es **`meta.updatedAt`**, NO el reloj del sistema. Esto
hace la salida **determinista** para un mismo Excel y respeta la decisión de que
el dashboard es una foto, no un seguimiento continuo.

### Motivo

- `TIMELINE_SPEC.md`: "Inicio desde la última actualización del Excel".
- Una única referencia elimina la inconsistencia cabecera ↔ Timeline ↔ tabla.
- Con datos reales, una ventana fija a las 23:00 dejaría el dashboard vacío.
- No cambia la **forma** del Data Contract v1: solo varían los valores de
  `windowStart` / `windowEnd` / `updatedAt`. El frontend congelado no se toca.

### Regla "Inicio atrasado" (corregida)

`Estado == "Coordinado"` **y** el sello de actualización supera en más de
5 minutos el inicio planificado de implementación. No se compara contra
`FECHA DE REGISTRO` (que siempre es anterior al inicio).

## ADR-006 Exclusión de estados terminales en KPIs operativos

Los **KPIs operativos** y la **detección de conflictos** se calculan solo
sobre filas **no terminales**. Los estados terminales no representan trabajo
pendiente, así que no pueden generar atrasos, alertas de ratificación ni
conflictos.

### Estados terminales

Coincidencia por palabra clave normalizada (sin acentos, minúsculas):

| Palabra clave | Cubre |
|---|---|
| `cerrado` | Cerrado, Cerrada |
| `terminado` | Terminado, Terminado Satisfactorio |
| `rechazado` | Rechazado, Rechazada |
| `cancelado` | Cancelado, Cancelada |
| `anulado` | Anulado, Anulada |

Los estados operativos (Coordinado, Registrado, Pase en curso, Aprobado LT,
Aprobado CL QA, Aprobado CL DEV, Ratificación Parcial Satisfactorio) **sí**
cuentan.

### Alcance

- **KPI scope** = filas R1 no terminales (una fila por registro, sin dedup),
  referencia `updatedAt` (ADR-005).
- **Timeline scope** = sin cambios: barras cuya implementación cae en la
  ventana dinámica de 8 h. ADR-005 intacto.
- El frontend congelado no se modifica.

### Implementación

- `rules.py`: `TERMINAL_STATE_KEYWORDS`, `normalize_state()`, `is_terminal()`,
  `filter_operational()`. Las reglas de ratificación y el detector de
  conflictos **saltan** las filas terminales.
- `diagnostic_report.json`: bloque `kpiScope` con `operationalRows`,
  `excludedTerminal` y `terminalStatesExcluded` (desglose por estado).

## ADR-007 Feature Freeze v1.0 — alcance de ratificación y reversiones

Congela el alcance de los KPIs de ratificación y reversión para v1.0.

### Ratificación

- **`FIN_RATI` (`FEC. HORA. FIN. RATI`) es la única referencia de fin de
  ratificación** para los KPIs operativos.
- **`FIN_RATI_TOTAL` (`FEC. HORA. FIN. RATI. TOTAL`) NO se usa**: no está
  mapeada, no se parsea y no participa de ninguna regla. Se eliminó toda
  lógica pendiente asociada.
- KPIs derivados:
  - *Ratificación por vencer*: `0 ≤ (FIN_RATI_INI − updatedAt) ≤ 10 min`.
  - *Ratificación vencida*: `updatedAt > FIN_RATI`.

### Reversiones

- `reversions` se mantiene como KPI **"Próximamente"** con valor `0`.
- **No lee ninguna columna del Excel.** Las columnas de reversión
  (`TIEMPO REVERSION`, `FEC_HOR_INI_REVERSION`, `FEC_HOR_FIN_REVERSION`)
  ya no están mapeadas ni se parsean.
- **Fuente futura: JIRA.**
- El campo se conserva en el Data Contract v1 (valor 0) para no romper la
  forma del contrato ni el frontend congelado.

### Invariantes de v1.0

- No se modifica el **frontend** (`web/*`).
- No se modifica la **forma del Data Contract v1**.
- ADR-005 (ventana dinámica) y ADR-006 (exclusión de terminales) intactos.

## ADR-008 Action Payload — Action Drawers sin tocar el contrato

Los KPIs dejan de ser contadores y pasan a ser **puntos de acción**, sin
modificar el **Data Contract v1**.

### Arquitectura

- Se mantiene `window.MockOperations.data` (Data Contract v1, **byte-idéntico**).
- Se agrega `window.ChangeOpsActions`, un payload **separado y no-contrato**,
  emitido por `renderer.py`.

### Payload

```
window.ChangeOpsActions = {
  passesInWindow:       [ … ],
  lateStarts:           [ … ],
  ratificationsSoon:    [ … ],
  ratificationsExpired: [ … ]
}
```

Cada registro: `ticket`, `app`, `resource`, `status` y los horarios necesarios
para su Drawer (`iniImpl`/`finImpl` o `iniRati`/`finRati`). `endRatiTotal`
(`FEC. HORA. FIN. RATI. TOTAL`) se incluye **solo** en `ratificationsExpired`
como dato **informativo**: no participa de KPIs ni de reglas (ADR-007 se mantiene
para el cálculo; ADR-008 lo re-habilita únicamente para mostrarlo).

### UI

- **Pases en ventana** → scroll al Timeline + resaltado ~1 s (sin Drawer).
- **Pases atrasados / Rati. por vencer / Rati. vencidas** → Action Drawer
  (reutiliza el Drawer derecho existente; sin modales nuevos).
- Ticket clicable (`<a target="_blank">`, cursor pointer, Enter nativo) →
  `https://bcp-ti.atlassian.net.mcas.ms/browse/<ticket>` (sin prefijos hardcodeados).
- El Drawer **permanece abierto** al abrir JIRA (nueva pestaña).
- Compatible con el sandbox de SharePoint (sin `localStorage`, sin red).

### Invariantes

- Data Contract v1: **sin cambios de forma ni de valores por este ADR**.
- ADR-005, ADR-006 y ADR-007 intactos.
- Sin reglas de negocio nuevas: el payload deriva de flags ya calculados.



