# PRISM frontend: structure, layout and design rules

The direction is **Sticker Album** (ADR-001, `.impeccable/surfaces/frontend.md`).
Every answer is an album page: numbered pipeline slots and source stickers
press in as the answer streams. Emil Kowalski's motion rules apply to every
interaction.

---

## 1. Colour

| Token | Hex | Role |
|---|---|---|
| `--gum` | `#FF9FD0` | **Bubblegum pink: the page ground everywhere.** Dominant colour. Never white |
| `--hot` | `#FF3D9A` | Prismo's body, citation stickers [S1], focus rings |
| `--ink` | `#000000` | Text, every 3px outline, every hard shadow |
| `--card` | `#FFFFFF` | Inside cards only (answers, inputs), so long text stays readable |
| `--sun` | `#FFE14D` | Primary buttons, the active tab |
| `--lilac` | `#C9B6FF` | Your questions, the **medical** stamp |
| `--baby` | `#A8DEFF` | **Baby blue:** the Files drawer, "retrieve" slot, info notes |
| `--mint` | `#7CF5C4` | Success, the **finance** stamp |
| `--live` | `#2B3AE0` | Reserved: the one pipeline step still running. Nothing else uses it |

Contrast: black on every fill above passes WCAG AA. White text is used only on `--live`.

## 2. Type

One family: **Bricolage Grotesque** (variable: weight 400–800, optical size).
- Display: 800, tight tracking, set large and tilted like a sticker.
- Body: 400/500, 17px, line-height 1.55, line length ≤ 70 characters.
- Numbers in slots: 800, tabular figures.
- Sentence case everywhere. No all-caps labels, no monospace labels, no "→" on buttons.

## 3. Shape and depth

- Outline: `3px solid --ink` on every sticker, card, button and input.
- Shadow: hard offset `5px 5px 0 --ink` (stickers 4px, big cards 8px). Never blurred grey shadows.
- Radius: stickers 14px; slots and cards 6px. Hierarchy shows through tilt and shadow, not one radius for everything.
- Tilt: placed stickers sit at −2° to +2°. Text inside cards is never tilted.

## 4. Pages (tabs)

The nav is a row of sticker tabs, with the PRISM sticker logo on the left and the server status + today's quota on the right.

| Tab | Route | Heading | What's on it |
|---|---|---|---|
| Welcome | `/` | "Hi, I'm Prismo." | Big PRISM wordmark sticker; Prismo waving; 3 sample-question stickers (click = ask); a "Start chatting" button; what I can read (finance, medical; CSV, Excel, Word) |
| Chat | `/chat` | (none; the conversation is the page) | Album pages (one per question); input dock; Files drawer |
| How it works | `/how-it-works` | "How I find an answer" | Scroll story: Prismo walks 5 steps; sticky Star Atlas chart animates each step; "What I can't do" |
| Benchmarks | `/benchmarks` | "How well it works" | Live numbers from `GET /benchmark`; honest notes, n=11 caveat, unvalidated judge |

## 5. Layout

```
WELCOME (desktop)                              CHAT
+--------------------------------------------+ +-------------------------------------+
| [PRISM] [Welcome][Chat][How][Bench]  ●ready| | nav                                 |
|                                            | |      +--------- album page -------+ |
|  PRISM  (giant tilted sticker)   /\ Prismo | |      | [your question sticker]    | |
|                                 /  \ "Hi!" | |      | (01)(02)(03)(04)(05) slots | |
|  I read finance and medical files and      | |      | answer text  [S1] [S2]     | |
|  show you exactly where each answer        | |      | source stickers shelf      | |
|  came from.                                | |      +----------------------------+ |
|  [sample q][sample q][sample q]            | |                       [My files 2]  |
|  [Start chatting]                          | | [ask about your files...   ][Ask]  |
+--------------------------------------------+ +-------------------------------------+
```
- Content is **left-aligned**; only the Chat column is centred (max 760px).
- One spacing scale: 4, 8, 12, 16, 24, 32, 48, 72px. More space above a heading than below it.
- Mobile (<720px): nav tabs scroll horizontally; slots wrap 3+2; the Files drawer becomes a bottom sheet.

## 6. Components

| Component | Job | Key states |
|---|---|---|
| `Prismo` | The guide (inline SVG) | idle (slow bob), thinking (spins its facet), happy, sorry, waving |
| `Sticker` | Base look: outline, shadow, tilt | resting, hover lift (pointer devices only), pressed 0.97 |
| `Slot` | One numbered pipeline step | empty (dashed ghost + number), live (`--live` outline), filled (sticker pressed in + timing), skipped (stays dashed, says why) |
| `AlbumPage` | One question and its answer | streaming, done, error, refused (quota) |
| `SourceSticker` | One citation | collapsed (file, section); open: popover with the exact chunk text and score |
| `FilesDrawer` | Uploads | dropzone; checking ("finance or medical?"); domain stamp + switch; indexing; ready; refused with reason; expiry countdown |
| `StatusPill` | Is the backend awake? | waking (Prismo yawns, about 1 min), ready, offline |
| `QuotaBadge` | Questions/uploads left today | normal; last few (sun); none left (explains tomorrow) |
| `StarChart` | How it works visual | one state per step; star radius = real hybrid score |

## 7. Motion (Emil rules)

- **Signature:** a sticker pressing into its slot as each streamed stage lands: `scale(1.06)` to `1`, shadow 6px to 4px, 220ms `cubic-bezier(0.23,1,0.32,1)`.
- Buttons: `:active` scale 0.97, 140ms ease-out. Hover lift only under `(hover:hover) and (pointer:fine)`.
- Drawer: transform only, 320ms `cubic-bezier(0.32,0.72,0,1)`; exit faster (200ms).
- Popovers scale from their trigger (`transform-origin` at the sticker), from 0.95 + opacity 0, never from 0.
- Background: tiny outlined prisms drifting very slowly across the pink (CSS, transform only). The only ambient motion.
- Welcome: one orchestrated entrance (stickers stagger 60ms, once). No per-section fade-ups.
- Typing in the input and keyboard shortcuts: no animation.
- `prefers-reduced-motion`: drift, bob and tilt-in removed; opacity/colour changes kept.

## 8. Words

- Prismo speaks in the first person, short and plain: "I'm checking whether this is finance or medical…"
- Buttons say what happens: "Ask", "Upload file", "Use finance instead", "Clear my files".
- Errors say what happened and what to do: "That file has 40 rows; I can read 25. Trim it and try again."
- Every answer carries the line: "Not medical or financial advice."
- Never invent numbers. The Benchmarks and How it works charts use real data (live API, or a real recorded trace, labelled as such).

## 9. Code rules (ponytail)

- Next.js App Router + TypeScript + Tailwind; **no UI kit, no animation library**: CSS transitions/keyframes and WAAPI cover everything here.
- Fewest files: one component per file in `frontend/components/`, one API client `frontend/lib/api.ts`.
- Every block of code has a one-line plain-English comment saying what it does.
- The backend URL comes from `NEXT_PUBLIC_API_URL`; it is never hardcoded in components.
