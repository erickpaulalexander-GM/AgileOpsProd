# Data Contract v1

Official contract between the data engine (Python / Excel) and the frontend
(`workspace/output/dashboard.html`).

The contract shape is **frozen** (ADR-007). This document describes the shape
*as implemented today* in this repository: `pool` carries the four AgileOps Prod
pool families and `meta.poolOrder` publishes their display order (ADR-009).

---

## Structure

Values below are the real values of the last pipeline run on
`workspace/input/ControlPases.xlsx` (see the "Verified run" section at the end).

```json
{
  "meta": {
    "updatedAt": "2026-10-05T21:40:36",
    "windowStart": "21:00",
    "windowEnd": "05:00",
    "poolOrder": ["Yape", "S&F", "AgileOps ORO", "AgileOps Prod"]
  },
  "kpis": {
    "lateStarts": 3,
    "ratificationsSoon": 0,
    "ratificationsExpired": 24,
    "reversions": 0
  },
  "timeline": [
    {
      "pool": "AgileOps Prod",
      "bars": [
        {
          "ticket": "MVPAGIPROD-251005",
          "name": "ANX5",
          "type": "implementacion",
          "start": 0,
          "duration": 60,
          "status": "coordinado"
        }
      ]
    }
  ],
  "table": [
    {
      "responsable": "Tony Clinton Calixto Lujan",
      "pool": "AgileOps Prod",
      "type": "Implementación",
      "ticket": "MVPAGIPROD-251005",
      "nombre_app": "ANX5",
      "status": "Coordinado",
      "inicio_impl": "05/10 21:00",
      "fin_impl": "05/10 22:00"
    }
  ]
}
```

`timeline[]` and `table[]` are examples of the *shape*; the ticket, app and
person values are illustrative placeholders, not real rows from the run.

---

## Fields

### `meta`

| Field | Type | Description |
|-------|------|-------------|
| `updatedAt` | string (ISO 8601, no timezone) | The single temporal reference of the whole dashboard: the **Excel file modification time** (`Path(excel_path).stat().st_mtime`). Set in `python/main.py`. |
| `windowStart` | string (`HH:MM`) | Start of the 8-hour window: `floor_to_hour(updatedAt)`. |
| `windowEnd` | string (`HH:MM`) | End of the window: `windowStart + 8h`. May cross midnight. |
| `poolOrder` | array of string | **Display order of the four pool families.** Emitted by Python (see below). |
| `visibilityGroups[]` | array of object | **Visibility groups the reader can switch between.** Emitted by Python (see below). ADR-011. |

#### `meta.poolOrder` (ADR-009)

| Property | Value |
|----------|-------|
| Emitter | Python — `python/adapter.py::to_contract`, from `column_map.POOL_FAMILY_ORDER` |
| Consumer | `web/components/timeline/timeline.js::_resolvePoolOrder` (called once in `init()`) and `web/dashboard.js` |
| Cardinality | Always **all 4** families, in this exact order: `Yape`, `S&F`, `AgileOps ORO`, `AgileOps Prod` |
| Empty-window behaviour | Unchanged: the full list is emitted even when `timeline` is `[]` |

* It is the **single source of display order**. The web layer contains no
  hardcoded pool list; it resolves this array once and both render loops
  (`_renderBars`, `_renderConflicts`) read the same resolved list.
* A family that has **zero bars in the current window renders no rows**, but it
  is still published in `poolOrder`. This is what guarantees that a pool never
  silently disappears from the dashboard: "declared" and "has bars" are two
  independent facts.
* `timeline[]` may be **shorter** than `poolOrder`, and may also contain a pool
  that is *not* in `poolOrder` (unmapped `RECURSO` variant). The frontend
  renders `poolOrder` first, then appends any pool that carries bars but is
  missing from `poolOrder`, in alphabetical order, so an unmapped pool can
  never be dropped.
* If `poolOrder` is missing or malformed, the frontend degrades to "every pool
  that actually has bars, alphabetical". It never falls back to a hardcoded list.

#### `meta.visibilityGroups[]` (ADR-011)

The pool visibility groups the reader can switch between. **A presentation
filter, not access control** — see the limitation note at the end of this
section.

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable group key, also the `localStorage` value. First entry is the default. |
| `label` | string | Display label, rendered verbatim in the selector. |
| `families` | array of string | Pool **family** names (the `pool` enum). Never `RECURSO` values. |
| `resources` | array of string | The `RECURSO` values of those families, flattened from `_POOL_FAMILY_RESOURCES`. |
| `kpis` | object | Same shape as the top-level `kpis`, computed over this group's rows only. |
| `tickets` | object | Ticket-ID sets per action scope, used to scope the action drawers. |

