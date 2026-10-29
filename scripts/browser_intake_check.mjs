import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const checks=[];await fs.mkdir('browser-evidence',{recursive:true});
try{for(const lang of ['ru','en','de','es'])for(const width of [1440,768,390]){
 const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/auth/session',r=>r.fulfill({json:{authenticated:false,user:null}}));
 await page.route('**/community/v1/session',r=>r.fulfill({json:{authenticated:false,roles:[],author:null}}));
 const suffix=lang==='ru'?'':'.'+lang;
 await page.goto(base+'agents'+suffix+'.html');
 if(!await page.locator('#a2a-guide').isVisible())throw Error('missing A2A instructions');
 if(await page.locator('link[rel=agent-card]').getAttribute('href')!=='https://ipvx.org/.well-known/agent-card.json')throw Error('card discovery missing');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('guide overflow '+lang+'/'+width);
 // Synthetic owner queue only: production authentication is tested by server tests.
 await page.route('**/assets/admin.js*',r=>r.fulfill({body:'',contentType:'text/javascript'}));
 await page.route('**/assets/*/admin.js*',r=>r.fulfill({body:'',contentType:'text/javascript'}));
 let reads=0,decisions=0,forbidden=false;
 const id='proposal_'+'a'.repeat(24);
 await page.route('**/community/v1/agents/proposals**',async r=>{
  if(forbidden)return r.fulfill({status:403,json:{error:'project_owner_required'}});
  if(r.request().method()==='POST'){const d=r.request().postDataJSON();if(!d.requestId||d.reason.length<3||Object.hasOwn(d,'actor'))throw Error('unsafe decision');decisions++;return r.fulfill({json:{id,status:d.decision,executionGranted:false,publicationGranted:false}});}
  reads++;return r.fulfill({json:{proposals:[{id,title:'Synthetic fixture: <script>window.injected=1</script>',summary:'Reproduce pinned native evidence. '.repeat(30),agentName:'Self-asserted test agent',kind:'experiment',rfc:'rfc-0006',references:['https://github.com/relcom-technologies/ipvx-research'],status:'pending_owner',reason:'',created:1793200000}],nextOffset:null}});
 });
 await page.goto(base+'admin'+suffix+'.html');await page.evaluate(()=>document.getElementById('admin-private').hidden=false);
 if(reads)throw Error('owner queue loaded without explicit action');
 await page.locator('#agent-intake-open').click();await page.locator('#agent-intake-list summary').click();
 await page.locator('#agent-intake-list textarea').fill('Synthetic owner review: request reproducibility');
 await page.locator('#agent-intake-list button[type=submit]').click();
 await page.waitForFunction(()=>document.querySelector('#agent-intake-list button[type=submit]')?.disabled===false);
 if(decisions!==1||await page.evaluate(()=>!!window.injected))throw Error('review or text safety failed');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('queue overflow '+lang+'/'+width);
 if(width!==768)await page.locator('#agent-intake-owner').screenshot({path:`browser-evidence/a2a-queue-${lang}-${width}.png`});
 forbidden=true;await page.locator('#agent-intake-open').click();await page.waitForFunction(()=>document.getElementById('agent-intake-status').textContent===document.getElementById('agent-intake-owner').getAttribute('data-copy-17'));
 if(errors.length)throw Error(errors.join('\n'));checks.push({lang,width,synthetic_fixture:true,review:true,unauthorized_rejected:true,no_overflow:true});await page.close();
 }
 await fs.writeFile('browser-evidence/a2a-intake.json',JSON.stringify(checks,null,2));console.log('A2A guide and synthetic owner queue: 12 language/viewport combinations passed');
}finally{await browser.close();}
