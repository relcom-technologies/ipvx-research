import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');

export default async function* report(events) {
  const passed=[],failed=[];
  for await(const event of events) {
    if(event.type==='test:pass') {passed.push(event.data.name);yield `PASS ${event.data.name}\n`;}
    if(event.type==='test:fail') {failed.push(event.data.name);yield `FAIL ${event.data.name}: ${event.data.details?.error?.message}\n`;}
    if(event.type==='test:stderr') yield event.data.message;
  }
  yield `${passed.length} passed; ${failed.length} failed; direct in-memory EVM messages only.\n`;
  assert.equal(failed.length,0,'Contract checks failed');
  const files=['package.json','package-lock.json'];
  for(const dir of ['src','test','tools']) {
    for(const file of fs.readdirSync(path.join(root,dir)).sort()) {
      if(/\.(sol|mjs)$/.test(file)) files.push(`${dir}/${file}`);
    }
  }
  const evidence={schema_version:1,recorded_by:'codex-assistant',basis_revision:'f71032b406d82c75e17724d32b791e95b5289ea3',
    scope:'Solidity bytecode in standalone EthereumJS EVM memory; no transaction objects, provider, live chain or RPC',
    test_count:passed.length,passed:passed.sort(),failed,
    compiler_evidence_sha256:createHash('sha256').update(fs.readFileSync(path.join(root,'evidence/compilation.json'))).digest('hex'),
    source_files:files.sort().map(file=>({path:file,sha256:createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')})),
    network_blocker_preloaded:true,transactions_constructed_or_submitted:false,on_chain_deployment:false,
    ethereum_finality_verified:false,independent_security_audit:false,production_actions:false};
  const serialized=`${JSON.stringify(evidence,null,2)}\n`;const target=path.join(root,'evidence/checks.json');
  if(process.env.BCP_WRITE_EVIDENCE==='1') fs.writeFileSync(target,serialized);
  else assert.equal(fs.readFileSync(target,'utf8'),serialized,'Test evidence differs; review before explicitly regenerating it');
}
