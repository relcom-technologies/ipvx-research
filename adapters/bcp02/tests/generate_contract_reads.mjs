// Offline messages against the accepted Solidity implementation; no RPC/tx.
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import { MemoryEVM, A, word } from '../../../contracts/bcp02/test/evm.mjs';
const require = createRequire(new URL('../../../contracts/bcp02/package.json', import.meta.url));
const { keccak256 } = require('ethers');
const { createAddressFromString, bytesToHex } = require('@ethereumjs/util');
const m = await (await MemoryEVM.create()).setup();
const { ar, rb, rule } = await m.connected();
const contracts = [m.registry,m.transit,m.connection];
const codes = {};
for (const c of contracts) codes[c.address] = bytesToHex(await m.evm.stateManager.getCode(createAddressFromString(c.address)));
async function capture() {
  const reads = {};
  const cases = [
    ...[1,2,3,9].map(n=>[m.registry,'node',[n]]),
    ...[1,2,3].map(n=>[m.registry,'ownerOf',[n]]),
    ...[ar,rb,word(0)].map(r=>[m.transit,'edge',[r]]),
    ...[rule,word(0)].map(r=>[m.connection,'connection',[r]]),
    ...[rule,word(0)].flatMap(c=>[ar,rb,word(0)].map(e=>[m.connection,'allowsEdge',[c,e]])),
    [m.transit,'registry',[]],[m.connection,'registry',[]],[m.connection,'transit',[]]
  ];
  for (const [c,fn,args] of cases) {
    const result = await m.attempt(c,fn,args);
    if (result.exceptionError) throw new Error('fixture view reverted');
    reads[c.address+':'+c.iface.encodeFunctionData(fn,args)] = bytesToHex(result.returnValue);
  }
  return reads;
}
const active = await capture();
await m.call(m.registry,'setKeys',[1,word(101),word(102),1],A);
const rotated = await capture();
const fixture = {
  schema:1, provenance:'Accepted contracts at 9ac92e80152e588abcee6b97b18796d038cd0154; in-memory EVM messages only',
  not_evidence_of:'Sepolia deployment, finalized state, actual operator addresses or network interoperability',
  addresses:contracts.map(c=>c.address), runtime_hashes:contracts.map(c=>keccak256(codes[c.address])),
  codes, rules:{ar,rb,connection:rule}, states:{active,rotated}
};
writeFileSync(process.argv[2],JSON.stringify(fixture,null,2)+'\n');
