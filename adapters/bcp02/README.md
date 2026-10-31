# BCP 0.2 validated-node EL/CL adapter

Read-only Python library connecting the accepted offline core to an **explicit
operator-bound full EL + CL pair**. No CLI, daemon, admission, contract deployment,
wallet, transaction construction, signing or broadcasting is included. Importing
the library performs no I/O. This change is source preparation with offline
checks, not a Sepolia run or permission to operate a network.

The normative profile, wire format, five read-ABI functions and existing core are
unchanged. Base: `9ac92e80152e588abcee6b97b18796d038cd0154` (PR43).
The mesh and its earlier measurements remain a separate experiment.

## Trust and operator inputs

`Binding` has no usable defaults. Before an explicitly authorized live use, the
operator must supply all three actual contract addresses, approved **actual
runtime Keccak-256 hashes** (including resolved immutable values), both HTTPS
URLs and SHA-256 DER certificate pins, CL genesis fields, a recent trusted
weak-subjectivity bootstrap (execution checkpoint + matching CL root/slot),
installed binary SHA-256 declarations and approved client version prefixes.
The specification pins Geth v1.17.10 and Lighthouse v8.3.2; no client binaries
were installed, measured or executed by these adapter checks.

CA validation, hostname checking and the additional certificate pins are
mandatory. The operator provisions ownership, isolation, credentials and any
custom CA/client certificate context outside this library. A pinned certificate
authenticates that endpoint; it cannot prove operator ownership, correct node
configuration, its executable hash or honest answers. API version strings are
only a consistency check. Binary hashes are out-of-band operator declarations,
not measurements obtained through RPC. No public-RPC voting or fallback exists.

The trusted full CL validates consensus. The adapter verifies the Beacon header
SSZ root, API flags, EL/CL payload/header agreement and ancestry, **not** BLS,
the complete Beacon body SSZ root, execution-header RLP hashing or account/storage
proofs. Malicious authenticated full nodes remain inside this trust boundary.
Synthetic header roots in the tests do not demonstrate Ethereum finality.

## Read algorithm

1. Refuse a persisted conflict or a changed binding. Verify Sepolia chain ID and
   execution genesis, the pinned CL genesis and client versions. Require EL and
   CL synced, CL not execution-optimistic and EL not offline.
2. Read the CL finalized header and its block by root. Compare its execution
   payload with EL `eth_getBlockByNumber("finalized", false)`, then fetch that
   EL header by hash. Compare execution number/hash/state root/timestamp, parent
   hash and CL slot timestamp. Transitional EL/CL head disagreements allow at
   most three attempts within the same resource/deadline budget; no `safe`,
   `head`, `latest` or block-number contract-read fallback is used.
3. Walk bounded EL parent hashes and CL parent roots to the durable saved point
   (initially the explicit bootstrap). Bind the first bootstrap CL block to its
   execution checkpoint. A proven conflicting finalized branch durably latches
   `STATE_CONFLICT`. A merely lagging endpoint cannot move the saved head back;
   unavailable or over-budget ancestry does not claim proof of a fork.
4. For each snapshot, read code and every `eth_call` with precisely
   `{"blockHash": "0x…", "requireCanonical": true}` (EIP-1898). Check runtime
   Keccak hashes, a complementary non-proxy opcode guard and immutable registry/
   transit getters. Decode fixed-size, correctly padded ABI words, enums, owners,
   epochs, keys, roles and policy fields. Any revert, pruned block, unsupported
   EIP-1898 selector, missing/malformed batch result or partial response rejects
   the entire bundle. It never means an absent record.
5. Build core `Snapshot`/`StateView` instances. With packet checkpoint `C` older
   than latest finalized `L`, prove C is an EL ancestor and read two separate
   snapshots, each entirely pinned to its own hash. Core authorization compares
   C against L; rotation/revocation in L invalidates old permissions. A fabricated
   packet checkpoint is rejected without poisoning the durable conflict latch.
6. Publish the new saved point atomically only after both snapshots pass. The
   store uses compare-and-swap, so another reader's update is not overwritten.
   Same-height conflict survives closing and reopening the SQLite store. There
   is no automatic reset, rollback, purge or operator override command.

