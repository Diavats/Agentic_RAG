---
name: PRISM
description: A sticker album for answers. Every step and every source is pressed onto the page where you can see it.
colors:
  gum: "#ff9fd0"
  hot: "#ff3d9a"
  ink: "#000000"
  card: "#ffffff"
  sun: "#ffe14d"
  lilac: "#c9b6ff"
  baby: "#a8deff"
  mint: "#7cf5c4"
  live: "#2b3ae0"
typography:
  display:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "clamp(64px, 13vw, 168px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "clamp(44px, 7vw, 84px)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "36px"
    fontWeight: 800
    lineHeight: 1.11
    letterSpacing: "-0.02em"
  lead:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.43
  numeral:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 700
    lineHeight: 1.33
    fontFeature: "tnum"
rounded:
  chip: "6px"
  card: "6px"
  slot: "10px"
  button: "12px"
  sticker: "14px"
  dock: "16px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  section: "64px"
  section-lg: "96px"
components:
  button-primary:
    backgroundColor: "{colors.sun}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 20px"
  button-secondary:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 20px"
  button-send:
    backgroundColor: "{colors.hot}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 20px"
  sticker:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sticker}"
    padding: "8px 16px"
  sticker-question:
    backgroundColor: "{colors.lilac}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sticker}"
    padding: "8px 16px"
  nav-tab:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sticker}"
    padding: "4px 12px"
  nav-tab-active:
    backgroundColor: "{colors.sun}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sticker}"
    padding: "4px 12px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "20px"
  slot-empty:
    textColor: "{colors.ink}"
    rounded: "{rounded.slot}"
    padding: "12px"
    height: "86px"
  citation-chip:
    backgroundColor: "{colors.hot}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chip}"
    padding: "0 4px"
  input-dock:
    backgroundColor: "{colors.sun}"
    rounded: "{rounded.dock}"
    padding: "12px"
  input-field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 12px"
    height: "48px"
---

# Design System: PRISM

## Overview

**Creative North Star: "The Sticker Album"**

Every answer is an album page. The pipeline's five steps are numbered slots; as each streamed stage lands, a glossy sticker presses down into its slot and settles. Sources are stickers you can peel open to read the exact quote. A slot that stays a dashed ghost is the system being honest about what it did not do or did not find. The world is loud on purpose: bubblegum ground, ink outlines, candy fills, hard shadows, a little tilt. It stays legible because reading always happens on white card stock.

The material is printed vinyl on a pink page: thick black die-cut outlines, an inner white rim, a hard offset ink shadow that reads as the sticker standing proud of the paper. Depth is never blurred. Hierarchy comes from shadow length and tilt, not from grey tones. One typeface, Bricolage Grotesque, carries everything from a 168px tilted wordmark to 12px tabular timings.

Motion is physical and short: stickers press in, buttons drop into their own shadow, the drawer slides on a soft spring. The only ambient motion is a handful of outlined prisms drifting in the side gutters of wide screens. Everything that moves is gated by `prefers-reduced-motion`.

**Key Characteristics:**
- Bubblegum pink ground on `<html>`; white only inside cards and inputs.
- 3px ink outline on every sticker, card, button, input and slot.
- Hard offset ink shadows, never blurred; stickers add an inset 3px white die-cut rim.
- Placed stickers tilt between -2deg and +2deg; reading text inside cards never tilts.
- One family (Bricolage Grotesque), weights 400 to 800, tabular figures for every number.
- Carbon blue appears only on the one pipeline step that is running right now.
- Prismo, an inline-SVG prism mascot, is the guide and the loading/error state.

## Colors

Candy pastels on a saturated pink ground, held together by pure black ink.

### Primary
- **Bubblegum Ground** (gum): the page itself, set on `<html>` so the drifting background prisms show through. It is the dominant colour of every screen.
- **Sun Yellow** (sun): primary buttons, the active nav tab, the chat input dock, the active How-it-works step card, table headers in answers, text selection, the "running low" quota badge.

### Secondary
- **Hot Pink** (hot): Prismo's body, citation chips (S1, S2), the send button, the selected search-scope toggle, the verify slot, constellation lines and cited stars on the star chart, and every focus ring.
- **Lilac** (lilac): the visitor's own question sticker, the medical domain stamp, medical stars, the route slot.

### Tertiary
- **Baby Blue** (baby): the Files drawer surface, the Files button, the retrieve slot, the "waking" status pill, table heads on Benchmarks.
- **Mint** (mint): success and "ready", the finance domain stamp, finance stars, the answer slot.
- **Carbon Live Blue** (live): reserved for the single step that is running now (pulsing outline and text). Nothing else may use it.

