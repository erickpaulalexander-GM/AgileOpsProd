/*
  OpsTable - operational table: next-60-minutes window, per-column filters,
  sorting and expand/collapse over ONE dataset.

  Single pipeline (never duplicated per view):
      source rows -> enrich (normalize, originals kept) -> column filters
                  -> time mode (next hour | all) -> sort -> render + counters

  Sources of truth shared with the Timeline:
    - pool         : window.Timeline.poolInfo()  (one catalog, one normalization)
    - clock        : meta.updatedAt, the same anchor the Timeline uses for its
                     4h viewport (no independent clock, no Date.now())
    - status/type  : the contract row values, compared verbatim

  Rows whose INICIO/FIN cannot be parsed are never given an invented time: they
  are left out of the "next hour" projection (an overlap cannot be proven) but
  stay in the full list, sorted last.
*/

window.OpsTable = (function () {
  'use strict';

  var WINDOW_MIN = 60;                      // "next hour" length
  var NONE_POOL_ID = 'sin-pool';            // keep in sync with Timeline.poolNoneId

  var COLUMNS = [
    { key: 'resp',    label: 'RECURSO ASIGNADO', filter: 'text' },
    { key: 'pool',    label: 'Pool',             filter: 'pool' },
    { key: 'tipo',    label: 'Tipo',             filter: 'values' },
    { key: 'ticket',  label: 'Ticket',           filter: 'text' },
    { key: 'app',     label: 'NOMBRE APP',       filter: 'text' },
    { key: 'estado',  label: 'Estado Actual',    filter: 'values' },
    { key: 'inicio',  label: 'Inicio Impl',      filter: 'date' },
    { key: 'fin',     label: 'Fin Impl',         filter: 'date' },
  ];

  /* ===================================================== PURE LOGIC */

  function _blankFilters() {
    return {
      resp: '', ticket: '', app: '',
      pools: [], tipos: [], estados: [],
      inicio: { from: '', to: '' }, fin: { from: '', to: '' },
    };
  }

  /** meta.updatedAt ("2026-10-19T19:15:00", local) -> Date, or null. */
  function refFromMeta(meta) {
    var m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String((meta && meta.updatedAt) || ''));
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], 0, 0);
    return isNaN(d.getTime()) ? null : d;
  }

  /**
   * "DD/MM HH:MM" (the table's display format, no year) -> epoch ms or NaN.
   * The year comes from the reference clock; a result more than ~6 months from
   * it is shifted a year (Dec/Jan run boundary).
   */
  function parseRowDate(text, ref) {
    var m = /^\s*(\d{1,2})\/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$/.exec(String(text == null ? '' : text));
    if (!m || !ref) return NaN;
    var day = +m[1], mon = +m[2], hh = +m[3], mi = +m[4];
    var year = ref.getFullYear();
    var d = new Date(year, mon - 1, day, hh, mi, 0, 0);
    // Reject overflow ("31/02", "25:00"): the Date must round-trip.
    if (d.getMonth() !== mon - 1 || d.getDate() !== day || d.getHours() !== hh || d.getMinutes() !== mi) {
      return NaN;
    }
    var diff = d.getTime() - ref.getTime();
    var HALF_YEAR = 183 * 86400000;
    if (diff > HALF_YEAR) d = new Date(year - 1, mon - 1, day, hh, mi, 0, 0);
    else if (diff < -HALF_YEAR) d = new Date(year + 1, mon - 1, day, hh, mi, 0, 0);
    return d.getTime();
  }

  function _fold(s) {
    return String(s == null ? '' : s).toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function _poolInfo(pool) {
    var T = window.Timeline;
    if (T && typeof T.poolInfo === 'function') return T.poolInfo(pool);
    return { id: NONE_POOL_ID, tag: 'SIN POOL', label: 'Sin pool', known: false, raw: '' };
  }

  /** Add normalized fields next to the untouched original row. */
  function enrich(rows, ref) {
    return (rows || []).map(function (r, i) {
      var info = _poolInfo(r.pool);
      return {
        raw: r,
        idx: i,
        poolId: info.id,
        poolTag: info.tag,
        startMs: parseRowDate(r.inicio_impl, ref),
        endMs: parseRowDate(r.fin_impl, ref),
        f: {
          resp: _fold(r.responsable),
          ticket: _fold(r.ticket),
          app: _fold(r.nombre_app),
        },
      };
    });
  }

  function _dateBound(v) {
    if (!v) return NaN;
    var t = new Date(v).getTime();   // "YYYY-MM-DDTHH:MM" is local time
    return isNaN(t) ? NaN : t;
  }

  function _inDateRange(ms, range) {
    var from = _dateBound(range.from), to = _dateBound(range.to);
    if (isNaN(from) && isNaN(to)) return true;
    if (isNaN(ms)) return false;                 // unknown time never matches a date filter
    if (!isNaN(from) && ms < from) return false;
    if (!isNaN(to) && ms > to) return false;
    return true;
  }

  /** "2026-10-19T20:00" -> "19/10 20:00": the same format the cells display. */
  function _stampLabel(v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})$/.exec(String(v || ''));
    return m ? (m[3] + '/' + m[2] + ' ' + m[4]) : String(v || '');
  }

  /** epoch ms -> "YYYY-MM-DDTHH:MM", the value a datetime control carries. */
  function _localStamp(ms) {
    var d = new Date(ms);
    var p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + 'T' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  /**
   * The ONLY values INICIO/FIN may offer: the timestamps present in the rows,
   * chronological and deduped. Anything the source file does not contain is
   * not a real pass time, so it is never invented. `other` narrows the list to
   * the side of the range the opposite bound has not excluded yet.
   */
  function dateOptions(items, key, other) {
    var msKey = key === 'fin' ? 'endMs' : 'startMs';
    var fromMs = other && other.from ? _dateBound(other.from) : NaN;
    var toMs = other && other.to ? _dateBound(other.to) : NaN;
    var seen = {}, out = [];
    (items || []).forEach(function (it) {
      var ms = it[msKey];
      if (isNaN(ms)) return;                        // unparseable: no option
      if (!isNaN(fromMs) && ms < fromMs) return;    // beyond the other bound
      if (!isNaN(toMs) && ms > toMs) return;
      if (seen[ms]) return;
      seen[ms] = 1;
      out.push({ ms: ms, value: _localStamp(ms) });
    });
    out.sort(function (a, b) { return a.ms - b.ms; });
    return out.map(function (o) { return o.value; });
  }

  function filtersActive(f) {
    return !!(f.resp || f.ticket || f.app || f.pools.length || f.tipos.length || f.estados.length
      || f.inicio.from || f.inicio.to || f.fin.from || f.fin.to);
  }

  /** Step 3 of the pipeline: every column filter, AND-combined. */
  function applyFilters(items, f) {
    var q = { resp: _fold(f.resp.trim()), ticket: _fold(f.ticket.trim()), app: _fold(f.app.trim()) };
    return items.filter(function (it) {
      if (q.resp && it.f.resp.indexOf(q.resp) === -1) return false;
      if (q.ticket && it.f.ticket.indexOf(q.ticket) === -1) return false;
      if (q.app && it.f.app.indexOf(q.app) === -1) return false;
      if (f.pools.length && f.pools.indexOf(it.poolId) === -1) return false;
      if (f.tipos.length && f.tipos.indexOf(it.raw.type) === -1) return false;
      if (f.estados.length && f.estados.indexOf(it.raw.status) === -1) return false;
      if (!_inDateRange(it.startMs, f.inicio)) return false;
      if (!_inDateRange(it.endMs, f.fin)) return false;
      return true;
    });
  }

  /** [ref, ref+60min): start < windowEnd AND end > windowStart. */
  function overlapsWindow(it, ref) {
    if (!ref || isNaN(it.startMs) || isNaN(it.endMs)) return false;
    var ws = ref.getTime(), we = ws + WINDOW_MIN * 60000;
    return it.startMs < we && it.endMs > ws;
  }

  function _sortValue(it, key) {
    switch (key) {
      case 'resp':   return _fold(it.raw.responsable);
      case 'pool':   return it.poolTag;
      case 'tipo':   return _fold(it.raw.type);
      case 'ticket': return _fold(it.raw.ticket);
      case 'app':    return _fold(it.raw.nombre_app);
      case 'estado': return _fold(it.raw.status);
      case 'inicio': return it.startMs;
      case 'fin':    return it.endMs;
      default:       return it.idx;
    }
  }

  /** Step 5. Dates compare as numbers (chronological); unknown dates go last. */
  function sortItems(items, sort) {
    var dir = sort.dir === 'desc' ? -1 : 1;
    return items.slice().sort(function (a, b) {
      var va = _sortValue(a, sort.key), vb = _sortValue(b, sort.key);
      var na = typeof va === 'number' && isNaN(va), nb = typeof vb === 'number' && isNaN(vb);
      if (na || nb) {
        if (na && nb) return a.idx - b.idx;
        return na ? 1 : -1;                       // unknown last, whichever the direction
      }
      var c = (typeof va === 'number') ? (va - vb) : String(va).localeCompare(String(vb), 'es');
      return c !== 0 ? c * dir : a.idx - b.idx;
    });
  }

  /** The whole pipeline, as one pure function. */
  function project(items, state, ref) {
    var out = applyFilters(items, state.filters);
    if (state.mode === 'next') {
      out = out.filter(function (it) { return overlapsWindow(it, ref); });
    }
    return sortItems(out, state.sort);
  }

  /* ===================================================== UI */

  var _opts = null;           // { head, body, toolbar, jiraUrl }
  var _ref = null;
  var _items = [];
  var _group = null;
  var _valueOptions = { tipos: [], estados: [] };
  var _state = {
    mode: 'next',
    filters: _blankFilters(),
    sort: { key: 'inicio', dir: 'asc' },
  };
  var _headBuilt = false;

  function _esc(v) {
    var d = document.createElement('div');
    d.textContent = v == null ? '' : String(v);
    return d.innerHTML;
  }

  function _hhmm(ms) {
    var d = new Date(ms);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  function _statusClass(status) {
    return status === 'Coordinado' ? 'badge--coordinado'
      : status === 'Pase en curso' ? 'badge--pase-en-curso'
      : status === 'Inicio atrasado' ? 'badge--inicio-atrasado'
      : 'badge--neutral';
  }

  function _poolChip(pool) {
    var T = window.Timeline;
    return (T && typeof T.poolChipHtml === 'function')
      ? T.poolChipHtml(pool)
      : '<span class="timeline__pool-chip">' + _esc(_poolInfo(pool).tag) + '</span>';
  }

  function _canWindow() { return !!_ref; }

  function _effectiveState() {
    // Without a reference clock there is no window to compute: show everything.
    if (!_canWindow() && _state.mode === 'next') {
      return { mode: 'all', filters: _state.filters, sort: _state.sort };
    }
    return _state;
  }

  /* ---- head: titles (sortable) + filter row, built once ---- */
  function _optionChips(field, values, selected) {
    var all = values.slice();
    selected.forEach(function (v) { if (all.indexOf(v) === -1) all.push(v); });
    return all.map(function (v) {
      return '<button type="button" class="tf-chip" data-f="' + field + '" data-v="' + _esc(v) + '"'
        + ' aria-pressed="' + (selected.indexOf(v) !== -1) + '">' + _esc(v) + '</button>';
    }).join('');
  }

  function _poolChips(selected) {
    var T = window.Timeline;
    var cat = (T && T.poolCatalog) ? T.poolCatalog() : [];
    var noneId = (T && T.poolNoneId) || NONE_POOL_ID;
    var entries = cat.map(function (c) { return { id: c.id, tag: c.tag }; })
      .concat([{ id: noneId, tag: 'SIN POOL' }]);
    return entries.map(function (e) {
      return '<button type="button" class="tf-chip tf-chip--pool" data-f="pools" data-v="' + _esc(e.id) + '"'
        + ' aria-pressed="' + (selected.indexOf(e.id) !== -1) + '" title="' + _esc(e.tag) + '">'
        + '<span class="timeline__pool-chip timeline__pool-chip--' + _esc(e.id) + '">' + _esc(e.tag) + '</span></button>';
    }).join('');
  }

  function _filterCell(col) {
    var f = _state.filters;
    var reset = '<button type="button" class="tf-reset" data-reset="' + col.key + '" hidden'
      + ' title="Restablecer este filtro" aria-label="Restablecer filtro">&times;</button>';
    var body = '';
    if (col.filter === 'text') {
      body = '<input type="search" class="tf-input" data-f="' + col.key + '" value="' + _esc(f[col.key])
        + '" placeholder="Filtrar" aria-label="Filtrar ' + _esc(col.label) + '" autocomplete="off">';
    } else if (col.filter === 'pool') {
      body = '<span class="tf-chips" data-slot="pools">' + _poolChips(f.pools) + '</span>';
    } else if (col.filter === 'values') {
      var field = col.key === 'tipo' ? 'tipos' : 'estados';
      body = '<span class="tf-chips" data-slot="' + field + '">'
        + _optionChips(field, _valueOptions[field], f[field]) + '</span>';
    } else {
      body = _dateFilterBody(col);
    }
    return '<td data-col="' + col.key + '"><div class="tf-cell">' + body + reset + '</div></td>';
  }

  /** One <select> per bound, offering ONLY the timestamps the data has.
      Each side is narrowed by the opposite bound: a "desde" later than
      "hasta" can only ever yield an empty result, so it is not offered. */
  function _dateFilterBody(col) {
    var f = _state.filters;
    var _dateSel = function (side, other) {
      var chosen = f[col.key][side];
      var opts = dateOptions(_items, col.key, other);
      if (chosen && opts.indexOf(chosen) === -1) opts = [chosen].concat(opts);
      return '<label class="tf-date"><span>' + (side === 'from' ? 'Desde' : 'Hasta') + '</span>'
        + '<select class="tf-input tf-input--date" data-f="' + col.key + '-' + side + '"'
        + ' aria-label="' + _esc(col.label) + ' ' + (side === 'from' ? 'desde' : 'hasta') + '">'
        + '<option value="">Sin l\u00edmite</option>'
        + opts.map(function (v) {
            return '<option value="' + _esc(v) + '"' + (v === chosen ? ' selected' : '') + '>'
              + _esc(_stampLabel(v)) + '</option>';
          }).join('')
        + '</select></label>';
    };
    return '<span class="tf-dates">'
      + _dateSel('from', f[col.key].to)
      + _dateSel('to', f[col.key].from)
      + '</span>';
  }

  function _buildHead() {
    var titles = COLUMNS.map(function (c) {
      return '<th data-col="' + c.key + '" aria-sort="none"><button type="button" class="th-sort"'
        + ' data-sort="' + c.key + '" title="Ordenar">' + _esc(c.label)
        + '<span class="th-arrow" aria-hidden="true"></span></button></th>';
    }).join('');
    var filters = COLUMNS.map(_filterCell).join('');
    _opts.head.innerHTML = '<tr class="th-row">' + titles + '</tr><tr class="tf-row">' + filters + '</tr>';
    _headBuilt = true;
  }

  /** Re-render only the controls whose option list depends on the data. */
  function _refreshValueChips() {
    ['tipos', 'estados'].forEach(function (field) {
      var slot = _opts.head.querySelector('[data-slot="' + field + '"]');
      if (slot) slot.innerHTML = _optionChips(field, _valueOptions[field], _state.filters[field]);
    });
    // The date <select>s are rebuilt from the same rows, so a group change
    // must re-offer only the timestamps still present in the visible data.
    ['inicio', 'fin'].forEach(function (key) {
      var cell = _opts.head.querySelector('td[data-col="' + key + '"]');
      if (!cell) return;
      var col = { key: key, filter: 'date', label: key === 'inicio' ? 'Inicio Impl' : 'Fin Impl' };
      var reset = cell.querySelector('.tf-reset');
      cell.querySelector('.tf-cell').innerHTML = _dateFilterBody(col) + (reset ? reset.outerHTML : '');
    });
  }

  function _filterActiveFor(key) {
    var f = _state.filters;
    switch (key) {
      case 'resp': case 'ticket': case 'app': return !!f[key];
      case 'pool': return f.pools.length > 0;
      case 'tipo': return f.tipos.length > 0;
      case 'estado': return f.estados.length > 0;
      case 'inicio': case 'fin': return !!(f[key].from || f[key].to);
      default: return false;
    }
  }

  /** Sync pressed chips, reset buttons and sort arrows with the state. */
  function _syncControls() {
    var f = _state.filters;
    var chips = _opts.head.querySelectorAll('.tf-chip');
    for (var i = 0; i < chips.length; i++) {
      var field = chips[i].getAttribute('data-f');
      var on = f[field].indexOf(chips[i].getAttribute('data-v')) !== -1;
      chips[i].setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    COLUMNS.forEach(function (c) {
      var rb = _opts.head.querySelector('[data-reset="' + c.key + '"]');
      if (rb) rb.hidden = !_filterActiveFor(c.key);
      var th = _opts.head.querySelector('th[data-col="' + c.key + '"]');
      if (th) {
        var active = _state.sort.key === c.key;
        th.setAttribute('aria-sort', active ? (_state.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none');
        th.querySelector('.th-arrow').textContent = active ? (_state.sort.dir === 'asc' ? ' \u25B2' : ' \u25BC') : '';
      }
    });
  }

  function _resetColumn(key) {
    var f = _state.filters;
    switch (key) {
      case 'resp': case 'ticket': case 'app': f[key] = ''; break;
      case 'pool': f.pools = []; break;
      case 'tipo': f.tipos = []; break;
      case 'estado': f.estados = []; break;
      case 'inicio': case 'fin': f[key] = { from: '', to: '' }; break;
    }
    // Reflect text/date controls (chips are synced by _syncControls). Both
    // INPUT and SELECT carry [data-f]; a <select> reset returns to its
    // "Sin l\u00edmite" option, whose value is the empty string.
    var inputs = _opts.head.querySelectorAll('[data-f]');
    for (var i = 0; i < inputs.length; i++) {
      var name = inputs[i].getAttribute('data-f');
      if (name === key) inputs[i].value = '';
      if (name === key + '-from' || name === key + '-to') inputs[i].value = '';
    }
  }

  function _toggle(list, v) {
    var at = list.indexOf(v);
    if (at === -1) list.push(v); else list.splice(at, 1);
  }

  function _onHeadInput(e) {
    var t = e.target;
    var name = t.getAttribute && t.getAttribute('data-f');
    // Both text inputs and the date <select>s drive the filters.
    if (!name || (t.tagName !== 'INPUT' && t.tagName !== 'SELECT')) return;
    var f = _state.filters;
    var m = /^(inicio|fin)-(from|to)$/.exec(name);
    // A <select> only offers real source timestamps; "" means "Sin l\u00edmite".
    if (m) f[m[1]][m[2]] = t.value || '';
    else f[name] = t.value;
    _render();
  }

  function _onHeadClick(e) {
    var el = e.target.closest ? e.target.closest('button') : null;
    if (!el) return;
    if (el.hasAttribute('data-sort')) {
      var key = el.getAttribute('data-sort');
      if (_state.sort.key === key) _state.sort.dir = _state.sort.dir === 'asc' ? 'desc' : 'asc';
      else _state.sort = { key: key, dir: 'asc' };
    } else if (el.classList.contains('tf-chip')) {
      _toggle(_state.filters[el.getAttribute('data-f')], el.getAttribute('data-v'));
    } else if (el.hasAttribute('data-reset')) {
      _resetColumn(el.getAttribute('data-reset'));
    } else {
      return;
    }
    _render();
  }

  function _clearAll() {
    _state.filters = _blankFilters();
    // Every filter control, text input or date <select>, returns to its
    // empty value ("Sin l\u00edmite" for the date selects).
    var controls = _opts.head.querySelectorAll('[data-f]');
    for (var i = 0; i < controls.length; i++) {
      if (controls[i].tagName === 'INPUT' || controls[i].tagName === 'SELECT') controls[i].value = '';
    }
    _render();
  }

  /* ---- toolbar ---- */
  function _buildToolbar() {
    if (!_opts.toolbar) return;
    _opts.toolbar.innerHTML =
      '<span class="tb-mode" id="tb-mode"></span>'
      + '<span class="tb-count" id="tb-count" aria-live="polite"></span>'
      + '<span class="tb-spacer"></span>'
      + '<button type="button" class="tb-btn tb-btn--ghost" id="tb-clear" hidden>Limpiar filtros</button>'
      + '<button type="button" class="tb-btn" id="tb-toggle"></button>';
    _opts.toolbar.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button') : null;
      if (!b) return;
      if (b.id === 'tb-toggle') {
        _state.mode = _state.mode === 'next' ? 'all' : 'next';   // filters and sort are untouched
        _render();
      } else if (b.id === 'tb-clear') {
        _clearAll();
      }
    });
  }

  function _renderToolbar(shown, eff) {
    if (!_opts.toolbar) return;
    var modeEl = document.getElementById('tb-mode');
    var countEl = document.getElementById('tb-count');
    var toggle = document.getElementById('tb-toggle');
    var clear = document.getElementById('tb-clear');
    if (!modeEl) return;
    if (eff.mode === 'next') {
      modeEl.textContent = 'Pr\u00F3xima hora (' + _hhmm(_ref.getTime()) + ' \u2013 '
        + _hhmm(_ref.getTime() + WINDOW_MIN * 60000) + ')';
      toggle.textContent = 'Ver todos los registros';
    } else {
      modeEl.textContent = 'Todos los registros';
      toggle.textContent = 'Mostrar pr\u00F3ximos 60 min';
    }
    toggle.hidden = !_canWindow();
    countEl.textContent = shown + ' de ' + _items.length + ' registros';
    clear.hidden = !filtersActive(_state.filters);
  }

  /* ---- body ---- */
  function _rowHtml(it) {
    var r = it.raw;
    return '<tr data-ticket="' + _esc(r.ticket) + '" data-pool="' + _esc(it.poolId) + '">'
      + '<td>' + (_esc(r.responsable) || '\u2014') + '</td>'
      + '<td title="' + _esc(r.pool || 'Sin pool') + '">' + _poolChip(r.pool) + '</td>'
      + '<td>' + _esc(r.type) + '</td>'
      + '<td><a class="row-link" href="' + _opts.jiraUrl(r.ticket) + '"'
      +   ' target="_blank" rel="noopener noreferrer"'
      +   ' title="Abrir ' + _esc(r.ticket) + ' en JIRA">'
      +   _esc(r.ticket) + '<span class="action-card__ext" aria-hidden="true">\u2197</span></a></td>'
      + '<td>' + _esc(r.nombre_app) + '</td>'
      + '<td><span class="badge ' + _statusClass(r.status) + '">' + _esc(r.status) + '</span></td>'
      + '<td>' + _esc(r.inicio_impl) + '</td>'
      + '<td>' + _esc(r.fin_impl) + '</td>'
      + '</tr>';
  }

  function _emptyHtml(eff) {
    if (_items.length === 0) {
      return '<tr class="table-empty"><td colspan="8">'
        + (_group ? 'Sin pases activos para el pool ' + _esc(_group.label) + '.' : 'Sin pases activos.')
        + '</td></tr>';
    }
    var msg, actions = '';
    if (eff.mode === 'next') {
      msg = filtersActive(_state.filters)
        ? 'No hay pases de la pr\u00F3xima hora con los filtros aplicados.'
        : 'No hay pases programados para los pr\u00F3ximos 60 minutos.';
      actions = '<button type="button" class="tb-btn" data-act="all">Ver todos los registros</button>';
    } else {
      msg = 'Ning\u00FAn registro coincide con los filtros.';
    }
    if (filtersActive(_state.filters)) {
      actions += ' <button type="button" class="tb-btn tb-btn--ghost" data-act="clear">Limpiar filtros</button>';
    }
    return '<tr class="table-empty"><td colspan="8">' + msg + ' ' + actions + '</td></tr>';
  }

  function _render() {
    if (!_opts || !_headBuilt) return;
    var eff = _effectiveState();
    var rows = project(_items, eff, _ref);
    _opts.body.innerHTML = rows.length ? rows.map(_rowHtml).join('') : _emptyHtml(eff);
    _syncControls();
    _renderToolbar(rows.length, eff);
  }

  /* ---- public ---- */
  function init(opts) {
    _opts = opts;
    _buildToolbar();
    _opts.head.addEventListener('click', _onHeadClick);
    _opts.head.addEventListener('input', _onHeadInput);
    _opts.head.addEventListener('change', _onHeadInput);
    _opts.body.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('button[data-act]') : null;
      if (!b) return;
      if (b.getAttribute('data-act') === 'all') _state.mode = 'all';
      else if (b.getAttribute('data-act') === 'clear') { _clearAll(); return; }
      _render();
    });
  }

  /** Replace the dataset (group change); filters, sort and mode are kept. */
  function setRows(rows, meta, group) {
    if (!_opts) return;
    _ref = refFromMeta(meta);
    _group = group || null;
    _items = enrich(rows, _ref);
    function distinct(pick) {
      var seen = {}, out = [];
      _items.forEach(function (it) {
        var v = pick(it.raw);
        if (v && !seen[v]) { seen[v] = true; out.push(v); }
      });
      return out;
    }
    _valueOptions = {
      tipos: distinct(function (r) { return r.type; }),
      estados: distinct(function (r) { return r.status; }),
    };
    if (!_headBuilt) _buildHead(); else _refreshValueChips();
    _render();
  }

  return {
    init: init,
    setRows: setRows,
    // Pure pipeline, exposed for tests.
    _pure: {
      parseRowDate: parseRowDate, refFromMeta: refFromMeta, enrich: enrich,
      applyFilters: applyFilters, overlapsWindow: overlapsWindow,
      sortItems: sortItems, project: project, blankFilters: _blankFilters,
      dateOptions: dateOptions,
    },
  };
})();
