# Timeline Component

Este componente debe poder evolucionar sin modificar dashboard.js.

Responsabilidades:

- Renderizar barras.
- Scroll horizontal.
- Resaltar barras.
- Abrir drawer.

## Pool families (data-driven, ADR-009)

El componente **no** conoce la lista de pools. La recibe del contrato:

| Fuente | Uso |
| --- | --- |
| `meta.poolOrder` | orden de las filas de pool, resuelto una vez en `init()` |
| `timeline[].pool` | nombre del pool al que pertenece cada barra |
| `Timeline.poolKey(name)` | slug CSS-safe; **única** fuente del mapeo nombre → token |

Pools actuales: `Yape`, `S&F`, `AgileOps ORO`, `AgileOps Prod` (4 familias;
`DERIVADO` es el tipo de barra, no un pool).

Reglas de comportamiento:

- `_poolOrder` se resuelve una sola vez y lo leen **ambos** bucles de render
  (`_renderBars` y `_renderConflicts`). Nunca hay dos listas que puedan
  discrepar.
- Un pool declarado sin barras simplemente no dibuja filas: no aparece
  `Unknown` ni `undefined` en pantalla.
- Una barra sin `pool` se agrupa bajo `Unknown`, nunca bajo un pool real.
- Si `meta.poolOrder` falta o viene vacío, el orden cae a los pools que sí
  tienen barras (alfabético). **Nunca** hay una lista de pools hardcodeada.
- Un pool presente en los datos pero ausente de `meta.poolOrder` se renderiza
  igual, al final, en orden alfabético.

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

Los acentos se declaran como tokens `--pool-accent-*` en `theme.css` (una vez
para light, otra para dark) y `timeline.css` solo liga token → token:

```css
.timeline__pool-header--agileops-oro { --pool-accent: var(--pool-accent-agileops-oro); }
```

El acento pinta el borde de 3 px y el punto de 8 px del encabezado de pool
(`.timeline__pool-dot` usa `background: var(--pool-accent)`, sin estilo inline).
Se declara por tema porque un acento oscuro es invisible sobre `--bg-surface`
en dark: los cuatro superan 3:1 en ambos temas.

El relleno de barra es siempre el tono claro `--color-*` y **no** se re-declara
para dark, porque el texto de la barra es oscuro (`rgba(0,0,0,.7)`): así la
etiqueta mantiene >14:1 en los dos temas.

## Añadir una familia de pool

1. Declararla en `python/column_map.py` (`_POOL_FAMILY_RESOURCES`).
2. Declarar su `--color-*` y sus `--pool-accent-*` (light y dark) en `theme.css`.
3. Enlazar el token en `timeline.css` (`.timeline__pool-header--<token>` y
   `.timeline__bar--<token>`) y en `theme.css` (`.badge--<token>`).

No hace falta tocar `timeline.js` ni el orden de render: el slug lo produce
`Timeline.poolKey()`.
