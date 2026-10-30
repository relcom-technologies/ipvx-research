import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});
const checks=[];
const assert=(condition,message)=>{if(!condition)throw Error(message);};
try{for(const lang of ['ru','en','de','es'])for(const width of [1440,768,390]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[],mutations=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')mutations.push(r.url());});
 const suffix=lang==='ru'?'':'.'+lang;
 await page.route('**/auth/session',r=>r.fulfill({json:{authenticated:false,user:null}}));
 await page.route('**/community/v1/session',r=>r.fulfill({json:{authenticated:false,roles:[],author:null}}));
 await page.route('**/community/v1/rfcs/**/entries?*',r=>r.fulfill({json:{entries:[{id:42,rfc:'rfc-0007',kind:'comment',status:'published',text:'Synthetic public comment',createdAt:1793300000,author:{label:'Public fixture'}}],nextBefore:null}}));
 await page.goto(base+'community'+suffix+'.html');await page.waitForFunction(()=>!document.getElementById('discussion-refresh').disabled);
 const original=page.locator('#comment-c1676dea-1818-47d6-a841-1a003e5ed585');await original.locator('summary').click();
 assert(await original.locator('[data-research-case]').count()===1,'missing comment-to-chain link');
 await original.locator('[data-research-case]').click();await page.waitForURL('**/experiments'+suffix+'.html#research-a2a-recovery');
 assert(await page.locator('.research-case').count()===2,'unified registry missing');
 assert(!await page.locator('#experiment-draft').evaluate(e=>e.open),'draft unexpectedly open');
 if(lang==='ru')await page.locator('#research-links').screenshot({path:`browser-evidence/research-closed-${width}.png`});
 await page.locator('#research-a2a-recovery a[href*="?case="]').click();await page.waitForFunction(()=>document.getElementById('experiment-draft')?.open);
 const form=page.locator('#research-draft-form');assert(await form.isVisible(),'draft link did not open form');
 assert((await form.locator('[name=source]').inputValue()).includes('c1676dea'),'source reference lost');
 assert(!await page.locator('#research-draft-output').isVisible(),'unreviewed draft exposed submit link');
 await form.locator('button').click();assert(!await page.locator('#research-draft-output').isVisible(),'empty fields bypass validation');
 for(const field of ['task','failures','scope','artifacts'])await form.locator(`[name=${field}]`).fill('Synthetic fixture <img src=x onerror="window.injected=1"> / '+field);
 if(lang==='ru')await page.locator('#experiment-draft').screenshot({path:`browser-evidence/research-draft-${width}.png`});
 const before=page.url();await form.locator('button').click();assert(page.url()===before,'assembling draft navigated or submitted');
 assert(await page.locator('#research-draft-output').isVisible(),'review output missing');assert(await page.evaluate(()=>document.getElementById('research-draft-output').clientWidth<=document.getElementById('research-draft-form').clientWidth),'preview exceeds readable form measure');
 const body=await page.locator('#research-draft-text').inputValue();assert(body.includes('<img src=x'),'draft text was not preserved');assert(!await page.evaluate(()=>!!window.injected),'draft HTML executed');
 const href=await page.locator('#research-draft-submit').getAttribute('href');assert(new URL(href).origin==='https://github.com'&&new URL(href).searchParams.get('draft')===body,'GitHub field lost text');
 const downloadPromise=page.waitForEvent('download');await page.locator('#research-draft-download').click();const download=await downloadPromise;const downloaded=await fs.readFile(await download.path(),'utf8');assert(downloaded===body,'download differs from reviewed text');
 await form.locator('[name=task]').fill('Updated task');assert(!await page.locator('#research-draft-output').isVisible(),'stale draft links remain');
 for(const field of ['source','hypothesis','task','failures','scope','artifacts'])await form.locator(`[name=${field}]`).fill('L'.repeat(2000));await form.locator('button').click();assert((await page.locator('#research-draft-submit').getAttribute('href'))==='https://github.com/relcom-technologies/ipvx-research/issues/new?template=experiment.yml','oversized draft fallback absent');
 await page.locator('#research-draft-text').focus();assert(await page.locator('#research-draft-text').evaluate(e=>getComputedStyle(e).outlineWidth)==='3px','focus not visible');
 assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'registry overflow '+lang+'/'+width);

 await page.goto(base+'experiments'+suffix+'.html?source=javascript%3Aalert(1)#experiment-draft');assert(await page.locator('#research-draft-status').textContent(),'invalid source not explained');assert(await page.locator('#draft-source').inputValue()==='','hostile source accepted');
 await page.goto(base+'rfc-0007'+suffix+'.html');await page.waitForSelector('[data-experiment-draft]');const link=page.locator('.community-public [data-experiment-draft]');assert(await link.count()===1,'public RFC draft link absent');await link.click();await page.waitForURL('**/experiments'+suffix+'.html?source=**');await page.waitForFunction(()=>document.getElementById('experiment-draft')?.open);assert((await page.locator('#draft-source').inputValue())==='https://ipvx.org/rfc-0007.html#entry-42','RFC public source not preserved');
 assert(!mutations.length,'browser unexpectedly wrote to a service');assert(!errors.length,errors.join('\n'));
 checks.push({lang,width,curated_links:true,review_before_submission:true,exact_download:true,public_rfc_source:true,untrusted_text_safe:true,no_service_mutations:true,no_overflow:true});await page.close();
}
const nojs=await browser.newPage({javaScriptEnabled:false});await nojs.goto(base+'experiments.html');assert(await nojs.locator('.research-case a').count()>4,'no-JS evidence links missing');await nojs.close();
await fs.writeFile('browser-evidence/research-links.json',JSON.stringify(checks,null,2)+'\n');console.log('Research evidence chains and local drafts: 12 combinations passed; static fallback verified');
}finally{await browser.close();}
