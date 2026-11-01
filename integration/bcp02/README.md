# BCP 0.2 adapter/core composition and full offline cycle

Source base: `8fb04e89dfbbe7a1b6f05f1fdb465bf4193c1179` (ordinary merge of
PR44). This adds a composition layer and reproducible **offline logical cycle**.
The accepted core, EL/CL adapter, contracts, wire profile, vectors, reports and
mesh measurements are retained byte for byte. No protocol version is changed.

## What is connected

`AdapterCore` owns a `Core` instance. Before each receive, sent-handshake hook,
state query, route query or DATA preparation it obtains a fresh `Bundle` from
the real `Adapter.read` implementation, using the packet's untrusted C when
appropriate and the **actual locally persisted core checkpoint** as the trusted
ancestry anchor. Its constructor and operations have no caller-supplied
`StateView`, attestation flags or saved-checkpoint parameter. The ephemeral
`Core.state` is cleared after success or failure; there is no cached-state fallback.

`BoundJournal` extends the core journal with a durable profile/local-NFT binding,
a checked checkpoint getter, an operation guard and an atomic checkpoint
comparison. The ancestry assertion may be consumed only for the exact saved
point checked by the adapter. A concurrent checkpoint change causes refusal
instead of applying that assertion to another point. A populated unscoped legacy
journal or a different chain/node binding is refused without guessing a migration
or resetting the original. Existing delivery and receipt semantics are inherited.

The existing persistent conflict stops remain in both databases. A request's
complete original plaintext, source/destination, message ID and request hash are
persisted before prepared DATA is returned. Conflicting reuse is refused. Up to
64 unfinished originals are allowed; COMPLETED frees a pending slot without
deleting the original or any receipts. No new ID or retry is allocated internally.

The fixed `Selection` is operator configuration, with explicit NFT, edge and
connection IDs including reverse session permissions. Unknown IDs and malformed
frames are refused before any adapter read; packet contents cannot broaden the
catalog. Every read remains bounded and EIP-1898 hash-pinned inside the unchanged
adapter. Sender keys and destination encryption keys come from checked state.
Both directions of neighbor consent are required for sessions; reverse receipts
also require a separately active reverse connection policy.

The host supplies trusted Unix/monotonic time and explicit packet/sequence IDs.
The bridge advances the core's time by elapsed adapter-read time, rounding Unix
time conservatively upward, so a packet that expires while reading state is not
accepted with its original arrival time. Sent controls must match the current
contract key and roles. Returned route candidates are scoped to the explicit C
passed to `routes`; cached routes at other checkpoints need their own refresh.

## Minimal embedding surface

Create the existing explicitly provisioned `Binding`, `Store` and `Adapter`, then
`BoundJournal(private_path, binding.profile, local_nft)` and
`AdapterCore(adapter, journal, selection, local_nft, local_mac, decryption_key=…)`.
Construction has no endpoint I/O. Methods return bundles, packet values or local
`Decision` instances. `FORWARD` and `DELIVER` do not send bytes or execute tasks.

Use `receive(raw_ethernet_bytes, now=…, monotonic=…, clock_trusted=True)` and the
`sent_hello`, `sent_challenge`, `sent_confirm` hooks around the existing pure
builders. `prepare_data` authorizes a supplied path/session and persists the
original before returning a freshly encrypted packet. State for other pure
builders can be obtained through `state`; there is no automatic peer discovery,
route advertisement, response generation, forwarding loop or social publisher.
The offline harness explicitly copies bytes, builds route suffixes, rewraps hops
and constructs responses. Its result bytes are fixtures, not execution receipts
from an independently running application.

The bridge intentionally uses private core hooks at the pinned base revision;
the preservation receipt and cycle tests make that coupling explicit. It is
composition of the existing state machine, not a replacement protocol engine.
Use one owner/runtime per journal. The guard rejects reentrant calls; checkpoint
CAS also detects another connection's advance. Adapter and core databases are
**not atomic together**, and this does not prove cross-process application
execution exactly once. A checked adapter head may persist even when a packet
is later rejected. No packet/decision escapes a failed core/outbox commit.

