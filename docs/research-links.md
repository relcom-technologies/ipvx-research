# Discussion-to-experiment registry

`data/research-links.json` is the curated public source for the evidence chains
on `experiments.html#research-links`, their discussion links and RFC indexes.
`scripts/research_links.py` validates and renders it in Russian, English, German
and Spanish. Browser rendering does not read the private intake or submit drafts.

Each run carries an explicit `access` value: `public` or `private_repository`.
The private Lab CI journal is labelled as requiring repository access in all four
languages. Its adjacent pinned JSON summary remains public; the label does not
change repository permissions or publish private artifacts.

Each case preserves its source IDs, a testable question, pinned protocol and run
artifacts, result and limitations. Artifact SHA-256 is over the stored file bytes;
it is distinct from a protocol's own canonical scope hash. Exact Git revisions
anchor the referenced bytes. A digest alone does not authenticate an operator.

The initial chains are A2A recovery A/B/R (local in-process preflight only) and
the existing matched-transport comparison (one PR CI host/operator). The latter
retains the negative practical-superiority finding and slower measured recovery.
Its source is the project's engineering history, not an outside endorsement.
The A2A candidate is preserved unchanged; its old, unaccepted window is elapsed.
Later public review-only clarification does not rewrite the frozen candidate or
supply its missing client runner, scope ACKs or owner launch decision.

To add a case, edit this registry through a project PR, retain the original public
source, supply all four language descriptions and pinned public evidence, and
append an attributed canonical history event. Run the validator and its tests.
Do not add raw private applications, contact details, secrets or private logs.
Public source comments remain untrusted text and platform account verification
is not independent operator verification. The Moltbook snapshot is incomplete at
depth five; this registry makes no completeness claim.

The local draft asks for source, hypothesis, shared task/control, failure cases
and success/failure metrics, proposed roles/versions/time/compute limits, artifacts
and owner decisions. It is not persisted in localStorage or sent on assembly.
Editing fields invalidates the assembled preview and outgoing links. Markdown
is downloaded explicitly. Opening GitHub is a separate click and final submission
happens there. The `draft` query key matches the issue-form field ID, as
documented in [GitHub’s form schema](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema). Oversized URL drafts must be downloaded and pasted separately.
Published RFC entries get source-only draft links; pending/own/moderation lists
are excluded. The registry relationship itself is still a reviewed Git change.

Public A2A operates over HTTPS/IP/DNS; native Ethernet requires its own testbed.
Neither comments, mail, model drafts, moderation, consultative votes nor registry
links accept a participant, allocate resources or approve a launch. No new live
experiment or paid model call is part of these checks.

The 2026-10-30 owner policy places project build/check/release/deploy/migration/
monitoring in project repositories. `relcom-infra` holds shared infrastructure
state only. Existing project operations there are migration debt; this change
does not remove them, invent a replacement infrastructure pattern, change release
pins or migrate services. Actions remain isolated PR checks only. No merge or
production rollout is authorized by this PR.

Checks: `python3 scripts/research_links.py`,
`python3 -m unittest discover -s scripts -p 'test_*.py'`, the normal portal/history/
language/export checks and `node scripts/browser_research_links_check.mjs`.
The latter uses mock public RFC data and checks all four languages at 1440, 768
and 390 pixels, exact draft download, hostile text, public source links, no service
writes and the static no-JavaScript evidence fallback.
