import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import net from 'node:net';
import { AbiCoder, id, keccak256 } from 'ethers';
import { MemoryEVM, BUILT, A, B, C, X, Z, word } from './evm.mjs';
import { compile, compilationEvidence, ROOT } from '../tools/compile.mjs';

const fresh = async options => (await MemoryEVM.create()).setup(options);
const status = row => row[row.length-1];
const nodeStatus = row => row[4];
const plain = row => Array.from(row);

test('network and RPC transports are blocked before tests and dependencies load', () => {
  assert.throws(()=>net.connect({host:'127.0.0.1',port:1}),/Network access forbidden/);
  assert.throws(()=>fetch('https://example.invalid'),/Network access forbidden/);
});

test('compiled five-function read ABI and deterministic evidence match the frozen specification', () => {
  assert.deepEqual(compilationEvidence(compile()),JSON.parse(fs.readFileSync(`${ROOT}/evidence/compilation.json`)));
});

test('missing views are all-zero while ERC721 ownerOf for a missing NFT reverts', async () => {
  const m=await fresh();
  assert.deepEqual(plain(await m.call(m.registry,'node',[999])),[Z,0n,word(0),word(0),0n,0n]);
  assert.deepEqual(plain(await m.call(m.transit,'edge',[word(999)])),Array(9).fill(0n));
  assert.deepEqual(plain(await m.call(m.connection,'connection',[word(999)])),Array(9).fill(0n));
  assert.equal((await m.call(m.connection,'allowsEdge',[word(999),word(998)]))[0],false);
  await m.rejects(m.registry,'ownerOf',[999],A,'ERC721NonexistentToken');
});

test('open registration creates unique owned NFTs with epoch one and no transit', async () => {
  const m=await fresh();
  const [token]=await m.call(m.registry,'register',[word(20),word(21),3],X);
  assert.equal(token,4n);
  const n=await m.call(m.registry,'node',[token]);
  assert.equal(n.owner.toLowerCase(),X);assert.equal(n.keyEpoch,1n);assert.equal(n.status,1n);assert.equal(n.roles,3n);
  assert.equal((await m.call(m.registry,'balanceOf',[X]))[0],1n);
  assert.equal((await m.call(m.registry,'supportsInterface',['0x80ac58cd']))[0],true);
  assert.equal((await m.call(m.registry,'supportsInterface',['0x01ffc9a7']))[0],true);
  assert.equal((await m.call(m.registry,'supportsInterface',['0xffffffff']))[0],false);
  assert.equal(status(await m.call(m.transit,'edge',[word(1)])),0n);
});

test('invalid zero/equal keys and unknown roles are rejected without consuming ids', async () => {
  const m=await fresh();
  for (const args of [[word(0),word(2),1],[word(1),word(0),1],[word(1),word(1),1],
    [word(1),word(2),0],[word(1),word(2),4],[word(1),word(2),255]]) {
    await m.rejects(m.registry,'register',args,X,'InvalidKeysOrRoles');
  }
  assert.equal((await m.call(m.registry,'register',[word(40),word(41),1],X))[0],4n);
});

test('operational key rotation and revocation are owner-only, checked monotonic epochs', async () => {
  const m=await fresh();
  await m.rejects(m.registry,'setKeys',[1,word(5),word(6),1],X,'NotNodeOwner');
  await m.rejects(m.registry,'revoke',[1],X,'NotNodeOwner');
  await m.call(m.registry,'setKeys',[1,word(5),word(6),3],A);
  assert.equal((await m.call(m.registry,'node',[1])).keyEpoch,2n);
  await m.call(m.registry,'revoke',[1],A);
  const n=await m.call(m.registry,'node',[1]);
  assert.equal(n.keyEpoch,3n);assert.equal(n.status,2n);assert.equal(n.signingKey,word(0));assert.equal(n.roles,0n);
  await m.rejects(m.registry,'revoke',[1],A,'InactiveNode');
  await m.call(m.registry,'setKeys',[1,word(7),word(8),1],A);
  assert.equal((await m.call(m.registry,'node',[1])).keyEpoch,4n);
});

