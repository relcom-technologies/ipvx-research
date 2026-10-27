import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});
const checks=[];
try {
 for(const width of [1440,1280,768,390]){
  for(const reduced of [false,true]){
   const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:reduced?'reduce':'no-preference'}),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'packet-replay.html');
   await page.getByText('Запись готова: все 90 кадров, 16 из 16 задач.',{exact:true}).waitFor();
   await page.evaluate(()=>document.fonts.ready);
   if(width===1440&&!reduced)await page.screenshot({path:'browser-evidence/replay-first-screen.png',fullPage:false});
   if(await page.locator('#replay-events button').count()!==90)throw Error('Omitted baseline frames');
   // Select a task, then verify that the physical hop and final addressee differ.
   await page.locator('#replay-events button').filter({hasText:'19. A → R · TASK №1'}).click();
   if(!(await page.locator('#replay-fields').innerText()).includes('B · 365eed0785936c4e'))throw Error('Final destination lost behind relay');
   await page.locator('.replay-inspect details').first().locator('summary').first().click();
   if((await page.locator('#replay-payload').innerText()).replaceAll('\n','').length!==2048)throw Error('Task bytes missing');
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Replay overflow '+width);
   if(width===1440||width===390)await page.screenshot({path:`browser-evidence/replay-${width}-${reduced?'reduced':'motion'}.png`,fullPage:true});
   await page.locator('#replay-speed').selectOption('150');
   await page.getByRole('button',{name:'Воспроизвести',exact:true}).click();
   if(reduced && await page.locator('#replay-packet').isVisible())throw Error('Reduced motion packet still moves');
   if(!reduced)await page.waitForFunction(()=>{
    const p=document.getElementById('replay-packet');
    return !p.hidden && p.getAnimations().some(a=>a.currentTime>30);
   });
   await page.waitForFunction(()=>Number(document.getElementById('replay-position').value)>=21);
   await page.getByRole('button',{name:'Пауза',exact:true}).click();
   const stopped=await page.locator('#replay-position').inputValue();
   await page.locator('#replay-scenario').selectOption('relay-down');
   if(await page.locator('#replay-events button').count()!==10||await page.locator('#replay-completed').innerText()!=='0 / 16')throw Error('Negative result misrepresented');
   await page.locator('#replay-position').focus();await page.keyboard.press('End');
   if(await page.locator('#replay-position-label').innerText()!=='10 из 10'||await page.locator('#replay-next').isEnabled())throw Error('Keyboard/end state broken');
   if(await page.locator('#replay-receipt').getAttribute('href')!=='data/strict-native-2026-10-27/relay-down/receipt.json')throw Error('Wrong receipt');
   await page.goto(base+'downloads.html');await page.evaluate(()=>document.fonts.ready);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Download overflow '+width);
   if(width===390&&!reduced)await page.screenshot({path:'browser-evidence/downloads-390.png',fullPage:true});
   // A failed or structurally invalid record must not enable playback; direct evidence survives.
   let bad=true;
   await page.route('**/data/packet-replay.json',route=>bad?route.fulfill({status:200,contentType:'application/json',body:'{"schema_version":1,"scenarios":[] }'}):route.continue());
   await page.goto(base+'packet-replay.html');await page.getByRole('button',{name:'Загрузить запись ещё раз'}).waitFor();
   if(await page.locator('#replay-play').isEnabled()||await page.getByRole('link',{name:'Код, инструкции и захваты трафика ↓'}).count()!==1)throw Error('Corrupt-data fallback lost evidence');
   bad=false;await page.getByRole('button',{name:'Загрузить запись ещё раз'}).click();
   await page.getByText('Запись готова: все 90 кадров, 16 из 16 задач.',{exact:true}).waitFor();
   if(errors.length)throw Error(errors.join('\n'));
   checks.push({width,reduced,frames:[90,10],pause_at:Number(stopped)+1,retry:true,no_page_overflow:true});await page.close();
  }
 }
 const request=await browser.newContext();
 const manifestResponse=await request.request.get(base+'data/downloads/manifest.json');
 if(manifestResponse.status()!==200)throw Error('Manifest requires sign-in');
 const manifest=await manifestResponse.json();
 for(const item of manifest.bundles){
  const response=await request.request.get(base+'data/downloads/'+item.name),bytes=await response.body();
  if(response.status()!==200||bytes.length!==item.bytes||bytes.subarray(0,2).toString()!=='PK'||createHash('sha256').update(bytes).digest('hex')!==item.sha256)throw Error('Public download differs from manifest: '+item.name);
 }
 await request.close();
 await fs.writeFile('browser-evidence/replay-checks.json',JSON.stringify({checks,public_bundles:manifest.bundles.map(x=>({name:x.name,sha256:x.sha256,bytes:x.bytes})),snapshot_through:manifest.snapshot_through},null,2));
 console.log(`${checks.length} replay/browser states; two public ZIP hashes verified`);
}finally{await browser.close();}
