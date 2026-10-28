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
 const roleNames={participant:"Participant",moderator:"Moderator",maintainer:"Maintainer",admin:"Administrator"};
 const statusNames={pending:"Awaiting moderation · not yet published",published:"Published",hidden:"Hidden by a moderator"};
 const errors={access_blocked:"Your participation was blocked by an administrator. Account sign-in remains available.",sign_in_required:"Your participation session has expired. Sign in again through Relcom ID.",verified_account_required:"An account with verified email is required to submit.",role_required:"This role is no longer available. Refresh your participation permissions.",write_rate_exceeded:"Too many actions in a short time. Try again later.",pending_limit_reached:"The limit for messages awaiting moderation has been reached. Wait for earlier submissions to be reviewed.",body_too_large:"The text is too large for one entry. Shorten it or split it into separate messages.",invalid_text:"Check the text and its length.",proposal_title_required:"Enter a proposal title.",entry_not_found:"The entry is unavailable or no longer published.",participant_not_found:"No participant with that ID has registered yet.",bootstrap_admin_requires_operator_migration:"The initial administrator can be changed only by a separate operator action.",idempotency_key_reused_with_different_request:"The request changed during retry. Save your text and reload the page.",invalid_role_change:"Check the participant ID, role and action."};
 const describe=error=>errors[error.code]||(error.status===401?"Sign in through Relcom ID to continue.":error.status===403?"This action is not permitted. Check your sign-in and role.":error.status===429?"The action limit has temporarily been reached. Try again later.":error.status===413?"The message is too large. Shorten the text.":"The discussion service is temporarily unavailable. Your text remains in the form; try again.");
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
 const date=value=>{const stamp=typeof value==='number'?value:Date.parse(value);return Number.isFinite(stamp)?new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short'}).format(stamp):"Date not specified";};
 const validEntry=entry=>entry&&Number.isSafeInteger(entry.id)&&entry.id>0&&typeof entry.text==='string'&&typeof entry.kind==='string'&&typeof entry.status==='string';
 const signedIn=()=>session?.authenticated===true&&session?.access!=='blocked';
 const privileged=role=>signedIn()&&session.roles.includes(role);
 const disableForm=(form,disabled)=>{for(const control of form.querySelectorAll('button,input,select,textarea'))control.disabled=disabled;};
 const clearPrivileges=()=>{
  session=null;
  for(const selector of ['.community-moderation','.community-admin']){const area=$(selector);if(area)area.hidden=true;}
  for(const selector of ['.community-moderation-list','.community-lookup-result','.community-audit-list','.community-own-list'])$(selector)?.replaceChildren();
  for(const button of document.querySelectorAll('.community-vote-controls button'))button.disabled=true;
  if(account){$('.community-account-details',account).hidden=true;$('.community-account-retry',account).hidden=false;setMessage($('.community-account-status',account),"Participation permissions changed or the session ended. Check your sign-in and reload permissions.");}
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
  article.append(node('p',(entry.author?.label||"Participant")+' · '+date(entry.createdAt)+' · № '+entry.id,'community-entry-meta'));
  const state=node('p',undefined,'community-entry-state');state.append(node('span',statusNames[entry.status]||"Status being checked",'badge'+(entry.status==='pending'?' warn':'')));article.append(state);
  article.append(node('p',entry.text,'community-entry-text'));
  if(/^rfc-\d{4}$/.test(entry.rfc||'')){const p=node('p');const link=node('a',"Open "+entry.rfc.toUpperCase());link.href=entry.rfc+'.en.html#discussion';p.append(link);article.append(p);}
  if(entry.kind==='proposal'&&entry.status==='published')article.append(voteView(entry));
  if(moderate)article.append(moderationForm(entry));
  return article;
 }
 function voteView(entry){
  const area=node('div',undefined,'community-vote'),counts=node('p',undefined,'community-vote-counts'),controls=node('div',undefined,'community-vote-controls'),status=node('p','','community-vote-status');status.setAttribute('role','status');
  const showCounts=item=>{const value=item.votes?.counts||{},text="Advisory: support "+(Number.isSafeInteger(value.yes)?value.yes:0)+", oppose "+(Number.isSafeInteger(value.no)?value.no:0)+", abstain "+(Number.isSafeInteger(value.abstain)?value.abstain:0)+". This does not adopt the RFC.";counts.textContent=text;for(const output of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-counts'))output.textContent=text;};
  showCounts(entry);area.append(counts);
  if(signedIn()){
   for(const [value,label] of [['yes',"Support"],['no',"Oppose"],['abstain',"Abstain"],['withdraw',"Withdraw opinion"]]){
    const button=node('button',label);button.type='button';
    button.addEventListener('click',async()=>{
     if(votesInFlight.has(entry.id))return;votesInFlight.add(entry.id);
     for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=true;
     setMessage(status,"Saving opinion…");
     try{const result=await post('/entries/'+entry.id+'/vote',{value},data=>validEntry(data.entry));showCounts(result.entry);setMessage(status,value==='withdraw'?"Opinion withdrawn.":"Saved: "+label.toLowerCase()+". You can change or withdraw your opinion.");}
     catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
     finally{votesInFlight.delete(entry.id);for(const control of document.querySelectorAll('[data-entry-id="'+entry.id+'"] .community-vote-controls button'))control.disabled=!signedIn();}
    });controls.append(button);
   }
   area.append(controls);
  }else area.append(node('p',"Sign in to leave an advisory opinion."));
  area.append(status);return area;
 }
 function moderationForm(entry){
  const form=node('form',undefined,'community-moderation-action'),id='reason-'+entry.id+'-'+crypto.getRandomValues(new Uint32Array(1))[0];
  const label=node('label',"Reason for decision");label.htmlFor=id;
  const reason=node('textarea');reason.id=id;reason.name='reason';reason.rows=3;reason.minLength=3;reason.maxLength=1000;reason.required=true;
  const actions=node('div',undefined,'community-actions'),status=node('p','','community-moderation-status');status.setAttribute('role','status');
  for(const [value,text] of [['publish',"Publish entry"],['hide',"Hide entry"]]){const button=node('button',text,'button'+(value==='hide'?' secondary':''));button.type='submit';button.name='action';button.value=value;actions.append(button);}
  form.append(label,reason,actions,status);
  form.addEventListener('submit',async event=>{
   event.preventDefault();const action=event.submitter?.value;if(!['publish','hide'].includes(action)||!form.reportValidity())return;
   const body={action,reason:reason.value.trim()};disableForm(form,true);setMessage(status,"Saving moderation decision…");
   try{const result=await post('/entries/'+entry.id+'/moderation',body,data=>validEntry(data.entry));form.closest('.community-entry').replaceWith(entryView(result.entry,{moderate:true}));const output=$('.community-moderation-status');if(output)setMessage(output,"Entry № "+entry.id+(action==='publish'?" published.":" hidden.")+" The RFC source text is unchanged.");}
   catch(error){handleAccessError(error);setMessage(status,describe(error),true);}
   finally{disableForm(form,false);}
  });return form;
 }
 if(location.hostname==='www.ipvx.org'){
  const target=discussion||account;target.replaceChildren(node('h2',"Discussion on the primary domain"),node('p',"Open the project's primary domain to sign in and participate. Public texts are available here without signing in."));
  const link=node('a',"Open participation on ipvx.org",'button');link.href='https://ipvx.org'+location.pathname+(discussion?'#discussion':'#community');target.append(link);return;
 }
 if(discussion){
  const rfc=discussion.dataset.communityRfc;if(!/^rfc-\d{4}$/.test(rfc))return;
  const status=$('.community-session-status',discussion),form=$('.community-submit',discussion),list=$('.community-public',discussion),more=$('.community-public-more',discussion),retry=$('.community-public-retry',discussion),own=$('.community-own',discussion),ownList=$('.community-own-list',discussion),ownMore=$('.community-own-more',discussion);
  let kind='comment',before=null,ownBefore=null,loadVersion=0,ownVersion=0;
  const entriesPath=(mine,cursor)=>'/rfcs/'+rfc+'/entries?kind='+kind+'&limit=25'+(mine?'&mine=1':'')+(cursor?'&before='+cursor:'');
  async function loadPublic(append=false){
   const version=++loadVersion;retry.hidden=true;more.hidden=true;
   if(!append)list.replaceChildren(node('p',"Loading the published discussion…"));
   try{const data=await get(entriesPath(false,append?before:null));if(version!==loadVersion)return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)||x.status!=='published'))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry));if(!list.children.length)list.append(node('p',kind==='proposal'?"No proposals have been published yet.":"No comments have been published yet."));before=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=before===null;}
   catch(error){if(version!==loadVersion)return;if(!append)list.replaceChildren(node('p',"Could not load the discussion. RFC text and sources remain available independently of the service."));retry.hidden=false;}
  }
  async function loadOwn(append=false){
   const version=++ownVersion;
   ownMore.hidden=true;if(!signedIn())return;
   if(!append)ownList.replaceChildren(node('p',"Checking your messages…"));
   try{const data=await get(entriesPath(true,append?ownBefore:null));if(version!==ownVersion||!signedIn())return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)ownList.replaceChildren();for(const entry of data.entries)ownList.append(entryView(entry));if(!ownList.children.length)ownList.append(node('p',"No messages of this type yet."));ownBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;ownMore.hidden=ownBefore===null;}
   catch(error){if(version!==ownVersion)return;handleAccessError(error);ownList.replaceChildren(node('p',describe(error),'community-error'));}
  }
  const chooseKind=value=>{kind=value;before=null;ownBefore=null;for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.setAttribute('aria-pressed',String(button.dataset.entryKind===value));loadPublic();if(signedIn())loadOwn();};
  for(const button of discussion.querySelectorAll('[data-entry-kind]'))button.addEventListener('click',()=>chooseKind(button.dataset.entryKind));
  more.addEventListener('click',()=>loadPublic(true));retry.addEventListener('click',()=>loadPublic());ownMore.addEventListener('click',()=>loadOwn(true));
  form.elements.kind.addEventListener('change',()=>{form.elements.title.required=form.elements.kind.value==='proposal';});
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(!form.reportValidity())return;
   const body={kind:form.elements.kind.value,title:form.elements.title.value.trim(),text:form.elements.text.value.trim()},feedback=$('.community-submit-status',form);
   disableForm(form,true);setMessage(feedback,"Submitting for moderation…");
   try{const data=await post('/rfcs/'+rfc+'/entries',body,result=>validEntry(result.entry)&&result.entry.status==='pending');form.elements.title.value='';form.elements.text.value='';setMessage(feedback,"Message № "+data.entry.id+" is awaiting moderation. Only you and moderators can see it for now.");chooseKind(body.kind);own.open=true;}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  (async()=>{try{await loadSession();if(signedIn()){setMessage(status,session.author.label+" · you can submit a message for moderation.");form.hidden=false;own.hidden=false;loadOwn();}else{setMessage(status,"The discussion can be read without signing in.");$('.community-sign-in',discussion).hidden=false;}}catch{setMessage(status,"Could not check sign-in. The published discussion remains available.");$('.community-sign-in',discussion).hidden=false;}finally{loadPublic();}})();
 }
 if(account){
  const status=$('.community-account-status',account),details=$('.community-account-details',account),retry=$('.community-account-retry',account),moderation=$('.community-moderation'),admin=$('.community-admin');
  let queueBefore=null,auditBefore=null;
  async function loadQueue(append=false){
   const list=$('.community-moderation-list'),feedback=$('.community-moderation-status'),more=$('.community-moderation-more');more.hidden=true;setMessage(feedback,"Loading the private queue…");
   try{const data=await get('/moderation?limit=50'+(append&&queueBefore?'&before='+queueBefore:''));if(!privileged('moderator')&&!privileged('admin'))return;if(!Array.isArray(data.entries)||data.entries.some(x=>!validEntry(x)))throw new Error('invalid_entries');if(!append)list.replaceChildren();for(const entry of data.entries)list.append(entryView(entry,{moderate:true}));queueBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=queueBefore===null;setMessage(feedback,data.entries.length?"Entries loaded: "+data.entries.length+'.':append?"This is the entire queue.":"No messages are awaiting moderation.");}
   catch(error){handleAccessError(error);list.replaceChildren();setMessage(feedback,describe(error),true);}
  }
  async function loadAudit(append=false){
   const list=$('.community-audit-list'),more=$('.community-audit-more');more.hidden=true;if(!append)list.replaceChildren(node('p',"Loading the private log…"));
   const labels={configure_admin:"Initial administrator configured",submit_comment:"Comment submitted",submit_proposal:"Proposal submitted",publish:"Entry published",hide:"Entry hidden",advisory_vote:"Advisory opinion changed",grant_role:"Role granted",revoke_role:"Role revoked"};
   try{const data=await get('/audit?limit=50'+(append&&auditBefore?'&before='+auditBefore:''));if(!privileged('admin'))return;if(!Array.isArray(data.events))throw new Error('invalid_audit');if(!append)list.replaceChildren();for(const entry of data.events){const row=node('article',undefined,'community-audit-event');row.append(node('h3',labels[entry.action]||"Portal action"),node('p','№ '+entry.id+' · '+date(Number(entry.at)*1000),'small'),node('p',"Participant: "+entry.actor+" · target: "+entry.target));let detail;try{detail=JSON.parse(entry.detail);}catch{detail={};}if(typeof detail.reason==='string')row.append(node('p',"Reason: "+detail.reason));if(typeof detail.role==='string')row.append(node('p',"Role: "+(roleNames[detail.role]||detail.role)));list.append(row);}if(!data.events.length&&!append)list.append(node('p',"No actions yet."));auditBefore=Number.isSafeInteger(data.nextBefore)?data.nextBefore:null;more.hidden=auditBefore===null;}
   catch(error){handleAccessError(error);list.replaceChildren(node('p',describe(error),'community-error'));}
  }
  async function loadAccount(){
   retry.hidden=true;details.hidden=true;moderation.hidden=true;admin.hidden=true;setMessage(status,"Checking roles on the server…");
   try{await loadSession();if(session?.access==='blocked'){setMessage(status,"An administrator has blocked your discussion participation. Account sign-in remains available.",true);return;}if(!signedIn()){setMessage(status,"Sign in through Relcom ID above. Public reading and preparing a GitHub proposal are available without signing in.");return;}$('.community-author-label',account).textContent=session.author.label;$('.community-author-id',account).textContent=session.author.id;$('.community-role-labels',account).textContent=session.roles.map(x=>roleNames[x]).join(', ');details.hidden=false;setMessage(status,"Account verified. Portal roles are shown from server data.");if(privileged('moderator')||privileged('admin')){moderation.hidden=false;loadQueue();}if(privileged('admin')){admin.hidden=false;loadAudit();}}
   catch{clearPrivileges();setMessage(status,"Could not load roles. Sign-in and public materials are checked separately; try again.",true);retry.hidden=false;}
  }
  retry.addEventListener('click',loadAccount);$('.community-moderation-refresh').addEventListener('click',()=>loadQueue());$('.community-audit-refresh').addEventListener('click',()=>loadAudit());$('.community-moderation-more').addEventListener('click',()=>loadQueue(true));$('.community-audit-more').addEventListener('click',()=>loadAudit(true));
  $('.community-entry-lookup').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;const id=Number(form.elements.entryId.value),target=$('.community-lookup-result');if(!Number.isSafeInteger(id)||id<1)return;
   disableForm(form,true);target.replaceChildren(node('p',"Loading entry…"));
   try{const data=await get('/entries/'+id);if(!validEntry(data.entry))throw new Error('invalid_entry');target.replaceChildren(entryView(data.entry,{moderate:true}));}
   catch(error){handleAccessError(error);target.replaceChildren(node('p',describe(error),'community-error'));}
   finally{disableForm(form,false);}
  });
  $('.community-role-form').addEventListener('submit',async event=>{
   event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;
   const body={authorId:form.elements.authorId.value.trim(),role:form.elements.role.value,action:form.elements.action.value,reason:form.elements.reason.value.trim()},feedback=$('.community-role-status',form);
   disableForm(form,true);setMessage(feedback,"Saving role change…");
   try{const data=await post('/roles',body,result=>Array.isArray(result.roles)&&typeof result.authorId==='string');setMessage(feedback,"Change saved for "+body.authorId+". Roles: "+(data.roles.map(x=>roleNames[x]||x).join(', ')||"participant")+". Voting rights and network access are unchanged.");form.elements.reason.value='';loadAudit();}
   catch(error){handleAccessError(error);setMessage(feedback,describe(error),true);}
   finally{disableForm(form,false);}
  });
  loadAccount();
 }
})();