Current groups, all three emitted unconditionally:

| # | `id` | `label` | `families` | Default |
|---|------|---------|------------|---------|
| 1 | `yape` | `YAPE` | `Yape` | **yes** |
| 2 | `sf` | `S&F` | `S&F` | no |
| 3 | `agileops` | `AgileOps` | `AgileOps ORO`, `AgileOps Prod` | no |

##### `meta.visibilityGroups[].tickets`

| Field | Type | Description |
|-------|------|-------------|
| `passesInWindow` | array of string | Tickets with a row in the 8h window, for this group. |
| `lateStarts` | array of string | Tickets whose `_late_start` flag is set, for this group. |
| `ratificationsSoon` | array of string | Tickets whose `_ratification_soon` flag is set. |
| `ratificationsExpired` | array of string | Tickets whose `_ratification_expired` flag is set. |

These are **ID sets, not record copies**. `window.ChangeOpsActions` stays one
global payload (ADR-008) with no pool field; the web layer filters it by
membership in the active group's set. One copy of the record data, every drawer
scoped. A ticket can legitimately repeat inside a scope (the same ticket with
two different assigned resources), so the array length is the number of
**records** to render, and the deduplicated count is the number of distinct
tickets.

##### Invariants

* The groups are a **partition** of the four pool families. Every family is in
  exactly one group, so the union of the groups covers the whole in-scope
  dataset and no record is invisible in every view.
  `column_map._build_visibility_groups()` raises `ValueError` at import if that
  stops being true.
* The top-level `kpis` is **not always the sum of the groups**: rows outside
  every group (outside the pool whitelist) contribute to the global object
  only.
* If the key is missing (an older generated file) the web layer renders the
  unfiltered dashboard. Python leaves such a contract untouched rather than
  raising.
* If a group's `tickets` object is malformed, the web layer logs
  `console.error` and falls back to the **unfiltered** action payload. Hiding
  real data would be worse than showing all of it.

##### Limitation — read before relying on this

> All three groups' rows and records are embedded in the **same**
> `dashboard.html` / `dashboard_data.json`. Anyone can read every group's data
> from the file or from devtools, including the groups not selected. The
> `localStorage` key is a convenience, not a guard. Real enforcement needs a
> per-group payload split or an authorising backend; neither exists here.
> Full statement in ADR-011.

### `kpis`

| Field | Type | Description |
|-------|------|-------------|
| `lateStarts` | number | Late starts (`rules.LATE_START_THRESHOLD`, terminal states excluded) |
| `ratificationsSoon` | number | Ratifications about to start (within `rules.RATIFICATION_SOON_THRESHOLD`) |
| `ratificationsExpired` | number | Ratifications already past `FIN_RATI` |
| `reversions` | number | Always `0`. Placeholder KPI, future source JIRA (ADR-007). Reads no Excel column. |

### `timeline[]`

One element per pool **that has at least one bar in the window**. Groups with no
bars are omitted entirely (`python/adapter.py::to_contract`).

| Field | Type | Description |
|-------|------|-------------|
| `pool` | string | Pool family name — **exactly one of** `"Yape"`, `"S&F"`, `"AgileOps ORO"`, `"AgileOps Prod"` (see `pool` enum below) |
| `bars[]` | array | The bars of that pool |

#### `pool` enum

The `pool` field is a closed enum of exactly four values, and those are the only
four values that ever appear in the contract:

| # | `pool` | CSS token slug | Matching `RECURSO` values |
|---|--------|----------------|--------------------------|
| 1 | `Yape` | `yape` | `POOL - YAPE`, `POOL - YAPE-DERIVADO` |
| 2 | `S&F` | `sf` | `Pool S&F`, `POOL S&F-DERIVADO` |
| 3 | `AgileOps ORO` | `agileops-oro` | `Pool AgileOps ORO`, `Pool AgileOps ORO - Derivado` |
| 4 | `AgileOps Prod` | `agileops-prod` | `Pool AgileOps Prod`, `Pool AgileOps Prod - Derivado` |

`timeline[].pool` and `table[].pool` share this enum — they are produced by the
same function, `column_map.get_pool_name()`.

#### CSS token slugs

