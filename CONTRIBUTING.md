# Contributing to IPvX research

Read the public [RFC drafts](rfc/), [evidence limits](docs/native-device-prototype.md),
[community workflow](docs/community-workflow.md) and [attributed history](history/README.md).
Reading and forking the public research repository do not require portal registration.
The complete private lab and operational infrastructure are not published by this policy.
There is no general source or contribution license grant yet; clarify reuse and contributor
rights before importing someone else's implementation or distributing a derivative.

Use a GitHub issue for a research proposal or a verified portal comment under the relevant
RFC. Comments enter a private moderation queue; publication is not technical acceptance.
Portal support votes are advisory. Binding governance uses RFC-0003 and the pinned human
electorate in governance.json, initially only the owner. Do not equate account count,
model count or cryptographic network IDs with independent governance votes.

For the existing binding proposal workflow, eligible humans comment exactly
`/vote yes`, `/vote no` or `/vote abstain` on GitHub. The window is 72 hours;
strictly more than half of the entire electorate pinned when the proposal opens
must approve, with no early approval. Changes to the roster/rules use the same
proposal/review process. Model admission additionally requires a maintainer's
separate isolation, resource, code and license checks. Approval never executes
the submitted model automatically.

For a concrete change, fork the repository and open a pull request against main. Explain
the problem, exact proposed behavior, evidence, checks and limitations. Link the original
proposal and preserve its author. Append your own history record under a registered
participant ID. Never add credentials, personal account data or infrastructure inventory.
Publish raw model outputs and negative results with dataset/prompt hashes, topology
and ordinary-IP comparisons. Do not infer global deployment or independent operator
adoption from this single-operator lab. RFC text stays Draft until its approved
exact revision and decision record are committed.

Participants propose changes; moderators decide discussion visibility with a recorded reason;
maintainers review source and tests; administrators manage portal roles. Portal roles do
not grant GitHub credentials, infrastructure, model execution or native network admission.
Nobody's comment or vote automatically edits a specification or merges code.

Source changes use reviewed PRs and passing verification/browser checks. Protocol policy,
membership and admission changes additionally require the existing formal approval gate.
Check actual repository rules before claiming they are enforced; CODEOWNERS alone is not
branch protection. Repository administrators retain explicit emergency authority, which
must be documented when used. Draft RFCs are proposals, not adopted standards.

For local checks use the pinned authentication requirements and run the Python unit tests,
scripts/check_site.py, and the browser workflow. The isolated whole-guest experiment has
its own instructions in experiments/strict-native/README.md and a separate manual CI run.

## Owner control of source changes

The project owner decides whether an individual contribution is accepted and
performs merges to the public repository. Branch rules require the owner's
account for repository branch changes; main also requires a pull request and
passing `verify` and `browser` checks. No separate reviewer is required for
ordinary source releases. A merge through the owner's account is not evidence
that an assistant has received the owner's approval; agents must obtain the
owner's authorization before acting. Organization owners remain able to change
repository rules, and those organization-wide roles are outside this repository
policy. These source-control rules do not themselves change the separate draft
RFC-0003 procedure for research admission.
