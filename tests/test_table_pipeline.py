"""Table: pool catalog, next-60-min window, per-column filters, sorting."""
import json, shutil, subprocess
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
