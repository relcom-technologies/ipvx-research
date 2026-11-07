// Forum pages against a synthetic API: plain-text rendering, sign-in gates, posting, moderation, widths, languages.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const root=process.cwd();
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const out=root+'/browser-evidence';await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const hostile='<img src=x onerror="window.__forumXss=1">';
const member={id:'member_'+'0'.repeat(24),label:'Участник 000000',named:false};
const stamp='2026-11-07T18:00:00Z';
function fixture(){
 const threads=[{id:1,category:'bcp',subject:'h5',title:'Synthetic topic '+hostile,status:'published',locked:false,author:member,replies:1,createdAt:stamp,lastActivityAt:stamp}];
 const posts=[{id:1,thread:1,text:'Opening text <script>window.__forumXss=1</script>',replyTo:null,status:'published',author:member,createdAt:stamp},
  {id:2,thread:1,text:'Second line\nwith a break',replyTo:1,status:'published',author:{...member,label:'Alice Novak',named:true},createdAt:stamp}];
 return {threads,posts,writes:[],keys:new Set()};
}
async function open(width,{signedIn=false,roles=[],path='forum.html'}={}){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[],state=fixture();
 page.on('pageerror',error=>errors.push(error.message));
 const reply=(route,status,data)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 await page.route('**/auth/session',route=>reply(route,200,{authenticated:signedIn,user:null}));
 await page.route('**/community/v1/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.replace('/community/v1',''),method=request.method();
  if(method==='GET'){
   if(path==='/session')return reply(route,200,{authenticated:signedIn,author:signedIn?member:null,roles:signedIn?['participant',...roles]:[],access:signedIn?'active':'anonymous',capabilities:[]});
   if(path==='/forum/profile')return signedIn?reply(route,200,{author:member,pendingPosts:0,publishesDirectly:roles.length>0}):reply(route,401,{error:'sign_in_required'});
   if(path==='/forum/categories')return reply(route,200,{categories:['bcp','blog','rfc','experiments','architecture','questions','meta'].map((id,i)=>({id,threads:i?0:1,lastActivityAt:i?null:stamp}))});
   if(/^\/forum\/(categories\/bcp|subjects\/(h5|rfc-0005\.s3))\/threads$/.test(path))return reply(route,200,{threads:state.threads,nextBefore:null});
   if(path==='/forum/threads/1')return reply(route,200,{thread:state.threads[0],posts:state.posts,nextAfter:null});
   if(path==='/forum/search')return reply(route,200,{results:[{post:1,thread:1,title:state.threads[0].title,excerpt:'…Opening text…'}]});
   if(path==='/forum/moderation')return roles.length?reply(route,200,{queue:url.searchParams.get('queue'),posts:[{...state.posts[0],id:3,status:'pending',review:{queue:'people',note:'Unsure '+hostile},threadTitle:'Queued '+hostile,category:'bcp',opening:false}],nextBefore:null}):reply(route,403,{error:'role_required'});
   return reply(route,404,{error:'route_not_found'});
  }
  if(!signedIn)return reply(route,401,{error:'sign_in_required'});
  const key=request.headers()['idempotency-key'];
  if(!/^[a-f0-9]{32}$/.test(key||''))throw Error('Missing idempotency key');
  if(request.headers()['content-type']!=='application/json')throw Error('JSON content type expected');
  const body=request.postDataJSON();state.writes.push({path,body});state.keys.add(key);
  if(path==='/forum/categories/bcp/threads')return reply(route,201,{thread:{...state.threads[0],id:1,title:body.title,status:'pending'},post:{...state.posts[0],status:'pending'},visibility:'own-private'});
  if(path==='/forum/threads/1/posts')return reply(route,201,{post:{id:9,thread:1,text:body.text,replyTo:body.replyTo??null,status:'pending',author:member,createdAt:stamp},visibility:'own-private'});
  if(path==='/forum/posts/3/moderation')return reply(route,200,{post:{...state.posts[0],id:3,status:body.action==='publish'?'published':'hidden'}});
  if(path==='/forum/profile')return reply(route,200,{author:{...member,label:body.name,named:true}});
  return reply(route,404,{error:'route_not_found'});
 });
 await page.goto(base+path);
 await page.waitForFunction(()=>!document.querySelector('.forum-status')?.textContent.includes('…'));
 return {page,errors,state};
}
async function settle(page){await page.waitForFunction(()=>!document.querySelector('.forum-status')?.textContent.includes('…'));}
async function noOverflow(page,label){
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 if(overflow>1)throw Error(label+': horizontal overflow '+overflow);
}
const checks=[];
for(const width of [1440,768,390]){
 // Anonymous reader: categories, sign-in gate, nothing executable from data.
 let {page,errors}=await open(width);
 if(await page.locator('.forum-category').count()!==7)throw Error('categories missing at '+width);
 if(!(await page.locator('.forum-who a[href*="/auth/login?returnTo="]').count()))throw Error('sign-in link missing');
 if(await page.locator('.forum-compose form').count())throw Error('composer shown to an anonymous reader');
 await noOverflow(page,'home '+width);
 await page.screenshot({path:`${out}/forum-home-${width}.png`,fullPage:true});
 await page.goto(base+'forum.html?t=1');await settle(page);
 if(await page.evaluate(()=>window.__forumXss))throw Error('post text executed');
 if(!(await page.locator('.forum-heading').first().textContent()).includes('<img'))throw Error('title not rendered as text');
 if(await page.locator('.forum-post').count()!==2)throw Error('posts missing');
 if(!(await page.locator('#post-2 .forum-text').textContent()).includes('\n'))throw Error('line break lost');
 if(await page.locator('.forum-reply form').count())throw Error('reply form shown to an anonymous reader');
 await noOverflow(page,'thread '+width);
 await page.screenshot({path:`${out}/forum-thread-${width}.png`,fullPage:true});
 if(errors.length)throw Error('page errors: '+errors.join('; '));
 await page.close();
 checks.push(['anonymous',width]);
}
{
 // Participant: open a topic, reply to a post, set a public name; every write keyed and JSON.
 const {page,errors,state}=await open(1440,{signedIn:true,path:'forum.html?c=bcp'});
 await page.fill('.forum-compose input[name=title]','A new topic');
 await page.fill('.forum-compose textarea[name=text]','Body of the new topic');
 await Promise.all([page.waitForURL(/forum\.html\?t=1$/),page.click('.forum-compose button[type=submit]')]);
 await settle(page);
 await page.click('#post-1 .forum-link-button');
 await page.fill('.forum-reply textarea','A reply '+hostile);
 await page.click('.forum-reply button[type=submit]');
 await page.waitForSelector('#post-9');
 if(!(await page.locator('#post-9 .forum-state').count()))throw Error('pending reply not marked');
 if(await page.evaluate(()=>window.__forumXss))throw Error('reply executed');
 const writes=state.writes.map(w=>w.path).join(',');
 if(writes!=='/forum/categories/bcp/threads,/forum/threads/1/posts')throw Error('unexpected writes: '+writes);
 if(state.writes[0].body.title!=='A new topic'||state.writes[1].body.replyTo!==1)throw Error('write bodies wrong');
 if(state.keys.size!==2)throw Error('each write needs its own idempotency key');
 await page.goto(base+'forum.html');await settle(page);
 await page.fill('.forum-profile input[name=name]','Alice Novak');
 await page.click('.forum-profile button[type=submit]');
 await page.waitForFunction(()=>document.querySelector('.forum-profile .forum-form-status')?.textContent.includes('Alice Novak'));
 if(errors.length)throw Error('page errors: '+errors.join('; '));
 await page.close();checks.push(['participant',1440]);
}
{
 // Moderator: queues, a decision with a reason; a participant cannot open the queue.
 const {page,errors,state}=await open(390,{signedIn:true,roles:['moderator'],path:'forum.html?mod=people'});
 if(await page.locator('.forum-tabs a').count()!==3)throw Error('queue tabs missing');
 if(!(await page.locator('.forum-post .small').first().textContent()).includes('<img'))throw Error('review note not text');
 await page.click('.forum-post .forum-moderate summary');
 await page.fill('.forum-post .forum-moderate input[name=reason]','Reviewed and fine');
 await page.click('.forum-post .forum-moderate button[type=submit]');
 await page.waitForFunction(()=>document.querySelector('.forum-post .forum-form-status')?.textContent.length>0);
 const decision=state.writes.find(w=>w.path==='/forum/posts/3/moderation');
 if(decision?.body.action!=='publish'||decision.body.reason!=='Reviewed and fine')throw Error('moderation request wrong');
 await noOverflow(page,'moderation 390');
 await page.screenshot({path:`${out}/forum-moderation-390.png`,fullPage:true});
 if(errors.length)throw Error('page errors: '+errors.join('; '));
 await page.close();
 const participant=await open(1440,{signedIn:true,path:'forum.html?mod=people'});
 if(!(await participant.page.locator('.forum-status.forum-error').count()))throw Error('participant reached moderation');
 await participant.page.close();checks.push(['moderator',390]);
}
{
 // A project object's discussions: readable label, a link back in the same edition, category suggested.
 const {page,errors}=await open(390,{signedIn:true,path:'forum.html?s=rfc-0005.s3'});
 if(!(await page.locator('.forum-view h2').first().textContent()).includes('RFC-0005, раздел 3'))throw Error('subject label missing');
 if(await page.locator('.forum-lead a[href="rfc-0005.html#s3"]').count()!==1)throw Error('link back to the RFC section missing');
 if(await page.locator('.forum-compose select[name=category]').inputValue()!=='rfc')throw Error('category not suggested');
 await noOverflow(page,'subject 390');
 await page.screenshot({path:`${out}/forum-subject-390.png`,fullPage:true});
 if(errors.length)throw Error('page errors: '+errors.join('; '));
 await page.close();
 const english=await open(768,{path:'forum.en.html?s=rfc-0005.s3'});
 if(await english.page.locator('.forum-lead a[href="rfc-0005.en.html#s3"]').count()!==1)throw Error('link back leaves the English edition');
 await english.page.close();checks.push(['subject',390]);
}
for(const [language,word] of [['en','Categories'],['de','Kategorien'],['es','Categorías']]){
 const {page,errors}=await open(768,{path:`forum.${language}.html`});
 if((await page.locator('.forum-view h2').first().textContent())!==word)throw Error(language+' view not translated');
 if(!(await page.locator(`.forum-category a[href^="forum.${language}.html?c="]`).count()))throw Error(language+' links leave the edition');
 if(errors.length)throw Error('page errors: '+errors.join('; '));
 await page.close();checks.push([language,768]);
}
await browser.close();
await fs.writeFile(out+'/forum-checks.json',JSON.stringify(checks,null,1)+'\n');
console.log('forum browser checks passed:',checks.length);
