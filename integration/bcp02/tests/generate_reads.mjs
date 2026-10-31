// Public test keys and direct local EVM messages only; never an operational key.
import {createRequire} from 'node:module';
import {createHash,createPrivateKey,createPublicKey} from 'node:crypto';
import {writeFileSync} from 'node:fs';
import {MemoryEVM,A,B,C,word} from '../../../contracts/bcp02/test/evm.mjs';
const require=createRequire(new URL('../../../contracts/bcp02/package.json',import.meta.url));
const {keccak256}=require('ethers');
const {createAddressFromString,bytesToHex}=require('@ethereumjs/util');
function key(n,kind) {
  const seed=createHash('sha256').update(`PUBLIC IPvX offline cycle ${kind} ${n}`).digest();
  const prefix=kind==='signing'?'302e020100300506032b657004220420':'302e020100300506032b656e04220420';
  const privateKey=createPrivateKey({key:Buffer.concat([Buffer.from(prefix,'hex'),seed]),format:'der',type:'pkcs8'});
  return {public_test_seed_hex:seed.toString('hex'),public_key_hex:createPublicKey(privateKey).export({format:'der',type:'spki'}).subarray(-32).toString('hex')};
}
const keys=Object.fromEntries([1,2,3,101].map(n=>[n,{signing:key(n,'signing'),encryption:key(n,'encryption')}]));
const m=await MemoryEVM.create();
m.registry=await m.construct('NodeRegistry');m.transit=await m.construct('TransitPolicy',[m.registry.address]);
m.connection=await m.construct('ConnectionPolicy',[m.registry.address,m.transit.address]);
for (const [n,owner] of [[1,A],[2,B],[3,C]]) await m.call(m.registry,'register',[
  '0x'+keys[n].signing.public_key_hex,'0x'+keys[n].encryption.public_key_hex,n===3?2:1],owner);
const edgeSpecs=[['ar',1,3,A],['ra',3,1,C],['rb',3,2,C],['br',2,3,B]];
const edges={};
for (const [i,[name,source,destination,owner]] of edgeSpecs.entries()) {
  edges[name]=await m.edge(source,destination,word(i+1),owner);await m.accept(m.transit,edges[name]);
}
const connections={};
for (const [name,source,destination,owner,salt,list] of [
  ['ab',1,2,A,9,[edges.ar,edges.rb]],['ba',2,1,B,10,[edges.br,edges.ra]]]) {
  connections[name]=(await m.call(m.connection,'propose',[source,destination,word(salt),7,2,1500,list.sort()],owner))[0];
  await m.accept(m.connection,connections[name]);
}
const contracts=[m.registry,m.transit,m.connection],codes={};
for (const c of contracts) codes[c.address]=bytesToHex(await m.evm.stateManager.getCode(createAddressFromString(c.address)));
async function capture() {
  const reads={};
  const cases=[...[1,2,3].flatMap(n=>[[m.registry,'node',[n]],[m.registry,'ownerOf',[n]]]),
    ...Object.values(edges).map(e=>[m.transit,'edge',[e]]),
    ...Object.values(connections).map(c=>[m.connection,'connection',[c]]),
    ...Object.values(connections).flatMap(c=>Object.values(edges).map(e=>[m.connection,'allowsEdge',[c,e]])),
    [m.transit,'registry',[]],[m.connection,'registry',[]],[m.connection,'transit',[]]];
  for (const [c,fn,args] of cases) {
    const result=await m.attempt(c,fn,args);if (result.exceptionError) throw new Error('fixture view reverted');
    reads[c.address+':'+c.iface.encodeFunctionData(fn,args)]=bytesToHex(result.returnValue);
  }
  return reads;
}
const states={active:await capture()};
await m.evm.stateManager.checkpoint();
await m.call(m.registry,'setKeys',[1,'0x'+keys[101].signing.public_key_hex,'0x'+keys[101].encryption.public_key_hex,1],A);
states.rotated=await capture();await m.evm.stateManager.revert();
await m.evm.stateManager.checkpoint();
await m.call(m.connection,'withdraw',[connections.ba,1,2],B);
states.reverse_denied=await capture();await m.evm.stateManager.revert();
await m.call(m.transit,'withdraw',[edges.ar,1,1],A);states.edge_denied=await capture();
writeFileSync(process.argv[2],JSON.stringify({schema:1,base:'8fb04e89dfbbe7a1b6f05f1fdb465bf4193c1179',
  warning:'PUBLIC TEST SEEDS ONLY. Never use these keys, addresses or hashes as operational pins. No RPC or transactions.',
  keys,addresses:contracts.map(c=>c.address),runtime_hashes:contracts.map(c=>keccak256(codes[c.address])),
  codes,edges,connections,states},null,2)+'\n');
