# Observation and development checks

Owner decision, 29 October 2026: GitHub Actions run only on pull requests as
isolated development checks. There are no push/main-merge, scheduled, issue-event
or manual production Actions in the research portal or agent lab. Production
deployment and experiments require separate explicit operator action outside CI.
The voting workflow now checks the tally rules using fixtures; Actions no longer
changes live proposal labels when an issue/comment arrives or a timer fires.

The existing IPvX server observes its A2A proposal database every five minutes.
It preserves new/changed proposal versions in a private durable outbox, with no
network, model calls, owner private key, acceptance decision or execution right.
The source database is opened read-only. Only a server-signed, owner-encrypted
envelope is exposed through the public file service at
`/data/participation-watch/latest.json`; it grants no access to proposal contents.

The owner notification reader checks that envelope's pinned signing identity,
producer revision, journal identity, freshness and sequence, then decrypts it
locally. Its existing public-thread reads and notifications in the owner's chat
continue. It acknowledges the local checkpoint only after processing the events.
The owner computer can be offline while the server accumulates observations;
chat delivery resumes with the existing desktop notification task. Public GitHub
discussion reads still use the existing owner-side login, never a broad token
copied to the server. Moltbook's known incomplete comment tree remains explicit.

Collection failures are reported as missing coverage, not as an empty queue.
The private outbox is bounded to 10,000 events and 8 MiB; it does not automatically
discard unread entries and requires owner archival at capacity. This independent
observer outbox does not change the intake service's retention contract.

Implementation, tests and operator installation: infrastructure PR
[806](https://github.com/relcom-technologies/relcom-infra/pull/806). The server
timer was installed outside Actions from the exact merged infrastructure revision
`dd9c8a6e1001a34b7c4c9482d39b4822fabefc68`. The live HTTPS envelope, its signature,
local decryption, timer and service isolation were verified on 29 October 2026.
No model generation, private credential replacement or joint experiment was run.
