# AgileOps Prod Console

A self-contained operational dashboard for the **AgileOps Prod pool families**.
It reads one Excel control workbook and produces a single-file HTML dashboard
plus the machine-readable contract and a diagnostic report.

This repository is a **port of `D:\IA_DEV\ChangeOpsConsole`** — same pipeline
shape, same window/KPI/timeline math, same web components — rescoped from the
Legacy/Yape universe to the AgileOps Prod pools (Yape, S&F, AgileOps ORO,
AgileOps Prod). It is a **separate application with its own history**, not a
configuration of the original: mixing the two universes would corrupt both
dashboards' KPIs and timelines.

The ported pipeline logic is unchanged; the pool scope and the I/O layout are
the two things that differ, and both are deliberate (ADR-009, ADR-010).

---

## Requirements

- Python **3.12+** (`pyproject.toml` sets `requires-python = ">=3.12"`).
- `pandas` + `openpyxl` to read the workbook (`requirements.txt`).
- `pytest` + `ruff` to verify (`requirements-dev.txt`).
- Node.js — **only** for `node --check` syntax validation of the two JS files.
  The pipeline itself does not need Node.

---

## Setup

```powershell
# From the repository root
cd D:\IA_DEV\AgileOpsProd

python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install --upgrade pip
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` pulls in `requirements.txt`, so the single install above
covers runtime and tooling.

> `pyproject.toml` declares a `[dependency-groups]` entry, but **pip does not
> read dependency groups** — use `requirements-dev.txt`, not
> `pip install --group dev`.

If your machine has no Python on `PATH`, use the launcher:
`py -3.12 -m venv .venv-win`.

---

## Run

The workbook **must be placed at `workspace/input/ControlPases.xlsx`**. That is
the default input path and the layout the code expects.

```powershell
# Default input — no arguments needed (this is what Task Scheduler runs)
.\.venv-win\Scripts\python.exe python\main.py

# Explicit input path (output directory is always workspace/output)
.\.venv-win\Scripts\python.exe python\main.py "D:\somewhere\else\ControlPases.xlsx"

# Reproduce a run exactly by pinning the run clock (window -> 09:00 .. 17:00)
.\.venv-win\Scripts\python.exe python\main.py --now "2026-10-06 09:55"
```

