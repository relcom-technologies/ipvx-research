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

The original owner-side reader still verifies and decrypts the signed envelope
locally for review. The subsequent notification migration removes the desktop
dependency from delivery: `ipvx-notifier.timer` runs every five minutes on the
existing server and sends owner-only email through the existing TLS-required
Relcom SMTP relay. The owner selected the already established notification
address; its value is installed privately and is not part of this public record.

A separate network-free service projects only journal identity, sequence,
freshness and coverage. The networked notifier runs as a non-login user with no
access to the private journal, intake database, model keys or owner RSA key.
Email contains fixed links and counts, without proposal text, identifiers or
credentials. New/changed versions, public activity and source access transitions
are notified; stable state stays quiet. The old private checkpoint seeds the
server state, avoiding another notification for already handled comments.

Pending batches are saved before SMTP; cursors advance only after acceptance.
Failed delivery retries the same persisted batch and Message-ID. Acceptance by
the relay is not proof of inbox receipt. A crash after acceptance but before
checkpoint persistence can duplicate a message with the same Message-ID.
The server/relay cannot report their own complete outage while disconnected.

All three approved public sources are read without deploying the owner's GitHub
token. GitHub discussion 2406 uses validated public comment-count and timeline
activity markers: it signals page activity, not complete comment-body retrieval.
Changed/missing markup becomes missing coverage. ClawMesh uses its public issue
API. Moltbook's known depth-five incomplete comment tree remains explicit.
Local assistant runs can still review evidence and prepare private proposals;
they no longer gate owner email delivery. No automatic reply publisher or model
generation is introduced.

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

Autonomous notifications: infrastructure PR
[810](https://github.com/relcom-technologies/relcom-infra/pull/810), merged revision
`59e88f46f1abc1e03fe180573e4b9989e29e24d9`. Installation uses the existing owner SSH
route, outside Actions. The original observer remains pinned to its earlier
revision; the notification migration does not rotate its keys or reset its journal.
