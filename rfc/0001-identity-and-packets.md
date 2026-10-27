# RFC-0001 — Identity and authenticated messages

Status: Draft · experimental IPvX research document · not an IETF RFC.

## Problem
An agent needs a stable identity that does not depend on a DNS name or its current transport address.

## Proposed mechanism
An agent generates an Ed25519 signing key and a separate X25519 encryption key locally. Its ID is derived from the signing public key. Neighbors are explicitly admitted by public key. A signed contact binds the ID to a current link endpoint, version and short expiry. A contact is an assertion by its owner; it does not itself grant network admission.

Tasks bind sender, recipient, message ID, issuance/expiry and ciphertext hash. The destination decrypts and verifies the task, persists a receipt, and uses a request hash to reject reuse of the same ID for different content. Acknowledging admission to a queue is different from completing a model inference.

## Implemented evidence
The bounded lab implements native Ethernet frames using experimental EtherType 0x88B5, fragmentation, hop proofs, signed route advertisements and encrypted task/receipt payloads. MAC addresses are local link locators. Public-key IDs are not automatically globally routable addresses.

## Unresolved
Key recovery and rotation; duplicate-ID behavior during partitions; anti-Sybil admission; metadata privacy; replay/resource exhaustion; cryptographic algorithm agility; persistent application exactly-once semantics after crashes. Current receipt deduplication does not prove universal exactly-once business execution.

## Review criteria
Publish a packet schema, deterministic test vectors, cross-implementation signature verification and failure cases. The existing implementation remains a research baseline until these criteria and the governance vote are completed.
