// REG-001 results, recomputed offline from the run journals in runs/.
//   node experiments/bcp02-reg-001/summarize.mjs           writes results.json
//   node experiments/bcp02-reg-001/summarize.mjs --check   fails if results.json is stale
// No network, no keys: everything here is derived from files already in this directory.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const read = name => fs.readFileSync(path.join(HERE, name), 'utf8');
const journal = n => read(`runs/run-${n}.jsonl`).trim().split('\n').map(line => JSON.parse(line));
const permit = n => JSON.parse(read(`runs/permit-${n}.json`));

// Why runs 1-5 stopped is not in their journals; it was diagnosed after each stop and fixed in a PR
// with a test that fails on the old code. No step was retried inside a run.
const STOPS = {
  1: { cause: 'runtime hash read at "latest" on a load-balanced RPC; a lagging backend had no code yet', fix: 'relcom-technologies/ipvx-research#56' },
  2: { cause: 'journal could not serialize a BigInt', fix: 'relcom-technologies/ipvx-research#57' },
  3: { cause: 'an RPC 500 during the latency series escaped as an unhandled rejection; process exited without a journal line', fix: 'relcom-technologies/ipvx-research#58' },
  4: { cause: 'gas estimated at "latest" on a backend one block behind the previous write', fix: 'relcom-technologies/ipvx-research#59' },
  5: { cause: 'a missing block on a lagging backend is reported by ethers as CALL_EXCEPTION and was taken for a revert', fix: 'relcom-technologies/ipvx-research#60' },
};

const runs = [1, 2, 3, 4, 5, 6].map(n => {
  const rows = journal(n);
  const done = rows.filter(r => r.ok && r.step !== 'permit').map(r => r.step);
  const error = rows.find(r => r.step === 'error');
  return {
    run: n,
    source_revision: permit(n).source_revision,
    window_start: permit(n).window_start,
    steps_passed: done.length,
    steps_total: permit(n).steps.length,
    last_passed: done.at(-1) ?? null,
    error: error?.detail.split(' (')[0] ?? null,
    contracts: rows.filter(r => r.step.startsWith('deploy-') && r.records?.[0]?.address)
      .map(r => ({ [r.records[0].call.split('.')[0]]: r.records[0].address })).reduce((a, b) => ({ ...a, ...b }), {}),
    ...(STOPS[n] ?? { cause: null, fix: null }),
  };
});

const main = journal(6);
const step = id => main.find(r => r.step === id);
const snapshots = Object.fromEntries(['s1', 's2', 's3', 's4'].map(s => {
  const snap = step(`snapshot-${s}`).snapshot;
  return [s.toUpperCase(), { block: snap.block.number, block_hash: snap.block.hash, mode: snap.mode, nfts: snap.nfts, edges: snap.edges, connections: snap.connections }];
}));
const failed = main.filter(r => !r.ok);
assert.equal(failed.length, 0, 'run 6 has a failed step');

// R2: W3's attempts. The runner simulates each call against the live chain first (eth_call after
// the last write) and does not submit a call that reverts there, so these are refusals by the
// deployed contracts on live state, not mined failed transactions.
const thirdParty = ['w3-setkeys-a', 'w3-revoke-r', 'w3-consent-b', 'w3-transfer-a'].map(id => {
  const r = step(id).records[0];
  return { step: id, call: r.call, refused: r.status === 'reverted', error: r.error, simulated: r.simulated === true };
});

// R4: one write per row, seconds from submission on the operator clock.
const series = step('latency-series').records;
const nearestRank = (values, q) => { const s = [...values].sort((a, b) => a - b); return s[Math.max(0, Math.ceil(q * s.length) - 1)]; };
const stats = values => ({ n: values.length, min: nearestRank(values, 0), p50: nearestRank(values, 0.5), p90: nearestRank(values, 0.9), max: nearestRank(values, 1) });
const secs = key => series.map(t => Math.round((t[key] - t.submitted_ms) / 100) / 10);

// R5: gas from receipts of every transaction W1-W3 sent in run 6's block range.
const txs = JSON.parse(read('runs/run-6-transactions.json')).transactions;
const gas = {};
for (const t of txs) {
  const key = `${t.contract}.${t.fn}`;
  (gas[key] ??= []).push(Number(t.gas));
}