Both default paths resolve from the **repository root**, not from the current
working directory, so the pipeline runs correctly from any directory — including
Task Scheduler on the client machine, where the "Start in" folder is not the
repo. This is ADR-010; how to prove it is in
[`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md).

On the corporate PC you don't edit code to move paths — you edit
`config.yaml` in the repo root (created for this feature):

```yaml
environment: DEV
paths:
  input_dir: workspace/input     # relative = repo root; absolute also works
  output_dir: workspace/output
excel:
  pattern: "ControlPases*.xlsx"  # newest match inside input_dir wins
  sheet: 0                       # name or index; 0 = first sheet
app:
  name: "AgileOps Prod Console"
  timezone: "America/Lima"        # wall-clock; --now still wins for replays
```

Precedence: CLI `excel_path` > config > built-in defaults. Missing
`config.yaml` warns and falls back to defaults, so old Scheduler tasks keep
working. Extra diagnostic keys (`environment`, `configSource`, `timezone`,
`excelSheet`, `excelPattern`) land in `diagnostic_report.json` only — the
Data Contract shape is untouched.

The root executor `run.py` is what Scheduler points at (thin wrapper over
`python/main.py`, same CLI: `[excel_path] [--now DATETIME] [--config PATH]`):

```powershell
.\.venv-win\Scripts\python.exe run.py
.\.venv-win\Scripts\python.exe run.py --now "2026-10-06 09:55"
.\.venv-win\Scripts\python.exe run.py --config "D:\corp\config.yaml"
```

### The timeline window is anchored to the run clock (ADR-012)

The 8-hour timeline window starts at the **floor of the clock when the pipeline
runs**, not at the Excel file's modification time:

| Run at | Window |
|--------|--------|
| `09:55` | `09:00 → 17:00` |
| `21:40` | `21:00 → 05:00` |

The Excel mtime is a **copy artifact** (when the file landed on the machine),
not when its data changed, so it is reported only in
`diagnostic_report.json` as `excelFileMtime` and never drives the window. See
ADR-012 in [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md)
(which supersedes ADR-005's anchor).

A clock-anchored run is not deterministic, so a run can be pinned with `--now`:

```powershell
# --now accepts "YYYY-MM-DD HH:MM", "YYYY-MM-DDTHH:MM", "DD/MM/YYYY HH:MM"
# or a bare "HH:MM" (today). An unparseable value fails loudly, never silently.
.\.venv-win\Scripts\python.exe python\main.py --now "2026-10-06 09:55"
```

`diagnostic_report.json::updatedAtSource` records `"run_clock"` for an organic
run and `"now_override"` when `--now` was supplied.

### Windows Task Scheduler

The pipeline is designed to be run by Task Scheduler on the client machine. It
resolves its own paths (ADR-010) and needs no `.bat` launcher (those are blocked
there). Create a daily task with `schtasks` from an elevated prompt — quote the
whole `/TR` value and use the venv's Python directly:

```cmd
schtasks /Create /TN "AgileOps Prod Console" /SC DAILY /ST 09:55 /TR "\"D:\IA_DEV\AgileOpsProd\.venv-win\Scripts\python.exe\" \"D:\IA_DEV\AgileOpsProd\run.py\""
```

- `/ST 09:55` is when the task runs; if it runs at 09:55, the window starts at
  `09:00`.
- The "Start in" directory does not matter — every path resolves from the
  repository root.
- To run it now without waiting for the schedule: `schtasks /Run /TN "AgileOps
  Prod Console"`.
- To inspect or remove it: `schtasks /Query /TN "AgileOps Prod Console" /V /FO
  LIST` and `schtasks /Delete /TN "AgileOps Prod Console" /F`.

Output lands in `D:\IA_DEV\AgileOpsProd\workspace\output\` (`dashboard.html`,
`dashboard_data.json`, `diagnostic_report.json`).

### No `.bat` launchers

**This repo ships no `.bat` files, by design.** They are blocked on the target
corporate machine — the last line of `workspace/input/dev-report.txt` reads
`NO usar .bat esta bloqueado en pc corporativa.` Use the PowerShell/cmd commands
above instead.

cmd.exe equivalents, if you prefer them:

```cmd
.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv-win\Scripts\python.exe python\main.py
.venv-win\Scripts\python.exe -m pytest -q
.venv-win\Scripts\python.exe -m ruff check .
```

To open the result:

```powershell
Start-Process .\workspace\output\dashboard.html
```

### Output

Three files, written to `workspace/output/`:

| File | Contents |
|------|----------|
| `dashboard.html` | The dashboard. Fully self-contained: all CSS and JS inlined, contract embedded. SharePoint-safe — no network, no `localStorage`. |
| `dashboard_data.json` | Data Contract v1 — the machine-readable contract. |
| `diagnostic_report.json` | Processing statistics: row counts, scopes, window, conflicts, terminal-state breakdown. |

`workspace/output/*` is git-ignored except `.gitkeep` — regenerate, don't commit.

---

## Verify

```powershell
cd D:\IA_DEV\AgileOpsProd

.\.venv-win\Scripts\python.exe -m pytest -q          # expect: 137 passed
.\.venv-win\Scripts\python.exe -m ruff check .       # expect: All checks passed!

node --check web\components\timeline\timeline.js    # expect: exit 0, no output
node --check web\dashboard.js                       # expect: exit 0, no output
```

`conftest.py` puts `python/` on `sys.path`, so tests import the pipeline modules
by their flat names (`import adapter`, `import column_map`). No packaging step
is needed. `ruff` config lives in `pyproject.toml` (`line-length = 100`,
`select = ["E4", "E7", "E9", "F"]`, `ignore = ["E501"]`).

> `python/table.py` and `python/timeline.py` are one-line placeholder stubs
> (`"""Pendiente implementar."""`) inherited from `ChangeOpsConsole`. Nothing
> imports them and nothing produces them — ignore them.

An end-to-end smoke check is the pipeline run above: exit code `0` plus three
fresh files in `workspace/output/`, with `meta.poolOrder` reporting exactly the
four pool families and `meta.visibilityGroups` reporting exactly the three
visibility groups.

---

## Layout

```
AgileOpsProd/
├── python/                     the pipeline engine (flat modules, no package)
│   ├── main.py                 entry point + CLI report
│   ├── excel_reader.py         pandas read, column mapping, pool-scope filter
│   ├── column_map.py           Excel→field map + THE pool family table (ADR-009)
│   │                           + the visibility group table (ADR-011)
│   ├── rules.py                late start, ratification, conflicts
│   ├── kpi.py                  KPI counters from rule flags + per-group KPIs (ADR-011)
│   ├── adapter.py              Data Contract v1, window math, meta.poolOrder,
│   │                           meta.visibilityGroups
│   └── renderer.py             writes dashboard.html / dashboard_data.json / diagnostic_report.json
├── web/                        the frontend, inlined verbatim into the HTML
│   ├── dashboard_template.html
│   ├── theme.css               design tokens, pool colours, badges
│   ├── dashboard.js            visibility selector + filter, KPIs, table, drawers
│   └── components/timeline/
│       ├── timeline.js         CSS-Grid timeline (ADR-002), reads meta.poolOrder
│       ├── timeline.css
│       └── timeline.md
├── tests/                      13 modules, 137 tests
├── docs/
│   ├── DATA_CONTRACT.md        the contract the engine and frontend share
│   └── ARCHITECTURE_DECISIONS.md  ADR-001 .. ADR-012
├── README.md                   this file
├── workspace/
│   ├── input/                  ControlPases.xlsx (supplied externally, not versioned)
│   │                           + dev-report.txt
│   └── output/                 generated artifacts (git-ignored)
├── conftest.py                 puts python/ on sys.path for pytest
├── pyproject.toml              deps, ruff config, pytest config
├── requirements.txt            pandas, openpyxl
└── requirements-dev.txt        + pytest, ruff
```

---

## Pool families

The timeline has **4 pool rows**. The `-DERIVADO` resource variants are the bar
**type**, never a separate pool.

| # | Pool (`pool` field) | CSS token | Matching `RECURSO` values | Rows in the current workbook |
|---|---------------------|-----------|---------------------------|------------------------------|
| 1 | `Yape` | `yape` | `POOL - YAPE`, `POOL - YAPE-DERIVADO` | 8 + 0 |
| 2 | `S&F` | `sf` | `Pool S&F`, `POOL S&F-DERIVADO` | 59 + 47 |
| 3 | `AgileOps ORO` | `agileops-oro` | `Pool AgileOps ORO`, `Pool AgileOps ORO - Derivado` | 32 + 39 |
| 4 | `AgileOps Prod` | `agileops-prod` | `Pool AgileOps Prod`, `Pool AgileOps Prod - Derivado` | 231 + 155 |
| | | | **Total in scope** | **571** |

Display order is fixed at `Yape → S&F → AgileOps ORO → AgileOps Prod`, published
by Python as `meta.poolOrder` and consumed by the web layer.

Of the 1432 data rows in the workbook, **571 are in scope and 861 are ignored**.
The excluded `RECURSO` values are `INFRAESTRUCTURA` (265), `AUTOMATIZADO` (248),
`AUTOMATIZADO ITSM` (167), `EXPRESS AUTOMATICO` (136),
`DC_CONNECTIVITY(TELECOM)` (20), `CyberSOC` (12), `EU_NETWORKING` (6),
`OPERACIONES DATA` (5), `SelfServices APIG` (1), `SelfServices AGIL` (1).

Families roll up into the three visibility groups of the next section; the
mapping is declared over family names, so the two tables cannot drift apart.

Note that `AUTOMATIZADO` and `AUTOMATIZADO ITSM` differ by one token. Inclusion
is an **exact match on a whitespace/case-normalized value**, never a substring
match — see ADR-009 for why that is a correctness requirement and not a style
preference.

---

## Visibility groups (ADR-011)

The topbar has a **Visibilidad** selector that narrows the whole dashboard to
one of three **visibility groups**, so somebody working a single pool family does
not have to read the other families' passes.

> **This is a presentation filter, NOT access control.** Every group's data is
> embedded in the same generated `dashboard.html`, so anyone can read every group
> from the file or from devtools. The `localStorage` key is a convenience, not a
> guard. Real enforcement needs a per-group payload split or an authorising
> backend; neither exists here. Full statement in
> `docs/ARCHITECTURE_DECISIONS.md` (ADR-011).

| # | `id` | Label | Pool families | Default |
|---|------|-------|---------------|---------|
| 1 | `yape` | YAPE | `Yape` | **yes** |
| 2 | `sf` | S&F | `S&F` | no |
| 3 | `agileops` | AgileOps | `AgileOps ORO`, `AgileOps Prod` | no |

Switching a group re-renders **everything**: the timeline, the operational table,
the four KPI cards and the three action drawers. The active group and its record
count are shown next to the selector, scroll position and bar highlight reset,
and a group with no results gets an explicit empty state instead of a blank
screen.

The selection is remembered in `localStorage` under
`agileops-visibility-group`. A missing, empty, unknown or stale value falls back
to the **first** group — `yape` today.

The groups are declared as **pool families**, never as `RECURSO` values, in
`python/column_map.py::_VISIBILITY_GROUPS`, and their `resources` lists are
flattened from `_POOL_FAMILY_RESOURCES`. Python publishes the whole thing as
`meta.visibilityGroups`, each entry carrying its own `kpis` and per-scope ticket
ID sets, so **the web layer hardcodes no group and no pool**. The definitions must
partition the four families: an orphaned or duplicated family raises
`ValueError` at import rather than silently dropping a pool from every view.

Adding a pool family therefore touches the group table too — see the next
section.

---

## Adding a new pool family

One table is the only place to edit:

**`python/column_map.py::_POOL_FAMILY_RESOURCES`** — append a
`(display family, (RECURSO values...))` pair. Its **position is the display
order**, and everything else is derived from it: the inclusion whitelist, the
family index, `POOL_FAMILY_ORDER` and the `meta.poolOrder` the frontend reads.
Nothing in `python/` or `web/` needs a second edit.

Then, for the colours only, and for the visibility group that will own it:

2. `web/theme.css` — declare `--color-<token>` (bar fill / badge background) and
   `--pool-accent-<token>` for **both** the light and the dark theme block.
3. `web/components/timeline/timeline.css` — bind the token:
   `.timeline__pool-header--<token>` and `.timeline__bar--<token>`.
4. `web/theme.css` — add `.badge--<token>`.

The token itself is **computed**, not tabulated: `Timeline.poolKey()` slugifies
the family name, so `S&F → sf` and `AgileOps ORO → agileops-oro` without any
JavaScript edit. `dashboard.js` delegates to `window.Timeline.poolKey`, so the
badge class cannot drift from the bar token.

Finally, before the pipeline will even start:

5. `python/column_map.py::_VISIBILITY_GROUPS` — add the family to the group
   that should own it. This is **required**, not optional: the group table is
   validated as a partition at import, so a family in no group raises
   `ValueError`. That is deliberate — a family invisible in every view is a
   silent data loss, which is exactly the failure mode ADR-009 removed.
6. Add the family to the pinned assertions in `tests/test_pool_scope.py`,
   `tests/test_visibility_groups.py` and to the `pool` enum table in
   `docs/DATA_CONTRACT.md`.

---

## Reading the output

`dashboard_data.json` is the contract; `docs/DATA_CONTRACT.md` is its spec.
Entries in `diagnostic_report.json` are worth watching after any change:

- `timelineScope` — bars in / out of the dynamic 8-hour window (anchored to the
  run clock, ADR-012), and the per-pool split.
- `kpiScope` — how many in-scope rows were evaluated vs. how many were excluded
  as terminal, with a per-state breakdown, plus the conflict and late-start
  counts.
- `updatedAtSource` — `"run_clock"` or `"now_override"`, i.e. whether the run
  was organic or pinned with `--now`.
- `excelFileMtime` — the workbook's mtime, kept for diagnostics only; it never
  drives the window.

Both are scoped differently from each other on purpose: the **timeline** shows
the 8-hour slice, the **table** shows the live operational universe, and the
**KPIs** run over the in-scope set with terminal states excluded (ADR-006). A
number that looks inconsistent between the three is usually that difference, not
a bug.