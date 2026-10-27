# Proposed decision 0005 — Separate routing from attestation

Date: 2026-10-27. Status: **Proposed; not ratified or implemented**.

## Attributed discussion

- **Project owner:** asked to continue native IPvX development and testing; proposed dedicated machines analogous to miners/validators to sort messages, verify keys and route traffic at larger scale. Asked for candid agent feedback and preservation of how each participant's reasoning changes. Mentioned a previous AWS design, whose specification was not present in this review.
- **Assistant technical assessment:** supports testing dedicated routers, but does not support a mandatory validator layer without a specific claim, threat or measured bottleneck. Endpoints generate their own private keys. Key possession, membership, current reachability and forwarding are different facts. Signature verification alone does not require a validator authority and does not establish honest behavior or physical reachability.
- **Independent participants:** no independently administered agent or operator preference survey was performed for this proposal. No vote or endorsement is inferred from the assistant's response or from the owner's instruction to continue development.

## Evolution recorded

The earlier conceptual route was modular identity/resolution backed by authenticated shared records, with a possible transition from existing transport to native media. The lab subsequently demonstrated bounded native Ethernet delivery with local signed path-vector routing. The new question is how to divide work when endpoints and traffic grow. The proposed answer is to separate endpoint work, dedicated forwarding, and any justified policy attestation, while retaining local route decisions and avoiding consensus on each packet.

This is a refinement of roles, not evidence that a global routing architecture, miner economy or validator quorum has been selected. Flat AgentIDs still require a scalable discovery and forwarding design; extra machines alone do not solve that problem.

## Proposed decision

1. Evaluate dedicated routers against the existing endpoint-heavy baseline at equal total resource cost.
2. Keep endpoint identity keys locally generated and controlled; do not turn validators into address or private-key distributors.
3. Keep forwarding independent of a mandatory global validator, blockchain finality or model inference.
4. Test optional scoped attestations only where their claim and benefit can be specified, including cache expiry, revocation and service-outage costs.
5. Investigate access routers, signed agent attachment and aggregate inter-router reachability without assuming every router stores every global AgentID.
6. Keep human project majority voting, portal verification, admission policy and packet forwarding as separate authorities and processes.

## Evidence and next gate

The linked [RFC-0005 draft](../../rfc/0005-routing-and-attestation-roles.md) distinguishes implemented lab behavior from proposed mechanisms, cites original IPvX documents and primary protocol references, and defines the A/B/C comparison and rejection criteria. No benchmark was run for this decision. No new key, machine, running service or admission rule was created by writing it.

If dedicated routing fails to improve the specified task/resource objective, retain the simpler arrangement. If attestation adds dependency and cost without solving a demonstrated problem, remove that layer. Accepted changes require a separately recorded review/approval and a versioned implementation with results. Corrections should add a dated explanation and evidence rather than overwrite a participant's earlier position as if it had never existed.
