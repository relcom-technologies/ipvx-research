import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});const checks=[];
try{
 for(const width of [1440,1280,768,390]){
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const id=n=>'member_'+String(n).repeat(24),owner={id:id(0),label:'Синтетический администратор',roles:['participant','admin'],access:'active',protected:true,lastSeenAt:'2026-10-27T15:00:00Z'};
  const members=[owner,{...owner,id:id(1),label:'Синтетический участник <script>',roles:['participant'],protected:false},{...owner,id:id(2),label:'Синтетический исследователь',roles:['participant','maintainer'],protected:false},{...owner,id:id(3),label:'Синтетический заблокированный участник',roles:['participant'],access:'blocked',protected:false}];
  let authenticated=false,admin=false,memberReads=0,malformed=true,revoke=false,effects=0;const keys=[],saved=new Map();
  const reply=(route,status,data)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
  await page.route('**/community/v1/**',async route=>{
   const r=route.request(),url=new URL(r.url()),path=url.pathname.replace('/community/v1','');
   if(path==='/session')return reply(route,200,{authenticated,author:authenticated?{id:owner.id,label:owner.label}:null,roles:authenticated?admin?['participant','admin']:['participant']:[],access:'active'});
   if(!admin)return reply(route,403,{error:'role_required'});
   if(r.method()==='GET'){
    if(path==='/members'){
     memberReads++;let rows=members.filter(m=>(url.searchParams.get('access')==='all'||m.access===url.searchParams.get('access'))&&m.label.includes(url.searchParams.get('search')||''));const total=rows.length,after=url.searchParams.get('after');if(after)rows=rows.filter(m=>m.id>after);const result=rows.slice(0,2);return reply(route,200,{members:result,total,nextAfter:rows.length>2?result.at(-1).id:null});
    }
    if(path==='/moderation')return reply(route,200,{entries:[{id:1,rfc:'rfc-0006',title:'Синтетическое предложение',text:'Пример очереди. Это тестовые данные, а не вклад исследователя.',author:{label:members[1].label},createdAt:'2026-10-27T15:00:00Z'}],nextBefore:null});
    if(path==='/audit')return reply(route,200,{events:[{id:1,action:'grant_role',actor:owner.id,target:members[1].id,detail:JSON.stringify({reason:'Синтетическая причина',role:'moderator'}),at:1793113200}],nextBefore:null});
   }
   const body=r.postDataJSON(),key=r.headers()['idempotency-key'];keys.push(key);
   if(revoke){admin=false;return reply(route,403,{error:'role_required'});}
   if(saved.has(key))return reply(route,200,saved.get(key));
   let result;
   if(path==='/roles'){
    const member=members.find(m=>m.id===body.authorId);
    if(member.access==='blocked'&&body.action==='grant')return reply(route,409,{error:'participant_blocked'});
    if(body.action==='grant'&&!member.roles.includes(body.role))member.roles.push(body.role);
    if(body.action==='revoke')member.roles=member.roles.filter(x=>x!==body.role);
    result={authorId:member.id,roles:member.roles.filter(x=>x!=='participant')};
   }else if(path.endsWith('/access')){
    const member=members.find(m=>path.includes(m.id));member.access=body.action==='block'?'blocked':'active';result={authorId:member.id,access:member.access};
   }else return reply(route,200,{entry:{id:1,status:body.action==='publish'?'published':'hidden'}});
   effects++;saved.set(key,result);
   if(malformed&&path==='/roles'){malformed=false;return reply(route,200,{authorId:body.authorId,roles:'broken'});}
   return reply(route,200,result);
  });
  await page.goto(base+'admin.html');await page.getByText('Войдите через Relcom ID, чтобы открыть администрирование.',{exact:true}).waitFor();
  if(memberReads||await page.locator('#admin-private').isVisible())throw Error('Anonymous read private administration');
  authenticated=true;await page.getByRole('button',{name:'Проверить доступ ещё раз'}).click();await page.getByText('Вход подтверждён. Для этой страницы нужна роль администратора IPvX.',{exact:true}).waitFor();if(memberReads)throw Error('Participant read inventory');
  admin=true;await page.getByRole('button',{name:'Проверить доступ ещё раз'}).click();await page.getByText('Найдено: 4. Показано: 2.',{exact:true}).waitFor();
  await page.locator('#admin-members-more').click();await page.getByText('Найдено: 4. Показано: 4.',{exact:true}).waitFor();
  await page.locator('#admin-members button').filter({hasText:'Синтетический участник <script>'}).click();await page.getByLabel('Причина изменения роли').fill('Синтетическое назначение для проверки');await page.getByRole('button',{name:'Применить роль',exact:true}).click();
  await page.getByText('Не удалось получить подтверждение сервера.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Применить роль',exact:true}).click();await page.getByText('Роль сохранена.',{exact:true}).waitFor();
  if(effects!==1||keys[0]!==keys[1])throw Error('Malformed committed response duplicated role change');
  await page.getByLabel('Причина изменения доступа').fill('Синтетическая временная блокировка');await page.getByRole('button',{name:'Заблокировать участие',exact:true}).click();await page.getByRole('button',{name:'Восстановить участие',exact:true}).waitFor();
  await page.getByRole('button',{name:'Применить роль',exact:true}).click();await page.getByText('Сначала восстановите доступ пользователя.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Восстановить участие',exact:true}).click();await page.getByText('Доступ восстановлен.',{exact:true}).waitFor();
  if(await page.locator('#admin-members script,#admin-queue script').count())throw Error('Profile/queue XSS');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Administration overflow '+width);
  if(width===1440||width===390)await page.screenshot({path:`browser-evidence/admin-${width}.png`,fullPage:true});
  // Self/owner protection is also enforced in backend tests.
  await page.locator('#admin-members button').filter({hasText:owner.label}).click();if(await page.getByRole('button',{name:'Заблокировать участие',exact:true}).isEnabled())throw Error('Owner block exposed');
  await page.locator('#admin-members button').filter({hasText:'Синтетический участник <script>'}).click();await page.getByLabel('Причина изменения роли').fill('Проверка отзыва прав');revoke=true;await page.getByRole('button',{name:'Применить роль',exact:true}).click();await page.waitForFunction(()=>document.getElementById('admin-private').hidden);
  if(await page.locator('#admin-members button').count())throw Error('Revoked admin retained private inventory');
  if(errors.length)throw Error(errors.join('\n'));
  checks.push({width,anonymous_denied:true,participant_denied:true,pagination:true,idempotent_retry:true,block_restore:true,revocation_clears_private:true});await page.close();
 }
 await fs.writeFile('browser-evidence/admin-checks.json',JSON.stringify({data:'synthetic browser fixtures; no production role changed',checks},null,2));
 console.log('Administration: four widths, private access, role retry, block/restore and revocation passed');
}finally{await browser.close();}
