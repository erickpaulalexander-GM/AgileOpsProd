# Timeline Global (ventana 4h, sin división por pool)

Objetivo: una única vista de Timeline, global (sin bloques por pool) y con ventana de 4 h anclada al minuto exacto de la corrida, que sea la vista por defecto. Filtro global por pool que afecta timeline, KPIs y tabla.

- Branch: `feature/timeline-global-view`
- Estrategia de entrega: `ask-on-risk`. Forecast inicial ~300 líneas < 400; real: 985 líneas autoradas (ver L15) → decisión de entrega pendiente (un solo PR vs cadena)
- Runner de tests: `& .venv-win\Scripts\python.exe -m pytest` (el `python` del PATH no tiene pandas). Cubre `python/` + `tests/test_timeline_global_view.py` (probe Node con DOM stub, skip si no hay `node`)

## Specs

S1. **Vista única y global, sin división por pool.** El Timeline deja de dividirse por pool: se eliminan los encabezados/bloques por pool. Las filas son una lista plana de recursos (`RECURSO ASIGNADO`) de todos los pools. (Cliente: "que no se divida por pool", "quita las vistas de los otros pools. para q no nos estorbe".)

S2. **Ventana visible de 4 h anclada al minuto exacto de la corrida.** La ventana visible del Timeline es de 240 min y arranca en `meta.updatedAt` (reloj de corrida, sin truncar a la hora). (Cliente: "el scrip corre 4:30 am y debe verse en el timeline de 04:30 AM hasta las 08:30 AM", "que el rango del timeline sea de las prox 4 horas, actualmete esta en 8hrs", opción A: "Anclar la vista global al minuto exacto de la corrida".)

S3. **Default "Todos".** Al abrir el dashboard, la vista muestra el universo completo (timeline + KPIs + tabla) sin filtro aplicado. (Cliente: "la vista global muestra todo, tabla kpi, timeline, etc.", "genera una vista que se la que salga por default".)

S4. **Filtro global por pool.** El selector actual (Yape / S&F / AgileOps ORO / AgileOps Prod) pasa a ser el filtro global, más una opción "Todos". Al cambiar el filtro se actualizan timeline, KPIs y tabla juntos. (Cliente: "si quiero ver los pases de yape aplico el filtro, este filtro afecta a todo timeline, kpi, tabla etc, si filtro por S&F igual todo se actualiza".)

S5. **Recorte de pases ya iniciados.** Un pase que ya empezó se recorta al borde izquierdo de la ventana (su tramo visible se dibuja completo). Un pase que empieza después de las 4 h no se muestra. (Cliente: "un pase inicio a las 3AM hasta las 5AM si corre el scrip a las 04:30 AM debe verse esa media hora del pase en curso. Por que eso significa que el recurso esta ocupado.")

S6. **Sin vista "Por pool" ni toggle.** No hay modo alterno de visualización. (Cliente: "que solo quede el global", "por ahora que conviva…" → revertido: "quita las vistas de los otros pools".)

Supuestos:
- A1: el filtrado por **recurso** (además de pool) queda para v2. (Cliente: "luego la idea es que la vista global se puede filtrar por recuro o pool. tenlo en cuenta para la siguiente versión.")
- A2: las filas se agrupan por `(pool, RESPONSABLE)` — igual que hoy — para no fusionar personas homónimas de pools distintos ni romper el sombreado de fuera-de-turno (que es por `pool` + `responsable`). El orden de las filas es por primer inicio y, como desempate, por responsable.

## Tasks