const results = {
  schema_version: 1,
  protocol_id: 'IPVX-BCP02-REG-001',
  protocol_version: '0.1',
  result_status: 'completed_read_mode_Q',
  read_mode: 'Q',
  chain_id: 11155111,
  recorded_by: 'claude-code-assistant',
  derived_by: 'experiments/bcp02-reg-001/summarize.mjs from runs/',
  runs,
  complete_run: {
    run: 6,
    steps_passed: runs[5].steps_passed,
    contracts: runs[5].contracts,
    snapshots,
    transactions_sent: txs.length,
    gas_total: txs.reduce((a, t) => a + Number(t.gas), 0),
  },
  replication: 'run 3 passed the same 29 steps up to snapshot-s4-check on separate contracts; it stopped only in the latency series',
  claims: {
    R1: {
      verdict: 'not_claimed_mode_Q',
      observed: 'A, R, B in S1 match the written owner, epoch, keys, role; NFT 99 reads as all-zero with status 0; each snapshot accepted only when 3 providers returned identical data at one finalized blockHash',
      why_not_claimed: 'the pass condition requires read mode V (own validated node); public RPCs are not admission under BCP 0.2',
    },
    R2: {
      verdict: 'supported_with_reservation',
      third_party: thirdParty,
      transfer: step('transfer-b').detail,
      unchanged_after_attempts: step('w3-unchanged').ok,
      reservation: 'pre-registered wording is "revert on chain"; the attempts were refused by the deployed contracts on live state via eth_call and were not mined as failed transactions',
    },
    R3: {
      verdict: 'supported',
      one_sided_edge: step('edge-rb-one-side').detail,
      after_rotation_S2: step('snapshot-s2-check').detail,
      reconsent_S3: step('snapshot-s3-check').detail,
      after_transfer_S4: step('snapshot-s4-check').detail,
      note: 'in S2 the connection record keeps status 1; it stops allowing the path through allowsEdge=false on both edges',
    },
    R4: {
      verdict: 'immediately_available_not_supported_for_finalized_reading',
      seconds_from_submit: {
        inclusion_block_time: stats(secs('inclusion_block_time_ms')),
        safe_seen: stats(secs('safe_seen_ms')),
        finalized_seen: stats(secs('finalized_seen_ms')),
        reader_accepted: stats(secs('reader_accepted_ms')),
      },
      preregistered_expectation: 'about 13 minutes',
      note: 'writes are visible in a block within seconds; under BCP 0.2 a reader acts on them only after finality. The 20 writes were sent within about 5 minutes and finalized together, so the spread reflects send time, not 20 independent finality samples. Times on the operator clock, polled every 12 s.',
    },
    R5: {
      verdict: 'measured',
      gas_units_by_call: Object.fromEntries(Object.entries(gas).map(([k, v]) => [k, { n: v.length, values: [...new Set(v)].sort((a, b) => a - b) }])),
      gas_price_wei_in_journal: [...new Set(main.flatMap(r => r.records ?? []).map(x => x.gas_price).filter(Boolean))],
      not_measured: ['NodeRegistry.revoke by the owner (the sequence only has a refused third-party revoke)', 'withdrawal of consent (not in the registered sequence)'],
      note: 'first propose of a rule pays for its storage; re-proposing the same rule as a new version is cheaper (TransitPolicy 491401 vs 69983, ConnectionPolicy 1097195 vs 158215)',
    },
  },
  limitations: [
    'read mode Q only; R1 and NET-001 state need read mode V on an own Geth + Lighthouse pair',
    'W1 and W2 belong to one lab owner: the mechanism of bilateral consent is tested, not independent parties',
    'gas in Sepolia units; no mainnet money figure is given',
    'the transport for transactions and reads was JSON-RPC over the ordinary Internet; it is a carrier here, not part of any claim',
  ],
};

const text = `${JSON.stringify(results, null, 1)}\n`;
const target = path.join(HERE, 'results.json');
if (process.argv.includes('--check')) {
  assert.equal(fs.readFileSync(target, 'utf8'), text, 'results.json is stale: rerun summarize.mjs');
  console.log('results.json matches the run journals');
} else {
  fs.writeFileSync(target, text);
  console.log(`wrote ${path.relative(process.cwd(), target)}`);
}
