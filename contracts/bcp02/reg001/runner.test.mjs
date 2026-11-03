import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { MemoryEVM, A, B, X } from '../test/evm.mjs';
import { run, MemoryBackend, Journal, PROTOCOL, STEP_IDS, assertSepolia, build, iface, expectedRuntime } from './runner.mjs';
import { checkPermit, LiveBackend } from './live.mjs';

const WALLETS = { W1: A, W2: B, W3: X };
const backend = async () => new MemoryBackend(await MemoryEVM.create(), WALLETS);

test('the registered REG-001 sequence passes end to end on the in-memory EVM, step for step', async () => {
  const journal = new Journal();
  const result = await run(await backend(), journal, { latencyWrites: 3 });
  const failed = journal.entries.filter(e => !e.ok);
  assert.equal(result.ok, true, JSON.stringify(failed));
  // The journal follows protocol.json exactly, so the experiment cannot drift from its registration.
  assert.deepEqual(journal.entries.map(e => e.step), PROTOCOL.steps.map(s => s.id));
  assert.ok(journal.entries.find(e => e.step === 'latency-series').records.every(t => t.synthetic), 'memory timings are labelled synthetic');
});

test('a registry that lets a third party rotate keys stops the run at that step', async () => {
  const b = await backend();
  const send = b.send.bind(b);
  b.send = async (w, name, fn, args) => w === 'W3' && fn === 'setKeys' ? { status: 'success', returned: [], block: 0, wallet: w } : send(w, name, fn, args);
  const journal = new Journal();
  const result = await run(b, journal, { latencyWrites: 1 });
  assert.equal(result.ok, false);
  assert.deepEqual(journal.entries.at(-1).step, 'w3-setkeys-a');
  assert.equal(journal.entries.some(e => e.step === 'rotate-r'), false, 'no step runs after the first mismatch');
});

test('runtime code that differs from the local build stops the run before any node is registered', async () => {
  const b = await backend();
  b.runtimeHash = async () => '0x' + '00'.repeat(32);
  const journal = new Journal();
  assert.equal((await run(b, journal)).ok, false);
  assert.deepEqual(journal.entries.map(e => e.step), ['deploy-registry']);
});

test('only Sepolia is accepted and an existing journal is never reused', () => {
  assertSepolia(11155111);
  assert.throws(() => assertSepolia(1), /only on Sepolia/);
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'reg001-')), 'journal.jsonl');
  new Journal(file).add({ step: 'x', ok: true });
  assert.throws(() => new Journal(file), /rerun needs a new journal/);
});

test('a live run needs a current permit for exactly this protocol, chain, step list and read mode', () => {
  const permit = { protocol_id: PROTOCOL.protocol_id, protocol_version: PROTOCOL.version, chain_id: 11155111, steps: STEP_IDS, read_mode: 'Q',
    approved_by: 'project owner', window_start: '2026-11-03T08:00:00Z', window_end: '2026-11-03T20:00:00Z' };
  const now = new Date('2026-11-03T10:00:00Z');
  checkPermit(permit, now);
  for (const [change, error] of [[{ chain_id: 1 }, /another chain/], [{ steps: STEP_IDS.slice(1) }, /exactly the registered steps/],
    [{ read_mode: 'V' }, /mode Q only/], [{ approved_by: '' }, /who approved/], [{ protocol_version: '9' }, /another protocol version/]]) {
    assert.throws(() => checkPermit({ ...permit, ...change }, now), error);
  }
  assert.throws(() => checkPermit(permit, new Date('2026-11-04T10:00:00Z')), /Outside the permitted window/);
});

// Live reads against fake load-balanced providers: no network. Run 1 on Sepolia stopped because one
// provider, a block behind, answered 'latest' with empty code right after a deployment.
const notYet = () => Object.assign(new Error('header not found'), { code: 'UNKNOWN_ERROR' });
const fake = answers => ({ seen: [], async send(method, params) {
  this.seen.push([method, params]);
  const a = answers[Math.min(this.seen.length - 1, answers.length - 1)];
  if (a instanceof Error) throw a;
  return a;
} });
const live = providers => new LiveBackend(providers, {}, null, { readWaitMs: 1, readTries: 5 });

test('deployed code is read at the deployment block on every provider, waiting for one that is behind', async () => {
  const code = `0x${build().TransitPolicy.evm.deployedBytecode.object}`, blockHash = `0x${'11'.repeat(32)}`;
  const providers = [fake([code]), fake([notYet(), notYet(), code]), fake([code])];
  const b = live(providers);
  b.contracts.TransitPolicy = { address: `0x${'22'.repeat(20)}`, blockHash };
  assert.equal(await b.runtimeHash('TransitPolicy'), expectedRuntime('TransitPolicy'));
  assert.equal(providers[1].seen.length, 3);
  for (const p of providers) assert.deepEqual(p.seen[0], ['eth_getCode', [`0x${'22'.repeat(20)}`, { blockHash, requireCanonical: true }]]);
});

test('a provider that never reaches the block, or returns other code, stops the read instead of passing it', async () => {
  const code = `0x${build().TransitPolicy.evm.deployedBytecode.object}`;
  const b = live([fake([code]), fake([notYet()]), fake([code])]);
  b.contracts.TransitPolicy = { address: `0x${'22'.repeat(20)}`, blockHash: `0x${'11'.repeat(32)}` };
  await assert.rejects(b.runtimeHash('TransitPolicy'), /header not found/);
  const c = live([fake([code]), fake(['0x']), fake([code])]);
  c.contracts.TransitPolicy = b.contracts.TransitPolicy;
  await assert.rejects(c.runtimeHash('TransitPolicy'), /Providers disagree on deployed code/);
});

test('only a real revert counts as an expected rejection; an unavailable block is not mistaken for one', async () => {
  const reverts = { async call() { throw Object.assign(new Error('execution reverted'), { code: 'CALL_EXCEPTION' }); } };
  const behind = { tags: [], async call(tx) { this.tags.push(tx.blockTag); throw notYet(); } };
  const b = new LiveBackend([fake([]), fake([]), fake([])], { W3: reverts, W1: behind }, null, { readWaitMs: 1, readTries: 3 });
  b.contracts.NodeRegistry = { address: `0x${'22'.repeat(20)}`, iface: iface('NodeRegistry') };
  b.lastBlock = 123;
  const r = await b.send('W3', 'NodeRegistry', 'revoke', [1n]);
  assert.equal(r.status, 'reverted');
  assert.equal(r.simulated, true);
  await assert.rejects(b.send('W1', 'NodeRegistry', 'revoke', [1n]), /header not found/);
  assert.deepEqual(behind.tags, [123, 123, 123], 'simulation reads the state after the last write, never an older latest');
});
