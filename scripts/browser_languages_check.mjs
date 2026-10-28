import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});
const checks=[];
try{
 for(const lang of ['en','de','es'])for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/auth/session',r=>r.fulfill({status:200,contentType:'application/json',body:'{"authenticated":false,"user":null}'}));
  await page.route('**/community/v1/session',r=>r.fulfill({status:200,contentType:'application/json',body:'{"authenticated":false,"roles":[],"author":null}'}));
  for(const name of ['index','architecture','experiments','packet-replay','rfc-0006','history','account','admin']){
   await page.goto(`${base}${name}.${lang}.html`);await page.evaluate(()=>document.fonts.ready);
   if(await page.locator('html').getAttribute('lang')!==lang)throw Error('Wrong document language');
   if(await page.locator('h1').count()!==1)throw Error('Heading hierarchy');
   if(await page.locator('.language-switch a').count()!==4)throw Error('Language navigation missing');
   if(await page.locator('.translation-note').count()!==1)throw Error('Unmarked translation');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`${name}/${lang}/${width} overflows`);
   if(name==='packet-replay'){
    await page.locator('#agent-message:enabled').waitFor();
    if(await page.locator('#agent-message option').count()!==48)throw Error('Missing actual deliveries');
    await page.locator('#agent-step').click();
    if(!(await page.locator('#agent-hop-text').innerText()).includes('R1'))throw Error('Translated step broke route');
    await page.locator('#agent-play').click();
    await page.waitForFunction(()=>document.getElementById('agent-play').textContent!=='Пауза'&&document.getElementById('agent-hop').textContent.startsWith('4'));
    if(width===390)await page.locator('#native-agents').screenshot({path:`browser-evidence/languages-agents-${lang}-390.png`});
   }
   if(name==='history'){
    const count=await page.locator('.history-entry').count();
    if(count<98||await page.locator('.history-entry .translation-original').count()!==count)throw Error('History translation/original missing');
    await page.locator('.history-entry summary').first().click();
    await page.locator('.history-entry .translation-original summary').first().click();
    if(!await page.locator('.original-record').first().isVisible())throw Error('Original attributed record unavailable');
   }
   if(name==='rfc-0006'){
    await page.locator('.rfc-prose>.translation-original>summary').click();
    if(!await page.locator('.translation-original .rfc-prose[lang=en]').isVisible())throw Error('Original RFC unavailable');
   }
   checks.push({lang,width,page:name,no_overflow:true});
  }
  await page.goto(`${base}packet-replay.${lang}.html#native-agents`);
  await page.locator('.language-switch a[lang=ru]').click();
  if(!page.url().endsWith('packet-replay.html#native-agents'))throw Error('Language switch lost section');
  if(errors.length)throw Error(errors.join('\n'));
  await page.close();
 }
 const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:1000}});
 for(const lang of ['en','de','es']){
  const page=await nojs.newPage();await page.goto(`${base}rfc-0006.${lang}.html`);
  if(await page.locator('.rfc-prose').first().innerText()==='')throw Error('JavaScript required to read RFC');
  if(await page.locator('.language-switch a').count()!==4)throw Error('No-JS language links unavailable');
  await page.close();
 }
 await nojs.close();
 await fs.writeFile('browser-evidence/languages-checks.json',JSON.stringify({checks,no_javascript_languages:3},null,2));
 console.log(`${checks.length} localized page states;3 no-JavaScript RFC editions`);
}finally{await browser.close();}