test('all ERC721 transfer paths invalidate keys before the new owner explicitly binds them', async () => {
  for (const fn of ['transferFrom','safeTransferFrom(address,address,uint256)','safeTransferFrom(address,address,uint256,bytes)']) {
    const m=await fresh();
    const args=[A,X,1];if (fn.endsWith(',bytes)')) args.push('0x1234');
    await m.call(m.registry,fn,args,A);
    let n=await m.call(m.registry,'node',[1]);
    assert.equal(n.owner.toLowerCase(),X);assert.equal(n.status,2n);assert.equal(n.keyEpoch,2n);
    assert.equal(n.signingKey,word(0));assert.equal(n.encryptionKey,word(0));
    await m.rejects(m.registry,'setKeys',[1,word(5),word(6),1],A,'NotNodeOwner');
    await m.call(m.registry,'setKeys',[1,word(5),word(6),1],X);
    n=await m.call(m.registry,'node',[1]);assert.equal(n.keyEpoch,3n);assert.equal(n.status,1n);
  }
});

test('approved ERC721 operators may transfer but cannot change keys or consent to policies', async () => {
  const m=await fresh();const rule=await m.edge();
  await m.call(m.registry,'approve',[X,1],A);
  await m.rejects(m.registry,'setKeys',[1,word(5),word(6),1],X,'NotNodeOwner');
  await m.rejects(m.transit,'consent',[rule,1,1],X,'NotPartyOwner');
  await m.rejects(m.transit,'withdraw',[rule,1,1],X,'NotPartyOwner');
  await m.call(m.registry,'transferFrom',[A,B,1],X);
  assert.equal((await m.call(m.registry,'node',[1])).status,2n);
  assert.equal((await m.call(m.registry,'getApproved',[1]))[0],Z);
});

test('safe transfer callback sees revoked keys and can only bind new keys as the new owner', async () => {
  const m=await fresh();const receiver=await m.construct('ObservingReceiver',[m.registry.address]);
  await m.call(receiver,'setReactivate',[true],A);
  await m.call(m.registry,'safeTransferFrom(address,address,uint256)',[A,receiver.address,1],A);
  assert.equal((await m.call(receiver,'observedStatus'))[0],2n);
  assert.equal((await m.call(receiver,'observedEpoch'))[0],2n);
  assert.equal((await m.call(receiver,'observedKeysZero'))[0],true);
  const n=await m.call(m.registry,'node',[1]);assert.equal(n.keyEpoch,3n);assert.equal(n.status,1n);
});

test('safe mint callback sees fully initialized state and rejected transfer rolls back the epoch', async () => {
  const m=await fresh();const receiver=await m.construct('ObservingReceiver',[m.registry.address]);
  await m.call(receiver,'registerNode',[word(20),word(21),1],A);
  assert.equal((await m.call(receiver,'observedStatus'))[0],1n);
  assert.equal((await m.call(receiver,'observedEpoch'))[0],1n);
  const rejecting=await m.construct('RejectingReceiver');
  await m.rejects(m.registry,'safeTransferFrom(address,address,uint256)',[A,rejecting.address,1],A,'ERC721InvalidReceiver');
  const n=await m.call(m.registry,'node',[1]);assert.equal(n.owner.toLowerCase(),A);assert.equal(n.keyEpoch,1n);assert.equal(n.status,1n);
});

test('uint64 key epoch cannot wrap, including during transfer', async () => {
  const m=await fresh({registry:'EpochHarness'});await m.call(m.registry,'forceEpoch',[1,2n**64n-1n],A);
  await m.rejects(m.registry,'setKeys',[1,word(8),word(9),1],A,'Panic');
  await m.rejects(m.registry,'transferFrom',[A,B,1],A,'Panic');
  assert.equal((await m.call(m.registry,'node',[1])).owner.toLowerCase(),A);
});

test('rule ids bind chain, contract, directed endpoints and salt', async () => {
  const m=await fresh();const salt=word(43);
  const [rule]=await m.call(m.transit,'ruleIdFor',[1,3,salt]);
  const expected=keccak256(AbiCoder.defaultAbiCoder().encode(['bytes32','uint256','address','uint256','uint256','bytes32'],
    [id('IPvX-BCP/0.2/transit-rule'),11155111,m.transit.address,1,3,salt]));
  assert.equal(rule,expected);
  assert.notEqual(rule,(await m.call(m.transit,'ruleIdFor',[3,1,salt]))[0]);
  assert.notEqual(rule,(await m.call(m.connection,'ruleIdFor',[1,3,salt]))[0]);
});

