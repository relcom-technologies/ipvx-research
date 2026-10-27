---
name: IPvX Research Portal
description: A public reading surface for protocol evidence, demonstrations and draft RFCs.
colors:
  ground: "#f7f6f2"
  surface: "#fff"
  raised: "#f5f5f1"
  ink: "#171916"
  muted: "#62645b"
  rule: "#e8e8e0"
  control: "#c8c9c0"
  active: "#9f8700"
  signal: "#fff9d9"
  positive: "#216340"
  negative: "#a72828"
  focus: "#9b8000"
  hover: "#ecece5"
  primary-hover: "#3b3d35"
  badge-pass-fill: "#e9f3ec"
  badge-warn-fill: "#fff6d8"
  badge-warn-ink: "#735400"
  badge-fail-fill: "#fff0ec"
typography:
  headline:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "clamp(32px, 4vw, 52px)"
    fontWeight: 600
    lineHeight: 1.13
    letterSpacing: "-0.025em"
  section:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  lead:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  navigation:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  code:
    fontFamily: "PlexMono, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  inline-code:
    fontFamily: "PlexMono, monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  surface: "0"
  badge: "4px"
  control: "6px"
  node: "8px"
spacing:
  gap: "8px"
  small: "12px"
  inset: "16px"
  mobile: "20px"
  medium: "24px"
  panel: "28px"
  section: "32px"
  wide: "40px"
  section-block: "48px"
  page: "clamp(16px, 3vw, 48px)"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
  navigation-current:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    typography: "{typography.navigation}"
  proposal-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
    typography: "{typography.body}"
    width: "100%"
  reading-section:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "48px 40px"
  trace-step:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    typography: "{typography.navigation}"
  trace-step-selected:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.ink}"
  badge-neutral:
    backgroundColor: "{colors.raised}"
    textColor: "{colors.muted}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
    typography: "{typography.label}"
  badge-pass:
    backgroundColor: "{colors.badge-pass-fill}"
    textColor: "{colors.positive}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-warn:
    backgroundColor: "{colors.badge-warn-fill}"
    textColor: "{colors.badge-warn-ink}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-fail:
    backgroundColor: "{colors.badge-fail-fill}"
    textColor: "{colors.negative}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
---

# Design System: IPvX Research Portal

## Overview

**Creative North Star: "The Operating Sheet"**

The public portal carries the inherited Operating Sheet identity into a generous reading surface. Warm stone surrounds square white cells; black ink, local Plex type and thin rules support research prose, measurements and source links. Ochre gives the RFC invitation, protocol path and selected explanatory step a restrained signal.

The hierarchy serves comprehension: a clear subject, an early scope disclosure, a protocol explanation, then evidence and draft documents. Russian interface copy is direct and sentence case; source RFCs retain their English text. The metaphor is inherited identity language, not a newly approved visual direction. The implemented portal has no private operating sidebar, launch console or live event journal.

**Key Characteristics:**
- Square white reading cells on a continuous stone ground.
- Readable prose, larger headings and bounded text measures.
- Ink actions, thin rules and restrained ochre emphasis.
- Explanatory protocol steps separated from saved signed evidence.
- Responsive diagrams, charts and evidence tables preserve meaning.

This is a scan of the implemented public portal, refreshed from `assets/portal.css`, `assets/portal.js`, `scripts/build_portal.py` and the generated HTML. The frontmatter owns implemented primitives; `.impeccable/design.json` extends them with responsive behavior, motion and component previews. The surface brief records the Read-mode composition and content boundaries. No formal seeded five-block direction card was supplied; this record does not assert one was approved.

## Colors

Warm, low-chroma stone neutrals support ink; ochre connects protocol explanation and RFC participation without competing with research prose.

### Primary

- **Active ochre** (`active`): directed trace edges, link-underline hover and the IPvX series in comparison charts.
- **Signal wash** (`signal`): the RFC invitation, selected trace-step control, navigation-rail hover, notes and text selection.

### Neutral

