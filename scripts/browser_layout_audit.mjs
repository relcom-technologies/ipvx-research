import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base=process.env.PORTAL_BASE_URL||'http://127.0.0.1:8110/';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const root=new URL('..',import.meta.url);const files=(await fs.readdir(root)).filter(f=>f.endsWith('.html')&&!f.startsWith('.'));
let failed=[],total=0;await fs.mkdir('browser-evidence',{recursive:true});
try{
 for(const width of [1440,768,390]){
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});const page=await context.newPage();
  for(const name of files){
   await page.goto(base+name,{waitUntil:'domcontentloaded'});await page.evaluate(()=>document.fonts.ready);
   const issues=await page.evaluate(async()=>{
    const out=[];if(document.documentElement.scrollWidth>innerWidth+1)out.push('page overflow '+document.documentElement.scrollWidth);
    for(const img of document.images){if(img.offsetWidth && (!img.complete||img.naturalWidth===0))out.push('broken image '+img.getAttribute('src'))}
    for(const el of document.querySelectorAll('.trace-mobile>div,.native-device-mobile li,.net-machine,.net-guest,.net-controls button')){
     if(el.clientWidth && el.scrollWidth>el.clientWidth+2)out.push('clipped content '+el.className+' '+el.scrollWidth+'/'+el.clientWidth);
    }
    for(const text of document.querySelectorAll('svg text')){
     if(!text.getClientRects().length)continue;const box=text.getBoundingClientRect(), svg=text.ownerSVGElement.getBoundingClientRect();
     if(box.left<svg.left-1||box.right>svg.right+1||box.top<svg.top-1||box.bottom>svg.bottom+1)out.push('SVG label outside graphic '+text.textContent.trim().slice(0,50));
     const rect=text.parentElement?.querySelector(':scope > rect');if(rect){const r=rect.getBoundingClientRect();if(box.right>r.right+2||box.left<r.left-2||box.bottom>r.bottom+2||box.top<r.top-2)out.push('SVG label outside node '+text.textContent.trim().slice(0,50));}
    }
    return out;
   });
   if(issues.length)failed.push({name,width,issues});total++;
   if(['architecture.html','architecture.de.html','index.de.html','participate.es.html'].includes(name)&&[1440,390].includes(width))await page.screenshot({path:`browser-evidence/layout-${name.replace('.html','')}-${width}.png`,fullPage:true});
  }
  await context.close();
 }
 const svgPage=await browser.newPage({viewport:{width:1440,height:900}});
 for(const locale of ['','en/','de/','es/'])for(const kind of ['llm-comparison.svg','llm-comparison-mobile.svg']){
  const name='assets/'+locale+kind;await svgPage.goto(base+name);await svgPage.evaluate(()=>document.fonts.ready);
  const labels=await svgPage.evaluate(()=>{const svg=document.querySelector('svg'),box=svg.getBoundingClientRect();return [...svg.querySelectorAll('text')].filter(t=>{const r=t.getBoundingClientRect();return r.left<box.left-1||r.right>box.right+1||r.top<box.top-1||r.bottom>box.bottom+1}).map(t=>t.textContent.trim())});
  if(labels.length)failed.push({name,width:'SVG',issues:labels.map(x=>'SVG label outside image '+x)});
 }
 await svgPage.close();
 const page=await browser.newPage({viewport:{width:390,height:950},reducedMotion:'reduce'});
 for(const suffix of ['','.en','.de','.es']){
  await page.goto(base+'architecture'+suffix+'.html#research-network');
  const nodes=await page.locator('.net-machine').count(), stages=await page.locator('.net-stage').count();
  if(nodes!==3||stages!==4)throw Error('incomplete diagram '+suffix);
  await page.locator('[data-net-select="1"]').click();
  if(await page.locator('[data-net-stage="1"]').isHidden())throw Error('stage button failed '+suffix);
  if(await page.locator('[data-net-topology]').getAttribute('data-phase')!=='1')throw Error('stage highlight failed '+suffix);
  await page.locator('[data-net-play]').click();await page.waitForTimeout(1950);
  if(await page.locator('[data-net-topology]').getAttribute('data-phase')!=='1')throw Error('playback did not advance '+suffix);
  await page.locator('[data-net-play]').click();
  await page.goto(base+'agents'+suffix+'.html');
  if(await page.locator('link[rel="alternate"][type="application/json"][href="data/agent-discovery.json"]').count()!==1)throw Error('agent discovery link missing '+suffix);
  if(await page.locator('#agent-invitation a[href="data/agent-discovery.json"]').count()!==1)throw Error('agent directory unavailable '+suffix);
  const descriptor=await page.evaluate(async()=>await (await fetch('data/agent-discovery.json')).json());
  if(descriptor.protocols.a2a_server_available||descriptor.participation.automatic_resource_access)throw Error('nonexistent capability advertised');
  await page.goto(base+'participate'+suffix+'.html#compute-contributions');
  if(await page.locator('#compute-contributions a[href="#join-form"]').count()!==1)throw Error('compute proposal link missing '+suffix);
  await page.locator('#compute-contributions a[href="#join-form"]').click();
  if(await page.locator('#kind option').count()<5)throw Error('compute proposal option missing '+suffix);
 }
 await page.close();
 const context=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:900}});const nojs=await context.newPage();await nojs.goto(base+'architecture.html');if(await nojs.locator('.net-stage:visible').count()!==4)throw Error('no-JS explanation missing');await context.close();
 await fs.writeFile('browser-evidence/layout-audit.json',JSON.stringify({total,failed},null,2));console.log(JSON.stringify({total,failed},null,2));if(failed.length)process.exitCode=1;
}finally{await browser.close()}
