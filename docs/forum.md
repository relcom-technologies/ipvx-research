# Participants' forum: forum.ipvx.org

Date: 2026-11-07. Status: **Planned.** The owner chose Discourse with Relcom ID sign-in. The VM and
ingress route are requested in relcom-infra #866; nothing is installed yet.

## Why

ipvx.org signs people in through Relcom ID, but signed-in participants have no place to talk to each
other:

- The RFC comment and proposal path (`docs/community-workflow.md`) is deliberately formal: every entry
  is pending until a moderator publishes it, and proposals collect advisory votes on the way to a
  GitHub PR. It is the right tool for changing an RFC, and the wrong one for a question or a sketch.
- Blog comments live in Relcom Press under its own reader pool, so the ipvx.org session does not carry
  over.
- The discussion page mirrors an external network of AI agents, not the project's participants.

Open protocol and research communities mostly use a forum with a chat tab: ethresear.ch,
discuss.python.org and internals.rust-lang.org run Discourse; Rust and Lean also use Zulip; the IETF
works on mailing lists plus GitHub. A forum keeps long technical threads readable and linkable, which
suits this project's habit of giving every object an address.

## Boundaries

- The forum is for discussion. It does not change an RFC, grant a role, count a vote, admit a model or
  open lab access. The RFC-0003 and `docs/community-workflow.md` paths stay authoritative, and a forum
  thread that should change an RFC ends as a proposal there or as a GitHub PR.
- Separate origin: forum.ipvx.org shares no cookies, scripts or allowlist with ipvx.org or
  lab.ipvx.org. The research site keeps its strict self-only policy; it only links to the forum.
- Reading is public. Posting needs a Relcom ID account with a verified email.
- No private data on the forum: no keys, credentials, private intake or host inventory. The forum
  rules say so, and moderators remove such posts.

## Shape

| Part | Choice |
|---|---|
| Host | `proj-ipvx-forum`, a project VM with 2 vCPU / 4 GB / 40 GB on the internal network only, requested in relcom-infra #866 |
| Public name | `forum.ipvx.org`, Cloudflare-proxied, through the cluster's shared ingress to the guest |
| Software | Discourse, official `discourse_docker` single container (app, Sidekiq, PostgreSQL, Redis), stable branch |
| TLS | Ends at Cloudflare and ingress; the container serves plain HTTP on the guest's internal address only, with the `force_https` site setting on |
| Sign-in | OpenID Connect (Discourse's bundled OIDC plugin) against Relcom ID; local logins and other providers off |
| Mail | Outbound only, for notifications and digests; provider to be chosen by the owner |
| Backups | Discourse daily backup on the guest, copied off the guest by the project; restore tested before launch |

## Relcom ID client

Register a second application in the **IPvX Research** project (pool `396952378110115842`), so a
participant keeps one account for ipvx.org and the forum:

- Type: web application, authorization code with PKCE; a confidential client (Discourse's OIDC plugin
  keeps the secret server-side).
- Issuer and discovery: `https://id.relcom.com/.well-known/openid-configuration`.
- Redirect URI: `https://forum.ipvx.org/auth/oidc/callback`.
- Post-logout URI: `https://forum.ipvx.org/`.
- Scopes: `openid profile email`.
- The client secret goes into the container's environment on the guest only; never into Git, a
  report or a chat.

Discourse settings: `openid_connect_enabled`, `openid_connect_discovery_document` as above,
`openid_connect_authorize_scope: openid profile email`, `openid_connect_rp_initiated_logout` on,
`enable_local_logins` off, `auth_overrides_email` on, `auth_overrides_name` on,
`email_editable` off. If Relcom ID does not report an email as verified, Discourse sends its own
confirmation before the account can post; acceptance checks both cases.

## Structure

- Categories: **BCP 0.2**, **RFC drafts** (one tag per RFC, e.g. `rfc-0005`), **Experiments and lab**,
  **Architecture**, **Questions**, **Site and forum** (feedback, moderation notes).
- Profiles: name (from Relcom ID), optional affiliation, optional ORCID iD as a custom user field.
- Chat: Discourse's built-in chat, one public channel per category, open from trust level 1. Direct
  messages from trust level 1 as well, to limit spam from new accounts.
- Trust levels and flags as shipped. The owner is the first admin; moderators are named in the forum's
  about page. Rules: a short code of conduct written for the forum before launch, plus "no private data".

## Links from the site and the lab

Phase 2, after launch: the site and the lab gain an "Обсудить" link next to objects that already have
an address (an RFC section, an experiment, hypothesis H5, lab gate M3). The link opens the forum
search for that object's tag or address, e.g. `https://forum.ipvx.org/tag/rfc-0005`, so the site never
needs forum credentials and stays static. Embedding forum comments into ipvx.org pages is not planned:
it would load forum scripts into the research site's origin.

## Rollout

1. relcom-infra #866 merged; the infrastructure owner applies Terraform.
2. On the guest: Docker, `discourse_docker` with `app.yml` bound to the internal address, the
   Cloudflare real-IP template, mail settings, `DISCOURSE_HOSTNAME=forum.ipvx.org`. Each step on the
   guest needs the IPvX owner's permission.
3. Relcom ID client registered as above; OIDC settings applied; local logins off.
4. The owner adds the proxied Cloudflare record `forum`, like `lab`; a relcom-infra PR
   removes `awaiting_dns`.
5. Acceptance (below), then categories, rules and the first threads.
6. ipvx.org: a "Форум" link in the header and on the discussion page; phase-2 links later.

## Acceptance

- `https://forum.ipvx.org/` answers 200 over CA-verified HTTPS through Cloudflare; the guest has no
  public address of its own.
- Sign-in with an existing ipvx.org Relcom ID account goes through without a new registration; an
  account without a Relcom ID-verified email cannot post before Discourse's own confirmation.
- Sign-out ends the forum session and returns to the forum.
- A notification email arrives with SPF/DKIM passing.
- A backup is copied off the guest and restored into a scratch container.
- Pages pass at 1440, 768 and 390 px in the default theme, with the IPvX palette applied.

## Open decisions for the owner

- Mail provider for notifications (the one Relcom ID uses, or another transactional provider).
- Where backups are kept off the guest (the shared MinIO, or the owner's storage).
- Who moderates besides the owner.
- Whether chat opens at launch or after the forum has its first threads.
