# Feature: corporate-paths-config

## Objective
Hacer input/output configurables vía `config.yaml` en raíz y exponer un ejecutor `run.py` en raíz para Task Scheduler en la PC corporativa.

## Problem
Los paths están hardcodeados: `python/main.py:44` (`workspace/input/ControlPases.xlsx`) y `python/renderer.py:28` (`workspace/output`). En la PC corporativa input/output van a vivir en otro lado y hoy hay que editar código para moverlos.

## Why
El usuario lo pidió explícito: un archivo de config para cambiar paths rápido + un script en raíz al que apuntar la tarea programada. El ejemplo que le pasaron era de otro proyecto (traía `data_file`, `bundle_dir`, `logs_dir`, `cache_dir`, `app: Change Triage` que acá no existen); el usuario autorizó adaptarlo al caso real.

## Scope
In:
- `config.yaml` en raíz (adaptado, no copia literal del ejemplo).
- Loader `python/config.py` con defaults + fallback si falta el archivo.
- Resolución de input por `input_dir` + `excel.pattern` (novedad más nueva) con override CLI intacto.
- Soporte `excel.sheet` (nombre o índice, default primera hoja).
- `output_dir` configurable en renderer.
- `app.name` / `app.timezone` (`America/Lima`) como wall-clock + `environment` solo como etiqueta en diagnóstico/logs.
- `run.py` en raíz como ejecutor para Scheduler.
- Tests + README/docs junto al cambio.
Out:
- Sin `.bat` (bloqueados en la corporativa, README lo prohíbe).
- Sin control de acceso por environment; `environment` no cambia comportamiento.
- Sin dirs `logs/`/`cache/`/`bundle/` (no los usa el pipeline).

## Constraints
- Backward compatible: sin `config.yaml` el pipeline corre con los defaults actuales.
- Precedencia: CLI `excel_path` > config > defaults. CLI `--now` > reloj.
- Timezone sin romper matemática: wall-time Lima naive para window/rules; tz queda registrada en diagnóstico.
- `pyyaml` nuevo: agregarlo a `requirements.txt` (runtime lo necesita).
- Delegación no disponible en este runtime (Task `gentle-ai-explore` falló con error de tier); se trabaja inline acotado con disclosure explícito, no silencioso.

## Authorized scope (allowed edit surfaces)
- `config.yaml`
- `python/config.py`
- `python/main.py`
- `python/kpi.py`
- `python/renderer.py`
- `python/excel_reader.py`
- `run.py`
- `web/dashboard.js`
- `requirements.txt`
- `tests/test_config*.py`
- `tests/test_in_flight.py`
- `tests/test_actions.py`
- `tests/test_visibility_groups.py`
- `README.md`
- `docs/*`
- `odd/tasks/corporate-paths-config.md`

## Tasks
- [x] T1 — Loader + config.yaml + dep + tests (route: inline; trigger evidence: <3 archivos no triviales en este slice, batches acotados; delegación intentada y caída)
- [x] T2 — Wire pipeline a config (main/renderer/excel_reader: input resolve, sheet, output_dir, timezone wall-clock, env en diagnóstico; compat intacta) (route: inline)
- [x] T3 — Ejecutor raíz `run.py` + docs Scheduler + verificación total (route: inline)
- [x] T4 — `run.py` auto-bootstrap al venv (route: inline; un archivo mecánico)
- [x] T5 — KPI pases en vuelo (route: inline; test-first RED→GREEN)

## Acceptance criteria
- Con `config.yaml` por defecto, `run.py` y `python/main.py` generan los mismos 3 outputs que hoy en `workspace/output/`.
- Cambiando `input_dir`/`output_dir` en el yaml, el pipeline escribe donde dice el yaml sin editar código.
- `excel.pattern: "ControlPases*.xlsx"` resuelve el match más nuevo dentro de `input_dir`.
- `excel.sheet` acepta nombre o índice; default primera hoja.
- Sin `config.yaml`, el pipeline funciona con defaults (warning, no crash).
- `pytest -q` 137+ nuevos tests en verde; `ruff check .` limpio.
- Scheduler puede apuntar a `run.py` (ejemplo documentado, sin `.bat`).

