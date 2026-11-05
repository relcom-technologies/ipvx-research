# BCP 0.2-LC light-client reader

Read-only Python library for the second BCP 0.2 trust mode,
[verified-light-client](../../docs/proposals/bcp-0.2-light-client/README.md). It reads
the same registry snapshots as [adapters/bcp02](../../adapters/bcp02/README.md), but
through a local Helios 0.12.0 instead of an operator's full EL + CL pair. The accepted
adapter files are imported, never modified: later work pins their hashes.

Helios verifies sync-committee signatures from a pinned weak-subjectivity checkpoint
and every account, storage and code value against the verified state root. This
library reaches it over loopback HTTP only and never contacts its upstream RPCs.
`LightBinding` pins the loopback endpoint, the three contracts and runtime hashes,
the Helios checkpoint, an execution bootstrap, the Helios binary SHA-256, its exact
version and the declared upstreams. The profile ID differs from validated-node only
in the trust-mode byte (2 instead of 1).

`LightAdapter.read` keeps the adapter's snapshot, packet, core-journal and store
rules. It changes the identity and head checks: chain ID and the exact client
version (Helios cannot serve block 0); Helios must report itself not syncing, which
it does only while its verified head is under 60 s old; the head is its `finalized`
block. Ancestry to the saved point is one block-by-number lookup, which Helios
answers only when the hash matches the EIP-2935 history of its verified head. A saved
point more than 8191 blocks (about 27 hours) old is therefore `STATE_UNAVAILABLE`,
never a conflict, and needs a new bootstrap. No beacon root is tracked.

Reproduce offline from the repository root:

```sh
python3 -m pip install -r adapters/bcp02/requirements.lock
python3 -B -m unittest discover -s lightclient/bcp02/tests -v
```

Tests block real sockets and answer as Helios would around the adapter's offline
contract-read fixtures. Live compatibility with Helios is untested; nothing here
installs or runs it. The first live read is specified by
[REG-001-LC](../../experiments/bcp02-reg-001-lc/README.md).
