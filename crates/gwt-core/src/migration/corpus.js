'use strict';
const template=JSON.parse(document.getElementById('decision-data').textContent);
const reviewer=document.querySelector('[data-reviewer]');
const rows=[...document.querySelectorAll('[data-index]')];
const message=document.querySelector('[data-message]');
const search=document.querySelector('[data-search]');
const filter=document.querySelector('[data-filter]');
const bytes=value=>new TextEncoder().encode(value).length;
const nonblank=value=>/[^\p{White_Space}]/u.test(value);
function tell(text,error=false){message.textContent=text;message.classList.toggle('error',error);}
function exactKeys(value,keys){return value!==null && typeof value==='object' && !Array.isArray(value) && Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));}
function validate(value){
  if(!exactKeys(value,['kind','schemaVersion','reportIntegrity','reviewer','decisions']) || value.kind!==template.kind || value.schemaVersion!==1)throw new Error('Expected corpus migration decisions schema 1.');
  if(value.reportIntegrity!==template.reportIntegrity)throw new Error('Decisions belong to a different corpus transition.');
  if(typeof value.reviewer!=='string' || bytes(value.reviewer)>256 || /[\u0000-\u001f\u007f-\u009f]/.test(value.reviewer))throw new Error('Reviewer permits 256 UTF-8 bytes without controls.');
  if(!Array.isArray(value.decisions) || value.decisions.length!==rows.length)throw new Error('Decisions must cover every case exactly once.');
  const seen=new Set();
  for(const decision of value.decisions){
    if(!exactKeys(decision,['id','status','note']) || typeof decision.id!=='string' || seen.has(decision.id))throw new Error('Invalid or duplicate case decision.');
    const index=template.decisions.findIndex(row=>row.id===decision.id);
    if(index<0)throw new Error('Decisions must cover every case exactly once.');
    seen.add(decision.id);
    if(!['pending','accept','reject','needs_information'].includes(decision.status))throw new Error('Unknown decision status.');
    if(typeof decision.note!=='string' || bytes(decision.note)>4096)throw new Error('Notes permit 4096 UTF-8 bytes.');
    if(decision.status!=='pending' && (!nonblank(value.reviewer) || !nonblank(decision.note)))throw new Error('Non-pending choices require a reviewer and a note.');
    if(decision.status==='accept' && rows[index].dataset.ready!=='true')throw new Error('An unavailable case cannot be accepted.');
  }
}
function snapshot(){return {...template,reviewer:reviewer.value,decisions:rows.map((row,index)=>({id:template.decisions[index].id,status:row.querySelector('[data-status]').value,note:row.querySelector('[data-note]').value}))};}
function refresh(){
  const counts={pending:0,accept:0,reject:0,needs_information:0};let shown=0;
  rows.forEach(row=>{const status=row.querySelector('[data-status]').value;counts[status]++;const matches=filter.value==='all' || (filter.value==='changed' && row.dataset.changed==='true') || (filter.value==='unavailable' && row.dataset.ready!=='true') || (filter.value==='pending' && status==='pending');const text=row.querySelector('h2').textContent+' '+row.querySelector('p').textContent;row.hidden=!(matches && text.toLowerCase().includes(search.value.toLowerCase()));if(!row.hidden)shown++;});
  document.querySelector('[data-counts]').textContent=`${counts.accept} accepted · ${counts.pending} pending · ${counts.reject} rejected · ${counts.needs_information} need information`;
  document.querySelector('[data-empty]').hidden=shown!==0;
}
function download(text,name){const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.querySelector('[data-download]').addEventListener('click',()=>download(document.getElementById('report-data').textContent,'gwt-corpus-migration.json'));
document.querySelector('[data-save]').addEventListener('click',()=>{try{const value=snapshot();validate(value);download(JSON.stringify(value,null,2)+'\n','gwt-corpus-migration-decisions.json');tell('Decision download prepared. Assessment and export recheck every case.');}catch(error){tell(error.message,true);}});
function rejectDuplicateKeys(text){const stack=[];for(let index=0;index<text.length;index++){const ch=text[index];if(ch==='"'){const start=index++;while(index<text.length && text[index]!=='"'){if(text[index]==='\\')index++;index++;}const parent=stack[stack.length-1];if(parent && parent.object && parent.key){const key=JSON.parse(text.slice(start,index+1));if(parent.keys.has(key))throw new Error('Decision file contains a duplicate JSON key.');parent.keys.add(key);parent.key=false;}}else if(ch==='{' || ch==='['){stack.push({object:ch==='{',key:ch==='{',keys:new Set()});}else if(ch==='}' || ch===']'){stack.pop();}else if(ch===',' && stack.length && stack[stack.length-1].object){stack[stack.length-1].key=true;}}}
let loading=0;
document.querySelector('[data-load]').addEventListener('change',async event=>{const current=++loading;try{const file=event.target.files[0];if(!file)return;if(file.size>2097152)throw new Error('Decisions exceed two MiB.');const text=await file.text();if(current!==loading)return;const value=JSON.parse(text);rejectDuplicateKeys(text);validate(value);reviewer.value=value.reviewer;rows.forEach((row,index)=>{const decision=value.decisions.find(item=>item.id===template.decisions[index].id);row.querySelector('[data-status]').value=decision.status;row.querySelector('[data-note]').value=decision.note;});refresh();tell('Decisions restored for this exact corpus transition.');}catch(error){if(current===loading)tell(error.message,true);}finally{if(current===loading)event.target.value='';}});
search.addEventListener('input',refresh);filter.addEventListener('change',refresh);rows.forEach(row=>row.querySelector('[data-status]').addEventListener('change',refresh));
document.addEventListener('click',event=>{const link=event.target.closest('[data-operand]');if(!link)return;event.preventDefault();const target=document.getElementById(link.getAttribute('href').slice(1));if(!target)return;for(let node=target;node;node=node.parentElement){if(node.tagName==='DETAILS')node.open=true;}target.querySelector('details').open=true;target.scrollIntoView({block:'center'});});
refresh();
