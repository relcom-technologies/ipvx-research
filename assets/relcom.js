/* Public reading stays available independently of account or Press availability. */
(()=>{
 'use strict';
 const byId=id=>document.getElementById(id);
 const request=async(url,options={})=>{
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),10000);
  try{
   const response=await fetch(url,{...options,signal:controller.signal});
   if(!response.ok)throw new Error('unavailable');
   return await response.json();
  }finally{clearTimeout(timer);}
 };
 const sessionStatus=byId('session-status');
 if(sessionStatus){
  let expiryTimer;
  const anonymous=byId('session-anonymous'),verified=byId('session-verified'),retry=byId('session-retry');
  const params=new URLSearchParams(location.search),authError=params.get('auth');
  const errorText=authError==='unavailable'?'Сервис входа временно недоступен. Попробуйте позже.':authError==='error'?'Вход не подтверждён. Попробуйте войти снова.':'';
  if(authError){params.delete('auth');history.replaceState(null,'',location.pathname+(params.size?'?'+params.toString():'')+location.hash);}
  const showAnonymous=message=>{verified.hidden=true;anonymous.hidden=false;sessionStatus.textContent=message;};
  const loadSession=async()=>{
   clearTimeout(expiryTimer);retry.hidden=true;anonymous.hidden=true;verified.hidden=true;
   sessionStatus.textContent='Проверяем состояние входа…';
   try{
    const data=await request('/auth/session',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
    if(typeof data.authenticated!=='boolean')throw new Error('invalid_session');
    if(!data.authenticated){showAnonymous(errorText||'Вы не вошли. Можно использовать существующую учётную запись или зарегистрироваться.');return;}
    if(!data.user||typeof data.user.sub!=='string')throw new Error('invalid_user');
    const expiry=data.expiresAt?Date.parse(data.expiresAt):NaN;
    if(Number.isFinite(expiry)&&expiry<=Date.now()){showAnonymous('Сеанс истёк. Войдите снова, чтобы подтвердить учётную запись.');return;}
    byId('account-name').textContent=typeof data.user.name==='string'&&data.user.name.trim()?data.user.name:'Участник IPvX';
    byId('account-email').textContent=typeof data.user.email==='string'?data.user.email:'Адрес не предоставлен';
    byId('account-verification').textContent=data.user.emailVerified===true?'Электронная почта подтверждена Relcom ID':'Подтверждение электронной почты не получено';
    byId('account-expiry-row').hidden=!Number.isFinite(expiry);
    if(Number.isFinite(expiry)){
     byId('account-expiry').textContent=new Intl.DateTimeFormat('ru-RU',{dateStyle:'medium',timeStyle:'short',timeZoneName:undefined}).format(expiry);
     const delay=Math.min(expiry-Date.now(),2147483647);
     expiryTimer=setTimeout(()=>{showAnonymous('Сеанс истёк. Войдите снова, чтобы подтвердить учётную запись.');},Math.max(0,delay));
    }
    sessionStatus.textContent='Вход выполнен. Права участия и голосования определяются отдельно.';
    verified.hidden=false;anonymous.hidden=true;
   }catch{
    showAnonymous(errorText||'Не удалось проверить вход. Попробуйте ещё раз; материалы исследования доступны без входа.');retry.hidden=false;
   }
  };
  retry.addEventListener('click',loadSession);loadSession();
 }
 const pressStatus=byId('press-status');
 if(pressStatus){
  const feed='https://press.relcom.com/embed/v1/sites/01a17cfa-d34c-7081-9631-e1489dac0e47/latest?locale=ru&limit=5&kind=article';
  const list=byId('press-articles'),retry=byId('press-retry');
  const loadArticles=async()=>{
   pressStatus.textContent='Загружаем опубликованные статьи…';retry.hidden=true;
   try{
    const data=await request(feed,{credentials:'omit',headers:{Accept:'application/json'}});
    if(!Array.isArray(data.items))throw new Error('invalid_feed');
    const articles=[];
    for(const item of data.items.slice(0,5)){
     if(typeof item.title!=='string'||!item.title.trim()||typeof item.url!=='string')continue;
     let url;try{url=new URL(item.url);}catch{continue;}
     if(url.origin!=='https://ipvx.press.relcom.org'||url.username||url.password)continue;
     const article=document.createElement('article');article.className='press-article';
     const title=document.createElement('h3'),link=document.createElement('a');link.href=url.href;link.textContent=item.title.slice(0,300);title.append(link);article.append(title);
     const published=Date.parse(item.publishedAt),meta=[];
     if(Number.isFinite(published))meta.push(new Intl.DateTimeFormat('ru-RU',{dateStyle:'long'}).format(published));
     if(Number.isInteger(item.readingMinutes)&&item.readingMinutes>0&&item.readingMinutes<1000)meta.push(item.readingMinutes+' мин чтения');
     if(meta.length){const p=document.createElement('p');p.className='small';p.textContent=meta.join(' · ');article.append(p);}
     if(typeof item.excerpt==='string'&&item.excerpt.trim()){const p=document.createElement('p');p.textContent=item.excerpt.slice(0,1200);article.append(p);}
     articles.push(article);
    }
    list.replaceChildren(...articles);
    pressStatus.textContent=articles.length?'Опубликованные статьи в Relcom Press.':'Пока нет опубликованных статей. Новые материалы появятся здесь после публикации в Relcom Press.';
   }catch{
    pressStatus.textContent='Не удалось загрузить список статей. Откройте блог в Relcom Press или попробуйте ещё раз.';retry.hidden=false;
   }
  };
  retry.addEventListener('click',loadArticles);loadArticles();
 }
})();