- **Stone ground** (`ground`): the continuous page background and narrow gutters between reading cells.
- **White surface** (`surface`): name band, reading sections, trace nodes, publication rows and fields.
- **Quiet supporting wash** (`raised`): scope disclosure, result panel, code blocks and the participation aside.
- **Ink and supporting text** (`ink`, `muted`): the main hierarchy and its metadata, captions and secondary explanations.
- **Rules and control outlines** (`rule`, `control`): thin content dividers and stronger interactive or node boundaries.
- **Interaction tones** (`hover`, `primary-hover`): neutral navigation and secondary hover, and the primary ink action's hover.

Semantic colors are supporting evidence cues: `positive` with `badge-pass-fill` for measured results; `badge-warn-ink` with `badge-warn-fill` for bounded warnings; `negative` with `badge-fail-fill` for failures. Neutral badges use the supporting wash and text. Each carries a readable label. `focus` is the shared keyboard-outline color. Charts reuse the existing ochre/ink/muted roles; they do not add a separate series palette.

**The Active Signal Rule.** Ochre identifies the protocol path, selected explanation and the RFC invitation; primary actions remain ink.

**The Evidence Label Rule.** Keep the textual evidence state and limitation beside semantic color; a measured result is scoped to its experiment.

## Typography

**Reading font:** IBM Plex Sans, served locally as `Plex` in regular (400), medium (500) and semibold (600), with Arial and sans-serif fallbacks.

**Identifier and code font:** IBM Plex Mono, served locally as `PlexMono` at regular weight (400), with monospace fallback.

The pairing retains the inherited technical character while opening the type scale for reading. Body numerals use tabular figures. Headings balance their lines; there is no uppercase decorative label layer. Exported measurement SVGs currently use their own DejaVu Sans-compatible sans-serif stack; they share the portal's color roles and should not be described as Plex artwork.

### Hierarchy

- **Page headline:** the frontmatter `headline` role; it grows from the small-screen size to the wide-screen maximum. At the mobile breakpoint it is explicitly (32px). Its measure is bounded (27ch on inner page titles; 14ch on the mobile index name band).
- **Section heading:** the `section` role, reduced to (24px) on mobile. The trace title is (24px desktop / 22px mobile); the RFC aside title is (24px), and the scope title is a supporting (20px).
- **Subheading:** the `title` role, used for explanatory steps and transcript stages.
- **Body:** the `body` role throughout reading prose, bounded to (74ch). Leads use the `lead` role and a tighter measure (66ch), reduced to (18px) on mobile.
- **Navigation and controls:** the `navigation` role; primary actions remain at the body size with medium weight (500). The wordmark is semibold (29px), with a regular (14px) Research subline.
- **Supporting labels:** the `label` role for badges, captions, table cues and small notes. Mobile experiment-row badges are (12px). These sizes do not replace research prose.
- **Tables and code:** tables use (14px desktop / 13px mobile). Inline identifiers use `inline-code`; wrapped evidence blocks use `code` with the supporting wash and a roomy inset (20px).
- **Diagram labels:** desktop SVG node titles are semibold (20px), descriptions (16px), and public-key ID metadata (12px mono). The intermediary keeps only its name and next-neighbor role, avoiding crowded labels.

**The Reading Scale Rule.** Keep research prose at the body role and reserve compact sizes for navigation, metadata, tables and code.

## Layout

The portal is a static document family of **17 pages**: overview, architecture, experiments, RFC index, publications, participation, governance, reproducibility, five individual RFCs, the saved native exchange, a participant account, research blog and attributed history. All share a normal-flow header and footer; six primary navigation links lead into the research material. This public surface uses no fixed private-app sidebar.

The centered content width is capped (1600px). Page gutters follow the frontmatter `page` token, and the desktop content starts beneath the header with the `gap` spacing. The index uses a twelve-column board: a name band spanning eight columns beside a four-column scope cell; four equal navigation rails below; then an eight-column mechanism cell beside a four-column RFC invitation. Narrow stone gutters connect square tonal cells. The trace and RFC invitation are not floating cards.

