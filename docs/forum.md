# Participants' forum: ipvx.org/forum

Date: 2026-11-07. Status: **Backend implemented and locally tested; pages, automatic moderator and
deployment not yet done.** This replaces the Discourse plan of the same date (see "Superseded").

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

1. **Automatic moderator.** A separate process on the server reads `forum_review_queue()` and records a
   verdict with `forum_review(post, verdict, reason, reviewer)`, in-process only, never over HTTP:
   - `publish` — on topic, nothing that breaks the rules;
   - `hide` — clear violations: sexual content, spam or advertising, abuse, credentials, keys or
     personal data;
   - `escalate` — unsure; the post stays pending in the people queue.

   Each verdict is an audit event naming the model and the reason. It will call Claude through the
   Anthropic SDK with the API key in the server's private environment, never in Git.
2. **People.** Moderators see three queues: escalated posts, posts the automatic moderator has not
   reached, and hidden posts. Any verdict can be reversed with a reason. Hiding or publishing a
   thread's opening post does the same to the thread.

If the automatic moderator is not running, posts wait for people; nothing is published unreviewed.

## Phases

1. **Backend** (this change): data model, API, moderation hooks, search, tests.
2. **Pages:** `/forum/`, category, thread and composer pages in the portal's own style and i18n
   (ru/en/de/es), the moderation queues on the admin page, a "Форум" link in the ipvx.org header.
3. **Automatic moderator:** the worker, its prompt and rules, a systemd unit and timer, a local test
   against fixtures. Turning it on in production makes paid API calls and needs the owner's separate
   permission and key.
4. **Links:** "Обсудить" next to RFC sections, experiments, hypotheses, lab gates; a "Форум" link in
   the lab header and the blog footer (Press Settings → Footer).
5. **Notifications:** an on-site unread count for threads a participant wrote in. Email later, once a
   mail provider is chosen.

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