### Neutral
- **Ink** (ink): all text, every outline, every shadow, the star-chart night sky.
- **Card White** (card): card stock for reading (album pages, popovers, step cards), input fields, unselected tabs and stickers, the die-cut rim.
- **Muted ink**: secondary copy is ink at reduced alpha. On the pink ground the floor is 60% (`ink/60`, about 4.6:1); on white, 60% and up.

### Named Rules
**The Pink Ground Rule.** The page ground is always bubblegum. White is card stock, never the page.

**The One Live Rule.** Carbon blue marks exactly one thing: the step running right now. When nothing is running, it is absent from the screen.

**The Stamp Rule.** Domains keep fixed colours everywhere: medical is lilac, finance is mint, on stamps, stickers and stars alike.

## Typography

**Display Font:** Bricolage Grotesque (with system-ui, sans-serif), loaded once via `next/font` as `--font-bricolage`.

**Character:** A chunky, slightly quirky grotesque with optical sizing; at 800 it reads like printed sticker type, at 400 it is calm enough for long answers.

### Hierarchy
- **Display** (800, clamp(64px, 13vw, 168px), 1): the PRISM wordmark only, set inside a tilted sun sticker.
- **Headline** (800, clamp(44px, 7vw, 84px), 1.05): page titles on How it works and Benchmarks.
- **Title** (800, 36px, about 1.1): section headings; 30px for step-card headings and the drawer title, 24px for card sub-heads.
- **Lead** (600, 20 to 24px): the one-breath intro under a title, max 34 to 62ch.
- **Body** (400, 17px, 1.55): answers and explanations, max 60 to 70ch. Supporting copy commonly steps to 600.
- **Label** (700, 14px): sticker text, slot captions, nav tabs, notes. 12px on status pills.
- **Numeral** (700, 12px, tabular figures): slot numbers (01 to 05), timings, scores. Every number in the product uses `tabular-nums`.

### Named Rules
**The One Family Rule.** Bricolage Grotesque only. Weight and size do the work; no second face, no monospace.

**The Sentence Case Rule.** Headings, buttons and labels are sentence case. No all-caps labels and no label-above-the-heading lines.

## Layout

Content sits in a 1152px column (`max-w-6xl`) with 16px side padding, left-aligned. Chat is the exception: a centred 768px column (`max-w-3xl`) with the input dock stuck 16px above the viewport bottom. Spacing runs on a 4px base, used as 8, 12, 16, 24, 32 and 40px inside components, with 64 to 96px between page sections; headings get more space above than below.

Welcome splits 1.4fr / 1fr at `md` (wordmark and samples left, Prismo right). How it works is a two-column scroll story at `md`: step cards on the left with very tall gaps, the star chart sticky on the right; below `md` the chart pins under the nav and the steps scroll beneath it. Pipeline slots are a 5-across row from 640px and wrap 2-up below. The Files drawer is a 420px right panel from 640px and a bottom sheet (max 85dvh) below. Nav tabs scroll sideways on narrow phones with the scrollbar hidden.

The decorative prisms render only at `xl` (1280px+) and only in the outer 5% gutters, so they never cross text.

## Elevation & Depth

Depth is entirely hard offset ink shadow, used structurally: the longer the shadow, the more the object stands off the page. There is no blur anywhere. Stickers also carry an inset 3px white rim inside their outline, the die-cut edge that makes them read as vinyl rather than a flat box.

### Shadow Vocabulary
- **Sticker rest** (`box-shadow: inset 0 0 0 3px #fff, 4px 4px 0 #000`): every sticker, tab, slot and pill.
- **Sticker lifted** (`box-shadow: inset 0 0 0 3px #fff, 6px 6px 0 #000`): hover on a pressable sticker, plus a 2px up-left lift (fine pointers only).
- **Button** (`box-shadow: 5px 5px 0 #000`): rest; 7px on hover, 1px on press.
- **Dock** (`box-shadow: 6px 6px 0 #000`): the chat input dock.
- **Card** (`box-shadow: 8px 8px 0 #000`): album pages, step cards, popovers, benchmark panels.
- **Hero** (`box-shadow: inset 0 0 0 5px #fff, 10px 10px 0 #000`): the PRISM wordmark only.

### Named Rules
**The No-Blur Rule.** Shadows are solid ink at an offset down and to the right. Never blurred, never grey, never another direction.

**The Press Rule.** Pressing an object shrinks its shadow and moves it the same distance toward the shadow, so it visibly drops into place.

## Shapes

Rounded rectangles in a graduated radius ramp: citation chips and cards are crisp (6px), slots slightly softer (10px), buttons and inputs 12px, stickers 14px, the input dock 16px. Every outline is 3px ink (2px on tiny chips and answer-table cells). Empty states use the same shape as a dashed 3px ghost outline (ink at 40 to 100%) with no fill and no shadow. The recurring silhouette is the triangle prism: Prismo, the background prisms, and the star chart's split beam.

