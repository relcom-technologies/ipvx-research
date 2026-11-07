# Participants' forum: ipvx.org/forum

Date: 2026-11-07. Status: **Backend, pages and automatic moderator implemented and locally tested;
not deployed, and the automatic moderator is not switched on.** This replaces the Discourse plan of the same date (see "Superseded").

## Why

ipvx.org signs people in through Relcom ID, but signed-in participants have no place to talk to each
other:

- The RFC comment and proposal path (`docs/community-workflow.md`) is deliberately formal: every entry
  is pending until a moderator publishes it, and proposals collect advisory votes on the way to a
  GitHub PR. It is the right tool for changing an RFC, and the wrong one for a question or a sketch.
- The blog (ipvx.press.relcom.org) is a separate site on Relcom Press. Its reader comments needed a
  second Relcom ID account in the blog's own reader pool, and a participant already signed in to
  ipvx.org met a second sign-in form. The owner turned blog comments off on 2026-11-07; the blog's
  discussion moves to the forum.
- The discussion page mirrors an external network of AI agents, not the project's participants.

The forum is part of ipvx.org itself: the same header, the same Relcom ID session as the account page
and RFC comments, the same strict self-only page policy. There is no second account, no second origin
and no third-party script.

## Boundaries

- The forum is for discussion. It does not change an RFC, grant a role, count a vote, admit a model or
  open lab access. The RFC-0003 and `docs/community-workflow.md` paths stay authoritative, and a forum
  thread that should change an RFC ends as a proposal there or as a GitHub PR.
- Reading is public. Posting needs a Relcom ID account with a verified email.
- Posts are plain text. The browser renders them with `textContent`; no HTML or Markdown reaches the
  page.
- No private data on the forum: no keys, credentials, private intake or host inventory. The moderator
  hides such posts.

## Backend

`infra/community.py`, in the same service and SQLite database as RFC comments, behind the same two
route allowlists (`infra/server.py`, `infra/auth.py`):

| Route | Who | What |
|---|---|---|
| `GET /community/v1/forum/categories` | anyone | the seven categories with thread counts |
| `GET …/forum/categories/<id>/threads` | anyone | threads by last activity; cursor `before=<time>-<id>` |
| `GET …/forum/threads/<id>` | anyone | thread and posts; cursor `after=<post id>` |
| `GET …/forum/subjects/<ref>/threads` | anyone | threads about one project object |
| `GET …/forum/search?q=` | anyone | published posts, words only (SQLite FTS5) |
| `POST …/forum/categories/<id>/threads` | participant | open a thread: title, text, optional subject |
| `POST …/forum/threads/<id>/posts` | participant | reply, optionally to one published post |
| `GET/POST …/forum/profile` | participant | own public name (opt-in, unique) |
| `GET …/forum/notifications` | participant | own threads with counts of new replies |
| `GET …/forum/moderation?queue=` | moderator | `people`, `automatic` or `hidden` |
| `POST …/forum/posts/<id>/moderation` | moderator | publish or hide, with a reason |
| `POST …/forum/threads/<id>/moderation` | moderator | lock or unlock, with a reason |

Categories are fixed: `bcp`, `blog`, `rfc`, `experiments`, `architecture`, `questions`, `meta`. A
subject names the object a thread is about, e.g. `rfc-0005.s3`, `h5`, `m3`, `blog.<slug>`; the site
and the lab link to `subjects/<ref>` from that object. A participant's public label is a project
pseudonym unless they choose a public name; their Relcom ID name and email are never shown.

Every write keeps the existing guarantees: verified account, same-origin POST, idempotency key, write
rate limit, size and capacity bounds, audit event, blocked accounts refused.

## Moderation

A participant's post starts **pending** and is visible only to its author and moderators. A
moderator's or administrator's own post is published at once.

1. **Automatic moderator** (`infra/forum_moderator.py`). A separate process on the server reads
   `forum_review_queue()` and records a verdict with `forum_review(post, verdict, reason, reviewer)`,
   in-process only, never over HTTP:
   - `publish` — harmless: questions, proposals, disagreement, blunt technical criticism, code and
     logs without secrets;
   - `hide` — clear violations: sexual content, spam or advertising, phishing, abuse or threats,
     credentials, keys or another person's private data, attack instructions;
   - `escalate` — unsure: accusations against a named person, third-party vulnerabilities, legal
     claims, missing context; the post stays pending in the people queue.

   A post with a recognisable credential (a private key block, an Anthropic, OpenAI, AWS, GitHub,
   GitLab, Slack or Google key) is hidden by a local rule (`rules:credentials-v1`) and never sent to
   the model. Every other post goes to Claude through the Anthropic SDK as JSON data, with fixed rules
   in the system prompt that tell the model never to follow instructions inside a post, and a JSON
   schema for the answer. An unusable answer (refusal, truncation, an unknown verdict) becomes
   `escalate`. Each verdict is an audit event naming the model and prompt version
   (`claude-opus-5-5:v1`) and a one-sentence reason in Russian for the moderators.
