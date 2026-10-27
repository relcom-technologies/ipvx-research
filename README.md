# IPvX Research

Public research and draft RFC portal for IPvX. Static HTML/CSS/JavaScript, local IBM Plex fonts, public sanitized evidence snapshots. The portal itself uses ordinary IP/DNS/HTTPS; experimental native Ethernet delivery is a separate lab.

## Run

Python 3: `python3 -m http.server 8091 --bind 127.0.0.1`, then open http://127.0.0.1:8091/ . No npm, server secrets or private database. Rebuild owned page sources with `python3 scripts/build_portal.py`.

## Checks

`python3 -m unittest discover -s scripts -p 'test_*.py'`

`python3 scripts/check_site.py`

Browser CI checks desktop/tablet/mobile, keyboard trace controls, navigation, proposal drafting, no overflow and JS errors. Source ZIP for Relcom excludes Git, internal design notes, CI captures and all secrets. Hosting is prepared through https://resources.relcom.com/mcp and activated in the customer cabinet. A custom domain requires the provider's paid capability; no automatic charge is authorized by this repository.

## Contribute

Read RFC-0003 and governance.json. A public proposal and authenticated majority vote are required before admission. The initial electorate contains only the owner; this is bootstrap, not independent community approval. Votes never deploy code or issue credentials. External model code is never executed automatically by a GitHub issue or a vote.

All four initial RFCs are drafts, not IETF RFCs. The full private lab implementation is separate and is not included in this repository. Evidence snapshots distinguish real measurements from modeling and describe retained failures.

## Content and dependency rights

Original project publications remain attributed to their authors. Font files include their upstream license. Qwen weights are not distributed by this portal; the experiment refers to the official Apache-2.0 model and pinned SHA-256. A general contribution/source licensing policy remains an open governance question; do not assume a license for unrelated upstream work.
