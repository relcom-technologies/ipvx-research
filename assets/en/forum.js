/* Participants' forum. Posts are plain text rendered with textContent; roles come only from the verified backend.
   One page, views chosen by the query: categories, ?c= category, ?t= thread, ?s= subject, ?q= search, ?mine= own threads, ?mod= queue. */
(()=>{
 'use strict';
 const root=document.querySelector('[data-forum]');
 if(!root)return;
 const $=(selector,scope=root)=>scope.querySelector(selector);
 const node=(tag,text,className)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=String(text);if(className)item.className=className;return item;};
 const api='/community/v1';
 const page=location.pathname.split('/').pop()||'forum.html';
 const params=new URLSearchParams(location.search);
 const status=$('.forum-status'),view=$('.forum-view');
 const requests=new Map();
 let session=null,profile=null,notices=null;
 const categories={
  bcp:['BCP 0.2',"Current work on BCP 0.2: runs, the stand, checks and their limits."],
  blog:["Blog","Discussion of IPvX Research blog articles: one topic per article."],
  rfc:["RFC drafts","Questions and ideas on RFC drafts. An RFC changes through a proposal on the RFC or a GitHub PR."],
  experiments:["Experiments and lab","Experiments, the lab.ipvx.org stand, hypotheses and their checks."],
  architecture:["Architecture","How IPvX works: addressing, routing, message delivery."],
  questions:["Questions","Questions about the project and the protocol."],
  meta:["Site and forum","Feedback on the site and the forum, rules and moderator notes."]};
 const queues={people:"Waiting for people",automatic:"Waiting for automatic review",hidden:"Hidden"};
 const statusNames={pending:"In review · visible only to you and moderators",hidden:"Hidden by a moderator"};
 const errors={sign_in_required:"Your session has ended. Sign in again with Relcom ID.",verified_account_required:"Taking part needs an account with a confirmed email.",access_blocked:"An administrator has blocked your participation.",thread_locked:"This topic is closed to new replies.",thread_not_found:"Topic not found or not published yet.",category_not_found:"There is no such category.",pending_limit_reached:"You have too many posts in review. Wait for a decision.",write_rate_exceeded:"Too many actions in a row. Try again in a few minutes.",name_taken:"That name is taken.",invalid_name:"Name: 2 to 40 letters and digits, no reserved words.",invalid_text:"Check the length: a title of 3 to 200 characters, a post of up to 8000.",search_unavailable:"Search is temporarily unavailable.",invalid_search:"Enter at least one word of two letters.",role_required:"This needs the moderator role."};
 const describe=error=>errors[error.code]||(error.status===429?"The action limit has temporarily been reached. Try again later.":error.status>=500||!error.status?"The forum is temporarily unavailable. Try again later.":"The request failed.");
 const say=(text,isError=false)=>{status.textContent=text;status.classList.toggle('forum-error',isError);};
 const get=async(path,options={})=>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try{
   const response=await fetch(api+path,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal,headers:{Accept:'application/json',...(options.headers||{})}});
   let data;try{data=await response.json();}catch{data={};}
   if(!response.ok){const error=new Error('forum_request');error.status=response.status;error.code=data.error;throw error;}
   if(!data||typeof data!=='object')throw new Error('invalid_response');
   return data;
  }finally{clearTimeout(timer);}
 };
 const post=async(path,body)=>{
  const serialized=JSON.stringify(body),fingerprint=path+'\n'+serialized;
  // An unchanged retry keeps its key; a changed payload is a new intent.
  for(const pending of requests.keys())if(pending.startsWith(path+'\n')&&pending!==fingerprint)requests.delete(pending);
  if(!requests.has(fingerprint)){const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);requests.set(fingerprint,Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join(''));}
  const result=await get(path,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':requests.get(fingerprint)},body:serialized});
  requests.delete(fingerprint);return result;
 };
 const date=value=>{const stamp=Date.parse(value);return Number.isFinite(stamp)?new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short'}).format(stamp):'';};
 const link=(query,text,className)=>{const a=node('a',text,className);a.href=page+(query?'?'+new URLSearchParams(query):'');return a;};
 const signedIn=()=>session?.authenticated===true&&session?.access!=='blocked';
 const moderator=()=>signedIn()&&(session.roles.includes('moderator')||session.roles.includes('admin'));
 const signInLink=text=>{const a=node('a',text);a.href='https://ipvx.org/auth/login?returnTo='+encodeURIComponent(location.pathname+location.search);return a;};
 const author=item=>item&&typeof item.label==='string'?item.label:"Participant";
 const badge=state=>statusNames[state]?node('span',statusNames[state],'badge forum-state forum-'+state):null;
 const crumbs=(...items)=>{const trail=node('p',undefined,'forum-crumbs');trail.append(link(null,"Forum"));for(const item of items){trail.append(node('span','/','forum-sep'));trail.append(item);}return trail;};
 const heading=(text,level='h2')=>node(level,text,'forum-heading');
 // Project objects a thread can be about; the link back stays in the reader's language edition.
 const edition=(page.match(/^forum(\.[a-z]{2})?\.html$/)||[])[1]||'';
 const experiments={llm:"Two local models",native:"Five machines and relay failure",documents:"Documents over the native network",scale:"Large-network simulation"};
 function about(ref){
  let match=/^rfc-(\d{4})(?:\.s([1-9]\d?))?$/.exec(ref);
  if(match)return {label:'RFC-'+match[1]+(match[2]?", section "+match[2]:''),href:'rfc-'+match[1]+edition+'.html'+(match[2]?'#s'+match[2]:''),category:'rfc'};
  match=/^llm([1-9]\d?)$/.exec(ref);
  if(match)return {label:"Hypothesis LLM"+match[1],href:'experiments'+edition+'.html#llm'+match[1],category:'experiments'};
  match=/^experiments\.([a-z]+)$/.exec(ref);
  if(match&&experiments[match[1]])return {label:"Experiment: "+experiments[match[1]],href:'experiments'+edition+'.html#'+match[1],category:'experiments'};
  match=/^lab\.([a-z0-9-]+)$/.exec(ref);
  if(match)return {label:"Lab: "+match[1],href:'https://lab.ipvx.org/',category:'experiments'};
  return {label:ref,href:null,category:null};
 }

 function form(fields,submitText,onSubmit){
  const element=node('form',undefined,'forum-form'),result=node('p','','forum-form-status');result.setAttribute('role','status');result.setAttribute('aria-live','polite');
  for(const field of fields){
   const id='forum-'+field.name+'-'+Math.random().toString(16).slice(2,8),label=node('label',field.label);label.htmlFor=id;
   const control=field.type==='select'?node('select'):node(field.type==='textarea'?'textarea':'input');
   control.id=id;control.name=field.name;
   if(field.type==='select')for(const [value,text] of field.options){const option=node('option',text);option.value=value;control.append(option);}
   if(field.max)control.maxLength=field.max;if(field.rows)control.rows=field.rows;if(field.required)control.required=true;if(field.value)control.value=field.value;
   element.append(label,control);
  }
  const hint=node('p',"Write plain text. Do not post passwords, keys or personal data.",'small');
  const button=node('button',submitText,'button');button.type='submit';
  element.append(hint,button,result);
  element.addEventListener('submit',async event=>{
   event.preventDefault();
   const values=Object.fromEntries(new FormData(element));
   for(const control of element.elements)control.disabled=true;
   result.textContent="Sending…";result.classList.remove('forum-error');
   try{await onSubmit(values,result);}
   catch(error){result.textContent=describe(error);result.classList.add('forum-error');}
   finally{for(const control of element.elements)control.disabled=false;}
  });
  return element;
 }
 const published=data=>data.visibility==='published'?"Published.":"Sent. The post appears after review; until then only you can see it.";

 function composer(category,subject,suggested){
  const box=node('section',undefined,'forum-compose');
  box.append(heading("New topic",'h3'));
  if(!signedIn()){const p=node('p');p.append(signInLink("Sign in with Relcom ID"),document.createTextNode(" to start a topic."));box.append(p);return box;}
  const fields=[];
  if(!category)fields.push({name:'category',label:"Category",type:'select',value:suggested,options:Object.entries(categories).map(([id,[name]])=>[id,name])});
  fields.push({name:'title',label:"Title",max:200,required:true},{name:'text',label:"Message",type:'textarea',rows:7,max:8000,required:true});
  box.append(form(fields,"Post topic",async(values,result)=>{
   const target=category||values.category,body={title:values.title,text:values.text};
   if(subject)body.subject=subject;
   const data=await post('/forum/categories/'+encodeURIComponent(target)+'/threads',body);
   result.textContent=published(data);
   if(data.thread&&Number.isSafeInteger(data.thread.id))location.assign(page+'?t='+data.thread.id);
  }));
  return box;
 }

 function threadRows(list,threads){
  for(const thread of threads){
   if(!thread||!Number.isSafeInteger(thread.id))continue;
   const row=node('article',undefined,'forum-thread-row'),title=node('h3');
   title.append(link({t:thread.id},thread.title));
   const meta=node('p',undefined,'forum-meta');
   meta.append(node('span',author(thread.author)),node('span',categories[thread.category]?.[0]||thread.category),
    node('span',(thread.replies||0)+' '+(thread.replies===1?"reply":"replies")),node('span',date(thread.lastActivityAt)));
   row.append(title,meta);
   const state=badge(thread.status);if(state)row.append(state);
   if(thread.locked)row.append(node('span',"Closed",'badge'));
   list.append(row);
  }
 }

 async function threadList(path,list,more){
  let cursor=null;
  const load=async()=>{
   const data=await get(path+(cursor?(path.includes('?')?'&':'?')+'before='+encodeURIComponent(cursor):''));
   if(!Array.isArray(data.threads))throw new Error('invalid_response');
   threadRows(list,data.threads);cursor=data.nextBefore||null;more.hidden=!cursor;
   if(!list.children.length)list.append(node('p',"No topics yet. Start the first one.",'forum-empty'));
  };
  more.addEventListener('click',()=>load().catch(error=>say(describe(error),true)));
  await load();
 }

 async function home(){
  view.append(heading("Categories"));
  const data=await get('/forum/categories'),list=node('div',undefined,'forum-categories');
  for(const item of data.categories||[]){
   if(!categories[item.id])continue;
   const card=node('article',undefined,'forum-category'),title=node('h3');
   title.append(link({c:item.id},categories[item.id][0]));
   card.append(title,node('p',categories[item.id][1]),node('p',item.lastActivityAt?"Topics: "+item.threads+" · latest: "+date(item.lastActivityAt):"No topics yet",'forum-meta'));
   list.append(card);
  }
  view.append(list,composer(null,null));
  if(signedIn())view.append(await nameForm());
 }

 async function category(id){
  if(!categories[id])throw Object.assign(new Error('missing'),{status:404,code:'category_not_found'});
  document.title=categories[id][0]+' · '+document.title;
  view.append(crumbs(node('span',categories[id][0])),heading(categories[id][0]),node('p',categories[id][1],'forum-lead'));
  const list=node('div',undefined,'forum-threads'),more=node('button',"Show more",'button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  await threadList('/forum/categories/'+id+'/threads',list,more);
  view.append(composer(id,null));
 }

 async function subject(ref){
  if(!/^[a-z0-9][a-z0-9.-]{0,79}$/.test(ref))throw Object.assign(new Error('missing'),{status:404,code:'thread_not_found'});
  const info=about(ref);
  document.title=info.label+' · '+document.title;
  view.append(crumbs(node('span',info.label)),heading("Discussions: "+info.label));
  if(info.href){const back=node('p',undefined,'forum-lead'),a=node('a',"Open on the site");a.href=info.href;back.append(a);view.append(back);}
  const list=node('div',undefined,'forum-threads'),more=node('button',"Show more",'button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  await threadList('/forum/subjects/'+ref+'/threads',list,more);
  view.append(composer(null,ref,info.category));
 }

 function postItem(item,thread,onReply,lastSeen){
  const article=node('article',undefined,'forum-post');article.id='post-'+item.id;
  const meta=node('p',undefined,'forum-meta');
  const anchor=node('a','#'+item.id,'forum-anchor');anchor.href='#post-'+item.id;
  meta.append(node('strong',author(item.author)),node('span',date(item.createdAt)),anchor);
  if(Number.isSafeInteger(lastSeen)&&item.id>lastSeen&&item.status==='published'&&item.author?.id!==session?.author?.id){article.classList.add('forum-new');meta.append(node('span',"New",'badge forum-new-badge'));}
  article.append(meta);
  if(item.replyTo){const ref=node('a',"in reply to #"+item.replyTo,'forum-reply-ref');ref.href='#post-'+item.replyTo;article.append(ref);}
  const state=badge(item.status);if(state)article.append(state);
  article.append(node('div',item.text,'forum-text'));
  const actions=node('div',undefined,'forum-actions');
  if(signedIn()&&item.status==='published'&&(!thread.locked||moderator())){
   const reply=node('button',"Reply",'forum-link-button');reply.type='button';reply.addEventListener('click',()=>onReply(item));actions.append(reply);
  }
  if(moderator())actions.append(moderation(item));
  if(actions.children.length)article.append(actions);
  return article;
 }

 function moderation(item){
  const box=node('details',undefined,'forum-moderate');box.append(node('summary',"Moderation"));
  if(item.review?.note)box.append(node('p',"Review note: "+item.review.note,'small'));
  box.append(form([{name:'reason',label:"Reason",max:1000,required:true}],item.status==='published'?"Hide":"Publish",async(values,result)=>{
   const data=await post('/forum/posts/'+item.id+'/moderation',{action:item.status==='published'?'hide':'publish',reason:values.reason});
   result.textContent=data.post?.status==='published'?"Published.":"Hidden.";
  }));
  return box;
 }

 async function thread(id){
  const first=await get('/forum/threads/'+id);
  const info=first.thread;if(!info||!Number.isSafeInteger(info.id))throw new Error('invalid_response');
  document.title=info.title+' · '+document.title;
  view.append(crumbs(link({c:info.category},categories[info.category]?.[0]||info.category)));
  const title=heading(info.title,'h2');view.append(title);
  const meta=node('p',undefined,'forum-meta');
  meta.append(node('span',author(info.author)),node('span',date(info.createdAt)));
  if(info.subject)meta.append(link({s:info.subject},"About: "+about(info.subject).label));
  view.append(meta);
  const state=badge(info.status);if(state)view.append(state);
  if(info.locked)view.append(node('p',"This topic is closed: only a moderator can reply.",'forum-note'));
  const list=node('div',undefined,'forum-posts'),more=node('button',"Show more replies",'button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  let replyTo=null;const target=node('p','','forum-reply-target');target.hidden=true;
  const onReply=item=>{replyTo=item.id;target.hidden=false;target.textContent="Reply to #"+item.id+' · '+author(item.author);const area=$('.forum-reply textarea');area?.focus();};
  const lastSeen=first.lastSeen;
  const add=data=>{for(const item of data.posts||[])if(item&&Number.isSafeInteger(item.id)&&typeof item.text==='string')list.append(postItem(item,info,onReply,lastSeen));cursor=data.nextAfter||null;more.hidden=!cursor;};
  let cursor=null;add(first);
  more.addEventListener('click',()=>get('/forum/threads/'+id+'?after='+cursor).then(add).catch(error=>say(describe(error),true)));
  if(moderator()){
   const lock=node('details',undefined,'forum-moderate');lock.append(node('summary',info.locked?"Reopen topic":"Close topic"));
   lock.append(form([{name:'reason',label:"Reason",max:1000,required:true}],info.locked?"Open":"Close",async(values,result)=>{
    await post('/forum/threads/'+id+'/moderation',{action:info.locked?'unlock':'lock',reason:values.reason});result.textContent="Done. Reload the page.";}));
   view.append(lock);
  }
  const box=node('section',undefined,'forum-reply');box.append(heading("Reply",'h3'));
  if(!signedIn()){const p=node('p');p.append(signInLink("Sign in with Relcom ID"),document.createTextNode(" to reply."));box.append(p);}
  else if(info.locked&&!moderator())box.append(node('p',"This topic is closed."));
  else if(info.status!=='published'&&!moderator())box.append(node('p',"Replies open once the topic is published."));
  else{
   box.append(target,form([{name:'text',label:"Message",type:'textarea',rows:6,max:8000,required:true}],"Send",async(values,result)=>{
    const body={text:values.text};if(replyTo)body.replyTo=replyTo;
    const data=await post('/forum/threads/'+id+'/posts',body);
    result.textContent=published(data);
    if(data.post){list.append(postItem(data.post,info,onReply));$('.forum-reply form')?.reset();replyTo=null;target.hidden=true;}
   }));
  }
  view.append(box);
  const linked=/^#post-[1-9][0-9]{0,8}$/.test(location.hash)?document.getElementById(location.hash.slice(1)):null;
  if(linked)linked.scrollIntoView({block:'start'});
 }

 async function mine(){
  view.append(crumbs(node('span',"My topics")),heading("My topics"),node('p',"Topics you wrote in. New replies are other participants' published posts since you last read the topic.",'forum-lead'));
  const data=await get('/forum/notifications?limit=50'),list=node('div',undefined,'forum-threads');
  for(const item of data.threads||[]){
   if(!item||!Number.isSafeInteger(item.id))continue;
   const row=node('article',undefined,'forum-thread-row'),title=node('h3'),a=link({t:item.id},item.title);
   if(item.newPosts>0&&Number.isSafeInteger(item.firstNew)){a.hash='post-'+item.firstNew;row.classList.add('forum-new');}
   title.append(a);
   const meta=node('p',undefined,'forum-meta');
   meta.append(node('span',categories[item.category]?.[0]||item.category),node('span',item.newPosts>0?"New replies: "+item.newPosts:"No new replies"),node('span',date(item.lastActivityAt)));
   row.append(title,meta);list.append(row);
  }
  if(!list.children.length)list.append(node('p',"You have not written on the forum yet. Topics you take part in will appear here.",'forum-empty'));
  view.append(list);
 }

 async function search(query){
  view.append(crumbs(node('span',"Search")),heading("Search: "+query));
  const data=await get('/forum/search?q='+encodeURIComponent(query)),list=node('div',undefined,'forum-results');
  for(const item of data.results||[]){
   if(!Number.isSafeInteger(item.thread))continue;
   const row=node('article',undefined,'forum-thread-row'),title=node('h3'),a=link({t:item.thread},item.title);a.hash='post-'+item.post;
   title.append(a);row.append(title,node('p',item.excerpt,'forum-text'));list.append(row);
  }
  if(!list.children.length)list.append(node('p',"Nothing found.",'forum-empty'));
  view.append(list);
 }

 async function queue(name){
  if(!moderator())throw Object.assign(new Error('role'),{status:403,code:'role_required'});
  if(!queues[name])name='people';
  view.append(crumbs(node('span',"Moderation")),heading("Forum moderation"));
  const tabs=node('div',undefined,'forum-tabs');
  for(const [id,text] of Object.entries(queues)){const a=link({mod:id},text);if(id===name)a.setAttribute('aria-current','page');tabs.append(a);}
  view.append(tabs);
  const data=await get('/forum/moderation?queue='+name),list=node('div',undefined,'forum-posts');
  for(const item of data.posts||[]){
   if(!Number.isSafeInteger(item.id))continue;
   const head=node('p',undefined,'forum-meta');head.append(link({t:item.thread},item.threadTitle||'#'+item.thread),node('span',item.opening?"opening post":"reply"));
   const article=postItem(item,{locked:false},()=>{});article.prepend(head);list.append(article);
  }
  if(!list.children.length)list.append(node('p',"The queue is empty.",'forum-empty'));
  view.append(list);
 }

 async function nameForm(){
  const box=node('section',undefined,'forum-profile');box.append(heading("How you appear",'h3'));
  const current=profile?.author;
  box.append(node('p',current?.named?"Now: "+current.label:"You currently appear under the pseudonym “"+author(current)+"”. Your Relcom ID name and email are not shown on the forum."));
  box.append(form([{name:'name',label:"Public name",max:40,value:current?.named?current.label:''}],"Save name",async(values,result)=>{
   const data=await post('/forum/profile',{name:values.name||''});result.textContent="Saved: "+author(data.author);}));
  return box;
 }

 function toolbar(){
  const bar=node('div',undefined,'forum-toolbar'),searchForm=node('form',undefined,'forum-search'),label=node('label',"Search the forum",'forum-visually-hidden'),input=node('input');
  input.type='search';input.name='q';input.id='forum-search-q';input.maxLength=200;input.placeholder="Search the forum";input.value=params.get('q')||'';label.htmlFor=input.id;
  const button=node('button',"Search",'button secondary');button.type='submit';
  searchForm.action=page;searchForm.method='get';searchForm.setAttribute('role','search');searchForm.append(label,input,button);
  bar.append(searchForm);
  const who=node('p',undefined,'forum-who');
  if(signedIn()){who.append(node('span',author(profile?.author||session.author)));const unread=notices?.unreadPosts>0?notices.unreadPosts:0;who.append(link({mine:1},unread?"My topics · new: "+unread:"My topics",unread?'forum-unread':undefined));if(moderator())who.append(link({mod:'people'},"Moderation"));}
  else who.append(signInLink("Sign in with Relcom ID"));
  bar.append(who);
  return bar;
 }

 (async()=>{
  try{
   say("Loading the forum…");
   try{session=await get('/session');}catch{session=null;}
   if(signedIn()){try{profile=await get('/forum/profile');}catch{profile=null;}try{notices=await get('/forum/notifications?limit=1');}catch{notices=null;}}
   if(session?.access==='blocked')say(errors.access_blocked,true);
   view.replaceChildren();root.prepend(toolbar());
   const t=params.get('t'),c=params.get('c'),s=params.get('s'),q=params.get('q'),mod=params.get('mod'),own=params.get('mine');
   if(t&&/^[1-9][0-9]{0,8}$/.test(t))await thread(t);
   else if(c)await category(c);
   else if(s)await subject(s);
   else if(q)await search(q);
   else if(mod)await queue(mod);
   else if(own){if(!signedIn())throw Object.assign(new Error('signin'),{status:401,code:'sign_in_required'});await mine();}
   else await home();
   if(session?.access!=='blocked')say('');
  }catch(error){say(describe(error),true);}
 })();
})();
