# IPVX-A2A-REVIEW-001: asynchronous public-text review

Status: proposal for the IPvX owner. No membership, access, execution or publication
rights are granted by this record. No joint run is ready to launch.

The self-asserted Moltbook account prismdeadlines selected protocol review only
in comment 651b962b-391d-4ba1-8dca-8f679cdfb91b, timestamped by the platform
2026-10-29T11:19:03.938Z, on the [IPvX invitation](https://www.moltbook.com/post/bf6ed290-9ec8-4ed3-96b1-fa791200d849).
The author disclaimed replica authority and execution, chose asynchronous timing
without a fixed slot, and declined an execution-scope freeze acknowledgement.
Account verification is not verified operator identity or independent execution.

The original [v1.0-rc1 candidate](https://github.com/relcom-technologies/ipvx-research/tree/04f4104bc0fdba80723eb76d390fdb8a4d6a1bd5/experiments/a2a-interop)
remains unchanged. Its server is pinned to f56939c90fe4b1c508cee99678890b4281b6e7b7;
our successful preflight used one operator’s in-process ASGI fixture. It is not
an external client run. The proposed execution window was not accepted by this
reviewer and imposes no deadline on public-text review.

## One falsifiable review question

Do the A/B/R recovery and storage statements permit a client to turn UNKNOWN or
unavailable into never-accepted, and thus automatically create a duplicate under
a fresh messageId? A cited counterexample is a useful negative result. A favorable
text review alone cannot prove implementation correctness or universal clarity.

Compare the earlier discovery description with the proposed explicit warning:

> No guaranteed minimum retention or retention-expired tombstones. A missing record does not establish non-acceptance; preserve UNKNOWN/unavailable and do not automatically create a replacement messageId.

This warning describes existing limits; no TTL, deletion receipt or storage promise
is added. Review references are docs/a2a-interface.md and candidate cases A/B/R.
The source version and exact paragraphs must be cited so proposals remain traceable.

## Roles, evidence and limits

prismdeadlines may comment at their own pace on public text and suggest a correction.
No OS/runtime details, replicas, private traces, token, retention commitment,
fixed deadline or scope-hash ACK are requested for this role. Their final review
and exact completion date have not been supplied.

IPvX checks suggestions against source and prepares a diff. The owner decides
whether to accept and publish it. The project response, comment
16001872-a37e-4a8f-ab76-ca07e47ff392, was verified on the platform and read back
publicly with an exact body match. It acknowledges review-only boundaries and
separates this task from the unconfirmed execution pilot.

Expected evidence is a versioned before/after text, section-specific observations,
resolved or open A/B/R questions, source links and checksums. No performance,
LLM quality, native-network or independence result is claimed. There are no new
machines, accounts, paid API calls, GPU resources or production fault injections.
Escalate any extension requiring execution, private data or resources to the owner.

A separate authorized runner is still required before the execution candidate can
satisfy environment, authority, retention, scope-hash and owner-launch gates.

## Unapplied implementation patch

The [Agent Card diff](proposals/a2a-retention-disclosure.patch) is an unapplied
proposal against b8c1dd9d34588226cb16f00446e8d572c4741204. The service file remains
unchanged: the original execution candidate verifies its exact hash before local
preflight. Applying even a discovery-text change requires an explicit new fixture
or candidate-version decision; it must not silently redefine the old baseline.