The frontend derives every class name from `Timeline.poolKey(pool)`. The mapping
is computed, never looked up in a table, so a new family needs no JavaScript
change:

| `pool` | slug | Bar fill token | Pool-header accent (light / dark) | Badge class |
|--------|------|----------------|-----------------------------------|-------------|
| `Yape` | `yape` | `--color-yape` | `#B45309` / `#FB923C` | `.badge--yape` |
| `S&F` | `sf` | `--color-sf` | `#7C3AED` / `#A78BFA` | `.badge--sf` |
| `AgileOps ORO` | `agileops-oro` | `--color-agileops-oro` | `#1D4ED8` / `#38BDF8` | `.badge--agileops-oro` |
| `AgileOps Prod` | `agileops-prod` | `--color-agileops-prod` | `#BE185D` / `#F472B6` | `.badge--agileops-prod` |
| *(no pool)* | `unknown` | `--bg-hover` | `var(--border-strong)` | *(no rule — falls back to the base `.badge`)* |

`pool.toLowerCase()` is **not** sufficient: `S&F` contains `&` and
`AgileOps ORO` / `AgileOps Prod` contain a space, all invalid in a class
selector. `poolKey()` therefore lower-cases, drops combining marks, turns
whitespace/underscores into `-`, drops every remaining non-`[a-z0-9-]`
character and trims `-`. `dashboard.js` delegates to `window.Timeline.poolKey`
so the badge class can never drift from the bar token.

### `timeline[].bars[]`

| Field | Type | Description |
|-------|------|-------------|
| `ticket` | string | Ticket ID (e.g. `"MVPAGIPROD-251005"`). Also the bar label rendered on screen. |
| `name` | string | `NOMBRE APP`, truncated to 50 chars. Shown in the bar's `title` tooltip. |
| `type` | string | `"implementacion"` or `"derivado"` — **the `type` axis, not the pool identity** (see below) |
| `start` | number | Integer minutes from `windowStart` (ADR-004). Always in `[0, 480)`. |
| `duration` | number | Integer minutes. Clipped so `start + duration <= 480`. |
| `status` | string | `"coordinado"`, `"pase-en-curso"` or `"inicio-atrasado"` |

> **A bar has no `pool` field.** The pool is carried **only** by the enclosing
> `timeline[].pool` group. `timeline.js` injects it onto each bar when it
> flattens the contract (`pool: group.pool`), which is why the frontend's
> `Unknown` fallback cannot fire for a valid contract — a bar that reached
> `_groupByPool` without a group would have had no parent to inherit from.

#### `type` enum: `implementacion` | `derivado`

`type` has exactly two values and they live on the **bar axis**, never on the
pool axis:

* `python/adapter.py::get_bar_type()` returns `"derivado"` when the raw
  `RECURSO` value contains the token `DERIVADO`, otherwise `"implementacion"`.
* `python/rules.py::_is_implementation()` uses the same predicate for conflict
  detection.

**The `-DERIVADO` resource variant maps to `type`, not to a separate pool.**
`POOL - YAPE-DERIVADO`, `POOL S&F-DERIVADO`, `Pool AgileOps ORO - Derivado` and
`Pool AgileOps Prod - Derivado` resolve to the **same** pool family as their
non-derivado sibling. The dashboard therefore shows 4 pool rows with two bar
styles inside each, never 8 pool rows.

### `table[]`

The operational table: the **full in-scope pool universe**, restricted to live
active work. Column order is the render order in `web/dashboard.js`.

| Field | Type | Description |
|-------|------|-------------|
| `responsable` | string | `RECURSO ASIGNADO` (person). Empty string when the cell is empty. |
| `pool` | string | Same closed enum as `timeline[].pool` |
| `type` | string | `"Implementación"` or `"Derivado"` — the table's own label casing of the same `type` axis |
| `ticket` | string | Ticket ID |
| `nombre_app` | string | `NOMBRE APP` |
| `status` | string | `ESTADO ACTUAL`, raw workbook value |
| `inicio_impl` | string | `FEC. HORA. INI. IMPL` formatted as `DD/MM HH:MM` |
| `fin_impl` | string | `FEC. HORA. FIN. IMPL` formatted as `DD/MM HH:MM` |

Table scope (all three filters are ANDed, one row per record, no dedup, sorted
by planned start ascending):

1. `RECURSO` is in the 8-value in-scope whitelist (exact match after
   normalization — ADR-009).
