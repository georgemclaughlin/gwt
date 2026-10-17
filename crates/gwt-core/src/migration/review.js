'use strict';
const template=JSON.parse(document.getElementById('decision-data').textContent);
const reviewer=document.querySelector('[data-reviewer]');
const status=document.querySelector('[data-status]');
const note=document.querySelector('[data-note]');
const message=document.querySelector('[data-message]');
const available=document.querySelector('main').dataset.candidate==='true';
const bytes=text=>new TextEncoder().encode(text).length;
function tell(text,error=false){message.textContent=text;message.classList.toggle('error',error);}
function validate(value){
  const keys=['kind','schemaVersion','proposalIntegrity','reviewer','status','note'];
  if(value===null || typeof value!=='object' || Array.isArray(value) || Object.keys(value).length!==keys.length || !keys.every(key=>Object.hasOwn(value,key)) || value.kind!==template.kind || value.schemaVersion!==1)throw new Error('Expected migration-decision schema version 1.');
  if(value.proposalIntegrity!==template.proposalIntegrity)throw new Error('This decision belongs to a different proposal.');
  if(typeof value.reviewer!=='string' || bytes(value.reviewer)>256 || /[\u0000-\u001f\u007f-\u009f]/.test(value.reviewer))throw new Error('Reviewer permits 256 UTF-8 bytes without control characters.');
  if(typeof value.note!=='string' || bytes(value.note)>4096)throw new Error('Note permits 4096 UTF-8 bytes.');
  if(!['pending','accept','reject','needs_information'].includes(value.status))throw new Error('Unknown migration decision.');
  if(value.status!=='pending' && (!/[^\p{White_Space}]/u.test(value.reviewer) || !/[^\p{White_Space}]/u.test(value.note)))throw new Error('A non-pending decision requires a reviewer and a note.');
  if(value.status==='accept' && !available)throw new Error('An unavailable candidate cannot be accepted.');
}
function download(text,name){const url=URL.createObjectURL(new Blob([text],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.querySelector('[data-download]').addEventListener('click',()=>download(document.getElementById('proposal-data').textContent,'gwt-migration-proposal.json'));
document.querySelector('[data-save]').addEventListener('click',()=>{try{const value={...template,reviewer:reviewer.value,status:status.value,note:note.value};validate(value);download(JSON.stringify(value,null,2)+'\n','gwt-migration-decision.json');tell('Decision download prepared. Keep the file for fresh assessment and export.');}catch(error){tell(error.message,true);}});
// Reject duplicate JSON keys instead of accepting JSON.parse's last value.
function rejectDuplicateKeys(text){const stack=[];for(let index=0;index<text.length;index++){const ch=text[index];if(ch==='"'){const start=index++;while(index<text.length && text[index]!=='"'){if(text[index]==='\\')index++;index++;}const parent=stack[stack.length-1];if(parent && parent.object && parent.key){const key=JSON.parse(text.slice(start,index+1));if(parent.keys.has(key))throw new Error('Decision file contains a duplicate JSON key.');parent.keys.add(key);parent.key=false;}}else if(ch==='{' || ch==='['){stack.push({object:ch==='{',key:ch==='{',keys:new Set()});}else if(ch==='}' || ch===']'){stack.pop();}else if(ch===',' && stack.length && stack[stack.length-1].object){stack[stack.length-1].key=true;}}}
let loading=0;
document.querySelector('[data-load]').addEventListener('change',async event=>{const current=++loading;try{const file=event.target.files[0];if(!file)return;if(file.size>32768)throw new Error('Decision file exceeds 32 KiB.');const text=await file.text();if(current!==loading)return;const value=JSON.parse(text);rejectDuplicateKeys(text);validate(value);reviewer.value=value.reviewer;status.value=value.status;note.value=value.note;tell('Decision restored for this exact proposal.');}catch(error){if(current===loading)tell(error.message,true);}finally{if(current===loading)event.target.value='';}});
document.addEventListener('click',event=>{const link=event.target.closest('[data-operand]');if(!link)return;event.preventDefault();const target=document.getElementById(link.getAttribute('href').slice(1));if(!target)return;for(let node=target;node;node=node.parentElement){if(node.tagName==='DETAILS')node.open=true;}target.querySelector('details').open=true;target.scrollIntoView({block:'center'});});