## Components

### Buttons
Tactile and chunky: a button is a yellow block that physically sinks into its shadow.
- **Shape:** gently rounded (12px), 3px ink outline.
- **Primary:** sun fill, ink text at 800, 10px 20px padding, 5px button shadow.
- **Hover / Focus:** fine pointers lift 2px up-left with a 7px shadow; focus shows a 3px hot outline offset 3px.
- **Active:** translate 4px down-right, shadow to 1px, 140ms ease-out.
- **Secondary:** card fill, same everything else. **Send:** hot fill. **Files:** baby fill.
- **Disabled:** card fill, ink at 45%, no lift or press.

### Chips
- **Citation chip:** hot fill, 2px ink outline, 6px radius, 12px at 800, inline with answer text; it opens the matching source.
- **Domain stamp:** a small sticker in lilac (medical) or mint (finance).
- **Status pill / quota badge:** small stickers; baby while waking, mint when ready, card when offline; quota turns sun at 3 or fewer left.

### Cards / Containers
- **Corner Style:** 6px.
- **Background:** card white (the star chart card is ink, a night sky).
- **Shadow Strategy:** Card shadow (8px).
- **Border:** 3px ink.
- **Internal Padding:** 20px, 24px from 640px.

### Inputs / Fields
- **Style:** card fill, 3px ink outline, 12px radius, min height 48px, grows with content up to 160px, weight 600.
- **Focus:** 3px hot outline. Placeholders rotate example questions every 4s.
- **Dock:** the field sits in a sun dock (16px radius, 6px shadow) with Files and Ask buttons either side.

### Navigation
A sticky bar on 90% bubblegum with a light backdrop blur and a 3px ink bottom rule. Left: the PRISM logo as a hot sticker tilted -3deg. Centre: page tabs as stickers, card when idle, sun when current (`aria-current`), lifting on hover. Right: status pill and quota badge, which wrap to their own row on phones.

### Pipeline Slot (signature)
Five numbered slots per answer (route lilac, plan sun, retrieve baby, answer mint, verify hot), each with a fixed tilt between -1.5deg and +1.5deg. Empty: dashed ghost outline, number, what the step will do. Running: carbon blue outline pulsing on a 900ms cycle. Filled: the sticker presses in (220ms, from scale 1.06 and a 7px shadow down to 1 and 4px), showing the result and its real timing. A step that never ran stays dashed and says "Skipped".

### Source Sticker
A card sticker carrying the citation chip, the file name, its kind, and the first eight words of the passage, alternately tilted +/-1.5deg. Opening it pops a card from the sticker's top-left corner (160ms, from scale 0.95 and transparent) with the full passage and its rank and score. When nothing is cited, a dashed ghost sticker says so.

### Files Drawer
A baby blue panel that slides in on transform only: 320ms in, 200ms out, `cubic-bezier(0.32, 0.72, 0, 1)`, over a 30% ink scrim. The drop zone is a dashed card that switches to a sun fill with marching-ants edges while a file is dragged over it. Each file is a pressed-in sticker that moves through checking, confirm topic, indexing (live outline) and ready.

### Prismo
An inline-SVG hot-pink prism with a lilac facet, a hard ink shadow, sun cheeks and five moods: idle and waving bob gently, thinking spins a sun/baby/mint light beam, happy and sorry change the eyes and mouth. Prismo is the loading, empty and error state on every page.

## Do's and Don'ts

### Do:
- **Do** put the bubblegum ground on the page and keep white for card stock, inputs and the die-cut rim.
- **Do** give every sticker, card, button, input and slot a 3px ink outline and a hard ink offset shadow sized to its role (4, 5, 6, 8px).
- **Do** tilt placed stickers between -2deg and +2deg and keep text inside cards straight.
- **Do** press new stickers in with the 220ms `cubic-bezier(0.23, 1, 0.32, 1)` press-in; keep feedback at 140 to 220ms.
- **Do** reserve carbon blue for the one running step, and keep lilac = medical and mint = finance.
- **Do** show what did not happen as a dashed ghost in the same shape, with words saying why.
- **Do** use tabular figures for every number, and gate every movement behind `prefers-reduced-motion` (keep opacity and colour, drop movement).
- **Do** restrict hover lifts to `(hover: hover) and (pointer: fine)`.

### Don't:
- **Don't** use white as a page ground or blurred grey shadows.
- **Don't** use carbon blue for anything that is not running right now.
- **Don't** add a second typeface, monospace labels, all-caps labels or label-above-the-heading lines.
- **Don't** scale popovers from zero; open them from their trigger at 0.95.
- **Don't** let ambient motion near text: background prisms stay in the `xl` gutters only.
- **Don't** set secondary text on the pink ground below 60% ink.
