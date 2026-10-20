"""Regression probes for the 4h global timeline (S1/S2/S5/S6/A2) and for the
dashboard visible-count ordering (B1). pytest suite; the geometry probe needs
Node and skips when it is absent."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_s1_s6_no_pool_sections_or_toggle():
    """S1 + S6: flat global view, no pool headers, no alternate-view toggle."""
    js = _read("web/components/timeline/timeline.js")
    css = _read("web/components/timeline/timeline.css")
    tpl = _read("web/dashboard_template.html")
    assert "timeline__pool-header" not in js + css
    assert "renderPoolHeader" not in js
    assert "Por pool" not in tpl
    assert "view-toggle" not in tpl


def test_s3_s4_todos_default_and_filter():
    """S3 + S4: Todos is the default and is persisted as the empty id."""
    src = _read("web/dashboard.js")
    assert "all.value = '';" in src and "all.textContent = 'Todos';" in src
    initial = src[src.index("function _initialGroup"):src.index("function _onGroupChange")]
    assert "return null;" in initial
    assert "_applyGroup(null, { persist: true })" in src
    assert "storageSet(GROUP_STORAGE_KEY, group ? group.id : '')" in src


NODE_PROBE = r'''
const fs = require('fs'), vm = require('vm');
const code = fs.readFileSync(process.argv[2], 'utf8');
const V = {'--timeline-row-height':'32px','--timeline-gap':'2px','--timeline-header-height':'28px','--timeline-label-width':'220px'};
function E(){
  return {innerHTML:'',textContent:'',scrollLeft:0,scrollTop:0,dataset:{},
    appendChild(){},addEventListener(){},querySelector(){return null;},
    querySelectorAll(){return {forEach(){}};},classList:{add(){},remove(){}},
    get firstChild(){return null;}};
}
const els = {};
const doc = {
  createElement(){ const e=E(); Object.defineProperty(e,'textContent',{
    set(v){ this._v=String(v); this.innerHTML=this._v.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); },
    get(){ return this._v||''; }}); return e; },
  getElementById(id){ return els[id]||(els[id]=E()); },
  querySelectorAll(){ return {forEach(){}}; },
  addEventListener(){}, documentElement:E(), head:E(), readyState:'complete'
};
const sb = {console, Math, JSON, Date, parseInt, isNaN, String, Object, Array, RegExp};
sb.window=sb; sb.document=doc;
sb.getComputedStyle=()=>({getPropertyValue:n=>V[n]||''});
vm.createContext(sb); vm.runInContext(code, sb);
const T = sb.window.Timeline;
const bar=(tk,st,du)=>({ticket:tk,name:tk,type:'implementacion',status:'pase-en-curso',start:st,duration:du,responsable:'Ana'});
const c={meta:{updatedAt:'2026-10-19T04:30:00',windowStart:'04:00',windowEnd:'12:00',poolOrder:['P','Q']},
  timeline:[{pool:'P',bars:[bar('EARLY',-60,120),bar('LATE',400,60)]},
            {pool:'Q',bars:[bar('C',0,120)]}]};
T.init(doc.getElementById('timeline'), c, null);
const h=els['timeline-header'].innerHTML, g=els['timeline-grid'].innerHTML, b=els['timeline-bars'].innerHTML;
const styleOf=(tk)=>{ const m=new RegExp('<div class="timeline__bar[^"]*" style="([^"]*)" data-ticket="'+tk+'"').exec(b); return m?m[1]:'ABSENT'; };
const rows=[...b.matchAll(/class="timeline__row-name">([^<]*)</g)].map(m=>m[1]);
console.log(JSON.stringify({ offsetMin:T.viewWindow().offsetMin, minutes:T.viewWindow().minutes,
  widths:[...g.matchAll(/width:([0-9.]+)px/g)].map(m=>+m[1]),
  labels:[...h.matchAll(/>(\d{2}:\d{2})</g)].map(m=>m[1]),
  barEarly:styleOf('EARLY'), barLate:styleOf('LATE'), rows }));
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_s2_s5_a2_geometry(tmp_path):
    probe = tmp_path / "probe.js"
    probe.write_text(NODE_PROBE, encoding="utf-8")
    out = subprocess.run(
        ["node", str(probe), str(ROOT / "web/components/timeline/timeline.js")],
        capture_output=True, text=True, check=True,
    )
    d = json.loads(out.stdout)
    assert d["minutes"] == 240 and d["offsetMin"] == 30
    assert d["labels"] == ["04:30", "05:00", "06:00", "07:00", "08:00"]
    assert d["widths"] == [96] * 8 and sum(d["widths"]) == 768
    # 1px inset per side so adjacent passes never fuse: left 0+1, width 96-2\n    assert "left:1px" in d["barEarly"] and "width:94px" in d["barEarly"]
    assert d["barLate"] == "ABSENT"
    assert d["rows"] == ["Ana", "Ana"]


def test_b1_indicator_rendered_after_timeline_init():
    """B1: the counts label must read the CURRENT render, not the previous one."""
    src = _read("web/dashboard.js")
    body = src[src.index("function _applyGroup"):src.index("function _viewWindowLabel")]
    assert body.index("window.Timeline.init(") < body.index("_renderGroupIndicator(view)")


def test_bar_palette_is_status_driven_and_pool_is_a_chip():
    """Bar fill follows the status tokens; the pool is a chip + stable data hook."""
    css = _read("web/components/timeline/timeline.css")
    theme = _read("web/theme.css")
    for tok in ("--tl-en-curso-bg: #A7F3D0", "--tl-atrasado-bg: #FBBF24",
                "--tl-coordinado-bg: #BFDBFE", "--tl-chip-accent-yape: #8B5CF6"):
        assert tok in theme
    # no pool-driven bar fill any more
    for pool in ("yape", "sf", "agileops-oro", "agileops-prod"):
        assert ".timeline__bar--%s {" % pool not in css
    assert "border: 2px dashed" in css            # derivado frame
    js = _read("web/components/timeline/timeline.js")
    assert "data-pool=" in js and "_hasPool(pool)" in js