Inner pages open with a white title band (56px 40px 40px), followed by white reading sections with the frontmatter insets. Longer prose stays bounded instead of stretching across the full sheet. Section introductions use a narrow heading column and a wider explanation column. Evidence rows, RFC rows and publications use rules and whitespace. The participation page uses a two-column proposal/approval composition with a small gutter. No sticky or pinned reading behavior is implemented.

### Responsive behavior

- **At or below 1050px:** the header wraps and navigation occupies a full row; the source link stays beside the brand. Section side insets reduce (28px); stages become two columns. From (701px) through this width, the mechanism and RFC invitation each span all twelve columns, keeping the diagram readable on tablets.
- **At or below 850px:** the LLM figure selects `assets/llm-comparison-mobile.svg` through a picture source. Its two charts stack vertically with readable labels instead of shrinking the wide two-panel artwork. A written horizontal-scroll cue becomes visible above the result table.
- **At or below 700px:** the board cells stack with insets (24px 20px), the four rails become two columns, and page gutters become (8px). Prose/title/section insets are (32px 20px). Navigation scrolls horizontally in a single row. The footer, stage list and participation sections become one column. RFC and experiment rows rearrange their title, ID, summary and badge across readable rows.
- **Mobile protocol explanation:** the desktop SVG hides and a vertical A → R1 → B sequence appears, with the local model and next-neighbor roles in text. The four step controls become a two-column grid. This is an equivalent explanation, not event replay; the diagram does not claim a selected live route.
- **Mobile evidence table:** the table keeps a minimum width (560px) within a focusable horizontal scroll region; the region has an accessible name, and the cue names the columns to the right. Surrounding prose and the independent comparison figure stay within the page.
- **Long evidence:** code wraps with `overflow-wrap:anywhere` and preserved line breaks. Disclosures expand in document flow; data remains available without automatic fetching.

## Elevation & Depth

There are no box shadows, gradients, blur or floating layers. Stone gutters, white reading cells, supporting washes and thin rules establish depth. The supporting result/code tone is a semantic grouping, not an elevated card.

**The Flat Sheet Rule.** Use tonal surfaces, whitespace and thin rules for structure; do not add shadows to ordinary reading cells or controls.

## Shapes

Reading cells and rows are square. The `control` corner applies to actions, navigation states and fields; `badge` to compact evidence labels; `node` to desktop trace blocks and their mobile counterparts. Boundaries are thin (1px), with slightly stronger diagram-node outlines (1.5px) and directed ochre edges (2px). These restrained corners belong to components rather than to every content section.

## Components

### Actions and navigation

Primary links and buttons are ink with white medium text, the shared control corner, frontmatter padding and a minimum height (46px). Secondary actions are white with a control outline. Plain source/text links retain the readable underline treatment. Navigation uses normal-flow links with minimum targets (44px), a neutral wash on hover and the current page, and semibold current-page text. Current navigation is a wash on mobile too; there is no inherited private-app underline state.

All focusable elements share a visible outline (3px, offset 3px) in `focus`. Disabled buttons lower opacity (0.45). Hover changes are immediate; controls do not move or animate. The skip link appears at keyboard focus.

### Reading cells, source rows and RFC records

White square sections carry long-form material. Scope, participation guidance and result summaries use the quiet wash; the RFC invitation uses the signal wash. Publication rows are full links with a supporting description and an underlined destination. RFC records align a mono ID, semibold title, **Черновик** badge and directional mark; every current RFC is a draft. On mobile these items reflow without hiding the status.

### Protocol explanation and saved exchange

The index and architecture page share an explanatory A → R1 → B SVG, a vertical mobile counterpart, four real button controls and a polite live detail region. Choosing a step changes its pressed state and replaces the heading/explanation immediately. Initial content exists in the HTML. The component explicitly says it is an interactive explanation and links to a separate saved exchange; it has no autoplay, replay timer or launch behavior.

