# BCP 0.2 — implementation boundary and fixture erratum

Author/recorder: `codex-assistant`. Basis: accepted draft at research merge
`51294fd987658236b42db6211645f0f707dbe243` (PR41). This is a linked clarification,
not a rewrite of the earlier specification, vectors or their recorded checks.

The first implementation PR adds an **offline library**, not a live BCP network.
Its modules, checks and omitted chain/transport/application components are listed
in [bcp/README.md](../../bcp/README.md). Registry/policy/finality inputs are synthetic
in the tests. Real blockchain identity, contract execution and independent
interoperability have not been demonstrated by these tests.

## N29-REQUEST-HASH: earlier authentication failure

The original vector has BCP SHA-256
`0bbe49bfa23674bb2f732ac4065fcacc8483e0e240a9f1bf5b6ca4ff194bbab6`.
The retained [vectors.json](bcp-0.2/vectors.json) is the primary
record of its original bytes and expected INVALID_PAYLOAD.

N29's hop is sender NFT 3 → receiver NFT 2, with Ethernet MACs for that pair.
Its session ID is `009ec418d6c26af25dfe3862c52c4ace514bf3f45982d3185d3f6739ae99a9b8`,
which [fixture-context.json](bcp-0.2/fixture-context.json) binds to NFTs **1 and 3**.
The actual 3–2 session is
`36435ace0ebe6aac463ec447f2082fa047e2451cca8e10437e9c1939d5d24613`.

Under the specified validation order, the original must therefore produce local
**AUTH_FAILED before decryption**. Relaxing session membership to obtain the old
expected payload error would violate the protocol. The compatibility test records
this one discrepancy explicitly; all other 49 frozen outcomes match.

An additional, separately recorded case changes only the hop's session ID to the
3–2 session and recomputes its Ed25519 hop signature with the existing public test
key. The immutable bytes, source signature, HPKE metadata, ciphertext and bad
request hash remain unchanged. The fixed case authenticates, decrypts successfully,
then returns **INVALID_PAYLOAD** because SHA-256(plaintext) differs from request_hash.
Its complete bytes and hash are in
[offline-checks.json](../../bcp/evidence/offline-checks.json).

The previous static checks authenticated signatures and ciphertext, not session
membership or BCP execution. Their historical result remains accurately scoped;
the new implementation exposed a fixture preparation error. No old evidence is
deleted or silently replaced. This clarification changes no wire format, policy,
validation order or deployment setting.

Mesh and earlier strict-native/LLM measurements remain separate experiments with
their original revisions and limitations. This PR contains no live network test,
chain transaction, model call, deployment or production Actions.
