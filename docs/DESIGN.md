# DESIGN.md

The visual and interaction system: what exists today, the principles for changes, and the direction for Phase 6 (motion site and 3D).

## 1. Current state (as of 2026-10-24)

`frontend/src/index.css` (~1,330 lines) contains **two themes stacked on top of each other**:

1. **Original warm theme** (top of the file): tokens on `:root`
   - `--bg #17130f`, `--panel #1f1a15`, `--panel-border #332c22`
   - `--gold #d4a35a`, `--cream #f0e6d6`, `--text-dim #a89a86`
   - Semantic: `--real #4a9d7f` (green), `--simulated #c47f3a` (amber), `--danger #c05b4d`
2. **Later violet layer** (from about line 1217): **redefines the `:root` tokens**: `--bg #030306`, `--gold #c5a5ff` (lavender, not gold), `--real #80e2c1`, `--simulated #bc9cff` (lavender, not amber), `--danger #ff8caf`. Adds violet radial glows (`rgba(105,68,255,…)`), lavender text accents (`#d9c8ff`, `#bda0ff`), some `!important`. So on screen today "simulated" is lavender and "real" is mint. Always use the tokens, never hardcode these colours.

Type in use: **Instrument Serif** (display headings), **Inter** (body), **DM Mono** (labels, IDs, code), loaded from Google Fonts.

Background: `RevenueNetworkBackground.jsx` draws a rotating gold coin with a **"$"** on a full-screen canvas, with three blur filters every frame, on every page.

Problems to fix in Phase 6:
- Two competing palettes; tokens no longer describe what's on screen.
- "$" coin on an INR product.
- The background costs a lot per frame and keeps running when reduced motion hides it.
- Several cards imitate live data that isn't live (see `RULES.md` §1).

## 2. Principles

1. **Evidence first.** The design serves the real-vs-simulated story. Real data is visually distinct (green, solid); simulated is visually distinct (amber, dashed or hatched); the two never share a card.
2. **Calm fintech, not casino.** Precise, legible, trustworthy. Motion explains state changes; it doesn't decorate.
3. **One system.** Every colour and size comes from tokens.
4. **Accessible by default.** WCAG AA contrast, visible focus, keyboard operable, reduced motion respected.
5. **Fast.** Animation stays on the GPU-friendly properties (`transform`, `opacity`); heavy effects have a static fallback.
6. **Indian context.** ₹ and `en-IN` number formatting throughout.

## 3. Semantic colours (keep regardless of theme)

| Meaning | Token | Use |
|---|---|---|
| Real (Razorpay returned it) | `--real` | Live demo results, real order counts, "verified" states |
| Simulated (model output) | `--simulated` | Batch outcomes, projected amounts |
| Danger / blocked | `--danger` | Failures, fraud holds, errors |
| Accent | `--gold` (or the chosen accent) | Primary actions, highlights |

## 4. Components (inventory)

- Navigation bar with route and scroll links (`Landing.jsx`)
- Hero: title, subtitle, CTAs, provenance chips
- Cards: `HeroTransactionVisual`, `RecoveryEventCard`, `AgentActivityFeed`, `AuditTrailVisual` (to be made truthful, P3-2)
- `AgentJourney`: six-step control board
- `HeadlineMetrics`: four metric tiles (to be fed by real data, P3-1)
- Compare cards: real vs simulated
- Dashboard: provenance banner, metric grids, breakdown table, results table with expandable audit trail
- Live demo: staged panels with test-card instructions

## 5. Phase 6 direction: motion site and 3D

To be designed in detail at P6-1/P6-2/P6-3; these are the constraints.

**Motion**
- Scroll-driven storytelling of one payment's journey: failure → diagnosis → safety gate → recovery → verification, mirroring the agent's real steps.
- Each animated section has a reduced-motion version that shows the end state statically.
- Prefer CSS and small libraries; justify any animation library in `MEMORY.md`.

**3D**
- One centrepiece that represents the product honestly (e.g. a payment flowing through the agent's gates, or a ₹ token passing a safety gate), replacing the "$" coin.
- Performance budget: loads lazily, under ~200 KB extra JS gzipped, holds 60 fps on a mid-range laptop, pauses when off-screen or tab hidden, static image fallback for no-WebGL and reduced motion.
- No fake data in the 3D scene either: if it shows numbers, they come from the API or are labelled as an example.

## 6. Decisions log

| Date | Decision |
|---|---|
| 2026-10-24 | Keep the real / simulated / danger semantic colours whatever the final theme. |
| 2026-10-24 | Motion and 3D work waits until Phases 1–5 are done. |
