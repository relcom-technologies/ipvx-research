---
name: IPvX Agent Lab
description: A quiet operating sheet for observable agent experiments and their evidence.
colors:
  ground: "#f7f6f2"
  surface: "#fff"
  raised: "#f5f5f1"
  ink: "#171916"
  muted: "#62645b"
  rule: "#e8e8e0"
  control: "#c8c9c0"
  signal-active: "#9f8700"
  signal-fill: "#fff9d9"
  signal-border: "#b99c00"
  positive: "#216340"
  negative: "#a72828"
  error-fill: "#fff1ee"
  button-hover: "#ecece5"
  primary-hover: "#3b3d35"
  nav-active: "#eeede5"
  event-selected: "#f5f4eb"
  focus: "#9b8000"
  graph-edge: "#b4b8aa"
  graph-border: "#d5d8cd"
  notice-bg: "#fff9d8"
  notice-ink: "#654e00"
  notice-error-bg: "#fff0ed"
  notice-error-ink: "#882424"
  badge-neutral-bg: "#efefea"
  badge-neutral-ink: "#55584c"
  badge-pass-bg: "#e9f3ec"
  badge-partial-bg: "#fff6d8"
  badge-partial-ink: "#735400"
  badge-fail-bg: "#fff0ec"
  badge-fail-ink: "#a02525"
  badge-running-bg: "#f5edbb"
  badge-running-ink: "#6b5700"
typography:
  headline:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.25
  body:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
  event-title:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.5
  graph-title:
    fontFamily: "Plex, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 500
  code:
    fontFamily: "PlexMono, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.65
rounded:
  row: "0"
  badge: "4px"
  control: "6px"
  graph-node: "8px"
  sheet: "16px"
spacing:
  compact: "4px"
  tight: "8px"
  small: "12px"
  inset: "16px"
  medium: "20px"
  gap: "24px"
  sheet: "28px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  button-quiet:
    rounded: "{rounded.control}"
    padding: "8px 14px"
    textColor: "{colors.ink}"
  navigation-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  scenario-select:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  sheet:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.sheet}"
    padding: "28px 28px 16px"
  event-selected:
    backgroundColor: "{colors.event-selected}"
    rounded: "{rounded.row}"
    padding: "10px 8px"
  verdict-pass:
    backgroundColor: "{colors.badge-pass-bg}"
    textColor: "{colors.positive}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  verdict-partial:
    backgroundColor: "{colors.badge-partial-bg}"
    textColor: "{colors.badge-partial-ink}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  verdict-fail:
    backgroundColor: "{colors.badge-fail-bg}"
    textColor: "{colors.badge-fail-ink}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  verdict-not-run:
    backgroundColor: "{colors.badge-neutral-bg}"
    textColor: "{colors.badge-neutral-ink}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  verdict-running:
    backgroundColor: "{colors.badge-running-bg}"
    textColor: "{colors.badge-running-ink}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
---

# Design System: IPvX Agent Lab

## Overview

**Creative North Star: "The Operating Sheet"**

The interface is a calm, code-led operating surface for a founder or engineer examining an experiment. A tinted stone shell surrounds a white sheet. Black ink, compact Plex typography and thin rules make the action, event sequence and evidence readable without decorative imagery or raised dashboard tiles.

The system gives observations a visible hierarchy: an experiment action, a brief truth disclosure, participants, an explanation, then detailed evidence. Russian interface text is direct and sentence case; identifiers and protocol examples keep their technical spelling. The disclosure that data is synthetic, there is one operator and no language model remains visible in the primary screen on small displays as well as large ones.

**Key Characteristics:**
- Flat white working surface within a tinted L-shaped shell.
- Ink actions, quiet neutral structure and restrained state color.
- Separate text weights, tabular numerals and monospace identifiers.
- Event selection connects the journal, participants and evidence.
- Responsive reflow preserves the meaning of the selected event.

Source of truth: `src/ipvx_agent_lab/static/style.css`, `index.html` and `app.js`. The frontmatter records implemented primitives; the sidecar extends it with states, motion and responsive behavior. The review captures at 1440, 768 and 390 pixels show this same visual world.

## Colors

Warm, low-chroma stone neutrals support black ink; ochre yellow marks selected activity and run feedback. Green and red communicate observed outcomes.

### Primary

- **Active signal** (`signal-active`): selected directed route, range control, the small brand separator and the mobile navigation underline.
- **Selected participant wash and stroke** (`signal-fill`, `signal-border`): the two participants of a selected event, shared by desktop graph nodes and mobile participant cells.
- **Run feedback wash and ink** (`notice-bg`, `notice-ink`): readable notices about starting, running or completed experiments.

### Neutral

