import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});const checks=[];
try {
 for(const language of ['ru','en','de','es'])for(const width of [1440,768,390]){
  const suffix=language==='ru'?'':'.'+language;
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}packet-replay${suffix}.html#observatory`);
  if(await page.locator('.obs-case').count()!==4||await page.locator('.obs-node').count()!==3||await page.locator('.obs-step').count()!==28)throw Error('Incomplete task/node disclosures');
  const first=page.locator('#obs-case-delivery');
  if(await first.getAttribute('open')===null)throw Error('Default task not open');
  await first.locator('.obs-step>summary').nth(0).click();
  if(language!=='en')await first.locator('.obs-step').first().locator('details>summary').click();
  if(!(await first.innerText()).includes('A1: Accepted native run completed 384/384'))throw Error('Actual input evidence missing');
  await first.locator('.obs-step>summary').nth(1).click();
  if(!(await first.innerText()).includes('8196.360'))throw Error('Draft inference timing missing');
  await first.locator('.obs-step>summary').nth(2).click();
  if(!(await first.innerText()).includes('d5cb8cd8c779483197db58de1f848aba'))throw Error('Real request ID missing');
  await first.locator('.obs-step>summary').nth(4).click();
  if(!(await first.innerText()).includes('9c769a29e5e142e190e04cb1a326027e'))throw Error('Separate review message missing');
  await page.locator('#obs-node-R1>summary').click();
  if(!(await page.locator('#obs-node-R1').innerText()).includes('ipvx:agent:'))throw Error('Relay identity missing');
  await page.locator('.obs-more>summary').last().click();
  if(await page.locator('a[href="data/strict-agent-manifest.json"]').count()!==1)throw Error('Manifest missing');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Document overflow '+language+'/'+width);
  if(width===390||width===1440){await page.locator('#observatory').screenshot({path:`browser-evidence/observatory-${language}-${width}.png`});}
  await page.goto(`${base}packet-replay${suffix}.html#obs-node-B`);
  if(await page.locator('#obs-node-B').getAttribute('open')===null)throw Error('Direct node link did not open');
  await page.goto(`${base}packet-replay${suffix}.html#obs-case-speed`);
  if(await page.locator('#obs-case-speed').getAttribute('open')===null)throw Error('Direct task link did not open');
  if(errors.length)throw Error(errors.join('\n'));
  checks.push({language,width,tasks:4,stages:28,nodes:3,source_evidence:true,deep_links:true,no_overflow:true});await page.close();
 }
 const ctx=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:1000},reducedMotion:'reduce'});const page=await ctx.newPage();
 await page.goto(`${base}packet-replay.html#observatory`);await page.locator('#obs-case-internet>summary').click();
 if(await page.locator('#obs-case-internet').getAttribute('open')===null)throw Error('Native task disclosure requires JavaScript');
 await page.locator('#obs-node-R1>summary').click();
 if(await page.locator('#obs-node-R1').getAttribute('open')===null)throw Error('Native node disclosure requires JavaScript');
 await ctx.close();await fs.writeFile('browser-evidence/observatory-checks.json',JSON.stringify({checks,no_javascript:true},null,2));
 console.log(`${checks.length} localized observatory states; source linkage and no-JS controls verified`);
}finally{await browser.close();}
