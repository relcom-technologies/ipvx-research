import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import solc from 'solc';
import { keccak256 } from 'ethers';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO = path.resolve(ROOT, '../..');
export const SETTINGS = {
  optimizer: { enabled: true, runs: 200 },
  viaIR: true,
  evmVersion: 'cancun',
  metadata: { bytecodeHash: 'none', appendCBOR: false },
  outputSelection: { '*': { '*': ['abi', 'storageLayout', 'evm.bytecode.object',
    'evm.deployedBytecode.object', 'evm.deployedBytecode.immutableReferences', 'evm.methodIdentifiers'], '': ['ast'] } },
};

export function compile({ support = false } = {}) {
  assert.match(solc.version(), /^0\.8\.38\+/);
  const sources = {};
  for (const name of fs.readdirSync(path.join(ROOT, 'src')).filter(n => n.endsWith('.sol')).sort()) {
    sources[`src/${name}`] = { content: fs.readFileSync(path.join(ROOT, 'src', name), 'utf8') };
  }
  if (support) sources['test/Support.sol'] = { content: fs.readFileSync(path.join(ROOT, 'test/Support.sol'), 'utf8') };
  const imported = {};
  const output = JSON.parse(solc.compile(JSON.stringify({ language: 'Solidity', sources, settings: SETTINGS }), {
    import(name) {
      if (!name.startsWith('@openzeppelin/contracts/') || !name.endsWith('.sol') || name.includes('..')) {
        return { error: 'Only pinned OpenZeppelin imports are allowed' };
      }
      const content = fs.readFileSync(path.join(ROOT, 'node_modules', name), 'utf8');
      imported[name] = { content };
      return { contents: content };
    },
  }));
  const errors = (output.errors ?? []).filter(e => e.severity === 'error');
  assert.equal(errors.length, 0, errors.map(e => e.formattedMessage).join('\n'));
  const warnings = (output.errors ?? []).filter(e => e.severity === 'warning');
  // Production sources must compile without warnings; test harnesses may use a
  // receiver that intentionally cannot receive arbitrary Ether.
  if (!support) assert.equal(warnings.length, 0, warnings.map(e => e.formattedMessage).join('\n'));
  return { output, sources: { ...sources, ...imported } };
}

export function artifacts(result) {
  const byName = {};
  for (const [source, contracts] of Object.entries(result.output.contracts)) {
    for (const [name, contract] of Object.entries(contracts)) byName[name] = { ...contract, source };
  }
  return byName;
}

export function compilationEvidence(result) {
  const built = artifacts(result);
  const frozen = JSON.parse(fs.readFileSync(path.join(REPO, 'docs/proposals/bcp-0.2/contract-views.json'), 'utf8'));
  const contracts = {};
  for (const [name, group] of [['NodeRegistry', 'node_registry'], ['TransitPolicy', 'transit_policy'], ['ConnectionPolicy', 'connection_policy']]) {
    const c = built[name];
    for (const expected of frozen[group]) {
      const actual = c.abi.find(entry => entry.type === 'function' && entry.name === expected.name);
      // solc adds internalType metadata; it is not part of the frozen wire ABI.
      const normalized = JSON.parse(JSON.stringify(actual, (key,value) => key === 'internalType' ? undefined : value));
      assert.deepEqual(normalized, expected, `${name}.${expected.name}: frozen read ABI changed`);
    }
    const bytecode = c.evm.bytecode.object;
    const runtime = c.evm.deployedBytecode.object;
    assert.ok(runtime.length / 2 < 24576, `${name} exceeds EIP-170`);
    // Decode opcodes, skipping PUSH data; raw byte searches produce false alarms.
    const bytes = Buffer.from(runtime, 'hex');
    for (let pc = 0; pc < bytes.length; pc++) {
      const op = bytes[pc];
      assert.ok(![0xf2, 0xf4, 0xff].includes(op), `${name}: forbidden CALLCODE/DELEGATECALL/SELFDESTRUCT`);
      if (op >= 0x60 && op <= 0x7f) pc += op - 0x5f;
    }
    contracts[name] = {
      abi: c.abi,
      method_identifiers: c.evm.methodIdentifiers,
      creation_bytes: bytecode.length / 2,
      creation_keccak256: keccak256(`0x${bytecode}`),
      runtime_template_bytes: runtime.length / 2,
      runtime_template_keccak256: keccak256(`0x${runtime}`),
      immutable_references: c.evm.deployedBytecode.immutableReferences,
      storage_layout: c.storageLayout,
      frozen_read_abi_matches: true,
    };
  }
  return {
    schema_version: 1,
    recorded_by: 'codex-assistant',
    basis_revision: 'f71032b406d82c75e17724d32b791e95b5289ea3',
    compiler: solc.version(),
    settings: SETTINGS,
    contracts,
    sources: Object.entries(result.sources).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0).map(([name,s]) => ({
      path: name, sha256: createHash('sha256').update(s.content).digest('hex'),
    })),
    package_lock_sha256: createHash('sha256').update(fs.readFileSync(path.join(ROOT, 'package-lock.json'))).digest('hex'),
    note: 'Runtime hashes are compiler templates with immutable placeholders, NOT deployed-code hashes or operational BCP context pins.',
    transactions_constructed_or_submitted: false,
    network_or_deployment_performed: false,
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const evidence = `${JSON.stringify(compilationEvidence(compile()), null, 2)}\n`;
  const target = path.join(ROOT, 'evidence/compilation.json');
  if (process.argv.includes('--write-evidence')) {
    fs.mkdirSync(path.dirname(target), { recursive: true }); fs.writeFileSync(target, evidence);
  } else {
    assert.equal(fs.readFileSync(target, 'utf8'), evidence, 'Compilation evidence differs; review and regenerate explicitly');
  }
  console.log('Three contracts compile; five frozen read functions match; bytecode/ABI/storage evidence reproduced.');
}