`Selection` is the explicit bounded query catalog: up to 128 NFTs, 64 edge IDs,
16 connection IDs; referenced endpoint NFTs are included automatically (total
128). `allowsEdge` is queried for selected connection/edge pairs only. This is
**not a ledger enumerator**. Unqueried IDs remain unknown; the embedding caller
must include the entire route and both directions needed for session admission.
Explicit missing records require the contract's all-zero/status-zero tuple;
existing NFT ownership is cross-checked with `ownerOf`.

The adapter accepts finalized-block envelopes for Deneb, Electra and Fulu.
Gloas and any unknown fork are refused, not decoded using an older shape. Live
compatibility with the pinned clients/current Sepolia fork is still untested.

## Embedding interface (no invocation on import)

Construct `Binding`, then `Store(private_path, binding.fingerprint)` and
`Adapter(binding, store)`. Provision a private local parent directory and file
permissions for the store; it is independent of the existing core journal.
Call `read(selection, now=trusted_unix_time, clock_trusted=True, …)` only under
separate operating authorization. The returned `Bundle.view` is accepted by the
unchanged offline core. `clock_trusted=True` is a host assertion, not NTP or clock
authentication performed here; max state age is 1800s and future skew 5s.

Optional `packet_checkpoint` comes from a packet and is treated as untrusted.
Optional `confirmed_core_checkpoint` **must come from the host's trusted durable
core journal**, never from that packet. Only after checking its ancestry does
the adapter set `latest_extends_saved=True`. Without it the value remains `None`;
advancing an already populated core journal must still meet the core's original
ancestry gate. Adapter persistence does not impersonate that separate journal.

Default limits: 512 ancestry steps per walk, 4096 logical API/RPC requests,
128 items per batch, 30s read budget, 3s maximum exchange budget and 8 MiB per
HTTP body. Chunks recheck a monotonic body deadline. Normal OS DNS resolution is
still subject to the host resolver; this library is not a hard real-time process
sandbox. Cancellation/process supervision and bootstrap refresh remain host
responsibilities. No snapshot is returned after the read budget expires.

## Reproduce without a network experiment

Install locked test dependencies in an isolated environment, then from repo root:

```sh
python3 -m pip install -r adapters/bcp02/requirements.lock
python3 -B -m unittest discover -s adapters/bcp02/tests -v
python3 -B adapters/bcp02/checks.py --output /tmp/bcp-adapter-checks.json
cmp adapters/bcp02/evidence/checks.json /tmp/bcp-adapter-checks.json
```

The contract-read fixture is generated using the accepted Solidity bytecode,
constructor immutables and direct messages inside the existing in-memory EVM:

```sh
npm --prefix contracts/bcp02 ci --ignore-scripts --no-audit --no-fund
node --import ./contracts/bcp02/test/offline.mjs adapters/bcp02/tests/generate_contract_reads.mjs /tmp/contract-reads.json
cmp adapters/bcp02/tests/contract-reads.json /tmp/contract-reads.json
```

It includes an active path and the subsequent effective policy invalidation
after a node key rotation. Its addresses, code hashes and EL/CL wrappers are
**fixtures, not operational deployment pins**. Test processes block real socket
connections; transport tests mock HTTPS responses, including certificate failure,
batch errors and truncated/malformed data. No local TCP server is required.
The old core vectors and contract reports are reproduced separately unchanged.

Primary API sources consulted for this implementation:
[EIP-1898](https://eips.ethereum.org/EIPS/eip-1898),
[execution API](https://ethereum.github.io/execution-apis/api/methods/eth_getBlockByNumber/),
[Beacon header](https://github.com/ethereum/beacon-APIs/blob/master/apis/beacon/blocks/header.yaml),
[Beacon block v2](https://github.com/ethereum/beacon-APIs/blob/master/apis/beacon/blocks/block.v2.yaml),
[Beacon sync status](https://github.com/ethereum/beacon-APIs/blob/master/apis/node/syncing.yaml).

No chain transaction, network experiment, deployment, production Action,
independent audit, packet delivery or performance claim follows from these tests.
