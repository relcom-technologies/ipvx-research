// IPVX-BCP02-REG-001 step runner: the registry experiment as code.
// One sequence of steps and expectations runs on a backend. MemoryBackend (tests) executes
// against the in-memory EVM; the live Sepolia backend lives in reg001-live.mjs and is never
// imported by tests. Every step records what happened and whether it matched the expectation
// registered in experiments/bcp02-reg-001/protocol.json; the first mismatch stops the run.
// There is no automatic retry: a repeated step needs a new journal.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { Interface, keccak256, zeroPadValue, toBeHex, getBytes, hexlify } from 'ethers';
import { compile, artifacts, REPO } from '../tools/compile.mjs';

export const PROTOCOL = JSON.parse(fs.readFileSync(path.join(REPO, 'experiments/bcp02-reg-001/protocol.json'), 'utf8'));
export const STEP_IDS = PROTOCOL.steps.map(s => s.id);
export const CONTRACTS = ['NodeRegistry', 'TransitPolicy', 'ConnectionPolicy'];
const ROLE = { endpoint: 1, router: 2 };
const STATUS = { missing: 0, active: 1, unusable: 2 };
const EDGE = { cost: 1, size: 1500, mask: 7 };
const CONN = { mask: 7, hops: 2, size: 1500 };

let built;
export function build() {
  built ??= artifacts(compile());
  return built;
}
export const iface = name => new Interface(build()[name].abi);
export const key = n => zeroPadValue(toBeHex(n), 32);
export const salt = text => keccak256(new TextEncoder().encode(`ipvx-reg-001:${text}`));

// Runtime code with every immutable reference zeroed, so a deployed contract can be compared
// with the local build; the immutable values themselves are checked through their getters.
export function maskImmutables(runtimeHex, references) {
  const bytes = getBytes(runtimeHex);
  for (const ranges of Object.values(references ?? {})) for (const { start, length } of ranges) bytes.fill(0, start, start + length);
  return keccak256(bytes);
}
export function expectedRuntime(name) {
  const c = build()[name];
  return maskImmutables(`0x${c.evm.deployedBytecode.object}`, c.evm.deployedBytecode.immutableReferences);
}

export class Journal {
  constructor(file) { this.file = file; this.entries = []; if (file && fs.existsSync(file)) throw new Error(`Journal exists: ${file}; a rerun needs a new journal`); }
  add(entry) {
    const row = { at: new Date().toISOString(), ...entry };
    this.entries.push(row);
    if (this.file) fs.appendFileSync(this.file, `${JSON.stringify(row)}\n`, { mode: 0o600 });
    return row;
  }
}

class Mismatch extends Error {}
// Addresses come back checksummed from ABI decoding and lowercase from some backends.
const same = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
function expect(journal, step, ok, detail, records = []) {
  journal.add({ step, ok, detail, records });
  if (!ok) throw new Mismatch(`${step}: ${detail}`);
}

