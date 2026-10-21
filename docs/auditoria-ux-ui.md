# Auditoría UX/UI — AgileOps Prod Console

Auditoría de solo lectura. No se modificó código, CSS, HTML ni lógica de negocio.

## 1. Limitaciones de la auditoría (conservadas del informe original)

- **Contrastes estimados manualmente.** Los ratios se calcularon a mano sobre `#FFFFFF` (o el fondo indicado), no con una herramienta de medición. Son valores aproximados.
- **Responsive no validado visualmente.** El hallazgo A15 se basa en lectura de CSS, no en pruebas en pantalla.
- **Archivos no revisados:** `python/renderer.py`, `python/shifts.py`, `python/main.py`, `web/components/timeline/timeline.md` y los ADR de `docs/ARCHITECTURE_DECISIONS.md`.
- **Lectura parcial:** `docs/DATA_CONTRACT.md` solo hasta la línea 200 y `README.md` solo hasta la línea 80.
- **Archivos leídos:** `web/dashboard_template.html`, `web/theme.css`, `web/dashboard.js`, `web/components/timeline/timeline.js`, `web/components/timeline/timeline.css`, `python/rules.py`, `python/kpi.py`.
- **No se ejecutó la aplicación** ni se probó con lector de pantalla o teclado reales. Los hallazgos de accesibilidad se infieren del código.
- Tres estados calculados ("en vuelo", "colgado", "adelantado") se conocen solo por `DATA_CONTRACT.md:153-155`; su implementación no se leyó.

### Convenciones de este documento

- **Confirmado (código):** observado directamente en el código leído (existencia de atributos, reglas, selectores, tokens).
- **Estimado:** valores calculados a mano (contrastes) o inferencias sobre comportamiento no probado.
- **Impacto:** el informe original no tenía un campo "impacto" separado. Se resume a partir del problema descrito, sin añadir información nueva.
- **Riesgo de regresión:** el informe original no lo evaluó. Se marca "No evaluado en la auditoría original" y se detalla en el plan de implementación solo para los cambios que se vayan a ejecutar.

## 1b. Contexto de negocio (aportado por el usuario, posterior a la auditoría)

Esta información no surge del análisis de código; la indicó el usuario después de entregada la auditoría.

- El dashboard es para **pases a producción de un banco**.
- **Adelantar un pase es crítico.**
- Cada pase tiene su horario de implementación y de ratificación. **No se debe modificar ni alterar sin un conforme del gestor de cambios.**
- **"Ratificaciones vencidas" es crítico** (confirmado por el usuario).

### Restricciones derivadas para cualquier implementación

- El dashboard es de **solo lectura sobre horarios**. Ningún cambio debe permitir ni sugerir modificar la implementación o la ratificación de un pase. Por ejemplo, las mejoras de A6 (selección cruzada, KPI como filtro) solo pueden resaltar y filtrar; no debe haber edición ni arrastre de barras.
- Antes de implementar, hay que revisar que no exista ninguna ruta que escriba o modifique fechas u horas. Esa revisión **no se hizo** en la auditoría original.
- El mapa de severidad de A8 refleja este criterio (adelantados y vencidas son críticos).

## 2. Stack y arquitectura

- **Pipeline:** Python 3.12 (pandas + openpyxl) lee `ControlPases.xlsx` y genera un HTML de un solo archivo con datos incrustados. También genera `dashboard_data.json` y un diagnóstico.
- **Cliente:** JS vanilla (IIFE, ES5), sin framework ni bundler. Datos desde `window.MockOperations.data`, `window.ChangeOpsActions` y `window.ResourceShifts`.
- **Estilos:** CSS Grid, tokens en `:root`, temas `[data-theme=light|dark]` y componente Timeline en capas (`timeline.css`).
- **Reloj:** estático. `meta.updatedAt` es el reloj de la corrida (ADR-012). La ventana es de 8 h desde `floor_to_hour(updatedAt)`. No hay vista "en vivo".
- **Visibilidad:** 4 grupos de pool (Yape, S&F, ORO, Prod). Es un filtro de presentación, no control de acceso. Los datos de todos los grupos viajan en el mismo archivo.

