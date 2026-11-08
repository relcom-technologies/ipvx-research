# BCP 0.2 isolated stand and runner

Implementation of **IPVX-BCP02-NET-001-F / protocol 0.1**, adopted by
[PR46](https://github.com/relcom-technologies/ipvx-research/pull/46), merge
`a81e6d1251baf51c0ab6be1a1be05bb24b7c028c`.

**Implementation for review; network experiment NOT_RUN.** No namespace, raw
socket, networked node, chain transaction or deployment was used to prepare this
package. The accepted plan directory, core, contracts, adapter, integration and
historical mesh evidence remain unchanged. Its old missing-implementation text
is the preserved planning snapshot; this directory records subsequent work.

The dataset/admission lifecycle is revised for review in
[dataset-admission.md](dataset-admission.md). Original PR47 checks and manifest
remain byte-identical in `evidence/archive/pr47/` and Git; PR48 preparation stays
an unchanged dated snapshot. No old permit authorizes this runner2 revision.

Correction, 2026-11-06, runner revision 3. The statement above that no namespace or
raw socket was used held until this date. Revision 3 was prepared with them in a
disposable local Docker container, see [Permit-free rehearsal](#permit-free-rehearsal).
Network experiment still NOT_RUN. Revision 2 sources and reports stay byte-identical in
`evidence/archive/runner-v2/`. No permit for an earlier revision authorizes revision 3.

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
- `fixture.py`, `generate_bank.mjs`, `dataset.py`: separately prepared and sealed per-run Ed25519/X25519 keys; each actor
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
network prohibition. No CI command invokes `run`, `rehearse`, `entry`, namespace setup,
packet sockets, seccomp installation or privileged Linux processes.

The new workflow is PR-only, isolated and without production credentials.
Existing workflows and prior evidence reports retain their original hashes.
Preparation failures and corrections are retained in `evidence/preparation-notes.json`.

## Permit-free rehearsal

Offline tests inject the kernel, and a real run consumes its one-use permit before
its first namespace. So the first contact with a real kernel would have cost a permit,
and it would have failed. Revision 2 in a disposable container showed four faults,
each one fatal to a run and none able to produce a false PASS:

1. `ip -j netns list` prints nothing until `/run/netns` exists, and `Stand.create` parsed that as JSON.
2. A capture socket bound to a down link has `ENETDOWN` pending, so its first `recv` killed the capture before link-up.
3. `if_nametoindex` opens a socket inside glibc, so the seccomp policy broke every frame sent or received after the drop.
4. SQLite reopens a journal by absolute path, which root-owned 0700 parents refuse to the actor UID, so every node would have stopped at startup.

`python3 -m runners.bcp02.cli rehearse --output <new-directory>` runs the same kernel
contact without a permit: the declared namespaces and veth links, both captures before
link-up, privilege drop and seccomp, denied socket and process creation, a journal and
signatures on throwaway keys under that policy, synthetic 0x88B5 frames of 60 and 1514
bytes along A—R—B and back, the `/proc` process audit, capture reconciliation and
cleanup. Its marked frames do not decode as BCP. It reads no permit, dataset, run key,
Core or chain, changes no launch gate, and `verify` never reads its directory as a run.
Passing shows kernel plumbing only: no Node, no BCP delivery, no measurement.

It needs root and creates and removes network namespaces on the host, so **running it on
the stand takes its own owner permission**. It does not need host egress closed.

Result on 2026-11-06 in a disposable Docker container, not on the stand and not on the
x86_64 architecture of a run, with details in `evidence/preparation-notes.json`:
`REHEARSAL_PASS` with 4 frames and 0 drops per link on revision 3, only with the probe
hiding that kernel's fallback tunnels and bypassing the x86_64 guard. It fails with
each of faults 2, 3 and 4 put back, and without hiding the tunnels. Rehearsal directly
on the stand is what remains; a pass here says nothing about that host.

Conditions a host must meet, each checked only by the rehearsal or run itself:

- no fallback tunnels in new namespaces: where the kernel creates `tunl0`, `gre0` and the like,
  the audit refuses them and cleanup leaves the namespaces in place. Set
  `net.core.fb_tunnels_only_for_init_net=1` first (kernel documentation; not exercised here);
- every directory above `--output` searchable by the actor UIDs (`run` checks this before consuming the permit).

Known gap left open by this revision: each capture runs under its node's UID, because
`spawn` looks the UID up by node and 60004 is never used. Two earlier gaps are closed.
Pins outside the paths that trigger the runner workflow are closed by the source scope
below. `run` no longer calls `git rev-parse` after consuming the permit: the stand has
neither git nor a repository. The run reads the revision from `SOURCE_REVISION` next to
the deployed tree, and preflight requires that file before any permit is claimed.

## Launch tools (2026-11-08)

[LAUNCH.md](LAUNCH.md) describes one authorized run on the stand.

- `owner.py` runs on the owner's own computer only. It generates an Ed25519 key, encrypted
  with a passphrase, and signs the exact v2 permit request after showing it.
- `stand_launch.py` runs on the stand as root:
  - `prepare` exports and seals a dataset, writes the run slots of `launch-config.json`,
    re-pins that file and writes the permit request;
  - `start` checks the permit before taking the host off the network, runs once, brings
    the network back and arms an independent restore timer;
  - `restore` brings the network back on its own;
  - `reviewed-pins` prints the digest the owner acknowledges (below); it needs no root.
- `launch-config.json` carries the measured host pins, the owner's public key and the
  owner's scope acknowledgement. Dataset, window and launch decision stay empty: `prepare`
  fills them for one run.

### Owner key and scope acknowledgement

The owner generated the key on their own computer; only the public key is in
`launch-config.json`. The acknowledgement cannot name the full scope hash, because writing
it, and later the run slots, changes `launch-config.json`, which is itself pinned. It names
`reviewed_pins_sha256` instead: the digest of `manifest.json` without that one file, so it
covers all runner code, tests, plan and evidence pins. `prepare` refuses when the digest no
longer matches, and a test fails on `main`, so any later change to a pinned file needs a new
acknowledgement before a run. The permit still binds the full scope hash of the prepared tree.

## Source scope (2026-11-08)

Until 2026-11-08 `manifest.json` pinned 450 repository files, among them the website, forum,
documentation and old evidence, although a run reads none of them. Website and forum edits
then blocked `cli check` and both preservation checks on `main` without the runner workflow
noticing. Pins now cover the 146 files inside `scope`: the 145 sources already pinned there,
byte-identical, and `tests/test_scope.py`. The scope lists the CI path globs of
`.github/workflows/bcp-runner.yml`: runner, BCP core, adapters, integration, contracts,
NET-001 plan and stand preparation, BCP tests, the BCP 0.2 proposal and the BCP workflows.
A test keeps the workflow triggers equal to the scope, so a change to any pinned file runs
`cli check`. `preserve.py` here and in the plan check accepted earlier sources only inside the
scope; files outside it may change. The scope hash changed with the manifest, so no earlier
review or permit covers it.

## Future admission and operation — not authorized by this PR

`launch-config.json` deliberately has no dataset descriptor, accepted window or separate
launch decision; the owner key, host pins and scope acknowledgement are reviewed above. Default CLI
only reports NOT_RUN. `run` fails before setup under the committed configuration.
Changing it requires a reviewed candidate and a newly frozen `manifest.json`.

A future operator must allocate one disposable **Linux x86_64** host, at most two
CPUs and 4 GiB RAM, provision dependencies first, close host egress, obtain a
trusted synchronized clock and record image/kernel/binary pins. UIDs 60001–60004
must be unused. Node processes start in their own namespace, open only their
declared packet sockets, read own key, then drop all capabilities and install the
filter. Files are 0600. Actor directories are 0700 under different owners; the
root-owned run, cases and case directories above them are 0711, search-only, because
SQLite reopens journals by absolute path after the drop. Everything else stays 0700.

Only after reviewed configuration and separate owner authorization may an
operator supply a root-owned 0600 permit signed by the configured owner key.
The signed payload binds `scope_sha256`, `run_id`, `host_image_sha256`,
`not_before`, `not_after`, `launch:true`, `transactions:0`, `production:false`, and
the complete sealed dataset descriptor under a version-2 signature domain. It
binds raw dataset/bundle hashes, creation time and the exclusive freshness
deadline; the window must end no later than that deadline. See the lifecycle
document above for preparation and review before signing.
The window must match the accepted configuration and last at most one hour.
Source hashes alone and a user-supplied JSON assertion never grant authority.
The allocated host's machine-ID hash is checked. Before any setup, the permit
and run ID are consumed in a root-private host ledger; copying a permit, changing
its filename or retrying a failed run does not authorize another attempt.

The explicit future command is `python3 -m runners.bcp02.cli run --permit <private-permit> --dataset <sealed-directory> --output <new-private-directory>`.
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

Linux namespace/capability/seccomp/AF_PACKET behavior is implemented and rehearsed in
one disposable container, but **not yet measured**, on the stand or anywhere else. Offline
mocks cannot prove kernel enforcement, capture coverage or Ethernet delivery. The real
`entry` loop and Node have still never met a real kernel: that is the run itself. This is one host and one infrastructure operator, not proof of
physical Ethernet, a whole device without IP, independent operators or utility
over IP. Headers/roots are synthetic; ABI execution does not prove Ethereum
finality. A separate live-chain protocol would be needed for that conclusion.
Host resources, a real reviewed run dataset, installed binary pins, review and launch approval
remain missing. Neither merge nor green unit tests remove those gates.

Reference mechanisms: [packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html),
[veth(4)](https://man7.org/linux/man-pages/man4/veth.4.html),
[network_namespaces(7)](https://man7.org/linux/man-pages/man7/network_namespaces.7.html),
[libseccomp rules](https://man7.org/linux/man-pages/man3/seccomp_rule_add.3.html).
