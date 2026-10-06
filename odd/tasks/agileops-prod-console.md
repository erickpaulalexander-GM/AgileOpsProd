# Feature: AgileOps Prod Console

## Objective

Create a dashboard console at `D:\IA_DEV\AgileOpsProd` that mirrors the architecture and
behavior of `D:\IA_DEV\ChangeOpsConsole`, but scopes the operational universe to the
AgileOps Prod pool families instead of Legacy/Yape.

## Problem

`ChangeOpsConsole` hardcodes its pool scope in three independent places (Python filter,
Python operational whitelist, JavaScript render order). Its input lives in `data/` and its
output in `output/`. Reusing it for the AgileOps Prod pools requires either duplicating the
repo with every hardcoded value edited, or having one app parameterize the pool scope. The
user asked for a separate app whose input/output live under `workspace/`.

## Why

The AgileOps Prod, AgileOps ORO, S&F and Yape pools are a different operational universe with
different volume (the AgileOps workbook has 1433 data rows vs 1331 in ChangeOps). Mixing
them into the Legacy/Yape console would corrupt its KPIs and its timeline.

## Scope

### Verified input facts

`workspace/input/ControlPases.xlsx`, sheet `Hoja1`, **1432 data rows x 34 columns** (corrected
after verification — an earlier draft of this document said "1433 x 44"; the 1433 was
header-inclusive and the 44 column count was simply wrong). Same schema as the ChangeOps
workbook: `RECURSO` (index 25), `ESTADO ACTUAL` (index 33). 571 rows are in scope, 861 ignored.

Observed distinct `RECURSO` values in the requested scope:

| RECURSO value | rows |
| --- | --- |
| Pool AgileOps Prod | 231 |
| Pool AgileOps Prod - Derivado | 155 |
| Pool S&F | 59 |
| POOL S&F-DERIVADO | 47 |
| Pool AgileOps ORO - Derivado | 39 |
| Pool AgileOps ORO | 32 |
| POOL - YAPE | 8 |
| POOL - YAPE-DERIVADO | 0 |

Out-of-scope values that must stay excluded: `INFRAESTRUCTURA` (265), `AUTOMATIZADO` (248),
`AUTOMATIZADO ITSM` (167), `EXPRESS AUTOMATICO` (136), `DC_CONNECTIVITY(TELECOM)` (20),
`CyberSOC` (12), `EU_NETWORKING` (6), `OPERACIONES DATA` (5), `SelfServices APIG` (1),
`SelfServices AGIL` (1).

Note: `Pool S&F` is *excluded* by ChangeOpsConsole today (it does not match `LEGACY`/`YAPE`)
and is *included* here. That is an intended difference.

### Grouping decision (answered by user)

The 8 `RECURSO` values collapse into 4 families. The Timeline shows **4 pool rows**, and
`DERIVADO` remains the bar type, not the pool identity.

| Pool (timeline row) | Matching RECURSO values | Bar types |
| --- | --- | --- |
| Yape | `POOL - YAPE`, `POOL - YAPE-DERIVADO` | implementacion, derivado |
| S&F | `Pool S&F`, `POOL S&F-DERIVADO` | implementacion, derivado |
| AgileOps ORO | `Pool AgileOps ORO`, `Pool AgileOps ORO - Derivado` | implementacion, derivado |
| AgileOps Prod | `Pool AgileOps Prod`, `Pool AgileOps Prod - Derivado` | implementacion, derivado |

### Ported unchanged

Window/KPI/timeline math (`adapter.py` window logic, `hhmm_to_minutes`, lane packing),
`rules.py` business rules, `kpi.py`, `renderer.py` templating mechanism, web CSS layout and
theme, and the whole `excel_reader`/`column_map` date parsing.

### Constraints

- Input: `workspace/input/ControlPases.xlsx`. Output: `workspace/output/`.
- No `.bat` launchers (the corporate machine blocks them, per `workspace/input/dev-report.txt`).
- Pool matching must be whitespace-insensitive (`POOL S&F-DERIVADO` has no space before
  DERIVADO; `Pool AgileOps ORO - Derivado` has several) and must be an exact match on the
  normalized value. **Corrected premise:** this document originally justified exact matching
  by claiming a loose substring matcher would pull in `AUTOMATIZADO` / `AUTOMATIZADO ITSM`.
  That was measured and it is FALSE on this snapshot — a naive `AGILEOPS|YAPE|S&F` substring
  union returns exactly the correct 571 rows with zero collisions. The real justification for
  exact matching is that `AGILEOPS` alone matches 457 rows spanning 4 distinct values and
  cannot separate `AgileOps ORO` from `AgileOps Prod`; only the specific tokens do. Exact
  matching is kept because it is auditable against an explicit 8-value list.
