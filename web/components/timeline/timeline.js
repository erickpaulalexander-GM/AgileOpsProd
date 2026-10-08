/**
 * Timeline Component — ADR-002 + ADR-004 (v1.1.5)
 *
 * Self-contained, layered CSS-Grid timeline. NO <table>.
 *
 * Responsibilities (TIMELINE_SPEC.md):
 *   - Render bars with correct positioning (ADR-004: minutes)
 *   - Group rows by RECURSO ASIGNADO (render-only, from window.ChangeOpsActions)
 *   - One single row per responsable: sticky label + bar lane
 *   - Detect and stack overlapping bars vertically
 *   - Detect Implementation vs Implementation conflicts (orange triangle)
 *   - Horizontal scroll with sticky responsable column
 *   - Drawer integration (click → open)
 *
 * Architecture: 5 layers (header, grid, bars, indicators, selection).
 *
 * Data source: Data Contract v1 (meta, kpis, timeline, table). The pool rows
 * and their display order come from `meta.poolOrder`, which Python emits from
 * the single source of truth (column_map.POOL_FAMILY_ORDER) — this layer never
 * hardcodes the pool list. The responsable grouping is derived at render time
 * from `window.ChangeOpsActions.passesInWindow[].resource` — the Contract is
 * frozen.
 */

