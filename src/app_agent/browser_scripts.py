"""Reviewed scripts in an isolated world; webpage/model strings are data only."""
OBSERVE=r'''(() => {
 const state=globalThis.__appAgent ||= {ids:new WeakMap(),nodes:new Map(),next:2};
 const visible=el=>{
  const rect=el.getBoundingClientRect();if(!rect.width || !rect.height)return false;
  for(let node=el;node;node=node.parentElement){const s=getComputedStyle(node);if(s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || s.contentVisibility==='hidden' || Number(s.opacity)===0)return false;}
  return true;
 };
 state.visible=visible;
 const describe=(el,id) => {
  const tag=el.tagName.toLowerCase(),kind=(el.type||'').toLowerCase();
  const password=tag==='input' && (kind==='password' || /password|one.time|verification.code/i.test(el.autocomplete||''));
  const name=(el.getAttribute('aria-label') || Array.from(el.labels||[]).map(l=>l.innerText).join(' ') || el.innerText || el.getAttribute('placeholder') || el.name || el.id || tag).trim().slice(0,300);
  const enabled=!el.disabled && !el.matches(':disabled') && !el.closest('[inert]') && el.getAttribute('aria-disabled')!=='true';
  let actions=[];
  if(enabled && !password){
   if(tag==='textarea' || tag==='input' && ['text','search','email','url','tel','number',''].includes(kind)){if(!el.readOnly)actions=['type'];}
   else if(tag==='input' && kind==='checkbox')actions=['toggle'];
   else if(tag==='button' || tag==='a' || el.getAttribute('role')==='button' || tag==='input' && ['submit','button','reset'].includes(kind))actions=['click'];
  }
  if(tag==='a' && el.href.length>4096)actions=[];
  return {id,name,type:actions.includes('type')?'Edit':actions.includes('toggle')?'CheckBox':tag==='a'?'Hyperlink':actions.includes('click')?'Button':'Custom',automation_id:'dom:'+id,enabled,visible:true,actions,value:password?'':String(el.value||'').slice(0,2000),password,state:actions.includes('toggle')?{toggle:el.checked?'on':'off'}:{},href:tag==='a' && el.href.length<=4096?el.href:null};
 };
 state.describe=describe;
 const controls=[{id:0,name:'Browser page',type:'Window',automation_id:'',enabled:true,visible:true,actions:[],value:'',password:false,state:{}},
 {id:1,name:(document.body?.innerText||'').slice(0,16000),type:'Text',automation_id:'page:text',enabled:true,visible:true,actions:[],value:'',password:false,state:{}}];
 const nodes=document.querySelectorAll('button,a[href],input,textarea,select,[role=button]');
 for(const el of nodes){
  if(!visible(el))continue;
  if(controls.length>=202)break;
  if(!state.ids.has(el)){const id=state.next++;state.ids.set(el,id);state.nodes.set(id,el);}
  controls.push(describe(el,state.ids.get(el)));
 }
 let inspected=0,outputs=0;
 for(const el of document.querySelectorAll('output,[role=status],[role=alert],p,div,span,h1,h2,h3,td,li')){
  if(++inspected>4000 || outputs>=200)break;
  if(el.children.length && !el.matches('output,[role=status],[role=alert]'))continue;
  if(el.closest('button,a,label') || el.querySelector('input,textarea,button,select'))continue;
  const text=(el.innerText||'').trim();
  if(!text || !visible(el))continue;
  if(!state.ids.has(el)){const id=state.next++;state.ids.set(el,id);state.nodes.set(id,el);}
  controls.push({id:state.ids.get(el),name:text.slice(0,2000),type:'Text',automation_id:'page:output',enabled:true,visible:true,actions:[],value:'',password:false,state:{truncated:text.length>2000}});outputs++;
 }
 return {title:document.title,url:location.href,controls};
})()'''

ACT=r'''(payload => {
 if(location.href!==payload.url)throw Error('Browser page changed before dispatch.');
 const state=globalThis.__appAgent,el=state?.nodes.get(payload.control.id);
 if(!el || !el.isConnected)throw Error('Browser control was replaced.');
 const current=state.describe(el,payload.control.id);
 for(const key of ['name','type','automation_id','value','password','enabled','href'])if(current[key]!==payload.control[key])throw Error('Browser control changed before dispatch.');
 if(!state.visible(el) || !current.enabled || current.password || !current.actions.includes(payload.action.kind))throw Error('Browser control action is unavailable.');
 el.scrollIntoView({block:'center'});el.focus();
 if(payload.action.kind==='type'){
  const prototype=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype,'value').set.call(el,payload.action.text);
  el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
 }else if(payload.action.kind==='toggle'){
  if(el.checked!==(payload.action.state==='on'))el.click();
 }else el.click();
 return true;
})'''