### Ubicaciones clave

| Elemento | Ubicación |
|---|---|
| Topbar, selector de Pool, badge, contadores, sync, tema | `web/dashboard_template.html:16-36` |
| Tarjetas KPI (HTML) | `web/dashboard_template.html:39-64` |
| KPI: render, etiquetas y orden reales | `web/dashboard.js:386-428` |
| Leyenda del timeline | `web/dashboard_template.html:67-77`; CSS `web/theme.css:340-389` |
| Timeline: 5 capas | `web/dashboard_template.html:81-91` |
| Timeline: barras y filas | `web/components/timeline/timeline.js:207-319` |
| Timeline: conflictos | `web/components/timeline/timeline.js:431-470` |
| Timeline: turnos fuera de horario | `web/components/timeline/timeline.js:332-369` |
| Estado vacío del timeline | `web/dashboard_template.html:95-104`; `web/dashboard.js:945-968` |
| Tabla | `web/dashboard_template.html:108-113`; `web/dashboard.js:592-639` |
| Drawers (barra y acción) | `web/dashboard.js:491-540` y `:660-716`; `web/theme.css:534-623` |
| Selector de grupo | `web/dashboard.js:797-871` |
| Render único por grupo (`_applyGroup`) | `web/dashboard.js:893-938` |
| Tokens base | `web/theme.css:7-125` |
| Estilos de componentes | `web/theme.css:159-630` |
| Estilos del timeline | `web/components/timeline/timeline.css` |
| Estilos inyectados por JS | `web/dashboard.js:558-587` |
| Reglas de estado | `python/rules.py:27-28` (umbrales), `:89-122` (inicio atrasado), `:125-163` (ratificación), `:166-205` (conflicto) |
| KPIs por grupo | `python/kpi.py:34-65` y `:164-251` |

## 3. Cómo se calculan y presentan los estados

**Reglas de negocio (`rules.py`)**
- Inicio atrasado: estado "Coordinado" y reloj > inicio + 5 min (`rules.py:27,114`).
- Ratificación por vencer: faltan de 0 a 10 min para el **cierre** de la ratificación (FIN_RATI; enmienda 2026-10-21 — antes decía "inicio", anclado al inicio de la ventana).
- Ratificación vencida: reloj > `fin_rati` (`rules.py:159`).
- Conflicto: mismo responsable, ambas Implementación (no Derivado) y solape de intervalos (`rules.py:166-205`).
- Estados terminales (cerrado, terminado, rechazado, cancelado, anulado, registrado) quedan fuera de KPIs y conflictos (`rules.py:33-40`).
- "En vuelo", "colgado" y "adelantado": según `DATA_CONTRACT.md:153-155` (implementación no revisada).

**KPI (`dashboard.js:405-428`)**
- El JS sobrescribe las etiquetas del HTML y reordena las tarjetas: Pases en curso (neutral), Pases atrasados (rojo), Pases fuera de ventana (rojo), Pases adelantados (ámbar), Ratificaciones por vencer (verde), Ratificaciones vencidas (ámbar).
- Las etiquetas del HTML ("Coordinados", "En Curso", "Atrasados") no coinciden con las visibles. El color viene de clases estáticas del HTML.

**Barras del timeline**
- Fondo según pool (`timeline.css:324-338`). `pase-en-curso` (`:346-367`) e `inicio-atrasado` (`:369-373`) lo sobrescriben. Derivado: outline punteado (`:377`). Turnos fuera de horario: sombreado rayado (`:253-278`). Un estado desconocido conserva el color del pool.

**Tabla (`dashboard.js:621-624`)**
- Solo 3 estados tienen badge propio; el resto cae en `badge--neutral`. `badge--coordinado` usa `--color-yape` (`theme.css:513-516`), el mismo token que el pool Yape.

## 4. Relación Timeline ↔ Tabla ↔ KPI