- **Stone ground** (`ground`): the page, sidebar and topbar form one continuous shell.
- **White sheet** (`surface`): the main frame, graph nodes, scenario control and secondary actions.
- **Quiet raised tone** (`raised`): code and evidence blocks; this is tonal separation rather than elevation.
- **Ink and supporting text** (`ink`, `muted`): headings/actions and explanatory/metadata text respectively.
- **Rules and control outlines** (`rule`, `control`): section dividers and interactive boundaries. Graph nodes use their own lighter `graph-border`; inactive links use `graph-edge`.
- **Neutral interaction washes** (`button-hover`, `nav-active`, `event-selected`): pointer hover, current section and selected journal row.

Outcome colors are semantic: `positive` and `badge-pass-bg` for checked results; the partial family for limited evidence; the fail family and error family for failure/refusal; the neutral badge family for untested hypotheses; the running family for checks in progress. Each state also carries a text label.

**The Active Signal Rule.** Yellow carries selection and run feedback; the experiment action stays ink. Preserve the small identity and active-navigation uses already present.

**The Evidence Label Rule.** Never communicate a verdict through color alone: retain its Russian label and its supporting checks or limitations.

## Typography

**Interface font:** IBM Plex Sans, loaded locally under the CSS family `Plex`, with Arial and sans-serif fallbacks. The build ships separate normal-style files for regular (400), medium (500) and semibold (600); match the requested weight to its file.

**Identifier and code font:** IBM Plex Mono, loaded locally as `PlexMono`, with monospace fallback at regular weight (400).

The pairing is technical but readable. Sans handles Russian prose, actions and labels; mono marks code, event numbers and hypothesis identifiers. All interface numerals use tabular figures. There is no oversized display face or forced uppercase label layer.

### Hierarchy

- **Headline:** the frontmatter `headline` role; mobile uses the observed smaller size (23px).
- **Section title:** the `title` role. Inspector titles keep the same size and weight with a more open line height (1.4).
- **Body:** the `body` role. Inspector explanations use a smaller, more open treatment (13px / 1.7); longer protocol/library prose uses body size with line height (1.8).
- **Event title:** the `event-title` role; graph participant names use `graph-title`, with supporting graph text at regular weight (12px).
- **Metadata:** `label` is the common supporting role. Event metadata, badges and the footer use the observed compact size (11px); keep this use confined to metadata and short state labels.
- **Code:** the `code` role. Inline code is slightly larger (13px); expanded event payloads use the compact evidence size (11px).

Body measures are bounded where the content needs it: primary introduction (69ch), hypothesis explanations (75ch), and protocol/library pages (80ch).

**The Weight File Rule.** Use the shipped 400, 500 and 600 Plex Sans faces for regular copy, medium actions/event titles and semibold headings/current navigation. Keep identifiers in Plex Mono.

## Layout

The desktop shell is L-shaped: a fixed left sidebar (228px) and a topbar (48px) share the stone ground. The white sheet starts beside the sidebar, leaves a narrow exterior gutter (8px), has a thin border and rounded outer corners. Its inner inset is the frontmatter `sheet` spacing, with a smaller bottom inset.

The operating view uses a flexible main column and a fixed evidence rail (275px). The graph and inspector share one ruled workspace rather than separate cards. A playback strip follows it. The journal and result area repeat the two-column relationship below with the `gap` spacing. The event list scrolls within a bounded region (345px maximum); payload evidence has its own scroll limit (250px).

Spacing follows the observed compact-to-section steps in the frontmatter. Small gaps separate related controls and metadata; the larger steps separate work areas. Use alignment and thin rules to group information, rather than giving every group its own rounded panel.

### Responsive behavior

- **At or below 1250px:** the page header wraps; scenario selection and the action form a full-width horizontal row. The evidence rail narrows (235px), and the replay-mode caption hides.
- **At or below 960px:** the sidebar narrows (180px), the sheet inset becomes (24px 20px), the topbar's descriptive sentence hides, and health remains. The inspector stacks below the graph with a top rule; journal/results become one column. Playback may wrap.
- **At or below 600px:** the sidebar becomes a normal-flow header with horizontally scrollable navigation. The active section uses an underline. The topbar becomes a compact health row (34px). The sheet becomes edge-to-edge, square and borderless with side insets (16px); the launch controls stack, with a primary action at least (46px) high. Reports wrap below the run label.
- **Mobile event view:** the SVG is replaced by a directed source → target label and a two-column participant grid. The selected source and target receive the same wash/stroke states as desktop nodes; an error target receives the error state. The synthetic-data/one-operator/no-model disclosure remains above the launch controls.

## Elevation & Depth

The system has no box shadows, blur, gradients or floating card layers. Depth comes from the stone shell, white sheet, subtle code wash and thin separators. The main sheet is the one enclosing frame; internal sections use borders and whitespace.

**The Flat Sheet Rule.** Preserve tonal layers and rules as the depth vocabulary; do not add shadows to ordinary controls, journal rows or evidence panels.

## Shapes

Corners are restrained and role-specific: the main frame uses `sheet`, graph participants use `graph-node`, controls/notices/code/mobile participants use `control`, and verdict badges use `badge`. Journal rows remain square with a bottom divider. Mobile removes the outer sheet's corner treatment.