Private paths, file permissions, disk limits/retention supervision, key custody,
local-interface lifecycle, process supervision, chain/endpoint provisioning and
live operating authorization remain host responsibilities. There is no daemon,
operational CLI, endpoint loader, migration/reset command, wallet or transaction
capability here. This PR does not authorize attaching a network interface.

## Offline evidence

The new generator uses the unchanged Solidity contracts with direct in-memory
EVM messages. Three public test Ed25519/X25519 key pairs are registered; four
directed edges and two directed connections receive both explicit owner consents.
It records active views and separate key-rotation, transit-withdrawal and reverse-
connection-withdrawal states. No transaction objects, RPC, real NFT registrations
or chain deployments are involved. All published test seeds are **public fixtures
and must never be operational keys**. Addresses and runtime hashes are fixture
bindings, not an assigned deployment.

The unchanged adapter consumes these exact ABI words inside synthetic EL/CL
envelopes via mocked authenticated-transport I/O. The full cycle performs:

1. Two real HELLO/CHALLENGE/CONFIRM exchanges, with no session injection.
2. ROUTE origin/suffix signatures and core route authorization.
3. DATA encryption, source/hop signatures, relay authorization and immutable
   rewrap, followed by destination decryption and delivery deduplication.
4. Reverse ACCEPTED and COMPLETED receipts, then ERROR. The durable receipt stays
   COMPLETED with the same result hash; ERROR is recorded without rollback.

Negative tests cover key and policy withdrawal in L against old C, RPC/storage
failure without fallback, expiry during a read, replay, duplicate delivery,
conflicting requests/results, UNKNOWN linkage, scoped journals, checkpoint races,
persistent conflict stops and restarts. Session admission must be repeated after
restart; original requests, deliveries and receipts persist. Application execution
or independent operation is never inferred from these outcomes.

The deterministic receipt records logical stages, frame lengths, plaintext/result
digests and source hashes. HPKE uses fresh randomness, so newly built ciphertext
bytes vary. Within each run every immutable byte and source signature must survive
rewrapping unchanged. The old fixed 50-vector report remains byte-identical,
including the recorded N29 caveat.

## Reproduce

From repository root with Python 3.13 and Node 24:

```sh
python3 -m pip install -r adapters/bcp02/requirements.lock
npm --prefix contracts/bcp02 ci --ignore-scripts --no-audit --no-fund
node --import ./contracts/bcp02/test/offline.mjs integration/bcp02/tests/generate_reads.mjs /tmp/bcp-cycle-reads.json
cmp integration/bcp02/tests/contract-reads.json /tmp/bcp-cycle-reads.json
python3 -B integration/bcp02/checks.py --output /tmp/bcp-cycle-checks.json
cmp integration/bcp02/evidence/checks.json /tmp/bcp-cycle-checks.json
python3 -B integration/bcp02/preserve.py
python3 -B integration/bcp02/offline_cycle.py
```

Test processes block real TCP connections and DNS. Node generation preloads the
existing comprehensive network guard; Python uses only mocked HTTP responses and
local temporary SQLite files. Logical clocks avoid treating machine load as a
protocol result; the read-delay case explicitly advances time to test expiry.
These runs measure neither latency nor throughput. No local socket server or external chain is used.
The new CI is `pull_request` only, isolated and without production credentials.

This is one-process verification of component composition. It proves neither
Ethereum finality/live client interoperability, physical Ethernet delivery,
distributed route discovery with separate key holders, independent operators,
application semantics nor practical advantage over IP. The adapter's validated-
node trust limits (including no local BLS/full-body-SSZ/storage-proof verification)
remain unchanged. Mesh is a separate historical experiment. No network experiment,
chain transaction, paid model, deployment or production Action was performed.