// Runs the registered sequence. Node keys are deterministic public test values (bytes32), not secrets.
// node() returns (owner, keyEpoch, signingKey, encryptionKey, status, roles).
export async function run(backend, journal, { latencyWrites = 20 } = {}) {
  const S = {};
  const send = (w, c, fn, args) => backend.send(w, c, fn, args);
  const ok = r => r.status === 'success';
  const reverted = (r, error) => r.status === 'reverted' && (!error || r.error === error);
  const node = async id => backend.read('NodeRegistry', 'node', [id]);
  const edge = async rule => backend.read('TransitPolicy', 'edge', [rule]);
  const conn = async rule => backend.read('ConnectionPolicy', 'connection', [rule]);
  try {
    for (const [step, name, args] of [['deploy-registry', 'NodeRegistry', () => []], ['deploy-transit', 'TransitPolicy', () => [S.NodeRegistry]],
      ['deploy-connection', 'ConnectionPolicy', () => [S.NodeRegistry, S.TransitPolicy]]]) {
      const r = await backend.deploy('W1', name, args());
      S[name] = r.address;
      const runtime = await backend.runtimeHash(name);
      expect(journal, step, ok(r) && runtime === expectedRuntime(name), `deployed at ${r.address}; runtime ${runtime === expectedRuntime(name) ? 'matches' : 'DIFFERS FROM'} local build`, [r]);
    }
    const immutables = [await backend.read('TransitPolicy', 'registry', []), await backend.read('ConnectionPolicy', 'registry', []), await backend.read('ConnectionPolicy', 'transit', [])];
    expect(journal, 'deploy-immutables', same(immutables[0][0], S.NodeRegistry) && same(immutables[1][0], S.NodeRegistry) && same(immutables[2][0], S.TransitPolicy), 'policy contracts reference the deployed registry and transit');

    for (const [step, w, label, k, role] of [['register-a', 'W1', 'A', 10, ROLE.endpoint], ['register-r', 'W1', 'R', 30, ROLE.router], ['register-b', 'W2', 'B', 20, ROLE.endpoint]]) {
      const r = await send(w, 'NodeRegistry', 'register', [key(k), key(k + 1), role]);
      S[label] = r.returned?.[0] ?? await backend.lastTokenId();
      const n = await node(S[label]);
      expect(journal, step, ok(r) && n[1] === 1n && n[2] === key(k) && n[4] === 1n && n[5] === BigInt(role), `NFT ${label}=${S[label]} epoch ${n[1]}`, [r]);
    }

    const agree = async (step, contract, rule, parties) => {
      const records = [];
      for (const [w, nft] of parties) {
        const version = (contract === 'TransitPolicy' ? await edge(rule) : await conn(rule))[2];
        records.push(await send(w, contract, 'consent', [rule, version, nft]));
      }
      const status = (contract === 'TransitPolicy' ? await edge(rule) : await conn(rule)).at(-1);
      expect(journal, step, records.every(ok) && status === BigInt(STATUS.active), `${contract} rule ${rule.slice(0, 10)} status ${status}`, records);
    };
    const propose = async (w, from, to, text) => {
      const r = await send(w, 'TransitPolicy', 'propose', [from, to, salt(text), EDGE.cost, EDGE.size, EDGE.mask]);
      return [r, r.returned?.[0] ?? await backend.read('TransitPolicy', 'ruleIdFor', [from, to, salt(text)]).then(x => x[0])];
    };
    let [pAR, AR] = await propose('W1', S.A, S.R, 'edge-ar');
    await agree('edge-ar', 'TransitPolicy', AR, [['W1', S.A], ['W1', S.R]]);
    let [pRB, RB] = await propose('W1', S.R, S.B, 'edge-rb');
    const beforeW2 = await (async () => { const v = (await edge(RB))[2]; const c = await send('W1', 'TransitPolicy', 'consent', [RB, v, S.R]); return [c, (await edge(RB)).at(-1)]; })();
    expect(journal, 'edge-rb-one-side', ok(beforeW2[0]) && beforeW2[1] === BigInt(STATUS.unusable), `after only R consented, status ${beforeW2[1]} (needs B's owner W2)`, [pRB, beforeW2[0]]);
    await agree('edge-rb', 'TransitPolicy', RB, [['W2', S.B]]);
    const proposeConn = async text => {
      const edges = [AR, RB].sort();
      const r = await send('W1', 'ConnectionPolicy', 'propose', [S.A, S.B, salt(text), CONN.mask, CONN.hops, CONN.size, edges]);
      return r.returned?.[0] ?? (await backend.read('ConnectionPolicy', 'ruleIdFor', [S.A, S.B, salt(text)]))[0];
    };
    let AB = await proposeConn('conn-ab');
    await agree('conn-ab', 'ConnectionPolicy', AB, [['W1', S.A], ['W2', S.B]]);
    const allows = async () => [await backend.read('ConnectionPolicy', 'allowsEdge', [AB, AR]), await backend.read('ConnectionPolicy', 'allowsEdge', [AB, RB])].map(x => x[0]);
    const snapshot = async step => {
      const snap = await backend.snapshot({ nfts: [S.A, S.R, S.B, 99n], edges: [AR, RB], connections: [AB] });
      journal.add({ step, ok: true, detail: `snapshot at ${snap.block?.hash ?? 'memory'}`, snapshot: snap });
      return snap;
    };
    const s1 = await snapshot('snapshot-s1');
    expect(journal, 'snapshot-s1-check', s1.nfts[3][4] === 0n && same(s1.nfts[3][0], '0x0000000000000000000000000000000000000000') && (await allows()).every(Boolean), 'absent NFT reads as all-zero; both edges allowed for A->B');

    for (const [step, contract, fn, args, error] of [
      ['w3-setkeys-a', 'NodeRegistry', 'setKeys', [S.A, key(90), key(91), ROLE.endpoint], 'NotNodeOwner'],
      ['w3-revoke-r', 'NodeRegistry', 'revoke', [S.R], 'NotNodeOwner'],
      ['w3-consent-b', 'TransitPolicy', 'consent', [RB, (await edge(RB))[2], S.B], 'NotPartyOwner'],
      ['w3-transfer-a', 'NodeRegistry', 'transferFrom', [await backend.address('W1'), await backend.address('W3'), S.A], null]]) {
      const r = await send('W3', contract, fn, args);
      expect(journal, step, reverted(r, error), `third party ${fn}: ${r.status}${r.error ? ` (${r.error})` : ''}`, [r]);
    }
    expect(journal, 'w3-unchanged', (await node(S.A))[2] === key(10) && (await node(S.R))[4] === 1n && same((await backend.read('NodeRegistry', 'ownerOf', [S.A]))[0], await backend.address('W1')), 'A keys, R state and A owner unchanged');

    const rot = await send('W1', 'NodeRegistry', 'setKeys', [S.R, key(40), key(41), ROLE.router]);
    expect(journal, 'rotate-r', ok(rot) && (await node(S.R))[1] === 2n, `R epoch ${(await node(S.R))[1]}`, [rot]);
    await snapshot('snapshot-s2');
    const after = [(await edge(AR)).at(-1), (await edge(RB)).at(-1), ...(await allows())];
    expect(journal, 'snapshot-s2-check', after[0] === BigInt(STATUS.unusable) && after[1] === BigInt(STATUS.unusable) && after[2] === false && after[3] === false, `edges ${after[0]}/${after[1]}, allowsEdge ${after[2]}/${after[3]}`);

    const oldVersions = [(await edge(AR))[2], (await edge(RB))[2]];
    [pAR] = await propose('W1', S.A, S.R, 'edge-ar'); await agree('repropose-ar', 'TransitPolicy', AR, [['W1', S.A], ['W1', S.R]]);
    [pRB] = await propose('W1', S.R, S.B, 'edge-rb'); await agree('repropose-rb', 'TransitPolicy', RB, [['W1', S.R], ['W2', S.B]]);
    AB = await proposeConn('conn-ab'); await agree('repropose-ab', 'ConnectionPolicy', AB, [['W1', S.A], ['W2', S.B]]);
    await snapshot('snapshot-s3');
    const newVersions = [(await edge(AR))[2], (await edge(RB))[2]];
    expect(journal, 'snapshot-s3-check', newVersions[0] > oldVersions[0] && newVersions[1] > oldVersions[1] && (await allows()).every(Boolean), `versions ${oldVersions} -> ${newVersions}; path allowed again only under new versions`);

    const epochB = (await node(S.B))[1];
    const out = await send('W2', 'NodeRegistry', 'transferFrom', [await backend.address('W2'), await backend.address('W1'), S.B]);
    const mid = await node(S.B);
    const back = await send('W1', 'NodeRegistry', 'transferFrom', [await backend.address('W1'), await backend.address('W2'), S.B]);
    const end = await node(S.B);
    expect(journal, 'transfer-b', ok(out) && ok(back) && mid[1] === epochB + 1n && end[1] === epochB + 2n && end[2] === key(0) && same(end[0], await backend.address('W2')),
      `epoch ${epochB} -> ${mid[1]} -> ${end[1]}; keys cleared; owner W2 again`, [out, back]);
    await snapshot('snapshot-s4');
    expect(journal, 'snapshot-s4-check', (await conn(AB)).at(-1) === BigInt(STATUS.unusable) && (await edge(RB)).at(-1) === BigInt(STATUS.unusable), 'B unbound: its edge and the connection are unusable until rebound and re-consented');

    // Writes go out one after another; each one's path to finality is watched concurrently, so the
    // series takes about one finality delay, not one per write.
    const watched = [];
    for (let i = 0; i < latencyWrites; i++) {
      const r = await send('W1', 'NodeRegistry', 'setKeys', [S.A, key(1000 + 2 * i), key(1001 + 2 * i), ROLE.endpoint]);
      watched.push(backend.timing(r));
    }
    const series = await Promise.all(watched);
    expect(journal, 'latency-series', series.length === latencyWrites && series.every(t => t.included), `${series.length} writes timed`, series);
    return { ok: true, state: S, journal: journal.entries };
  } catch (error) {
    if (!(error instanceof Mismatch)) journal.add({ step: 'error', ok: false, detail: `${error.name}: ${error.message}`.slice(0, 500) });
    return { ok: false, state: S, journal: journal.entries };
  }
}

