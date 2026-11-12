/* Participants' forum. Posts are plain text rendered with textContent; roles come only from the verified backend.
   Machine translations come from the server, are always marked and switch back to the original text.
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
  bcp:['BCP 0.2','Текущая работа над BCP 0.2: прогоны, стенд, проверки и их границы.'],
  blog:['Блог','Обсуждение статей блога IPvX Research: одна тема на статью.'],
  rfc:['Черновики RFC','Вопросы и идеи по черновикам RFC. Изменение RFC идёт через предложение к RFC или PR в GitHub.'],
  experiments:['Эксперименты и лаборатория','Эксперименты, стенд lab.ipvx.org, гипотезы и их проверки.'],
  architecture:['Архитектура','Устройство IPvX: адресация, маршрутизация, доставка сообщений.'],
  questions:['Вопросы','Вопросы о проекте и протоколе.'],
  meta:['Сайт и форум','Отзывы о сайте и форуме, правила и заметки модераторов.']};
 const queues={people:'Ждут решения людей',automatic:'Ждут автоматической проверки',hidden:'Скрытые'};
 const statusNames={pending:'На проверке · видно только вам и модераторам',hidden:'Скрыто модератором'};
 const errors={sign_in_required:'Сеанс истёк. Войдите снова через Relcom ID.',verified_account_required:'Для участия нужна учётная запись с подтверждённой почтой.',access_blocked:'Ваше участие заблокировано администратором.',thread_locked:'Тема закрыта для новых ответов.',thread_not_found:'Тема не найдена или ещё не опубликована.',category_not_found:'Такой категории нет.',pending_limit_reached:'У вас слишком много сообщений на проверке. Дождитесь решения.',write_rate_exceeded:'Слишком много действий подряд. Попробуйте через несколько минут.',name_taken:'Это имя уже занято.',invalid_name:'Имя: от 2 до 40 букв и цифр, без служебных слов.',invalid_text:'Проверьте длину текста: заголовок от 3 до 200 знаков, сообщение до 8000.',search_unavailable:'Поиск временно недоступен.',invalid_search:'Введите хотя бы одно слово из двух букв.',role_required:'Нужна роль модератора.'};
 const describe=error=>errors[error.code]||(error.status===429?'Временно достигнут предел действий. Попробуйте позже.':error.status>=500||!error.status?'Форум временно недоступен. Повторите позже.':'Запрос не выполнен.');
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
 const date=value=>{const stamp=Date.parse(value);return Number.isFinite(stamp)?new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short'}).format(stamp):'';};
 const link=(query,text,className)=>{const a=node('a',text,className);a.href=page+(query?'?'+new URLSearchParams(query):'');return a;};
 const signedIn=()=>session?.authenticated===true&&session?.access!=='blocked';
 const moderator=()=>signedIn()&&(session.roles.includes('moderator')||session.roles.includes('admin'));
 const signInLink=text=>{const a=node('a',text);a.href='https://ipvx.org/auth/login?returnTo='+encodeURIComponent(location.pathname+location.search);return a;};
 const author=item=>item&&typeof item.label==='string'?item.label:'Участник';
 const badge=state=>statusNames[state]?node('span',statusNames[state],'badge forum-state forum-'+state):null;
 const crumbs=(...items)=>{const trail=node('p',undefined,'forum-crumbs');trail.append(link(null,'Форум'));for(const item of items){trail.append(node('span','/','forum-sep'));trail.append(item);}return trail;};
 const heading=(text,level='h2')=>node(level,text,'forum-heading');
 // Project objects a thread can be about; the link back stays in the reader's language edition.
 const edition=(page.match(/^forum(\.[a-z]{2})?\.html$/)||[])[1]||'';
 const lang=edition?edition.slice(1):'ru';
 const localized=path=>path+(path.includes('?')?'&':'?')+'lang='+lang;
 const fromNames={ru:'Машинный перевод с русского',en:'Машинный перевод с английского',de:'Машинный перевод с немецкого',es:'Машинный перевод с испанского'};
 const translated=item=>{const value=item?.translation;return value&&value.lang===lang&&typeof value.text==='string'&&value.text?value:null;};
 // A machine translation shown in place of the original, marked, with a switch back to the original text.
 function bilingual(target,original,translation){
  const source=/^[a-z]{2,3}$/.test(translation.from||'')&&translation.from!=='und'?translation.from:'';
  const note=node('p',undefined,'forum-translation'),button=node('button','','forum-link-button');button.type='button';
  let originalShown=false;
  const show=()=>{
   target.textContent=originalShown?original:translation.text;
   if(!originalShown)target.lang=lang;else if(source)target.lang=source;else target.removeAttribute('lang');
   button.textContent=originalShown?'Показать перевод':'Показать оригинал';
  };
  button.addEventListener('click',()=>{originalShown=!originalShown;show();});
  note.append(node('span',fromNames[translation.from]||'Машинный перевод'),button);
  show();
  return note;
 }
 const experiments={llm:'Две локальные модели',native:'Пять машин и отказ посредника',documents:'Документы через нативную сеть',scale:'Расчёт больших сетей'};
 function about(ref){
  let match=/^rfc-(\d{4})(?:\.s([1-9]\d?))?$/.exec(ref);
  if(match)return {label:'RFC-'+match[1]+(match[2]?', раздел '+match[2]:''),href:'rfc-'+match[1]+edition+'.html'+(match[2]?'#s'+match[2]:''),category:'rfc'};
  match=/^llm([1-9]\d?)$/.exec(ref);
  if(match)return {label:'Гипотеза LLM'+match[1],href:'experiments'+edition+'.html#llm'+match[1],category:'experiments'};
  match=/^experiments\.([a-z]+)$/.exec(ref);
  if(match&&experiments[match[1]])return {label:'Опыт: '+experiments[match[1]],href:'experiments'+edition+'.html#'+match[1],category:'experiments'};
  match=/^lab\.([a-z0-9-]+)$/.exec(ref);
  if(match)return {label:'Лаборатория: '+match[1],href:'https://lab.ipvx.org/?lang='+(edition?edition.slice(1):'ru'),category:'experiments'};
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
  const hint=node('p','Пишите простым текстом. Не публикуйте пароли, ключи и личные данные.','small');
  const button=node('button',submitText,'button');button.type='submit';
  element.append(hint,button,result);
  element.addEventListener('submit',async event=>{
   event.preventDefault();
   const values=Object.fromEntries(new FormData(element));
   for(const control of element.elements)control.disabled=true;
   result.textContent='Отправляем…';result.classList.remove('forum-error');
   try{await onSubmit(values,result);}
   catch(error){result.textContent=describe(error);result.classList.add('forum-error');}
   finally{for(const control of element.elements)control.disabled=false;}
  });
  return element;
 }
 const published=data=>data.visibility==='published'?'Опубликовано.':'Отправлено. Сообщение появится после проверки; пока его видите только вы.';

 function composer(category,subject,suggested){
  const box=node('section',undefined,'forum-compose');
  box.append(heading('Новая тема','h3'));
  if(!signedIn()){const p=node('p');p.append(signInLink('Войдите через Relcom ID'),document.createTextNode(', чтобы начать тему.'));box.append(p);return box;}
  const fields=[];
  if(!category)fields.push({name:'category',label:'Категория',type:'select',value:suggested,options:Object.entries(categories).map(([id,[name]])=>[id,name])});
  fields.push({name:'title',label:'Заголовок',max:200,required:true},{name:'text',label:'Сообщение',type:'textarea',rows:7,max:8000,required:true});
  box.append(form(fields,'Опубликовать тему',async(values,result)=>{
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
   const row=node('article',undefined,'forum-thread-row'),title=node('h3'),version=translated(thread);
   const a=link({t:thread.id},version?version.text:thread.title);if(version){a.lang=lang;a.title=thread.title;}
   title.append(a);
   const meta=node('p',undefined,'forum-meta');
   meta.append(node('span',author(thread.author)),node('span',categories[thread.category]?.[0]||thread.category),
    node('span',(thread.replies||0)+' '+(thread.replies===1?'ответ':'ответов')),node('span',date(thread.lastActivityAt)));
   if(version)meta.append(node('span','Машинный перевод заголовка'));
   row.append(title,meta);
   const state=badge(thread.status);if(state)row.append(state);
   if(thread.locked)row.append(node('span','Закрыта','badge'));
   list.append(row);
  }
 }

 async function threadList(path,list,more){
  let cursor=null;
  const load=async()=>{
   const data=await get(path+(cursor?(path.includes('?')?'&':'?')+'before='+encodeURIComponent(cursor):''));
   if(!Array.isArray(data.threads))throw new Error('invalid_response');
   threadRows(list,data.threads);cursor=data.nextBefore||null;more.hidden=!cursor;
   if(!list.children.length)list.append(node('p','Тем пока нет. Начните первую.','forum-empty'));
  };
  more.addEventListener('click',()=>load().catch(error=>say(describe(error),true)));
  await load();
 }

 async function home(){
  view.append(heading('Категории'));
  const data=await get('/forum/categories'),list=node('div',undefined,'forum-categories');
  for(const item of data.categories||[]){
   if(!categories[item.id])continue;
   const card=node('article',undefined,'forum-category'),title=node('h3');
   title.append(link({c:item.id},categories[item.id][0]));
   card.append(title,node('p',categories[item.id][1]),node('p',item.lastActivityAt?'Тем: '+item.threads+' · последнее: '+date(item.lastActivityAt):'Тем пока нет','forum-meta'));
   list.append(card);
  }
  view.append(list,composer(null,null));
  if(signedIn())view.append(await nameForm());
 }

 async function category(id){
  if(!categories[id])throw Object.assign(new Error('missing'),{status:404,code:'category_not_found'});
  document.title=categories[id][0]+' · '+document.title;
  view.append(crumbs(node('span',categories[id][0])),heading(categories[id][0]),node('p',categories[id][1],'forum-lead'));
  const list=node('div',undefined,'forum-threads'),more=node('button','Показать ещё','button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  await threadList(localized('/forum/categories/'+id+'/threads'),list,more);
  view.append(composer(id,null));
 }

 async function subject(ref){
  if(!/^[a-z0-9][a-z0-9.-]{0,79}$/.test(ref))throw Object.assign(new Error('missing'),{status:404,code:'thread_not_found'});
  const info=about(ref);
  document.title=info.label+' · '+document.title;
  view.append(crumbs(node('span',info.label)),heading('Обсуждения: '+info.label));
  if(info.href){const back=node('p',undefined,'forum-lead'),a=node('a','Открыть на сайте');a.href=info.href;back.append(a);view.append(back);}
  const list=node('div',undefined,'forum-threads'),more=node('button','Показать ещё','button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  await threadList(localized('/forum/subjects/'+ref+'/threads'),list,more);
  view.append(composer(null,ref,info.category));
 }

 function postItem(item,thread,onReply,lastSeen){
  const article=node('article',undefined,'forum-post');article.id='post-'+item.id;
  const meta=node('p',undefined,'forum-meta');
  const anchor=node('a','#'+item.id,'forum-anchor');anchor.href='#post-'+item.id;
  meta.append(node('strong',author(item.author)),node('span',date(item.createdAt)),anchor);
  if(Number.isSafeInteger(lastSeen)&&item.id>lastSeen&&item.status==='published'&&item.author?.id!==session?.author?.id){article.classList.add('forum-new');meta.append(node('span','Новое','badge forum-new-badge'));}
  article.append(meta);
  if(item.replyTo){const ref=node('a','в ответ на #'+item.replyTo,'forum-reply-ref');ref.href='#post-'+item.replyTo;article.append(ref);}
  const state=badge(item.status);if(state)article.append(state);
  const text=node('div',item.text,'forum-text'),version=translated(item);
  if(version)article.append(bilingual(text,item.text,version));
  article.append(text);
  const actions=node('div',undefined,'forum-actions');
  if(signedIn()&&item.status==='published'&&(!thread.locked||moderator())){
   const reply=node('button','Ответить','forum-link-button');reply.type='button';reply.addEventListener('click',()=>onReply(item));actions.append(reply);
  }
  if(moderator())actions.append(moderation(item));
  if(actions.children.length)article.append(actions);
  return article;
 }

 function moderation(item){
  const box=node('details',undefined,'forum-moderate');box.append(node('summary','Модерация'));
  if(item.review?.note)box.append(node('p','Отметка проверки: '+item.review.note,'small'));
  box.append(form([{name:'reason',label:'Причина',max:1000,required:true}],item.status==='published'?'Скрыть':'Опубликовать',async(values,result)=>{
   const data=await post('/forum/posts/'+item.id+'/moderation',{action:item.status==='published'?'hide':'publish',reason:values.reason});
   result.textContent=data.post?.status==='published'?'Опубликовано.':'Скрыто.';
  }));
  return box;
 }

 async function thread(id){
  const first=await get(localized('/forum/threads/'+id));
  const info=first.thread;if(!info||!Number.isSafeInteger(info.id))throw new Error('invalid_response');
  const titleVersion=translated(info);
  document.title=(titleVersion?titleVersion.text:info.title)+' · '+document.title;
  view.append(crumbs(link({c:info.category},categories[info.category]?.[0]||info.category)));
  const title=heading(info.title,'h2');view.append(title);
  if(titleVersion)view.append(bilingual(title,info.title,titleVersion));
  const meta=node('p',undefined,'forum-meta');
  meta.append(node('span',author(info.author)),node('span',date(info.createdAt)));
  if(info.subject)meta.append(link({s:info.subject},'Обсуждается: '+about(info.subject).label));
  view.append(meta);
  const state=badge(info.status);if(state)view.append(state);
  if(info.locked)view.append(node('p','Тема закрыта: новые ответы может оставить только модератор.','forum-note'));
  const list=node('div',undefined,'forum-posts'),more=node('button','Показать ещё ответы','button secondary forum-more');more.type='button';more.hidden=true;
  view.append(list,more);
  let replyTo=null;const target=node('p','','forum-reply-target');target.hidden=true;
  const onReply=item=>{replyTo=item.id;target.hidden=false;target.textContent='Ответ на #'+item.id+' · '+author(item.author);const area=$('.forum-reply textarea');area?.focus();};
  const lastSeen=first.lastSeen;
  const add=data=>{for(const item of data.posts||[])if(item&&Number.isSafeInteger(item.id)&&typeof item.text==='string')list.append(postItem(item,info,onReply,lastSeen));cursor=data.nextAfter||null;more.hidden=!cursor;};
  let cursor=null;add(first);
  more.addEventListener('click',()=>get(localized('/forum/threads/'+id+'?after='+cursor)).then(add).catch(error=>say(describe(error),true)));
  if(moderator()){
   const lock=node('details',undefined,'forum-moderate');lock.append(node('summary',info.locked?'Открыть тему':'Закрыть тему'));
   lock.append(form([{name:'reason',label:'Причина',max:1000,required:true}],info.locked?'Открыть':'Закрыть',async(values,result)=>{
    await post('/forum/threads/'+id+'/moderation',{action:info.locked?'unlock':'lock',reason:values.reason});result.textContent='Готово. Обновите страницу.';}));
   view.append(lock);
  }
  const box=node('section',undefined,'forum-reply');box.append(heading('Ответить','h3'));
  if(!signedIn()){const p=node('p');p.append(signInLink('Войдите через Relcom ID'),document.createTextNode(', чтобы ответить.'));box.append(p);}
  else if(info.locked&&!moderator())box.append(node('p','Тема закрыта.'));
  else if(info.status!=='published'&&!moderator())box.append(node('p','Ответы откроются, когда тему опубликуют.'));
  else{
   box.append(target,form([{name:'text',label:'Сообщение',type:'textarea',rows:6,max:8000,required:true}],'Отправить',async(values,result)=>{
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
  view.append(crumbs(node('span','Мои темы')),heading('Мои темы'),node('p','Темы, в которых вы писали. Новыми считаются опубликованные ответы других участников после вашего последнего прочтения.','forum-lead'));
  const data=await get(localized('/forum/notifications?limit=50')),list=node('div',undefined,'forum-threads');
  for(const item of data.threads||[]){
   if(!item||!Number.isSafeInteger(item.id))continue;
   const row=node('article',undefined,'forum-thread-row'),title=node('h3'),version=translated(item),a=link({t:item.id},version?version.text:item.title);
   if(version){a.lang=lang;a.title=item.title;}
   if(item.newPosts>0&&Number.isSafeInteger(item.firstNew)){a.hash='post-'+item.firstNew;row.classList.add('forum-new');}
   title.append(a);
   const meta=node('p',undefined,'forum-meta');
   meta.append(node('span',categories[item.category]?.[0]||item.category),node('span',item.newPosts>0?'Новых ответов: '+item.newPosts:'Новых ответов нет'),node('span',date(item.lastActivityAt)));
   row.append(title,meta);list.append(row);
  }
  if(!list.children.length)list.append(node('p','Вы ещё не писали на форуме. Здесь появятся темы, в которых вы участвуете.','forum-empty'));
  view.append(list);
 }

 async function search(query){
  view.append(crumbs(node('span','Поиск')),heading('Поиск: '+query));
  const data=await get('/forum/search?q='+encodeURIComponent(query)),list=node('div',undefined,'forum-results');
  for(const item of data.results||[]){
   if(!Number.isSafeInteger(item.thread))continue;
   const row=node('article',undefined,'forum-thread-row'),title=node('h3'),a=link({t:item.thread},item.title);a.hash='post-'+item.post;
   title.append(a);row.append(title,node('p',item.excerpt,'forum-text'));list.append(row);
  }
  if(!list.children.length)list.append(node('p','Ничего не найдено.','forum-empty'));
  view.append(list);
 }

 async function queue(name){
  if(!moderator())throw Object.assign(new Error('role'),{status:403,code:'role_required'});
  if(!queues[name])name='people';
  view.append(crumbs(node('span','Модерация')),heading('Модерация форума'));
  const tabs=node('div',undefined,'forum-tabs');
  for(const [id,text] of Object.entries(queues)){const a=link({mod:id},text);if(id===name)a.setAttribute('aria-current','page');tabs.append(a);}
  view.append(tabs);
  const data=await get('/forum/moderation?queue='+name),list=node('div',undefined,'forum-posts');
  for(const item of data.posts||[]){
   if(!Number.isSafeInteger(item.id))continue;
   const head=node('p',undefined,'forum-meta');head.append(link({t:item.thread},item.threadTitle||'#'+item.thread),node('span',item.opening?'начало темы':'ответ'));
   const article=postItem(item,{locked:false},()=>{});article.prepend(head);list.append(article);
  }
  if(!list.children.length)list.append(node('p','Очередь пуста.','forum-empty'));
  view.append(list);
 }

 async function nameForm(){
  const box=node('section',undefined,'forum-profile');box.append(heading('Как вас показывать','h3'));
  const current=profile?.author;
  box.append(node('p',current?.named?'Сейчас: '+current.label:'Сейчас вы показаны псевдонимом «'+author(current)+'». Имя и почта из Relcom ID на форуме не видны.'));
  box.append(form([{name:'name',label:'Публичное имя',max:40,value:current?.named?current.label:''}],'Сохранить имя',async(values,result)=>{
   const data=await post('/forum/profile',{name:values.name||''});result.textContent='Сохранено: '+author(data.author);}));
  return box;
 }

 function toolbar(){
  const bar=node('div',undefined,'forum-toolbar'),searchForm=node('form',undefined,'forum-search'),label=node('label','Поиск по форуму','forum-visually-hidden'),input=node('input');
  input.type='search';input.name='q';input.id='forum-search-q';input.maxLength=200;input.placeholder='Поиск по форуму';input.value=params.get('q')||'';label.htmlFor=input.id;
  const button=node('button','Найти','button secondary');button.type='submit';
  searchForm.action=page;searchForm.method='get';searchForm.setAttribute('role','search');searchForm.append(label,input,button);
  bar.append(searchForm);
  const who=node('p',undefined,'forum-who');
  if(signedIn()){who.append(node('span',author(profile?.author||session.author)));const unread=notices?.unreadPosts>0?notices.unreadPosts:0;who.append(link({mine:1},unread?'Мои темы · новых: '+unread:'Мои темы',unread?'forum-unread':undefined));if(moderator())who.append(link({mod:'people'},'Модерация'));}
  else who.append(signInLink('Войти через Relcom ID'));
  bar.append(who);
  return bar;
 }

 (async()=>{
  try{
   say('Загружаем форум…');
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
