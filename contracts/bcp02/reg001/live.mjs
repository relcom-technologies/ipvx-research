// IPVX-BCP02-REG-001 on Sepolia. Sends real testnet transactions: run only under a one-run owner
// permit (experiments/bcp02-reg-001/README.md §7). Never imported by tests.
//
//   node reg001/live.mjs --permit permit.json --wallets wallets.json --rpc URL --rpc URL --rpc URL --journal run.jsonl
//
// wallets.json (mode 0600, outside Git): {"W1": "<private key>", "W2": "...", "W3": "..."}.
// Read mode Q: snapshots are accepted only when every RPC provider returns identical data for one
// finalized block hash. This is the labelled interim deviation, not BCP-T validated-node admission.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JsonRpcProvider, Wallet, ContractFactory } from 'ethers';
import { run, Journal, PROTOCOL, STEP_IDS, build, iface, maskImmutables, assertSepolia } from './runner.mjs';

const POLL_MS = 12_000;
const sleep = ms => new Promise(r => setTimeout(r, ms));

export function checkPermit(permit, now = new Date()) {
  assert.equal(permit.protocol_id, PROTOCOL.protocol_id, 'Permit is for another protocol');
  assert.equal(permit.protocol_version, PROTOCOL.version, 'Permit is for another protocol version');
  assert.equal(BigInt(permit.chain_id), BigInt(PROTOCOL.chain.chain_id), 'Permit is for another chain');
  assert.deepEqual(permit.steps, STEP_IDS, 'Permit must list exactly the registered steps');
  assert.equal(permit.read_mode, 'Q', 'This tool reads in mode Q only; mode V uses adapters/bcp02');
  assert.ok(typeof permit.approved_by === 'string' && permit.approved_by, 'Permit names who approved it');
  const start = new Date(permit.window_start), end = new Date(permit.window_end);
  assert.ok(start <= now && now < end, `Outside the permitted window ${permit.window_start} – ${permit.window_end}`);
}