| ID | Descripción | Specs | Ruta | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| T1 | `timeline.js`: viewport de 4 h anclado a `meta.updatedAt` + recorte/ocultado de barras | S2, S5 | inline | done | `ff93f03` |
| T2 | `timeline.js`: render plano (sin encabezados de pool), conflictos y fuera-de-turno alineados al viewport | S1, S6 | inline | done | `ff93f03` |
| T3 | `timeline.css`: ancho de la ventana a 8 celdas + limpieza de estilos de pool header | S1, S2 | inline | done | `ff93f03` |
| T4 | `dashboard.js` + `dashboard_template.html`: default "Todos" y filtro global | S3, S4 | inline | done | `bb8035e` |
| T5 | `timeline.md`: documentar la vista global | S1, S2, S4 | inline | done | `ff93f03` |
| T6 | Verificación (pytest + generación de dashboard + verifier independiente) y Risk line | S1-S6 | inline | done | `88ef987` |

Risk de los commits `ff93f03` + `bb8035e` + `88ef987`: **item 6** (ningún test automático cubría el render: no había tests de frontend). Se declaró el riesgo, se lanzó un verifier independiente y el hallazgo se corrigió con su suite de regresión; a partir de `88ef987` el ítem queda mitigado por `tests/test_timeline_global_view.py`.

## Log

L1 (2026-10-19, pedido original): "actualmente hay un timeline por agrupación , pero me dicen que quieren uno vista global, osea q no se divida por pool y que el rango del timeline sea de las prox 4 horas, actualmete esta en 8hrs. genera una vista que se la que salga por default. realizame preguntas para estar sincronizados con el requerimiento."

L2 (2026-10-19, ancla): "sería desde la corrida ósea el scrip corre 4:30 am y debe verse en el timeline de 04:30 AM hasta las 08:30 AM. Así sucesivamente."

L3 (2026-10-19, agrupación y convivencia): "que muestre todo, ya si luego se puede filtrar sobre ese timeline sería genial. Cosa q se maneja una única vista pero versátil." / "por ahora que conviva para poder comparar y validar luego ya lo dejamos como único."

L4 (2026-10-19, recorte y alcance): "Si tal cual si un pase inicio a las 3AM hasta las 5AM si corre el scrip a las 04:30 AM debe verse esa media hora del pase en curso. Por que eso significa que el recurso esta ocupado." / "A la vista global si convence al cliente el resto será retirado y todo se trabajará con la vista global."

L5 (2026-10-19, opción de ancla): se elige la opción A (minuto exacto de la corrida) y se deja el filtrado por recurso/pool para v2.

L6 (2026-10-19, cambio de alcance): "creo q vamos con la opcion A, que solo quede el global quita las vistas de los otros pools. para q no nos estorbe. la vista global muestra todo, tabla kpi, timeline, etc. pero esto se pueda filtrar si quiero ver los pases de yape aplico el filtro, este filtro afecta a todo timeline , kpi, tabla etc, si filtro por S&F igual todo se actualiza". Al confirmar, se elimina la vista "Por pool" y el toggle.

L7 (2026-10-19, evidencia de código): estado actual verificado — `python/adapter.py` (`WINDOW_MINUTES = 480`, `floor_to_hour`) fija la ventana de 8 h; `web/components/timeline/timeline.js` agrupa por pool con encabezados (`_renderPoolHeader`, `_groupByPool`) y hardcodea `totalHours = 8` / `480 / CELL_MIN`; `web/dashboard.js` (ADR-011) aplica los grupos de visibilidad por defecto al primero (`YAPE`) y ya filtra KPIs/tabla/timeline de forma coherente. No se modifica el Data Contract: el contrato sigue agrupando por pool y el recorte de 4 h se resuelve en el frontend.

L8 (2026-10-19, riesgo): no existen tests de frontend (sólo `pytest` sobre `python/`), por lo que ningún test automático atraparía una regresión del render → Task Size high-risk item 6. Verificación: pytest completo + generación del dashboard de muestra + verifier independiente.

