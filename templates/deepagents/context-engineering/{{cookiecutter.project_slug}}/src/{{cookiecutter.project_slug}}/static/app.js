const $=id=>document.getElementById(id), sides=['left','right'];
const copy={
zh:{headline:'相同上下文，比较不同模型。',subtitle:'左右独立选择模型，把任务、材料、记忆与上下文策略固定下来，再查看各自的真实执行。',connection:'连接与预算',budget:'每次模型调用最多 3,000 输出 Token；每侧：4 次搜索 × 3 条结果 · 6,000 Token 触发摘要 · 180 秒总限时',setupNote:'密钥只在本地终端填写，修改配置后重启服务。',sharedTask:'共同任务',frozen:'比较开始时冻结输入',addMaterial:'添加共同材料，保留完整原文',materialNote:'每侧独立保存相同原文，任务只携带文件路径与 300 字符预览。',memoryTitle:'已批准的长期记忆',memoryNote:'两侧读取同一份已保存快照，模型不能修改它。',saveMemory:'批准并保存',refresh:'刷新可用模型',discoveryInitial:'从当前目录端点读取真实模型列表，也可手填精确 ID。',modelNote:'目录不保证聊天或工具调用能力，以实际端点支持为准。推理档位仅 OpenAI 兼容协议且服务支持时生效。',comparisonNote:'按左、右顺序运行，降低并发限流。动态检索可能不同；共同输入不等于严格基准。',download:'导出比较',fixture:'离线示例',compare:'开始比较',left:'左侧模型',right:'右侧模型',modelId:'模型 ID',reasoning:'推理档位',providerDefault:'提供方默认',waiting:'等待开始',modelCalls:'模型调用',searchCalls:'搜索调用',elapsed:'用时',empty:'选择模型，或先用离线示例查看可检查的上下文机制。',trace:'执行轨迹',files:'可回读文件',capabilities:'同一上下文策略：原文外置 · 可恢复摘要 · 按需技能 · 子智能体 · 批准后记忆。配置不等于触发，实际轨迹只记录本次发生的事件。',prompt:'比较线程状态与长期记忆。检索官方 Deep Agents 资料，给出 3 条关键发现、来源链接和不确定性，并将简报写入 /reports/brief.md。',saved:'记忆已保存；下次比较会同时读取。当前比较仍使用开始时的快照。',saveFailed:'保存失败，请检查内容后重试。',keysMissing:'实时比较前，请在终端填写所选模型提供方与 Querit 密钥。离线示例无需密钥。',refreshing:'正在读取真实目录…',discoveryFailed:'当前目录端点不支持读取、未授权或暂时不可用。请手填精确模型 ID；推理端点没有改变。',modelsFound:n=>`目录返回 ${n} 个模型 ID。可选择或继续手填；目录不保证当前账户可调用。`,partialList:'当前列表有分页上限，可手填其他精确 ID。',modelKeyMissing:'读取目录前请填写所选模型提供方密钥。',catalogSource:'模型目录',inferenceSource:'推理端点',tracingOn:'LangSmith 已启用：比较 ID、侧别与模型会标记在轨迹中。',tracingOff:'LangSmith 未启用。',running:'运行中',queued:'等待左侧结束',complete:'已完成',incomplete:'输出未完成',failed:'本侧失败',fixtureBadge:'离线示意',fixtureNotice:'机制示意：没有模型或搜索请求，不能用来比较速度、成本或效果。',incompleteNotice:'模型输出达到当前上限，结果未完成。实际用量和部分文件已保留；可缩小任务或调整模型支持的推理档位后重试。',sideFailed:'本侧运行失败，可能已产生用量。另一侧继续运行；已完成结果会保留。',runningNotice:'正在使用同一份输入与批准记忆快照进行独立执行。',pairFinished:'比较已结束，请分别查看两侧状态、证据与用量。',streamFailed:'连接中断或比较未完整结束。已收到的另一侧结果会保留，请检查本地服务。',validationError:'请填写共同任务和两侧精确模型 ID，并检查连接配置。',notReported:'未返回',notMeasured:'未测量',noAnswer:'最终模型消息没有文本，请查看文件与执行轨迹。',started:'开始',finished:'结束'},
en:{headline:'Same context. Compare your models.',subtitle:'Choose each model independently. Freeze the task, source material, approved memory and context strategy, then inspect each real execution.',connection:'Connection and budgets',budget:'Up to 3,000 output tokens per model call; each side: 4 searches × 3 results · summarize at 6,000 tokens · 180 seconds total',setupNote:'Enter keys privately in your local terminal. Restart the service after changing configuration.',sharedTask:'Shared task',frozen:'Inputs freeze when comparison starts',addMaterial:'Add shared material; keep the complete original',materialNote:'Each graph receives its own copy of the same source. The task carries a file path and a 300-character preview.',memoryTitle:'Approved persistent memory',memoryNote:'Both sides read the same saved snapshot. Models cannot modify it.',saveMemory:'Approve and save',refresh:'Refresh available models',discoveryInitial:'Read actual model IDs from the configured catalog, or enter an exact ID manually.',modelNote:'A catalog entry does not guarantee chat or tool-call support. Reasoning levels apply only to OpenAI-compatible services that support them.',comparisonNote:'Runs left, then right to reduce concurrent rate limits. Dynamic search can differ; shared inputs are not a controlled benchmark.',download:'Export comparison',fixture:'Offline example',compare:'Compare models',left:'Left model',right:'Right model',modelId:'Model ID',reasoning:'Reasoning level',providerDefault:'Provider default',waiting:'Ready to begin',modelCalls:'Model calls',searchCalls:'Search calls',elapsed:'Elapsed',empty:'Choose a model, or explore inspectable context mechanisms in the offline example.',trace:'Execution trace',files:'Retrievable files',capabilities:'Shared context strategy: offload · recoverable summaries · on-demand skills · subagents · approved memory. Configuration does not imply execution; live traces show observed events only.',prompt:'Compare thread state and long-term memory. Search official Deep Agents sources, return 3 findings with source links and uncertainty, and write /reports/brief.md.',saved:'Memory saved for both sides of the next comparison. The current comparison keeps its original snapshot.',saveFailed:'Could not save memory. Check the content and retry.',keysMissing:'Before comparing live, enter the selected provider and Querit keys in your terminal. Offline examples need no keys.',refreshing:'Reading the actual model catalog…',discoveryFailed:'This catalog endpoint is unsupported, unauthorized or temporarily unavailable. Enter exact IDs manually; the inference endpoint has not changed.',modelsFound:n=>`The catalog returned ${n} model IDs. Choose one or enter an exact ID; entries do not guarantee account access.`,partialList:'The list reached a pagination limit; additional exact IDs can be entered manually.',modelKeyMissing:'Enter the selected model provider key before reading the catalog.',catalogSource:'Model catalog',inferenceSource:'Inference endpoint',tracingOn:'LangSmith enabled: traces carry the comparison ID, side and model.',tracingOff:'LangSmith is disabled.',running:'Running',queued:'Waiting for left side',complete:'Complete',incomplete:'Incomplete output',failed:'This side failed',fixtureBadge:'Offline illustration',fixtureNotice:'Illustrative mechanisms only: no model or search calls. This example cannot compare speed, cost or quality.',incompleteNotice:'The model reached its output limit. Actual usage and partial files are preserved. Narrow the task or adjust a reasoning level supported by your model before retrying.',sideFailed:'This candidate failed and may have incurred usage. The other side continues; completed results remain available.',runningNotice:'Independent graphs are using the same input and approved-memory snapshot.',pairFinished:'Comparison finished. Review each side’s status, evidence and usage.',streamFailed:'The connection ended before the comparison finished. Received results remain available; check the local service.',validationError:'Enter a shared task and two exact model IDs, and check connection settings.',notReported:'Not reported',notMeasured:'Not measured',noAnswer:'The final model message contained no text. Inspect files and execution events.',started:'started',finished:'finished'}
};
Object.assign(copy.zh,{runFrom:'本次运行模型',resultFrom:'本次结果来自',fixtureIdentity:'离线示意：未调用任何模型。',nextSelection:'选择框用于下一次比较。'});
Object.assign(copy.en,{runFrom:'Run candidate',resultFrom:'Result from',fixtureIdentity:'Offline illustration: no model was called.',nextSelection:'Selections apply to the next comparison.'});
Object.assign(copy.zh,{
  answerTitle:'模型回答',traceHint:'仅记录实际发生的事件；展开单项查看原始记录。',
  noEvents:'尚无执行事件。运行后可在此检查工具与上下文操作。',
  noFiles:'本侧尚无可回读文件。',noFileSelected:'选择文件查看完整内容',
  fileNavigation:'本侧可回读文件',plainText:'纯文本',rawEvent:'原始事件',
  eventTool:'工具',eventOffload:'原文外置',eventIllustration:'离线示意',eventScope:'作用域',eventPhase:'阶段'
});
Object.assign(copy.en,{
  answerTitle:'Model answer',traceHint:'Observed events only. Expand an item to inspect its raw record.',
  noEvents:'No execution events yet. Inspect tool and context activity here after a run.',
  noFiles:'No retrievable files for this candidate yet.',noFileSelected:'Select a file to read its full content',
  fileNavigation:'Retrievable files for this candidate',plainText:'Plain text',rawEvent:'Raw event',
  eventTool:'Tool',eventOffload:'Offload',eventIllustration:'Offline illustration',eventScope:'Scope',eventPhase:'Phase'
});
let language=localStorage.getItem('context-lab-language')==='en'?'en':'zh',config=null,busy=false,pair=null;
let state={left:{phase:'waiting',events:[]},right:{phase:'waiting',events:[]}};
let discovery={phase:'initial',count:0,complete:true};
const t=key=>copy[language][key]||key;
function notify(message,error=false){$('notice').textContent=message;$('notice').className=error?'error':'';}
function controls(){const ids=sides.every(side=>$(side+'-model').value.trim());$('compare').disabled=busy||!config?.keys_ready||!ids;$('fixture').disabled=busy;$('refresh-models').disabled=busy||discovery.phase==='loading'||!config?.model_key_ready;$('language').disabled=busy;for(const side of sides){$(side+'-model').disabled=busy;$(side+'-effort').disabled=busy||config?.provider==='anthropic';}$('prompt').disabled=busy;$('material').disabled=busy;}
function discoveryText(){let message=t('discoveryInitial');if(discovery.phase==='loading')message=t('refreshing');if(discovery.phase==='failed')message=t('discoveryFailed');if(discovery.phase==='missing')message=t('modelKeyMissing');if(discovery.phase==='ready')message=t('modelsFound')(discovery.count)+(discovery.complete?'':' '+t('partialList'));$('discovery-status').textContent=message;}
function connectionLink(id,value){
  const link=$(id);link.textContent=value||'—';
  try{const url=new URL(value);if(url.protocol==='https:'||url.protocol==='http:'){link.setAttribute('href',url.href);return;}}catch{}
  link.removeAttribute('href');
}
function translate(){document.documentElement.lang=language==='zh'?'zh-CN':'en';document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));$('language').textContent=language==='zh'?'English':'中文';if(!$('prompt').value)$('prompt').value=t('prompt');if(config){connectionLink('inference-endpoint',config.base_url);connectionLink('catalog-endpoint',config.models_base_url);if(!config.keys_ready&&!pair)notify(t('keysMissing'));}if(pair){notify(t(pair.error|| (pair.execution==='fixture'?'fixtureNotice':pair.outcomes?'pairFinished':'runningNotice')),Boolean(pair.error));$('compare-status').textContent=t(pair.error||(pair.outcomes?'pairFinished':'running'));}discoveryText();for(const side of sides)renderSide(side);controls();}
function renderMarkdown(element,text){
  element.classList.add('markdown-body');
  if(globalThis.ContextMarkdown?.render){element.innerHTML=globalThis.ContextMarkdown.render(String(text));}
  else{element.textContent=String(text);}
}
function eventLabel(event){
  const labels={tool:'eventTool',offload:'eventOffload',illustration:'eventIllustration'};
  return labels[event.kind]?t(labels[event.kind]):event.kind||'';
}
function appendEvent(side,event){
  const list=$(side+'-events');
  if(list.children.length===1&&list.children[0].className==='evidence-empty')list.replaceChildren();
  const li=document.createElement('li'),details=document.createElement('details'),summary=document.createElement('summary');
  details.className='trace-event';summary.className='trace-event-summary';
  const name=document.createElement('strong');name.textContent=event.name||event.kind||t('trace');
  const meta=document.createElement('span');meta.className='trace-event-meta';
  const kind=eventLabel(event),phase=event.phase||(event.detail==='started'||event.detail==='finished'?event.detail:'');
  meta.textContent=[kind,phase==='started'?t('started'):phase==='finished'?t('finished'):phase,event.scope?`${t('eventScope')}: ${event.scope}`:''].filter(Boolean).join(' · ');
  summary.append(name,meta);details.append(summary);
  if(event.detail&&event.detail!=='started'&&event.detail!=='finished'){
    const description=document.createElement('p');description.className='trace-description';
    description.textContent=String(event.detail);details.append(description);
  }
  const raw=document.createElement('pre');raw.className='trace-raw';raw.textContent=JSON.stringify(event,null,2);
  raw.setAttribute('aria-label',t('rawEvent'));details.append(raw);li.append(details);list.append(li);
  $(side+'-event-count').textContent=state[side].result?.events?.length??state[side].events.length;
}
function selectFile(side,path){
  const item=state[side],files=item.result?.files||{},preview=$(side+'-file-content');
  item.selectedFile=path;
  $(side+'-files').querySelectorAll('button').forEach(button=>{
    const active=button.dataset.path===path;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));
  });
  $(side+'-file-path').textContent=path;
  const markdown=/\.(md|markdown)$/i.test(path);$(side+'-file-format').textContent=markdown?'Markdown':t('plainText');
  preview.className='file-content';
  if(markdown){renderMarkdown(preview,files[path]);}
  else{const pre=document.createElement('pre');pre.className='plain-content';pre.textContent=String(files[path]);preview.replaceChildren(pre);}
}
function renderFiles(side){
  const item=state[side],files=Object.entries(item.result?.files||{}),list=$(side+'-files'),preview=$(side+'-file-content');
  list.replaceChildren();list.setAttribute('aria-label',t('fileNavigation'));
  $(side+'-file-count').textContent=files.length;
  if(!files.length){
    const empty=document.createElement('p');empty.className='evidence-empty';empty.textContent=t('noFiles');list.append(empty);
    $(side+'-file-path').textContent=t('noFileSelected');$(side+'-file-format').textContent='';
    preview.className='file-content empty-preview';preview.textContent=t('noFiles');return;
  }
  for(const[path]of files){
    const button=document.createElement('button'),name=document.createElement('strong'),folder=document.createElement('span');
    button.className='file-button';button.type='button';button.dataset.path=path;button.title=path;
    name.textContent=path.split('/').pop()||path;folder.textContent=path.slice(0,path.lastIndexOf('/')+1)||'/';
    button.append(name,folder);button.addEventListener('click',()=>selectFile(side,path));list.append(button);
  }
  const paths=files.map(([path])=>path);
  const selected=paths.includes(item.selectedFile)?item.selectedFile:paths.find(path=>path==='/reports/brief.md')||paths.find(path=>/^\/reports\/.*\.(md|markdown)$/i.test(path))||paths[0];
  selectFile(side,selected);
}
function runIdentity(item){
  const result=item.result,candidate=item.candidate;
  if(!result&&!candidate)return '';
  if((result?.execution||pair?.execution)==='fixture')return t('fixtureIdentity');
  const model=result?.model||candidate?.model_id;
  if(!model)return '';
  const effort=result?.effective_options?result.effective_options.reasoning_effort:config?.provider==='anthropic'?null:candidate?.reasoning_effort;
  return `${t(result?'resultFrom':'runFrom')}: ${model} · ${t('reasoning')}: ${effort||t('providerDefault')}. ${t('nextSelection')}`;
}
function renderSide(side){
  const item=state[side],result=item.result,phase=item.phase,badge=$(side+'-status');
  badge.textContent=t(phase==='fixture'?'fixtureBadge':phase==='error'?'failed':phase);badge.className='run-badge '+phase;
  const notice=$(side+'-notice');notice.className='side-notice';notice.textContent='';
  if(phase==='fixture'){notice.textContent=t('fixtureNotice');notice.classList.add('fixture');}
  if(phase==='error'||phase==='incomplete'){notice.textContent=t(phase==='error'?'sideFailed':'incompleteNotice');notice.classList.add('error');}
  const answer=$(side+'-answer');answer.className=result?'answer':'answer empty';
  answer.setAttribute('aria-label',`${t(side)}: ${t('answerTitle')}`);answer.setAttribute('aria-busy',String(phase==='running'));
  if(result){renderMarkdown(answer,result.answer||t('noAnswer'));}
  else{answer.textContent=t(phase==='running'?'running':phase==='queued'?'queued':'empty');}
  $(side+'-result-from').textContent=runIdentity(item);
  const metrics=result?.metrics,values=metrics?[metrics.provider_calls,metrics.search_calls,metrics.tokens?.total_tokens??t(result.execution==='fixture'?'notMeasured':'notReported'),result.execution==='fixture'?'—':`${(metrics.elapsed_ms/1000).toFixed(1)} s`]:['—','—','—','—'];
  $(side+'-metrics').querySelectorAll('strong').forEach((el,i)=>el.textContent=values[i]);
  const events=result?.events||item.events,list=$(side+'-events');list.replaceChildren();list.setAttribute('aria-label',t('trace'));
  events.forEach(event=>appendEvent(side,event));$(side+'-event-count').textContent=events.length;
  if(!events.length){const empty=document.createElement('li');empty.className='evidence-empty';empty.textContent=t('noEvents');list.append(empty);}
  renderFiles(side);
}
async function refreshModels(){if(busy||!config?.model_key_ready)return;discovery.phase='loading';discoveryText();controls();try{const response=await fetch('/api/models');if(!response.ok)throw new Error();const data=await response.json();$('available-models').replaceChildren();if(!data.available){discovery.phase=data.code==='model_key_required'?'missing':'failed';}else{const models=Array.isArray(data.models)?data.models:[];for(const id of models){const option=document.createElement('option');option.value=id;$('available-models').append(option);}discovery={phase:'ready',count:models.length,complete:data.complete!==false};}}catch{discovery.phase='failed';}finally{discoveryText();controls();}}
function consume(item){if(item.type==='compare_start'){pair={...pair,compare_id:item.compare_id,shared:item.shared};$('pair-id').textContent=`Compare ${item.compare_id.slice(0,8)}`;}const side=item.side;if(side&&state[side]){const current=state[side];if(item.type==='side_start'){current.phase='running';renderSide(side);}if(item.type==='event'){current.events.push(item.event);appendEvent(side,item.event);}if(item.type==='result'){current.result=item.result;current.phase=item.result.execution==='fixture'?'fixture':item.result.status==='incomplete'?'incomplete':'complete';renderSide(side);}if(item.type==='error'){current.error={code:item.code,message:item.message};current.phase='error';renderSide(side);}}if(item.type==='compare_end'){pair.outcomes=item.outcomes;$('compare-status').textContent=t('pairFinished');notify(pair.execution==='fixture'?t('fixtureNotice'):t('pairFinished'));$('download-pair').disabled=false;}}
async function compare(execution){if(busy)return;const prompt=$('prompt').value.trim();if(!prompt||(execution==='live'&&sides.some(side=>!$(side+'-model').value.trim()))){notify(t('validationError'),true);return;}const payload={execution,language,prompt,material:$('material').value};for(const side of sides)payload[side]={model_id:$(side+'-model').value.trim(),reasoning_effort:$(side+'-effort').value};state={left:{phase:'waiting',events:[],candidate:{...payload.left}},right:{phase:'queued',events:[],candidate:{...payload.right}}};pair={execution,input:payload};$('compare-status').textContent=t('running');$('pair-id').textContent='';$('download-pair').disabled=true;busy=true;for(const side of sides)renderSide(side);controls();notify(t(execution==='fixture'?'fixtureNotice':'runningNotice'));let ended=false;try{const response=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!response.ok)throw new Error('validation');const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const{value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let newline;while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(line){const item=JSON.parse(line);consume(item);if(item.type==='compare_end')ended=true;}}if(done)break;}if(!ended)throw new Error('stream');}catch(error){for(const side of sides)if(!state[side].result){state[side].phase='error';renderSide(side);}pair.error=error.message==='validation'?'validationError':'streamFailed';$('compare-status').textContent=t(pair.error);notify(t(pair.error),true);$('download-pair').disabled=!sides.some(side=>state[side].result);}finally{busy=false;controls();}}
$('language').addEventListener('click',()=>{const wasDefault=$('prompt').value===t('prompt');language=language==='zh'?'en':'zh';localStorage.setItem('context-lab-language',language);if(wasDefault)$('prompt').value=t('prompt');translate();});$('refresh-models').addEventListener('click',refreshModels);sides.forEach(side=>$(side+'-model').addEventListener('input',controls));$('fixture').addEventListener('click',()=>compare('fixture'));$('compare').addEventListener('click',()=>compare('live'));$('save-memory').addEventListener('click',async()=>{try{const response=await fetch('/api/memory',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('memory').value,approved:true})});if(!response.ok)throw new Error();$('memory-status').textContent=t('saved');}catch{$('memory-status').textContent=t('saveFailed');}});$('download-pair').addEventListener('click',()=>{if(!pair)return;const blob=new Blob([JSON.stringify({...pair,sides:state},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`context-lab-compare-${(pair.compare_id||'partial').slice(0,8)}.json`;link.click();URL.revokeObjectURL(url);});translate();fetch('/api/config').then(response=>response.json()).then(value=>{config=value;$('memory').value=config.memory;translate();}).catch(()=>notify(t('streamFailed'),true));
