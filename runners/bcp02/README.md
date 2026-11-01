# BCP 0.2 isolated stand and runner

Implementation of **IPVX-BCP02-NET-001-F / protocol 0.1**, adopted by
[PR46](https://github.com/relcom-technologies/ipvx-research/pull/46), merge
`a81e6d1251baf51c0ab6be1a1be05bb24b7c028c`.

**Implementation for review; network experiment NOT_RUN.** No namespace, raw
socket, networked node, chain transaction or deployment was used to prepare this
package. The accepted plan directory, core, contracts, adapter, integration and
historical mesh evidence remain unchanged. Its old missing-implementation text
is the preserved planning snapshot; this directory records subsequent work.

## What is implemented

- `stand.py`, `controller.py`: collision-safe creation of the three declared
  namespaces and two veth pairs, initially down, IPv6 disabled, no IP addresses,
  no routes or bridges. Audit peer ifindices and namespace inodes. Start both
  full captures before link-up; archive before deleting only owned objects.
- `transport.py`, `entry.py`: AF_PACKET/SOCK_RAW with explicit interface binding,
  outgoing-copy suppression, truncation/original-length checks and MTU limits.
  Separate ETH_P_ALL captures retain all EtherTypes and kernel drop counters.
- `node.py`, `runtime.py`: one sequential loop per node; R has two different MACs
  and Core contexts sharing one BoundJournal. Session-to-port binding is checked.
  Payloads/results travel only through Ethernet. Controls carry a declared case
  and START/STOP/barrier stage, never frames, request bytes or application results.
- `routes.py`: verify the peer's signed suffix, preserve its signatures and sign
  only the local prefix/link. No use of the all-private-keys fixture constructor.
- `fixture.py`, `generate_bank.mjs`: fresh per-run Ed25519/X25519 keys; each actor
  loads only its own private material. Public keys are registered in the accepted
  contracts using direct in-memory EVM messages, not transactions or RPC. Fixed
  synthetic EL/CL envelopes wrap those ABI reads; the accepted adapter checks
  hash-pinned snapshots. No baseline time relabeling, live fallback or old seeds.
- `worker.py`, `scenarios.py`: every declared case, including separate N07 forward
  and reverse subcases, bounded attempts and a SHA-256 worker. Requests and IDs
  survive UNKNOWN. A committed-delivery/worker gap is never automatically executed
  again. A single R-off attempt per original (within the maximum of three) keeps
  ten serial requests inside the protocol's 90-second case bound.
- `linux.py`, `admission.py`: dedicated unused UIDs, all capabilities dropped
  after opening packet sockets, no_new_privs and seccomp denying new sockets,
  namespace changes, process spawning, exec and related escape surfaces. The
  controller independently audits child `/proc` status, namespace and socket FDs.
- `pcap.py`, `verifier.py`: reconcile full captures, signed frames, event hashes,
  retained immutable bytes and closed SQLite journals. Missing evidence/drop is
  INCONCLUSIVE; unexpected EtherType is FAIL_ISOLATION. All cases are mandatory.

## Offline checks permitted in this PR

```sh
python3 -m pip install -r runners/bcp02/requirements.lock
npm --prefix contracts/bcp02 ci --ignore-scripts --no-audit --no-fund
python3 -B runners/bcp02/checks.py --output /tmp/bcp-runner-checks.json
python3 -B runners/bcp02/preserve.py
python3 -B -m runners.bcp02.cli check
```

Tests inject memory ports, synthetic clocks, fake kernel command APIs and
fabricated PCAP/SQLite evidence. Their PASS branch tests the verifier, **not a
network measurement**. The EVM generator is preloaded with the existing offline
network prohibition. No CI command invokes `run`, `entry`, namespace setup,
packet sockets, seccomp installation or privileged Linux processes.

The new workflow is PR-only, isolated and without production credentials.
Existing workflows and prior evidence reports retain their original hashes.
Preparation failures and corrections are retained in `evidence/preparation-notes.json`.

## Future admission and operation — not authorized by this PR

`launch-config.json` deliberately has no owner key, allocated host, binary/image
pins, accepted window, owner scope ACK or separate launch decision. Default CLI
only reports NOT_RUN. `run` fails before setup under the committed configuration.
Changing it requires a reviewed candidate and a newly frozen `manifest.json`.

A future operator must allocate one disposable **Linux x86_64** host, at most two
CPUs and 4 GiB RAM, provision dependencies first, close host egress, obtain a
trusted synchronized clock and record image/kernel/binary pins. UIDs 60001–60004
must be unused. Node processes start in their own namespace, open only their
declared packet sockets, read own key, then drop all capabilities and install the
filter. Private artifact directories are 0700 and files 0600. Private actor cwd
directories have different owners; their root-owned parent is not traversable.

Only after reviewed configuration and separate owner authorization may an
operator supply a root-owned 0600 permit signed by the configured owner key.
The signed payload binds `scope_sha256`, `run_id`, `host_image_sha256`,
`not_before`, `not_after`, `launch:true`, `transactions:0`, `production:false`.
The window must match the accepted configuration and last at most one hour.
Source hashes alone and a user-supplied JSON assertion never grant authority.
The allocated host's machine-ID hash is checked. Before any setup, the permit
and run ID are consumed in a root-private host ledger; copying a permit, changing
its filename or retrying a failed run does not authorize another attempt.

The explicit future command is `python3 -m runners.bcp02.cli run --permit <private-permit> --output <new-private-directory>`.
**Do not execute it under the present authorization.** Each child also verifies
admission before opening sockets. Image identity is operator-attested; actual
kernel config, binaries, CPU/RAM, namespace, socket and clock checks are measured
only during the future authorized preflight. No such preflight has run here.

After stopping children, the runner writes payload, worker, injection, state-bank,
clock, capability/socket, fault-barrier and source/binary/dataset indexes, closed
SQLite hashes, both captures/statistics, result and SHA256SUMS. Teardown happens
after archival; final outcome/checksums also record cleanup failures. No evidence
is purged or automatically published; retain private files for at least seven days.
Collision or replaced namespace/interface identity blocks deletion. A host crash
can leave owned namespaces requiring operator reconciliation; a new run refuses
to delete colliding objects.

## Limits that remain

Linux namespace/capability/seccomp/AF_PACKET behavior is implemented but **not yet
measured**. Offline mocks cannot prove kernel enforcement, capture coverage or
Ethernet delivery. This is one host and one infrastructure operator, not proof of
physical Ethernet, a whole device without IP, independent operators or utility
over IP. Headers/roots are synthetic; ABI execution does not prove Ethereum
finality. A separate live-chain protocol would be needed for that conclusion.
Host resources, a run dataset, installed binary pins, review and launch approval
remain missing. Neither merge nor green unit tests remove those gates.

Reference mechanisms: [packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html),
[veth(4)](https://man7.org/linux/man-pages/man4/veth.4.html),
[network_namespaces(7)](https://man7.org/linux/man-pages/man7/network_namespaces.7.html),
[libseccomp rules](https://man7.org/linux/man-pages/man3/seccomp_rule_add.3.html).
