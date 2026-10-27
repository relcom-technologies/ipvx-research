# IPvX Research

Public research and draft RFC portal for IPvX. Static HTML/CSS/JavaScript, local IBM Plex fonts, public sanitized evidence snapshots. The portal itself uses ordinary IP/DNS/HTTPS; experimental native Ethernet delivery is a separate lab.

## Run

Python 3: `python3 -m http.server 8091 --bind 127.0.0.1`, then open http://127.0.0.1:8091/ . The static preview needs no npm, server secrets or private database. Authentication requires the separate server-side service; it is not simulated as a successful sign-in by this preview. Rebuild owned page sources with `python3 scripts/build_portal.py`.

## Checks

Install the pinned sign-in test dependencies first: `python3 -m pip install -r infra/auth-requirements.lock`.

`python3 -m unittest discover -s scripts -p 'test_*.py'`

`python3 scripts/check_site.py`

Browser CI checks desktop/tablet/mobile, keyboard trace controls, navigation, proposal drafting, no overflow and JS errors using the production static handler and its content security policy. Source ZIP for Relcom excludes Git, internal design notes, CI captures and all secrets.

The MCP hosting draft was prepared through https://resources.relcom.com/mcp but never activated or charged. On 2026-10-27 the owner declined a new subscription and selected the existing IPvX infrastructure for ipvx.org instead. The separate static service in `infra/` binds only to the existing observer's internal address and is published through the normal relcom-infra ingress. See `infra/README.md`. This does not activate a Resources plan or expose the lab controller.

## Contribute

Read RFC-0003 and governance.json. A public proposal and authenticated majority vote are required before admission. The initial electorate contains only the owner; this is bootstrap, not independent community approval. Votes never deploy code or issue credentials. External model code is never executed automatically by a GitHub issue or a vote.

All project RFCs, including RFC-0005, are drafts, not IETF RFCs. The full private lab implementation is separate and is not included in this repository. Evidence snapshots distinguish real measurements from modeling and describe retained failures.

## Content and dependency rights

Original project publications remain attributed to their authors. Font files include their upstream license. Qwen weights are not distributed by this portal; the experiment refers to the official Apache-2.0 model and pinned SHA-256. A general contribution/source licensing policy remains an open governance question; do not assume a license for unrelated upstream work.

## Participant account, blog and history

`account.html` uses the same-origin `/auth/session` endpoint and redirects sign-in and registration to Relcom ID through `/auth/login`. Logout is an ordinary POST to `/auth/logout`; sessions and tokens remain server-side. A plain static preview deliberately cannot authenticate. See the auth service documentation for deployment configuration. Sign-in verifies the browser account/email as returned by Relcom ID; it grants no votes, network membership, AgentID or KYC status. Public proposals and research material remain readable without sign-in.

`blog.html` reads the public Relcom Press latest-article feed using local JavaScript, credentials omitted. It renders titles/excerpts as text and accepts article URLs only on `https://ipvx.press.relcom.org`. Loading, empty and failed states retain the direct blog link. No third-party script or raw article HTML is embedded. CSP must permit only the documented Press feed origin in `connect-src`.

`history.html` is generated from the append-only `history/events.jsonl` and attributed `history/participants.json`. Rebuild after adding a new author record. Draft RFC rows are discovered from the actual `rfc/*.md` files. The measured LLM table/transcripts remain embedded statically by the generator before optional browser refresh.
