"""Table: pool catalog, next-60-min window, per-column filters, sorting."""
import json, re, shutil, subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent

PROBE = r'''
const fs=require('fs'), vm=require('vm');
const sb={console,Math,JSON,Date,parseInt,isNaN,String,Object,Array,RegExp,Number};
sb.window=sb;
sb.document={createElement(){const e={};Object.defineProperty(e,'textContent',{set(v){this.innerHTML=String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}});return e;},
  getElementById(){return null;},querySelectorAll(){return {forEach(){}};},addEventListener(){},documentElement:{},head:{},readyState:'complete'};
sb.getComputedStyle=()=>({getPropertyValue:()=>''});
vm.createContext(sb);
for (const f of process.argv.slice(2)) vm.runInContext(fs.readFileSync(f,'utf8'), sb);
const T=sb.window.Timeline, P=sb.window.OpsTable._pure;
const ref=P.refFromMeta({updatedAt:'2026-10-19T19:15:00'});
const rows=[
 {responsable:'Ana',pool:'AgileOps Prod',type:'Implementaci\u00f3n',ticket:'OCD-1',nombre_app:'DWLI',status:'Coordinado',inicio_impl:'19/10 16:00',fin_impl:'19/10 20:00'}, // running, overlaps
 {responsable:'Beto',pool:'S&F',type:'Derivado',ticket:'OCD-2',nombre_app:'MBBK',status:'Inicio atrasado',inicio_impl:'19/10 20:00',fin_impl:'19/10 21:00'}, // starts inside window
 {responsable:'Cesar',pool:'Yape',type:'Implementaci\u00f3n',ticket:'OCD-3',nombre_app:'SFCA',status:'Coordinado',inicio_impl:'19/10 18:00',fin_impl:'19/10 19:15'}, // ends exactly at window start
 {responsable:'Dino',pool:'AgileOps ORO',type:'Implementaci\u00f3n',ticket:'OCD-4',nombre_app:'ALMR',status:'Coordinado',inicio_impl:'19/10 20:15',fin_impl:'19/10 22:00'}, // starts exactly at window end
 {responsable:'Eva',pool:'',type:'Implementaci\u00f3n',ticket:'OCD-5',nombre_app:'X',status:'Coordinado',inicio_impl:'bad',fin_impl:'19/10 22:00'}, // invalid date, no pool
 {responsable:'Fer',pool:'Pool AgileOps Prod',type:'Implementaci\u00f3n',ticket:'OCD-6',nombre_app:'Y',status:'Coordinado',inicio_impl:'09/11 01:00',fin_impl:'09/11 02:00'},
];
const items=P.enrich(rows,ref);
const st=(o)=>Object.assign({mode:'next',filters:P.blankFilters(),sort:{key:'inicio',dir:'asc'}},o||{});
const tk=(a)=>a.map(i=>i.raw.ticket);
const f=(m)=>Object.assign(P.blankFilters(),m);
const out={
 pools: items.map(i=>i.poolId),
 info_alias: T.poolInfo('Pool AgileOps Prod').id, info_none: T.poolInfo('').id, info_unknown: T.poolInfo('Foo').known,
 next: tk(P.project(items,st(),ref)),
 all: tk(P.project(items,st({mode:'all'}),ref)),
 fPool: tk(P.project(items,st({mode:'all',filters:f({pools:['agileops-prod']})}),ref)),
 fNone: tk(P.project(items,st({mode:'all',filters:f({pools:['sin-pool']})}),ref)),
 fTipo: tk(P.project(items,st({mode:'all',filters:f({tipos:['Derivado']})}),ref)),
 fEstado: tk(P.project(items,st({mode:'all',filters:f({estados:['Inicio atrasado']})}),ref)),
 fResp: tk(P.project(items,st({mode:'all',filters:f({resp:'dIN'})}),ref)),
 fTicket: tk(P.project(items,st({mode:'all',filters:f({ticket:'ocd-3'})}),ref)),
 fApp: tk(P.project(items,st({mode:'all',filters:f({app:'mb'})}),ref)),
 fIni: tk(P.project(items,st({mode:'all',filters:f({inicio:{from:'2026-10-19T19:00',to:'2026-10-19T20:00'}})}),ref)),
 combo: tk(P.project(items,st({mode:'all',filters:f({pools:['agileops-prod','sf'],estados:['Coordinado']})}),ref)),
 comboNext: tk(P.project(items,st({mode:'next',filters:f({pools:['sf']})}),ref)),
 sortDesc: tk(P.project(items,st({mode:'all',sort:{key:'inicio',dir:'desc'}}),ref)),
 sortFin: tk(P.project(items,st({mode:'all',sort:{key:'fin',dir:'asc'}}),ref)),
  yearWrap: new Date(P.parseRowDate('02/01 10:00',P.refFromMeta({updatedAt:'2026-12-31T23:00:00'}))).getFullYear(),
  badDate: [P.parseRowDate('31/02 10:00',ref),P.parseRowDate('x',ref)].map(Number.isNaN),
  dIni: P.dateOptions(items,'inicio'),
  dFin: P.dateOptions(items,'fin'),
  dIniNoSf: P.dateOptions(items.filter(i=>i.poolId!=='sf'),'inicio'),
  dAfter: P.dateOptions(items,'inicio',{from:'2026-10-19T20:00'}),
  dBefore: P.dateOptions(items,'fin',{to:'2026-10-19T21:00'}),
  dEmpty: P.dateOptions([], 'inicio'),
  dBadOnly: P.dateOptions(P.enrich(rows.filter(r=>r.inicio_impl==='bad'),ref),'inicio'),
};
console.log(JSON.stringify(out));
'''

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_table_pipeline(tmp_path):
    probe = tmp_path / "probe.js"
    probe.write_text(PROBE, encoding="utf-8")
    out = subprocess.run(
        ["node", str(probe), str(ROOT / "web/components/timeline/timeline.js"),
         str(ROOT / "web/components/table/table.js")],
        capture_output=True, text=True, check=True, encoding="utf-8")
    d = json.loads(out.stdout)
    assert d["pools"] == ["agileops-prod", "sf", "yape", "agileops-oro", "sin-pool", "agileops-prod"]
    assert d["info_alias"] == "agileops-prod" and d["info_none"] == "sin-pool" and d["info_unknown"] is False
    # window [19:15, 20:15): running + starting inside; ended-at-start and starts-at-end excluded; bad date excluded
    assert d["next"] == ["OCD-1", "OCD-2"]
    # full list recovers everything; unknown/late dates sorted last, chronological otherwise
    assert d["all"] == ["OCD-1", "OCD-3", "OCD-2", "OCD-4", "OCD-6", "OCD-5"]
    assert d["fPool"] == ["OCD-1", "OCD-6"] and d["fNone"] == ["OCD-5"]
    assert d["fTipo"] == ["OCD-2"] and d["fEstado"] == ["OCD-2"]
    assert d["fResp"] == ["OCD-4"] and d["fTicket"] == ["OCD-3"] and d["fApp"] == ["OCD-2"]
    assert d["fIni"] == ["OCD-2"]                           # only OCD-2 starts in 19:00-20:00
    assert d["combo"] == ["OCD-1", "OCD-6"]
    assert d["comboNext"] == ["OCD-2"]                      # filters survive the mode change
    assert d["sortDesc"] == ["OCD-6", "OCD-4", "OCD-2", "OCD-3", "OCD-1", "OCD-5"]   # chronological, not lexicographic
    assert d["sortFin"] == ["OCD-3", "OCD-1", "OCD-2", "OCD-4", "OCD-5", "OCD-6"]
    assert d["yearWrap"] == 2027
    assert d["badDate"] == [True, True]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_date_filter_offers_only_source_dates(tmp_path):
    """INICIO/FIN filters must offer ONLY the timestamps that exist in the data
    (a <select>, not free typing), in chronological order, derived from the
    visible rows and narrowed by the opposite bound of the range."""
    probe = tmp_path / "probe.js"
    probe.write_text(PROBE, encoding="utf-8")
    out = subprocess.run(
        ["node", str(probe), str(ROOT / "web/components/timeline/timeline.js"),
         str(ROOT / "web/components/table/table.js")],
        capture_output=True, text=True, check=True, encoding="utf-8")
    d = json.loads(out.stdout)

    # Only real source values, chronological (20:00 before 20:15, not lexicographic)
    assert d["dIni"] == ["2026-10-19T16:00", "2026-10-19T18:00",
                         "2026-10-19T20:00", "2026-10-19T20:15",
                         "2026-11-09T01:00"]           # OCD-6, three weeks out
    # FIN offers its OWN column's values, not INICIO's
    assert d["dFin"] == ["2026-10-19T19:15", "2026-10-19T20:00",
                         "2026-10-19T21:00", "2026-10-19T22:00",
                         "2026-11-09T02:00"]           # OCD-6

    # Unparseable dates ("bad") are never invented into the catalogue
    assert d["dBadOnly"] == []

    # Options follow the visible rows: without S&F, its 20:00 start is gone
    # (2026-10-19T20:00 belonged to OCD-2 alone), while OCD-4 keeps 20:15.
    assert "2026-10-19T20:00" in d["dIni"]
    assert "2026-10-19T20:00" not in d["dIniNoSf"]
    assert "2026-10-19T20:15" in d["dIniNoSf"]
    # ...but OCD-2 (S&F) also owns the 20:00 FIN shared with OCD-4 (ORO)
    assert "2026-10-19T20:00" in d["dFin"]

    # A bound narrows the opposite side: nothing earlier than 20:00 is offered.
    # (2026-11-09T01:00 is OCD-6, legitimately after the bound, so it stays.)
    assert d["dAfter"][0] == "2026-10-19T20:00"
    assert "2026-10-19T18:00" not in d["dAfter"] and "2026-10-19T16:00" not in d["dAfter"]
    assert "2026-10-19T20:15" in d["dAfter"]
    # ...and the reverse: a FIN "hasta" of 21:00 leaves every earlier FIN
    # available for "desde", and drops the later ones (22:00, OCD-6's 02:00).
    assert d["dBefore"][0] == "2026-10-19T19:15"
    assert d["dBefore"][-1] == "2026-10-19T21:00"
    assert "2026-10-19T22:00" not in d["dBefore"] and "2026-11-09T02:00" not in d["dBefore"]
    assert d["dEmpty"] == []


