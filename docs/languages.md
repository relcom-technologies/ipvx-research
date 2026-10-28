# Portal language editions

The owner requested English, German and Spanish versions, including every draft
RFC and the attributed project history, with originals alongside. Russian remains
the canonical portal source. The English RFC sources and original actor records
remain canonical in their original languages; a translation does not replace a
record, prove attribution, change a vote or ratify a draft.

The portal builds flat, static sibling URLs, such as `index.en.html`,
`rfc-0006.de.html` and `history.es.html`. This preserves the existing scoped
`/*.html` ingress allowance. Language links work without JavaScript. A small
optional enhancement carries the current fragment to the selected language;
there is no automatic browser-language redirect or third-party translation call.

Each translated page declares its language, canonical URL and four `hreflang`
alternates. RFC prose and every history entry include a disclosure with the
original text. Editorial translations are visibly identified. Raw signed proof
objects, code, keys, model JSON, measurements and original downloadable evidence
are unchanged. User comments, names and live moderation text are displayed as
submitted, never translated by the browser. Relcom ID and Press are separate
services; this change does not alter their provider interfaces or OAuth settings.

## Rebuild

1. Update owned Russian editorial source or RFC/history documents normally.
2. If a JavaScript source changed, run `npm ci --prefix i18n --ignore-scripts`, then
   `node scripts/extract_js_i18n.mjs`. Acorn is pinned for this build-time extraction.
3. Run `python3 scripts/build_portal.py --source-only`, then
   `python3 scripts/i18n_sources.py` to collect
   exact editorial strings. Keys are SHA-256 prefixes of trimmed source text.
4. Translate each new source key in `i18n/en.json`, `de.json` and `es.json`.
   Preserve dates, revision hashes, evidence identities, failed results and all
   qualifications. Translation values are text, never executable markup.
5. Rebuild public bundles and pages with the normal scripts. `build_portal.py`
   also builds the language editions. Missing translations or stale JS spans stop
   the build; no silent Russian fallback is allowed.
6. Run `check_languages.py`, normal site/history checks and the browser scenarios.

Source code and translation catalogs are reviewable in Git; only generated HTML,
CSS, JavaScript and explicit public data enter the static export. The original
history archive remains authoritative and is not silently rewritten into another
language. Publication uses the existing reviewed source pin and scoped CI path;
prior one-time review exceptions grant no permission for this release.
