import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const root=process.cwd();
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const out=root+'/browser-evidence';await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const checks=[];
for(const width of [1440,1280,768,390]){
 const page=await browser.newPage({viewport:{width,height:1050},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 const actor={id:'member_'+('0'.repeat(24)),label:'Участник fixture'};
 const entry=(id,kind,status,title,text)=>({id,rfc:'rfc-0005',kind,status,title,text,author:actor,createdAt:'2026-10-27T11:00:00Z',votes:{counts:{yes:1,no:0,abstain:0},binding:false}});
 const rows=[entry(1,'comment','published','','Синтетический комментарий <script>alert(1)</script>'),entry(2,'proposal','published','Синтетическое предложение','Уточнить ограничение протокола. Это fixture, а не реальный вклад.'),entry(3,'comment','pending','','Частная запись fixture на модерации.')];
 let authenticated=false,roles=[],fail=false,loseNext=false,malformedNext=false,wrongShapeNext=false,voteLoseNext=false,shortPage=false,revokeOnWrite=false,serverEffects=0,actualVote='withdraw';
 const requestKeys=[],voteKeys=[],dedupe=new Map(),voteCache=new Map(),reads=[];
 const response=(route,status,data)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 await page.route('**/auth/session',route=>response(route,200,{authenticated:true,user:{sub:'fixture',name:'Fixture',email:'fixture@example.invalid',emailVerified:true,roles:['admin']},expiresAt:new Date(Date.now()+600000).toISOString()}));
 await page.route('**/community/v1/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.replace('/community/v1',''),method=request.method();
  if(fail)return response(route,503,{error:'community_temporarily_unavailable'});
  if(method==='GET'){
   reads.push(path);
   if(path==='/session')return response(route,200,{authenticated,author:authenticated?actor:null,roles:authenticated?['participant',...roles]:[],governance:{votesBinding:false},capabilities:authenticated?['submit_pending','advisory_vote']:[]});
   if(path.includes('/rfcs/')&&path.endsWith('/entries')){
    const own=url.searchParams.get('mine')==='1',kind=url.searchParams.get('kind');
    if(own&&!authenticated)return response(route,401,{error:'sign_in_required'});
    return response(route,200,{entries:rows.filter(row=>row.kind===kind&&(own?row.author.id===actor.id:row.status==='published')),nextBefore:null});
   }
   if(path==='/moderation'){if(shortPage)return response(route,200,{entries:[{...rows[2],id:url.searchParams.has('before')?1:3}],nextBefore:url.searchParams.has('before')?null:3});return response(route,roles.includes('admin')?200:403,{entries:rows.filter(x=>x.status==='pending'),nextBefore:null});}
   if(path==='/audit')return response(route,roles.includes('admin')?200:403,{events:[{id:shortPage?(url.searchParams.has('before')?9:10):1,action:'publish',actor:actor.id,target:'4',detail:JSON.stringify({reason:'Синтетическая причина <img src=x>'}),at:1793102400}],nextBefore:shortPage&&!url.searchParams.has('before')?10:null});
   const match=path.match(/^\/entries\/(\d+)$/);if(match)return response(route,200,{entry:rows.find(x=>x.id===Number(match[1]))});
   return response(route,404,{error:'entry_not_found'});
  }
  if(!authenticated)return response(route,401,{error:'sign_in_required'});
  if(revokeOnWrite){roles=[];return response(route,403,{error:'role_required'});}
  const body=request.postDataJSON(),key=request.headers()['idempotency-key'];
  if(!/^[a-f0-9]{32}$/.test(key||''))throw Error('Missing stable idempotency key');
  if(path.includes('/rfcs/')&&path.endsWith('/entries')){
   requestKeys.push(key);
   if(dedupe.has(key))return response(route,201,dedupe.get(key));
   const created=entry(Math.max(...rows.map(row=>row.id))+1,body.kind,'pending',body.title,body.text);rows.push(created);const result={entry:created};dedupe.set(key,result);serverEffects++;
   if(loseNext){loseNext=false;return route.abort('failed');}
   if(malformedNext){malformedNext=false;return route.fulfill({status:200,contentType:'application/json',body:'{"entry":'});}
   if(wrongShapeNext){wrongShapeNext=false;return response(route,200,{unexpected:true});}
   return response(route,201,result);
  }
  const match=path.match(/^\/entries\/(\d+)\/(vote|moderation)$/);
  if(match){const row=rows.find(x=>x.id===Number(match[1]));if(match[2]==='vote'){voteKeys.push(key);if(voteCache.has(key))return response(route,200,voteCache.get(key));actualVote=body.value;row.votes.counts={yes:1+(actualVote==='yes'?1:0),no:actualVote==='no'?1:0,abstain:actualVote==='abstain'?1:0};const result=JSON.parse(JSON.stringify({entry:row,binding:false}));voteCache.set(key,result);if(voteLoseNext){voteLoseNext=false;return route.abort('failed');}return response(route,200,result);}row.status=body.action==='publish'?'published':'hidden';return response(route,200,{entry:row,binding:false});}
  if(path==='/roles')return response(route,200,{authorId:body.authorId,roles:[body.role]});
  return response(route,404,{error:'route_not_found'});
 });
 let navigation=0; const go=async path=>{const url=new URL(path,base);url.searchParams.set('fixture',String(++navigation));await page.goto(url.href);await page.evaluate(()=>document.fonts.ready);};
 const noOverflow=async state=>{if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(state+' overflow '+width);checks.push({width,state,pass:true});};
 await go('rfc-0006.html');await page.getByRole('heading',{name:'Узел без TCP/IP',exact:true}).waitFor();await noOverflow('strict-diagram');await page.screenshot({path:`${out}/community-native-hero-${width}.png`});
 await go('rfc-0005.html#discussion');await page.locator('.community-public .community-entry').waitFor();
 if(await page.locator('.community-submit').isVisible())throw Error('Anonymous form visible');
 if(await page.locator('.community-public script,.community-public img').count())throw Error('Public text interpreted as HTML');
 await noOverflow('anonymous-public');
 authenticated=true;await go('rfc-0005.html#discussion');await page.locator('.community-submit').waitFor();
 await page.getByLabel('Тип сообщения',{exact:true}).selectOption('proposal');await page.getByLabel('Заголовок',{exact:false}).fill('Fixture pending proposal');await page.getByLabel('Текст',{exact:true}).fill('Синтетическое предложение <img src=x onerror=alert(1)>; не настоящий внешний участник.');
 loseNext=true;await page.getByRole('button',{name:'Отправить на модерацию',exact:true}).click();await page.locator('.community-submit-status').getByText('Текст сохранён в форме',{exact:false}).waitFor();
 await page.getByRole('button',{name:'Отправить на модерацию',exact:true}).click();await page.locator('.community-submit-status').getByText('Сообщение № 4 на модерации.',{exact:false}).waitFor();
 if(requestKeys.length!==2||requestKeys[0]!==requestKeys[1]||serverEffects!==1)throw Error('Retry duplicated request effect');
 if(await page.locator('.community-public [data-entry-id="4"]').count())throw Error('Pending leaked into public view');
 await page.locator('.community-own-list [data-entry-id="4"]').waitFor();
 for(const [failure,id] of [['malformed',5],['shape',6]]){
  await page.getByLabel('Заголовок',{exact:false}).fill('Fixture '+failure+' reply');await page.getByLabel('Текст',{exact:true}).fill('Fixture committed request with unreadable acknowledgement: '+failure);
  if(failure==='malformed')malformedNext=true;else wrongShapeNext=true;
  await page.getByRole('button',{name:'Отправить на модерацию',exact:true}).click();await page.locator('.community-submit-status').getByText('Текст сохранён в форме',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Отправить на модерацию',exact:true}).click();await page.locator('.community-submit-status').getByText('Сообщение № '+id+' на модерации.',{exact:false}).waitFor();
  if(requestKeys.at(-1)!==requestKeys.at(-2)||serverEffects!==id-3)throw Error('Malformed/invalid response lost idempotency key: '+failure);
 }

 await page.locator('.community-public').getByRole('button',{name:'Поддерживаю',exact:true}).click();await page.locator('.community-public .community-vote-status').getByText('Сохранено: поддерживаю',{exact:false}).waitFor();
 
 voteLoseNext=true;await page.locator('.community-public').getByRole('button',{name:'Поддерживаю',exact:true}).click();await page.locator('.community-public .community-vote-status').getByText('Текст сохранён в форме',{exact:false}).waitFor();
 await page.locator('.community-public').getByRole('button',{name:'Против',exact:true}).click();await page.locator('.community-public .community-vote-status').getByText('Сохранено: против',{exact:false}).waitFor();
 await page.locator('.community-public').getByRole('button',{name:'Поддерживаю',exact:true}).click();await page.locator('.community-public .community-vote-status').getByText('Сохранено: поддерживаю',{exact:false}).waitFor();
 if(voteKeys.at(-1)===voteKeys.at(-3)||actualVote!=='yes')throw Error('Changed vote intent replayed an old cached result');
await noOverflow('participant-pending-and-advisory');await page.locator('.community-discussion').screenshot({path:`${out}/community-participant-${width}.png`});
 await go('account.html');await page.locator('.community-account-status').getByText('Учётная запись подтверждена.',{exact:false}).waitFor();
 if(await page.locator('.community-admin').isVisible()||await page.locator('.community-moderation').isVisible())throw Error('Injected auth profile role was trusted');
 if(reads.includes('/moderation')||reads.includes('/audit'))throw Error('Ordinary participant requested private moderation');
 roles=['admin'];await go('account.html');await page.locator('.community-moderation [data-entry-id="4"]').waitFor();
 await noOverflow('administrator-panels');await page.locator('.community-moderation').screenshot({path:`${out}/community-moderation-${width}.png`});
 let pending=page.locator('.community-moderation [data-entry-id="4"]');await pending.getByLabel('Причина решения').fill('Fixture: approve visibility only.');await pending.getByRole('button',{name:'Опубликовать запись'}).click();await page.locator('.community-moderation>p.community-moderation-status').getByText('Запись № 4 опубликована.',{exact:false}).waitFor();
 pending=page.locator('.community-moderation [data-entry-id="4"]');await pending.getByLabel('Причина решения').fill('Fixture: hide visibility only.');await pending.getByRole('button',{name:'Скрыть запись'}).click();await page.locator('.community-moderation>p.community-moderation-status').getByText('Запись № 4 скрыта.',{exact:false}).waitFor();
 await page.getByLabel('Номер участника',{exact:true}).fill('member_'+('1'.repeat(24)));await page.getByLabel('Причина изменения',{exact:true}).fill('Fixture role test only.');await page.getByRole('button',{name:'Применить изменение роли'}).click();await page.locator('.community-role-status').getByText('Изменение сохранено',{exact:false}).waitFor();
 
 shortPage=true;await page.getByRole('button',{name:'Обновить очередь',exact:true}).click();await page.getByRole('button',{name:'Показать ещё из очереди',exact:true}).waitFor();await page.getByRole('button',{name:'Показать ещё из очереди',exact:true}).click();await page.locator('.community-moderation-list [data-entry-id="1"]').waitFor();
 await page.getByRole('button',{name:'Обновить журнал',exact:true}).click();await page.getByRole('button',{name:'Показать предыдущие действия',exact:true}).waitFor();await page.getByRole('button',{name:'Показать предыдущие действия',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.community-audit-event').length===2);await noOverflow('short-page-server-cursor');
revokeOnWrite=true;pending=page.locator('.community-moderation [data-entry-id="3"]');await pending.getByLabel('Причина решения').fill('Fixture revoked moderator role.');await pending.getByRole('button',{name:'Опубликовать запись'}).click();await page.locator('.community-account-status').getByText('Права участия изменились',{exact:false}).waitFor();
 if(await page.locator('.community-admin').isVisible()||await page.locator('.community-moderation').isVisible())throw Error('Revoked private panels remained visible');
 await noOverflow('revoked-role');
 fail=true;await go('rfc-0006.html#discussion');await page.getByRole('button',{name:'Повторить загрузку обсуждения'}).waitFor();await noOverflow('community-unavailable-reading-preserved');await page.locator('.community-discussion').screenshot({path:`${out}/community-error-${width}.png`});
 fail=false;authenticated=false;await page.getByRole('button',{name:'Повторить загрузку обсуждения'}).click();await page.locator('.community-public .community-entry').waitFor();
 if(errors.length)throw Error(errors.join('\n'));
 await page.close();
}
await browser.close();await fs.writeFile(out+'/community-checks.json',JSON.stringify(checks,null,2));console.log('PASS:',checks.length,'community/viewport states plus idempotency, privacy and role gates');