## Applicable checks
- `.\.venv-win\Scripts\python.exe -m pytest -q`
- `.\.venv-win\Scripts\python.exe -m ruff check .`
- `node --check web\dashboard.js` + `node --check web\components\timeline\timeline.js`
- Smoke: `run.py` y `python\main.py --now "2026-10-06 09:55"` → 3 archivos frescos + `meta.poolOrder` 4 familias.

## Test-first policy
Runner: `pytest -q` (conftest pone `python/` en sys.path). Donde haya test determinístico con outcome claro (T1 loader, T2 resolve/pattern/sheet): observar RED antes de implementar, luego GREEN, luego refactor en verde. Donde no aplique (docs, smoke Scheduler): verificación estructural/funcional proporcional explícita.

## Delivery strategy
- Forecast: ~300 líneas autoradas (loader ~80 + yaml ~20 + run.py ~40 + wiring ~60 + tests ~80 + docs ~30). Bajo el heurístico de 400/tarea y el budget de entrega de 400.
- Estrategia: `ask-on-risk` (default). Sin slicing previsto; si el conteo corriendo supera 400, se aplica la estrategia antes del próximo commit y se registran boundaries.
- Cada tarea cierra con ≥1 work-unit commit en `feature/corporate-paths-config` (Conventional Commits, tests+docs junto al comportamiento); se registra la identidad del commit como evidencia. Push/PR los decide el usuario.

## Progress
- 2026-10-07: rama `feature/corporate-paths-config` creada desde `main`. Doc creado, 3 tareas. Sin writes de fuente aún.
- 2026-10-07 T1 done: RED `ModuleNotFoundError: No module named 'config'` → GREEN `tests/test_config.py 4 passed` + `ruff check` limpio. Commit `586e234`.
- 2026-10-07 T2 done: wiring con compat (renderer.OUTPUT_DIR parcheable, seam _now honrado). `pytest 141 passed` + `ruff` limpio. Commit `85c4461`.
- 2026-10-07 T3 done: `run.py` raíz + README (config + Scheduler a run.py) + fix output custom por cfg. Static: ruff ok, `pytest 141 passed`, `node --check` x2 ok. Smoke `run.py --now "2026-10-06 09:55"`: exit 0, 1432 leídas/571 en scope, 3 archivos frescos, poolOrder 4 + 3 groups, diag env=DEV cfg=file tz=America/Lima. Custom output_dir a tmp: 3 archivos EXISTS True. Commit `fa855f8`.
- 2026-10-07 T4 done: `run.py` re-ejecuta con `.venv-win` si al intérprete le falta pandas (`py run.py` directo). Detalle: `os.execv` en Windows parte args con espacios (reproducido aislado) → se usa `subprocess.call` con exit code propagado. `ruff` limpio + `py run.py --now '2026-10-06 09:55'` end-to-end ok. Commit `147b8dc`.
- 2026-10-07 T5 done: definición del cliente = estado `Pase en curso` (sale de la tabla) con `INI<=ahora<=FIN`, sobre el universo operativo (no solo la ventana). Campo aditivo `inFlightNow` (payload global + tickets por grupo + diagnóstico); tarjeta titular + drawer + reporte muestran eso como `Pases en vuelo`; `passesInWindow` intacto para el Timeline. RED `ImportError filter_in_flight` → GREEN `pytest 152 passed` + `ruff` + `node --check` x2. Tests que pineaban 4 scopes actualizados a 5 (cambio deliberado). Smoke pineado 09:55: 45 en ventana vs 2 en vuelo. Docs: DATA_CONTRACT v1.4 + ADR-008. Commit `460b018`.
- Verificación hasta acá: `git status` limpio; `git branch` main → nueva rama ok.

## Next step
Hecho: las 3 tareas están en verde. Falta la decisión de entrega (la rama acumula ~490 líneas: con `ask-on-risk` el usuario elige slice/PR) y el push/PR, que son decisión tuya.
