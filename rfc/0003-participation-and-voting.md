# RFC-0003 — Participation and majority approval

Status: Draft. The owner's majority requirement is binding for project admission. The detailed bootstrap rules below are a provisional implementation proposal, not a claim of community ratification.

## Participation
Anyone can read the public materials and submit a public proposal. Proposals cover an RFC, an experiment, a model or a roster change. Never submit an API key, private key, confidential dataset or unrestricted callable endpoint.

## Electorate and threshold
The current electorate is the human GitHub accounts in governance.json. Initially it contains only the project owner, ashkitt: one eligible person, threshold one. This is explicitly a bootstrap phase. Model instances and duplicate accounts do not gain votes by being connected.

The electorate for a proposal is pinned to the governance.json commit at proposal opening. Approval requires more than half of ALL eligible accounts, not just a majority of those who voted. An abstention or no vote does not reduce the threshold. The provisional voting window is 72 hours from issue creation, with no early approval. A future majority can revise this policy through a roster/policy proposal and reviewed change.

## Votes
Eligible people comment exactly /vote yes, /vote no or /vote abstain on a proposal issue. Only authenticated GitHub User comments count; the latest valid comment per person within the window is used. Late comments, bots, prose and ineligible accounts do not count. Operational status (2026-10-30): CI runs only on pull requests with read-only permissions and tests tally rules on fixtures. Automatic labelling of real votes is not enabled. Comments and membership are publicly inspectable; a label alone or a passed test is not evidence of approval. The voting procedure above remains a draft; this correction does not establish a new operational voting service.

## Separate gates
An explicitly recorded majority decision authorizes research admission in principle; a label alone does not establish that decision. It does not merge code, publish an RFC, run a model or issue a credential. A maintainer still reviews reproducibility, licensing, resource limits and isolation, then performs the scoped deployment through a reviewed change. RFC status remains Draft until the accepted revision and decision record are committed. An external machine can run an experiment locally without being admitted into this private lab.

## Open governance questions
Appeals, removing inactive members, conflict of interest, funding and compute quotas, membership duplication, emergency suspension and long-term release authority require public discussion. This first portal does not pretend those questions are settled.
