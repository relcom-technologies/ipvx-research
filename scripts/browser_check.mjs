import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const browser=await chromium.launch({headless:true});await fs.mkdir('browser-evidence',{recursive:true});let checks=[];
for(const width of [1440,768,390]){
 const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 for(const route of ['index.html','architecture.html','experiments.html','rfcs.html','participate.html','governance.html']){
  await page.goto('http://127.0.0.1:8091/'+route);await page.evaluate(()=>document.fonts.ready);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw Error(route+' overflow '+width);
  if(route==='index.html'||route==='experiments.html'||route==='participate.html')await page.screenshot({path:`browser-evidence/${route}-${width}.png`,fullPage:true});
  checks.push({width,route,overflow});
 }
 await page.goto('http://127.0.0.1:8091/architecture.html');await page.getByRole('button',{name:'3. Выполнить',exact:true}).focus();await page.keyboard.press('Enter');await page.getByRole('heading',{name:'Агент B запускает свою модель'}).waitFor();
 await page.goto('http://127.0.0.1:8091/participate.html');await page.getByLabel('Короткое название').fill('Browser fixture: model proposal');await page.getByLabel('Цель и способ проверки').fill('Fixture, no secrets. Local model, reproducible task.');
 // Inspect the outgoing draft URL; never actually create a GitHub issue in UI tests.
 await page.route('https://github.com/relcom-technologies/ipvx-research/issues/new?**',async route=>{const url=new URL(route.request().url());if(!url.searchParams.get('body').includes('Fixture'))throw Error('Proposal body missing');await route.abort();});
 await page.getByRole('button',{name:'Открыть заявку в GitHub'}).click();
 if(errors.length)throw Error(errors.join('\n'));await page.close();
}
await browser.close();await fs.writeFile('browser-evidence/checks.json',JSON.stringify(checks,null,2));