- **Filtro compartido:** solo el grupo de pool. `_groupView()` filtra KPIs, timeline, tabla y acciones (`dashboard.js:326-381`). `_applyGroup` re-renderiza todo, cierra el drawer y reinicia el scroll. Es consistente.
- **Sin sincronía Timeline↔Tabla.** Las filas llevan `data-ticket` (`dashboard.js:625`) sin handlers de hover, clic ni selección. Las barras abren un drawer (`timeline.js:306-318`).
- **Código preparado y sin uso (en lo leído):** capa `timeline__selection` vacía (`template:91`); `.timeline__select-highlight` (`timeline.css:429`); `Timeline.filterByStatus` y `.timeline__bar--dimmed` (`timeline.js:475`, `timeline.css:383`) sin invocar desde los KPI; `.kpi-card--active` (`theme.css:626`) nunca aplicada; `_scrollAndHighlightTimeline` y el flash (`dashboard.js:471-486`) no se llaman desde los handlers de KPI.
- **Los KPI solo abren un drawer** con tarjetas; no resaltan nada en timeline ni tabla.
- **Anclaje del reloj:** el eje se ancla a `updatedAt` (`timeline.js:177-185`). No hay marcador de "ahora" (`timeline.css:19`: "Removed 'now' line (static snapshot)"); `--timeline-now-line` (`theme.css:80,112`) sigue declarado sin uso. El indicador de sincronía compara `updatedAt` con `Date.now()` del navegador, umbral 15 min (`dashboard.js:108-110`). El sello de fuente usa 30 min (`dashboard.js:95`).

## 5. Resumen de hallazgos

| ID | Área | Severidad | Esfuerzo | Verificación |
|---|---|---|---|---|
| A1 | Contraste | Alta | S | Código confirmado; ratios estimados |
| A2 | Contraste | Alta | S | Código confirmado; ratios estimados |
| A3 | Teclado/foco | Alta | S | Confirmado (código) |
| A4 | Accesibilidad/drawer | Alta | M | Confirmado (código); comportamiento no probado |
| A5 | Accesibilidad/timeline | Alta | M | Confirmado (código); efecto en lectores no probado |
| A6 | Interacción | Alta | M | Confirmado (código) |
| A7 | Reloj/Timeline | Media | M | Confirmado (código) |
| A8 | Semántica del color | Media | S | Confirmado (código) |
| A9 | Leyenda | Media | S | Confirmado (código) |
| A10 | Etiquetas/KPI | Media | S | Confirmado (código) |
| A11 | Tabla | Media | M | Confirmado en parte; sticky es inferencia |
| A12 | Errores | Media | S | Confirmado (código) |
| A13 | Barras | Media | M | Confirmado (código); táctil no probado |
| A14 | Conflicto | Media | M | Confirmado (código) |
| A15 | Responsive | Media | M | Inferido; no validado visualmente |
| A16 | Tema | Baja | S | Confirmado en parte; parpadeo es riesgo inferido |
| A17 | CSS/mantenimiento | Baja | S | Confirmado; contraste estimado |
| A18 | Estados vacíos | Baja | S | Confirmado; contraste estimado |
| A19 | Región viva | Baja | S | Confirmado (código) |

Esfuerzo: S = pequeño, M = medio (escala del informe original). Riesgo de regresión: **No evaluado en la auditoría original** en ningún hallazgo.

## 6. Hallazgos detallados