- Single source of truth for the pool list. ChangeOpsConsole duplicates it in
  `column_map.py` and `timeline.js`, which is how a pool silently fails to render.
- `AGILEOPSORO` must be resolved before any looser `AGILEOPS` token, so family resolution is
  ordered and never relies on `AGILEOPS` alone.
- Artifacts in English (per the language domain contract).

## Tasks

### T1 — Scaffold repository and project config
- [ ] `git init`, `.gitignore` excluding `workspace/output/*` but keeping `.gitkeep`
- [ ] `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `conftest.py`
- [ ] Python env for verification (reuse/point at an interpreter with pandas + openpyxl + pytest)
- Route: inline (mechanical copy, already understood)

### T2 — Copy source tree and re-point paths
- [ ] Copy `python/`, `web/`, `docs/`, `tests/` from ChangeOpsConsole; drop `__pycache__`,
      `web/validate_phase*.py` (they grep for Legacy/Yape), `web/data/mock-operations.js`
      (dev fixture, data is embedded JSON), `output/`, `.venv*`
- [ ] `main.py` default input -> `workspace/input/ControlPases.xlsx`
- [ ] `renderer.py` output dir -> `workspace/output`, `<title>` -> AgileOps Prod
- [ ] `main.py` report strings: "Filas R1 (Legacy + Yape)" -> AgileOps scope
- [ ] Rename the venv-related and app-name references consistently
- Route: delegated writer

### T3 — Pool scope as one source of truth
- [ ] `column_map.py`: replace `R1_POOL_KEYWORDS` + `is_r1_pool` with an exact, normalized
      8-value resource whitelist and an ordered family resolver
- [ ] Rename `is_r1_pool` -> `is_in_scope_pool`; update `excel_reader.py` caller and docstrings
- [ ] `adapter.py` `OPERATIONAL_RESOURCES` -> the same 8 values, sourced from `column_map`
- [ ] Emit `meta.poolOrder` from Python so the web layer stops hardcoding the list
- Route: delegated writer

### T4 — Web layer: 4 pools instead of 2
- [ ] `timeline.js`: `poolOrder` from `meta.poolOrder`; bar default pool `Unknown`;
      accent color from a 4-entry palette keyed by pool, not a binary ternary
- [ ] `dashboard.js`: badge class `badge--<key>` instead of the Legacy/Yape ternary
- [ ] `timeline.css` / `theme.css`: pool accent + badge rules for the 4 pools
- Route: delegated writer

### T5 — Tests ported and green
- [ ] Port all 10 test modules with pool fixtures updated to the AgileOps values
- [ ] Add a test that pins the 8-value whitelist and rejects `AUTOMATIZADO`/`INFRAESTRUCTURA`
- [ ] Add a test that pins the 4-family resolution including `POOL S&F-DERIVADO` and
      `Pool AgileOps ORO - Derivado`
- [ ] Add a test that pins `meta.poolOrder`
- Route: delegated writer

### T6 — Docs and end-to-end run
- [ ] `docs/DATA_CONTRACT.md`: `pool` enum is the 4 families; document `meta.poolOrder`
- [ ] `docs/ARCHITECTURE_DECISIONS.md`: add ADR-009 (pool scope as data) and ADR-010
      (workspace paths)
- [ ] `README.md` with the no-`.bat` run instructions
- [ ] Run the pipeline end to end on the real workbook and verify the outputs
- Route: delegated writer

### T7 — Pool visibility selector (Yape / S&F / AgileOps)
- [ ] `column_map.py`: 3 visibility groups declared as pool families, partition-validated at import
- [ ] Per-group KPIs and ticket id sets emitted from Python
- [ ] Web selector in the topbar, filtered timeline + table + KPIs + drawer
- [ ] `localStorage` persistence with fallback, empty state, active-group indicator
- [ ] ADR-011 and the honest limitation recorded in UI, contract and README
- Route: delegated writer

## Authorized edit surfaces

- `D:\IA_DEV\AgileOpsProd\**` except `workspace/input/**` and `D:\IA_DEV\ChangeOpsConsole\**`

## Acceptance criteria

1. `python -m pytest` passes with zero failures. **MET** — 84 passed (ChangeOps baseline 57).
2. `ruff check .` is clean. **MET** — All checks passed.
3. Running the pipeline on `workspace/input/ControlPases.xlsx` writes
   `workspace/output/dashboard.html`, `dashboard_data.json` and `diagnostic_report.json`.
   **MET** — verified, including a run from `C:\Windows` with no arguments, exit code 0.
4. `dashboard_data.json` reports only the 4 AgileOps families and the 8-value scope;
   `INFRAESTRUCTURA` / `AUTOMATIZADO` never appear. **MET** — leak scan returns none.
5. The generated HTML renders 4 pool rows with no `undefined`/`Unknown` pool leakage when a
   pool has no bars in the window. **MET** — all 4 tokens rendered
   (`yape`, `sf`, `agileops-oro`, `agileops-prod`) in a `node:vm` harness executing the real
   `timeline.js` against the real `dashboard_data.json`.
6. No file in `D:\IA_DEV\ChangeOpsConsole` is modified. **MET** — verified by mtime and by
   `timeline.js:167` there still reading `['Legacy', 'Yape']`.

## Applicable checks

- `python -m pytest` (unit)
- `python -m ruff check .` (lint)
- End-to-end pipeline run against the real workbook, asserting the output files exist and the
  pool set is exactly the 4 families
- Test-first applies to T3, T4, T5: write the failing pool-scope test first, observe RED,
  implement, observe GREEN.

## Route declaration

| Task | Route | Trigger |
| --- | --- | --- |
| T1 | inline | mechanical copy, already understood, 0 research |
| T2 | delegated | 2+ non-trivial files |
| T3 | delegated | 2+ non-trivial files, cross-module contract |
| T4 | delegated | 2+ non-trivial files, CSS + JS |
| T5 | delegated | full suite, must run pytest |
| T6 | delegated | docs + full-suite run |

## Delivery strategy

`ask-on-risk`. Forecast is well over 400 authored changed lines because the whole app is new,
so this app ships as its own repository and its own history: the chain question does not
apply until a second pushable unit exists.

## Progress

- [x] T1 scaffold — committed in `170a276`
- [x] T2 copy + paths — committed in `170a276`
- [x] T3 pool scope single source of truth — committed in `170a276`
- [x] T5 tests ported + 17 new pool-scope tests — committed in `170a276`
- [x] T4 web layer renders 4 pools from data — committed in `874fc24`
- [x] T6 docs, contract, README

### Verification evidence

| Check | Result |
| --- | --- |
| `pytest -q` | 84 passed, 0 failed (11 modules) |
| `ruff check .` | All checks passed |
| `node --check timeline.js` / `dashboard.js` | exit 0 / exit 0 |
| Pipeline run, in-repo | exit 0, 3 artifacts written |
| Pipeline run from `C:\Windows`, no args | exit 0, same byte sizes — ADR-010 holds |
| `meta.poolOrder` readback | `["Yape","S&F","AgileOps ORO","AgileOps Prod"]` |
| Timeline groups | Yape 2, S&F 18, ORO 9, Prod 53 (82 bars) |
| Table rows | 175, pool set exactly the 4 families |
| Bar types | implementacion 50, derivado 32 |
| Leak scan | 0 hits for INFRAESTRUCTURA, AUTOMATIZADO, EXPRESS AUTOMATICO, Legacy, Unknown, undefined |
| Native review | not run — receipt-driven development is `off` (global) |

Authored changed lines across both work units: ~1200 (the whole app is new). This repository
is its own product, so the `ask-on-risk` chain question does not apply until a second pushable
unit exists.

### Inherited defects found, deliberately NOT fixed (out of scope)

1. **`python/table.py` and `python/timeline.py` are dead placeholders** — each is a single
   line `"""Pendiente implementar."""` and nothing imports them. Carried over verbatim from
   ChangeOpsConsole. Documented in the README as ignorable.
2. **Conflict-count divergence between the two layers.** `web/components/timeline/timeline.js`
   `_renderConflicts` scopes conflicts to a `(pool, responsable)` group, while
   `python/rules.py:183-200` groups by `responsable` only, with no pool condition. A person
   holding overlapping implementations across two pools is therefore counted by the
   diagnostic `conflictsDetected` but not drawn by the UI. Both read 0 on the current run, so
   it is unobservable today. This is pre-existing in ChangeOpsConsole, not candidate-caused.
3. **Inherited contract constants were wrong.** ChangeOpsConsole's `DATA_CONTRACT.md` claimed
   a 30-minute cell is 80px; the actual value is 96px (`theme.css:11`,
   `timeline.js:32`). Already false in the source repo. Corrected in our contract.