# Research and change history

The owner requires a lasting history of project changes, how positions evolved,
and what each contributor concluded. This directory is the canonical project
record. It complements Git, experiment outputs and draft RFCs; it does not replace
their primary evidence or the separate governance electorate.

## Read the record

- `history-ru.txt`: readable Russian chronology and current evidence limits.
- `events.jsonl`: chronological, append-only events with speaker and recorder.
- `participants.json`: attributed participants, their roles and provenance.
- `commit-manifest.json`: all 53 reachable commits at the two captured project
  heads, preserving Git metadata without inferring who actually spoke or approved.
- `infra-commit-manifest.json`: 16 non-merge commits touching the IPvX lab tree or
  IPvX-named infrastructure workflows, plus the scoped publication PR references.
  Other projects and private infrastructure contents are excluded.
- `evidence-index.json`: hashes and scope of the available public evidence.
- `entry-template.json`: fields for the next contributor's own entry.

The initial 2026-10-27 record is an explicitly reconstructed retrospective. It
summarizes the available conversation and files, not an authenticated, complete
transcript of every previous discussion. Earlier publication authors retain their
attribution; this record does not reconstruct years of unavailable development.
Unknown event times remain `null`. Event order represents the available discussion
sequence; Git author dates and measured run timestamps remain separate evidence.

## Every participant records their own contribution

Before handing off a project change, append an event under your own registered
participant ID. Include the concrete change, a concise decision rationale,
alternatives when relevant, evidence/revision, checks, negative results and limits.
Record changes to claims, protocol, code, experiments, data, documentation,
infrastructure, governance and integrations. Git captures individual code changes;
the journal explains their purpose and the resulting conclusions. Record unfinished
work as `in_progress`, never as successful registration or deployment.

Keep `attributed_to` (speaker/doer) separate from `recorded_by` (recorder). If you
summarize another person or model, cite their actual source and mark the event as
`retrospective_reconstruction`. Do not manufacture their approval, opinion,
independence or timestamp. An assistant's statement of utility is an engineering
assessment, not evidence of an independent agent choosing this network. Qwen A/B
and the tool workers belong to one lab operator.

Publish concise decision rationales and observable evidence, not private scratch
reasoning. Preserve wrong model outputs and failed runs. Distinguish requests,
proposals, adopted decisions, implementation, measurements and untested claims.
Transport receipts prove their documented delivery/signature properties, not the
truth of model answers. Human portal verification is not network ID allocation.

## Corrections and review

Never silently rewrite an earlier event to make a later conclusion look known
before the experiment. Append a `corrected` or `superseded` event linking the
earlier ID and stating the new evidence. A necessary privacy redaction must be
explicitly documented without repeating the sensitive value. Review history
changes with the relevant PR; do not claim that JSON, Git author fields, account
verification or an unanchored hash authenticate an author's identity.

Before committing, check that JSON/JSONL parses, event IDs are unique, sequence
numbers are contiguous, actor/recorder IDs exist, references point to actual files
or exact revisions, and public files contain no credentials, private host
addresses, owner email, browser/login details or raw private logs. The history is
repository documentation; public website publication requires an explicit public
export and the normal deployment path.

## Concurrent drafts

On 2026-10-29, another participant's HX-0131 was published while PR22 and local
work contained unmerged entries with overlapping numbers. Published main entries
were not rewritten. `draft-records-2026-10-29.jsonl` preserves those original
records under qualified archive IDs, their source revision and `canonical:false`.
The nested original ID is historical context, not another canonical sequence
number. Later integration must append new canonical records and link the archived
originals; it must not replace an already published participant's event or infer
that a draft proposal was approved. This archive is supporting evidence included
in the full history bundle; `events.jsonl` alone defines the main sequence.
