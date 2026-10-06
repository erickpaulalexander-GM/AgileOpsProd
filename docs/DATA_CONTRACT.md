# Data Contract v1

Contrato oficial entre el motor de datos (Python/Excel) y el frontend (dashboard.html).

## Estructura

```json
{
  "meta": {
    "updatedAt": "2026-09-10T23:40:00",
    "windowStart": "23:00",
    "windowEnd": "07:00"
  },
  "kpis": {
    "lateStarts": 2,
    "ratificationsSoon": 3,
    "ratificationsExpired": 1,
    "reversions": 0
  },
  "timeline": [
    {
      "pool": "Legacy",
      "bars": [
        {
          "ticket": "247397",
          "name": "Migración BD Legacy",
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
      "pool": "Legacy",
      "type": "Implementación",
      "ticket": "MVPLEGBCP-250917",
      "nombre_app": "ANX5",
      "status": "Coordinado",
      "inicio_impl": "11/09 10:00",
      "fin_impl": "11/09 11:00"
    }
  ]
}
```

## Campos

### `meta`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `updatedAt` | string (ISO 8601) | Fecha/hora de la última actualización del Excel |
| `windowStart` | string (HH:MM) | Hora de inicio de la ventana de 8 horas |
| `windowEnd` | string (HH:MM) | Hora de fin de la ventana |

### `kpis`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `lateStarts` | number | Inicios atrasados |
| `ratificationsSoon` | number | Ratificaciones próximas a vencer |
| `ratificationsExpired` | number | Ratificaciones vencidas |
| `reversions` | number | Reversiones |

### `timeline[]`

Cada elemento es un pool con sus barras.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `pool` | string | Nombre del pool (`"Legacy"` o `"Yape"`) |
| `bars[]` | array | Barras del pool |

### `timeline[].bars[]`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `ticket` | string | ID del ticket (ej. `"247397"`) |
| `name` | string | Nombre descriptivo del pase |
| `type` | string | `"implementacion"` o `"derivado"` |
| `start` | number | Minutos desde el inicio de la ventana (ADR-004) |
| `duration` | number | Duración en minutos |
| `status` | string | `"coordinado"`, `"pase-en-curso"`, o `"inicio-atrasado"` |

### `table[]`

Tabla operativa (universo Legacy/Yape vivo). Orden de columnas:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `responsable` | string | RECURSO ASIGNADO |
| `pool` | string | `"Legacy"` o `"Yape"` |
| `type` | string | `"Implementación"` o `"Derivado"` |
| `ticket` | string | ID del ticket |
| `nombre_app` | string | NOMBRE APP |
| `status` | string | ESTADO ACTUAL (valor crudo del Excel) |
| `inicio_impl` | string | `FEC. HORA. INI. IMPL` como `DD/MM HH:MM` |
| `fin_impl` | string | `FEC. HORA. FIN. IMPL` como `DD/MM HH:MM` |

## Reglas

1. **Minutos desde ventana** (ADR-004): `timeline[].bars[].start` son minutos desde `windowStart`. `table[]` usa fechas ya formateadas (`DD/MM HH:MM`). No usar horas decimales.
2. **Ventana de 8 horas**: 480 minutos totales. `windowStart` a `windowEnd` = 8h.
3. **Celdas de 30 minutos**: Cada celda = 30 minutos = 80px.
4. **Separación**: 2px entre barras (manejado por CSS).
5. **Conflictos**: Solo `implementacion` vs `implementacion` en el mismo pool.
6. **Sin cruces de medianoche**: El motor Python debe convertir HH:MM a minutos correctamente.

## Diagrama de flujo

```
Excel
  ↓
Python adapter (python/adapter.py)
  ↓
Data Contract (JSON)
  ↓
Frontend (dashboard.html)
```

## Cambios

| Versión | Fecha | Cambio |
|---------|-------|--------|
| v1 | 2026-09-10 | Contrato inicial con ADR-004 (minutos) |
