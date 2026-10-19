# Timeline Component

Este componente debe poder evolucionar sin modificar dashboard.js.

Responsabilidades:

- Renderizar barras.
- Scroll horizontal.
- Resaltar barras.
- Abrir drawer.

## Vista global de 4 h (anclada al reloj de la corrida)

El timeline es **una sola vista global**: no hay secciones, cabeceras ni
sub-vistas por pool. El pool sigue existiendo como identidad de carril, no como
bloque visual.

| Concepto | Valor |
| --- | --- |
| Ventana que dibuja | 4 h = 240 min = 8 celdas de 30 min |
| Ancla | `meta.updatedAt` (minuto exacto de la corrida), **no** la hora del contrato |
| Offset | `updatedAt − meta.windowStart`, en minutos (`_viewOffsetMin`) |
| Contrato | sigue siendo de 8 h (`windowStart`/`windowEnd`); el recorte a 4 h es del frontend |

Una corrida a las 04:30 muestra **04:30 → 08:30**, aunque el contrato empiece a
las 04:00. Si el offset cae fuera de `[0, 240)` se usa `0` (degradado, sin
recorte).

Reglas de geometría:

- El eje se alinea al **reloj**, no al offset: la primera celda de la grilla es
  parcial (`CELL_MIN − off % CELL_MIN`) y el resto son celdas completas de
  30 min. Con off = 40 la primera celda mide 20 min y las líneas siguientes caen
  en :00 y :30 reales.
- El header se parte en segmentos alineados a la hora; el primero absorbe el
  offset (`04:30 → 05:00`) y se etiqueta con su hora real de inicio
  (`_offClock`). El último segmento puede ser parcial.
- Todas las posiciones se calculan con `_minutesToPx(min)` sobre minutos
  **relativos al viewport** (`min − off`).
- Una barra que ya estaba en curso se **recorta al borde izquierdo** (03:00–05:00
  con corrida 04:30 se ve 04:30–05:00: el recurso está ocupado ahora). Una barra
  que empieza después de las 4 h **no se dibuja**.
- El sombreado fuera de turno (`_offShiftHtml`) usa el mismo recorte; el tooltip
  conserva los bordes reales del turno, no los recortados.
- `Timeline.visibleBarCount()` devuelve cuántas barras se dibujaron de verdad;
  el badge del dashboard usa ese número (no el del contrato de 8 h) y el estado
  vacío se decide con él.

Los conflictos (ADR-004) se miden sobre el rango visible: un solapamiento que
queda fuera del viewport no es un conflicto en pantalla.

## API pública

| Símbolo | Uso |
| --- | --- |
| `init(container, contract, onBarClick)` | monta el componente y renderiza |
| `render()` | re-render completo |
| `filterByStatus(status)` / `clearFilter()` / `getActiveFilter()` | filtro por estado |
| `scrollToHour(hour)` | scrollea a una hora; fuera del viewport vuelve a 0 |
| `poolKey(name)` | slug CSS-safe; **única** fuente del mapeo nombre → token |
| `viewWindow()` | `{ startMin, endMin, offsetMin, minutes }` del viewport de 4 h |
| `clockLabel(min)` | `min` de día → `"04:30"` |
| `visibleBarCount()` | barras dibujadas en el último render |

## Filas (carriles)

Las filas se agrupan por **(pool, responsable)**, no solo por responsable: dos
personas homónimas en pools distintos conservan su propio carril, y el sombreado
fuera de turno se busca por pool + responsable. El orden es por primer inicio,
con el responsable como desempate. La clave interna del carril es
`_laneKey(pool, responsable)`.

El mismo listado de carriles lo leen **ambos** bucles de render (`_renderBars` y
`_renderConflicts`): nunca hay dos listas que puedan discrepar.

## Pool families (data-driven, ADR-009)

El componente **no** conoce la lista de pools. La recibe del contrato:

| Fuente | Uso |
| --- | --- |
| `timeline[].pool` | pool al que pertenece cada barra (identidad de carril y turnos) |
| `Timeline.poolKey(name)` | slug CSS-safe; **única** fuente del mapeo nombre → token |

Pools actuales: `Yape`, `S&F`, `AgileOps ORO`, `AgileOps Prod` (4 familias;
`DERIVADO` es el tipo de barra, no un pool).

Reglas de comportamiento:

- Una barra sin `pool` se agrupa bajo `Unknown`, nunca bajo un pool real.
- Un pool sin barras dentro del viewport simplemente no dibuja filas: no
  aparece `Unknown` ni `undefined` en pantalla.
- `meta.poolOrder` **ya no** define el orden de las filas (el orden es por
  primer inicio). Sigue en el contrato y lo consumen otros consumidores, pero el
  timeline no lo lee para ordenar.
- **Nunca** hay una lista de pools hardcodeada en este componente.

## Tokens CSS

`Timeline.poolKey()` produce el token; `dashboard.js` lo consume vía
`window.Timeline.poolKey` para el badge, de modo que la clase del badge nunca
puede desviarse del token de la barra. `pool.toLowerCase()` **no** alcanza:
`S&F` contiene `&` y `AgileOps ORO` contiene un espacio, y ambos son inválidos
en un selector de clase.

| Pool | Token | Acento light | Acento dark | Relleno de barra |
| --- | --- | --- | --- | --- |
| `Yape` | `yape` | `#B45309` | `#FB923C` | `--color-yape` `#F6E7A7` |
| `S&F` | `sf` | `#7C3AED` | `#A78BFA` | `--color-sf` `#E6D7FF` |
| `AgileOps ORO` | `agileops-oro` | `#1D4ED8` | `#38BDF8` | `--color-agileops-oro` `#BFDBFE` |
| `AgileOps Prod` | `agileops-prod` | `#BE185D` | `#F472B6` | `--color-agileops-prod` `#FBCFE8` |
| (sin pool) | `unknown` | `var(--border-strong)` | `var(--border-strong)` | `var(--bg-hover)` |

El relleno de barra es siempre el tono claro `--color-*` y **no** se re-declara
para dark, porque el texto de la barra es oscuro (`rgba(0,0,0,.7)`): así la
etiqueta mantiene >14:1 en los dos temas.

Los acentos se declaran como tokens `--pool-accent-*` en `theme.css` (una vez
para light, otra para dark) y se ligan en `.pool-group__badge--<token>`, el badge
del filtro global de pools (ADR-011). Se declara por tema porque un acento oscuro
es invisible sobre `--bg-surface` en dark: los cuatro superan 3:1 en ambos temas.

## Añadir una familia de pool

1. Declararla en `python/column_map.py` (`_POOL_FAMILY_RESOURCES`).
2. Declarar su `--color-*` y sus `--pool-accent-*` (light y dark) en `theme.css`.
3. Enlazar el token en `timeline.css` (`.timeline__bar--<token>`) y en
   `theme.css` (`.pool-group__badge--<token>` y `.badge--<token>`).

No hace falta tocar `timeline.js` ni el orden de render: el slug lo produce
`Timeline.poolKey()` y el orden de filas sale del primer inicio de cada carril.

## Fuera de turno (T19)

El fondo del carril sombrea los intervalos fuera de turno del responsable
(`window.ResourceShifts`, payload del backend): fondo slate-100 + diagonal
0.06 en claro (el slate-50 original se perdia; en dark variante propia),
siempre DETRÁS de las barras (orden DOM) para que los pases protagonicen.
Sin match de persona o sin archivo de turnos no se pinta nada. Las etiquetas
solo salen en segmentos anchos; todo segmento lleva tooltip.
