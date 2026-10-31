# BCP 0.2 contracts — source and offline checks

Author/recorder: `codex-assistant`. Research basis:
`f71032b406d82c75e17724d32b791e95b5289ea3` (accepted offline core, PR42).
This package implements NodeRegistry, TransitPolicy and ConnectionPolicy against
the unchanged [five-function read ABI](../../docs/proposals/bcp-0.2/contract-views.json).
It does not contain a provider, wallet, transaction builder, broadcast script,
service installer or deployment configuration.

## Contracts

`NodeRegistry` uses pinned OpenZeppelin ERC-721. Anyone can register an NFT for
their own calling account, supplying nonzero, distinct Ed25519/X25519 public-key
bytes and roles 1/2/3. The first epoch is one. Registration provides identity
storage only: no transit, membership, vote, legal identity, independence or Sybil
resistance. There is no registration fee in this implementation; real chain gas
and any future abuse-control policy remain outside this PR.

Only the current NFT owner may rotate/reactivate keys or revoke a node. ERC-721
approvals permit transfers, not key or policy management. Rotation and revocation
increment the checked uint64 epoch. All transfer entry points, including approved
operators and self-transfer, increment the epoch, clear both working keys and
roles, and mark the node inactive before any receiver callback. The new owner must
explicitly bind new keys. Receiver callbacks cannot cause stale post-callback
writes. There is no burn/remint path, administrator, upgrade or recovery backdoor.
Lost wallet ownership has no privileged recovery in this minimum implementation.

`TransitPolicy` stores directed edges with cost, ciphertext bound and traffic mask.
The metric is a uint32 route cost, not money. Each proposal records both current
node epochs. Both owners must explicitly consent for their own NFT, even if one
account owns both NFTs. The reverse edge is a separate agreement. A new proposal
or withdrawal increments the checked uint64 version and clears both consents.
Either current owner can withdraw, including while the node is inactive.

`ConnectionPolicy` applies the same bilateral protocol to endpoint NFTs (role bit
1), traffic, maximum hops and ciphertext size. It references exactly one immutable
TransitPolicy, which must reference the same immutable NodeRegistry. Each proposal
contains 1–64 strictly sorted unique edge IDs. Every selected edge must be active
at proposal time; its **exact version** is stored. Changing or withdrawing an edge
makes its old grant unusable, even if that edge later becomes active again.
Reproposal plus both endpoint consents is required to accept a new edge version.
Removed edges are cleared. There is no implicit reverse connection.

The 64-edge limit bounds proposal storage/processing; it is a write-API resource
limit, not a change to the frozen packet format or its seven-hop bound. The
allowlist is not a claim that a physical path exists. Connection endpoints do not
need to own intermediate NFTs; those owners consent through TransitPolicy.

## Write API and effective reads

- NodeRegistry: `register(signingKey,encryptionKey,roles)`,
  `setKeys(tokenId,signingKey,encryptionKey,roles)`, `revoke(tokenId)`, plus standard
  ERC-721 ownership/approval/transfer functions.
- TransitPolicy: `propose(fromNft,toNft,salt,cost,maxCiphertext,trafficMask)`.
- ConnectionPolicy: `propose(sourceNft,destinationNft,salt,trafficMask,maxHops,maxCiphertext,allowedEdges)`.
- Both policies: `consent(ruleId,expectedVersion,partyNft)` and
  `withdraw(ruleId,expectedVersion,partyNft)`; `ruleIdFor(...)` exposes ID derivation.

Rule IDs are Keccak-256 of ABI-encoded domain hash, chain ID, policy contract
address, directed NFT endpoints and caller-selected salt. Domains differ for
transit and connection. A third party cannot reserve a predicted ID without
owning an endpoint. IDs do not change with terms; proposal versions do.

A proposal does not implicitly consent on behalf of its author. Consent pins the
proposal version and the stored node epochs; a rotation between approvals requires
a new proposal. Versions identify terms/withdrawals, not individual approval
events. On withdrawal both sides must approve the new version before use.

Read status 0 means missing (all remaining fields zero). Status 1 means both
consents and current active node epochs match. Status 2 means unusable, including
an unactivated proposal, a withdrawal or stale/revoked node epochs. Missing
ERC-721 `ownerOf` reverts as specified. `allowsEdge` returns false for missing,
inactive, removed or changed-version grants. A connection can remain active while
one permitted edge becomes unusable; other explicitly pinned active edges can
still be checked. Off-chain path validation must additionally check traffic,
sizes, endpoint/path binding and current keys, as the existing BCP core does.

