"""Reviewed bounded DOM tools; webpage/model strings remain data only."""
DOM_TOOLS_VERSION='semantic-dom-3'

OBSERVE=r'''(() => {
 const state=globalThis.__appAgent ||= {ids:new WeakMap(),nodes:new Map(),next:2};
 state.nodes.clear();
 const identify=el=>{if(!state.ids.has(el))state.ids.set(el,state.next++);return state.ids.get(el);};
 const parent=el=>el.assignedSlot || el.parentElement || el.getRootNode().host || el.ownerDocument.defaultView?.frameElement;
 const ancestor=(el,selector)=>{for(let node=el,depth=0;node && depth++<64;node=parent(node))if(node.matches(selector))return true;return false;};
 const context=el=>{
  const path=[];let node=el,depth=0;
  while(node && depth++<64){
   if(node.parentElement){node=node.parentElement;continue;}
   const root=node.getRootNode();
   if(root.host){if(!root.host.isConnected)return null;path.push({kind:'shadow',host:identify(root.host)});node=root.host;continue;}
   const doc=node.ownerDocument;
   if(doc===document)return {url:el.ownerDocument.URL,path:path.reverse()};
   const frame=doc.defaultView?.frameElement;
   if(!frame || !frame.isConnected || frame.contentDocument!==doc || doc.URL.length>4096 || new URL(doc.URL).origin!==location.origin)return null;
   path.push({kind:'frame',host:identify(frame),url:doc.URL});node=frame;
  }
  return null;
 };
 const visible=el=>{
  const rect=el.getBoundingClientRect();if(!rect.width || !rect.height || !context(el))return false;
  let node=el,depth=0;
  for(;node && depth++<64;node=parent(node)){
   const s=node.ownerDocument.defaultView.getComputedStyle(node);
   if(s.display==='none' || s.visibility==='hidden' || s.visibility==='collapse' || s.contentVisibility==='hidden' || Number(s.opacity)===0)return false;
  }
  return !node;
 };
 state.visible=visible;
 const interactiveSelector='button,a[href],input,textarea,select,[contenteditable],[role=button],[role=textbox],[role=checkbox],[role=switch],[role=radio],[role=tab],[role=option],[role=menuitem],[role=menuitemcheckbox],[role=menuitemradio]';
 const editingRoot=el=>el.isContentEditable && !el.parentElement?.isContentEditable;
 const editorText=el=>el.textContent===''?'':el.innerText;
 const safeEditor=el=>editingRoot(el) && el.innerText.length<=2000 && el.innerHTML.length<=16000 && !ancestor(el,'[aria-readonly=true]') && !el.querySelector(interactiveSelector+',[contenteditable=false],iframe,img,video,audio,canvas,object,embed,script,style');
 const describe=(el,id) => {
  const tag=el.tagName.toLowerCase(),kind=(el.type||'').toLowerCase(),role=el.getAttribute('role')||'';
  const password=tag==='input' && (kind==='password' || /password|one.time|verification.code/i.test(el.autocomplete||''));
  const referenced=(el.getAttribute('aria-labelledby')||'').trim().split(/\s+/).slice(0,5).map(id=>el.getRootNode().getElementById?.(id)).filter(node=>node && visible(node)).map(node=>node.innerText.slice(0,300)).join(' ');
  const name=(el.getAttribute('aria-label') || referenced || Array.from(el.labels||[]).map(l=>l.innerText).join(' ') || (el.hasAttribute('contenteditable')?el.id:el.innerText) || el.getAttribute('placeholder') || el.name || el.id || tag).trim().slice(0,300);
  const enabled=!el.disabled && !el.matches(':disabled') && !ancestor(el,'[inert],[aria-disabled=true]');
  let actions=[],details={context:context(el)},type='Custom';
  if(role){details.role=role;for(const key of ['checked','selected','pressed','expanded','readonly','controls'])details[key]=el.getAttribute('aria-'+key);}
  if(el.hasAttribute('contenteditable'))details.editor={editable:el.isContentEditable,root:editingRoot(el),safe:safeEditor(el),mode:el.getAttribute('contenteditable'),markup:safeEditor(el)?el.innerHTML:null};
  if(enabled && !password){
   if(el.hasAttribute('contenteditable')){if(safeEditor(el))actions=['type'];}
   else if(tag==='textarea' || tag==='input' && ['text','search','email','url','tel','number',''].includes(kind)){if(!el.readOnly && !ancestor(el,'[aria-readonly=true]'))actions=['type'];}
   else if(tag==='input' && kind==='checkbox'){actions=['toggle'];details.toggle=el.checked?'on':'off';}
   else if(tag==='input' && kind==='radio'){actions=['click'];details.checked=el.checked;type='RadioButton';}
   else if(tag==='select'){
    details.options=Array.prototype.slice.call(el.options,0,80).map(o=>({value:o.value.slice(0,2000),label:o.label.slice(0,300),enabled:!o.disabled && !(o.parentElement.tagName==='OPTGROUP' && o.parentElement.disabled),selected:o.selected}));
    details.options_truncated=el.options.length>80;details.multiple=el.multiple;
    if(!details.options_truncated && !el.multiple && Array.from(el.options).every(o=>o.value.length<=2000 && o.label.length<=300))actions=['select'];
   }else if(['checkbox','switch','menuitemcheckbox'].includes(role)){
    type='CheckBox';if(['true','false'].includes(details.checked)){actions=['toggle'];details.toggle=details.checked==='true'?'on':'off';}
   }else if(role==='button' && ['true','false'].includes(details.pressed)){
    actions=['toggle'];details.toggle=details.pressed==='true'?'on':'off';type='ToggleButton';
   }else if(['radio','tab','option','menuitem','menuitemradio'].includes(role)){
    actions=['click'];type=role==='tab'?'TabItem':role==='radio' || role==='menuitemradio'?'RadioButton':role==='option'?'ListItem':'MenuItem';
   }else if(tag==='button' || tag==='a' || role==='button' || tag==='input' && ['submit','button','reset'].includes(kind))actions=['click'];
  }
  if(tag==='a' && el.href.length>4096)actions=[];
  const value=el.hasAttribute('contenteditable')?(safeEditor(el)?editorText(el):''):String(el.value||'');
  return {id,name,type:tag==='select'?'ComboBox':actions.includes('type')?'Edit':type!=='Custom'?type:actions.includes('toggle')?'CheckBox':tag==='a'?'Hyperlink':actions.includes('click')?'Button':'Custom',automation_id:'dom:'+id,enabled,visible:true,actions,value:password?'':value.slice(0,2000),password,state:details,href:tag==='a' && el.href.length<=4096?el.href:null};
 };
 state.describe=describe;
 const controls=[{id:0,name:'Browser page',type:'Window',automation_id:'',enabled:true,visible:true,actions:[],value:'',password:false,state:{}},
 {id:1,name:(document.body?.innerText||'').slice(0,16000),type:'Text',automation_id:'page:text',enabled:true,visible:true,actions:[],value:'',password:false,state:{}}];
 const coverage={elements:0,roots:0,frames_unavailable:0,frames_loading:0,limited:false};
 const roots=[{root:document,depth:0}];let interactive=0,outputs=0;
 while(roots.length){
  const entry=roots.pop();if(coverage.roots>=64){coverage.limited=true;break;}coverage.roots++;
  const walker=(entry.root.ownerDocument || document).createTreeWalker(entry.root,1);
  while(walker.nextNode()){
   const el=walker.currentNode;
   if(coverage.elements>=8000){coverage.limited=true;return {title:document.title,url:location.href,controls,coverage};}coverage.elements++;
   if(entry.depth<16 && roots.length<64){
    if(el.shadowRoot)roots.push({root:el.shadowRoot,depth:entry.depth+1});
    if(el.tagName==='IFRAME'){
     try{
      const doc=el.contentDocument;
      if(doc && doc.URL.length<=4096 && ['http:','https:'].includes(new URL(doc.URL).protocol) && new URL(doc.URL).origin===location.origin){
       if(doc.readyState!=='complete' && visible(el))coverage.frames_loading++;
       roots.push({root:doc,depth:entry.depth+1});
      }else if(!el.hasAttribute('srcdoc') && !(el.hasAttribute('sandbox') && !el.sandbox.contains('allow-same-origin')) && el.src && new URL(el.src).origin===location.origin && (!doc || doc.URL==='about:blank') && visible(el))coverage.frames_loading++;
      else coverage.frames_unavailable++;
     }catch(error){coverage.frames_unavailable++;}
    }
   }else if(el.shadowRoot || el.tagName==='IFRAME')coverage.limited=true;
   if(!visible(el))continue;
   if(el.matches(interactiveSelector)){
    if(el.isContentEditable && !editingRoot(el))continue;
    if(interactive>=200){coverage.limited=true;continue;}
    const id=identify(el);state.nodes.set(id,el);controls.push(describe(el,id));interactive++;
   }else if(el.matches('output,[role=status],[role=alert],p,div,span,h1,h2,h3,td,li')){
    if(el.children.length && !el.matches('output,[role=status],[role=alert]'))continue;
    if(ancestor(el,'button,a,label,'+interactiveSelector) || el.querySelector(interactiveSelector))continue;
    const text=(el.innerText||'').trim();if(!text)continue;
    if(outputs>=200){coverage.limited=true;continue;}
    const id=identify(el);state.nodes.set(id,el);
    controls.push({id,name:text.slice(0,2000),type:'Text',automation_id:'page:output',enabled:true,visible:true,actions:[],value:'',password:false,state:{truncated:text.length>2000,context:context(el)}});outputs++;
   }
  }
 }
 return {title:document.title,url:location.href,controls,coverage};
})()'''

