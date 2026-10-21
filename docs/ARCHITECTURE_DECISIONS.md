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
| `registrado` | Registrado, Pre Registrado (subcadena, intencional) |
| `aprobado` | Aprobado LT/CL QA/CL DEV/PO/Ops, Preaprobado (enmienda 2026-10-21) |

Los únicos estados que cuentan para KPIs y conflictos son los activos:
**Coordinado**, **Pase en curso**, **Ratificación total en curso** y
**Ratificación Parcial Satisfactorio**.

### Enmienda 2026-10-21 — familia Aprobado* y Preaprobado

Reporte del usuario: tickets en estado "Aprobado LT" aparecían en el KPI
Ratificaciones vencidas (OCD-237620, MVPLEGBCP-252621 en el artefacto del
2026-10-20). Causa: dos catálogos desalineados — la tabla operativa excluye
"Aprobado LT/CL QA/CL DEV/PO" (`EXCLUDED_TABLE_STATES`, adapter.py), pero
`TERMINAL_STATE_KEYWORDS` no contenía ninguna keyword que la matcheara.
Enmienda: se agregó la keyword `aprobado`, que por subcadena cubre toda la
familia `Aprobado *` y `Preaprobado`. Efecto: la familia desaparece de
vencidas, por-vencer, late starts (ya gated por Coordinado), conflictos y
todo scope derivado de `filter_operational()`. Este doc también corregía
de paso el desglose previo: la keyword `registrado` existía en el código
pero faltaba en la tabla.

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
  ratificationsExpired: [ … ],
  inFlightNow:          [ … ]   // T5 (2026-10-07): en curso cubriendo updatedAt
  staleInFlight:         [ … ]   // T6 (2026-10-07): en curso con FIN pasado
}
```

Cada registro: `ticket`, `app`, `resource`, `status` y los horarios necesarios
para su Drawer (`iniImpl`/`finImpl` o `iniRati`/`finRati`). `endRatiTotal`
(`FEC. HORA. FIN. RATI. TOTAL`) se incluye **solo** en `ratificationsExpired`
como dato **informativo**: no participa de KPIs ni de reglas (ADR-007 se mantiene
para el cálculo; ADR-008 lo re-habilita únicamente para mostrarlo).

### UI

- **Pases en ventana** → scroll al Timeline + resaltado ~1 s (sin Drawer).
  **Pases en curso** (T5) → Action Drawer con `inFlightNow`; la tarjeta
  titular muestra este scope, no la ventana.
  **Pases fuera de ventana** (T6) → Action Drawer con `staleInFlight`;
  tarjeta propia porque estos tickets no aparecen en ningun otro lado.
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

## ADR-009 The pool scope is data, not code

The operational pool scope is declared **once, as an ordered table in Python**,
and published to the frontend through the Data Contract. No pool list is ever
written twice.

### Problem

`ChangeOpsConsole` hardcoded its pool scope in **three** places across **two**
languages:

| Location | Literal |
|----------|---------|
| `python/column_map.py:81` | `R1_POOL_KEYWORDS = ["LEGACY", "YAPE"]` |
| `web/components/timeline/timeline.js:167` | `var poolOrder = ['Legacy', 'Yape'];` |
| `web/components/timeline/timeline.js:333` | `var poolOrder = ['Legacy', 'Yape'];` (a **second copy in the same file**) |
| `web/dashboard.js:396` | `r.pool === 'Legacy' ? 'badge--legacy' : 'badge--yape'` (binary ternary) |
| `web/components/timeline/timeline.js:309` | `poolName === 'Legacy' ? '#B45309' : '#7C3AED'` (binary ternary) |

Those copies were free to drift, and when they did, the failure was
**silent**. A pool present in Python but absent from the JavaScript array was
still written into `dashboard_data.json` — the contract was valid, the JSON
looked correct, the pool name appeared in the data — and the Timeline simply
never drew a row for it. No error, no warning, no empty state: the pool just did
not exist on screen. Adding a third family meant editing several of those
locations, and forgetting one produced a dashboard that quietly lied. The two
literals inside `timeline.js` are the sharpest illustration: `_renderBars` and
`_renderConflicts` each declared their own `poolOrder`, so the bar layer and the
conflict layer could disagree about the order in the same render pass.

There is a second, sharper reason this must be data and not code. The four
display pools are **not** the eight `RECURSO` values in the workbook. The eight
collapse into four families, and `-DERIVADO` is the **bar type**, not a pool.
Any list that lives in JavaScript is a list of *display families*; any list that
lives in Python is a list of *workbook resource values*. Two representations of
one concept, in two languages, with a mapping between them that nobody could see
in either place.

### Decision

1. **One ordered family table is the only place to edit.**
   `python/column_map.py::_POOL_FAMILY_RESOURCES` is a tuple of
   `(display family, (RECURSO values...))` pairs, in display order. Everything
   else is derived from it:

   | Derived symbol | Meaning |
   |---|---|
   | `POOL_FAMILY_ORDER` | Display order of the families |
   | `IN_SCOPE_RECURSO` | The 8 in-scope `RECURSO` values, flattened |
   | `IN_SCOPE_POOL_KEYS` | Normalized exact-match inclusion whitelist |
   | `_RESOURCE_TO_FAMILY` | Inverse index, normalized value → display family |

   `python/adapter.py` **imports** these; it never re-declares a literal pool
   value. `tests/test_pool_scope.py::test_adapter_source_does_not_duplicate_the_pool_list`
   reads `adapter.py` as text and fails if any of the 8 literals reappears there,
   so the duplication cannot come back silently.

2. **Python publishes `meta.poolOrder`.**
   `adapter.to_contract()` writes `meta.poolOrder = list(POOL_FAMILY_ORDER)`
   into the Data Contract. It is emitted unconditionally — the full list of 4
   families even when `timeline` is empty or a family has zero bars in the
   window. "Declared in scope" and "has bars in this window" are two independent
   facts, and collapsing them is what made the original bug invisible.

3. **The web layer reads it and hardcodes nothing.**
   `timeline.js::_resolvePoolOrder` resolves `meta.poolOrder` **once** in
   `init()`, and both render loops (`_renderBars`, `_renderConflicts`) iterate
   that single resolved list — so the bar layer and the conflict layer can never
   disagree about the order. A pool that carries bars but is missing from
   `poolOrder` is appended in alphabetical order rather than dropped; a missing or
   malformed `poolOrder` degrades to "every pool that has bars, alphabetical".
   There is no fallback array of pool names anywhere in `web/`.

4. **Family → CSS token is computed, not tabulated.**
   `Timeline.poolKey(pool)` is the single source of the name → slug mapping and
   is exposed on the public API so `dashboard.js` delegates to it instead of
   re-deriving the class name. `toLowerCase()` alone is not enough: `S&F`
   contains `&` and `AgileOps ORO` contains a space, both invalid in a class
   selector. Because the slug is computed, adding a family needs no JavaScript
   change at all.

5. **Inclusion matching is exact on a normalized value, never a substring.**

   `normalize_recurso()` upper-cases and removes **all whitespace** — and
   nothing else. Hyphens are preserved, so `Pool AgileOps Prod` can never
   collapse onto a hypothetical `POOL-AGILEOPS-PROD`.

   The reason is not style. A substring test answers the question "does this value
   **mention** one of my tokens", which is a different predicate from "**is** one
   of my pools". `ChangeOpsConsole` implemented the former:
   `column_map.py:100` was `return any(kw in upper for kw in R1_POOL_KEYWORDS)`
   against `R1_POOL_KEYWORDS = ["LEGACY", "YAPE"]`.

   On *this* workbook that predicate happens to accept only `POOL - YAPE`
   (8 rows), and a naive substring union of `AGILEOPS | YAPE | S&F` also lands
   on exactly the right 571 rows — **the current snapshot does not collide.**
   The rule is still exact-match-only, because that safety is a property of
   today's data, not of the predicate. Three concrete reasons:

   * **It is one edit away from a real defect.** The workbook contains
     `AUTOMATIZADO` (248) and `AUTOMATIZADO ITSM` (167) — a pair that differs by
     exactly one token. Any scope token those values happen to contain, or any
     future scope added by loose token, silently changes the operational universe
     and therefore every KPI. An enumerated exact whitelist makes that
     impossible: adding a pool adds one literal, and it cannot capture a
     neighbour.
   * **A token is not a family.** `AGILEOPS` matches **457** rows spanning four
     `RECURSO` values, and it cannot tell `AgileOps ORO` from `AgileOps Prod`.
     The tokens that discriminate are `AGILEOPSORO` and `AGILEOPSPROD`, which is
     precisely why `_FAMILY_TOKENS` is ordered and why
     `test_family_resolution_never_relies_on_agileops_alone` exists.
   * **Exact matching keeps the scope auditable.** The workbook has **17**
     distinct `RECURSO` values; the whitelist names 8 of them verbatim and
     excludes the other 9. "Why is this row in scope?" is answered by looking up
     one literal in one 8-entry table. With a substring matcher the same question
     has no local answer — it depends on the whole vocabulary of values that might
     appear, now or after the next workbook drop.

   `tests/test_pool_scope.py::test_substring_lookalikes_are_rejected` pins the
   behaviour explicitly, so the rule cannot be quietly relaxed later.

   Normalization is whitespace-and-case only because the real data demands
   exactly that much: `POOL S&F-DERIVADO` has no space before the hyphen while
   `Pool AgileOps ORO - Derivado` has several, and both must resolve to the same
   key. Nothing more.

6. **Family resolution is ordered, and `-DERIVADO` never becomes a pool.**
   `get_pool_name()` resolves the exact key first; only on a miss does it fall
   back to ordered family tokens `YAPE`, `S&F`, `AGILEOPSORO`, `AGILEOPSPROD`.
   `AGILEOPSORO` and `AGILEOPSPROD` are strictly longer than `AGILEOPS`, and
   they are evaluated in that order, so resolution never collapses onto
   `AGILEOPS` alone and cannot steal one family from another. The `-DERIVADO`
   distinction is read by `adapter.get_bar_type()` on the `type` axis and by
   `rules._is_implementation()` for conflicts — never by the pool resolver.

### Consequence

- Adding a pool family is a **one-line edit** in `column_map.py` plus CSS tokens.
  No JavaScript change, no contract shape change, no re-run of the frontend to
  teach it a new name.
- The pool enum in `docs/DATA_CONTRACT.md` is now a projection of the family
  table, not a second hand-maintained list.
- Cost: the Python engine is now load-bearing for display order. A malformed
  entry in `_POOL_FAMILY_RESOURCES` is a visible data defect rather than a
  silent render drop — which is the point.

## ADR-010 Workspace input/output layout, resolved from the repository root

Input lives under `workspace/input/`, output under `workspace/output/`, and
**both default paths resolve from the repository root, not from the current
working directory**.

### Context

`ChangeOpsConsole` was inconsistent. Its **output** was already anchored to the
module — `renderer.py:25,27` used `Path(__file__).parent.parent / "web"` and
`/ "output"` — but its **input was a bare relative string**: `main.py:61` and
`main.py:294` both used the literal `"data/ControlPases.xlsx"`, which resolves
against the **current working directory**.

That half-and-half split is the real defect, and it is a nasty one precisely
because the output worked. Running the pipeline from anywhere other than the repo
root failed with a bare `FileNotFoundError` on a file that plainly existed, and
because output *did* land in the right place in the working cases, the failure
looked like a missing or corrupt workbook rather than a CWD problem. A
double-click, a Task Scheduler job, an IDE task, or a manual `cd` each needed the
CWD to be the repo root.

This app fixes both halves with one rule — nothing resolves against the CWD — and
relocates both trees under a single `workspace/` namespace, so everything mutable
and everything supplied externally is visible at a glance and separated from the
source tree.

### Decision

| Path | Resolved from | Code |
|------|---------------|------|
| Default input | `REPO_ROOT / "workspace" / "input" / "ControlPases.xlsx"` | `python/main.py` |
| Template + CSS + JS | `REPO_ROOT / "web"` | `python/renderer.py` |
| Output | `REPO_ROOT / "workspace" / "output"` | `python/renderer.py` |

`REPO_ROOT = Path(__file__).resolve().parent.parent` — the parent of the
directory holding the module. `.resolve()` fully resolves symlinks and
normalisation, which the inherited `Path(__file__).parent.parent` did not.
`main.py` and `renderer.py` each compute it locally, because the `python/`
modules are imported flat (they sit on `sys.path` via `conftest.py` or via the
script's own directory), so they cannot share a package-relative import without
restructuring the module convention.

Because the anchor is `__file__` and not `os.getcwd()`, `main.py` resolves its
own default input with **zero arguments** and still writes to the repository's
own `workspace/output/`, from any directory. `sys.argv[1]`, when present,
overrides only the input; the output directory is never configurable.

### How to prove it

Run the pipeline with **no arguments** from a directory that is not the repo
root and confirm the artifacts land in the repository, not in the CWD:

```powershell
Set-Location C:\Windows
& 'D:\IA_DEV\AgileOpsProd\.venv-win\Scripts\python.exe' 'D:\IA_DEV\AgileOpsProd\python\main.py'
'EXIT=' + $LASTEXITCODE      # 0
Get-ChildItem 'D:\IA_DEV\AgileOpsProd\workspace\output'
```

Expected: exit code `0`, and `dashboard.html`, `dashboard_data.json` and
`diagnostic_report.json` freshly written under
`D:\IA_DEV\AgileOpsProd\workspace\output\`. If the run instead reports a missing
workbook or writes relative to `C:\Windows`, the root resolution has regressed.

The same property is what makes the pipeline usable from Task Scheduler on the
client machine, where the "Start in" directory is not the repo root and there
are no `.bat` launchers to set it (see `workspace/input/dev-report.txt`).

### Notes

- `workspace/output/*` is git-ignored except `.gitkeep`;
  `workspace/input/*.xlsx` is git-ignored entirely — the workbook is supplied
  externally and is not versioned.
- `renderer.py` substitutes the `<title>` tag by exact byte match
  (`TEMPLATE_TITLE_TAG`). If `web/dashboard_template.html` changes that tag, the
  renderer logs a warning and the HTML keeps the raw title.

## ADR-011 Pool visibility groups - a presentation filter, not access control

The dashboard lets the reader switch between **visibility groups**: YAPE,
S&F and AgileOps. Every consumer of operational data - the Timeline, the
table, the four KPI cards and the three action drawers - renders **only** the
active group's rows.

**This is a presentation filter. It is not access control, and it is not
security.** This ADR states that limitation in the decision itself so it can
never be misread downstream.

### Problem

A person working a single pool family does not need - or want - the other
families' passes on screen. Before this decision there was one view with all
four families, and no way to narrow it.

The tempting fix is a filter over the rendered rows. That fix alone is
insufficient and, worse, dishonest: the KPI cards aggregate `meta.kpis`, which
is global, and the action drawers read `window.ChangeOpsActions`, which is one
global payload whose records carry no pool field at all (ADR-008). A row-level
filter would therefore have produced a screen where the bars were YAPE-only
while the "Atrasados: 3" card still counted AgileOps' late starts - a
dashboard that lies about the data it is showing.

### Decision

**1. The groups are declared in `python/column_map.py` as pool FAMILIES, never
as `RECURSO` values.**

```python
_VISIBILITY_GROUPS = (
    ("yape",     "YAPE",     ("Yape",)),
    ("sf",       "S&F",      ("S&F",)),
    ("agileops", "AgileOps", ("AgileOps ORO", "AgileOps Prod")),
)
```

Each group's `resources` list is **flattened from the existing
`_POOL_FAMILY_RESOURCES` table**, so there is no second `RECURSO` literal list
anywhere and a group cannot smuggle in a value the pool whitelist does not
already accept. This is the principle of ADR-009, applied one level up.

**2. The group table is validated as a PARTITION, once at import.**

`_build_visibility_groups(POOL_FAMILY_ORDER, _VISIBILITY_GROUPS)` raises
`ValueError` on an orphaned family (invisible in every view = silently lost
data), a duplicated family, an unknown family, a duplicated id, an empty id or
label, or an empty group. A malformed visibility definition must be a loud data
defect at startup, never a silent render drop - the exact failure ADR-009 was
written to eliminate.

**3. Python publishes the groups AND their aggregates; the web layer hardcodes
nothing.**

| Contract location | Content | Emitted by |
|---|---|---|
| `meta.visibilityGroups[]` | `id`, `label`, `families`, `resources` | `adapter.to_contract()` |
| `meta.visibilityGroups[].kpis` | `lateStarts`, `ratificationsSoon`, `ratificationsExpired`, `reversions` | `kpi.update_contract_visibility_kpis()` |
| `meta.visibilityGroups[].tickets` | ticket ID sets per action scope | `kpi.update_contract_visibility_kpis()` |

The global `meta.kpis` **stays**: it is the contract's overall aggregate and
other consumers may read it.

Per-group `kpis` is not optional. Without it the cards cannot be scoped, and a
scoped table next to a global card is the lie described above.

**4. The drawers are scoped by ticket membership, not by duplicated records.**

`window.ChangeOpsActions` is one global payload (ADR-008) whose records have no
pool field. Rather than republishing per-group copies - which would let two
copies of one record drift - the contract publishes, per group, the ticket ID
sets `passesInWindow`, `lateStarts`, `ratificationsSoon` and
`ratificationsExpired`. The web layer filters the global payload by
membership. One copy of the record data; every drawer scoped.

**5. One render pass reads one view object.**

`web/dashboard.js::_groupView()` builds the single object every consumer reads:

```
{ kpis, timeline, table, actions, barCount, rowCount }
```

`_applyGroup()` is the only render pass. `renderKPIs`, `_onKPIClick`,
`renderTable`, `_buildTableIndex` and `Timeline.init` all take their input from
that object, so no render function can accidentally read the unfiltered
contract. The Timeline is re-`init`ed with the filtered contract - it rebuilds
`_allBars` / `_rowMetrics` / `_poolOrder` internally, and
`web/components/timeline/*` was not modified.

**6. Default and persistence.**

The default is the **FIRST** declared group (`yape`). There is no safe
universal default - no group is more privileged than another - so declaration
order decides, and it is decided in Python, not in the browser. The choice is
persisted to `localStorage` under `agileops-visibility-group`; a missing,
empty, unknown or stale value falls back to the first group. Because
`storageGet()` is wrapped in a `try` (SharePoint sandbox, see the file header),
a `localStorage` that throws degrades to the first group rather than breaking
the page.

**7. Degradation is explicit.**

A contract without `meta.visibilityGroups` (an older generated file) is left
untouched by Python, and a group whose `tickets` object is malformed makes the
web layer log `console.error` and fall back to the **unfiltered** payload
rather than show an empty drawer. Hiding real data would be worse than showing
all of it.

### The limitation, stated plainly

| Property | Reality |
|---|---|
| Data at rest | **All** groups' rows and records are embedded in the single generated `dashboard.html` and `dashboard_data.json`. |
| Devtools / source view | Any reader can read every group's data, including the groups not selected. |
| Transport | One file, one payload. There is no server and no per-user session. |
| `localStorage` | A convenience, not a guard. It is user-writable and trivial to bypass. |

Real enforcement would need a different architecture: split the payload per
group, or serve it from a backend that authorises the caller and returns only
the rows that caller may see. Neither exists here.

**Do not describe this feature as restricting access, as "role-based
visibility", or as anything that protects data.** It narrows what is rendered.

### Consequences

- Every consumer had to be routed explicitly, and a missed one is a silent
  leak: a card or drawer reading global data while the rest of the screen is
  filtered. `tests/test_visibility_groups.py` and the three-group union
  assertion exist to catch exactly that.
- `meta.visibilityGroups` is now part of the contract.
  `docs/DATA_CONTRACT.md` documents it; a v1 consumer that ignores it still
  works, because Python keeps `meta.kpis` and the web layer degrades when the
  key is absent.
- The group definition is a **partition**, so the union of the groups'
  records equals the full in-scope dataset (three groups at ADR-011 time,
  four since T11 — same invariant, asserted in tests), and the
  global KPI object is not always the sum of the groups: rows outside every
  group (i.e. outside the pool whitelist) contribute to the global object only.

## ADR-012 The window is anchored to the RUN CLOCK

**This ADR supersedes ADR-005's anchor choice.** It does **not** revise or
delete ADR-005: that record stays as history. Read it for the *single
temporal reference* principle, which this ADR keeps; its choice of **what**
anchors that reference is what changes.

### What was reversed

ADR-005 declared, verbatim:

> El "ahora" de las reglas es `meta.updatedAt`, NO el reloj del sistema. Esto
> hace la salida determinista para un mismo Excel y respeta la decisión de que
> el dashboard es una foto, no un seguimiento continuo.

and set the anchor to the workbook's modification time:

```python
meta.updatedAt = Path(excel_path).stat().st_mtime
```

ADR-012 reverses exactly that: the anchor is now the **run clock** — the system
time at which the pipeline executes — captured once per run.

### Why

The dashboard is executed by **Windows Task Scheduler** on the client machine.
The requirement, from the product owner, is: *if the task runs at 09:55, the
timeline must show the window starting at 09:00.*

The Excel mtime cannot express that, because for the real workbook it is a
**copy artifact**: `workspace/input/ControlPases.xlsx` reports
`2026-10-05 21:40:36`, which is when the file was dropped onto the machine, not
when its contents changed. Anchoring to it produced a `21:00 → 05:00` window
while the operator was working the 09:00 shift. ADR-005's "deterministic photo"
property was real, but it was determinism about the wrong instant.

### Decision

1. **One reference, sourced from the clock.** `python/main.py` computes the
   reference exactly once:

   ```python
   anchor_dt = _resolve_reference_now(reference_now)  # datetime.now() if None
   ```

   Every consumer still flows from that **single** value: the window
   (`compute_window(anchor_dt)`), the rules' `reference_now`, the operational
   table's live-work filter and `meta.updatedAt`. This preserves the good half
   of ADR-005 — one reference, never two — and changes only its source. No
   second temporal reference is introduced.

2. **A `--now` override makes a run reproducible.** Because the clock is not
   reproducible, `main(excel_path, reference_now=None)` accepts an explicit
   reference and the CLI exposes it:

   ```powershell
   python python\main.py --now "2026-10-06 09:55"
   ```

   The value flows through the **same** single-reference path; it is not a
   parallel one. `--now` accepts several formats (`2026-10-06 09:55`,
   `2026-10-06T09:55`, ...). An unparseable value is a **loud** error
   (`argparse` exits non-zero); it never silently falls back to the clock.
   `python python\main.py` with no arguments keeps working, because that is the
   form the scheduler uses.

3. **The Excel mtime is kept, but demoted to diagnostics.** It is still useful
   to spot a stale workbook in a scheduled run, so it is reported in
   `diagnostic_report.json` as `excelFileMtime` (with
   `excelFileMtimeSource = "excel_file_mtime"`). It can no longer influence the
   window, the rules or the table filter in any code path.

4. **`updatedAtSource` tells the truth.** The diagnostic now records whether the
   anchor came from an organic run (`"run_clock"`) or a reproduced one
   (`"now_override"`), so a reader can distinguish them. Previously it was
   hardcoded to `"excel_file_mtime"`.

5. **The latent second reference inside `adapter.to_contract` is removed.**
   Its signature defaulted `window=None` and fell back to
   `compute_window(datetime.now())`. That fallback read the wall clock while the
   main path read the Excel mtime — two references in one system, the precise
   defect ADR-005 was written to eliminate, reintroduced one layer down. Every
   caller already passed a window, so `to_contract` now **raises `ValueError`**
   when `window` is missing instead of inventing one.

### Cost, and its mitigation

The output is **no longer deterministic for the same Excel**. Two runs of the
same workbook at different times produce different windows, timelines, table
rows and KPIs. That cost is accepted because the dashboard is meant to track the
current shift, not to be a fixed photograph.

The mitigation is the `--now` override: a run that must be reproduced exactly
(support, an incident review, a test) is pinned with an explicit reference, and
the diagnostic records `updatedAtSource = "now_override"` so the pinning is
visible. `tests/test_run_clock.py` uses this path for every clock-anchored
assertion.

### What does NOT change

- The Data Contract **shape** is untouched: only the provenance and the values
  of `updatedAt` / `windowStart` / `windowEnd` change. `web/*` is not modified.
- The single-reference principle of ADR-005, ADR-006's terminal-state exclusion,
  ADR-007's freeze, ADR-008's action payload, ADR-009's pool scope, ADR-010's
  path resolution and ADR-011's visibility groups are all intact.
- ADR-005 remains in this file as the historical record of the mtime anchor.

### How to prove it

```powershell
# Reproduced run: window must start at 09:00.
python python\main.py --now "2026-10-06 09:55"
#   meta.updatedAt = 2026-10-06T09:55:00, windowStart = 09:00, windowEnd = 17:00
#   diagnostic.updatedAtSource = now_override

# Organic run: window follows the real clock.
python python\main.py
#   windowStart = floor(current hour)
#   diagnostic.updatedAtSource = run_clock
#   diagnostic.excelFileMtime = the workbook's mtime (diagnostic only)
```

## ADR-013 AgileOps ORO Derivado is its own pool

**Partial exception to ADR-009, at the client's request — REVERTED the same
day (T12), at the same requester's request.** The lanes must read exactly
like every other pool, so ORO Derivado is bar type inside ORO again and this
ADR is historical record only. The 4th topbar filter (T11, `oro` group owning
the whole ORO family) stays.

What was decided (and reverted) is preserved verbatim below.

**Partial exception to ADR-009, at the client's request.** ADR-009 stays the
rule — every other `-DERIVADO` variant remains bar type, never pool — but
`Pool AgileOps ORO - Derivado` now resolves to its own family,
`AgileOps ORO Derivado`, with its own timeline row, right after `AgileOps ORO`.

### Why

Operators read ORO and ORO-Derivado as separate lanes, the way Yape and S&F
are separate rows. Merging 32 + 39 rows into one ORO row hid the lane they
work in. Only ORO splits: S&F-Derivado, Prod-Derivado (and Yape-Derivado)
keep the ADR-009 treatment, so the change is deliberately asymmetric.

### Decision

1. **One table row.** `_POOL_FAMILY_RESOURCES` gains
   `("AgileOps ORO Derivado", ("Pool AgileOps ORO - Derivado",))` between ORO
   and Prod. Position is display order: `meta.poolOrder` now carries 5
   entries and the timeline renders 5 rows. Inclusion is untouched — the same
   8 `RECURSO` values, so scope counts (571 in the reference workbook) do
   not move.
2. **Token before base.** `_FAMILY_TOKENS` checks `AGILEOPSORODERIVADO`
   before `AGILEOPSORO` (exact-table hits never reach the fallback, but an
   unknown spelling variant must not collapse onto the base family).
3. **Same group.** The `agileops` visibility group owns the new family, so
   the partition invariant holds and no pool goes dark in any view.
   T11 (2026-10-07): the group later split in two — `oro` (ORO + Derivado)
   and `prod` (Prod) — for a 4th topbar filter at the client's request.
   T12 (2026-10-07): reverted with the family — `oro` now owns ORO alone,
   `prod` owns Prod; both filters stay.
4. **Full token set.** `agileops-oro-derivado` gets `--color-*` +
   `--pool-accent-*` (light + dark), `.badge--*`, `.timeline__pool-header--*`
   and `.timeline__bar--*`, exactly like any family per `timeline.md`.
5. **Bar type unchanged.** Derivado rows keep `type: "derivado"` (dashed
   frame) inside their own row — lane and type stay orthogonal.

### How to prove it (historical — asserted while the split lived)

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests/test_pool_scope.py tests/test_timeline_grouping.py tests/test_visibility_groups.py -q
#   poolOrder has 5 entries; ORO-Derivado resolves to its own family;
#   the agileops group owns 3 families; the whitelist still holds 8 values
```

## ADR-014 The timeline draws overlap, not just window starts

At the operator's request: lane occupancy must read NOW. A pass that started
before the 8h window but is still alive at its left edge is drawn clipped to
that edge (`start: 0`, visible duration), so a resource working a pass never
looks free. This reverses nothing — ADR-012's anchor and single reference
stand; only the timeline's *membership* widens from starts-inside to overlap.

### Decision

1. **Overlap, proven.** `filter_to_window()` keeps a pre-window row only with
   a valid `FIN_IMPL` past the window start. No valid FIN = no provable
   overlap = out, the same rule T6 uses for colgados.
2. **Clip in the backend.** `_compute_start_duration()` clips both edges to
   `[0, 480]`; the frontend receives valid geometry and does not change.
   Rows, flags, KPIs and the table are untouched — same dict objects, only
   the bar dict carries clipped minutes.
3. **Stale rows may clip too.** An `en curso` row with FIN between the window
   start and now renders as a sliver at the left edge. That is correct lane
   information (it just finished); the stale drawer stays the action point.

### How to prove it

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests/test_window_overlap.py -q
#   pre-window alive -> drawn clipped; spanning -> full grid; finished/
#   missing-FIN/future -> out; in-window geometry byte-identical
```