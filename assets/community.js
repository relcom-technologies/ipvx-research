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
 const roleNames={participant:'Участник',moderator:'Модератор',maintainer:'Сопровождающий',admin:'Администратор'};
 const statusNames={pending:'На модерации · пока не опубликовано',published:'Опубликовано',hidden:'Скрыто модератором'};
 const errors={access_blocked:'Ваше участие заблокировано администратором. Вход в аккаунт сохраняется.',sign_in_required:'Сеанс участия истёк. Войдите снова через Relcom ID.',verified_account_required:'Для отправки нужна учётная запись с подтверждённой почтой.',role_required:'Эта роль больше недоступна. Обновите права участия.',write_rate_exceeded:'Слишком много действий за короткое время. Попробуйте позже.',pending_limit_reached:'Достигнут предел сообщений на модерации. Дождитесь рассмотрения предыдущих.',body_too_large:'Текст слишком большой для одной записи. Сократите его или разделите на отдельные сообщения.',invalid_text:'Проверьте текст и его длину.',proposal_title_required:'Укажите заголовок предложения.',entry_not_found:'Запись недоступна или больше не опубликована.',participant_not_found:'Участник с таким номером ещё не зарегистрирован.',bootstrap_admin_requires_operator_migration:'Начального администратора можно изменить только отдельным действием оператора.',idempotency_key_reused_with_different_request:'Запрос изменился при повторной отправке. Обновите страницу, сохранив текст.',invalid_role_change:'Проверьте номер участника, роль и действие.'};
 const describe=error=>errors[error.code]||(error.status===401?'Войдите через Relcom ID, чтобы продолжить.':error.status===403?'Действие не разрешено. Проверьте вход и роль.':error.status===429?'Временно достигнут предел действий. Попробуйте позже.':error.status===413?'Сообщение слишком большое. Сократите текст.':'Сервис обсуждения временно недоступен. Текст сохранён в форме; попробуйте ещё раз.');
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
 const date=value=>{const stamp=typeof value==='number'?value:Date.parse(value);return Number.isFinite(stamp)?new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(stamp):'Дата не указана';};
 const validEntry=entry=>entry&&Number.isSafeInteger(entry.id)&&entry.id>0&&typeof entry.text==='string'&&typeof entry.kind==='string'&&typeof entry.status==='string';
 const signedIn=()=>session?.authenticated===true&&session?.access!=='blocked';
 const privileged=role=>signedIn()&&session.roles.includes(role);
 const disableForm=(form,disabled)=>{for(const control of form.querySelectorAll('button,input,select,textarea'))control.disabled=disabled;};
 const clearPrivileges=()=>{
  session=null;
  for(const selector of ['.community-moderation','.community-admin']){const area=$(selector);if(area)area.hidden=true;}
  for(const selector of ['.community-moderation-list','.community-lookup-result','.community-audit-list','.community-own-list'])$(selector)?.replaceChildren();
  for(const button of document.querySelectorAll('.community-vote-controls button'))button.disabled=true;
  if(account){$('.community-account-details',account).hidden=true;$('.community-account-retry',account).hidden=false;setMessage($('.community-account-status',account),'Права участия изменились или сеанс завершился. Проверьте вход и загрузите права повторно.');}
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
  article.append(node('p',(entry.author?.label||'Участник')+' · '+date(entry.createdAt)+' · № '+entry.id,'community-entry-meta'));
  const state=node('p',undefined,'community-entry-state');state.append(node('span',statusNames[entry.status]||'Статус уточняется','badge'+(entry.status==='pending'?' warn':'')));article.append(state);
  article.append(node('p',entry.text,'community-entry-text'));
  if(/^rfc-\d{4}$/.test(entry.rfc||'')){const p=node('p');const link=node('a','Открыть '+entry.rfc.toUpperCase());link.href=entry.rfc+'.html#discussion';p.append(link);article.append(p);}
  if(entry.kind==='proposal'&&entry.status==='published')article.append(voteView(entry));
  if(moderate)article.append(moderationForm(entry));
  return article;
 }
 function voteView(entry){
  const area=node('div',undefined,'community-vote'),counts=node('p',undefined,'community-vote-counts'),controls=node('div',undefined,'community-vote-controls'),status=node('p','','community-vote-status');status.setAttribute('role','status');
  const showCounts=item=>{const value=item.votes?.counts||{},text='Консультативно: за '+(Number.isSafeInteger(value.yes)?value.yes:0)+', против '+(Number.isSafeInteger(value.no)?value.no:0)+', воздержались '+(Number.isSafeInteger(value.abstain)?value.abstain:0)+'. Это не принятие RFC.';counts.textContent=text;for(const output of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-counts'))output.textContent=text;};
  showCounts(entry);area.append(counts);
  if(signedIn()){
   for(const [value,label] of [['yes','Поддерживаю'],['no','Против'],['abstain','Воздерживаюсь'],['withdraw','Отозвать мнение']]){
    const button=node('button',label);button.type='button';
    button.addEventListener('click',async()=>{
     if(votesInFlight.has(entry.id))return;votesInFlight.add(entry.id);
     for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=true;
     setMessage(status,'Сохраняем мнение…');
     try{const result=await post('/entries/'+entry.id+'/vote',{value},data=>validEntry(data.entry));showCounts(result.entry);setMessage(status,value==='withdraw'?'Мнение отозвано.':'Сохранено: '+label.toLowerCase()+'. Можно изменить или отозвать мнение.');}
     catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
     finally{votesInFlight.delete(entry.id);for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=!signedIn();}
    });controls.append(button);
   }
   area.append(controls);
  }else area.append(node('p','Войдите, чтобы оставить консультативное мнение.'));
  area.append(status);return area;
 }
 function moderationForm(entry){
  const form=node('form',undefined,'community-moderation-action'),id='reason-'+entry.id+'-'+crypto.getRandomValues(new Uint32Array(1))[0];
  const label=node('label','Причина решения');label.htmlFor=id;
  const reason=node('textarea');reason.id=id;reason.name='reason';reason.rows=3;reason.minLength=3;reason.maxLength=1000;reason.required=true;
  const actions=node('div',undefined,'community-actions'),status=node('p','','community-moderation-status');status.setAttribute('role','status');
  for(const [value,text] of [['publish','Опубликовать запись'],['hide','Скрыть запись']]){const button=node('button',text,'button'+(value==='hide'?' secondary':''));button.type='submit';button.name='action';button.value=value;actions.append(button);}
  form.append(label,reason,actions,status);
  form.addEventListener('submit',async event=>{
   event.preventDefault();const action=event.submitter?.value;if(!['publish','hide'].includes(action)||!form.reportValidity())return;
   const body={action,reason:reason.value.trim()};disableForm(form,true);setMessage(status,'Сохраняем решение модерации…');
   try{const result=await post('/entries/'+entry.id+'/moderation',body,data=>validEntry(data.entry));form.closest('.community-entry').replaceWith(entryView(result.entry,{moderate:true}));const output=$('.community-moderation-status');if(output)setMessage(output,'Запись № '+entry.id+(action==='publish'?' опубликована.':' скрыта.')+' Исходный текст RFC не изменён.');}
   catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
   finally{disableForm(form,false);}
  });return form;
 }
 if(location.hostname==='www.ipvx.org'){
  const target=discussion||account;target.replaceChildren(node('h2','Обсуждение на основном адресе'),node('p','Для входа и участия откройте основной адрес проекта. Публичные тексты доступны здесь без входа.'));
  const link=node('a','Открыть участие на ipvx.org','button');link.href='https://ipvx.org'+location.pathname+(discussion?'#discussion':'#community');target.append(link);return;
 }
 if(discussion){
  const rfc=discussion.dataset.communityRfc;if(!/^rfc-\d{4}$/.test(rfc))return;
  const status=$('.community-session-status',discussion),form=$('.community-submit',discussion),list=$('.community-public',discussion),more=$('.community-public-more',discussion),retry=$('.community-public-retry',discussion),own=$('.community-own',discussion),ownList=$('.community-own-list',discussion),ownMore=$('.community-own-more',discussion);
  let kind='comment',before=null,ownBefore=null,loadVersion=0,ownVersion=0;
  const entriesPath=(mine,cursor)=>'/rfcs/'+rfc+'/entries?kind='+kind+'&limit=25'+(mine?'&mine=1':'')+(cursor?'&before='+cursor:'');
  async function loadPublic(append=false){
   const version=++loadVersion;retry.hidden=true;more.hidden=true;
   if(!append)list.replaceChildren(node('p','Загружаем опубликованное обсуждение…'));
   try{const data=await get(entriesPath(false,append?before:null));if(version!==loadVersion)return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)||x.status!=='published'))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry));if(!list.children.length)list.append(node('p',kind==='proposal'?'Опубликованных предложений пока нет.':'Опубликованных комментариев пока нет.'));before=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=before===null;}
   catch(error){if(version!==loadVersion)return;if(!append)list.replaceChildren(node('p','Не удалось загрузить обсуждение. Текст RFC и исходники доступны независимо от сервиса.'));retry.hidden=false;}
  }
  async function loadOwn(append=false){
   const version=++ownVersion;
   ownMore.hidden=true;if(!signedIn())return;
   if(!append)ownList.replaceChildren(node('p','Проверяем ваши сообщения…'));
   try{const data=await get(entriesPath(true,append?ownBefore:null));if(version!==ownVersion||!signedIn())return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)ownList.replaceChildren();for(const entry of data.entries)ownList.append(entryView(entry));if(!ownList.children.length)ownList.append(node('p','Сообщений этого типа пока нет.'));ownBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;ownMore.hidden=ownBefore===null;}
   catch(error){if(version!==ownVersion)return;handleAccessError(error);ownList.replaceChildren(node('p',describe(error),'community-error'));}
  }
  const chooseKind=value=>{kind=value;before=null;ownBefore=null;for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.setAttribute('aria-pressed',String(button.dataset.entryKind===value));loadPublic();if(signedIn())loadOwn();};
  for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.addEventListener('click',()=>chooseKind(button.dataset.entryKind));
  more.addEventListener('click',()=>loadPublic(true));retry.addEventListener('click',()=>loadPublic());ownMore.addEventListener('click',()=>loadOwn(true));
  form.elements.kind.addEventListener('change',()=>{form.elements.title.required=form.elements.kind.value==='proposal';});
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(!form.reportValidity())return;
   const body={kind:form.elements.kind.value,title:form.elements.title.value.trim(),text:form.elements.text.value.trim()},feedback=$('.community-submit-status',form);
   disableForm(form,true);setMessage(feedback,'Отправляем на модерацию…');
   try{const data=await post('/rfcs/'+rfc+'/entries',body,result=>validEntry(result.entry)&&result.entry.status==='pending');form.elements.title.value='';form.elements.text.value='';setMessage(feedback,'Сообщение № '+data.entry.id+' на модерации. Пока его видите вы и модераторы.');chooseKind(body.kind);own.open=true;}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  (async()=>{try{await loadSession();if(signedIn()){setMessage(status,session.author.label+' · можно отправить сообщение на модерацию.');form.hidden=false;own.hidden=false;loadOwn();}else{setMessage(status,'Чтение обсуждения доступно без входа.');$('.community-sign-in',discussion).hidden=false;}}catch{setMessage(status,'Не удалось проверить вход. Опубликованное обсуждение остаётся доступным.');$('.community-sign-in',discussion).hidden=false;}finally{loadPublic();}})();
 }
 if(account){
  const status=$('.community-account-status',account),details=$('.community-account-details',account),retry=$('.community-account-retry',account),moderation=$('.community-moderation'),admin=$('.community-admin');
  let queueBefore=null,auditBefore=null;
  async function loadQueue(append=false){
   const list=$('.community-moderation-list'),feedback=$('.community-moderation-status'),more=$('.community-moderation-more');more.hidden=true;setMessage(feedback,'Загружаем приватную очередь…');
   try{const data=await get('/moderation?limit=50'+(append&&queueBefore?'&before='+queueBefore:''));if(!privileged('moderator')&&!privileged('admin'))return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry,{moderate:true}));queueBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=queueBefore===null;setMessage(feedback,data.entries.length?'Загружено записей: '+data.entries.length+'.':append?'Это вся очередь.':'Нет сообщений, ожидающих модерации.');}
   catch(error){handleAccessError(error);list.replaceChildren();setMessage(feedback,describe(error),true);}
  }
  async function loadAudit(append=false){
   const list=$('.community-audit-list'),more=$('.community-audit-more');more.hidden=true;if(!append)list.replaceChildren(node('p','Загружаем приватный журнал…'));
   const labels={configure_admin:'Настроен начальный администратор',submit_comment:'Отправлен комментарий',submit_proposal:'Отправлено предложение',publish:'Запись опубликована',hide:'Запись скрыта',advisory_vote:'Изменено консультативное мнение',grant_role:'Назначена роль',revoke_role:'Роль отозвана'};
   try{const data=await get('/audit?limit=50'+(append&&auditBefore?'&before='+auditBefore:''));if(!privileged('admin'))return;if(!Array.isArray(data.events))throw new Error('invalid_audit');if(!append)list.replaceChildren();for(const entry of data.events){const row=node('article',undefined,'community-audit-event');row.append(node('h3',labels[entry.action]||'Действие портала'),node('p','№ '+entry.id+' · '+date(Number(entry.at)*1000),'small'),node('p','Участник: '+entry.actor+' · объект: '+entry.target));let detail;try{detail=JSON.parse(entry.detail);}catch{detail={};}if(typeof detail.reason==='string')row.append(node('p','Причина: '+detail.reason));if(typeof detail.role==='string')row.append(node('p','Роль: '+(roleNames[detail.role]||detail.role)));list.append(row);}if(!data.events.length&&!append)list.append(node('p','Действий пока нет.'));auditBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=auditBefore===null;}
   catch(error){handleAccessError(error);list.replaceChildren(node('p',describe(error),'community-error'));}
  }
  async function loadAccount(){
   retry.hidden=true;details.hidden=true;moderation.hidden=true;admin.hidden=true;setMessage(status,'Проверяем роли на сервере…');
   try{await loadSession();if(session?.access==='blocked'){setMessage(status,'Участие в обсуждениях заблокировано администратором. Вход в аккаунт сохраняется.',true);return;}if(!signedIn()){setMessage(status,'Войдите выше через Relcom ID. Публичное чтение и подготовка предложения в GitHub доступны без входа.');return;}$('.community-author-label',account).textContent=session.author.label;$('.community-author-id',account).textContent=session.author.id;$('.community-role-labels',account).textContent=session.roles.map(x=>roleNames[x]).join(', ');details.hidden=false;setMessage(status,'Учётная запись подтверждена. Роли портала показаны по данным сервера.');if(privileged('moderator')||privileged('admin')){moderation.hidden=false;loadQueue();}if(privileged('admin')){admin.hidden=false;loadAudit();}}
   catch{clearPrivileges();setMessage(status,'Не удалось загрузить роли. Вход и публичные материалы проверяются отдельно; попробуйте ещё раз.',true);retry.hidden=false;}
  }
  retry.addEventListener('click',loadAccount);$('.community-moderation-refresh').addEventListener('click',()=>loadQueue());$('.community-audit-refresh').addEventListener('click',()=>loadAudit());$('.community-moderation-more').addEventListener('click',()=>loadQueue(true));$('.community-audit-more').addEventListener('click',()=>loadAudit(true));
  $('.community-entry-lookup').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;const id=Number(form.elements.entryId.value),target=$('.community-lookup-result');if(!Number.isSafeInteger(id)||id<1)return;
   disableForm(form,true);target.replaceChildren(node('p','Загружаем запись…'));
   try{const data=await get('/entries/'+id);if(!validEntry(data.entry))throw new Error('invalid_entry');target.replaceChildren(entryView(data.entry,{moderate:true}));}
   catch(error){handleAccessError(error);target.replaceChildren(node('p',describe(error),'community-error'));}
   finally{disableForm(form,false);}
  });
  $('.community-role-form').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;
   const body={authorId:form.elements.authorId.value.trim(),role:form.elements.role.value,action:form.elements.action.value,reason:form.elements.reason.value.trim()},feedback=$('.community-role-status',form);
   disableForm(form,true);setMessage(feedback,'Сохраняем изменение роли…');
   try{const data=await post('/roles',body,result=>Array.isArray(result.roles)&&typeof result.authorId==='string');setMessage(feedback,'Изменение сохранено для '+body.authorId+'. Роли: '+(data.roles.map(x=>roleNames[x]||x).join(', ')||'участник')+'. Право голоса и доступ к сети не изменены.');form.elements.reason.value='';loadAudit();}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  loadAccount();
 }
})();
