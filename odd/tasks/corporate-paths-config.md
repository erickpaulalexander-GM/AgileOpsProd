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
- `tests/test_stale_flight.py`
- `tests/test_source_stamp.py`
- `tests/test_actions.py`
- `tests/test_visibility_groups.py`
- `tests/test_pool_scope.py`
- `tests/test_timeline_grouping.py`
- `web/components/timeline/*`
- `tests/test_source_stamp.py`
- `tests/test_stale_flight.py`
- `tests/test_window_overlap.py`
- `tests/test_shifts.py`
- `tests/test_early_start.py`
- `README.md`
- `docs/*`
- `odd/tasks/corporate-paths-config.md`

## Tasks
- [x] T1 — Loader + config.yaml + dep + tests (route: inline; trigger evidence: <3 archivos no triviales en este slice, batches acotados; delegación intentada y caída)
- [x] T2 — Wire pipeline a config (main/renderer/excel_reader: input resolve, sheet, output_dir, timezone wall-clock, env en diagnóstico; compat intacta) (route: inline)
- [x] T3 — Ejecutor raíz `run.py` + docs Scheduler + verificación total (route: inline)
- [x] T4 — `run.py` auto-bootstrap al venv (route: inline; un archivo mecánico)
- [x] T5 — KPI pases en vuelo (route: inline; test-first RED→GREEN)
- [x] T6 — Indicador pases colgados (route: inline; test-first RED→GREEN)
- [x] T7 — Lenguaje banco: orden + renombres de tarjetas (route: inline)
- [x] T8 — Sello de fuente en el header (route: inline; test-first RED→GREEN)
- [x] T9 — Alerta fuente >30min + formato legible (route: inline; JS solo-front)
- [x] T9b — Header todo relativo (`hace N min`, fecha exacta en tooltip)
- [x] T10 — Split ORO / ORO-Derivado en pools separados (route: inline; test-first RED→GREEN)
- [x] T11 — Cuarto filtro: grupo ORO propio + Prod aparte (route: inline; test-first RED→GREEN)
- [x] T12 — Revert split: derivado a tipo de barra, filtro ORO queda (route: inline; test-first RED→GREEN)
- [x] T14 — Timeline dibuja solape recortado (route: inline; test-first RED→GREEN)
- [x] T15 — Drawer con fechas reales, no geometría (route: inline; test-first RED→GREEN)
- [x] T16 — Badge en-curso de tabla en verde claro (route: inline; 1 regla CSS)
- [x] T17 — Turnos en Timeline: explorar JSON + identidad de recurso
- [x] T18 — Turnos backend: loader+matcher+payload (route: inline; test-first RED→GREEN)
- [x] T19 — Turnos frontend: sombreado fuera de turno + leyenda (route: inline; JS verificado por sintaxis+integración)
- [x] T19b — Subir presencia del sombreado en modo claro (route: inline; 2 reglas CSS)
- [x] T20 — Adelantados: en curso con inicio futuro (route: inline; test-first RED→GREEN)
- [x] T13 — Paleta en-curso del Timeline, solo visual (route: inline; 1 archivo)

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
- 2026-10-07 T6 done: `staleInFlight` (en curso con FIN pasado) con tarjeta `Pases colgados` + drawer + scopes por grupo + diagnóstico + reporte. RED `ImportError` → GREEN `pytest 162 passed` + `ruff` + `node --check`. Smoke en vivo 17:46: 21 colgados (todos agileops), 0 en vuelo. Docs: DATA_CONTRACT v1.5 + ADR-008. Commit `50892a6`.
- 2026-10-07 T7 done: orden En curso → Atrasados → Fuera de ventana → Ratis; renombres `Pases en vuelo`→`Pases en curso`, `Pases colgados`→`Pases fuera de ventana` (JS+template+reporte+docs; keys del contrato intactas). `pytest 162 passed` + `ruff` + `node --check`. Regen en vivo 17:51 ok. Commit `6cdda4f`.
- 2026-10-07 T8 done: header evidencia `Fuente: <archivo> · <mtime>` junto a Actualización vía `window.AgileOpsSource` (payload separado, contrato intacto). RED 2 fail → GREEN `pytest 165 passed` + `ruff` + `node --check`. Regen en vivo 17:57 con sello real 17:11:24. Docs: DATA_CONTRACT v1.6 + README. Commit `a842750`.
- 2026-10-07 T9 done: `Fuente: <arch> · DD/MM/YYYY HH:MM` + icono rojo y `hace N min` si supera 30 min (`SOURCE_STALE_MIN`, tooltip). Sin tests python (lógica solo-front); `node --check` ok + regen en vivo. Commit `f4bd8a1`.
- 2026-10-07 T10 done: `AgileOps ORO Derivado` familia propia (excepción parcial ADR-009 → ADR-013, solo ORO). Tabla + token largo-antes + grupo agileops + set CSS completo + docs (README, DATA_CONTRACT v1.7, ADR-013, timeline.md). RED 9 fail → GREEN `pytest 165 passed` + `ruff` + `node --check` x2. Smoke vivo 19:32: 5 filas, poolOrder 5, grupo agileops 3 familias. Commit `16f5172`.
- 2026-10-07 T11 done: grupos 3→4 (`oro` ORO+Derivado, `prod` Prod; `agileops` muere, localStorage viejo cae a `yape`). Badge CSS por id + docs (README, DATA_CONTRACT v1.8, ADR-011/013). RED 11 fail (motor viejo) → GREEN `pytest 165 passed` + `ruff` + `node --check`. Smoke vivo 19:41: 4 grupos con conteos propios. Commit `f25b920`.
- 2026-10-07 T12 done: revert T10 (derivado = tipo de barra en ORO, como los demás; tokens CSS muertos eliminados). Filtros intactos: `oro` owns ORO, `prod` owns Prod. RED 6 fail (motor spliteado) → GREEN `pytest 165 passed` + `ruff` + `node --check` x2. Smoke vivo 19:49: 4 filas, ORO 4 barras, grupos oro/prod con conteos. Docs: README, DATA_CONTRACT v1.9, ADR-013 marcado REVERTED. Commit `ea99216`.
- 2026-10-07 T14 done: timeline dibuja solape (inicio adentro o previo con FIN válido pasado el borde), recorte a grilla en backend, frontend intacto. RED 2 fail → GREEN `pytest 171 passed` + `ruff` + `node --check` x2, sin roturas. Smoke vivo 20:24: OCD-230862 recortado (0+120) + 3 más. Docs: DATA_CONTRACT v1.10 + README + ADR-014. Commit `42df08c`.
- 2026-10-07 T15 done: la barra lleva `iniPlan`/`finPlan` reales (mismo formato que la tabla); el drawer los prefiere con fallback calculado para HTML viejos; `timeline.js` los propaga en el aplanado. RED KeyError → GREEN `pytest 173 passed` + `ruff` + `node --check` x2. Smoke vivo 20:33: OCD-230862 (0+120, 07/10 19:00→22:00). Docs: DATA_CONTRACT v1.11. Commit `aa835aa`.
- 2026-10-07 T16 done: `.badge--pase-en-curso` a fondo #DCFCE7 + texto #15803D + borde #86EFAC (tamaño/padding/radius intactos; celdas con slack de 8px). Timeline T13 ya tenía la paleta pedida — verificado en el HTML. `pytest 173 passed` + paleta TIMELINE+BADGE en el HTML generado.
- 2026-10-07 T16 done: `.badge--pase-en-curso` a fondo #DCFCE7 + texto #15803D + borde #86EFAC (tamaño/padding/radius intactos; celdas con slack). Timeline T13 ya tenía la paleta pedida — verificado. `pytest 173 passed` + paleta en HTML. Timeline: barras ligeras; tabla: badge compacto.
- 2026-10-07 T17 done: explorado `horarios_importados_2026_10.json` (calendario mensual, datetimes absolutas, midnight gratis; matching 21/1:1/0 ambiguos + 2 carriles sin persona).
- 2026-10-07 T18 done: `python/shifts.py` (loader por patrón + match por tokens acotado por familia + segmentos recortados + fuera-de-turno) cableado en `main.py` (lanes por carril + `shiftScope` en diagnóstico) y `window.ResourceShifts` embebido. Pases fuera de turno: solo diagnóstico (anti-basura-visual). RED ImportError → GREEN `pytest 185 passed` + `ruff`. Smoke vivo 23:04: 14/14 carriles, 20 fuera de turno. Commit `8beaf36`.
- 2026-10-07 T19 done: fondo de carril fuera-de-turno detrás de barras + leyenda de 2 conceptos + tooltips/etiquetas por segmento; paleta exacta pedida + variante dark; carriles sin match sin pintar. `node --check` x2 + `pytest 185 passed` + leyenda/payload incrustados en HTML. Docs: DATA_CONTRACT v1.12 + timeline.md. Commit `b600195`.
- 2026-10-07 T19b done: sombreado a #F1F5F9 + trama 0.06 en claro (el slate-50 se perdía).
- 2026-10-08 T20 done: `earlyStart` (en curso con INI futuro) con tarjeta `Pases adelantados` + drawer + scopes por grupo + diagnóstico + reporte. RED ImportError → GREEN `pytest 195 passed` + `ruff` + `node --check`. Smoke vivo 00:00: OCD-231277 pescado. Docs: DATA_CONTRACT v1.13 + README 6 cards/drawers.
- 2026-10-07 T13 done: `.timeline__bar--pase-en-curso` con paleta exacta del diseño (fondo #ECFDF3 + diagonal 0.035 + outline #86D7A3 + acento izq 4px #16A34A vía background + texto #166534). Todo hacia adentro: dimensiones mapeadas intactas. Badge `.badge--pase-en-curso` y demás estados sin tocar. `pytest 165 passed` + `node --check` x2 + paleta verificada en el HTML generado.
- Verificación hasta acá: `git status` limpio; `git branch` main → nueva rama ok.

## Next step
Hecho: las 3 tareas están en verde. Falta la decisión de entrega (la rama acumula ~490 líneas: con `ask-on-risk` el usuario elige slice/PR) y el push/PR, que son decisión tuya.
