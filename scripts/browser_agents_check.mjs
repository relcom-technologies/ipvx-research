import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8091/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
await fs.mkdir('browser-evidence',{recursive:true});
const checks=[];
try {
 for(const width of [1440,768,390])for(const reduced of [false,true]){
  const page=await browser.newPage({viewport:{width,height:1000},reducedMotion:reduced?'reduce':'no-preference'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'packet-replay.html#native-agents');
  await page.locator('#agent-message:enabled').waitFor();
  if(await page.locator('#agent-message option').count()!==48)throw Error('Omitted measured deliveries');
  if(!(await page.locator('.agent-comparison').innerText()).includes('36.25 с'))throw Error('Matched summary missing');
  await page.locator('#agent-step').click();
  if(await page.locator('#agent-hop').innerText()!=='1 из 4 переходов')throw Error('Step lost');
  await page.locator('#agent-reset').click();
  await page.locator('#agent-play').click();
  if(!reduced) {
   await page.waitForFunction(()=>document.getElementById('agent-dot').getAnimations().some(a=>a.currentTime>30));
   await page.locator('#agent-play').click();
   const stopped=await page.locator('#agent-hop').innerText();
   await page.waitForTimeout(800);
   if(await page.locator('#agent-hop').innerText()!==stopped||await page.locator('#agent-dot').isVisible())throw Error('Pause did not cancel');
   await page.locator('#agent-play').click();
  }else if(await page.locator('#agent-dot').isVisible())throw Error('Reduced motion moves dot');
  await page.waitForFunction(()=>document.getElementById('agent-hop').textContent==='4 из 4 переходов');
  if(!(await page.locator('#agent-hop-text').innerText()).includes('проверил квитанцию'))throw Error('Receipt lost');
  await page.locator('#agent-message').selectOption('47');
  if(await page.locator('#agent-hop').innerText()!=='0 из 4 переходов')throw Error('Selection retained old path');
  await page.locator('#agent-step').click();
  if(!(await page.locator('#agent-hop-text').innerText()).startsWith('B → R1'))throw Error('Reverse review route lost');
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow');
  if(!reduced){await page.locator('#native-agents').screenshot({path:`browser-evidence/agents-${width}.png`});}
  await page.route('**/data/strict-agents-round.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{"schema_version":1,"deliveries":[]}'}));
  await page.reload();await page.getByText('Не удалось загрузить запись.',{exact:false}).waitFor();
  if(await page.locator('#agent-play').isEnabled()||await page.locator('.agent-comparison').count()!==1)throw Error('Corrupt data fallback broken');
  if(errors.length)throw Error(errors.join('\n'));
  checks.push({width,reduced,deliveries:48,step:true,receipt:true,reverse_path:true,pause:true,invalid_data:true,no_overflow:true});
  await page.close();
 }
 await fs.writeFile('browser-evidence/agents-checks.json',JSON.stringify({checks},null,2));
 console.log(`${checks.length} actual-agent replay states passed`);
}finally{await browser.close();}
