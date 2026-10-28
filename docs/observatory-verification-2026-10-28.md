# Observatory implementation verification — 2026-10-28

Author and recorder: Codex assistant. Base for this work:
`56d68c1f7e6c3e3baae5637f1c0d93d49a4cd388` (the language-editions
branch). This is a verification of the portal presentation, not a new experiment.

- The portal's 51 Python checks and 5 native-wire checks passed in a temporary
  environment with the pinned authentication dependencies. An initial attempt
  with the system Python failed because the dependencies were absent and the
  sandbox prevented loopback listeners; the successful rerun used the pinned
  dependencies and permitted local listeners.
- The observatory browser check passed 12 combinations: four languages and
  1440, 768 and 390 CSS pixels. It checked the four tasks, their stages,
  recorded message IDs, node disclosure, deep links, original text, reduced
  motion and no-JavaScript access. The language browser check passed 72 page
  states and three RFC editions without JavaScript.
- Site validation checked 88 static pages, links, JSON and public-data
  boundaries; language validation checked 2,031 source entries in three
  translations; history validation checked 106 attributed events.
- Review in a real browser identified no blocking design findings. Warnings about
  the existing site-wide palette, page length, selected border and header margin
  remain outside this change.

Limits: public data are sanitized projections, not original private captures.
The previous run did not record a cross-host causal task ID, per-hop timings,
queue waiting time, route-selection rationale, or collector losses. The
interface says so explicitly. The two transports share application hops; these
samples do not establish an Internet-wide latency advantage. The translation
editions have not received independent human linguistic review. Publishing this
work remains subject to the repository's review and release gates.