export class LiveBackend {
  constructor(providers, wallets, journal, { readWaitMs = 2_000, readTries = 30 } = {}) {
    assert.ok(providers.length >= 3, 'Read mode Q needs at least three independent RPC providers');
    this.providers = providers; this.wallets = wallets; this.journal = journal; this.contracts = {}; this.lastId = 0n;
    this.lastBlock = null; this.readWaitMs = readWaitMs; this.readTries = readTries;
  }
  // Public RPCs are load-balanced: a backend one block behind answers 'latest' with older state and
  // an unknown block with an error. Reads after a write therefore name the block of that write, and a
  // block not yet available is waited for, bounded, instead of being taken as a result. Only a real
  // revert (CALL_EXCEPTION) is a result.
  async available(read) {
    for (let i = 1; ; i++) {
      try {
        const value = await read();
        if (value === null || value === undefined) throw new Error('block not yet available');
        return value;
      } catch (error) {
        if (error.code === 'CALL_EXCEPTION' || i >= this.readTries) throw error;
        await sleep(this.readWaitMs);
      }
    }
  }
  get afterLastWrite() { return this.lastBlock ?? 'latest'; }
  async address(w) { return this.wallets[w].address; }
  async deploy(w, name, args) {
    const c = build()[name];
    const factory = new ContractFactory(c.abi, `0x${c.evm.bytecode.object}`, this.wallets[w]);
    const submitted = Date.now();
    const contract = await factory.deploy(...args);
    const receipt = await contract.deploymentTransaction().wait();
    this.contracts[name] = { address: await contract.getAddress(), iface: iface(name), blockHash: receipt.blockHash };
    return this.record(w, `${name}.deploy`, receipt, submitted, { address: this.contracts[name].address });
  }
  async runtimeHash(name) {
    // Code is read at the deployment block itself on every provider, never at 'latest'.
    const { address, blockHash } = this.contracts[name];
    const codes = await Promise.all(this.providers.map(p => this.available(() => p.send('eth_getCode', [address, { blockHash, requireCanonical: true }]))));
    assert.ok(codes.every(c => c === codes[0]), 'Providers disagree on deployed code');
    return maskImmutables(codes[0], build()[name].evm.deployedBytecode.immutableReferences);
  }
  record(w, call, receipt, submitted, extra = {}) {
    if (this.lastBlock === null || receipt.blockNumber > this.lastBlock) this.lastBlock = receipt.blockNumber;
    return { status: receipt.status === 1 ? 'success' : 'reverted', wallet: w, call, tx: receipt.hash, block: receipt.blockNumber,
      block_hash: receipt.blockHash, gas: receipt.gasUsed.toString(), gas_price: receipt.gasPrice?.toString(), submitted_ms: submitted, ...extra };
  }
  async send(w, name, fn, args) {
    const c = this.contracts[name];
    const data = c.iface.encodeFunctionData(fn, args);
    // A call simulated first tells an expected revert apart without spending gas on it.
    const call = () => this.available(() => this.wallets[w].call({ to: c.address, data, blockTag: this.afterLastWrite }));
    try { await call(); } catch (error) {
      if (error.code !== 'CALL_EXCEPTION') throw error;
      const reason = error.data ? c.iface.parseError(error.data)?.name ?? null : null;
      return { status: 'reverted', error: reason, wallet: w, call: `${name}.${fn}`, simulated: true };
    }
    let returned;
    try { returned = [...c.iface.decodeFunctionResult(fn, await call())]; } catch { returned = undefined; }
    const submitted = Date.now();
    const tx = await this.wallets[w].sendTransaction({ to: c.address, data });
    const receipt = await tx.wait();
    if (name === 'NodeRegistry' && fn === 'register' && returned) this.lastId = returned[0];
    return { ...this.record(w, `${name}.${fn}`, receipt, submitted), returned };
  }
  async lastTokenId() { return this.lastId; }
  async read(name, fn, args) {
    const c = this.contracts[name];
    const data = c.iface.encodeFunctionData(fn, args);
    return [...c.iface.decodeFunctionResult(fn, await this.available(() => this.providers[0].call({ to: c.address, data, blockTag: this.afterLastWrite })))];
  }
  async finalizedAtLeast(number) {
    for (;;) {
      const blocks = await Promise.all(this.providers.map(p => p.getBlock('finalized')));
      const lowest = blocks.reduce((a, b) => (b.number < a.number ? b : a));
      if (lowest.number >= number) return lowest;
      await sleep(POLL_MS);
    }
  }
  // A snapshot waits until the block holding the latest write (or `atLeast`) is finalized on every provider.
  async snapshot({ nfts, edges, connections, atLeast }) {
    const fin = await this.finalizedAtLeast(atLeast ?? await this.providers[0].getBlockNumber());
    const hashes = await Promise.all(this.providers.map(p => this.available(() => p.getBlock(fin.number)).then(b => b.hash)));
    assert.ok(hashes.every(h => h === hashes[0]), `Providers disagree on finalized block ${fin.number}`);
    const at = { blockHash: hashes[0], requireCanonical: true };
    const callAll = async (name, fn, args) => {
      const c = this.contracts[name], data = c.iface.encodeFunctionData(fn, args);
      const raw = await Promise.all(this.providers.map(p => p.send('eth_call', [{ to: c.address, data }, at])));
      assert.ok(raw.every(r => r === raw[0]), `Providers disagree on ${name}.${fn} at ${hashes[0]}`);
      return [...c.iface.decodeFunctionResult(fn, raw[0])];
    };
    return { mode: 'Q', accepted_ms: Date.now(), block: { number: fin.number, hash: hashes[0], timestamp: fin.timestamp },
      nfts: await Promise.all(nfts.map(n => callAll('NodeRegistry', 'node', [n]))),
      edges: await Promise.all(edges.map(e => callAll('TransitPolicy', 'edge', [e]))),
      connections: await Promise.all(connections.map(c => callAll('ConnectionPolicy', 'connection', [c]))) };
  }
  async timing(record) {
    const p = this.providers[0];
    const included = await this.available(() => p.getBlock(record.block));
    let safe_ms = null, finalized_ms = null;
    while (finalized_ms === null) {
      const [s, f] = await Promise.all([p.getBlock('safe'), p.getBlock('finalized')]);
      if (safe_ms === null && s.number >= record.block) safe_ms = Date.now();
      if (f.number >= record.block) finalized_ms = Date.now();
      else await sleep(POLL_MS);
    }
    const reader = await this.snapshot({ nfts: [], edges: [], connections: [], atLeast: record.block });
    return { included: record.status === 'success', tx: record.tx, block: record.block, submitted_ms: record.submitted_ms,
      inclusion_block_time_ms: included.timestamp * 1000, safe_seen_ms: safe_ms, finalized_seen_ms: finalized_ms, reader_accepted_ms: reader.accepted_ms,
      poll_interval_ms: POLL_MS, clock: 'operator host clock for *_ms; block timestamp from chain' };
  }
}

function args(argv) {
  const out = { rpc: [] };
  for (let i = 0; i < argv.length; i += 2) {
    const k = argv[i].replace(/^--/, '');
    if (k === 'rpc') out.rpc.push(argv[i + 1]); else out[k] = argv[i + 1];
  }
  return out;
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split('/').pop())) {
  const a = args(process.argv.slice(2));
  const permit = JSON.parse(fs.readFileSync(a.permit, 'utf8'));
  checkPermit(permit);
  assert.equal(fs.statSync(a.wallets).mode & 0o077, 0, 'wallets file must be mode 0600');
  const providers = a.rpc.map(url => new JsonRpcProvider(url, undefined, { staticNetwork: true }));
  for (const p of providers) assertSepolia((await p.getNetwork()).chainId);
  const keys = JSON.parse(fs.readFileSync(a.wallets, 'utf8'));
  const wallets = Object.fromEntries(['W1', 'W2', 'W3'].map(w => [w, new Wallet(keys[w], providers[0])]));
  const journal = new Journal(a.journal);
  journal.add({ step: 'permit', ok: true, detail: `${permit.approved_by}; window ${permit.window_start} – ${permit.window_end}`, read_mode: 'Q', providers: providers.length });
  const result = await run(new LiveBackend(providers, wallets, journal), journal);
  console.log(JSON.stringify({ ok: result.ok, steps: result.journal.length, last: result.journal.at(-1)?.step }));
  process.exit(result.ok ? 0 : 3);
}
