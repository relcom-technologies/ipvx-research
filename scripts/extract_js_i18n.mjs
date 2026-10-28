// Build-time parser only. Generated spans are checked against source hashes by Python.
import {parse} from '../i18n/node_modules/acorn/dist/acorn.mjs';
import fs from 'node:fs';
import crypto from 'node:crypto';
const sources=[];
for(const name of ['portal','relcom','community','admin','replay','agent-replay']){
 const text=fs.readFileSync(`assets/${name}.js`,'utf8');
 const spans=[];
 function visit(node){
  if(!node||typeof node!=='object')return;
  if(node.type==='Literal'&&typeof node.value==='string'&&/[А-Яа-яЁё]/.test(node.value)){
   spans.push({start:node.start,end:node.end,source:node.value,kind:'literal'});
  }else if(node.type==='TemplateElement'&&/[А-Яа-яЁё]/.test(node.value.cooked)){
   spans.push({start:node.start,end:node.end,source:node.value.cooked,kind:'quasi'});
  }
  for(const [k,v]of Object.entries(node))if(!['start','end','loc'].includes(k)){
   if(Array.isArray(v))v.forEach(visit);else if(v&&typeof v==='object')visit(v);
  }
 }
 visit(parse(text,{ecmaVersion:'latest',sourceType:'script'}));
 for(const s of spans)sources.push({...s,file:`assets/${name}.js`,context:`assets/${name}.js:${s.start}`,sha256:crypto.createHash('sha256').update(text).digest('hex')});
}
fs.writeFileSync('i18n/js-sources.json',JSON.stringify(sources,null,2)+'\n');