test('third parties cannot propose, consent or withdraw even with a predicted rule id', async () => {
  const m=await fresh();await m.rejects(m.transit,'propose',[1,3,word(1),1,1500,7],X,'NotPartyOwner');
  const rule=await m.edge();
  await m.rejects(m.transit,'consent',[rule,1,1],X,'NotPartyOwner');
  await m.rejects(m.transit,'consent',[rule,1,2],B,'InvalidEndpoints');
  await m.rejects(m.transit,'withdraw',[rule,1,3],X,'NotPartyOwner');
  assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
});

test('one consent never activates a rule, even when both NFTs have the same owner', async () => {
  const m=await fresh();const rule=await m.edge();
  await m.call(m.transit,'consent',[rule,1,1],A);
  assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
  await m.call(m.transit,'consent',[rule,1,3],C);
  assert.equal(status(await m.call(m.transit,'edge',[rule])),1n);
  await m.call(m.registry,'register',[word(40),word(41),1],A);
  const shared=await m.edge(1,4,word(4),A);
  await m.call(m.transit,'consent',[shared,1,1],A);
  assert.equal(status(await m.call(m.transit,'edge',[shared])),2n);
  await m.call(m.transit,'consent',[shared,1,4],A);
  assert.equal(status(await m.call(m.transit,'edge',[shared])),1n);
});

test('terms changes reset both consents and expectedVersion prevents stale approvals', async () => {
  const m=await fresh();const rule=await m.edge();await m.accept(m.transit,rule);
  await m.edge(1,3,word(1),C,{cost:8,size:1000,mask:1});
  let e=await m.call(m.transit,'edge',[rule]);assert.equal(e.version,2n);assert.equal(e.cost,8n);assert.equal(e.status,2n);
  await m.rejects(m.transit,'consent',[rule,1,1],A,'StaleVersion');
  await m.call(m.transit,'consent',[rule,2,1],A);assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
  await m.call(m.transit,'consent',[rule,2,3],C);assert.equal(status(await m.call(m.transit,'edge',[rule])),1n);
});

test('either endpoint withdrawal versions the rule and cannot preserve the other old consent', async () => {
  for (const [nft,owner] of [[1,A],[3,C]]) {
    const m=await fresh();const rule=await m.edge();await m.accept(m.transit,rule);
    await m.call(m.transit,'withdraw',[rule,1,nft],owner);
    assert.equal((await m.call(m.transit,'edge',[rule])).version,2n);
    await m.call(m.transit,'consent',[rule,2,nft],owner);
    assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
  }
});

test('rotation after the first consent prevents second-side approval until a new proposal', async () => {
  const m=await fresh();const rule=await m.edge();
  await m.call(m.transit,'consent',[rule,1,1],A);
  await m.call(m.registry,'setKeys',[1,word(10),word(11),1],A);
  await m.rejects(m.transit,'consent',[rule,1,3],C,'StaleEpoch');
  assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
  await m.edge();await m.accept(m.transit,rule);
  assert.equal((await m.call(m.transit,'edge',[rule])).fromEpoch,2n);
});

test('transfer, revoke and reactivation never revive old active transit consents', async () => {
  for (const action of ['rotate','revoke','transfer','self-transfer']) {
    const m=await fresh();const rule=await m.edge();await m.accept(m.transit,rule);
    if(action==='rotate') await m.call(m.registry,'setKeys',[1,word(8),word(9),1],A);
    if(action==='revoke') {await m.call(m.registry,'revoke',[1],A);await m.call(m.registry,'setKeys',[1,word(8),word(9),1],A);}
    if(action==='transfer') {await m.call(m.registry,'transferFrom',[A,X,1],A);await m.call(m.registry,'setKeys',[1,word(8),word(9),1],X);}
    if(action==='self-transfer') {await m.call(m.registry,'transferFrom',[A,A,1],A);await m.call(m.registry,'setKeys',[1,word(8),word(9),1],A);}
    assert.equal(status(await m.call(m.transit,'edge',[rule])),2n,action);
  }
});

