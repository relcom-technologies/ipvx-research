import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { MemoryEVM, A, B, X } from '../test/evm.mjs';
import { run, MemoryBackend, Journal, PROTOCOL, STEP_IDS, assertSepolia } from './runner.mjs';
import { checkPermit } from './live.mjs';

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
