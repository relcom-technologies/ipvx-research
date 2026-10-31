# BCP 0.2 offline reference core

This is the first **partial implementation** of the accepted
[BCP-T 0.2 draft](../docs/proposals/bcp-0.2/README.md), based on research merge
`51294fd987658236b42db6211645f0f707dbe243`. It is a library for bounded local
tests, not a deployed BCP node, chain client or replacement for the existing mesh.

## Implemented boundary

- `wire.py`: strict 44-byte header, all seven message layouts, canonical lengths,
  reserved fields, MTU, domain-separated signing inputs, deployment context hash
  and Ethernet byte framing. Parsing only; no socket or interface access.
- `build.py`: signed HELLO/CHALLENGE/CONFIRM, route suffixes and link signatures,
  DATA/RECEIPT/ERROR construction, standard HPKE single-shot encryption and hop
  replacement preserving the entire immutable packet. The route constructor is
  an offline convenience with explicit signer keys, **not distributed discovery**.
  Operational routers must obtain signed suffixes without possessing peer keys.
- `core.py`: pending handshake matching, local five-second deadlines, session
  admission and epoch binding, four-neighbor bound, local anti-replay floors,
  signature/hash/time checks, revocation and directed policy authorization,
  destination decryption, receipt linkage and route cache/ranking. HELLO is limited
  to one per second; control has a 32-frame burst and 16 frames/second refill.
  There are at most eight pending handshakes and 64 cached route advertisements.
  Limits use the caller's trusted monotonic clock, for one Core/interface instance.
- `state.py`: immutable registry/policy snapshots and fail-closed checks over
  explicitly trusted finalized-state inputs. Both packet checkpoint C and newest
  known L are checked. Owner/key/epoch changes and revoked rules invalidate use
  of the old snapshot. Route ranking uses contract costs, hop count and NFT bytes.
- `journal.py`: SQLite transactions for persisted finalized checkpoint, a latched
  finality conflict, outgoing request bytes/linkage, incoming deduplication and
  receipt progression. COMPLETED may arrive first; ACCEPTED/ERROR cannot undo it;
  a different completed result conflicts. Unknown originals stay UNKNOWN.

`receive()` returns local decisions such as FORWARD or DELIVER. **It does not send
frames, execute an application, retry a request, generate a new message ID, or
emit an ERROR.** DELIVER/NEW is a durable deduplication decision, not an exactly-once
transaction spanning an external application. A future application worker needs
its own durable transactional handoff and recovery design. ERROR-to-ERROR responses
are impossible here because there is no automatic error sender.

## Trust and lifecycle limits

`Attestation` is an explicit **trusted adapter input**, not a cryptographic proof.
There is no RPC/JSON loader for it. Setting its fields to true cannot establish
Ethereum finality. The test adapter lives only in `tests/bcp/fixtures.py` and uses
the public synthetic fixtures from the specification. Runtime code never imports
vectors, their IDs, expected outcomes, fixture keys or test timestamps.

This PR does **not** implement or validate the following:

- an authenticated Geth/Lighthouse adapter, EL/CL synchronization/ancestry proof,
  weak-subjectivity bootstrap, EIP-1898 contract reads, runtime code-hash checks,
  the NodeRegistry/TransitPolicy/ConnectionPolicy Solidity contracts or their
  transactions; the snapshot adapter remains a prerequisite to live operation;
- a live Ethernet transport, physical underlay, peer discovery on real machines,
  an operational route-distribution loop or BCP-N;
- an application executor, 64-task admission queue, one-in-flight data scheduler,
  five-second retry deadlines/three-attempt scheduler, service installation,
  monitoring integration or deployment.

Sessions/floors/pending handshakes/routes are memory-only and must be renegotiated
after restart. Persisted checkpoints prevent rollback; a same-height conflict or
explicit incompatible extension latches a stop in the journal. Clearing that stop
has no automatic API. A newer checkpoint needs explicit ancestry from the trusted
adapter; a missing ancestry assertion fails closed. Journal rows are retained
indefinitely in this minimal implementation, exceeding the seven-day minimum;
capacity, cleanup and recovery must be designed before a live service.

For file-backed journals, use a dedicated private directory (0700), a process
umask of 077 and one owner. This library does not install a service or select a
production storage location. Local clocks, state adapters and signing keys belong
to the embedding operator and are not supplied by an untrusted frame.

## Reproduce offline checks

Python 3.13; use a dedicated virtual environment and the pinned dependency set:

```sh
python3 -m venv /tmp/ipvx-bcp-venv
/tmp/ipvx-bcp-venv/bin/pip install -r bcp/requirements.lock
/tmp/ipvx-bcp-venv/bin/python -B -m unittest discover -s tests/bcp -v
/tmp/ipvx-bcp-venv/bin/python -B tests/bcp/vector_report.py --output /tmp/bcp-offline-checks.json
cmp bcp/evidence/offline-checks.json /tmp/bcp-offline-checks.json
```

Dependencies follow the already pinned project version of cryptography. HPKE uses
its standard [single-shot API](https://cryptography.io/en/49.0.0/hazmat/primitives/hpke/),
X25519/HKDF-SHA256/ChaCha20Poly1305, empty AAD and the exact BCP `info` bytes.
No handwritten HPKE/KDF or fake signature checks are used. The separate RFC 9180
primitive encryption KAT is retained unchanged; this PR does not claim to have
reproduced its deterministic ephemeral encryption through the single-shot API.

There are 23 test methods, including all 50 frozen vectors, independent packet
construction, persistent reopen/conflict cases, invalid receipt fields, revoked
policies, exact MTU, pending/expired handshakes, rate bounds, anti-replay poisoning,
all truncations of a routed frame, random bytes and structured byte mutations.
The compatibility harness blocks socket creation and name resolution.

**Results:** 14 positive vectors accepted, 36 negative vectors rejected. Forty-nine
outcomes match the frozen expectations. N29 is rejected earlier with AUTH_FAILED
because of a defective session binding; the separate corrected case reaches
INVALID_PAYLOAD. See [erratum](../docs/proposals/bcp-0.2-implementation-notes.md)
and the exact per-case [offline evidence](evidence/offline-checks.json). This is
one implementation against fixtures, not independent interoperability or a network
experiment. Source hashes make the report reproducible in PR-only CI.

## Preservation

The original 0.1 and 0.2 documents/vectors are unchanged, including the defective
vector. Historical mesh, strict-native/strict-LLM code, raw captures, signed
bundles and their attribution are separate and untouched. Preservation checks
are recorded in `evidence/preservation.json`. No existing experiment is renamed
or presented as blockchain-aware BCP evidence. No production Actions, chain calls,
models, infrastructure changes or deployments are part of this implementation.
