# Feature: table-filters (OpsTable + catálogo único de pools)

- Objetivo: extraer la tabla operativa a un componente propio (`OpsTable`) con pipeline único (filtros por columna, ventana "próxima hora", orden) y unificar el catálogo de pools en `Timeline.poolInfo()` para que barras, leyenda, columna Pool y filtro de pool compartan una sola fuente.
- Rama: `feature/table-filters` apilada sobre `feature/timeline-global-view` (PR #1). Entrega: **PR aparte** (decisión del usuario, L2), base = rama del timeline.
- Test runner: `& .venv-win\Scripts\python.exe -m pytest` (el `python` del PATH no tiene pandas) + `node --check` sobre los JS.
- Tamaño: ~1.090 líneas autoradas en tres unidades de trabajo (T1 catálogo, T2 componente, T4 filtros de fecha); T2 y T4 superan el presupuesto de 400 → se recomienda `size:exception` (ver L4, L7).

## Specs

Los comportamientos S1-S6 están reconstruidos desde el código implementado: el pedido original de esta iteración no quedó registrado en Engram (ver A1). S5 sí tiene ancla de requisito previo del usuario (L1).

- **S1 — Pipeline único, nunca duplicado**: source rows → `enrich` (normaliza y conserva originales) → filtros por columna → modo temporal (próxima hora | todos) → orden → render + contadores. Todo vive en `web/components/table/table.js`; `dashboard.js` sólo delega (`OpsTable.setRows(rows, DATA.meta, group)`).
- **S2 — Filtros por columna**: texto (RECURSO ASIGNADO, Ticket, NOMBRE APP), chips de valores (Tipo, Estado Actual), chips de pool, rango de fechas (Inicio/Fin Impl) y reset de filtros. **Cada extremo del rango es un `<select>` que ofrece exactamente los timestamps presentes en los datos visibles, en orden cronológico** — sin tipeo libre (ancla L7: "aqui el filtro de la fecha solo debe salir las disponibles del archivo fuente"). El valor lleva el año del reloj de referencia (el contrato sólo trae "DD/MM HH:MM" → epoch ms con corrección de borde Dic/Ene ~6 meses), las fechas no parseables nunca entran al catálogo, y cada extremo acota al opuesto: un "desde" posterior al "hasta" no se ofrece porque sólo puede dar vacío.
- **S3 — Modo temporal "próxima hora"**: ventana de 60 min anclada a `meta.updatedAt` (el mismo reloj del Timeline 4 h; sin `Date.now()`). Toggle "Próxima hora (HH:MM – HH:MM)" ↔ "Todos los registros". Las filas cuyo INICIO/FIN no se pueden parsear nunca reciben horario inventado: quedan fuera de la proyección de la próxima hora y al final de la lista completa. Contrae a "todos" si no hay reloj utilizable.
- **S4 — Orden y contadores**: orden estable por columna (asc/desc), contador de filas visibles, filtros/orden/modo sobreviven al cambio de grupo de visibilidad.
- **S5 — Catálogo único de pools** (ancla: "la vista global se puede filtrar por recurso o pool"): `POOL_CATALOG` en `timeline.js` + `Timeline.poolInfo()`/`poolNoneId`. Un valor en blanco o "Unknown" → chip neutro "SIN POOL" (nunca adivinado); un alias del catálogo → ese pool; cualquier otro valor → chip neutro con su propio nombre, sin mapear. Alimenta: chips de las barras del timeline, leyenda del timeline (ahora generada desde el catálogo, no hardcodeada en el HTML), la columna Pool de la tabla y el filtro de pool.
- **S6 — Integración**: `python/renderer.py` inlinea `table.js` igual que `timeline.js` (mismo mecanismo de reemplazo del `<script src>`); `dashboard_template.html` carga el componente y declara el contenedor de toolbar; `renderTable` sólo llama a `OpsTable.setRows`. El filtro global por pool (grupo de visibilidad) sigue filtrando el dataset que llega a la tabla.

## Tasks

| ID | Specs | Ruta | Estado | Commit |
|----|-------|------|--------|--------|
| T1 | S5 | inline | done | `bfcbd0b` |
| T2 | S1-S4, S6 | inline | done | `7598386` |
| T3 | A2 | inline | done | `6e7c6dd` (docs); PR apilado abierto tras `7598386` |
| T4 | S2 | inline | done | `576d600` (fix de layout) + `dace8bd` (selects desde la fuente) |

## Log

L1 (2026-10-20, origen): trabajo encontrado ya escrito pero **sin commitear** en el worktree, sin registro del pedido original en Engram (sesiones 2026-10-19 13:51 en adelante no dejaron observación). El alcance de S1-S6 se reconstruyó del código (ver A1). El usuario pidió revisar "donde quedo el proyecto" y luego "como PR aparte".

L2 (2026-10-20, decisión del usuario, verbatim): "como PR aparte / en que quedó?"

L3 (2026-10-20, evidencia previa a los commits):

L3 (2026-10-20, evidencia previa a los commits): `pytest` 203 passed (197 previos + 4 de timeline + 2 nuevos de tabla); `node --check` OK en `table.js`, `timeline.js` y `dashboard.js`; smoke `run.py --now "2026-10-16 14:40"` → `dashboard.html` 198.706 bytes con `window.OpsTable` inlineado, sin `<script src>` residual, toolbar y contenedor de leyenda presentes, `poolInfo` exportado; `dashboard_data.json` sha256 `2B18F73D8F309C9F…`.

L4 (2026-10-20, tamaño y slicing): total autorado del tramo ≈ 806 líneas (`table.js` 536, `theme.css` 112, `test_table_pipeline.py` 78, `timeline.js` 69, `dashboard.js` 68, template 7, `renderer.py` 5, test de timeline −1/+1). Un único slicing honesto: T1 (catálogo, ~71 líneas) y T2 (componente, ~806). T2 no puede bajar de 400 sin partir el IIFE en dos PRs artificiales que empeorarían la revisión → se entrega como un solo PR con recomendación `size:exception` para el maintainer.

L5 (2026-10-20, verificación y entrega): `gentle-ai review assess --base-ref origin/feature/timeline-global-view --committed-only` → `risk: medium` (`executable_change: python/renderer.py`), `review_due: false`, `review_due_reason: under_budget` → sin review nativo (el tier de verify cubrió el cambio). `pytest` 203 passed sobre el árbol commiteado.

L6 (2026-10-20, commits): tree limpio tras los tres commits `6e7c6dd` (docs) + `bfcbd0b` (T1, catálogo) + `7598386` (T2, componente). `pytest` 203 passed sobre el árbol commiteado. Pendiente: assess RDD sobre `b516270..HEAD` y push + PR apilado (T3).

L7 (2026-10-20, T4: layout + selects desde la fuente, verbatim): el usuario aprobó "opción A" para arreglar el desborde del filtro de fecha (label arriba, campo encoge, reset con `visibility:hidden` para no reflowear la fila), y luego pidió: "aqui el filtro de la fecha solo debe salir las disponibles del archivo fuente". Cambio: los `datetime-local` de INICIO/FIN IMPL pasaron a `<select>` con las opciones derivadas de `dateOptions()` sobre las filas visibles (42 valores de INICIO y 45 de FIN en la fuente real, `exact_match=true` por extremo; el HTML generado no conserva ningún `datetime-local`, los selects se arman en runtime). Evidencia: `pytest` **206 passed** (203 + test de layout + test sintético de catálogo + test anclado al archivo fuente); probe de runtime con DOM propio contra `dashboard_data.json` → `INICIO 42/42 exact_match=true`, `FIN 45/45 exact_match=true`, 4 selects, "Sin límite" presente. Commits: `576d600` (fix de layout con su test CSS) + `dace8bd` (feat selects con los 3 tests); retoque de comentario CSS ("datetime field" → "date select") viajó en `dace8bd`. Gotcha: `_esc()` redondea el texto por un `<div>` (set `textContent`, lee `innerHTML`); un stub de DOM que no imita el escaping reporta cada `<option value>` como `""` y hace parecer roto el producto — el producto nunca estuvo roto. `size:exception` sigue pendiente de decisión del maintainer.

L8 (2026-10-20, assess RDD tras T4): `gentle-ai review assess --base-ref origin/feature/timeline-global-view --committed-only` sobre el rango (incluye `576d600`, `dace8bd`, docs) → `risk: medium` (`executable_change: python/renderer.py`, 1161 líneas, 10 paths), `review_due: false`, `review_due_reason: under_budget` → sin review nativo; la frontera queda en pie para un corte posterior que alcance el presupuesto. `pytest` 206 passed sobre el árbol commiteado.