### A1 — Contraste de valores KPI y badges de estado
- **Severidad / esfuerzo:** Alta / S
- **Descripción:** Valores KPI en verde `#22C55E` (~2.3:1) y ámbar `#F59E0B` (~2.1:1) sobre blanco. El badge "Inicio atrasado" y la barra con texto blanco sobre ámbar (~2.1:1; la barra además a 9px). Incumple 3:1 para texto grande y 4.5:1 para el resto.
- **Evidencia:** `web/theme.css:41-42`, `:427-430`, `:527-531`. Barra: `timeline.css:369-373`.
- **Verificación:** código confirmado; ratios **estimados**.
- **Impacto:** legibilidad reducida de valores KPI y estados críticos.
- **Recomendación:** mantener los tonos para fondos y bordes; usar variantes más oscuras para texto (verde `#15803D`, ya usado en `theme.css:523`; ámbar `#B45309` o `#92400E`). Cambiar el texto del badge y de la barra "atrasado" a oscuro.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A2 — Contraste de `--text-muted`
- **Severidad / esfuerzo:** Alta / S
- **Descripción:** `--text-muted` `#94A3B8` sobre blanco (~2.6:1). En oscuro `#64748B` sobre `#1E293B` (~3:1). Lo usan contadores, estado vacío, conteos de pool y etiquetas de fuera de turno (10-11px).
- **Evidencia:** `theme.css:71,103`; usos en `theme.css:247,276,281`; `timeline.css:198,287`.
- **Verificación:** código confirmado; ratios **estimados**.
- **Impacto:** texto secundario difícil de leer en ambos temas.
- **Recomendación:** oscurecer el muted en claro (por ejemplo `#64748B`, ~4.8:1) y aclararlo en oscuro (por ejemplo `#94A3B8`). Cambio de token.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A3 — Foco de teclado ausente
- **Severidad / esfuerzo:** Alta / S
- **Descripción:** Barras y tarjetas KPI son `role=button tabindex=0`, pero solo el `<select>` tiene `:focus-visible`. Sin anillo de foco en barras, KPI, toggle de tema, cierre del drawer ni enlaces.
- **Evidencia:** `timeline.js:293`; `dashboard.js:437-438`; `theme.css:220-223`.
- **Verificación:** confirmado (código); no probado con teclado real.
- **Impacto:** navegación por teclado sin indicación de posición.
- **Recomendación:** regla global `:focus-visible` (outline 2px y offset) con token `--focus-ring`. Para barras, reutilizar el ring del hover (`timeline.css:317`).
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A4 — Drawer sin semántica de diálogo
- **Severidad / esfuerzo:** Alta / M
- **Descripción:** Alterna `aria-hidden` pero no tiene `role=dialog`, `aria-modal` ni `aria-labelledby`. El foco no entra al abrir, no hay trampa de foco ni retorno. Cerrado queda fuera de pantalla con `translateX`, pero sus enlaces siguen siendo enfocables (`aria-hidden=true` sobre elementos enfocables).
- **Evidencia:** `dashboard_template.html:119`; `dashboard.js:507,714`.
- **Verificación:** confirmado (código); no probado con lector de pantalla.
- **Impacto:** teclado y lectores de pantalla pierden contexto al abrir o cerrar el drawer.
- **Recomendación:** `role=dialog`, mover el foco al botón de cierre al abrir y devolverlo al disparador al cerrar. Añadir `inert` o `visibility:hidden` cuando está cerrado.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A5 — `role="img"` en el timeline
- **Severidad / esfuerzo:** Alta / M
- **Descripción:** `#timeline` tiene `role="img"`, lo que oculta las barras interactivas a los lectores de pantalla (hijos presentacionales). Contradice las barras con `role=button`. Las barras solo tienen `title`.
- **Evidencia:** `dashboard_template.html:81`; barras en `timeline.js:263-295`.
- **Verificación:** confirmado (código); efecto en lectores de pantalla **no probado**.
- **Impacto:** el timeline puede ser inaccesible para tecnologías de apoyo.
- **Recomendación:** quitar `role=img`; usar `role=region` con `aria-label` o una estructura de grid/lista. `aria-label` en cada barra con ticket, responsable, estado y horario.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A6 — Sin sincronía Timeline↔Tabla ni KPI→vista
- **Severidad / esfuerzo:** Alta / M
- **Descripción:** Las filas de la tabla no se pueden clicar ni resaltar. Los KPI no filtran ni resaltan, pese a que existen `dimmed`, `selection` y `kpi-card--active`.
- **Evidencia:** `dashboard.js:454-469`, `:625`; `timeline.js:475-484`; `dashboard_template.html:91`.
- **Verificación:** confirmado (código).
- **Impacto:** cruzar entre vistas es manual; el usuario no puede ubicar rápido en el timeline un pase de la tabla o de un KPI.
- **Recomendación:** (1) hover y selección cruzados barra↔fila reutilizando `data-ticket`; (2) KPI como filtro con `aria-pressed` y `kpi-card--active`, usando la capa y la clase existentes. El drawer queda como detalle.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A7 — Sin marcador de "ahora" y frescura inconsistente
- **Severidad / esfuerzo:** Media / M
- **Descripción:** No hay marcador de "ahora" aunque los KPI dependen del reloj de corrida. Dos umbrales de frescura (15 y 30 min) y dos relojes (corrida y navegador).
- **Evidencia:** `timeline.css:19`; `theme.css:80`; `dashboard.js:95,108-110`.
- **Verificación:** confirmado (código). La divergencia de relojes es una consecuencia descrita, no probada en ejecución.
- **Impacto:** si el HTML se abre horas después, los KPI cuentan "atrasados" a la hora de la corrida mientras el sync dice "hace N min" contra la hora actual.
- **Recomendación:** línea vertical estática en `updatedAt` (token `--timeline-now-line` ya existe) con etiqueta "Corrida HH:MM". Unificar el texto de frescura ("Datos de HH:MM (hace N min)") con un solo umbral documentado.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A8 — Semántica del color inconsistente
- **Severidad / esfuerzo:** Media / S
- **Descripción:** "Ratificaciones por vencer" en verde, "vencidas" en ámbar y "atrasados" en rojo. No queda claro si "adelantados" y "vencidas" deberían tener la misma severidad. `badge--coordinado` es amarillo y se confunde con el pool Yape.
- **Evidencia:** `dashboard_template.html:52,56,60`; `theme.css:513-516`.
- **Verificación:** confirmado (código). El criterio de severidad por KPI lo definió el usuario (ver sección 1b, "Contexto de negocio"); no proviene del código.
- **Impacto:** el color no comunica severidad de forma consistente y se confunde con la identidad de pool. Un pase adelantado es crítico, pero hoy "adelantados" y "vencidas" comparten ámbar.
- **Recomendación:** escala de severidad (neutral / atención / crítico) mapeada a los 6 KPI. Token propio para "Coordinado". Pool en borde o acento; estado en relleno.
  - **Mapa confirmado por el usuario:**

    | KPI | Severidad |
    |---|---|
    | Pases en curso | neutral |
    | Ratificaciones por vencer | atención |
    | Pases adelantados | crítico |
    | Pases atrasados | crítico |
    | Pases fuera de ventana | crítico |
    | Ratificaciones vencidas | crítico |

  - Los 6 niveles quedaron confirmados por el usuario, incluido "Ratificaciones por vencer" en atención.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A9 — Leyenda incompleta
