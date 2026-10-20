/**
 * Timeline Component — ADR-002 + ADR-004
 *
 * Self-contained, layered CSS-Grid timeline. NO <table>.
 *
 * Responsibilities (TIMELINE_SPEC.md):
 *   - Render bars with correct positioning (ADR-004: minutes)
 *   - ONE global view: a single flat lane list, no pool sections
 *   - Group rows by (pool, RECURSO ASIGNADO) so homonymous resources in
 *     different pools never share a lane
 *   - Detect and stack overlapping bars vertically
 *   - Detect Implementation vs Implementation conflicts (orange triangle)
 *   - Horizontal scroll with sticky responsable column
 *   - Drawer integration (click → open)
 *
 * Architecture: 5 layers (header, grid, bars, indicators, selection).
 *
 * Viewport: 4h anchored to the RUN CLOCK (meta.updatedAt), not to the
 * hour-floored contract window, so a 04:30 run reads 04:30 → 08:30.
 *
 * Data source: Data Contract v1 (meta, kpis, timeline, table). Python emits
 * `timeline` grouped by pool from the single source of truth
 * (column_map.POOL_FAMILY_ORDER); the 4h slice and the flattening into lanes
 * happen here, so the Contract stays frozen. The responsable comes from the bar
 * itself or, for older contracts, from
 * window.ChangeOpsActions.passesInWindow[].resource.
 */

