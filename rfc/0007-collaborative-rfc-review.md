# RFC-0007 — Authenticated discussion and reviewed RFC changes

Status: **Draft proposal**, 2026-10-27. Proposed amendment to RFC-0003; not ratified, not an IETF RFC. RFC-0003 and the current governance roster are unchanged by this draft. The discussion backend and authenticated HTTP adapter have local tests; actual production admission and formal adoption are separate acceptance gates.

## 1. Purpose and authorities

Permit researchers to register through Relcom ID, discuss RFCs, submit concrete proposals and offer feedback while ensuring that accepted protocol text changes only through a reviewed, approved pull request. Preserve who proposed, reviewed, voted, changed their position and implemented each revision.

Separate five authorities: provider-confirmed account/email, portal roles, public discussion moderation, formal governance ratification and GitHub merge/deployment permissions. None implies the others. Native AgentID generation and packet forwarding remain independent of portal registration. Verified email is not legal-identity, operator-independence or one-person-one-account proof. A user-typed GitHub login is not an authenticated identity binding.

## 2. Public and private material

Keep RFC drafts, decision records, reviewed public source/evidence and contribution history publicly readable. Keep credentials, identity mapping, pending moderation, session state and operational infrastructure private. The current native lab repository is not made public by this RFC. Publishing its code/SDK/test vectors requires a separately reviewed release and licensing decision; do not promise a full open implementation before it exists. General contribution licensing remains an open governance issue.

## 3. Roles and bootstrap

A verified participant submits pending comments/proposals and sees their own pending content. A moderator publishes/hides with reason and audit, without editing the author's words or accepting protocol changes. An administrator assigns/revokes portal roles with audit. A maintainer reviews and prepares concrete GitHub changes under actual repository permissions; that portal label neither issues credentials nor bypasses required review/checks.

After actual verified sign-in and enrollment, bootstrap administrator is pinned server-side by the owner's observed project author pseudonym in root-owned private configuration. The pinned pseudonym must already exist; raw provider subject never enters Git or workflow inputs. First-login, supplied email, profile name, client JSON roles or a typed GitHub account never confer privilege. The prototype stores a project-keyed pseudonym rather than public raw subject or email. The initial governance electorate remains the explicitly disclosed single human owner; portal registration does not enlarge it.

## 4. Discussion and feedback

New comments and proposals start pending and are private to their author and moderators. Only published entries are publicly readable. Hidden entries are not returned to ordinary readers, including by guessed ID. Use bounded plain text, stable author pseudonym, timestamps and original content. Publish/hide, role changes and votes produce durable audit events. Corrections are linked follow-ups; do not silently rewrite earlier positions or remove negative results from history.

This portal workflow supplements the existing GitHub proposal path in RFC-0003; it does not remove that path or require a portal account to read research or propose a GitHub change.

An authenticated participant may cast, replace or withdraw one advisory yes/no/abstain per published proposal. Explicitly label these counts nonbinding. They are not the RFC-0003 tally, not proof of independent humans and not a command to merge, grant access or run a model. Abuse/moderation appeals, retention and account duplication need further policy work.

## 5. Binding decisions and approved PR gate

Continue existing RFC-0003 formal voting until an identity-binding/electorate amendment is separately approved. Pin the eligible human roster and source revision at proposal opening; require more than half of the entire roster, the declared voting window and authenticated eligible latest votes, with no early approval. Model instances and extra verified accounts do not receive formal votes by joining the portal.

A maintainer converts a reviewed proposal into a concrete GitHub PR linking the exact discussion and proposed revision. Explain the problem, change, validation, attribution and limitations. Protocol/governance/admission changes obtain their applicable formal ratification before acceptance. Routine fixes still use an approved PR and required checks. Public comments, moderation publication and advisory support alone cannot change RFC source.

Configure and verify main-branch rules that require the intended review/checks and prevent unreviewed direct changes. Actual enforcement is a repository configuration step, not established by this document or by the backend. In the one-owner bootstrap, disclose the lack of independent review rather than fabricate another reviewer. Record the final decision, exact merge/release revision and subsequent reconsideration in the attributed append-only history. Deployment and infrastructure approval remain separate gates.

## 6. Prototype and acceptance

The standard-library `infra/community.py` prototype implements server-session permission checks, pending/public visibility, moderator publication/hiding, audited administrator role changes, nonbinding unique votes, bounded input/rate/storage and durable idempotent mutations. It has no HTTP listener, provider/GitHub token, network client or executable model path. See [community workflow](https://github.com/relcom-technologies/ipvx-research/blob/main/docs/community-workflow.md) for routes, bounds, state protection and the exact integration contract.

Before exposing it, the adapter must enforce canonical HTTPS Host, exact Origin/CSRF for writes, verified AuthService identity, request/time bounds and private/no-store caching. Bootstrap the actual owner only by an operator-confirmed enrolled pseudonym after verified sign-in. Test the real sign-in and pending/moderator/public workflow, role revocation, concurrent retry, guessed private IDs, hostile HTML treated as text, spoofed identity/roles, rate/capacity failure and actual branch-rule enforcement. Passing synthetic module tests is not production approval or outside adoption.

The prototype stores private submitted text and keyed project pseudonyms; it does not claim encrypted application content or cryptographic authorship of comments. The server authenticates account submissions. Exported journal records identify both original speaker and recorder and cite the review/PR. Retention, deletion/export, appeals and stronger signed contribution receipts remain open work.

## 7. Decision sought

Approve the separation of discussion, moderation, advisory feedback and formal reviewed changes; specify reviewer/branch enforcement and privacy/retention before general admission. Ratify any change to RFC-0003 through its current procedure. Until then this remains a proposed amendment, and neither current electorate nor production access is changed by its existence.