ACT=r'''(payload => {
 if(location.href!==payload.url)throw Error('Browser page changed before dispatch.');
 const state=globalThis.__appAgent,el=state?.nodes.get(payload.control.id);
 if(!el || !el.isConnected)throw Error('Browser control was replaced.');
 const current=state.describe(el,payload.control.id);
 for(const key of ['name','type','automation_id','value','password','enabled','href'])if(current[key]!==payload.control[key])throw Error('Browser control changed before dispatch.');
 if(JSON.stringify(current.state)!==JSON.stringify(payload.control.state))throw Error('Browser control context or options changed before dispatch.');
 if(!state.visible(el) || !current.enabled || current.password || !current.actions.includes(payload.action.kind))throw Error('Browser control action is unavailable.');
 if(payload.action.kind==='select'){
  const options=current.state.options.filter(o=>o.value===payload.action.text);
  if(options.length!==1 || !options[0].enabled)throw Error('Browser selection must identify one enabled advertised option value.');
 }
 el.scrollIntoView({block:'center'});el.focus();
 const focused=state.describe(el,payload.control.id);
 if(location.href!==payload.url || JSON.stringify(focused)!==JSON.stringify(current) || !state.visible(el))throw Error('Browser control changed while gaining focus.');
 const view=el.ownerDocument.defaultView;
 if(payload.action.kind==='type' && current.state.editor){
  const doc=el.ownerDocument,selection=doc.getSelection(),range=doc.createRange();range.selectNodeContents(el);selection.removeAllRanges();selection.addRange(range);
  if(el.getRootNode().activeElement!==el || !state.visible(el) || !state.describe(el,payload.control.id).actions.includes('type'))throw Error('Rich-text focus or editability changed.');
  // Only our escaped text and fixed line breaks enter this editing command.
  // insertText inherits paragraph markup and can turn one newline into two.
  const literal=payload.action.text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\r\n?|\n/g,'<br>');
  if(!doc.execCommand(payload.action.text?'insertHTML':'delete',false,literal))throw Error('Rich-text application refused the editing operation.');
 }else if(payload.action.kind==='type' || payload.action.kind==='select'){
  const prototype=payload.action.kind==='select'?view.HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?view.HTMLTextAreaElement.prototype:view.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype,'value').set.call(el,payload.action.text);
  el.dispatchEvent(new view.Event('input',{bubbles:true,composed:true}));el.dispatchEvent(new view.Event('change',{bubbles:true,composed:true}));
 }else if(payload.action.kind==='toggle'){
  if(current.state.toggle!==payload.action.state)el.click();
 }else el.click();
 return true;
})'''