L9 (2026-10-19, implementación T1-T5): vista global de 4 h anclada al reloj de corrida.
- `timeline.js`: `VIEW_MINUTES = 240`; `_viewOffsetMin = updatedAt − windowStart` (`_computeViewOffset`, con `+1440` si la corrida cruza medianoche y degradación a 0 si el offset sale de `[0,240)`); `_minutesToPx`; `_clockLabel`/`_viewWindow`; grilla y header alineados al reloj con primera celda/segmento parcial (`CELL_MIN − off % CELL_MIN`); `_groupLanes` (agrupa por `(pool, responsable)`, orden por primer inicio y desempate por responsable) reemplaza a `_groupByPool`; `_clipToView` recorta a `[off, off+240]` y guarda `_visStart`/`_visEnd`; `_renderBars` dibuja una lista plana y `_renderConflicts` lee la misma lista con `_laneKey`; `_barsOverlap`/`_detectConflicts` usan el rango visible; `_offShiftHtml(pool, resp, off)` recorta igual pero el tooltip conserva los bordes reales; `scrollToHour` resta el offset y vuelve a 0 fuera del viewport. Se eliminan `_resolvePoolOrder`, `_orderedPoolNames`, `_poolOrder`, `_groupByPool` y `_renderPoolHeader`. API nueva: `viewWindow()`, `clockLabel(min)`, `visibleBarCount()`.
- `timeline.css`: `--timeline-pool-header-height` y el bloque de pool headers (`.timeline__pool-header*`, `.timeline__pool-dot`, `.timeline__pool-name`, `.timeline__pool-counts`) eliminados; los 5 `min-width` de eje pasan de `* 16` a `* 8` celdas; `.timeline__hour` sin ancho fijo por breakpoint (el ancho exacto lo pone JS) y `white-space: nowrap`.
- `dashboard.js`/`dashboard_template.html`: opción "Todos" (value `''`) al frente del selector; `_initialGroup()` devuelve `null` por defecto (id guardado sigue ganando si existe); `_onGroupChange('')` → `_applyGroup(null)`; el badge resetea su clase cuando no hay grupo; el contador usa `Timeline.visibleBarCount()` ("N pases en la vista") porque el contrato es de 8 h y el timeline dibuja 4 h; el estado vacío usa el conteo visible y muestra la ventana real ("04:30 y 08:30 (ventana de 4 h)"); label `Pool` → `Filtro`; typo "Pooles" → "Pools". `theme.css`: comentario de los acentos actualizado (ahora alimentan el badge del filtro, no un encabezado de pool).

L10 (2026-10-19, evidencia T1-T5): `node --check` OK en `timeline.js` y `dashboard.js`; `pytest` 197 passed (sin tests de frontend, el cambio es frontend-only); smoke vivo `run.py --now "2026-10-16 14:40"` → `meta.windowStart 14:00`, `updatedAt 2026-10-16T14:40:00`, 2 barras (15:00–16:00 y 19:00–20:00) → la ventana 14:40–18:40 debe dibujar 1 y descartar la de 19:00. Geometría verificada con un harness Node desechable (DOM stub, fuera del repo): offset 40 → header `14:40(64px) 15:00 16:00 17:00 18:00(128px)`, grilla `[64,96×7,32]` = 768px = 4 h, barra `left:64px width:192px`, `visibleBarCount()=1`, barra de 19:00 ausente. Caso 04:30 (offset 30): pase 04:00–06:00 recortado a `left:0px width:288px` (90 min), pase de 10:40 descartado, y dos "Ana" en pools distintos → 2 filas. `scrollToHour` dentro del viewport = 288px, fuera = 0.

L11 (2026-10-19, hallazgos preexistentes, NO corregidos): (a) `.timeline__grid-col::after` es `position:absolute` sin ancestro posicionado, así que las líneas dashed de media hora se apilan relativas a `.timeline__grid`; (b) `render()` llama `_renderBars()` antes de `_renderConflicts()`, así que `bar._hasConflict` se marca cuando el HTML de las barras ya está en el DOM y la clase `--conflict` nunca llega a aplicarse; el triángulo sí se dibuja. Ambos son previos a este cambio y quedan fuera de alcance.