def _css_block(css, selector):
    """Declarations of the first rule whose selector IS exactly `selector`.

    Walk the stylesheet one rule at a time with a brace-depth counter instead
    of splitting on '}': a CSS comment may itself contain '}' (e.g.
    "~130px } ~135px"), which would truncate the rule that follows it.
    Comments are stripped first; selectors are split on ',' so `.tf-date` is
    not confused with the combined `.tf-chips, .tf-dates` rule.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    target = selector.strip()
    pos, n = 0, len(css)
    while pos < n:
        open_at = css.find("{", pos)
        if open_at == -1:
            return []
        depth, end = 1, open_at + 1
        while end < n and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        head, body = css[pos:open_at], css[open_at + 1:end - 1]
        if target in {s.strip() for s in head.split(",")}:
            return [d.strip() for d in body.split(";") if d.strip()]
        pos = end
    return []


def test_date_filter_cell_fits_the_column():
    """The datetime field must not overflow its ~135px column (it needs the
    full cell width, so its label stacks above instead of beside it), and the
    reset button must keep its slot when hidden or the filter row reflows."""
    css = (ROOT / "web/theme.css").read_text(encoding="utf-8")
    date_input = _css_block(css, ".tf-input--date")
    assert "min-width: 0" in date_input, "date input must be allowed to shrink to the column"
    label = _css_block(css, ".tf-date")
    assert "flex-direction: column" in label, "label sits above the input, not beside it"
    reset = _css_block(css, ".tf-reset[hidden]")
    assert any(d.startswith("visibility: hidden") for d in reset), \
        "hidden reset must stay in layout (display:none makes the row reflow)"


SOURCE = ROOT / "workspace" / "output" / "dashboard_data.json"

# Same harness as PROBE, but the rows come from the generated contract file
# (argv[4]) instead of a hand-written fixture.
SOURCE_PROBE = r'''
const fs=require('fs'), vm=require('vm');
const sb={console,Math,JSON,Date,parseInt,isNaN,String,Object,Array,RegExp,Number};
sb.window=sb;
sb.document={createElement(){const e={};Object.defineProperty(e,'textContent',{set(v){this.innerHTML=String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}});return e;},
  getElementById(){return null;},querySelectorAll(){return {forEach(){}};},addEventListener(){},documentElement:{},head:{},readyState:'complete'};
sb.getComputedStyle=()=>({getPropertyValue:()=>''});
vm.createContext(sb);
for (const f of process.argv.slice(2,4)) vm.runInContext(fs.readFileSync(f,'utf8'), sb);
const P=sb.window.OpsTable._pure;
const data=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
const ref=P.refFromMeta(data.meta);
const items=P.enrich(data.table, ref);
console.log(JSON.stringify({ini:P.dateOptions(items,'inicio'), fin:P.dateOptions(items,'fin')}));
'''


def _stamp(ddmm_hhmm):
    """'20/10 15:00' -> '2026-10-20T15:00'. The contract carries no year, so
    the fixture year is pinned here; the run clock supplies it at runtime."""
    day, mon = ddmm_hhmm[0:2], ddmm_hhmm[3:5]
    return f"2026-{mon}-{day}T{ddmm_hhmm[6:]}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_date_filters_match_the_source_file(tmp_path):
    """The generated dashboard's INICIO/FIN filters must offer EXACTLY the
    timestamps present in the source data — no invented times, no missing
    ones, and in chronological order.

    This pins the real workspace file rather than a synthetic fixture: the
    filters are a view of the source, so any divergence is a bug."""
    if not SOURCE.exists():
        pytest.skip("workspace/output/dashboard_data.json not generated yet")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = data["table"]

    expected_ini = sorted({_stamp(r["inicio_impl"]) for r in rows if r.get("inicio_impl")})
    expected_fin = sorted({_stamp(r["fin_impl"]) for r in rows if r.get("fin_impl")})
    if not expected_ini:
        pytest.skip("source file has no dated rows")

    probe = tmp_path / "probe_source.js"
    probe.write_text(SOURCE_PROBE, encoding="utf-8")
    out = subprocess.run(
        ["node", str(probe), str(ROOT / "web/components/timeline/timeline.js"),
         str(ROOT / "web/components/table/table.js"), str(SOURCE)],
        capture_output=True, text=True, check=True, encoding="utf-8")
    got = json.loads(out.stdout)

    assert got["ini"] == expected_ini
    assert got["fin"] == expected_fin
    # The year in the options must come from the run clock, never a hardcode.
    assert got["ini"][0].startswith(str(data["meta"]["updatedAt"][:4]))


# Full-component probe: init + setRows against a minimal DOM stub, so the
# RENDERED filter row is what gets pinned (not just the pure helpers).
DATE_UI_PROBE = r'''
const fs=require('fs'), vm=require('vm');
const holder={};
function el(tag){
  const e={tagName:String(tag).toUpperCase(), attrs:{}, style:{}, children:[],
    classList:{add(){},remove(){},contains(){return false;}},
    setAttribute(k,v){this.attrs[k]=String(v);},
    getAttribute(k){return k in this.attrs?this.attrs[k]:null;},
    hasAttribute(k){return k in this.attrs;},
    addEventListener(){}, appendChild(c){this.children.push(c);return c;},
    querySelector(){return null;}, querySelectorAll(){return {length:0, forEach(){}};},
    closest(){return null;}};
  Object.defineProperty(e,'innerHTML',{get(){return this._html||'';},
    set(v){this._html=String(v); if(this.id) holder[this.id]=this._html;}});
  // _esc() round-trips text through a real <div>: set textContent, read
  // innerHTML back. A real DOM escapes the five specials; mirror that or
  // every option value silently reads back as "".
  Object.defineProperty(e,'textContent',{get(){return this._t||'';},
    set(v){this._t=String(v==null?'':v);
      this._html=this._t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}});
  return e;
}
const head=el('thead'); head.id='table-head';
const body=el('tbody'); body.id='table-body';
const toolbar=el('div'); toolbar.id='table-toolbar';
const byId={'table-head':head,'table-body':body,'table-toolbar':toolbar,
  'tb-count':el('span'),'tb-mode':el('span'),'tb-toggle':el('button'),'tb-clear':el('button')};
const sb={console,Math,JSON,Date,parseInt,isNaN,String,Object,Array,RegExp,Number};
sb.window=sb;
sb.document={createElement:el, getElementById:(id)=>byId[id]||null,
  querySelectorAll(){return {forEach(){}};}, addEventListener(){},
  documentElement:{}, head:el('head'), readyState:'complete'};
sb.getComputedStyle=()=>({getPropertyValue:()=>''});
vm.createContext(sb);
for (const f of process.argv.slice(2,4)) vm.runInContext(fs.readFileSync(f,'utf8'), sb);
const Ops=sb.window.OpsTable, P=Ops._pure;
const meta={updatedAt:'2026-10-19T19:15:00'};
const rows=[
 {responsable:'Ana',pool:'AgileOps Prod',type:'Implementaci\u00f3n',ticket:'OCD-1',nombre_app:'DWLI',status:'Coordinado',inicio_impl:'19/10 16:00',fin_impl:'19/10 20:00'},
 {responsable:'Dino',pool:'AgileOps ORO',type:'Implementaci\u00f3n',ticket:'OCD-4',nombre_app:'ALMR',status:'Coordinado',inicio_impl:'19/10 20:15',fin_impl:'19/10 22:00'},
 {responsable:'Fer',pool:'Pool AgileOps Prod',type:'Implementaci\u00f3n',ticket:'OCD-6',nombre_app:'Y',status:'Coordinado',inicio_impl:'09/11 01:00',fin_impl:'09/11 02:00'},
];
Ops.init({head:head, body:body, toolbar:toolbar, jiraUrl:(t)=>'https://x/'+t});
Ops.setRows(rows, meta, null);
console.log(JSON.stringify({
  headHtml: holder['table-head']||'',
  specIni: P.dateFilterSpec('inicio','',''),
  specFin: P.dateFilterSpec('fin','',''),
  specIniBounded: P.dateFilterSpec('inicio','2026-10-19T21:00',''),
  specFinBounded: P.dateFilterSpec('fin','','2026-10-19T20:00'),
}));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_date_filter_is_one_select_per_column(tmp_path):
    """INICIO IMPL renders ONE "Desde" select (from-bound) and FIN IMPL ONE
    "Hasta" select (to-bound) — never a two-sided range per column. The two
    ends live on the two columns and narrow each other across them."""
    probe = tmp_path / "date_ui_probe.js"
    probe.write_text(DATE_UI_PROBE, encoding="utf-8")
    out = subprocess.run(
        ["node", str(probe), str(ROOT / "web/components/timeline/timeline.js"),
         str(ROOT / "web/components/table/table.js")],
        capture_output=True, text=True, check=True, encoding="utf-8")
    d = json.loads(out.stdout)
    h = d["headHtml"]

    # Exactly two date selects; each column keeps only its own bound.
    assert len(re.findall(r'<select class="tf-input tf-input--date"', h)) == 2
    assert 'data-f="inicio-from"' in h and 'data-f="inicio-to"' not in h
    assert 'data-f="fin-to"' in h and 'data-f="fin-from"' not in h

    # Labels: INICIO -> "Desde", FIN -> "Hasta".
    assert re.search(r'<span>Desde</span>\s*<select[^>]*data-f="inicio-from"', h)
    assert re.search(r'<span>Hasta</span>\s*<select[^>]*data-f="fin-to"', h)
    assert 'aria-label="Inicio Impl desde"' in h
    assert 'aria-label="Fin Impl hasta"' in h

    # Each select offers only its own column's source timestamps.
    def options_of(name):
        i = h.index('data-f="' + name + '"')
        seg = h[i:h.index("</select>", i)]
        return [v for v in re.findall(r'<option value="([^"]+)"', seg)]

    assert options_of("inicio-from") == ["2026-10-19T16:00", "2026-10-19T20:15",
                                         "2026-11-09T01:00"]
    assert options_of("fin-to") == ["2026-10-19T20:00", "2026-10-19T22:00",
                                    "2026-11-09T02:00"]

    # The spec pins which opposite end narrows each column across columns.
    assert d["specIni"] == {"side": "from", "label": "Desde", "other": None}
    assert d["specFin"] == {"side": "to", "label": "Hasta", "other": None}
    assert d["specIniBounded"] == {"side": "from", "label": "Desde",
                                   "other": {"to": "2026-10-19T21:00"}}
    assert d["specFinBounded"] == {"side": "to", "label": "Hasta",
                                   "other": {"from": "2026-10-19T20:00"}}
