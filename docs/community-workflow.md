# Proposed community workflow and implementation boundary

Date: 2026-10-27. Status: **Proposed workflow; backend and authenticated HTTP adapter implemented and locally tested, production user admission not yet demonstrated.** The existing RFC-0003 and `governance.json` remain authoritative until an amendment is approved. This document does not silently amend their electorate or voting window.

## Public work and private operations

The recommended public collaboration surface is `relcom-technologies/ipvx-research`: protocol drafts, decision history, reproducible public evidence, review discussions, proposed changes and issue/PR links. A public draft is easier to inspect and contribute to than a private document behind portal membership. Reading and downloading research do not require sign-in.

The moderated portal is an additional submission path. The existing public GitHub proposal path in RFC-0003 remains available; this prototype does not remove it or require a Relcom account for reading or making a GitHub proposal.

The native lab implementation is currently a separate repository and is not made public by this document. Publishing a reviewed native implementation, SDK, packet test vectors and reproducible interoperability tests is a useful next governance decision, after confirming ownership/license and removing operational material. Do not call the complete implementation open source before that decision and publication. The general source/contribution licensing policy remains open; a portal account or contribution does not transfer copyright or establish an upstream license.

Private operational records include infrastructure access, actual host inventory, user session tokens, OAuth state, database backups, moderation queues, identity mapping, HMAC keys and privileged configuration. No private key, user email, production address or raw private log belongs in public source or research history. A private repository does not substitute for secret management. Public documents and server implementation can remain reviewable while runtime identity and operations remain private.

## Identity and roles

Relcom ID verifies the browser account and its provider-confirmed email. It does not perform legal-identity verification or establish that one account equals one independent person/operator. Native AgentID, portal account, GitHub account and human governance membership are distinct. A typed GitHub username is never sufficient to bind accounts or grant votes.

- **Reader:** public access to RFCs, published discussion, experiments and history.
- **Verified participant:** submits comments and proposals to a private moderation queue; reads their own submissions; gives one changeable advisory vote per published proposal.
- **Moderator:** publishes or hides discussion with a reason and audit event. Cannot rewrite an author's text, change an RFC, assign roles, run models or merge code merely by being a moderator.
- **Maintainer:** reviews a concrete proposed diff and may open/merge a GitHub PR only through actual repository permissions, required checks and the applicable approval/ratification gate. The portal role does not mint a GitHub token or bypass branch protection.
- **Administrator:** assigns/revokes portal roles with a reason and audit event. Has no automatic native-network, infrastructure, model-execution or governance authority.

The backend does not promote the first visitor or match an email to obtain admin. After the owner's actual verified sign-in and community-session enrollment, the operator pins the observed project `author.id` in a root-owned private configuration outside the public tree and service-writable state. `bootstrap_admin_author_id` must name an existing enrolled participant; an invented unknown pseudonym is refused. The raw Relcom subject must not enter Git, workflow inputs or public history. If configuration is absent, everybody stays an ordinary participant. A changed bootstrap identity requires an explicit offline migration; API calls cannot remove the configured bootstrap administrator. Bootstrap is not independent community endorsement.

## A proposal becomes a reviewed change

1. A verified participant submits a bounded plain-text comment or proposal under a named RFC. It starts `pending`, visible only to its author and moderators. The visitor is told that it is not public yet. Do not submit private data or credentials.
2. A moderator publishes or hides it with an auditable reason. Publication approves discussion visibility, not the technical claim. Published text retains its original content and author pseudonym. To correct an argument, submit a linked follow-up; moderation does not silently rewrite it.
3. Other verified participants can give/change/withdraw advisory `yes`, `no` or `abstain`. These counts are feedback. They do not constitute RFC ratification, governance membership or majority admission. Accounts are not assumed independent, and moderators cannot turn a popularity count into a binding vote.
4. A maintainer converts a concrete proposal into a GitHub pull request. The PR links the proposal and exact text/revision, explains the change and validation, and preserves contributor attribution. The backend never writes the RFC source or opens/merges a PR on its own.
5. Changes requiring formal RFC/governance/model-admission approval use RFC-0003: electorate pinned at opening, strict majority of the entire eligible human roster, declared window, latest eligible authenticated vote, no early approval. The initial eligible roster contains one owner. Existing authenticated GitHub voting remains separate from Relcom advisory voting. Any new identity binding/electorate policy itself needs approval and a reviewed change.
6. Merge only a reviewed PR with required checks and the applicable decision recorded. Publish a new exact revision and attributed history event. A discussion approval, account verification, positive advisory tally or portal admin role cannot bypass this gate. Actual branch protection/reviewer settings must be configured and verified separately; this document does not claim they are already enabled.

For ordinary fixes, the maintainer records the required review and tests in the PR. Changes to protocol acceptance, electorate, policy or lab admission additionally require their formal approval. Emergency response and appeals remain open policy questions; moderation should retain reasons and the original audit record.

## Implemented pure-logic API

`infra/community.py` is standard-library-only logic, not an exposed HTTP service. Constructor:

```python
community = CommunityService(private_state_directory,
                             bootstrap_admin_author_id=confirmed_enrolled_author_id_or_none)
response = community.handle(method, path, trusted_session_user_or_none,
                            parsed_json_body, request_id=idempotency_header)
```