window.Timeline = (function () {
  'use strict';

  /* =========================================================
     CONSTANTS — ADR-004 grid math
     ========================================================= */
  var CELL_MIN = 30;   // minutes per grid cell
  var CELL_PX  = 96;   // pixels per grid cell (in sync with --timeline-grid-30min)
  var DEFAULT_LABEL_W = 220;

  /* =========================================================
     POOL SCOPE — data-driven, never hardcoded (ADR-009)
     ---------------------------------------------------------
     meta.poolOrder is the single source of truth for the display
     order, published by Python (column_map.POOL_FAMILY_ORDER). This
     layer resolves it ONCE in init() and both render loops read the
     same resolved list, so the two loops can never disagree.
     ========================================================= */
  var UNKNOWN_POOL = 'Unknown';       // pool label when a bar carries none
  var UNKNOWN_POOL_KEY = 'unknown';   // CSS token for UNKNOWN_POOL

  /* =========================================================
     STATE
     ========================================================= */
  var _container = null;      // #timeline element
  var _contract  = null;      // Data Contract v1 object
  var _activeFilter = null;   // null = no filter, or status string
  var _allBars = [];          // flat array of all bar data
  var _onBarClick = null;     // callback(barData)
  var _responsableMap = {};   // ticket → RECURSO ASIGNADO (render-only)
  var _rowMetrics = {};       // responsable → { top, height } within the rows area
  var _poolOrder = [];        // display order, resolved once from meta.poolOrder

  /* =========================================================
     INIT — receives Data Contract v1
     ========================================================= */
  function init(container, contract, onBarClick) {
    _container = container;
    _contract = contract;
    _onBarClick = onBarClick || null;

    _responsableMap = _buildResponsableMap();
    _poolOrder = _resolvePoolOrder(_contract);
    _buildAllBars();
    render();
  }

  /* =========================================================
     POOL ORDER — resolved once from meta.poolOrder (ADR-009)
     ---------------------------------------------------------
     Never falls back to a hardcoded pool list: when meta.poolOrder
     is missing, empty or malformed we fall back to the pools that
     actually carry bars (alphabetical, so the order stays stable).
     A pool declared with zero bars simply renders no rows.
     ========================================================= */
  function _resolvePoolOrder(contract) {
    var declared = contract && contract.meta ? contract.meta.poolOrder : null;
    if (!Array.isArray(declared)) return [];

    var seen = {};
    var order = [];
    declared.forEach(function (pool) {
      if (typeof pool !== 'string') return;
      var name = pool.trim();
      if (!name || seen[name]) return;
      seen[name] = true;
      order.push(name);
    });
    return order;
  }

  /**
   * The ONE pool display order every render loop iterates.
   *
   * meta.poolOrder leads; any pool that carries bars but is missing from it is
   * appended in alphabetical order, so an unmapped pool can never be silently
   * dropped and a missing meta.poolOrder degrades to "every pool that has
   * bars" instead of rendering nothing. Still no hardcoded pool list.
   */
  function _orderedPoolNames(poolGroups) {
    var order = _poolOrder.slice();
    Object.keys(poolGroups || {}).sort().forEach(function (pool) {
      if (order.indexOf(pool) === -1) order.push(pool);
    });
    return order;
  }

  /* =========================================================
     RESPONSABLE LOOKUP (render-only, from the action payload)
     ========================================================= */
  function _buildResponsableMap() {
    var map = {};
    var actions = window.ChangeOpsActions;
    if (actions && Array.isArray(actions.passesInWindow)) {
      actions.passesInWindow.forEach(function (r) {
        if (!r || !r.ticket) return;
        var resp = String(r.resource || '').trim();
        if (resp && resp.toLowerCase() !== 'nan') map[r.ticket] = resp;
      });
    }
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
        _allBars.push({
          ticket: bar.ticket,
          name: bar.name,
          type: bar.type,
          status: bar.status,
          start: bar.start,         // minutes from window start (ADR-004)
          duration: bar.duration,   // minutes (ADR-004)
          pool: group.pool,         // pool family, from meta.poolOrder
          responsable: _responsableFor(bar.ticket),
        });
      });
    });
  }

  /* =========================================================
     RENDER — orchestrates all 5 layers
     ========================================================= */
  function render() {
    if (!_container || !_contract) return;

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

    var startParts = _contract.meta.windowStart.split(':');
    var startHour = parseInt(startParts[0], 10);
    var totalHours = 8; // 480 min / 60

    var html = '<div class="timeline__header-gutter"></div>';
    for (var h = 0; h < totalHours; h++) {
      var hour = (startHour + h) % 24;
      html += '<div class="timeline__hour">' + _pad(hour) + ':00</div>';
    }
    el.innerHTML = html;
  }

  /* =========================================================
     LAYER 2: GRID (sticky gutter + 30-min columns)
     ========================================================= */
  function _renderGrid() {
    var el = document.getElementById('timeline-grid');
    if (!el) return;

    var totalCells = (480 / CELL_MIN);
    var html = '<div class="timeline__grid-gutter"></div>';
    for (var c = 0; c < totalCells; c++) {
      html += '<div class="timeline__grid-col"></div>';
    }
    el.innerHTML = html;
  }

  /* =========================================================
     LAYER 3: BARS — grouped by POOL, then by RECURSO ASIGNADO
     ========================================================= */
  function _renderBars() {
    var el = document.getElementById('timeline-bars');
    if (!el) return;

    // Group bars by pool, then by responsable
    var poolGroups = _groupByPool(_allBars);

    var rowHeight = _cssVar('--timeline-row-height', 32);
    var gap = _cssVar('--timeline-gap', 2);
    // Both offsets are owned by CSS (timeline.css custom properties) so the
    // geometry stays in sync if the header or pool header height changes.
    var headerHeight = _cssVar('--timeline-pool-header-height', 28); // pool header height
    var headerOffset = _cssVar('--timeline-header-height', 28);      // hour header / bars padding-top

    _rowMetrics = {};
    var html = '';
    var cumulativeTop = headerOffset; // bars layer padding-top (hour header offset)

    _orderedPoolNames(poolGroups).forEach(function (poolName) {
      var poolData = poolGroups[poolName];
      if (!poolData || poolData.responsables.length === 0) return;

      // Render pool header (in-flow: consumes headerHeight)
      html += _renderPoolHeader(poolName, poolData);
      cumulativeTop += headerHeight;

      // Render responsables in this pool
      poolData.responsables.forEach(function (group) {
        var bars = group.bars;

        // Lane packing (interval partitioning): each lane holds only
        // non-overlapping bars, so a cascade A-B-C with A not overlapping
        // C reuses the same lane instead of growing the row.
        var lanes = _groupOverlaps(bars);
        var maxDepth = Math.max(1, lanes.length);

        var rowH = Math.max(
          rowHeight,
          maxDepth * (rowHeight - gap * 2) + gap * 2 + gap * (maxDepth - 1)
        );

        _rowMetrics[group.responsable] = { top: cumulativeTop, height: rowH };

        html += '<div class="timeline__row" style="height:' + rowH + 'px">'
          + '<div class="timeline__row-label" title="' + _esc(group.responsable) + '">'
          + _esc(group.responsable) + '</div>'
          + '<div class="timeline__row-lane">';

        var barHeight = (rowH - gap * 2 - gap * (maxDepth - 1)) / maxDepth;

        lanes.forEach(function (lane, laneIdx) {
          lane.forEach(function (item) {
            var bar = item.bar;

            // ADR-004: left and width in minutes → pixels (relative to the lane)
            var left  = bar.start * CELL_PX / CELL_MIN;
            var width = bar.duration * CELL_PX / CELL_MIN;
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
              + ' data-status="' + _esc(bar.status) + '"'
              + ' title="' + _esc(bar.ticket) + ' — ' + _esc(bar.name) + ' (' + bar.duration + ' min)' + (bar.type === 'derivado' ? ' · Derivado' : '') + '"'
              + ' role="button" tabindex="0">'
              + _esc(bar.ticket)
              + '</div>';
          });
        });

        html += '</div></div>';   // lane + row
        cumulativeTop += rowH;
      });
    });

    el.innerHTML = html;

    el.querySelectorAll('.timeline__bar').forEach(function (barEl) {
      barEl.addEventListener('click', function () {
        var barData = _findBarByTicket(barEl.dataset.ticket);
        if (barData && _onBarClick) _onBarClick(barData);
      });
      barEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          var barData = _findBarByTicket(barEl.dataset.ticket);
          if (barData && _onBarClick) _onBarClick(barData);
        }
      });
    });
  }

  /**
   * Group bars by pool, then by responsable.
   * Returns: { "Yape": { responsables: [], barCount: N }, ... }
   * Keys are the pool names published in meta.poolOrder, in any order;
   * _poolOrder drives the iteration.
   */
  function _groupByPool(allBars) {
    var byPool = {};
    allBars.forEach(function (bar) {
      // A bar without a pool is grouped under UNKNOWN_POOL rather than being
      // forced into a real pool — a silent wrong default would mislabel it.
      var pool = bar.pool || UNKNOWN_POOL;
      if (!byPool[pool]) byPool[pool] = { bars: [] };
      byPool[pool].bars.push(bar);
    });

    // Now group by responsable within each pool
    var result = {};
    Object.keys(byPool).forEach(function (pool) {
      var byResp = {};
      byPool[pool].bars.forEach(function (bar) {
        var resp = bar.responsable;
        if (!byResp[resp]) byResp[resp] = [];
        byResp[resp].push(bar);
      });

      var responsables = Object.keys(byResp).map(function (resp) {
        return { responsable: resp, bars: byResp[resp] };
      }).sort(function (a, b) {
        return _firstStart(a.bars) - _firstStart(b.bars);
      });

      var barCount = byPool[pool].bars.length;
      result[pool] = { responsables: responsables, barCount: barCount };
    });

    return result;
  }

  function _firstStart(bars) {
    return Math.min.apply(null, bars.map(function (b) { return b.start; }));
  }

  /**
   * Render a pool group header.
   */
  function _renderPoolHeader(poolName, poolData) {
    var resourceCount = poolData.responsables.length;
    var passCount = poolData.barCount;
    var poolKey = _poolKey(poolName);

    return '<div class="timeline__pool-header timeline__pool-header--' + poolKey + '">'
      + '<div class="timeline__pool-label">'
      // The dot colour comes from --pool-accent, set by the
      // .timeline__pool-header--<token> rule in timeline.css. The token IS the
      // single source shared with the bar fill, the badge and dashboard.js.
      + '<span class="timeline__pool-dot"></span>'
      + '<span class="timeline__pool-name">' + poolName + '</span>'
      + '<span class="timeline__pool-counts">' + resourceCount + ' recurso' + (resourceCount !== 1 ? 's' : '') + ' · ' + passCount + ' pase' + (passCount !== 1 ? 's' : '') + '</span>'
      + '</div>'
      + '</div>';
  }

  /* =========================================================
     LAYER 4: INDICATORS (conflict triangles, row-aligned)
     ========================================================= */
  function _renderConflicts() {
    var el = document.getElementById('timeline-indicators');
    if (!el) return;

    _allBars.forEach(function (b) { b._hasConflict = false; });

    var poolGroups = _groupByPool(_allBars);
    var html = '';

    // Same resolved order as _renderBars — one list, two consumers.
    _orderedPoolNames(poolGroups).forEach(function (poolName) {
      var poolData = poolGroups[poolName];
      if (!poolData || poolData.responsables.length === 0) return;

      poolData.responsables.forEach(function (group) {
        var conflicts = _detectConflicts(group.bars);
        if (!conflicts.length) return;

        var metrics = _rowMetrics[group.responsable] || { top: 0, height: 44 };
        var top = metrics.top + (metrics.height / 2) - 5;

        conflicts.forEach(function (conflict) {
          conflict.barTickets.forEach(function (ticket) {
            var bar = _allBars.find(function (b) { return b.ticket === ticket; });
            if (bar) bar._hasConflict = true;
          });

          var midMin = (conflict.start + conflict.end) / 2;
          var left = _labelWidth() + midMin * CELL_PX / CELL_MIN;

          html += '<div class="timeline__conflict"'
            + ' style="left:' + (left - 8) + 'px;top:' + top + 'px"'
            + ' title="Conflicto: Implementación vs Implementación"'
            + '></div>';
        });
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
    return a.start < (b.start + b.duration) && b.start < (a.start + a.duration);
  }

  function _detectConflicts(bars) {
    var implBars = bars.filter(_isImplementacion);
    var conflicts = [];
    for (var i = 0; i < implBars.length; i++) {
      for (var j = i + 1; j < implBars.length; j++) {
        if (_barsOverlap(implBars[i], implBars[j])) {
          conflicts.push({
            barTickets: [implBars[i].ticket, implBars[j].ticket],
            start: Math.max(implBars[i].start, implBars[j].start),
            end: Math.min(
              implBars[i].start + implBars[i].duration,
              implBars[j].start + implBars[j].duration
            ),
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
    var startParts = _contract.meta.windowStart.split(':');
    var startHour = parseInt(startParts[0], 10);
    var minFromStart = ((hour - startHour + 24) % 24) * 60;
    _container.scrollLeft = Math.max(0, minFromStart * CELL_PX / CELL_MIN);
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
  };
})();