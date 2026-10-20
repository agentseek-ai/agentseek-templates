"""Exercise the shipped UI offline; Node is optional and not an app dependency."""

import shutil
import subprocess
from pathlib import Path

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
    this.dataset={}; this.listeners={}; this.attributes={}; this.classList={toggle(){},add(){}};
  }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children=[...items]; }
  setAttribute(name, value) { this.attributes[name]=value; }
  removeAttribute(name) { delete this.attributes[name]; }
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
if(scenario==='evidence'){
  result.answer='# Findings\n\nCompleted answer';
  result.files={'/sources/raw.txt':'<script>never execute</script>',
    '/reports/brief.md':'# Brief\n\n| Finding | Source |\n| --- | --- |\n| One | Official docs |'};
  result.events=[{kind:'tool',name:'read_file',detail:'finished',scope:'researcher',phase:'finished'}];
}
const configuration={keys_ready:true,model_key_ready:true,provider:'openai',memory:'',
  base_url:'https://example.test/v1',models_base_url:'https://example.test/v1',tracing_enabled:false};
const rerunScenario=scenario.startsWith('rerun-');
if(rerunScenario||scenario.startsWith('effort-')){
  const leftResult={...result,model:'submitted-a',effective_options:{reasoning_effort:'low'},
    answer:'Original A answer',events:[{kind:'tool',name:'read_file',detail:'finished'}],
    files:{'/reports/brief.md':'Original A report','/sources/raw.txt':'Original A source'}};
  packets.splice(1,3,{type:'side_start',side:'left',run_id:'run-a-original'},
    {type:'result',side:'left',run_id:'run-a-original',result:leftResult},
    {type:'side_end',side:'left',run_id:'run-a-original',outcome:'complete'});
  packets.find(item=>item.type==='side_start'&&item.side==='right').run_id='run-b-original';
  if(scenario==='effort-server-default')leftResult.effective_options.reasoning_effort=null;
  packets[packets.length-1].outcomes.left='complete';
}
if(scenario==='effort-anthropic') configuration.provider='anthropic';
function response(items=packets, interrupted=false) {
  let sent=false;
  return {ok:true,body:{getReader:()=>({read:async()=>{
    if(sent){if(interrupted)throw new Error('connection reset');return {done:true};}
    sent=true;return {done:false,value:new TextEncoder().encode(
      items.map(item=>JSON.stringify(item)).join('\n')+'\n')};
  }})}};
}
let held=false, release;
const requests=[];let rerunPackets=[],interruptRerun=false;
const context=vm.createContext({
  document:{getElementById:get,createElement:tag=>new Element(tag),documentElement:{},querySelectorAll:()=>localized},
  localStorage:{getItem:()=> 'en',setItem(){}},TextDecoder,Uint8Array,Blob,URL,
  fetch:async(url,options)=>{
    if (url==='/api/config') return {json:async()=>configuration};
    assert.equal(options.method,'POST');requests.push({url,payload:JSON.parse(options.body)});
    if(url==='/api/compare')return held?new Promise(resolve=>{release=resolve;}):response();
    assert.match(url,/^\/api\/compare\/12345678-pair\/rerun\/(left|right)$/);
    if(scenario==='rerun-expired')return {ok:false,status:404};
    return held?new Promise(resolve=>{release=resolve;}):response(rerunPackets,interruptRerun);
  }
});
vm.runInContext(fs.readFileSync(appPath,'utf8'),context);
const evaluate=source=>vm.runInContext(source,context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  if(scenario==='completed-notice'){
    await evaluate("compare('live')");
    assert.match(get('compare-status').textContent,/finished/i);
    assert.equal(get('notice').textContent,'','Completed live status belongs only in the toolbar');
    assert.notEqual(get('left-notice').textContent,'','Candidate failures must retain their own notice');
    get('language').click();
    assert.equal(get('notice').textContent,'','Translation must not recreate a completed banner');
    await evaluate("compare('fixture')");
    assert.notEqual(get('notice').textContent,'','Offline examples must retain their explanatory notice');
  } else if (scenario==='repeat') {
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
    assert.match(get('left-result-from').textContent,/submitted-a.*low/,
      'Failed runs must retain their submitted identity');
    assert.doesNotMatch(get('left-result-from').textContent,/next-a|max/);
    assert.match(get('right-result-from').textContent,/submitted-b.*high/,
      'Completed results must retain their actual identity');
    assert.doesNotMatch(get('right-result-from').textContent,/next-b/);
    assert.equal(get('left-events').children[0].children[0].children[0].children[0].textContent,'querit_search');
    assert.equal(get('right-answer').textContent,'Completed answer');
  } else if (scenario==='evidence') {
    const calls=[];
    context.ContextMarkdown={render:text=>{calls.push(text);return `<article>${text}</article>`;}};
    await evaluate("compare('live')");
    assert.ok(calls.includes(result.answer), 'Model answers must use the safe Markdown renderer');
    assert.ok(calls.includes(result.files['/reports/brief.md']), 'Report preview must use the same renderer');
    assert.equal(get('right-file-path').textContent,'/reports/brief.md', 'Reports should open by default');
    assert.equal(get('right-file-format').textContent,'Markdown');
    const buttons=get('right-files').children;
    assert.equal(buttons[1].attributes['aria-pressed'],'true');
    assert.equal(buttons[1].children[0].textContent,'brief.md');
    assert.equal(buttons[1].children[1].textContent,'/reports/');
    buttons[0].click();
    assert.equal(get('right-file-path').textContent,'/sources/raw.txt');
    assert.equal(get('right-file-content').children[0].textContent,'<script>never execute</script>',
      'Non-Markdown source content must be inserted as text');
    assert.equal(buttons[0].attributes['aria-pressed'],'true');
    const event=get('right-events').children[0].children[0];
    assert.match(event.children[0].children[1].textContent,/Tool.*finished.*researcher/);
    assert.deepEqual(JSON.parse(event.children[1].textContent),result.events[0],
      'Expanded trace detail must preserve the exact observed event');
    get('language').click();
    assert.equal(get('right-file-path').textContent,'/sources/raw.txt','Language changes must preserve file selection');
    assert.equal(get('right-file-format').textContent,'纯文本');
    assert.equal(get('right-event-count').textContent,1);
    assert.equal(get('left-event-count').textContent,1,'Failed candidates must retain observed events');
    assert.equal(get('inference-endpoint').attributes.href,configuration.base_url);
    assert.equal(get('catalog-endpoint').attributes.href,configuration.models_base_url);
    assert.doesNotMatch(html,/<details class="connection"/,'Connections must be visible without expanding a panel');
    assert.doesNotMatch(html,/id="tracing"|data-i18n="budget"|data-i18n="setupNote"/);
  } else if (rerunScenario) {
    await evaluate("compare('live')");
    assert.equal(get('left-rerun').disabled,false,'A completed pair must support independent reruns');
    assert.equal(get('right-rerun').disabled,false);
    if(scenario==='rerun-blocked'){
      const initialCount=requests.length,originalPrompt=get('prompt').value;
      get('prompt').value+=' edited';get('prompt').listeners.input();
      assert.equal(get('left-rerun').disabled,true,'Changed common tasks require a new pair');
      assert.match(get('left-rerun-hint').textContent,/new comparison/i);
      await evaluate("rerun('left')");assert.equal(requests.length,initialCount);
      get('prompt').value=originalPrompt;get('prompt').listeners.input();
      get('material').value='Changed source';get('material').listeners.input();
      assert.equal(get('right-rerun').disabled,true,'Changed source material must not silently reuse old input');
      await evaluate("rerun('right')");assert.equal(requests.length,initialCount);
      get('material').value='';get('material').listeners.input();
      get('language').click();
      assert.equal(get('prompt').value,originalPrompt,'UI translation must not edit frozen shared tasks');
      assert.equal(get('left-rerun').disabled,false,'UI language changes must allow reruns in original output language');
      assert.equal(evaluate('pair.input.language'),'en');
      evaluate('config.keys_ready=false;controls()');
      assert.equal(get('left-rerun').disabled,true,'Live reruns still require keys');
      return;
    }
    if(scenario==='rerun-expired'){
      const before=evaluate('JSON.stringify(state)');
      await get('left-rerun').click();
      assert.equal(evaluate('JSON.stringify(state)'),before,'A missing server snapshot must not erase existing evidence');
      assert.equal(get('left-rerun').disabled,true);
      assert.match(get('left-rerun-hint').textContent,/new comparison/i);return;
    }
    const selected=scenario==='rerun-right'?'right':'left',other=selected==='left'?'right':'left';
    evaluate(`selectFile('${other}','/reports/brief.md')`);
    const untouched=evaluate(`JSON.stringify(state.${other})`),otherEvents=get(other+'-events').children,
      otherFiles=get(other+'-files').children,originalOutcome=evaluate(`pair.outcomes.${other}`);
    get(selected+'-model').value='replacement-model';get(selected+'-effort').value='medium';
    get(selected+'-model').listeners.input();
    assert.match(get(selected+'-selection-note').textContent,/current selection.*differs/i,
      'Changed controls must be distinguished from displayed result identity');
    const nextResult={...result,model:'replacement-model',answer:'Updated answer',
      effective_options:{reasoning_effort:'medium'},files:{'/reports/brief.md':'Updated report'}};
    rerunPackets=[{type:'side_start',side:selected,run_id:'run-replacement',model_id:'replacement-model'},
      {type:'event',side:selected,run_id:'run-replacement',event:{kind:'tool',name:'read_file',detail:'started'}}];
    if(scenario==='rerun-error')rerunPackets.push(
      {type:'error',side:selected,run_id:'run-replacement',code:'side_run_failed',message:'Run failed'},
      {type:'side_end',side:selected,run_id:'run-replacement',outcome:'error'});
    else if(scenario==='rerun-interrupted')interruptRerun=true;
    else rerunPackets.push({type:'result',side:selected,run_id:'run-replacement',result:nextResult},
      {type:'side_end',side:selected,run_id:'run-replacement',outcome:'complete'});
    held=true;const pending=get(selected+'-rerun').click();
    assert.equal(get('left-rerun').disabled,true);assert.equal(get('right-rerun').disabled,true);
    assert.equal(get('compare').disabled,true,'Only one request can run at a time');
    assert.equal(evaluate(`state.${selected}.result`),undefined,'Only the rerun candidate should reset');
    assert.equal(evaluate(`JSON.stringify(state.${other})`),untouched);
    assert.equal(requests.at(-1).url,`/api/compare/12345678-pair/rerun/${selected}`);
    assert.deepEqual(requests.at(-1).payload,{model_id:'replacement-model',reasoning_effort:'medium'},
      'Reruns select a candidate and leave the shared snapshot on the server');
    release(response(rerunPackets,interruptRerun));await pending;
    assert.equal(evaluate(`JSON.stringify(state.${other})`),untouched,'Other-side data must survive success and failure unchanged');
    assert.equal(get(other+'-events').children,otherEvents,'Do not rebuild untouched-side traces');
    assert.equal(get(other+'-files').children,otherFiles,'Do not rebuild untouched-side files or selections');
    assert.equal(evaluate(`pair.outcomes.${other}`),originalOutcome);
    assert.equal(evaluate(`state.${selected}.run_id`),'run-replacement','Exports must identify the latest run of each side');
    assert.match(get(selected+'-result-from').textContent,/replacement-model.*medium/);
    assert.equal(get('download-pair').disabled,false);
    assert.equal(get(selected+'-rerun').disabled,false,'Single-side failures remain retryable');
    if(scenario==='rerun-error'||scenario==='rerun-interrupted'){
      assert.equal(evaluate(`state.${selected}.phase`),'error');
      assert.equal(evaluate(`pair.outcomes.${selected}`),'error');
      assert.equal(get(selected+'-event-count').textContent,1,'Observed events must survive rerun failure');
      assert.equal(evaluate(`state.${other}.phase`),'complete');
    } else {
      assert.equal(evaluate(`state.${selected}.phase`),'complete');
      assert.equal(evaluate(`pair.outcomes.${selected}`),'complete');
      assert.equal(get(selected+'-answer').textContent,'Updated answer');
      assert.equal(get(selected+'-file-path').textContent,'/reports/brief.md');
      assert.equal(evaluate('pair.input.left.model_id'),'submitted-a','Original pair inputs remain frozen');
      assert.equal(get('notice').textContent,'','Successful reruns must not duplicate the completed status');
      get('language').click();
      assert.equal(get('notice').textContent,'','Translation after a rerun must keep the completed banner hidden');
    }
  } else if(scenario.startsWith('effort-')){
    if(scenario==='effort-server-default'){
      await evaluate("compare('live')");
      assert.match(get('left-result-from').textContent,/Reasoning level: Provider default/,
        'An explicit server-reported default must not fall back to a requested override');
      assert.equal(get('left-selection-note').hidden,false);return;
    }
    get('left-effort').value='';get('right-effort').value='';evaluate('controls()');
    assert.equal(get('effort-warning').hidden,true,'Equal provider-default selections need no difference warning');
    get('left-effort').value='low';get('right-effort').value='high';evaluate('controls()');
    if(scenario==='effort-anthropic'){
      assert.equal(get('effort-warning').hidden,true,'Unsupported reasoning overrides are not compared');
      assert.equal(get('left-effort').disabled,true);
    } else {
      assert.equal(get('effort-warning').hidden,false);
      assert.match(get('effort-warning').textContent,/low.*high/);
      await evaluate("compare('live')");
      get('left-effort').value='high';evaluate('controls()');
      assert.equal(get('effort-warning').hidden,true);
      assert.equal(get('result-effort-warning').hidden,false,'Displayed results must retain their differing effective options');
      assert.match(get('result-effort-warning').textContent,/low.*high/);
    }
  } else { throw new Error(`Unknown scenario: ${scenario}`); }
})().catch(error=>{ console.error(error); process.exitCode=1; });
"""


@pytest.mark.parametrize(
    "scenario",
    [
        "completed-notice", "repeat", "ownership", "evidence", "rerun-left", "rerun-right", "rerun-error",
        "rerun-interrupted", "rerun-blocked", "rerun-expired", "effort-warning",
        "effort-anthropic", "effort-server-default",
    ],
)
def test_comparison_ui_state_and_ownership(scenario):
    result = subprocess.run([NODE, "-e", SCRIPT, str(APP), scenario], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