There is no unbounded enumeration of prior consents on rotation: policy views
derive effective status from current registry epochs. Reusing old signatures,
returning an NFT to its old owner or rebinding old public-key bytes never restores
the previous epoch or old consents. Arithmetic overflows revert; counters cannot
wrap. Public-key byte shape is checked, not possession or curve-point validity.

## Reproduce without transactions or network

Use Node 22+ (PR CI uses Node 24), Solidity **0.8.38**, OpenZeppelin **5.6.1**,
EthereumJS EVM/common/util **10.1.3**, ethers **6.17.0**. Exact tarball integrity
pins and transitive versions are in `package-lock.json`. Install scripts are
disabled. Solidity settings are optimizer 200, viaIR, Cancun EVM, no CBOR metadata;
they are fully recorded in `evidence/compilation.json`.

```sh
cd contracts/bcp02
npm ci --ignore-scripts --no-audit --no-fund
npm run compile
npm run check
```

Dependency installation is the only package-network operation. Tests preload
`test/offline.mjs` before dependencies: sockets, DNS, HTTP(S), fetch and WebSocket
are blocked. They execute compiled initcode and message calls only in a fresh
standalone EthereumJS EVM with ephemeral memory state. There is no RPC server,
chain connection, transaction object, signing key, signed transaction, receipt or
broadcast. The synthetic chain ID matches Sepolia for domain tests; this is **not
a Sepolia run or a finality check**. Local contract construction is a test setup
step, not an on-chain or service deployment.

Thirty tests cover frozen ABI, ERC-721 behavior, safe receiver callbacks and
reverts, owner-only permissions, both consents, role/size/traffic limits,
stale epochs/versions, removed and changed-version edges, both directions,
64-edge boundary, integer overflow, immutable bindings and 48 seeded lifecycle
steps. Test-only harnesses expose state injection for overflow checks and are
excluded from the three-contract compilation evidence.

`evidence/checks.json` records exact test names and source hashes. `evidence/compilation.json`
records ABI, selectors, storage layouts and bytecode template hashes. Both are
reproduced exactly by the normal commands and PR-only CI. Evidence regeneration
is explicit (`node tools/compile.mjs --write-evidence`, then
`BCP_WRITE_EVIDENCE=1 npm run check`) so a changed result cannot silently replace
an earlier reviewed expectation. Historical source/evidence remains in Git.

Preparation note: the first ABI checker rejected solc's extra `internalType`
metadata. Normalization was corrected to omit only that non-wire metadata;
function/input/output names, ABI types and mutability still match exactly.
The accepted ABI and contract behavior were not relaxed to pass this check.

## Evidence limits and preservation

The runtime hashes in compilation evidence are **templates with immutable
placeholders**, not deployed-code hashes or operational BCP profile pins. A future
authorized deployment must supply actual addresses, runtime code hashes, trusted
EL/CL channel and checkpoint, then bind a new BCP context. None are invented here.
These checks do not establish gas costs on a live chain, independent security
audit, Ethereum finality, successful packet delivery or practical network benefit.

The [0.1 draft](../../docs/proposals/bcp-minimal-0.1.md),
[0.2 profile](../../docs/proposals/bcp-0.2/README.md), original vectors (including
the documented N29 defect), prior offline core and mesh are preserved unchanged.
`evidence/preservation.json` records hash checks of the existing core/specifications,
38 Lab files and five PCAPs, feature ancestry and previous history. Original signed
bundles are not re-signed or relabeled as BCP evidence.

The next missing integration is an authenticated finalized-state adapter and
contract-read validation at one block hash; this package supplies no such adapter.
No real registrations, consents, transactions, network experiments, paid models,
infrastructure changes, deployment or production Actions were performed.

Primary references used for implementation:

- [OpenZeppelin ERC-721](https://docs.openzeppelin.com/contracts/5.x/api/token/erc721)
  and the locked 5.6.1 source (including its MIT license).
- [Solidity 0.8.38 release](https://www.soliditylang.org/blog/2026/10/22/solidity-0.8.38-release-announcement/),
  including the optimizer fix affecting earlier versions.
- [Standalone EthereumJS EVM](https://github.com/ethereumjs/ethereumjs-monorepo/tree/master/packages/evm),
  whose message-call API does not require transaction/block processing.