test('inactive owners can withdraw stale policies but the previous NFT owner cannot', async () => {
  const m=await fresh();const rule=await m.edge();await m.accept(m.transit,rule);
  await m.call(m.registry,'transferFrom',[A,X,1],A);
  await m.rejects(m.transit,'withdraw',[rule,1,1],A,'NotPartyOwner');
  await m.call(m.transit,'withdraw',[rule,1,1],X);
  assert.equal((await m.call(m.transit,'edge',[rule])).version,2n);
});

test('direction, traffic masks, MTU and missing/inactive endpoints fail closed', async () => {
  const m=await fresh();
  for(const [size,mask] of [[15,1],[1501,1],[1500,0],[1500,8],[1500,0xffffffff]]) {
    await m.rejects(m.transit,'propose',[1,3,word(1),1,size,mask],A,'InvalidParameters');
  }
  await m.rejects(m.transit,'propose',[1,1,word(1),1,1500,1],A,'InvalidEndpoints');
  await m.rejects(m.transit,'propose',[1,999,word(1),1,1500,1],A,'InactiveParty');
  const rule=await m.edge();await m.accept(m.transit,rule);
  const reverse=(await m.call(m.transit,'ruleIdFor',[3,1,word(1)]))[0];
  assert.equal(status(await m.call(m.transit,'edge',[reverse])),0n);
  await m.call(m.registry,'revoke',[3],C);
  assert.equal(status(await m.call(m.transit,'edge',[rule])),2n);
});

test('connections need two current owner consents and never authorize the reverse direction implicitly', async () => {
  const m=await fresh();const edge=await m.edge();await m.accept(m.transit,edge);
  const [rule]=await m.call(m.connection,'propose',[1,2,word(9),1,7,1500,[edge]],A);
  await m.call(m.connection,'consent',[rule,1,1],A);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,edge]))[0],false);
  await m.call(m.connection,'consent',[rule,1,2],B);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,edge]))[0],true);
  const reverse=(await m.call(m.connection,'ruleIdFor',[2,1,word(9)]))[0];
  assert.equal(status(await m.call(m.connection,'connection',[reverse])),0n);
});

test('connection writes reject unauthorized owners, zero/duplicate/unsorted/missing edge sets and bad limits', async () => {
  const m=await fresh();const {ar,rb,rule}=await m.connected();
  await m.rejects(m.connection,'propose',[1,2,word(10),1,7,1500,[ar]],X,'NotPartyOwner');
  for (const set of [[],[word(0)],[ar,ar],[ar,rb].sort().reverse(),[word(999)]]) {
    await m.rejects(m.connection,'propose',[1,2,word(10),1,7,1500,set],A);
  }
  for(const [mask,hops,size] of [[0,7,1500],[8,7,1500],[1,0,1500],[1,8,1500],[1,7,15],[1,7,1501]]) {
    await m.rejects(m.connection,'propose',[1,2,word(10),mask,hops,size,[ar]],A,'InvalidParameters');
  }
  await m.rejects(m.connection,'propose',[1,2,word(10),1,7,1500,Array(65).fill(ar)],A,'InvalidParameters');
  await m.rejects(m.connection,'propose',[3,2,word(10),1,7,1500,[ar]],C,'InvalidEndpoints');
  // A failing replacement reaches the array update but must restore the whole
  // previously active agreement, including removed allowlist entries.
  await m.rejects(m.connection,'propose',[1,2,word(9),1,7,1500,[ar,rb].sort().reverse()],A,'InvalidParameters');
  assert.equal((await m.call(m.connection,'connection',[rule])).version,1n);
  assert.equal(status(await m.call(m.connection,'connection',[rule])),1n);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],true);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,rb]))[0],true);
});

test('allowed edge versions are pinned; a changed or withdrawn transit rule cannot silently widen a connection', async () => {
  const m=await fresh();const {ar,rule}=await m.connected();
  await m.edge(1,3,word(1),A,{cost:2});await m.accept(m.transit,ar);
  assert.equal(status(await m.call(m.connection,'connection',[rule])),1n);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],false);
  await m.call(m.connection,'propose',[1,2,word(9),1,7,1500,[ar]],A);
  await m.accept(m.connection,rule);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],true);
});

test('the 64-edge boundary is usable and its accepted set remains exact', async () => {
  const m=await fresh();const rules=[];
  for(let i=0;i<64;i++) {const r=await m.edge(1,3,word(1000+i));await m.accept(m.transit,r);rules.push(r);}
  const [rule]=await m.call(m.connection,'propose',[1,2,word(20),1,7,1500,rules.sort()],A);
  await m.accept(m.connection,rule);
  for(const edge of rules) assert.equal((await m.call(m.connection,'allowsEdge',[rule,edge]))[0],true);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,word(999)]))[0],false);
});