2. `ESTADO ACTUAL` is one of the active operational states `Coordinado` /
   `Pase en curso` (`adapter.TIMELINE_ALLOWED_STATES`).
3. **Live work only**: `FEC. HORA. FIN. IMPL >= meta.updatedAt`. Finished
   implementations drop out.

`table[]` is deliberately **not** window-scoped: it is the operational universe,
not the 8-hour slice.

---

## Rules

1. **Minutes from window start** (ADR-004). `timeline[].bars[].start` is an
   integer count of minutes measured from `windowStart`, never a decimal hour and
   never an `"HH:MM"` string. Computed by
   `adapter.datetime_to_window_minutes()` as a real datetime delta, so it is
   day-aware. `table[]` ships pre-formatted `DD/MM HH:MM` strings and has no
   minute arithmetic.
2. **8-hour window**. 480 minutes total: `windowEnd - windowStart` is always
   8h, and the window crosses midnight when the anchor hour makes it (e.g.
   `21:00 → 05:00`).
3. **Grid cells are 30 minutes wide** — 16 cells across the window. Each cell is
   **96 px** (`--timeline-grid-30min` in `web/theme.css`, mirrored by
   `CELL_PX = 96` in `timeline.js`). Positioning is
   `left = start * 96 / 30`, `width = duration * 96 / 30`.
4. **Gap between bars is 2 px** (`--timeline-gap` in `web/theme.css`, read by
   `timeline.js` via `getComputedStyle`). Overlapping bars are stacked into
   lanes by interval partitioning; the row height grows with the max lane depth.
5. **Conflicts — `implementacion` vs `implementacion` only**, in two places:
   * **Timeline markers** (`timeline.js::_renderConflicts`): evaluated per
     `(pool, responsable)` row group, i.e. two `implementacion` bars that belong
     to the **same pool family** *and* the **same assigned person**
     (`RECURSO ASIGNADO`) and whose intervals overlap. `derivado` bars never
     conflict.
   * **Diagnostic report** (`rules.py::_detect_conflicts`, reported as
     `kpiScope.conflictsDetected`): evaluated per `responsable` across the whole
     in-scope set, `implementacion` only, terminal rows excluded (ADR-006).
6. **No midnight-crossing arithmetic on the frontend**. Python resolves every
   time into minutes from the window start before the data leaves the engine.
   The frontend only multiplies minutes by a constant.

---

## Data flow

```
workspace/input/ControlPases.xlsx
  ↓  python/excel_reader.py       (pandas; column mapping; pool-scope filter)
  ↓  python/rules.py              (late start, ratification, conflicts)
  ↓  python/kpi.py                (KPI counters from rule flags)
  ↓  python/adapter.py            (Data Contract v1 + meta.poolOrder + meta.visibilityGroups)
  ↓  python/renderer.py           (inline CSS/JS + embedded JSON)
workspace/output/dashboard_data.json · dashboard.html · diagnostic_report.json
  ↓
web/dashboard.js  +  web/components/timeline/timeline.js
```

The HTML is self-contained: all CSS and JS are inlined and the contract is
embedded as `window.MockOperations.data`. `window.ChangeOpsActions` (ADR-008) is
embedded alongside it as a **separate, non-contract** informational payload; it
must not be read as part of Data Contract v1.

---

## Pool scope (ADR-009) — how `pool` is decided

The four `pool` names, the eight in-scope `RECURSO` values and the display order
all derive from **one ordered table** in `python/column_map.py`
(`_POOL_FAMILY_RESOURCES`).

* **Inclusion is exact on a normalized value, never a substring.**
  `normalize_recurso()` upper-cases and removes **all whitespace** (and nothing
  else — hyphens survive), then the value is looked up in `IN_SCOPE_POOL_KEYS`.
  No `in` test is ever used. The hazard is specific: `AUTOMATIZADO` (248 rows)
  and `AUTOMATIZADO ITSM` (167 rows) differ by exactly one token, so if
  `AUTOMATIZADO` were ever brought into scope, a substring matcher would pull in
  all 415 rows instead of 248. Both are out of scope today and both must stay
  out; exact matching is what guarantees that. See ADR-009.
* Whitespace-only normalization is required by the real data:
  `POOL S&F-DERIVADO` has no space before the hyphen, while
  `Pool AgileOps ORO - Derivado` has several. Both must resolve to the same key.