Thin strokes are the default boundary (1px). Selected desktop graph nodes increase their stroke (1.5px), and the selected route is stronger (3px). The moved endpoint has a dashed outline; its identity comes from the label and dashed edge rather than a new color family.

## Components

### Buttons

Plain, compact and legible. The primary action uses ink with white text, medium weight, a modest corner and the frontmatter padding. Its hover changes to `primary-hover`. Secondary actions are white with a control outline; quiet actions retain a transparent background. Shared enabled hover uses `button-hover`; the primary has its own override. Text actions are underlined rather than boxed.

Controls have a minimum target height (44px). Disabled buttons lower opacity (0.45) and use the unavailable cursor. All keyboard-focused elements receive the same visible outline (3px, offset 3px) in `focus`. There is no animated button movement or fabricated pressed transform.

### Scenario selection and connection state

Use the native select: white fill, control outline, control corner and inset horizontal padding. It is (40px) high on wide desktop and (44px) at narrower widths. Its label is available to assistive technology.

The launch action is available only when the shared availability state allows it: no pending launch request, no running experiment, and all health-reported nodes connected. Connection health stays in the topbar as status text. Running, completed, failed/interrupted and unavailable states also have readable run/notice copy; do not substitute a decorative status dot for that text.

### Navigation

The desktop navigation is a quiet vertical list: muted defaults, ink semibold current item, neutral selected wash, and a small count beside hypotheses. On mobile, labels form one horizontal row; counts and the bottom sidebar disclosure hide while the primary screen's brief disclosure remains. The active item loses the desktop wash and receives the signal underline.

### Participant graph and mobile counterpart

The graph is an SVG with white, gently rounded participant blocks, orthogonal directed routes and an evidence inspector. The inactive network remains subdued. Selecting an event highlights its source and target and draws the matching ordered route; reverse routes have their own geometry and arrow direction. The inspector title, explanation, source → target metadata and optional payload all refer to the same selected event.

The mobile route label and participant cells are driven by that same event selection. Keep participant highlighting synchronized with desktop and retain an error target's red treatment. The static grid is a representation of participants, not a replay independent from the event journal.

The selected route uses a dashed moving stroke (1s, linear, infinite; dash pattern 8 / 5; offset travels to −26). Route stroke changes have a brief transition (0.18s). Under `prefers-reduced-motion: reduce`, all CSS animations and transitions stop. The selected color, arrow direction, participant states and event text remain. Replay still advances discrete saved events; reduced motion does not disable it.

### Journal and replay

Journal entries are full-width button rows: mono sequence number, medium-weight title, smaller source/target metadata and a textual fact/refusal status. The selected row has `event-selected` wash. Each row is at least (56px) high and divided from the next by a thin rule.

Replay, previous/next and the range control select persisted events. Replay advances at (1300ms) intervals and may be paused; manual navigation exits automatic following. The first/last bounds disable the corresponding arrow. Empty journals keep the controls disabled and show an explanatory empty state. The interface distinguishes the live journal label from replay of saved events.

### Verdicts and evidence disclosure

Badges are compact rectangular labels with the `badge` corner, short padding and no interaction implied. Their meaning is scoped to the current run:

- **Проверено / pass:** the implemented checks for this hypothesis passed in this run; this is not an unrestricted protocol certification.
- **Частично / partial:** checks produced evidence but a stated limitation remains. Keep that limitation visible when the hypothesis opens.
- **Не прошло / fail:** a check or the hypothesis execution failed. Show the failed check or error evidence.
- **Не проверено / not_run:** this run did not test the hypothesis. Preserve the reason rather than implying failure or success.
- **Проверяем… / running:** the hypothesis is currently being evaluated; no final conclusion yet.

Hypotheses use ruled disclosure rows with a mono ID, medium title and badge. Opening a row reveals expectation, checks, limitations and optional measurements. Summaries keep a minimum target height (44px; hypothesis summaries 64px). Payload/code blocks wrap long values and may scroll vertically. Notices use a soft run-feedback wash or error wash with readable text and status semantics.

## Do's and Don'ts

### Do:

- **Do** keep the stone shell, white sheet and ink hierarchy consistent across views.
- **Do** preserve the brief truth disclosure on desktop and mobile.
- **Do** connect the selected journal event to its ordered route, participants and evidence.
- **Do** retain text labels and limitations beside semantic verdict colors.
- **Do** use the shipped Plex weights and tabular figures, with mono for identifiers and code.
- **Do** keep keyboard focus visible and preserve selected-event meaning with reduced motion.

### Don't:

- **Don't** turn the primary experiment action yellow or add decorative color categories.
- **Don't** add ordinary card shadows, gradients or floating glass layers to the flat sheet system.
- **Don't** make a replay look like new network activity or present a stored event as a prewritten result.
- **Don't** label partial or untested hypotheses as passed.
- **Don't** hide the mobile participants' selected/error states or reduce the mobile graph to an unchanging process list.
