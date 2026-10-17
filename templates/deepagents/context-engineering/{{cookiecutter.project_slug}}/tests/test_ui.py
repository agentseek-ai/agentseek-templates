"""Exercise the shipped UI offline; Node is optional and not an app dependency."""
from pathlib import Path
import shutil
import subprocess

import pytest


NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is unavailable; optional offline UI checks skipped")
APP = Path(__file__).resolve().parents[1] / "src" / "{{cookiecutter.project_slug}}" / "static" / "app.js"

SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const [appPath, scenario] = process.argv.slice(1);
class Element {
  constructor(tag='div') {
    this.tagName=tag; this.value=''; this.textContent=''; this.children=[];
    this.dataset={}; this.listeners={}; this.classList={toggle(){},add(){}};
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=[...items]; }
  addEventListener(event, callback) { this.listeners[event]=callback; }
  querySelectorAll(tag) { return this.children.filter(item=>item.tagName===tag); }
  click() { return this.listeners.click?.(); }
}
const elements=new Map(), localized=[];
const html=fs.readFileSync(path.join(path.dirname(appPath),'index.html'),'utf8');
for (const [,tag,attributes] of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/g)) {
  const id=attributes.match(/\bid="([^"]+)"/), key=attributes.match(/\bdata-i18n="([^"]+)"/);
  const element=new Element(tag);
  if (id) elements.set(id[1],element);
  if (key) { element.dataset.i18n=key[1]; localized.push(element); }
}
const get=id=>{ assert.ok(elements.has(id), `Unknown UI element: ${id}`); return elements.get(id); };
for (const side of ['left','right']) get(side+'-metrics').append(...Array.from({length:4},()=>new Element('strong')));
get('left-model').value='submitted-a'; get('left-effort').value='low';
get('right-model').value='submitted-b'; get('right-effort').value='high';
const result={execution:'live',provider:'openai',model:'submitted-b',status:'complete',
  answer:'Completed answer',events:[],files:{'/reports/brief.md':'Completed brief'},
  effective_options:{reasoning_effort:'high'},
  metrics:{provider_calls:1,search_calls:0,tokens:null,elapsed_ms:1}};
const packets=[{type:'compare_start',compare_id:'12345678-pair',shared:{}},
  {type:'side_start',side:'left'},
  {type:'event',side:'left',event:{name:'querit_search',detail:'started'}},
  {type:'error',side:'left',code:'side_run_failed',message:'Candidate failed'},
  {type:'side_start',side:'right'}, {type:'result',side:'right',result},
  {type:'compare_end',outcomes:{left:'error',right:'complete'}}];
const configuration={keys_ready:true,model_key_ready:true,provider:'openai',memory:'',
  base_url:'https://example.test/v1',models_base_url:'https://example.test/v1',tracing_enabled:false};
function response() {
  let sent=false;
  return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:
    (sent=true,{done:false,value:new TextEncoder().encode(packets.map(item=>JSON.stringify(item)).join('\n')+'\n')})})}};
}
let held=false, release;
const context=vm.createContext({
  document:{getElementById:get,createElement:tag=>new Element(tag),documentElement:{},querySelectorAll:()=>localized},
  localStorage:{getItem:()=> 'en',setItem(){}},TextDecoder,Uint8Array,Blob,URL,
  fetch:async(url,options)=>{
    if (url==='/api/config') return {json:async()=>configuration};
    assert.equal(url,'/api/compare'); assert.equal(options.method,'POST');
    return held?new Promise(resolve=>{release=resolve;}):response();
  }
});
vm.runInContext(fs.readFileSync(appPath,'utf8'),context);
const evaluate=source=>vm.runInContext(source,context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  if (scenario==='repeat') {
    await evaluate("compare('live')");
    assert.match(get('compare-status').textContent,/finished/i);
    held=true;
    const pending=evaluate("compare('live')");
    assert.equal(get('compare-status').textContent,'Running', 'A new pair must replace the previous finished status');
    release(response()); await pending;
  } else if (scenario==='ownership') {
    held=true;
    const pending=evaluate("compare('live')");
    assert.match(get('left-result-from').textContent,/submitted-a.*low/, 'Pending runs need frozen candidate identity');
    release(response()); await pending;
    get('left-model').value='next-a'; get('left-effort').value='max';
    get('right-model').value='next-b'; get('right-effort').value='low';
    get('language').click();
    assert.match(get('left-result-from').textContent,/submitted-a.*low/, 'Failed runs must retain their submitted identity');
    assert.doesNotMatch(get('left-result-from').textContent,/next-a|max/);
    assert.match(get('right-result-from').textContent,/submitted-b.*high/, 'Completed results must retain their actual identity');
    assert.doesNotMatch(get('right-result-from').textContent,/next-b/);
    assert.equal(get('left-events').children[0].children[0].textContent,'querit_search');
    assert.equal(get('right-answer').textContent,'Completed answer');
  } else { throw new Error(`Unknown scenario: ${scenario}`); }
})().catch(error=>{ console.error(error); process.exitCode=1; });
"""


@pytest.mark.parametrize("scenario", ["repeat", "ownership"])
def test_comparison_ui_state_and_ownership(scenario):
    result = subprocess.run([NODE, "-e", SCRIPT, str(APP), scenario], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
