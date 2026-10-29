import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});
const snapshot=JSON.parse(await fs.readFile('data/community-discussions.json','utf8')),checks=[];
try{for(const lang of ['ru','en','de','es'])for(const width of [1440,768,390]){
 const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const suffix=lang==='ru'?'':'.'+lang;
 await page.route('**/auth/session',r=>r.fulfill({json:{authenticated:false,user:null}}));
 await page.route('**/community/v1/session',r=>r.fulfill({json:{authenticated:false,roles:[],author:null}}));
 await page.goto(base+'community'+suffix+'.html');
 await page.waitForFunction(()=>!document.getElementById('discussion-refresh').disabled);
 if(await page.locator('.collab-message').count()!==snapshot.comments.length)throw Error('mirror count differs from published data');
 if(await page.locator('#discussion-count').textContent()!==String(snapshot.comments.length))throw Error('visible count mismatch');
 await page.locator('.collab-message summary').last().focus();await page.keyboard.press('Enter');
 if(!await page.locator('.collab-message').last().getAttribute('open')&&await page.locator('.collab-message').last().getAttribute('open')!== '')throw Error('keyboard disclosure failed');
 const opened=await page.locator('.collab-message[open] .collab-message-text').last().textContent();
 if(opened!==snapshot.comments.at(-1).text)throw Error('source body was rewritten');
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('discussion overflow '+lang+'/'+width);
 await page.locator('#external-discussion').screenshot({path:`browser-evidence/discussion-${lang}-${width}.png`});
 // Refresh failure preserves the actual last snapshot instead of claiming zero.
 await page.route('**/data/community-discussions.json',r=>r.abort());await page.locator('#discussion-refresh').click();
 await page.waitForFunction(()=>!document.getElementById('discussion-refresh').disabled);
 if(await page.locator('.collab-message').count()!==snapshot.comments.length||!await page.locator('#discussion-refresh-status').textContent())throw Error('failed refresh discarded evidence');
 await page.unroute('**/data/community-discussions.json');
 const hostile=structuredClone(snapshot);hostile.comments[0].text='<img src=x onerror="window.injected=1">';
 await page.route('**/data/community-discussions.json',r=>r.fulfill({json:hostile}));await page.locator('#discussion-refresh').click();
 await page.waitForFunction(()=>!document.getElementById('discussion-refresh').disabled);
 if(await page.locator('.collab-message-text img').count()||await page.evaluate(()=>!!window.injected))throw Error('external content executed');
 await page.goto(base+'agents'+suffix+'.html');await page.locator('#collaboration-link a').click();
 if(!new URL(page.url()).pathname.endsWith('community'+suffix+'.html'))throw Error('agent entry lost language');
 await page.goto(base+'participate'+suffix+'.html');
 if(!await page.locator('#collaboration-link').isVisible()||!await page.locator('#join-form').isVisible())throw Error('participation paths missing');
 if(errors.length)throw Error(errors.join('\n'));
 checks.push({lang,width,original_text:true,refresh_failure_preserves_copy:true,external_html_is_text:true,channel_link:true,no_overflow:true});await page.close();
}await fs.writeFile('browser-evidence/collaboration.json',JSON.stringify(checks,null,2));console.log('Discussion mirror and contribution flow: 12 combinations passed');}
finally{await browser.close();}
