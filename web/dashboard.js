/**
 * ChangeOps Console — Dashboard Controller
 * Phase 2.5: Contract Freeze + ADR-004
 *
 * Data source: Data Contract v1 (meta, kpis, timeline, table)
 * No knowledge of Excel, Python, or MockOperations.
 *
 * Contract validation runs on init. If the contract is invalid,
 * an error is logged and the dashboard does not render.
 */

(function () {
  'use strict';

  /* =========================================================
     STORAGE — safe wrappers (hotfix v1.1, SharePoint sandbox)
     ---------------------------------------------------------
     In a sandboxed frame without `allow-same-origin` (the SharePoint
     viewer renders the file at about:srcdoc), ANY access to
     window.localStorage throws a SecurityError. These wrappers keep
     the dashboard running:
       - reads fall back to null,
       - writes are ignored,
       - and the theme falls back to the default (dark).
     ========================================================= */
  var THEME_KEY = 'changeops-theme';
  var DEFAULT_THEME = 'dark';

  var _storageAvailable = null; // tri-state: null = unknown, true, false

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch (e) {
      return false;
    }
  }

  function isStorageAvailable() {
    if (_storageAvailable !== null) return _storageAvailable;
    try {
      var probe = '__changeops_probe__';
      window.localStorage.setItem(probe, '1');
      window.localStorage.removeItem(probe);
      _storageAvailable = true;
    } catch (e) {
      _storageAvailable = false;
    }
    return _storageAvailable;
  }

  function getPreferredTheme() {
    var stored = storageGet(THEME_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
    // If storage is unavailable (sandboxed), use the default theme.
    if (!isStorageAvailable()) return DEFAULT_THEME;
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    var btn = document.getElementById('theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
  }

  function initTheme() {
    applyTheme(getPreferredTheme());

    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        storageSet(THEME_KEY, next);
      });
    }
  }

  /* =========================================================
     SYNC INDICATOR — shows data freshness
     ========================================================= */
  function updateSyncIndicator() {
    var indicatorEl = document.getElementById('sync-indicator');
    var textEl = document.getElementById('last-update');
    if (!indicatorEl || !textEl || !DATA) return;

    var lastUpdate = new Date(DATA.meta.updatedAt);
    var diffMin = (Date.now() - lastUpdate.getTime()) / 60000;
    var isStale = diffMin > 15;

    // Update icon
    indicatorEl.className = 'sync-indicator';
    if (isStale) {
      indicatorEl.classList.add('sync-indicator--stale');
      indicatorEl.innerHTML = '<svg class="sync-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
    } else {
      indicatorEl.classList.add('sync-indicator--fresh');
      indicatorEl.innerHTML = '<svg class="sync-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>';
    }

    // Update text (keep existing format)
    textEl.textContent = 'Actualización: ' + DATA.meta.updatedAt;
  }

  /* =========================================================
     CONTRACT VALIDATOR — Data Contract v1
     ========================================================= */
  function validateContract(data) {
    var errors = [];

    if (!data || typeof data !== 'object') {
      return ['Contract is not an object'];
    }

    // meta
    if (!data.meta) {
      errors.push('Missing required field: meta');
    } else {
      if (!data.meta.updatedAt) errors.push('Missing meta.updatedAt');
      if (!data.meta.windowStart) errors.push('Missing meta.windowStart');
      if (!data.meta.windowEnd) errors.push('Missing meta.windowEnd');
    }

    // kpis
    if (!data.kpis) {
      errors.push('Missing required field: kpis');
    } else {
      if (typeof data.kpis.lateStarts !== 'number') errors.push('Missing kpis.lateStarts');
      if (typeof data.kpis.ratificationsSoon !== 'number') errors.push('Missing kpis.ratificationsSoon');
      if (typeof data.kpis.ratificationsExpired !== 'number') errors.push('Missing kpis.ratificationsExpired');
      if (typeof data.kpis.reversions !== 'number') errors.push('Missing kpis.reversions');
    }

    // timeline
    if (!data.timeline) {
      errors.push('Missing required field: timeline');
    } else if (!Array.isArray(data.timeline)) {
      errors.push('timeline must be an array');
    } else {
      data.timeline.forEach(function (group, gi) {
        if (!group.pool) errors.push('timeline[' + gi + '].pool is missing');
        if (!Array.isArray(group.bars)) {
          errors.push('timeline[' + gi + '].bars must be an array');
        } else {
          group.bars.forEach(function (bar, bi) {
            if (!bar.ticket) errors.push('timeline[' + gi + '].bars[' + bi + '].ticket is missing');
            if (typeof bar.start !== 'number') errors.push('timeline[' + gi + '].bars[' + bi + '].start must be a number (minutes)');
            if (typeof bar.duration !== 'number') errors.push('timeline[' + gi + '].bars[' + bi + '].duration must be a number (minutes)');
            if (!bar.status) errors.push('timeline[' + gi + '].bars[' + bi + '].status is missing');
          });
        }
      });
    }

    // table
    if (!data.table) {
      errors.push('Missing required field: table');
    } else if (!Array.isArray(data.table)) {
      errors.push('table must be an array');
    }

    return errors;
  }

  /* =========================================================
     DATA — Data Contract v1 + ChangeOpsActions (ADR-008)
     ========================================================= */
  var DATA = window.MockOperations ? window.MockOperations.data : null;
  var ACTIONS = window.ChangeOpsActions || null;

  // JIRA base — no ticket prefixes are hardcoded (ADR-008)
  var JIRA_BASE = 'https://bcp-ti.atlassian.net.mcas.ms/browse/';

  /* =========================================================
     KPI RENDER — v1.1 action model
     ========================================================= */
  function renderKPIs(kpis) {
    var set = function (id, val) {
      var el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    var hasActions = ACTIONS && Array.isArray(ACTIONS.passesInWindow);
    set('kpi-total', hasActions
      ? ACTIONS.passesInWindow.length
      : (kpis.lateStarts + kpis.ratificationsSoon + kpis.ratificationsExpired + kpis.reversions));
    set('kpi-atrasados', kpis.lateStarts);
    set('kpi-coordinados', kpis.ratificationsSoon);
    set('kpi-en-curso', kpis.ratificationsExpired);

    _applyKPILabels();
  }

  function _applyKPILabels() {
    var labels = {
      'total': 'Pases en ventana',
      'atrasados': 'Pases atrasados',
      'coordinados': 'Ratificaciones por vencer',
      'en-curso': 'Ratificaciones vencidas',
    };
    var section = document.getElementById('kpi-section');
    if (!section) return;
    Object.keys(labels).forEach(function (key) {
      var card = section.querySelector('.kpi-card[data-kpi="' + key + '"]');
      if (card) {
        var lbl = card.querySelector('.kpi-card__label');
        if (lbl) lbl.textContent = labels[key];
      }
    });
    // Reorder cards to the v1.1 action-model order
    ['total', 'atrasados', 'coordinados', 'en-curso'].forEach(function (key) {
      var card = section.querySelector('.kpi-card[data-kpi="' + key + '"]');
      if (card) section.appendChild(card);
    });
  }

  /* =========================================================
     KPI ACTIONS (v1.1)
     ========================================================= */
  function wireKPIClicks() {
    document.querySelectorAll('.kpi-card').forEach(function (card) {
      card.style.cursor = 'pointer';
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');

      var handler = function () { _onKPIClick(card.dataset.kpi); };
      card.addEventListener('click', handler);
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handler();
        }
      });
    });
  }

  function _onKPIClick(key) {
    var A = ACTIONS || {};
    if (key === 'total') {
      _scrollAndHighlightTimeline();                       // Pases en ventana
    } else if (key === 'atrasados') {
      openActionDrawer('Pases atrasados', A.lateStarts, 'lateStarts');
    } else if (key === 'coordinados') {
      openActionDrawer('Ratificaciones por vencer', A.ratificationsSoon, 'ratificationsSoon');
    } else if (key === 'en-curso') {
      openActionDrawer('Ratificaciones vencidas', A.ratificationsExpired, 'ratificationsExpired');
    }
  }

  function _scrollAndHighlightTimeline() {
    var section = document.getElementById('timeline-section') || document.getElementById('timeline');
    if (section && section.scrollIntoView) {
      try { section.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
      catch (e) { section.scrollIntoView(); }
    }
    var bars = document.querySelectorAll('.timeline__bar');
    bars.forEach(function (b) { b.classList.add('timeline__bar--flash'); });
    window.setTimeout(function () {
      bars.forEach(function (b) { b.classList.remove('timeline__bar--flash'); });
    }, 1000);
  }

  /* =========================================================
     ACTION DRAWER — reuses the existing right drawer (ADR-008)
     ========================================================= */
  function openActionDrawer(titleText, records, kind) {
    var drawer  = document.getElementById('drawer');
    var overlay = document.getElementById('drawer-overlay');
    var title   = document.getElementById('drawer-title');
    var body    = document.getElementById('drawer-body');
    if (!drawer) return;

    records = Array.isArray(records) ? records : [];
    title.textContent = titleText + ' (' + records.length + ')';
    body.innerHTML = records.length
      ? '<div class="action-list">'
        + records.map(function (r) { return _actionCard(r, kind); }).join('')
        + '</div>'
      : '<div class="action-empty">Sin registros</div>';

    // Drawer stays open; JIRA opens in a new tab (target=_blank).
    drawer.setAttribute('aria-hidden', 'false');
    overlay.classList.add('active');
  }

  function _actionCard(r, kind) {
    var rows = [['Nombre APP', _esc(r.app)]];

    if (kind === 'ratificationsSoon' || kind === 'ratificationsExpired') {
      rows.push(['FEC. HORA. INI. RATI', _esc(r.iniRati)]);
      rows.push(['FEC. HORA. FIN. RATI', _esc(r.finRati)]);
      if (kind === 'ratificationsExpired') {
        rows.push(['FEC. HORA. FIN. RATI. TOTAL', _esc(r.endRatiTotal)]);
      }
    } else {
      rows.push(['FEC. HORA. INI. IMPL', _esc(r.iniImpl)]);
      rows.push(['FEC. HORA. FIN. IMPL', _esc(r.finImpl)]);
    }
    rows.push(['Recurso asignado', _esc(r.resource)]);
    rows.push(['Estado actual', _esc(r.status)]);

    return '<article class="action-card">'
      + '<a class="action-card__ticket" href="' + _jiraUrl(r.ticket) + '"'
      + ' target="_blank" rel="noopener noreferrer"'
      + ' title="Abrir ' + _esc(r.ticket) + ' en JIRA">'
      + _esc(r.ticket)
      + '<span class="action-card__ext" aria-hidden="true">\u2197</span>'
      + '</a>'
      + '<dl class="action-card__fields">'
      + rows.map(function (pair) {
          return '<dt>' + pair[0] + '</dt><dd>' + (pair[1] || '\u2014') + '</dd>';
        }).join('')
      + '</dl>'
      + '</article>';
  }

  function _jiraUrl(ticket) {
    return JIRA_BASE + encodeURIComponent(String(ticket || '').trim());
  }

  function _esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* =========================================================
     v1.1 STYLES — injected here to keep the build self-contained
     ========================================================= */
  function _injectStyles() {
    if (document.getElementById('changeops-v11-styles')) return;
    var css = ''
      + '.timeline__bar--flash{outline:3px solid var(--color-warning);outline-offset:1px;'
      + 'animation:co-flash .5s ease 2;}'
      + '@keyframes co-flash{0%,100%{filter:brightness(1)}50%{filter:brightness(1.4)}}'
      + '.action-list{display:flex;flex-direction:column;gap:10px;}'
      + '.action-card{border:1px solid var(--border-color);border-radius:8px;padding:10px 12px;'
      + 'background:var(--bg-surface-alt);}'
      + '.action-card__ticket{display:inline-flex;align-items:center;gap:6px;font-weight:700;'
      + 'color:var(--color-success);text-decoration:none;cursor:pointer;}'
      + '.action-card__ticket:hover{text-decoration:underline;}'
      + '.action-card__ext{font-size:12px;}'
      + '.action-card__fields{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:8px 0 0;'
      + 'font-size:12px;}'
      + '.action-card__fields dt{color:var(--text-secondary);font-weight:600;}'
      + '.action-card__fields dd{margin:0;word-break:break-word;}'
      + '.action-empty{color:var(--text-muted);font-size:13px;padding:16px 0;}'
      + '.badge--neutral{background:var(--bg-hover);color:var(--text-secondary);}'
      + '.drawer__link{display:inline-flex;align-items:center;gap:6px;font-weight:700;'
      + 'color:var(--color-success);text-decoration:none;cursor:pointer;}'
      + '.drawer__link:hover{text-decoration:underline;}'
      + '.row-link{display:inline-flex;align-items:center;gap:4px;font-weight:600;'
      + 'color:var(--color-success);text-decoration:none;cursor:pointer;}'
      + '.row-link:hover{text-decoration:underline;}';
    var style = document.createElement('style');
    style.id = 'changeops-v11-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* =========================================================
     TABLE RENDER — Data Contract v1 format
     ========================================================= */
  function renderTable(rows) {
    var thead = document.getElementById('table-head');
    var tbody = document.getElementById('table-body');
    if (!thead || !tbody) return;

    thead.innerHTML = '<tr>'
      + '<th>RECURSO ASIGNADO</th>'
      + '<th>Pool</th>'
      + '<th>Tipo</th>'
      + '<th>Ticket</th>'
      + '<th>NOMBRE APP</th>'
      + '<th>Estado Actual</th>'
      + '<th>Inicio Impl</th>'
      + '<th>Fin Impl</th>'
      + '</tr>';

    tbody.innerHTML = rows.map(function (r) {
      var poolClass = r.pool === 'Legacy' ? 'badge--legacy' : 'badge--yape';
      var statusClass = r.status === 'Coordinado' ? 'badge--coordinado'
        : r.status === 'Pase en curso' ? 'badge--pase-en-curso'
        : r.status === 'Inicio atrasado' ? 'badge--inicio-atrasado'
        : 'badge--neutral';
      return '<tr data-ticket="' + _esc(r.ticket) + '">'
        + '<td>' + (_esc(r.responsable) || '\u2014') + '</td>'
        + '<td><span class="badge ' + poolClass + '">' + _esc(r.pool) + '</span></td>'
        + '<td>' + _esc(r.type) + '</td>'
        + '<td><a class="row-link" href="' + _jiraUrl(r.ticket) + '"'
        +   ' target="_blank" rel="noopener noreferrer"'
        +   ' title="Abrir ' + _esc(r.ticket) + ' en JIRA">'
        +   _esc(r.ticket) + '<span class="action-card__ext" aria-hidden="true">\u2197</span></a></td>'
        + '<td>' + _esc(r.nombre_app) + '</td>'
        + '<td><span class="badge ' + statusClass + '">' + _esc(r.status) + '</span></td>'
        + '<td>' + _esc(r.inicio_impl) + '</td>'
        + '<td>' + _esc(r.fin_impl) + '</td>'
        + '</tr>';
    }).join('');
  }

  /* =========================================================
     DRAWER — bar detail (v1.1.4: full fields + JIRA ticket)
     ========================================================= */
  var _tableIndex = {};

  function _buildTableIndex() {
    _tableIndex = {};
    if (!DATA || !Array.isArray(DATA.table)) return;
    DATA.table.forEach(function (r) {
      if (r && r.ticket) _tableIndex[r.ticket] = r;
    });
  }

  function _lookupTicket(ticket) {
    return _tableIndex[ticket] || null;
  }

  function openDrawer(barData) {
    var drawer  = document.getElementById('drawer');
    var overlay = document.getElementById('drawer-overlay');
    var title   = document.getElementById('drawer-title');
    var body    = document.getElementById('drawer-body');

    if (!drawer || !barData) return;

    // Enrich from the operational table (pool / NOMBRE APP / Estado Actual).
    var idx = _lookupTicket(barData.ticket) || {};
    var appName = barData.name || idx.name || '';
    var pool = barData.pool || idx.pool || '';          // real pool (Legacy/Yape)
    var estadoActual = idx.status || barData.status || '';
    var recurso = barData.responsable || '';            // RECURSO ASIGNADO (v1.1.5)

    var typeLabel = barData.type === 'implementacion' ? 'Implementación' : 'Derivado';
    var startTime = _fmtDateHHMM(barData.start);
    var endTime = _fmtDateHHMM(barData.start + barData.duration);

    title.textContent = barData.ticket;
    body.innerHTML = '<dl class="drawer__detail">'
      + '<dt>Ticket</dt><dd>'
      +   '<a class="drawer__link" href="' + _jiraUrl(barData.ticket) + '"'
      +   ' target="_blank" rel="noopener noreferrer">'
      +   _esc(barData.ticket) + '<span class="action-card__ext" aria-hidden="true">\u2197</span></a></dd>'
      + '<dt>Nombre APP</dt><dd>' + (_esc(appName) || '\u2014') + '</dd>'
      + '<dt>Pool</dt><dd>'
      +   (pool ? '<span class="badge badge--' + _poolKey(pool) + '">' + _esc(pool) + '</span>' : '\u2014')
      +   '</dd>'
      + '<dt>Tipo</dt><dd>' + typeLabel + '</dd>'
      + '<dt>Estado Actual</dt><dd>' + _estadoBadge(estadoActual) + '</dd>'
      + '<dt>Recurso asignado</dt><dd>' + (_esc(recurso) || '\u2014') + '</dd>'
      + '<dt>Inicio</dt><dd>' + startTime + '</dd>'
      + '<dt>Fin</dt><dd>' + endTime + '</dd>'
      + '</dl>';

    drawer.setAttribute('aria-hidden', 'false');
    overlay.classList.add('active');
  }

  function _estadoBadge(estado) {
    var e = String(estado || '').trim();
    var cls = e === 'Coordinado' ? 'badge--coordinado'
      : e === 'Pase en curso' ? 'badge--pase-en-curso'
      : e === 'Inicio atrasado' ? 'badge--inicio-atrasado'
      : 'badge--neutral';
    return '<span class="badge ' + cls + '">' + (_esc(e) || '\u2014') + '</span>';
  }

  function closeDrawer() {
    var drawer  = document.getElementById('drawer');
    var overlay = document.getElementById('drawer-overlay');
    if (drawer) drawer.setAttribute('aria-hidden', 'true');
    if (overlay) overlay.classList.remove('active');
  }

  function _statusBadge(status) {
    var cls = status === 'coordinado' ? 'badge--coordinado'
      : status === 'pase-en-curso' ? 'badge--pase-en-curso'
      : 'badge--inicio-atrasado';
    var label = status.replace(/-/g, ' ');
    return '<span class="badge ' + cls + '">' + label + '</span>';
  }

  /** ADR-004: Convert minutes from window start to HH:MM display. */
  function _minToHHMM(min) {
    // Parse windowStart from contract
    var startParts = DATA.meta.windowStart.split(':');
    var startHour = parseInt(startParts[0], 10);
    var startMin = parseInt(startParts[1], 10);

    var totalMin = startHour * 60 + startMin + min;
    var hours = Math.floor(totalMin / 60) % 24;
    var mins = totalMin % 60;
    return _pad(hours) + ':' + _pad(mins);
  }

  /**
   * v1.1.7: render minutes-from-window-start as "DD/MM HH:MM" (same format as
   * the table). The window start datetime = date(meta.updatedAt) + meta.windowStart.
   * Day-aware, so bars on other dates get the right calendar day.
   */
  function _fmtDateHHMM(min) {
    var ws = DATA.meta.windowStart.split(':');
    var abs = parseInt(ws[0], 10) * 60 + parseInt(ws[1], 10) + min;

    var dayOffset = Math.floor(abs / 1440);
    var mod = ((abs % 1440) + 1440) % 1440;

    var m = /(\d{4})-(\d{2})-(\d{2})/.exec(DATA.meta.updatedAt);
    var y = m ? parseInt(m[1], 10) : 2026;
    var mo = m ? parseInt(m[2], 10) : 1;
    var d = m ? parseInt(m[3], 10) : 1;
    var dt = new Date(y, mo - 1, d + dayOffset);

    var dd = String(dt.getDate()).padStart(2, '0');
    var mm = String(dt.getMonth() + 1).padStart(2, '0');
    var hh = String(Math.floor(mod / 60)).padStart(2, '0');
    var mi = String(mod % 60).padStart(2, '0');
    return dd + '/' + mm + ' ' + hh + ':' + mi;
  }

  function _poolKey(pool) {
    return pool.toLowerCase();
  }

  function _pad(n) {
    return String(n).padStart(2, '0');
  }

  /* =========================================================
     INIT
     ========================================================= */
  function init() {
    initTheme();
    _injectStyles();

    if (!DATA) {
      console.error('[ChangeOps] MockOperations not loaded');
      return;
    }

    // Validate contract
    var errors = validateContract(DATA);
    if (errors.length > 0) {
      console.error('[ChangeOps] Invalid Data Contract:');
      errors.forEach(function (e) { console.error('  - ' + e); });
      return;
    }

    console.log('[ChangeOps] Data Contract v1 validated ✓');

    // Sync indicator
    updateSyncIndicator();

    // KPIs
    renderKPIs(DATA.kpis);
    wireKPIClicks();

    // Timeline — pass openDrawer as click callback
    var container = document.getElementById('timeline');
    window.Timeline.init(container, DATA, openDrawer);

    // Table + lookup index (for the drawer enrichment)
    renderTable(DATA.table);
    _buildTableIndex();

    // Drawer close handlers
    var closeBtn = document.getElementById('drawer-close');
    var overlayEl = document.getElementById('drawer-overlay');
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (overlayEl) overlayEl.addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDrawer();
    });
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