window.Timeline = (function () {
  'use strict';

  /* =========================================================
     CONSTANTS — ADR-004 grid math
     ========================================================= */
  var CELL_MIN = 30;   // minutes per grid cell
  var CELL_PX  = 96;   // pixels per grid cell (in sync with --timeline-grid-30min)
  var DEFAULT_LABEL_W = 220;

  /* Global view window: 4h anchored to the RUN CLOCK (meta.updatedAt), not to
     the hour-floored contract window. A run at 04:30 shows 04:30 → 08:30; the
     contract stays 8h wide and this layer only looks at the first 4h from the
     run minute. Bars keep absolute window minutes (ADR-004) and are shifted by
     _viewOffsetMin when drawn. */
  var VIEW_MINUTES = 240;   // 4 hours

  /* =========================================================
     POOL SCOPE — data-driven, never hardcoded (ADR-009)
     ---------------------------------------------------------
     A bar carries its pool family from the contract, which Python
     emits from column_map.POOL_FAMILY_ORDER. The pool is only used
     for lane identity and the off-shift lookup here; there is no
     pool section and no display order.
     ========================================================= */
  var UNKNOWN_POOL = 'Unknown';       // pool label when a bar carries none
  var UNKNOWN_POOL_KEY = 'unknown';   // CSS token for UNKNOWN_POOL

  /* Short on-bar pool tag. Keyed by the CSS token from _poolKey; a pool outside
     this table falls back to the first 3 letters of its name, so a new pool
     still gets a tag without a code change. */
  var CHIP_MIN_FULL_PX = 140;    // bar width for the full pool pill
  var CHIP_MIN_DOT_PX = 56;      // below this the ticket owns the whole bar
  var DERIVADO_TAG_MIN_PX = 250; // bar width for the secondary DERIVADO tag
  /* POOL CATALOG: the ONE place that decides which pool a record belongs to.
     `id` is the stable internal identifier (also the CSS token and data-pool);
     `aliases` are slugs (see _poolKey) of every spelling found in the data:
     the pool family from the contract ("AgileOps Prod") and the raw resource
     names ("Pool AgileOps Prod"). The Timeline bars, the legend, the table POOL
     column and the table pool filter all go through poolInfo(). */
  var POOL_CATALOG = [
    { id: 'yape',          tag: 'YAPE', label: 'Yape',          aliases: ['yape', 'pool-yape'] },
    { id: 'sf',            tag: 'S&F',  label: 'S&F',           aliases: ['sf', 'pool-sf'] },
    { id: 'agileops-oro',  tag: 'ORO',  label: 'AgileOps ORO',  aliases: ['agileops-oro', 'oro', 'pool-agileops-oro'] },
    { id: 'agileops-prod', tag: 'PROD', label: 'AgileOps Prod', aliases: ['agileops-prod', 'prod', 'pool-agileops-prod'] },
  ];
  var POOL_NONE_ID = 'sin-pool';

  /**
   * Normalize a pool value WITHOUT altering the original string:
   *   - blank / 'Unknown'     -> neutral SIN POOL (never guessed)
   *   - alias in the catalog  -> that pool
   *   - anything else         -> neutral chip with its own name (not mapped to
   *                              a catalog pool, because nothing backs that)
   */
  function _poolInfo(pool) {
    var raw = typeof pool === 'string' ? pool.trim() : '';
    if (!raw || raw === UNKNOWN_POOL) {
      return { id: POOL_NONE_ID, tag: 'SIN POOL', label: 'Sin pool', known: false, raw: '' };
    }
    var slug = _poolKey(raw);
    for (var n = 0; n < POOL_CATALOG.length; n++) {
      if (POOL_CATALOG[n].aliases.indexOf(slug) !== -1) {
        var c = POOL_CATALOG[n];
        return { id: c.id, tag: c.tag, label: c.label, known: true, raw: raw };
      }
    }
    return { id: slug, tag: raw.toUpperCase().slice(0, 8), label: raw, known: false, raw: raw };
  }

  /* Chip markup shared by bars, legend and table. `width` (px) picks the form on
     a bar: full pill, accent square, or nothing; omit it for the full pill. */
  function _poolChipHtml(pool, width) {
    var info = _poolInfo(pool);
    var w = (typeof width === 'number') ? width : Infinity;
    if (w < CHIP_MIN_DOT_PX) return '';
    var full = w >= CHIP_MIN_FULL_PX;
    return '<span class="timeline__pool-chip timeline__pool-chip--' + info.id
      + (full ? '' : ' timeline__pool-chip--dot') + '" aria-hidden="true">'
      + (full ? _esc(info.tag) : '') + '</span>';
  }
  function _derivadoTagHtml(bar, width) {
    return (bar.type === 'derivado' && width >= DERIVADO_TAG_MIN_PX)
      ? '<span class="timeline__derivado-tag" aria-hidden="true">DERIVADO</span>'
      : '';
  }

  /* Tooltip: ticket, app, pool and duration; a derivado also names its origin,
     found as the non-derivado bar that carries the same ticket. */
  function _barTitle(bar) {
    var t = bar.ticket + ' — ' + bar.name;
    t += ' · Pool: ' + _poolInfo(bar.pool).tag;
    t += ' (' + bar.duration + ' min)';
    if (bar.type === 'derivado') {
      t += ' · Derivado';
      var origin = null;
      for (var k = 0; k < _allBars.length; k++) {
        var o = _allBars[k];
        if (o.ticket === bar.ticket && o.type !== 'derivado') { origin = o; break; }
      }
      if (origin) {
        t += ' · Origen: ' + (origin.responsable || '—')
          + ' (' + _poolInfo(origin.pool).tag + ')';
      }
    }
    return t;
  }
  /* =========================================================
     STATE
     ========================================================= */
  var _container = null;      // #timeline element
  var _contract  = null;      // Data Contract v1 object
  var _activeFilter = null;   // null = no filter, or status string
  var _allBars = [];          // flat array of all bar data
  var _onBarClick = null;     // callback(barData)
  var _responsableMap = {};   // ticket → RECURSO ASIGNADO (render-only)
  var _rowMetrics = {};       // lane key (pool + responsable) → { top, height }
  var _viewOffsetMin = 0;     // minutes from the window start to the run clock
  var _visibleBarCount = 0;   // bars drawn inside the 4h viewport by the last render
  var _cellPx = CELL_PX;      // px per 30-min cell; stretched to fill the container (_fitScale)
  var _resizeBound = false;   // window resize listener registered once
  var _resizeTimer = null;

  /* =========================================================
     INIT — receives Data Contract v1
     ========================================================= */
  function init(container, contract, onBarClick) {
    _container = container;
    _contract = contract;
    _onBarClick = onBarClick || null;

    _responsableMap = _buildResponsableMap();
    _viewOffsetMin = _computeViewOffset();
    _visibleBarCount = 0;
    _buildAllBars();
    render();
  }

  /* =========================================================
     VIEWPORT — 4h anchored to the run clock (global view)
     ---------------------------------------------------------
     The contract window starts on the hour (ADR-012) and updatedAt carries the
     exact run minute, so offset = updatedAt - windowStart. Drawing everything
     relative to that offset is what makes a 04:30 run read 04:30 → 08:30.
     ========================================================= */
  function _computeViewOffset() {
    var meta = (_contract && _contract.meta) || {};

    var wsParts = String(meta.windowStart || '').split(':');
    if (wsParts.length !== 2) return 0;
    var wsMin = parseInt(wsParts[0], 10) * 60 + parseInt(wsParts[1], 10);
    if (isNaN(wsMin)) return 0;

    var m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(
      String(meta.updatedAt || ''));
    if (!m) return 0;
    var upMin = parseInt(m[4], 10) * 60 + parseInt(m[5], 10);
    if (isNaN(upMin)) return 0;

    var off = upMin - wsMin;
    if (off < 0) off += 1440;   // run just after midnight
    return off < VIEW_MINUTES ? off : 0;
  }

  /** Minutes → pixels on the time axis. */
  function _minutesToPx(min) {
    return min * _cellPx / CELL_MIN;
  }

  /**
   * Stretch the 4h axis to the container width so no horizontal space is wasted.
   * CELL_PX is the floor (narrow screens scroll); wider screens get wider cells.
   * The value is mirrored into --timeline-grid-30min so CSS min-widths agree.
   */
  function _fitScale() {
    // -2: border/rounding safety so the axis never triggers a stray scrollbar.
    var avail = _container ? _container.clientWidth - _labelWidth() - 2 : 0;
    var cell = avail > 0 ? Math.floor((avail / (VIEW_MINUTES / CELL_MIN)) * 100) / 100 : CELL_PX;
    _cellPx = Math.max(CELL_PX, cell);
    if (_container && _container.style && _container.style.setProperty) _container.style.setProperty('--timeline-grid-30min', _cellPx + 'px');
  }

  function _bindResize() {
    if (_resizeBound || typeof window.addEventListener !== 'function') return;
    _resizeBound = true;
    window.addEventListener('resize', function () {
      clearTimeout(_resizeTimer);
      _resizeTimer = setTimeout(function () { render(); }, 120);
    });
  }

  /** "04:30" for a clock minute-of-day. */
  function _clockLabel(min) {
    var t = ((min % 1440) + 1440) % 1440;
    return _pad(Math.floor(t / 60)) + ':' + _pad(t % 60);
  }

  /**
   * The 4h viewport as clock minutes, so every consumer (empty state, tests)
   * reads ONE offset rule instead of re-deriving it.
   */
  function _viewWindow() {
    var meta = (_contract && _contract.meta) || {};
    var parts = String(meta.windowStart || '').split(':');
    var wsMin = parts.length === 2
      ? parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10)
      : 0;
    if (isNaN(wsMin)) wsMin = 0;

    var startMin = (wsMin + _viewOffsetMin) % 1440;
    return {
      startMin: startMin,
      endMin: (startMin + VIEW_MINUTES) % 1440,
      offsetMin: _viewOffsetMin,
      minutes: VIEW_MINUTES,
    };
  }

  /* =========================================================
     RESPONSABLE LOOKUP (render-only, from the action payload)
     ========================================================= */
  function _buildResponsableMap() {
    var map = {};
    var ambiguous = {};
    var actions = window.ChangeOpsActions;
    if (actions && Array.isArray(actions.passesInWindow)) {
      actions.passesInWindow.forEach(function (r) {
        if (!r || !r.ticket) return;
        var resp = String(r.resource || '').trim();
        if (!resp || resp.toLowerCase() === 'nan') return;
        // Same ticket with different responsables (impl + derivado rows share
        // the ticket): never guess — mark ambiguous so the fallback does not
        // pull both bars into one lane and fake a conflict. Bars from new
        // contracts carry their own `responsable` and skip this map entirely.
        if (map[r.ticket] === undefined) {
          map[r.ticket] = resp;
        } else if (map[r.ticket] !== resp) {
          ambiguous[r.ticket] = true;
        }
      });
    }
    Object.keys(ambiguous).forEach(function (t) { delete map[t]; });
    return map;
  }

  function _responsableFor(ticket) {
    return _responsableMap[ticket] || 'Sin asignar';
  }

  /* =========================================================
     BUILD flat bar index (for lookup)
     ========================================================= */
  function _buildAllBars() {
    _allBars = [];
    if (!_contract || !_contract.timeline) return;

    _contract.timeline.forEach(function (group) {
      group.bars.forEach(function (bar) {
        // New contracts carry `responsable` per bar (backend): duplicate
        // tickets keep their own lane. Only contracts saved before that
        // field fall back to the ticket-keyed map (ambiguous → Sin asignar).
        var resp = (bar.responsable && String(bar.responsable).trim())
          ? String(bar.responsable).trim()
          : _responsableFor(bar.ticket);
        _allBars.push({
          _idx: _allBars.length,
          ticket: bar.ticket,
          name: bar.name,
          type: bar.type,
          status: bar.status,
          start: bar.start,         // minutes from window start (ADR-004)
          duration: bar.duration,   // minutes (ADR-004)
          // T15: real planned dates (clipped geometry must never pose as data)
          iniPlan: bar.iniPlan,
          finPlan: bar.finPlan,
          pool: group.pool,         // pool family, from meta.poolOrder
          responsable: resp,
        });
      });
    });
  }

  /* =========================================================
     RENDER — orchestrates all 5 layers
     ========================================================= */
  function render() {
    if (!_container || !_contract) return;

    _fitScale();
    _bindResize();
    _renderHeader();
    _renderGrid();
    _renderBars();
    _renderConflicts();
  }

  /* =========================================================
     LAYER 1: HEADER (sticky gutter + hour labels)
     ========================================================= */
  function _renderHeader() {
    var el = document.getElementById('timeline-header');
    if (!el) return;

    var off = _viewOffsetMin;
    var html = '<div class="timeline__header-gutter"></div>';

    // Segments aligned to the clock hour: the first absorbs the run-minute
    // offset (04:30 → 05:00), the rest are whole hours, the last may be
    // partial. Every label sits on a real clock time.
    var cursor = 0;
    while (cursor < VIEW_MINUTES) {
      var abs = off + cursor;
      var toHour = (60 - (abs % 60)) % 60;
      var seg = toHour === 0 ? 60 : toHour;
      if (cursor + seg > VIEW_MINUTES) seg = VIEW_MINUTES - cursor;

      // A segment too narrow for its label (run at 14:55 -> 5 min before 15:00)
      // would print over the next hour label, so it stays blank.
      var segPx = _minutesToPx(seg);
      html += '<div class="timeline__hour" style="width:'
        + segPx + 'px">' + (segPx < 44 ? '' : _offClock(abs)) + '</div>';
      cursor += seg;
    }
    el.innerHTML = html;
  }

  /* =========================================================
     LAYER 2: GRID (sticky gutter + 30-min columns)
     ========================================================= */
  function _renderGrid() {
    var el = document.getElementById('timeline-grid');
    if (!el) return;

    // 8 half-hour cells over the 4h viewport. The first cell is partial when
    // the run minute is not a multiple of 30, so the remaining lines stay on
    // clock half-hours instead of drifting with the run clock.
    var first = CELL_MIN - (_viewOffsetMin % CELL_MIN);
    var widths = [first];
    var remaining = VIEW_MINUTES - first;
    while (remaining > 0) {
      var w = Math.min(CELL_MIN, remaining);
      widths.push(w);
      remaining -= w;
    }

    var html = '<div class="timeline__grid-gutter"></div>';
    widths.forEach(function (w) {
      html += '<div class="timeline__grid-col" style="width:'
        + _minutesToPx(w) + 'px"></div>';
    });
    el.innerHTML = html;
  }

  /* =========================================================
     LAYER 3: BARS — ONE flat global list (no pool sections)
     ---------------------------------------------------------
     Rows are grouped by (pool, responsable) but drawn as a single flat list
     ordered by first start. The pool only keeps two pools' homonymous
     resources in separate lanes and feeds the per-pool off-shift lookup.
     ========================================================= */
  function _renderBars() {
    var el = document.getElementById('timeline-bars');
    if (!el) return;

    var laneGroups = _groupLanes(_allBars);

    var rowHeight = _cssVar('--timeline-row-height', 32);
    var gap = _cssVar('--timeline-gap', 2);
    var headerOffset = _cssVar('--timeline-header-height', 28); // hour header / bars padding-top
    var off = _viewOffsetMin;

    _rowMetrics = {};
    var html = '';
    var cumulativeTop = headerOffset; // bars layer padding-top (hour header offset)
    var visibleCount = 0;

    laneGroups.forEach(function (group) {
      // Only the slice inside the 4h viewport is drawn: a pass already running
      // is clipped to the left edge (the resource IS occupied), and one that
      // starts after the viewport is dropped entirely.
      var bars = _clipToView(group.bars, off);
      if (bars.length === 0) return;
      visibleCount += bars.length;

      // Lane packing (interval partitioning): each lane holds only
      // non-overlapping bars, so a cascade A-B-C with A not overlapping
      // C reuses the same lane instead of growing the row.
      var lanes = _groupOverlaps(bars);
      var maxDepth = Math.max(1, lanes.length);

      var rowH = Math.max(
        rowHeight,
        maxDepth * (rowHeight - gap * 2) + gap * 2 + gap * (maxDepth - 1)
      );

      _rowMetrics[_laneKey(group.pool, group.responsable)] = {
        top: cumulativeTop,
        height: rowH,
      };

      html += '<div class="timeline__row" style="height:' + rowH + 'px">'
        + '<div class="timeline__row-label" title="' + _esc(group.responsable) + '">'
        + '<span class="timeline__row-name">' + _esc(group.responsable) + '</span>'
        + '<span class="timeline__row-count" title="' + bars.length + ' pase(s) en la ventana">' + bars.length + '</span>'
        + '</div>'
        + '<div class="timeline__row-lane">'
        + _offShiftHtml(group.pool, group.responsable, off);

      var barHeight = (rowH - gap * 2 - gap * (maxDepth - 1)) / maxDepth;

      lanes.forEach(function (lane, laneIdx) {
        // Divider between stacked sub-lanes: makes 1 vs 2 simultaneous passes
        // of the same resource unambiguous.
        if (laneIdx > 0) {
          html += '<div class="timeline__sublane-sep" style="top:'
            + (gap + laneIdx * (barHeight + gap) - gap / 2 - 0.5) + 'px"></div>';
        }
        lane.forEach(function (item) {
          var bar = item.bar;

          // ADR-004 minutes from the window start, shifted into the viewport.
          // 1px inset each side so back-to-back passes never fuse into one block.
          var left  = _minutesToPx(bar._visStart) + 1;
          var width = Math.max(2, _minutesToPx(bar._visEnd - bar._visStart) - 2);
          var top   = gap + laneIdx * (barHeight + gap);

            var classes = [
              'timeline__bar',
              'timeline__bar--' + _poolKey(bar.pool),
              'timeline__bar--' + bar.status,
            ];
            if (bar.type === 'derivado') {
              classes.push('timeline__bar--derivado');
            }

            if (_activeFilter && bar.status !== _activeFilter) {
              classes.push('timeline__bar--dimmed');
            }
            if (bar._hasConflict) {
              classes.push('timeline__bar--conflict');
            }

            var style = 'left:' + left + 'px'
              + ';width:' + width + 'px'
              + ';top:' + top + 'px'
              + ';height:' + barHeight + 'px';

            html += '<div class="' + classes.join(' ') + '"'
              + ' style="' + style + '"'
              + ' data-ticket="' + _esc(bar.ticket) + '"'
              + ' data-idx="' + bar._idx + '"'
              + ' data-status="' + _esc(bar.status) + '"'
              + ' data-pool="' + _poolInfo(bar.pool).id + '"'
              + ' data-type="' + _esc(bar.type) + '"'
              + ' title="' + _esc(_barTitle(bar)) + '"'
              + ' role="button" tabindex="0">'
              + _poolChipHtml(bar.pool, width)
              + (width < 56 ? '' : _esc(bar.ticket))   // too narrow to read; the tooltip has it
              + _derivadoTagHtml(bar, width)
              + '</div>';
          });
      });

      html += '</div></div>';   // lane + row
      cumulativeTop += rowH;
    });

    _visibleBarCount = visibleCount;
    el.innerHTML = html;

    el.querySelectorAll('.timeline__bar').forEach(function (barEl) {
      barEl.addEventListener('click', function () {
        var barData = _findBarByIdx(barEl.dataset.idx) || _findBarByTicket(barEl.dataset.ticket);
        if (barData && _onBarClick) _onBarClick(barData);
      });
      barEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          var barData = _findBarByIdx(barEl.dataset.idx) || _findBarByTicket(barEl.dataset.ticket);
          if (barData && _onBarClick) _onBarClick(barData);
        }
      });
    });
  }

  /* =========================================================
     T19: OFF-SHIFT LANE SHADING from window.ResourceShifts (backend payload).
     Unmatched lanes and missing payload render nothing (degraded path).
     Labels render only on wide segments; every segment has a title tooltip.
     ========================================================= */
  function _laneShift(pool, responsable) {
    var RS = (typeof window !== 'undefined') ? window.ResourceShifts : null;
    if (!RS || !RS[pool] || !RS[pool][responsable]) return null;
    return RS[pool][responsable];
  }

  function _offClock(min) {
    var parts = _contract.meta.windowStart.split(':');
    var t = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + min;
    return _clockLabel(t);
  }

  function _offLabel(seg) {
    if (seg[0] <= 0 && seg[1] >= 480) return 'Fuera de turno';
    if (seg[0] <= 0) return 'Fuera de turno (antes de ' + _offClock(seg[1]) + ')';
    if (seg[1] >= 480) return 'Fuera de turno (después de ' + _offClock(seg[0]) + ')';
    return 'Fuera de turno (entre ' + _offClock(seg[0]) + ' y ' + _offClock(seg[1]) + ')';
  }

  function _offShiftHtml(pool, responsable, off) {
    var lane = _laneShift(pool, responsable);
    if (!lane || !lane.matched || !Array.isArray(lane.fuera)) return '';
    var viewEnd = off + VIEW_MINUTES;
    var out = '';
    lane.fuera.forEach(function (seg) {
      // Same 4h viewport as the bars: clip to the left edge and drop segments
      // that only exist outside it.
      var from = Math.max(seg[0], off);
      var to = Math.min(seg[1], viewEnd);
      if (to <= from) return;
      var left = _minutesToPx(from - off);
      var width = _minutesToPx(to - from);
      // The tooltip keeps the real shift boundaries, not the clipped ones.
      var label = _offLabel(seg);
      out += '<div class="timeline__offshift"'
        + ' style="left:' + left + 'px;width:' + width + 'px"'
        + ' title="' + _esc(label) + '">';
      if (width >= 140) {
        out += '<span class="timeline__offshift-label">' + _esc(label) + '</span>';
      }
      out += '</div>';
    });
    return out;
  }

  /** Stable lane identity: homonymous resources in different pools never merge. */
  function _laneKey(pool, responsable) {
    return String(pool || UNKNOWN_POOL) + '\u0000' + String(responsable || '');
  }

  /**
   * ONE flat lane list for the global view: group by (pool, responsable),
   * ordered by first start with responsable as the tie-breaker.
   * A bar without a pool is grouped under UNKNOWN_POOL rather than being
   * forced into a real pool — a silent wrong default would mislabel it.
   */
  function _groupLanes(allBars) {
    var byLane = {};
    allBars.forEach(function (bar) {
      var pool = bar.pool || UNKNOWN_POOL;
      var key = _laneKey(pool, bar.responsable);
      if (!byLane[key]) {
        byLane[key] = { pool: pool, responsable: bar.responsable, bars: [] };
      }
      byLane[key].bars.push(bar);
    });

    return Object.keys(byLane).map(function (key) {
      return byLane[key];
    }).sort(function (a, b) {
      var delta = _firstStart(a.bars) - _firstStart(b.bars);
      if (delta !== 0) return delta;
      if (a.responsable === b.responsable) return 0;
      return String(a.responsable) < String(b.responsable) ? -1 : 1;
    });
  }

  /**
   * Clip a lane's bars to [off, off + VIEW_MINUTES] and store the visible
   * range on each bar as _visStart / _visEnd (both relative to the viewport).
   * Mutating in place is safe: the visible range is recomputed on every render
   * and never feeds the contract.
   */
  function _clipToView(bars, off) {
    var viewEnd = off + VIEW_MINUTES;
    var out = [];
    bars.forEach(function (bar) {
      var from = Math.max(bar.start, off);
      var to = Math.min(bar.start + bar.duration, viewEnd);
      if (to <= from) return;
      bar._visStart = from - off;
      bar._visEnd = to - off;
      out.push(bar);
    });
    return out;
  }

  function _firstStart(bars) {
    return Math.min.apply(null, bars.map(function (b) { return b.start; }));
  }

  /* =========================================================
     LAYER 4: INDICATORS (conflict triangles, row-aligned)
     ========================================================= */
  function _renderConflicts() {
    var el = document.getElementById('timeline-indicators');
    if (!el) return;

    _allBars.forEach(function (b) { b._hasConflict = false; });

    var off = _viewOffsetMin;
    var html = '';

    // Same lane list as _renderBars — one list, two consumers.
    _groupLanes(_allBars).forEach(function (group) {
      var bars = _clipToView(group.bars, off);
      if (bars.length === 0) return;

      var conflicts = _detectConflicts(bars);
      if (!conflicts.length) return;

      var metrics = _rowMetrics[_laneKey(group.pool, group.responsable)]
        || { top: 0, height: 44 };
      var top = metrics.top + (metrics.height / 2) - 5;

      conflicts.forEach(function (conflict) {
        // Mark by object reference: duplicate tickets share the ticket
        // string, so a ticket-keyed lookup would flag the wrong bar.
        conflict.bars.forEach(function (bar) { bar._hasConflict = true; });

        var midMin = (conflict.start + conflict.end) / 2;
        var left = _labelWidth() + _minutesToPx(midMin);

        html += '<div class="timeline__conflict"'
          + ' style="left:' + (left - 8) + 'px;top:' + top + 'px"'
          + ' title="Conflicto: Implementación vs Implementación"'
          + '></div>';
      });
    });

    el.innerHTML = html;
  }

  /* =========================================================
     KPI FILTER
     ========================================================= */
  function filterByStatus(status) {
    _activeFilter = (_activeFilter === status) ? null : status;
    render();
    return _activeFilter;
  }

  function clearFilter() {
    _activeFilter = null;
    render();
  }

  function getActiveFilter() {
    return _activeFilter;
  }

  /* =========================================================
     HELPERS — conflict detection (ADR-004 minutes)
     ========================================================= */
  function _isImplementacion(bar) {
    return bar.type === 'implementacion';
  }

  function _barsOverlap(a, b) {
    // Visible-range geometry: an overlap is only real where both bars are
    // actually drawn inside the 4h viewport.
    return a._visStart < b._visEnd && b._visStart < a._visEnd;
  }

  function _detectConflicts(bars) {
    var implBars = bars.filter(_isImplementacion);
    var conflicts = [];
    for (var i = 0; i < implBars.length; i++) {
      for (var j = i + 1; j < implBars.length; j++) {
        if (_barsOverlap(implBars[i], implBars[j])) {
          conflicts.push({
            bars: [implBars[i], implBars[j]],
            barTickets: [implBars[i].ticket, implBars[j].ticket],
            start: Math.max(implBars[i]._visStart, implBars[j]._visStart),
            end: Math.min(implBars[i]._visEnd, implBars[j]._visEnd),
          });
        }
      }
    }
    return conflicts;
  }

  function _groupOverlaps(bars) {
    if (!bars || bars.length === 0) return [];
    var sorted = bars.map(function (b, i) { return { idx: i, bar: b }; })
      .sort(function (a, b) { return a.bar.start - b.bar.start; });

    // Interval partitioning: assign each bar to the first lane whose
    // last bar already ended. Lanes = max concurrency, not chain length.
    var lanes = [];
    var laneEnds = [];

    sorted.forEach(function (item) {
      var placed = false;
      for (var l = 0; l < lanes.length; l++) {
        if (item.bar.start >= laneEnds[l]) {
          lanes[l].push(item);
          laneEnds[l] = item.bar.start + item.bar.duration;
          placed = true;
          break;
        }
      }
      if (!placed) {
        lanes.push([item]);
        laneEnds.push(item.bar.start + item.bar.duration);
      }
    });
    return lanes;
  }

  /* =========================================================
     UTILITIES
     ========================================================= */
  function _findBarByTicket(ticket) {
    return _allBars.find(function (b) { return b.ticket === ticket; }) || null;
  }

  function _findBarByIdx(idx) {
    var n = parseInt(idx, 10);
    if (isNaN(n) || n < 0 || n >= _allBars.length) return null;
    return _allBars[n];
  }

  /**
   * Pool name → CSS-safe token. SINGLE SOURCE of the mapping (ADR-009).
   *
   * `String.prototype.toLowerCase()` alone is NOT enough: the real pool names
   * contain characters that are invalid in a class selector —
   * "S&F" carries '&', "AgileOps ORO" / "AgileOps Prod" carry a space.
   *
   * Rules, applied in order:
   *   1. non-string / empty → 'unknown' (never '' — an empty token would
   *      produce the bare `.timeline__bar--` class)
   *   2. decompose + drop combining marks, so accents never leak in
   *   3. lower-case
   *   4. spaces and underscores → '-'; collapse runs
   *   5. drop every remaining non [a-z0-9-] character ('&', '.', '/', …)
   *   6. trim leading/trailing '-'
   *
    *   "Yape"        → "yape"
    *   "S&F"         → "sf"
    *   "AgileOps ORO"  → "agileops-oro"
    *   "AgileOps Prod" → "agileops-prod"
   *
   * dashboard.js reaches this through window.Timeline.poolKey, so the badge
   * class can never drift from the timeline token.
   */
  function _poolKey(pool) {
    if (typeof pool !== 'string') return UNKNOWN_POOL_KEY;

    var token = pool
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[\s_]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/^-+|-+$/g, '');

    return token || UNKNOWN_POOL_KEY;
  }

  function _pad(n) {
    return String(n).padStart(2, '0');
  }

  function _esc(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function _cssVar(name, fallback) {
    var el = _container || document.documentElement;
    var val = getComputedStyle(el).getPropertyValue(name).trim();
    var num = parseInt(val, 10);
    return isNaN(num) ? fallback : num;
  }

  function _labelWidth() {
    return _cssVar('--timeline-label-width', DEFAULT_LABEL_W);
  }

  function scrollToHour(hour) {
    if (!_container || !_contract) return;
    var wsParts = _contract.meta.windowStart.split(':');
    var wsMin = parseInt(wsParts[0], 10) * 60 + parseInt(wsParts[1], 10);
    var delta = (parseInt(hour, 10) * 60) - wsMin;
    if (delta < 0) delta += 1440;

    // Only hours inside the 4h viewport are addressable; anything outside
    // scrolls back to the start instead of pointing past the grid.
    var visMin = delta - _viewOffsetMin;
    if (visMin < 0 || visMin > VIEW_MINUTES) {
      _container.scrollLeft = 0;
      return;
    }
    _container.scrollLeft = Math.max(0, _minutesToPx(visMin));
  }

  /* =========================================================
     PUBLIC API
     ========================================================= */
  return {
    init: init,
    render: render,
    filterByStatus: filterByStatus,
    clearFilter: clearFilter,
    getActiveFilter: getActiveFilter,
    scrollToHour: scrollToHour,
    // Public so dashboard.js shares ONE pool→token rule (ADR-009) instead of
    // re-deriving a class name with different logic.
    poolKey: _poolKey,
    // Pool catalog API: the table, legend and filters reuse it instead of
    // re-classifying pools (no second normalization anywhere).
    poolInfo: _poolInfo,
    poolChipHtml: function (pool) { return _poolChipHtml(pool); },
    poolCatalog: function () { return POOL_CATALOG.map(function (c) { return { id: c.id, tag: c.tag, label: c.label }; }); },
    poolNoneId: POOL_NONE_ID,
    // Public so the empty state and any consumer print the SAME 4h viewport the
    // grid draws, instead of re-deriving the run-clock offset.
    viewWindow: _viewWindow,
    clockLabel: _clockLabel,
    // Bars the last render actually drew. The contract window is 8h wide and
    // the component only draws 4h, so the contract bar count would overstate
    // what is on screen.
    visibleBarCount: function () { return _visibleBarCount; },
  };
})();