- **Severidad / esfuerzo:** Media / S
- **Descripción:** La leyenda solo explica "fuera de turno" y "disponible". Faltan colores de pool, "Pase en curso", "Inicio atrasado", Derivado punteado y triángulo de conflicto. El swatch "fuera de turno" usa `#F1F5F9` fijo y queda claro en tema oscuro.
- **Evidencia:** `dashboard_template.html:67-77`; `theme.css:374-376`; referencia temática en `timeline.css:269-278`.
- **Verificación:** confirmado (código).
- **Impacto:** el usuario no puede decodificar los elementos del timeline sin ayuda.
- **Recomendación:** ampliar de forma compacta con 4 a 5 ítems; swatch dependiente del tema.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A10 — Etiquetas de KPI y umbrales poco claros
- **Severidad / esfuerzo:** Media / S
- **Descripción:** Las etiquetas visibles no coinciden con el estado en tabla ("Pases atrasados" vs "Inicio atrasado"). "Pases fuera de ventana" es ambiguo (en curso con fin ya vencido). Los umbrales de 5 y 10 min no se muestran.
- **Evidencia:** `dashboard.js:407-412`; `rules.py:27-28`.
- **Verificación:** confirmado (código).
- **Impacto:** interpretación ambigua de los indicadores.
- **Recomendación:** `title` o tooltip con definición y umbral por KPI. Si es posible, renombrar "fuera de ventana" con validación del equipo.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A11 — Tabla sin orden, búsqueda ni filtro
- **Severidad / esfuerzo:** Media / M
- **Descripción:** Sin orden, búsqueda ni filtro por estado. El `position:sticky` del `th` queda limitado por `overflow-x:auto` del contenedor, por lo que *probablemente* no es sticky respecto de la página. Sin `<caption>`, `scope` ni `aria-sort`. Sin indicador de alertas.
- **Evidencia:** `dashboard.js:592-639`; `theme.css:452-480`.
- **Verificación:** ausencia de funciones confirmada; el comportamiento del sticky es **inferencia**, no probada.
- **Impacto:** exploración lenta de la tabla con muchos pases.
- **Recomendación:** orden por columna con `aria-sort`, buscador por ticket o responsable, filtro por estado, `scope="col"` e icono de alerta.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A12 — Error de carga sin mensaje visible
- **Severidad / esfuerzo:** Media / S
- **Descripción:** Si el contrato es inválido o `DATA` es null, solo hay `console.error`. El usuario ve KPIs en "—" y un dashboard vacío.
- **Evidencia:** `dashboard.js:985-996`.
- **Verificación:** confirmado (código).
- **Impacto:** falla silenciosa; el usuario no distingue error de ausencia de datos.
- **Recomendación:** banner visible `role=alert` ("No se pudo cargar los datos. Verifica la corrida") con el primer error. Reutilizar el estilo neutro de `timeline-empty`.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A13 — Barras del timeline con texto pequeño
- **Severidad / esfuerzo:** Media / M
- **Descripción:** Fuente de 9px, solo ticket como texto. Un pase corto (15 min = 48px) queda truncado. Estado, responsable y duración dependen de `title`; no hay soporte táctil.
- **Evidencia:** `timeline.css:306`; `timeline.js:263-295`.
- **Verificación:** confirmado (código); comportamiento táctil **no probado**.
- **Impacto:** información crítica poco accesible en barras estrechas.
- **Recomendación:** subir a 10-11px, mantener ticket y mostrar solo icono de estado en barras estrechas. Detalle completo en el drawer y en un tooltip accesible.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A14 — Indicador de conflicto no accesible
- **Severidad / esfuerzo:** Media / M
- **Descripción:** Triángulo CSS de 16px con `::after '⚠'` posicionado a mano, solo `title`, `cursor:help`, sin foco ni texto alternativo. El conflicto no aparece en la tabla ni como KPI, aunque `rules.py:260` ya cuenta conflictos.
- **Evidencia:** `timeline.css:403-421`; `timeline.js:461-464`; `rules.py:260`.
- **Verificación:** confirmado (código).
- **Impacto:** los conflictos son poco visibles y no accesibles.
- **Recomendación:** elemento enfocable con `aria-label` ("Conflicto entre X e Y"). Considerar contador de conflictos junto a los KPI e icono en la fila de la tabla.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A15 — Responsive
- **Severidad / esfuerzo:** Media / M
- **Descripción:** Topbar de altura fija 52px con muchos elementos y un único breakpoint a 768px. En anchos intermedios hay *riesgo* de desborde. Timeline con columna sticky de 220px y 96px por 30 min: en móvil la gutter ocupa gran parte de la pantalla.
- **Evidencia:** `theme.css:159-169,636-654`; `timeline.css:31`.
- **Verificación:** **inferido de CSS; no validado visualmente.**
- **Impacto:** posible desborde y poco espacio útil en pantallas pequeñas (no confirmado).
- **Recomendación:** `flex-wrap` y altura mínima en el topbar. Reducir `--timeline-label-width` bajo 768px y añadir un breakpoint ~1100px. Verificar visualmente antes de actuar.
- **Riesgo de regresión:** No evaluado en la auditoría original.
- **Estado 2026-10-21 (auditoría responsive celular, verbatim del usuario: "audita el modo resposive
  para la visualización desde un celular" → "si dale"):**
  - **Implementado (H1/H2):** breakpoint `@media (max-width: 1100px)` que envuelve el topbar
    (`flex-wrap: wrap`, `height: auto`, `min-height: var(--header-height)`) y su meta; bajo 768px,
    `.pool-group__counts` con `min-width: 0` + `white-space: normal` y `.topbar-meta` con wrap —
    la fila meta (~590px de footprints fijos: counts 46ch + select 18ch + badge 17ch) ya no
    desborda el ancho de página en celulares. El topbar apilado fuerza `flex-wrap: nowrap`
    (wrap en column crearía columnas horizontales). Tests: `tests/test_responsive_mobile.py`
    (RED→GREEN), `pytest` 211 passed.
  - **Backlog pendiente (sin validar visualmente):** (M1) reducir `--timeline-label-width`
    (220px) bajo 768px — la gutter se lleva ~61% de una pantalla de 360px; (M2) tap targets
    ≥44px para `.tb-btn`/`.tf-reset`/chips en mobile (hoy ~20px de alto); (L1) drawer
    `width: 340px` fijo → `min(340px, 100vw - 16px)` en viewports de 320px; (L2) barras del
    timeline bajan a 9px en móvil (contra la recomendación A13 de mantener ≥10px); (L3) KPIs
    forzados a 2 columnas bajo 768px → a 320px cada card queda bajo su mínimo de 180px.

### A16 — Tema inicial y toggle
- **Severidad / esfuerzo:** Baja / S
- **Descripción:** El HTML parte en `data-theme="light"` y el JS puede cambiar a oscuro (por defecto en sandbox), con riesgo de parpadeo. El toggle es un emoji con `aria-label` fijo "Cambiar tema" y sin `aria-pressed`.
- **Evidencia:** `dashboard_template.html:2,34`; `dashboard.js:26-27,74`.
- **Verificación:** atributos confirmados; el **parpadeo es un riesgo inferido**, no observado.
- **Impacto:** posible destello de tema y toggle sin estado accesible.
- **Recomendación:** aplicar el tema en un script inline en `<head>`; `aria-pressed` o `aria-label` que refleje el estado.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A17 — Estilos dispersos y enlaces de bajo contraste
- **Severidad / esfuerzo:** Baja / S
- **Descripción:** Parte de los estilos de acciones y enlaces está inyectada por JS. Hay CSS sin uso. Los enlaces de ticket usan `--color-success` (verde) como color de enlace, con bajo contraste (~2.3:1, **estimado**) y connotación de "éxito".
- **Evidencia:** `dashboard.js:558-587`; `theme.css:626-633`; `timeline.css:429`.
- **Verificación:** confirmado (código); ratio estimado.
- **Impacto:** mantenimiento más difícil y enlaces poco legibles.
- **Recomendación:** mover los estilos inyectados a `theme.css`; token `--link-color` accesible (por ejemplo azul oscuro).
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A18 — Estados vacíos sin acción sugerida
- **Severidad / esfuerzo:** Baja / S
- **Descripción:** Los estados vacíos son neutros y correctos (ADR-011, citado en el informe; el ADR no se leyó), pero el texto de la tabla en cursiva usa muted (ver A2). Sin acción sugerida.
- **Evidencia:** `theme.css:278-283`; `dashboard.js:610-615`.
- **Verificación:** confirmado (código); contraste estimado.
- **Impacto:** el usuario no recibe una salida clara desde un estado vacío.
- **Recomendación:** mantener el tono; añadir un hint ("Prueba otro pool") y listar los pools con datos.
- **Riesgo de regresión:** No evaluado en la auditoría original.

### A19 — Región viva incompleta
- **Severidad / esfuerzo:** Baja / S
- **Descripción:** Solo los contadores del pool tienen `aria-live`. El cambio de grupo no anuncia que KPIs, timeline y tabla cambiaron. `sync-indicator` tiene `aria-label` sin rol.
- **Evidencia:** `dashboard_template.html:28-31`; `dashboard.js:854-871`.
- **Verificación:** confirmado (código); no probado con lector de pantalla.
- **Impacto:** usuarios de lectores de pantalla no reciben aviso del cambio de grupo.
- **Recomendación:** anunciar el cambio de grupo vía la región viva existente; `role=img` o `role=status` al indicador de sincronía.
- **Riesgo de regresión:** No evaluado en la auditoría original.

## 7. Quick wins vs. cambios mayores

**Quick wins (S):** A1, A2, A3, A8, A9, A10, A12, A16, A17, A18, A19.
**Cambios mayores (M):** A4, A5, A6, A7, A11, A13, A14, A15.

## 8. Top 10 priorizado (informe original)

1. A1 + A2 — contraste de KPI, badges y texto muted (solo tokens).
2. A3 — anillo de foco global.
3. A6 — selección y hover cruzados, KPI como filtro.
4. A4 — drawer como diálogo accesible.
5. A5 — quitar `role=img` y dar `aria-label` a barras.
6. A7 — marcador de "ahora" y una política de frescura.
7. A8 — escala de severidad y color propio para "Coordinado".
8. A12 — mensaje visible de error de contrato.
9. A9 + A10 — leyenda completa y definiciones de KPI.
10. A11 — tabla con orden, búsqueda y filtro por estado.

**A preservar:** identidad visual (color de pool en barra, borde y badge), tono neutro de los vacíos, columna sticky y selector de pool. Ninguna recomendación requiere rediseñar.

## 9. Información faltante

- Ningún hallazgo del informe original quedó incompleto en evidencia o recomendación.
- El **riesgo de regresión** y un **impacto** formal no formaban parte del informe original; no se inventaron.
- Estado de implementación de los estados "en vuelo", "colgado" y "adelantado": no verificado.

## 10. Implementación de quick wins (A1, A2, A3, A8, A9, A10, A12)

Estado: **implementados**. Verificación visual en navegador pendiente (capturas claro/oscuro, navegación con Tab, error forzado).

- **A1 — Implementado.** Tokens de texto `--text-success` (#15803D claro / #4ADE80 oscuro), `--text-warning` (#B45309 / #FBBF24) y `--text-danger` solo para el texto de los valores KPI. Badge y barra "Inicio atrasado": texto oscuro `--text-on-warning` (#1F2937 sobre #F59E0B, 6.83:1; antes blanco, 2.15:1). Rellenos, bordes y colores de pool sin cambios.
- **A2 — Implementado.** `--text-muted`: claro #64748B (4.76:1 sobre blanco; 4.34:1 sobre #F1F5F9), oscuro #94A3B8 (5.71:1 sobre #1E293B).
- **A3 — Implementado.** Token `--focus-ring` (#1D4ED8 claro / #60A5FA oscuro) y regla global `:focus-visible` (2px, offset 2px). Las barras dibujan el anillo hacia adentro para que el contenedor con scroll no lo recorte. El `<select>` conserva su regla.
- **A8 — Implementado.** Clases `kpi-card--severity-neutral|attention|critical` con tokens `--severity-*`. Mapa: en curso = neutral; por vencer = atención; adelantados, atrasados, fuera de ventana y vencidas = crítico. `badge--coordinado` usa tokens propios (`--color-coordinado-*`), distintos de `--color-yape`. Conteo, orden y etiquetas de KPI intactos.
- **A9 — Implementado.** Leyenda ampliada (pool, Pase en curso, Inicio atrasado, Derivado punteado, Conflicto) y swatch "fuera de turno" dependiente del tema.
- **A10 — Implementado.** `title` en cada tarjeta KPI con definición y umbral (5 min inicio atrasado, 10 min ratificación por vencer; `python/rules.py:27-28`). Etiquetas sin renombrar.
- **A12 — Implementado.** Banner `role="alert"` oculto por defecto (`#load-error`); se muestra con el primer error solo en la ruta DATA nula / contrato inválido. `console.error` se conserva.

### Revisión de solo lectura sobre horarios (sección 1b)

Resultado: **no se encontraron rutas de escritura de fechas u horas de pases en `web/`.** Lo único que se persiste en el cliente son dos claves de `localStorage`: `changeops-theme` y `agileops-visibility-group`. En Python solo se escriben archivos de salida generados (`renderer.py:221-230` y `:350`); `excel_reader` solo lee (`pd.read_excel`).