`saved-trace.html` is a real drilldown: saved task, receiver model output, message identifier, delivery timing, a signed-hop/receipt disclosure, a shortened public JSON export and a local signature-verifier download. The public key material is limited to identity/verification-key pins; the export contains audited signed envelopes without a contact roster or internal addresses. Its visible limitation matters: signatures bind the chain to the ciphertext hash, while the displayed plaintext is matched to an owner-collected log; a public decryption proof and independent attestation are not provided.

### Measurement figures, tables and disclosures

The LLM section pairs separate desktop/mobile SVG figures with a static results table, transcript disclosures, a conclusion and limitations. The figure distinguishes short network exchange from model inference; the table preserves exact values. Native and simulated results retain separate headings, evidence labels and source downloads. Hypothesis and transcript details use native disclosure controls with readable summary targets (at least 44px); hypotheses use larger vertical padding (18px).

JavaScript may refresh the measured LLM summary and transcripts from the public JSON. Fetch failure appends a readable note and a direct data link while preserving the built-in result, table, conclusion and limitations. Without JavaScript, static pages and primary navigation remain usable.

### Contribution fields

Labels sit above native input, select and textarea fields. Fields use the control outline/corner, white fill, body type and full available width; the textarea can resize vertically. The form prepares a public GitHub proposal and tells the visitor the external submission boundary. Oversized link content leaves the entered text in place and shows a GitHub-template fallback. The site does not grant access or start a model. The nearby participation/governance text explains strict-majority approval and the one-owner bootstrap electorate.

### Motion and reduced motion

The only authored motion is smooth anchor scrolling. Step changes and disclosure expansion are immediate. Under `prefers-reduced-motion: reduce`, scrolling becomes automatic and CSS animations/transitions are disabled. Directional arrows, labels, source links, focus and the selected step remain understandable without motion.

## Do's and Don'ts

### Do:

- **Do** preserve stone, white, ink and ochre with the shipped Plex faces.
- **Do** keep ordinary-web scope disclosures visible before the protocol explanation on every screen size.
- **Do** distinguish an interactive explanation, a saved exchange, a measurement and a simulation in readable text.
- **Do** preserve static evidence, source links and limitations when JavaScript or data fetching is unavailable.
- **Do** retain the mobile diagram, separate comparison chart, horizontal table cue and visible keyboard focus.
- **Do** keep draft RFC status and the contribution approval boundary visible beside their actions.

### Don't:

- **Don't** copy the private lab's sidebar, compact body scale, launch controls or event replay into this reading portal.
- **Don't** turn primary actions yellow or add decorative color categories, gradients or floating card layers.
- **Don't** make the protocol explanation look like a live exchange or describe the saved trace as independent attestation.
- **Don't** imply that signed ciphertext hashes publicly prove the displayed plaintext without a decryption proof.
- **Don't** replace the mobile chart with a scaled-down desktop chart or hide the evidence table's off-screen columns.


## Participant account, blog and history

The October 27 extension preserves the Read-mode document family. The header groups a canonical account link with the existing source link; research pages remain public. Account details use the existing prose measures and supporting text roles, stack at the mobile breakpoint, and expose loading, anonymous, confirmed, expired, unavailable and retry states. Logout is an ordinary POST form. Verified email is kept distinct from governance membership, legal identity and native AgentID.

The blog uses the existing reading section and publication rhythm. A local script reads a public Press feed with credentials omitted, renders text through DOM text nodes, and permits article links only to the project's platform blog. Empty and failed feeds retain a real destination and explicit recovery. Article titles use the existing trace-title component scale (24px desktop, 22px mobile); the detector's off-ramp advisories for those two literals are intentional reuse of that documented scale. No external script or article HTML is embedded.

The history page renders the attributed append-only journal at build time through native disclosure controls. Summaries preserve author, date precision and proposal/implementation/measurement status. Expanded evidence and limitations remain wrapped and readable. RFC-0005 is a draft proposal; there is no new live routing display or claim of community ratification.