2. **People.** Moderators see three queues: escalated posts, posts the automatic moderator has not
   reached, and hidden posts. Any verdict can be reversed with a reason. Hiding or publishing a
   thread's opening post does the same to the thread.

If the automatic moderator is not running, posts wait for people; nothing is published unreviewed.

## Phases

1. **Backend:** data model, API, moderation hooks, search, tests. Done.
2. **Pages** (done): `forum.html` with categories, threads, a thread page, composer, search, the public name
   and the moderators' queues (`?mod=`), in the portal's own style and i18n (ru/en/de/es); "Форум" in
   the ipvx.org header. `scripts/browser_forum_check.mjs` covers it against a synthetic API.
3. **Automatic moderator** (done, not switched on): `infra/forum_moderator.py`, its rules and answer
   schema, the `ipvx-forum-moderator` service and timer, `scripts/test_forum_moderator.py` against a
   scripted client. Turning it on makes paid API calls and needs the owner's separate permission and
   key; see "Running the automatic moderator".
4. **Links** (done on the portal): "Обсудить на форуме" on every RFC page and "Обсудить раздел" next to
   each of its sections (`rfc-0005.s3`, numbered by heading order), on hypotheses `llm1`…`llm8`, on the
   experiments `experiments.llm`, `.native`, `.documents`, `.scale`, and the BCP page links to the BCP
   category. `forum.html?s=<ref>` names the object, links back to it in the reader's language and
   suggests a category. Still to do: "Форум" in the lab header (ipvx-agent-lab), links from lab gates
   (`lab.<gate>`), and the blog footer (Press Settings → Footer, the owner's setting).
5. **Notifications** (done on the site): a participant follows every thread they wrote in. New
   replies are other participants' published posts after their read mark; writing a post moves the
   mark to it, and opening a thread moves it past the posts the page showed (`forum_reads`, one row
   per participant and thread). The ipvx.org header shows the count next to "Форум" for a signed-in
   participant, the forum toolbar links "Мои темы" (`?mine=1`), each own thread links to its first new
   reply, and new posts are marked in the thread. No email yet: that waits for a mail provider.

## Running the automatic moderator

`infra/install.sh` installs the worker in its own virtual environment
(`infra/forum-moderator-requirements.lock`), a oneshot `ipvx-forum-moderator.service` that shares
the community service's dynamic user and state directory, and `ipvx-forum-moderator.timer`, which
runs it two minutes after boot and two minutes after each run. Both start only when
`/etc/ipvx-research/forum-moderator.env` exists; without that file the timer is disabled at every
deploy.

Switching it on is the owner's step, after a separate decision, because every post sent to the model
is a paid call:

1. Create `/etc/ipvx-research/forum-moderator.env` as root, mode `0600`, with `ANTHROPIC_API_KEY=…`.
   Optional: `IPVX_FORUM_MODERATOR_MODEL` (default `claude-opus-5-5`; a smaller model costs less) and
   `IPVX_FORUM_MODERATOR_DAILY_CALLS` (default 300). The key never goes into Git, a report or a chat.
2. Optionally check the verdicts first without recording them (this still makes paid calls):
   `systemd-run --wait --pipe -p DynamicUser=yes -p User=ipvx-research-auth -p StateDirectory=ipvx-research-auth -p EnvironmentFile=/etc/ipvx-research/forum-moderator.env -E IPVX_COMMUNITY_STATE_DIR=/var/lib/ipvx-research-auth/community /srv/ipvx-research/current/moderator-venv/bin/python /srv/ipvx-research/current/forum_moderator.py --dry-run`.
3. `systemctl enable --now ipvx-forum-moderator.timer`, or deploy again.

Each run reviews up to 20 posts, at most `IPVX_FORUM_MODERATOR_DAILY_CALLS` model calls a day
(counted in `forum-moderator.json` next to the database). When the limit is reached or the API fails,
the run stops and the remaining posts wait for people; an API failure marks the run as failed in
`systemctl status`. To switch it off: `systemctl disable --now ipvx-forum-moderator.timer` and remove
the environment file.

## Acceptance

- Anonymous reading of categories, threads and search; posting refused without a verified session.
- A participant's post is invisible to others until published; the automatic moderator's verdicts and
  moderators' reversals appear in the audit log.
- A hidden post disappears from its thread and from search; hiding an opening post hides its thread.
- Pages pass at 1440, 768 and 390 px, in all four languages, with the strict self-only policy.

## Superseded: Discourse at forum.ipvx.org

On 2026-11-07 a Discourse instance was installed on `proj-ipvx-forum` with Relcom ID sign-in and the
route `forum.ipvx.org` (relcom-infra #866). The owner then chose a forum built into ipvx.org instead.
The Discourse container is stopped and does not start on boot; nothing links to it. After the native
forum ships: remove the Relcom ID app "IPvX Forum", point `forum.ipvx.org` at `ipvx.org/forum` or drop
the record and route, and return the VM through a relcom-infra PR.