test('removed edge ids are cleared when proposing a new connection version', async () => {
  const m=await fresh();const {ar,rb,rule}=await m.connected();
  await m.call(m.connection,'propose',[1,2,word(9),1,7,1500,[ar]],B);await m.accept(m.connection,rule);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],true);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,rb]))[0],false);
  await m.rejects(m.connection,'consent',[rule,1,2],B,'StaleVersion');
});

test('connection endpoint epochs, router epochs and transit status are reevaluated on every view', async () => {
  for(const [nft,owner] of [[1,A],[2,B],[3,C]]) {
    const m=await fresh();const {ar,rb,rule}=await m.connected();
    await m.call(m.registry,'setKeys',[nft,word(80),word(81),nft===3?2:1],owner);
    if(nft!==3) assert.equal(status(await m.call(m.connection,'connection',[rule])),2n);
    assert.equal((await m.call(m.connection,'allowsEdge',[rule,nft===2?rb:ar]))[0],false);
  }
});

test('connection withdrawal cannot be undone by stale approvals and keeps all old edge grants ineffective', async () => {
  const m=await fresh();const {ar,rule}=await m.connected();
  await m.call(m.connection,'withdraw',[rule,1,2],B);
  await m.rejects(m.connection,'consent',[rule,1,1],A,'StaleVersion');
  await m.call(m.connection,'consent',[rule,2,1],A);
  assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],false);
});

test('uint64 policy versions cannot wrap on reproposal or withdrawal', async () => {
  const m=await fresh({transit:'TransitHarness',connection:'ConnectionHarness'});const {ar,rule}=await m.connected();
  const max=2n**64n-1n;
  await m.call(m.connection,'forceVersion',[rule,max],A);
  await m.rejects(m.connection,'withdraw',[rule,max,1],A,'Panic');
  await m.rejects(m.connection,'propose',[1,2,word(9),1,7,1500,[ar]],A,'Panic');
  await m.call(m.transit,'forceVersion',[ar,max],A);
  await m.rejects(m.transit,'withdraw',[ar,max,1],A,'Panic');
  await m.rejects(m.transit,'propose',[1,3,word(1),1,1500,7],A,'Panic');
});

test('constructor binding rejects absent code and a transit instance bound to another registry', async () => {
  const m=await fresh();
  await assert.rejects(m.construct('TransitPolicy',[Z]));
  await assert.rejects(m.construct('ConnectionPolicy',[m.registry.address,Z]));
  const other=await m.construct('NodeRegistry');
  await assert.rejects(m.construct('ConnectionPolicy',[other.address,m.transit.address]));
});

test('seeded lifecycle invariant: no active rule or edge grant survives an unacknowledged epoch change', async () => {
  const m=await fresh();let seed=0x49505658;let previousEpoch=1n;let previousVersion=1n;
  const {ar,rule}=await m.connected();
  for(let step=0;step<48;step++) {
    seed=(Math.imul(seed,1664525)+1013904223)>>>0;
    const source=seed%2===0?1:3;const owner=source===1?A:C;
    await m.call(m.registry,'setKeys',[source,word(1000+step*2),word(1001+step*2),source===1?1:2],owner);
    const epoch=(await m.call(m.registry,'node',[source])).keyEpoch;
    assert.ok(epoch>1n);
    assert.equal(status(await m.call(m.transit,'edge',[ar])),2n);
    assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],false);
    await m.edge();const edge=await m.call(m.transit,'edge',[ar]);assert.ok(edge.version>previousVersion);previousVersion=edge.version;
    await m.call(m.transit,'consent',[ar,edge.version,1],A);
    assert.equal(status(await m.call(m.transit,'edge',[ar])),2n);
    await m.call(m.transit,'consent',[ar,edge.version,3],C);
    assert.equal(status(await m.call(m.transit,'edge',[ar])),1n);
    assert.equal((await m.call(m.connection,'allowsEdge',[rule,ar]))[0],false);
    if(source===1) {assert.ok(epoch>previousEpoch);previousEpoch=epoch;}
  }
});