* `get_pool_name()` resolves exact keys first. Only if that fails does it fall
  back to **ordered** family tokens (`YAPE`, `S&F`, `AGILEOPSORO`,
  `AGILEOPSPROD`) so a new spelling variant of an in-scope pool resolves to its
  family instead of leaking a raw value. `AGILEOPSORO` / `AGILEOPSPROD` are
  strictly longer than `AGILEOPS`, so family resolution never collapses onto
  `AGILEOPS` alone and can never steal one family from another.
* `get_pool_name("")` returns the literal `"Unknown"`. In the timeline a bar
  without a pool is grouped under `Unknown` (token `unknown`) rather than being
  forced into a real pool — but with the current whitelist this cannot happen,
  because `""` / `None` / `"nan"` all fail inclusion.

---

## Verified run

Last real pipeline run, from the repository, on `workspace/input/ControlPases.xlsx`
(sheet `Hoja1`, **1432 data rows x 34 columns**; `RECURSO` at column index 25,
`ESTADO ACTUAL` at index 33):

| Fact | Value |
|------|-------|
| Rows read | 1432 |
| Rows in scope | 571 (861 ignored) |
| `meta.poolOrder` | `["Yape","S&F","AgileOps ORO","AgileOps Prod"]` |
| Window | `21:00 → 05:00` (480 min) |
| Timeline groups / bars | 4 groups — Yape 2, S&F 18, AgileOps ORO 9, AgileOps Prod 53 (82 bars) |
| Table rows | 175 |
| KPIs | `lateStarts` 3, `ratificationsSoon` 0, `ratificationsExpired` 24, `reversions` 0 |
| Visibility groups | 3 — `yape` (default), `sf`, `agileops`; see the per-group table below |
| Out-of-scope values present | none — `INFRAESTRUCTURA` and `AUTOMATIZADO` never appear |

The 571 in-scope rows are exactly the sum of the per-value `RECURSO` counts:

| `RECURSO` | Rows | Family |
|-----------|------|--------|
| `POOL - YAPE` | 8 | `Yape` |
| `POOL - YAPE-DERIVADO` | 0 | `Yape` |
| `Pool S&F` | 59 | `S&F` |
| `POOL S&F-DERIVADO` | 47 | `S&F` |
| `Pool AgileOps ORO` | 32 | `AgileOps ORO` |
| `Pool AgileOps ORO - Derivado` | 39 | `AgileOps ORO` |
| `Pool AgileOps Prod` | 231 | `AgileOps Prod` |
| `Pool AgileOps Prod - Derivado` | 155 | `AgileOps Prod` |
| **Total** | **571** | |

`POOL - YAPE-DERIVADO` is in the whitelist because the family definition
requires it, but this workbook snapshot contains **zero** rows with that value.

### Per visibility group (ADR-011)

Measured from the same run, by rendering the generated `dashboard.html` once per
group:

| `id` | Timeline families | Table rows | `tickets.passesInWindow` | `kpis.lateStarts` | `ratificationsSoon` | `ratificationsExpired` |
|------|-------------------|-----------|---------------------------|----------------------|---------------------|--------------------------|
| `yape` | Yape | 4 | 2 | 0 | 0 | 1 |
| `sf` | S&F | 28 | 24 | 0 | 0 | 4 |
| `agileops` | AgileOps ORO, AgileOps Prod | 143 | 70 | 3 | 0 | 19 |
| **union** | all 4 | **175** | **96** | **3** | **0** | **24** |

The union row is the invariant: every in-scope record belongs to exactly one
group, so the three views together reconstruct the unfiltered dashboard — 81
distinct timeline tickets and 165 distinct table tickets, equal to the
unfiltered contract. The table row count (175) exceeds the distinct ticket
count (165) because a ticket can carry more than one assigned resource.

---

## Changes

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-09-10 | Initial contract with ADR-004 (minutes) |
| v1.2 | 2026-10-05 | **Pool visibility groups** (ADR-011). `meta.visibilityGroups[]` added, each entry carrying `kpis` and `tickets` (ticket-ID sets per action scope) so the web layer can scope the timeline, table, KPI cards and action drawers without hardcoding anything. `meta.kpis` and `window.ChangeOpsActions` stay global. Presentation filter only — all groups remain embedded in the same file. |
| v1.1 | 2026-10-05 | **AgileOps Prod scope.** `pool` enum replaced with the four AgileOps Prod families; `meta.poolOrder` added (ADR-009); cell width corrected from 80 px to the real 96 px; `type` axis separated from pool identity; conflict rule restated precisely. |