// In-memory backend for offline tests: direct EVM messages, no keys, provider or network.
export class MemoryBackend {
  constructor(evm, wallets) { this.evm = evm; this.wallets = wallets; this.contracts = {}; this.block = 0; this.lastId = 0n; }
  async address(w) { return this.wallets[w]; }
  async deploy(w, name, args) {
    const c = await this.evm.construct(name, args);
    this.contracts[name] = { ...c, iface: iface(name) };
    return { status: 'success', address: c.address, block: ++this.block, gas: null, wallet: w };
  }
  async runtimeHash(name) {
    const { createAddressFromString } = await import('@ethereumjs/util');
    const code = await this.evm.evm.stateManager.getCode(createAddressFromString(this.contracts[name].address));
    return maskImmutables(hexlify(code), build()[name].evm.deployedBytecode.immutableReferences);
  }
  async send(w, name, fn, args) {
    const c = this.contracts[name];
    const result = await this.evm.attempt(c, fn, args, this.wallets[w]);
    const block = ++this.block;
    if (result.exceptionError) {
      let error = null;
      try { error = c.iface.parseError(hexlify(result.returnValue))?.name ?? null; } catch {}
      return { status: 'reverted', error, block, gas: result.executionGasUsed, wallet: w, call: `${name}.${fn}` };
    }
    const returned = c.iface.decodeFunctionResult(fn, hexlify(result.returnValue));
    if (name === 'NodeRegistry' && fn === 'register') this.lastId = returned[0];
    return { status: 'success', returned: [...returned], block, gas: result.executionGasUsed, wallet: w, call: `${name}.${fn}` };
  }
  async lastTokenId() { return this.lastId; }
  async read(name, fn, args) { return [...await this.evm.call(this.contracts[name], fn, args)]; }
  async snapshot({ nfts, edges, connections }) {
    return { block: null, mode: 'memory', nfts: await Promise.all(nfts.map(n => this.read('NodeRegistry', 'node', [n]))),
      edges: await Promise.all(edges.map(e => this.read('TransitPolicy', 'edge', [e]))), connections: await Promise.all(connections.map(c => this.read('ConnectionPolicy', 'connection', [c]))) };
  }
  async timing(record) { return { included: record.status === 'success', block: record.block, synthetic: true }; }
}

export function assertSepolia(chainId) {
  assert.equal(BigInt(chainId), BigInt(PROTOCOL.chain.chain_id), `Refusing chain ${chainId}: REG-001 runs only on Sepolia (${PROTOCOL.chain.chain_id})`);
}