L12 (2026-10-19, verificación independiente, veredicto por spec): S1 PASS, S2 PASS, S3 PASS, S4 PASS, S5 PASS, S6 PASS, A1 PASS, A2 PASS. Evidencia del verifier: contrato real con `--now "2026-10-16 14:40"` → offset 40, vista 14:40–18:40, header `[64,192,192,192,128]`, grilla `[64,96×7,32]` = 768 px, `visibleBarCount()=1` y la barra de 19:00 descartada; caso 04:30 con pase 03:00–05:00 recortado a `left:0px;width:96px` (30 min) y pase de 10:40 descartado; borde derecho 08:20–08:30 → `left:736px;width:32px`; dos "Ana" en pools distintos → 2 filas; orden de filas por primer inicio con desempate por responsable (`["Mia","Ana","Zoe"]`); fuera-de-turno sombreado por pool+responsable. Invariantes: `git diff c3b90d7..de6595f -- python/ tests/` vacío; `dashboard_data.json` con sha256 idéntico entre baseline y HEAD con el mismo `--now`; `pytest` 197 passed en ambos. Advisories AD1 y AD2 = L11(a) y L11(b) confirmadas como preexistentes en `c3b90d7`. AD3: un id de grupo guardado en `localStorage` sigue ganándole al default "Todos" (comportamiento previo, deliberado).

L13 (2026-10-19, corrección del bloqueante B1): el verifier encontró que `_renderGroupIndicator(view)` corría **antes** de `window.Timeline.init(...)` en `_applyGroup`, así que el contador "N pases en la vista" leía el `visibleBarCount()` del render anterior: en la carga mostraba `0 pases` con 1 barra dibujada y al pasar a S&F conservaba el número del grupo previo. `view.barCount` (baseline) se calculaba de forma síncrona, por eso el defecto lo introdujo este cambio. Fix en `88ef987`: el indicador se renderiza después del timeline. Recheck con el mismo probe de runtime del verifier, sin modificar: `RESULT ALL PASS` — `counts="1 pase en la vista · 113 filas en la tabla"` con `drawn bars=1` en la carga, `counts="0 pases en la vista · 22 filas en la tabla"` con `timelineBars=0` para S&F, y `window label="14:40 y 18:40 (ventana de 4 h)"`.

L14 (2026-10-19, red de seguridad): se incorpora `tests/test_timeline_global_view.py` (suite de regresión derivada por el verifier y validada por él en scratch, commiteada en `88ef987`): `test_s1_s6_no_pool_sections_or_toggle`, `test_s3_s4_todos_default_and_filter`, `test_s2_s5_a2_geometry` (probe Node con DOM stub, skip si no hay `node`) y `test_b1_indicator_rendered_after_timeline_init`. Estado: `pytest` 201 passed (197 previos + 4 nuevos); `node --check` OK en `timeline.js` y `dashboard.js`.

L15 (2026-10-19, RDD y entrega): RDD está **on** (decidido por default). `gentle-ai review assess --base-ref c3b90d7 --committed-only` se corrió dos veces: la primera devolvió `risk: high` con `reasons: [unassessable]` porque el feature doc estaba untracked (el tool exige declarar el inventario untracked) → se trató como **due** y por eso se resolvió primero la verificación independiente del item 6; la segunda, ya con el rango cerrado (`c3b90d7..a9fa2e8`), devolvió `risk: medium`, `reasons: [executable_change: tests/test_timeline_global_view.py]`, `review_due: false`, `review_due_reason: under_budget` → **no se inició review nativo**: el tier de verify ya cubrió el cambio y el slice queda pendiente bajo presupuesto. Tamaño acumulado de la rama: `8 files changed, 626 insertions(+), 359 deletions(-)` = 985 líneas autoradas (71 del feature doc + 99 de la suite de regresión + el resto en el componente y el dashboard), por encima del heurístico de ~400 → corresponde aplicar la estrategia de entrega `ask-on-risk` (una sola pregunta sobre `single-pr` vs cadena de PRs) antes de abrir el PR.
