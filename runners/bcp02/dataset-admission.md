# Dataset-bound admission v2

Implementation for PR review; **no network run or real owner permit issued**.
Supersedes the launch-data lifecycle of accepted PR47; the exact original
manifest/check receipt and preparation failures remain in `evidence/archive/pr47/`
and Git revision `8c68879211f2d491017bd5f821ec610138eade9c`. PR48 preparation files
are the unchanged dated snapshot which identified this gap, not current launch
readiness. Neither their preparation hash nor an old runner1 permit is v2 authority.

## Prepare, review, authorize, consume

1. On the separately allocated disposable host, a later authorized operator may
   invoke `python3 -m runners.bcp02.cli prepare-dataset --run-id <new-id> --output <new-private-directory>`.
   It exports only local in-memory EVM fixture state and fresh actor keys, seals
   the bundle and prints a descriptor. No namespace, packet socket, live RPC,
   transaction, controller, model or permit is created. The command checks source
   pins first. It refuses existing output/seal paths; failure leaves evidence in
   place. Tests use synthetic times/keys in disposable directories, never a live
   run dataset. This PR does not execute this preparation command on a real host.
2. Review exact source/configuration, the descriptor, host/runtime/preflight and
   launch window. `launch-config.json.run_dataset` must equal the complete signed
   descriptor. Other owner/resource gates remain required and default to null.
   Updating configuration requires a new source manifest/scope and owner ACK;
   the dataset contains no source hash, so there is no circular source/data hash.
   The final permit binds both. No operator-supplied hash grants launch authority.
3. A separately authorized owner signs a v2 payload with the reviewed trusted
   Ed25519 key. Signature domain is `IPVX BCP02 isolated run permit v2\0`.
   Required fields are exactly `version:2`, `scope_sha256`, `run_id`,
   `host_image_sha256`, `not_before`, `not_after`, `launch:true`, `transactions:0`,
   `production:false`, `dataset`. Old domains/payloads are rejected.
4. Future explicit `run` additionally requires `--dataset <sealed-directory>`.
   Before consuming a permit, the controller repeats admission and validates all
   bundle bytes, freshness, file permissions, run ID and actor key/public-state
   correspondence. It copies those checked bytes from memory into a new private
   run snapshot, not from paths read a second time. It never calls `export` and
   cannot silently regenerate, renew or replace a dataset. The checked permit is
   archived and that copy is passed to children. The existing one-use permit/run
   ledger remains mandatory; a consumed attempt needs a new decision, never a
   copied file or automatic run-ID replacement.

The descriptor has exactly these fields:

- `run_id`: the same immutable run ID as the permit and public fixture.
- `dataset_sha256`: SHA-256 of the **exact raw dataset.json bytes**.
- `bundle_sha256`: SHA-256 of the **exact raw bundle.json bytes**. The manifest
  binds `dataset.json`, `bank.json`, `public-keys.json` and A/B/R `key.json` hashes.
- `created_at`: integer Unix time fixed once during export.
- `expires_at`: exclusive integer deadline, derived as described below.
- `max_state_age_seconds`: exactly **1800**, never a caller-selected extension.

All directories are owner-only 0700; input files are regular, singly linked,
owner-only 0600 and bounded to 16 MiB. Symlinks, hardlinks, special files, duplicate
JSON keys, missing/extra files and unrecognized directories fail closed. Runtime
checks require root ownership through the root-only admission path. Secrets stay
private; no keys or operational permits are committed. Child processes read the
public manifest/state and only their own copied private key; its hash and derived
public keys must match the signed bundle and EVM fixture state.

## Freshness is part of the signature

Let `c` be `created_at`, and `t_min` the oldest checkpoint timestamp among the
three ordinary fresh checkpoints and all fresh fault branches. The intentional
stale N08 envelope is excluded. Fresh checkpoint times must be within `[c-60,c]`.
The fixed deadline is:

`expires_at = min(c + 1800, t_min + 1800)`

No reading, copying, signing, restarting or retrying updates this deadline. Current
wall time must satisfy `created_at <= now < expires_at`. The signed permit window
must fit wholly inside that interval and last at most one hour (the dataset bound
is stricter). It can be shorter; it does not extend the 1200-second active limit.
A future launch candidate must leave enough valid time for its intended cases.

The controller checks freshness before claiming, after copying, before namespace
creation, and during bounds/poll checks. Children recheck signed input/freshness
before packet sockets and then check time during their loop. Existing trusted
clock/discontinuity checks remain in force. Expiry stops further processing and
cannot become PASS. No clock skew exception extends this dataset deadline.

If owner review or environment work outlasts freshness, retain the expired package
as evidence, prepare a **new** dataset and obtain a new exact descriptor ACK and
permit/window. Never relabel old checkpoint times under an existing hash/signature.

## Evidence and limits

The run archives the signed envelope, declared owner public key, verified permit
hash, descriptor and admission time. Both dataset indexes, captures and event UTC
values must reconcile with that signed lifetime. The offline verifier checks
signature/integrity and that recorded traffic/events are inside the permit/data
window; unexpected EtherTypes remain FAIL_ISOLATION even with a bad timestamp.
Missing or inconsistent admission evidence is INCONCLUSIVE. A supplied public key
and self-contained receipt alone cannot authenticate a human owner or establish
independent approval. The operator must compare the owner key and scope with the
reviewed trusted configuration; these unit fixtures do not supply that authority.

State is still explicitly synthetic EL/CL envelopes around local ABI reads. This
change does not prove Ethereum finality, Linux isolation, physical Ethernet,
independent operators or utility over IP. VM allocation, target preflight, final
source/runtime/dataset review, owner scope ACK, launch window and separate one-run
owner decision remain pending. Mesh and its evidence remain separate and unchanged.
