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

// Run 2 on Sepolia stopped at register-a: the file journal could not serialize the BigInt token id.
// The in-memory journal above never serializes, so the full sequence is also written to a file here.
test('the full sequence is written to a journal file that parses back line for line', async () => {
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'reg001-')), 'journal.jsonl');
  const result = await run(await backend(), new Journal(file), { latencyWrites: 2 });
  assert.equal(result.ok, true);
  const rows = fs.readFileSync(file, 'utf8').trim().split('\n').map(l => JSON.parse(l));
  assert.deepEqual(rows.map(r => r.step), PROTOCOL.steps.map(s => s.id));
  assert.equal(rows.find(r => r.step === 'register-a').records[0].returned[0], '1', 'token id recorded as a decimal string');
  assert.equal(fs.statSync(file).mode & 0o077, 0, 'journal file is private to the operator');
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

// Run 3 on Sepolia passed every functional step, then died in the latency series: a provider answered
// a safe/finalized poll with a transient 500, the poll was not protected, and the failing observation
// escaped as an unhandled rejection while later writes were still being sent.
const busy = () => Object.assign(new Error('server response 500 Internal Server Error'), { code: 'SERVER_ERROR' });
const chain = (fail = 0) => ({ calls: 0, async getBlock(tag) {
  if (typeof tag === 'string' && this.calls++ < fail) throw busy();
  return { number: 100, hash: `0x${'33'.repeat(32)}`, timestamp: 1_800_000_000 };
} });

test('a transient 500 while polling safe/finalized blocks is waited out, not fatal', async () => {
  const providers = [chain(2), chain(1), chain(0)];
  const b = new LiveBackend(providers, {}, null, { readWaitMs: 1, readTries: 5 });
  const t = await b.timing({ block: 90, status: 'success', tx: '0xabc', submitted_ms: 0 });
  assert.equal(t.included, true);
  assert.ok(t.safe_seen_ms && t.finalized_seen_ms && t.reader_accepted_ms);
});

test('a latency observation that fails mid-series is journaled as the run error, not an unhandled crash', async () => {
  const b = await backend();
  const send = b.send.bind(b);
  b.send = async (...a) => { await new Promise(r => setTimeout(r, 5)); return send(...a); };
  let first = true;
  b.timing = async r => { if (first) { first = false; throw busy(); } return { included: true, ...r }; };
  const journal = new Journal();
  const result = await run(b, journal, { latencyWrites: 4 });
  assert.equal(result.ok, false);
  assert.equal(journal.entries.at(-1).step, 'error');
  assert.match(journal.entries.at(-1).detail, /500/);
  assert.ok(journal.entries.some(e => e.step === 'snapshot-s4-check' && e.ok), 'every functional step before the series is kept');
});

// Run 4 on Sepolia stopped at edge-ar: A's consent passed simulation at the block of the propose, but
// the signer then estimated gas at 'latest' on a backend a block behind, where the rule did not exist
// yet, and the estimate reverted with MissingRule.
test('gas for a write is estimated at the block of the last write, waiting for a backend that is behind', async () => {
  const estimates = fake([notYet(), '0x5208']);
  const sent = [];
  const W1 = { getAddress: async () => `0x${'aa'.repeat(20)}`, call: async () => '0x',
    sendTransaction: async tx => { sent.push(tx); return { wait: async () => ({ status: 1, hash: `0x${'44'.repeat(32)}`, blockNumber: 124,
      blockHash: `0x${'55'.repeat(32)}`, gasUsed: 30_000n, gasPrice: 1n }) }; } };
  const b = new LiveBackend([estimates, fake([]), fake([])], { W1 }, null, { readWaitMs: 1, readTries: 5 });
  b.contracts.TransitPolicy = { address: `0x${'22'.repeat(20)}`, iface: iface('TransitPolicy') };
  b.lastBlock = 123;
  const r = await b.send('W1', 'TransitPolicy', 'consent', [`0x${'66'.repeat(32)}`, 1n, 1n]);
  assert.equal(r.status, 'success');
  assert.deepEqual(estimates.seen.map(([m, p]) => [m, p[1]]), [['eth_estimateGas', '0x7b'], ['eth_estimateGas', '0x7b']]);
  assert.equal(sent[0].gasLimit, 0x5208n * 12n / 10n + 10_000n, 'the signer is given the pinned estimate instead of estimating at latest');
  assert.equal(b.lastBlock, 124);
});