Only the server adapter may obtain `trusted_session_user` from the verified `AuthService` session. Its minimal fields are `sub` and boolean `emailVerified`; the module ignores any injected role/name/email fields. Never accept this object from request JSON, query parameters or browser headers. A local HMAC key derives a stable project-specific public pseudonym; raw subjects, email, provider tokens and profile names are not stored by this module. Comments remain untrusted plain text and must be rendered through text nodes, never `innerHTML`.

Exact routes:

- `GET /community/v1/session`: own pseudonym and server-stored portal roles; anonymous readers get no roles.
- `GET /community/v1/rfcs/rfc-0005/entries?kind=comment`: published comments; `kind=proposal` selects proposals. `mine=1` requires verified sign-in and returns only that author's entries, including pending/hidden. `limit=1..50` and `before=<entry ID>` bound pagination.
- `POST /community/v1/rfcs/rfc-0005/entries`: `{kind, title, text}`; comment default, proposal requires title; always creates pending content.
- `GET /community/v1/entries/<id>`: published entry, or the author's own private entry, or a moderator's review.
- `POST /community/v1/entries/<id>/vote`: `{value: yes|no|abstain|withdraw}` on a published proposal; latest one per verified subject, explicitly nonbinding.
- `GET /community/v1/moderation`: private pending queue for moderator/admin.
- `POST /community/v1/entries/<id>/moderation`: `{action: publish|hide, reason}` for moderator/admin; audited, no content rewriting.
- `POST /community/v1/roles`: `{authorId, role: moderator|maintainer|admin, action: grant|revoke, reason}` for admin only; target must already be a known verified participant.
- `GET /community/v1/audit`: bounded private administrator audit view.

Each POST requires a client-generated stable `Idempotency-Key` of 8–128 safe characters. Same author/key/request returns the original response across process restarts; reuse for different content fails 409. Concurrent retries create one entry/audit effect. Keys are retained until an explicit reviewed archival/migration policy; the prototype refuses new writes at capacity instead of silently losing deduplication or audit history.

Bounds: 8,000 text characters, 200 title characters, 12,000 serialized body bytes, 20 pending entries per author, 30 accepted mutations per 10-minute fixed window, 10,000 enrolled accounts, 20,000 entries, 100,000 idempotency records, 200,000 votes and audit records. Queries return at most 50 rows. Votes have a database uniqueness constraint per entry/author. Rate counters expire; content/audit/request history does not silently expire. State directory is 0700; key/database are 0600. The database stores project pseudonyms and submitted content in plaintext, so the operator must keep access/backups private and define retention/export/deletion policy before general public admission. Pseudonyms are not legal anonymity or Sybil prevention.

List responses also have a cumulative 96 KiB item budget, below the existing 128 KiB public proxy limit. Long UTF-8 content can produce fewer than the requested number of rows; use `nextBefore` until it is absent (an exact full final page may lead to one empty page). Replaying a cached privileged operation after role revocation is denied, and a cached vote response cannot expose a subsequently hidden proposal. Back up the private HMAC key and database together; key loss changes pseudonyms and must not be repaired by silently inventing another owner.

The HTTP adapter is a separate required gate: fixed canonical HTTPS Host, exact Origin and CSRF policy for all writes; verified server session; body/header/time bounds; no-store on authenticated/private responses; correct 401/403/404 handling; no unrestricted proxy or private API exposure. Generic auth/CSRF, distributed rate limits, role administration UI, actual GitHub permissions, moderation operations and production acceptance are not claimed by testing the pure module. The module contains no network client, GitHub token, code/model execution or infrastructure control.

## Verification and remaining gates

Run `python3 -m unittest discover -s scripts -p 'test_community.py' -v`. Tests cover permission boundaries, no first-login/email admin, injected-role rejection, private pending/hidden content, moderation/audit, concurrent/restarted idempotency, latest nonbinding vote, rate/capacity rollback and private pseudonym/state files. These are synthetic identities, not a real Relcom sign-in or community adoption test.

Before publication of a working community feature: integrate the authenticated adapter and UI; verify Origin/session/private-cache behavior end to end; pin the real owner's observed enrolled pseudonym only after successful sign-in; exercise the actual pending→published→hidden workflow; inspect audit and role revocation; configure/verify approved-PR-only repository rules; ratify any amended governance policy. Do not publish a test discussion as if it were an outside researcher's contribution.

## Operator activation

The existing identity unit reads optional root-owned `/etc/ipvx-research/community.env`.
After the owner's verified sign-in, read their own project author ID on account.html.
The scoped `ipvx-research` operator workflow can pin exactly that already enrolled
ID on the existing observer. The helper checks the known participant and immutable
bootstrap record through a read-only database connection, writes a private atomic
configuration and restarts only the identity service. It never promotes a typed
email or the first visitor and does not change infrastructure or GitHub access.
A health failure after restart can occur after the audited role was committed:
the configuration is retained, the failure is reported, and recovery must use the
same confirmed ID or a reviewed migration. There is no false promise of an atomic
role rollback. Production activation is a separate receipt, not a local-test claim.

Pilot retention: pending submissions remain private until reviewed; published
research comments, proposals, voting changes and moderation decisions are retained
as project records. Capacity is bounded and there is no silent deletion/expiry.
For correction or a privacy-removal request, contact the project maintainers through
the repository; moderation can hide content promptly and any actual redaction
requires an attributed operator action without republishing the sensitive text.
Do not submit credentials or personal information. Backup/export/deletion automation
is not implemented by this prototype and must not be advertised as a capability.
