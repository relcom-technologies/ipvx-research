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
  const errorText=authError==='unavailable'?"El servicio de acceso no está disponible temporalmente. Inténtalo más tarde.":authError==='error'?"No se confirmó el acceso. Intenta acceder de nuevo.":'';
  if(authError){params.delete('auth');history.replaceState(null,'',location.pathname+(params.size?'?'+params.toString():'')+location.hash);}
  const showAnonymous=message=>{verified.hidden=true;anonymous.hidden=false;sessionStatus.textContent=message;};
  const loadSession=async()=>{
   clearTimeout(expiryTimer);retry.hidden=true;anonymous.hidden=true;verified.hidden=true;
   sessionStatus.textContent="Comprobando el estado de acceso…";
   try{
    const data=await request('/auth/session',{credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
    if(typeof data.authenticated!=='boolean')throw new Error('invalid_session');
    if(!data.authenticated){showAnonymous(errorText||"No has iniciado sesión. Puedes usar una cuenta existente o registrarte.");return;}
    if(!data.user||typeof data.user.sub!=='string')throw new Error('invalid_user');
    const expiry=data.expiresAt?Date.parse(data.expiresAt):NaN;
    if(Number.isFinite(expiry)&&expiry<=Date.now()){showAnonymous("La sesión caducó. Accede de nuevo para verificar tu cuenta.");return;}
    byId('account-name').textContent=typeof data.user.name==='string'&&data.user.name.trim()?data.user.name:"Participante IPvX";
    byId('account-email').textContent=typeof data.user.email==='string'?data.user.email:"Dirección no facilitada";
    byId('account-verification').textContent=data.user.emailVerified===true?"Correo electrónico confirmado por Relcom ID":"No se recibió confirmación del correo electrónico";
    byId('account-expiry-row').hidden=!Number.isFinite(expiry);
    if(Number.isFinite(expiry)){
     byId('account-expiry').textContent=new Intl.DateTimeFormat('es-ES',{dateStyle:'medium',timeStyle:'short',timeZoneName:undefined}).format(expiry);
     const delay=Math.min(expiry-Date.now(),2147483647);
     expiryTimer=setTimeout(()=>{showAnonymous("La sesión caducó. Accede de nuevo para verificar tu cuenta.");},Math.max(0,delay));
    }
    sessionStatus.textContent="Sesión iniciada. Los derechos de participación y votación se determinan por separado.";
    verified.hidden=false;anonymous.hidden=true;
   }catch{
    showAnonymous(errorText||"No se pudo comprobar el acceso. Inténtalo de nuevo; los materiales de investigación son públicos.");retry.hidden=false;
   }
  };
  retry.addEventListener('click',loadSession);loadSession();
 }
 const pressStatus=byId('press-status');
 if(pressStatus){
  const feed='https://press.relcom.com/embed/v1/sites/01a17cfa-d34c-7081-9631-e1489dac0e47/latest?locale=ru&limit=5&kind=article';
  const list=byId('press-articles'),retry=byId('press-retry');
  const loadArticles=async()=>{
   pressStatus.textContent="Cargando artículos publicados…";retry.hidden=true;
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
     if(Number.isFinite(published))meta.push(new Intl.DateTimeFormat('es-ES',{dateStyle:'long'}).format(published));
     if(Number.isInteger(item.readingMinutes)&&item.readingMinutes>0&&item.readingMinutes<1000)meta.push(item.readingMinutes+" min de lectura");
     if(meta.length){const p=document.createElement('p');p.className='small';p.textContent=meta.join(' · ');article.append(p);}
     if(typeof item.excerpt==='string'&&item.excerpt.trim()){const p=document.createElement('p');p.textContent=item.excerpt.slice(0,1200);article.append(p);}
     articles.push(article);
    }
    list.replaceChildren(...articles);
    pressStatus.textContent=articles.length?"Artículos publicados en Relcom Press.":"Aún no hay artículos publicados. Aparecerán aquí tras publicarse en Relcom Press.";
   }catch{
    pressStatus.textContent="No se pudo cargar la lista. Abre el blog en Relcom Press o inténtalo de nuevo.";retry.hidden=false;
   }
  };
  retry.addEventListener('click',loadArticles);loadArticles();
 }
})();
