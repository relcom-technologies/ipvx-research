# REG-001 runner

Code for [IPVX-BCP02-REG-001](../../../experiments/bcp02-reg-001/README.md). Author/recorder:
`claude-code-assistant`. It is kept apart from `tools/` and `test/`, whose files are hashed into
the accepted contract-check evidence.

- `runner.mjs` — the registered step sequence and its expectations, over a backend. The journal
  follows `protocol.json` step for step; the first mismatch stops the run; nothing is retried.
- `runner.test.mjs` — the full sequence on the in-memory EVM, plus a third party allowed to
  rotate keys, deployed code that differs from the local build, a non-Sepolia chain, a reused
  journal and permits that do not match. No network: `test/offline.mjs` is preloaded.
- `live.mjs` — Sepolia backend for read mode Q. It sends real testnet transactions and runs only
  with a current owner permit naming this protocol, version, chain, the exact step list and the
  window, a 0600 wallets file outside Git and at least three RPC providers. Not run so far.

```sh
node --import ./test/offline.mjs --test reg001/runner.test.mjs     # from contracts/bcp02, after npm ci
```

Before reading a snapshot it waits until the block of the latest write is finalized on every
provider, then reads each record with `{blockHash, requireCanonical: true}` from all providers and
accepts it only if they agree byte for byte. A simulated call before each write tells an expected
revert (third-party attempts) apart without spending gas on it.
