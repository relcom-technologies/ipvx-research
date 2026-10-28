/* Private portal administration; the backend checks every read and mutation. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 if(!$('admin-private'))return;
 const roleNames={participant:"Participante",moderator:"Moderador",maintainer:"Mantenedor",admin:"Administrador"};
 const actions={configure_admin:"Administrador inicial",grant_role:"Rol asignado",revoke_role:"Rol retirado",block_access:"Participación bloqueada",restore_access:"Acceso restaurado",publish:"Comentario publicado",hide:"Entrada oculta",submit_comment:"Comentario enviado",submit_proposal:"Propuesta enviada",advisory_vote:"Voto orientativo"};
 const messages={protected_admin:"No puedes bloquearte ni bloquear al administrador inicial.",participant_blocked:"Restaura primero el acceso del usuario.",bootstrap_admin_requires_operator_migration:"El rol del administrador inicial está protegido.",participant_not_found:"Usuario no encontrado. Actualiza la lista.",write_rate_exceeded:"Demasiados cambios. Inténtalo más tarde.",invalid_text:"Indica un motivo de entre 3 y 1 000 caracteres.",access_blocked:"Tu participación en el portal está bloqueada."};
 const keys=new Map();
 let session=null, selected=null, members=[], after=null, queueBefore=null, auditBefore=null, version=0, queueVersion=0, auditVersion=0, checking=false, mutating=false;
 const el=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;};
 const stamp=value=>{const n=Date.parse(value);return Number.isFinite(n)?new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:'short'}).format(n):"Sin datos";};
 const errorText=e=>messages[e.code]||(e.status===401?"Sesión terminada. Accede de nuevo.":e.status===403?"Acción no disponible: cambiaron los permisos.":"No se pudo obtener confirmación del servidor. Repite con los mismos datos.");
 function lock(text,login=false){
  session=null;selected=null;members=[];version++;queueVersion++;auditVersion++;after=null;queueBefore=null;auditBefore=null;
  $('admin-private').hidden=true;$('selected-user').hidden=true;
  for(const id of ['admin-members','admin-queue','admin-audit'])$(id).replaceChildren();
  for(const id of ['selected-user-name','selected-user-id','selected-user-summary'])$(id).textContent='';
  for(const form of [$('admin-role-form'),$('admin-access-form')])form.reset();
  $('admin-status').textContent=text;$('admin-login').hidden=!login;$('admin-retry').hidden=false;
 }
 async function request(path,options={}){
  const r=await fetch('/community/v1'+path,{credentials:'same-origin',cache:'no-store',...options,headers:{Accept:'application/json',...options.headers}});
  const data=await r.json();
  if(!r.ok){const e=new Error('request_failed');e.status=r.status;e.code=data?.error;if(r.status===401||r.status===403)lock(errorText(e),r.status===401);throw e;}
  return data;
 }
 async function post(path,body,valid){
  const payload=JSON.stringify(body),intent=path+'\n'+payload;
  for(const key of keys.keys())if(key.startsWith(path+'\n')&&key!==intent)keys.delete(key);
  if(!keys.has(intent)){if(keys.size>=30)throw new Error('pending_request_limit');keys.set(intent,crypto.randomUUID());}
  const data=await request(path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':keys.get(intent)},body:payload});
  if(!valid(data))throw new Error('invalid_confirmation');
  keys.delete(intent);return data;
 }
 const disable=(form,value)=>{for(const c of form.querySelectorAll('input,select,textarea,button'))c.disabled=value;};
 const validMember=m=>m&&/^member_[a-f0-9]{24}$/.test(m.id)&&typeof m.label==='string'&&m.label.length<=100&&Array.isArray(m.roles)&&m.roles.every(r=>Object.hasOwn(roleNames,r))&&['active','blocked'].includes(m.access)&&typeof m.protected==='boolean';
 function choose(member,focus=true){
  selected=member;$('selected-user').hidden=false;$('selected-user-name').textContent=member.label;$('selected-user-id').textContent=member.id;
  $('selected-user-summary').textContent=member.roles.map(r=>roleNames[r]).join(', ')+' · '+(member.access==='blocked'?"Participación bloqueada":"Acceso permitido")+" · Última visita: "+stamp(member.lastSeenAt);
  const button=$('admin-access-action');button.textContent=member.access==='blocked'?"Restaurar participación":"Bloquear la participación";
  button.disabled=member.access==='active'&&(member.protected||member.id===session?.author.id);
  if(button.disabled)$('admin-access-status').textContent="El acceso de este administrador está protegido.";
  for(const b of $('admin-members').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.member===member.id));
  if(focus)$('selected-user-heading').focus();
 }
 function memberRow(m){
  const row=el('div',undefined,'admin-member'),button=el('button');button.type='button';button.dataset.member=m.id;button.setAttribute('aria-pressed',String(m.id===selected?.id));
  button.append(el('strong',m.label),el('span',m.access==='blocked'?"Bloqueado":"Acceso permitido",'admin-member-state'+(m.access==='blocked'?' admin-blocked':'')),el('small',m.id+' · '+m.roles.map(r=>roleNames[r]).join(', ')+' · '+stamp(m.lastSeenAt)));
  button.disabled=mutating;
  button.addEventListener('click',()=>{if(mutating)return;if(selected?.id!==m.id){$('admin-role-form').reset();$('admin-access-form').reset();}for(const id of ['admin-role-status','admin-access-status'])$(id).textContent='';choose(m);});row.append(button);return row;
 }
 async function loadMembers(append=false){
  const generation=++version, form=$('admin-search'),params=new URLSearchParams({limit:'25',search:form.elements.search.value,access:form.elements.access.value});
  if(append&&after)params.set('after',after);
  $('admin-users-status').textContent="Cargando usuarios…";$('admin-members-more').hidden=true;
  try{
   const data=await request('/members?'+params);
   if(generation!==version||!session)return;
   if(!Array.isArray(data.members)||data.members.length>50||!data.members.every(validMember)||!Number.isSafeInteger(data.total)||data.total<0||!(data.nextAfter===null||/^member_[a-f0-9]{24}$/.test(data.nextAfter)))throw new Error('invalid_members');
   members=append?[...members,...data.members]:data.members;
   $('admin-members').replaceChildren(...members.map(memberRow));
   $('admin-users-status').textContent=data.total?`Encontrados: ${data.total}. Mostrados: ${members.length}.`:"No se encontraron usuarios para esta búsqueda.";
   after=data.nextAfter;$('admin-members-more').hidden=after===null;
   if(selected){const current=members.find(m=>m.id===selected.id);if(current)choose(current,false);else{selected=null;$('selected-user').hidden=true;}}
  }catch(e){if(generation===version)$('admin-users-status').textContent=errorText(e);}
 }
 function page(data,key){if(!Array.isArray(data[key])||!(data.nextBefore===null||Number.isSafeInteger(data.nextBefore)))throw new Error('invalid_page');return data[key];}
 async function loadQueue(append=false){
  const generation=++queueVersion;$('admin-queue-status').textContent="Cargando cola…";
  try{
   const data=await request('/moderation?limit=10'+(append&&queueBefore?'&before='+queueBefore:''));if(!session||generation!==queueVersion)return;
   const entries=page(data,'entries');const rows=[];
   for(const e of entries){
    if(!Number.isSafeInteger(e.id)||typeof e.text!=='string'||typeof e.title!=='string'||!/^rfc-000[1-7]$/.test(e.rfc))throw new Error('invalid_entry');
    const row=el('article',undefined,'admin-queue-entry');row.append(el('h3',e.title||"Comentario n.º"+e.id),el('p',e.rfc.toUpperCase()+' · '+e.author.label+' · '+stamp(e.createdAt),'small'),el('p',e.text,'admin-entry-text'));
    const form=el('form'),action=el('select'),reason=el('textarea');action.name='action';reason.name='reason';reason.required=true;reason.minLength=3;reason.maxLength=1000;reason.rows=2;
    for(const [v,label] of [['publish',"Publicar"],['hide',"Ocultar"]]){const o=el('option',label);o.value=v;action.append(o);}
    const a=el('label',"Decisión"),r=el('label',"Motivo");a.append(action);r.append(reason);const save=el('button',"Aplicar",'button secondary');save.type='submit';const status=el('p');status.setAttribute('role','status');form.append(a,r,save);row.append(form,status);
    form.addEventListener('submit',async event=>{event.preventDefault();if(!form.reportValidity())return;disable(form,true);status.textContent="Guardando decisión…";
     try{await post('/entries/'+e.id+'/moderation',{action:action.value,reason:reason.value},d=>d.entry?.id===e.id&&['published','hidden'].includes(d.entry.status));status.textContent="Decisión guardada.";if(session){await loadQueue();await loadAudit();}}
     catch(error){status.textContent=errorText(error);}finally{disable(form,false);}
    });rows.push(row);
   }
   if(!append)$('admin-queue').replaceChildren();$('admin-queue').append(...rows);
   queueBefore=data.nextBefore;$('admin-queue-more').hidden=queueBefore===null;$('admin-queue-status').textContent=!entries.length&&!append?"La cola está vacía.":"Cola cargada.";
  }catch(e){if(generation===queueVersion)$('admin-queue-status').textContent=errorText(e);}
 }
 async function loadAudit(append=false){
  const generation=++auditVersion;$('admin-audit-status').textContent="Cargando registro…";
  try{
   const data=await request('/audit?limit=10'+(append&&auditBefore?'&before='+auditBefore:''));if(!session||generation!==auditVersion)return;
   const events=page(data,'events'),rows=[];
   for(const e of events){
    if(typeof e.action!=='string'||typeof e.actor!=='string'||typeof e.target!=='string')throw new Error('invalid_audit');
    const row=el('article',undefined,'admin-log-entry');row.append(el('h3',actions[e.action]||e.action),el('p',stamp(typeof e.at==='number'?new Date(e.at*1000).toISOString():e.at)+' · '+e.actor),el('code',e.target));
    let detail;try{detail=JSON.parse(e.detail);}catch{detail={};}if(typeof detail.reason==='string')row.append(el('p',"Motivo: "+detail.reason));if(typeof detail.role==='string')row.append(el('p',"Rol: "+(roleNames[detail.role]||detail.role)));rows.push(row);
   }
   if(!append)$('admin-audit').replaceChildren();$('admin-audit').append(...rows);auditBefore=data.nextBefore;$('admin-audit-more').hidden=auditBefore===null;$('admin-audit-status').textContent=events.length?"Registro cargado.":"Aún no hay acciones.";
  }catch(e){if(generation===auditVersion)$('admin-audit-status').textContent=errorText(e);}
 }
 async function check(){
  if(checking)return;checking=true;
  try{
   const data=await request('/session');
   if(data.authenticated!==true){lock("Accede mediante Relcom ID para abrir la administración.",true);return;}
   if(!Array.isArray(data.roles)||!data.roles.includes('admin')||!/^member_[a-f0-9]{24}$/.test(data.author?.id)){lock(data.access==='blocked'?"Tu participación está bloqueada.":"Acceso confirmado. Esta página requiere el rol de administrador IPvX.");return;}
   session=data;$('admin-private').hidden=false;$('admin-login').hidden=true;$('admin-retry').hidden=true;$('admin-status').textContent="Has accedido como administrador IPvX. Las acciones quedan registradas.";
   await Promise.all([loadMembers(),loadQueue(),loadAudit()]);
  }catch{lock("No se pudieron comprobar los permisos. Inténtalo de nuevo.");}finally{checking=false;}
 }
 function mutationBusy(value){mutating=value;for(const form of [$('admin-role-form'),$('admin-access-form')])disable(form,value);for(const b of $('admin-members').querySelectorAll('button'))b.disabled=value;if(!value&&selected)choose(selected,false);}
 $('admin-role-form').addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget;if(mutating||!selected||!form.reportValidity())return;
  const target=selected.id,body={authorId:target,role:form.elements.role.value,action:form.elements.action.value,reason:form.elements.reason.value};mutationBusy(true);$('admin-role-status').textContent="Guardando rol…";
  try{await post('/roles',body,d=>d.authorId===target&&Array.isArray(d.roles)&&d.roles.every(r=>Object.hasOwn(roleNames,r)));$('admin-role-status').textContent="Rol guardado.";if(session){await loadMembers();await loadAudit();}}
  catch(error){$('admin-role-status').textContent=errorText(error);}finally{mutationBusy(false);}
 });
 $('admin-access-form').addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget;if(mutating||!selected||!form.reportValidity())return;
  const target=selected.id,action=selected.access==='blocked'?'restore':'block',body={action,reason:form.elements.reason.value};mutationBusy(true);$('admin-access-status').textContent="Guardando acceso…";
  try{await post('/members/'+target+'/access',body,d=>d.authorId===target&&d.access===(action==='block'?'blocked':'active'));$('admin-role-status').textContent='';$('admin-access-status').textContent=action==='block'?"Participación bloqueada.":"Acceso restaurado.";if(session){await loadMembers();await loadAudit();}}
  catch(error){$('admin-access-status').textContent=errorText(error);}finally{mutationBusy(false);}
 });
 $('admin-search').addEventListener('submit',e=>{e.preventDefault();loadMembers();});
 for(const id of ['admin-refresh','admin-retry'])$(id).addEventListener('click',check);
 $('admin-members-more').addEventListener('click',()=>loadMembers(true));$('admin-queue-refresh').addEventListener('click',()=>loadQueue());$('admin-queue-more').addEventListener('click',()=>loadQueue(true));$('admin-audit-refresh').addEventListener('click',()=>loadAudit());$('admin-audit-more').addEventListener('click',()=>loadAudit(true));
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
 window.addEventListener('pageshow',e=>{if(e.persisted){lock("Comprobando de nuevo los permisos…");check();}});
 check();
})();
