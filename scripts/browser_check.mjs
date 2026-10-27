import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});await fs.mkdir('browser-evidence',{recursive:true});let checks=[];
for(const width of [1440,1280,768,390]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let session={authenticated:false,user:null,membership:'not_granted_by_sign_in'},sessionCode=200;
 let feed={items:[]},feedCode=200;
 await page.route('**/auth/session',route=>route.fulfill({status:sessionCode,contentType:'application/json',body:JSON.stringify(session)}));
 await page.route('https://press.relcom.com/embed/v1/sites/**',route=>route.fulfill({status:feedCode,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(feed)}));
 for(const route of ['index.html','architecture.html','experiments.html','rfcs.html','participate.html','governance.html','saved-trace.html','account.html','blog.html','history.html','rfc-0005.html']){
  await page.goto(base+route);await page.evaluate(()=>document.fonts.ready);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw Error(route+' overflow '+width);
  if(route==='account.html')await page.getByText('Вы не вошли.',{exact:false}).waitFor();
  if(route==='blog.html'){await page.getByText('Пока нет опубликованных статей.',{exact:false}).waitFor();if(await page.locator('#press-retry').isVisible())throw Error('Unexpected empty-state retry');}
  if(['index.html','experiments.html','participate.html','saved-trace.html','account.html','blog.html','history.html','rfc-0005.html'].includes(route))await page.screenshot({path:`browser-evidence/${route}-${width}.png`,fullPage:true});
  if(route==='history.html'){if(await page.locator('.history-entry').count()<41)throw Error('Missing attributed history');await page.locator('.history-entry summary').first().click();}
  if(route==='experiments.html'){await page.getByRole('table').waitFor();if(await page.locator('#llm-transcript details').count()!==6)throw Error('Missing measured transcripts');await page.locator('#llm-transcript summary').first().click();await page.screenshot({path:`browser-evidence/llm-open-${width}.png`,fullPage:true});}
  checks.push({width,route,overflow});
 }
 session={authenticated:true,user:{sub:'fixture-sub',name:'Исследователь с очень длинным именем для проверки переноса',email:'researcher-fixture@example.invalid',emailVerified:true},expiresAt:new Date(Date.now()+60000).toISOString(),membership:'not_granted_by_sign_in'};
 await page.goto(base+'account.html');await page.getByText('Электронная почта подтверждена Relcom ID',{exact:true}).waitFor();
 if(await page.locator('#session-verified form').getAttribute('method')!=='post')throw Error('Logout must POST');
 if(await page.locator('#session-verified form').getAttribute('action')!=='https://ipvx.org/auth/logout')throw Error('Wrong logout origin');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Verified account overflow '+width);
 await page.screenshot({path:`browser-evidence/account-verified-${width}.png`,fullPage:true});
 session.expiresAt=new Date(Date.now()-1000).toISOString();await page.goto(base+'account.html');await page.getByText('Сеанс истёк.',{exact:false}).waitFor();
 sessionCode=503;await page.goto(base+'account.html');await page.getByRole('button',{name:'Проверить вход ещё раз'}).waitFor();
 await page.screenshot({path:`browser-evidence/account-error-${width}.png`,fullPage:true});
 sessionCode=200;session={authenticated:false,user:null};await page.getByRole('button',{name:'Проверить вход ещё раз'}).click();await page.getByText('Вы не вошли.',{exact:false}).waitFor();
 await page.goto(base+'account.html?auth=error');await page.getByText('Вход не подтверждён.',{exact:false}).waitFor();
 feed={items:[{title:'<img src=x onerror=alert(1)> Проверка IPvX',excerpt:'Текст <script> не выполняется',url:'https://ipvx.press.relcom.org/articles/browser-fixture',publishedAt:'2026-10-27T09:00:00Z',readingMinutes:4},{title:'Недопустимая ссылка',url:'https://example.invalid/unsafe'},{title:'Схема JavaScript',url:'javascript:alert(1)'}]};
 await page.goto(base+'blog.html');await page.locator('.press-article').waitFor();
 if(await page.locator('.press-article').count()!==1||await page.locator('.press-article img,.press-article script').count())throw Error('Feed escaping/URL allowlist failed');
 await page.screenshot({path:`browser-evidence/blog-populated-${width}.png`,fullPage:true});
 feedCode=503;await page.goto(base+'blog.html');await page.getByRole('button',{name:'Попробовать ещё раз'}).waitFor();
 feedCode=200;feed={items:[]};await page.getByRole('button',{name:'Попробовать ещё раз'}).click();await page.getByText('Пока нет опубликованных статей.',{exact:false}).waitFor();
 await page.goto(base+'architecture.html');await page.getByRole('button',{name:'3. Выполнить',exact:true}).focus();await page.keyboard.press('Enter');await page.getByRole('heading',{name:'Агент B запускает свою модель'}).waitFor();
 await page.goto(base+'participate.html');await page.getByLabel('Короткое название').fill('Browser fixture: model proposal');await page.getByLabel('Цель и способ проверки').fill('Fixture, no secrets. Local model, reproducible task.');
 // Inspect the outgoing draft URL; never actually create a GitHub issue in UI tests.
 await page.route('https://github.com/relcom-technologies/ipvx-research/issues/new?**',async route=>{const url=new URL(route.request().url());if(!url.searchParams.get('body').includes('Fixture'))throw Error('Proposal body missing');await route.abort();});
 await page.getByRole('button',{name:'Открыть заявку в GitHub'}).click();
 await page.goto(base+'participate.html');await page.getByLabel('Короткое название').fill('Long input');await page.getByLabel('Цель и способ проверки').fill('Факт '.repeat(750));await page.getByRole('button',{name:'Открыть заявку в GitHub'}).click();await page.getByText('Заявка слишком длинная для ссылки.',{exact:false}).waitFor();
 await page.route('**/data/llm-summary.json',route=>route.abort());await page.goto(base+'experiments.html');await page.getByText('Не удалось загрузить файл данных.',{exact:false}).waitFor();await page.screenshot({path:`browser-evidence/report-error-${width}.png`,fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));await page.close();
}
await browser.close();await fs.writeFile('browser-evidence/checks.json',JSON.stringify(checks,null,2));
