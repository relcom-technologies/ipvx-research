/* RFC discussion is plain text. Portal roles come only from the verified backend. */
(()=>{
 'use strict';
 const discussion=document.querySelector('[data-community-rfc]');
 const account=document.querySelector('.community-account');
 if(!discussion&&!account)return;
 const $=(selector,root=document)=>root.querySelector(selector);
 const node=(tag,text,className)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=String(text);if(className)item.className=className;return item;};
 const api='/community/v1';
 const requests=new Map();
 const votesInFlight=new Set();
 let session=null;
 const roleNames={participant:"Participante",moderator:"Moderador",maintainer:"Mantenedor",admin:"Administrador"};
 const statusNames={pending:"En moderación · aún no publicado",published:"Publicado",hidden:"Oculto por moderación"};
 const errors={access_blocked:"El administrador bloqueó tu participación. Puedes seguir accediendo a la cuenta.",sign_in_required:"La sesión de participación caducó. Accede de nuevo mediante Relcom ID.",verified_account_required:"Para enviar necesitas cuenta con correo confirmado.",role_required:"Este rol ya no está disponible. Actualiza tus permisos.",write_rate_exceeded:"Demasiadas acciones en poco tiempo. Inténtalo más tarde.",pending_limit_reached:"Se alcanzó el límite de mensajes pendientes. Espera la revisión de los anteriores.",body_too_large:"El texto es demasiado largo para una entrada. Acórtalo o divídelo en mensajes.",invalid_text:"Revisa el texto y su longitud.",proposal_title_required:"Indica el título de la propuesta.",entry_not_found:"La entrada no está disponible o ya no está publicada.",participant_not_found:"Aún no hay participante registrado con ese número.",bootstrap_admin_requires_operator_migration:"El administrador inicial solo puede cambiarse mediante una acción separada del operador.",idempotency_key_reused_with_different_request:"La solicitud cambió al reenviarse. Guarda el texto y actualiza la página.",invalid_role_change:"Revisa número de participante, rol y acción."};
 const describe=error=>errors[error.code]||(error.status===401?"Accede mediante Relcom ID para continuar.":error.status===403?"Acción no permitida. Comprueba sesión y rol.":error.status===429?"Se alcanzó temporalmente el límite de acciones. Inténtalo después.":error.status===413?"Mensaje demasiado largo. Acorta el texto.":"El debate no está disponible temporalmente. El formulario conserva el texto; inténtalo de nuevo.");
 const get=async(path,options={})=>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try{
   const response=await fetch(api+path,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal,headers:{Accept:'application/json',...(options.headers||{})}});
   let data;try{data=await response.json();}catch{if(response.ok)throw new Error('invalid_json_response');data={};}
   if(!response.ok){const error=new Error('community_request');error.status=response.status;error.code=data.error;throw error;}
   if(!data||typeof data!=='object')throw new Error('invalid_response');
   return data;
  }finally{clearTimeout(timer);}
 };
 const post=async(path,body,validate=()=>true)=>{
  const serialized=JSON.stringify(body);
  if(new TextEncoder().encode(serialized).length>12000){const error=new Error('body_size');error.code='body_too_large';throw error;}
  const fingerprint=path+'\n'+serialized;
  // A changed payload is a new intent. An unchanged retry keeps its key;
  // returning to an older payload must not replay a superseded cached effect.
  for(const pending of requests.keys())if(pending.startsWith(path+'\n')&&pending!==fingerprint)requests.delete(pending);
  if(!requests.has(fingerprint)){
   if(requests.size>=30)throw new Error('too_many_pending_requests');
   const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);
   requests.set(fingerprint,Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join(''));
  }
  const result=await get(path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':requests.get(fingerprint)},body:serialized});
  if(!validate(result))throw new Error('invalid_mutation_response');
  requests.delete(fingerprint);return result;
 };
 const setMessage=(element,text,isError=false)=>{element.textContent=text;element.classList.toggle('community-error',isError);};
 const date=value=>{const stamp=typeof value==='number'?value:Date.parse(value);return Number.isFinite(stamp)?new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:'short'}).format(stamp):"Fecha no indicada";};
 const validEntry=entry=>entry&&Number.isSafeInteger(entry.id)&&entry.id>0&&typeof entry.text==='string'&&typeof entry.kind==='string'&&typeof entry.status==='string';
 const signedIn=()=>session?.authenticated===true&&session?.access!=='blocked';
 const privileged=role=>signedIn()&&session.roles.includes(role);
 const disableForm=(form,disabled)=>{for(const control of form.querySelectorAll('button,input,select,textarea'))control.disabled=disabled;};
 const clearPrivileges=()=>{
  session=null;
  for(const selector of ['.community-moderation','.community-admin']){const area=$(selector);if(area)area.hidden=true;}
  for(const selector of ['.community-moderation-list','.community-lookup-result','.community-audit-list','.community-own-list'])$(selector)?.replaceChildren();
  for(const button of document.querySelectorAll('.community-vote-controls button'))button.disabled=true;
  if(account){$('.community-account-details',account).hidden=true;$('.community-account-retry',account).hidden=false;setMessage($('.community-account-status',account),"Los permisos cambiaron o la sesión terminó. Comprueba el acceso y vuelve a cargar los permisos.");}
  if(discussion){$('.community-submit',discussion).hidden=true;$('.community-own',discussion).hidden=true;$('.community-sign-in',discussion).hidden=false;}
 };
 const handleAccessError=error=>{if(error.status===401||error.status===403)clearPrivileges();};
 async function loadSession(){
  const data=await get('/session');
  if(typeof data.authenticated!=='boolean'||!Array.isArray(data.roles))throw new Error('invalid_session');
  if(data.authenticated&&(!data.author||typeof data.author.id!=='string'||typeof data.author.label!=='string'))throw new Error('invalid_author');
  session={...data,roles:data.roles.filter(role=>Object.hasOwn(roleNames,role))};return session;
 }
 function entryView(entry,{moderate=false}={}){
  const article=node('article',undefined,'community-entry');article.dataset.entryId=String(entry.id);
  if(entry.title)article.append(node('h3',entry.title));
  article.append(node('p',(entry.author?.label||"Participante")+' · '+date(entry.createdAt)+' · № '+entry.id,'community-entry-meta'));
  const state=node('p',undefined,'community-entry-state');state.append(node('span',statusNames[entry.status]||"Estado pendiente de confirmar",'badge'+(entry.status==='pending'?' warn':'')));article.append(state);
  article.append(node('p',entry.text,'community-entry-text'));
  if(/^rfc-\d{4}$/.test(entry.rfc||'')){const p=node('p');const link=node('a',"Abrir "+entry.rfc.toUpperCase());link.href=entry.rfc+'.es.html#discussion';p.append(link);article.append(p);}
  if(entry.kind==='proposal'&&entry.status==='published')article.append(voteView(entry));
  if(moderate)article.append(moderationForm(entry));
  return article;
 }
 function voteView(entry){
  const area=node('div',undefined,'community-vote'),counts=node('p',undefined,'community-vote-counts'),controls=node('div',undefined,'community-vote-controls'),status=node('p','','community-vote-status');status.setAttribute('role','status');
  const showCounts=item=>{const value=item.votes?.counts||{},text="Orientativo: a favor "+(Number.isSafeInteger(value.yes)?value.yes:0)+", en contra "+(Number.isSafeInteger(value.no)?value.no:0)+", abstenciones "+(Number.isSafeInteger(value.abstain)?value.abstain:0)+". No equivale a aceptar el RFC.";counts.textContent=text;for(const output of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-counts'))output.textContent=text;};
  showCounts(entry);area.append(counts);
  if(signedIn()){
   for(const [value,label] of [['yes',"A favor"],['no',"En contra"],['abstain',"Me abstengo"],['withdraw',"Retirar opinión"]]){
    const button=node('button',label);button.type='button';
    button.addEventListener('click',async()=>{
     if(votesInFlight.has(entry.id))return;votesInFlight.add(entry.id);
     for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=true;
     setMessage(status,"Guardando opinión…");
     try{const result=await post('/entries/'+entry.id+'/vote',{value},data=>validEntry(data.entry));showCounts(result.entry);setMessage(status,value==='withdraw'?"Opinión retirada.":"Guardado: "+label.toLowerCase()+". Puedes cambiar o retirar la opinión.");}
     catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
     finally{votesInFlight.delete(entry.id);for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=!signedIn();}
    });controls.append(button);
   }
   area.append(controls);
  }else area.append(node('p',"Accede para dejar una opinión orientativa."));
  area.append(status);return area;
 }
 function moderationForm(entry){
  const form=node('form',undefined,'community-moderation-action'),id='reason-'+entry.id+'-'+crypto.getRandomValues(new Uint32Array(1))[0];
  const label=node('label',"Motivo de la decisión");label.htmlFor=id;
  const reason=node('textarea');reason.id=id;reason.name='reason';reason.rows=3;reason.minLength=3;reason.maxLength=1000;reason.required=true;
  const actions=node('div',undefined,'community-actions'),status=node('p','','community-moderation-status');status.setAttribute('role','status');
  for(const [value,text] of [['publish',"Publicar entrada"],['hide',"Ocultar entrada"]]){const button=node('button',text,'button'+(value==='hide'?' secondary':''));button.type='submit';button.name='action';button.value=value;actions.append(button);}
  form.append(label,reason,actions,status);
  form.addEventListener('submit',async event=>{
   event.preventDefault();const action=event.submitter?.value;if(!['publish','hide'].includes(action)||!form.reportValidity())return;
   const body={action,reason:reason.value.trim()};disableForm(form,true);setMessage(status,"Guardando decisión de moderación…");
   try{const result=await post('/entries/'+entry.id+'/moderation',body,data=>validEntry(data.entry));form.closest('.community-entry').replaceWith(entryView(result.entry,{moderate:true}));const output=$('.community-moderation-status');if(output)setMessage(output,"Entrada n.º "+entry.id+(action==='publish'?" publicada.":" oculta.")+" No se modificó el texto fuente del RFC.");}
   catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
   finally{disableForm(form,false);}
  });return form;
 }
 if(location.hostname==='www.ipvx.org'){
  const target=discussion||account;target.replaceChildren(node('h2',"Debate en la dirección principal"),node('p',"Para acceder y participar, abre la dirección principal. Los textos públicos están disponibles aquí sin iniciar sesión."));
  const link=node('a',"Abrir participación en ipvx.org",'button');link.href='https://ipvx.org'+location.pathname+(discussion?'#discussion':'#community');target.append(link);return;
 }
 if(discussion){
  const rfc=discussion.dataset.communityRfc;if(!/^rfc-\d{4}$/.test(rfc))return;
  const status=$('.community-session-status',discussion),form=$('.community-submit',discussion),list=$('.community-public',discussion),more=$('.community-public-more',discussion),retry=$('.community-public-retry',discussion),own=$('.community-own',discussion),ownList=$('.community-own-list',discussion),ownMore=$('.community-own-more',discussion);
  let kind='comment',before=null,ownBefore=null,loadVersion=0,ownVersion=0;
  const entriesPath=(mine,cursor)=>'/rfcs/'+rfc+'/entries?kind='+kind+'&limit=25'+(mine?'&mine=1':'')+(cursor?'&before='+cursor:'');
  async function loadPublic(append=false){
   const version=++loadVersion;retry.hidden=true;more.hidden=true;
   if(!append)list.replaceChildren(node('p',"Cargando el debate publicado…"));
   try{const data=await get(entriesPath(false,append?before:null));if(version!==loadVersion)return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)||x.status!=='published'))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry));if(!list.children.length)list.append(node('p',kind==='proposal'?"Aún no hay propuestas publicadas.":"Aún no hay comentarios publicados."));before=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=before===null;}
   catch(error){if(version!==loadVersion)return;if(!append)list.replaceChildren(node('p',"No se pudo cargar el debate. El RFC y sus fuentes están disponibles independientemente del servicio."));retry.hidden=false;}
  }
  async function loadOwn(append=false){
   const version=++ownVersion;
   ownMore.hidden=true;if(!signedIn())return;
   if(!append)ownList.replaceChildren(node('p',"Comprobando tus mensajes…"));
   try{const data=await get(entriesPath(true,append?ownBefore:null));if(version!==ownVersion||!signedIn())return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)ownList.replaceChildren();for(const entry of data.entries)ownList.append(entryView(entry));if(!ownList.children.length)ownList.append(node('p',"Aún no hay mensajes de este tipo."));ownBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;ownMore.hidden=ownBefore===null;}
   catch(error){if(version!==ownVersion)return;handleAccessError(error);ownList.replaceChildren(node('p',describe(error),'community-error'));}
  }
  const chooseKind=value=>{kind=value;before=null;ownBefore=null;for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.setAttribute('aria-pressed',String(button.dataset.entryKind===value));loadPublic();if(signedIn())loadOwn();};
  for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.addEventListener('click',()=>chooseKind(button.dataset.entryKind));
  more.addEventListener('click',()=>loadPublic(true));retry.addEventListener('click',()=>loadPublic());ownMore.addEventListener('click',()=>loadOwn(true));
  form.elements.kind.addEventListener('change',()=>{form.elements.title.required=form.elements.kind.value==='proposal';});
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(!form.reportValidity())return;
   const body={kind:form.elements.kind.value,title:form.elements.title.value.trim(),text:form.elements.text.value.trim()},feedback=$('.community-submit-status',form);
   disableForm(form,true);setMessage(feedback,"Enviando a moderación…");
   try{const data=await post('/rfcs/'+rfc+'/entries',body,result=>validEntry(result.entry)&&result.entry.status==='pending');form.elements.title.value='';form.elements.text.value='';setMessage(feedback,"Mensaje n.º "+data.entry.id+" en moderación. De momento solo lo veis tú y los moderadores.");chooseKind(body.kind);own.open=true;}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  (async()=>{try{await loadSession();if(signedIn()){setMessage(status,session.author.label+" · puedes enviar un mensaje a moderación.");form.hidden=false;own.hidden=false;loadOwn();}else{setMessage(status,"El debate se puede leer sin iniciar sesión.");$('.community-sign-in',discussion).hidden=false;}}catch{setMessage(status,"No se pudo comprobar el acceso. El debate publicado sigue disponible.");$('.community-sign-in',discussion).hidden=false;}finally{loadPublic();}})();
 }
 if(account){
  const status=$('.community-account-status',account),details=$('.community-account-details',account),retry=$('.community-account-retry',account),moderation=$('.community-moderation'),admin=$('.community-admin');
  let queueBefore=null,auditBefore=null;
  async function loadQueue(append=false){
   const list=$('.community-moderation-list'),feedback=$('.community-moderation-status'),more=$('.community-moderation-more');more.hidden=true;setMessage(feedback,"Cargando cola privada…");
   try{const data=await get('/moderation?limit=50'+(append&&queueBefore?'&before='+queueBefore:''));if(!privileged('moderator')&&!privileged('admin'))return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry,{moderate:true}));queueBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=queueBefore===null;setMessage(feedback,data.entries.length?"Entradas cargadas: "+data.entries.length+'.':append?"Esta es toda la cola.":"No hay mensajes pendientes de moderación.");}
   catch(error){handleAccessError(error);list.replaceChildren();setMessage(feedback,describe(error),true);}
  }
  async function loadAudit(append=false){
   const list=$('.community-audit-list'),more=$('.community-audit-more');more.hidden=true;if(!append)list.replaceChildren(node('p',"Cargando registro privado…"));
   const labels={configure_admin:"Administrador inicial configurado",submit_comment:"Comentario enviado",submit_proposal:"Propuesta enviada",publish:"Entrada publicada",hide:"Entrada oculta",advisory_vote:"Opinión orientativa modificada",grant_role:"Rol asignado",revoke_role:"Rol retirado"};
   try{const data=await get('/audit?limit=50'+(append&&auditBefore?'&before='+auditBefore:''));if(!privileged('admin'))return;if(!Array.isArray(data.events))throw new Error('invalid_audit');if(!append)list.replaceChildren();for(const entry of data.events){const row=node('article',undefined,'community-audit-event');row.append(node('h3',labels[entry.action]||"Acción del portal"),node('p','№ '+entry.id+' · '+date(Number(entry.at)*1000),'small'),node('p',"Participante: "+entry.actor+" · objeto: "+entry.target));let detail;try{detail=JSON.parse(entry.detail);}catch{detail={};}if(typeof detail.reason==='string')row.append(node('p',"Motivo: "+detail.reason));if(typeof detail.role==='string')row.append(node('p',"Rol: "+(roleNames[detail.role]||detail.role)));list.append(row);}if(!data.events.length&&!append)list.append(node('p',"Aún no hay acciones."));auditBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=auditBefore===null;}
   catch(error){handleAccessError(error);list.replaceChildren(node('p',describe(error),'community-error'));}
  }
  async function loadAccount(){
   retry.hidden=true;details.hidden=true;moderation.hidden=true;admin.hidden=true;setMessage(status,"Comprobando roles en el servidor…");
   try{await loadSession();if(session?.access==='blocked'){setMessage(status,"El administrador bloqueó la participación en debates. Se conserva el acceso a la cuenta.",true);return;}if(!signedIn()){setMessage(status,"Accede arriba con Relcom ID. La lectura pública y preparar propuestas GitHub no requieren iniciar sesión.");return;}$('.community-author-label',account).textContent=session.author.label;$('.community-author-id',account).textContent=session.author.id;$('.community-role-labels',account).textContent=session.roles.map(x=>roleNames[x]).join(', ');details.hidden=false;setMessage(status,"Cuenta confirmada. Los roles se muestran según el servidor.");if(privileged('moderator')||privileged('admin')){moderation.hidden=false;loadQueue();}if(privileged('admin')){admin.hidden=false;loadAudit();}}
   catch{clearPrivileges();setMessage(status,"No se pudieron cargar los roles. Acceso y materiales públicos se verifican por separado; inténtalo otra vez.",true);retry.hidden=false;}
  }
  retry.addEventListener('click',loadAccount);$('.community-moderation-refresh').addEventListener('click',()=>loadQueue());$('.community-audit-refresh').addEventListener('click',()=>loadAudit());$('.community-moderation-more').addEventListener('click',()=>loadQueue(true));$('.community-audit-more').addEventListener('click',()=>loadAudit(true));
  $('.community-entry-lookup').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;const id=Number(form.elements.entryId.value),target=$('.community-lookup-result');if(!Number.isSafeInteger(id)||id<1)return;
   disableForm(form,true);target.replaceChildren(node('p',"Cargando entrada…"));
   try{const data=await get('/entries/'+id);if(!validEntry(data.entry))throw new Error('invalid_entry');target.replaceChildren(entryView(data.entry,{moderate:true}));}
   catch(error){handleAccessError(error);target.replaceChildren(node('p',describe(error),'community-error'));}
   finally{disableForm(form,false);}
  });
  $('.community-role-form').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;
   const body={authorId:form.elements.authorId.value.trim(),role:form.elements.role.value,action:form.elements.action.value,reason:form.elements.reason.value.trim()},feedback=$('.community-role-status',form);
   disableForm(form,true);setMessage(feedback,"Guardando cambio de rol…");
   try{const data=await post('/roles',body,result=>Array.isArray(result.roles)&&typeof result.authorId==='string');setMessage(feedback,"Cambio guardado para "+body.authorId+". Roles: "+(data.roles.map(x=>roleNames[x]||x).join(', ')||"participante")+". No cambiaron el derecho de voto ni el acceso a la red.");form.elements.reason.value='';loadAudit();}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  loadAccount();
 }
})();
