# DESIGN.md

The visual and interaction system. Sections 1–3 are the system as built in Phase 6; section 7 records what it replaced.

## 1. Brief

- **Subject:** a rule-based agent that handles failed Razorpay payments: it reads the real error, picks an action from a fixed policy, runs it past a safety gate and records every step.
- **Audience:** engineers and hiring managers looking at a fintech portfolio piece. They are sceptical of demo theatre.
- **The page's one job:** show one real recorded case end to end, make the real-vs-simulated line impossible to miss, and send people to run the live demo.

## 2. Design system (P6-1)

### Signature: the recorded case is a printed receipt

The hero is a point-of-sale printer slot. The recorded case (from `/api/showcase/case`, never invented) feeds out of it as a thermal receipt: amount, order, failure, action, gate, outcome. It ends with a rubber stamp whose **ink is the provenance**:

| Stamp | Ink | When |
|---|---|---|
| `CAPTURED · VERIFIED` | real green | live demo, Razorpay reported the recovery payment captured |
| `NOT RECOVERED` | danger red | live demo, recovery attempts failed |
| `HELD` | danger red | safety gate blocked the case |
| `SIMULATED` (hatched) | simulated amber | batch record: synthetic failure, simulated outcome |

The receipt vocabulary (monospace lines, dotted leaders, perforations, stamps) carries through the page: the evaluation is a statement, the audit trail is a tape. Everything else stays quiet so the receipt is the one memorable thing.

### Palette

| Token | Hex | Use |
|---|---|---|
| `--carbon` | `#111214` | Page background |
| `--graphite` | `#1A1C20` | Surfaces (panels, cards) |
| `--rule` | `#2B2E35` | Borders, dividers |
| `--paper` | `#EEECE6` | Thermal paper; primary buttons |
| `--ink` | `#26252C` | Print on paper |
| `--ink-faded` | `#5E5C65` | Secondary print on paper |
| `--text` / `--text-dim` | `#E9E7E2` / `#A3A3AB` | Text on dark |
| `--real` | `#63C99A` | Real, on dark |
| `--simulated` | `#E3A653` | Simulated, on dark |
| `--danger` | `#EC7B6F` | Failure / blocked, on dark |
| `--stamp-real` / `--stamp-sim` / `--stamp-danger` | `#1B6E48` / `#87530F` / `#A8392F` | The same meanings, on paper (stamps and small tape text) |
| `--signal` | `#93B4FF` (`#3D63D6` on paper) | Links and the focus ring |

Contrast (WCAG): text 15.2, dim 7.5 (6.8 on graphite), semantic-on-dark 6.2–8.4, ink on paper 12.9; faded ink and the three paper inks ≥ 4.5 even on the receipt's shaded top (`#DEDCD4`), because they're also used for small text on the tape. axe-core (WCAG 2 A/AA) reports no violations on any page.

There are no gradients, glows or glass. Depth comes from the 3D printer and plain shadows.

### Type

| Role | Face | Setting |
|---|---|---|
| Display | **Archivo**, width 118–125, weight 780 | h1 and section titles only; tight tracking. Reads like a bank-statement header |
| Body | **Archivo**, width 100, weight 400/600 | Everything else (one variable font file for both roles) |
| Data / receipt | **Martian Mono** | Width 75 on the receipt and tape (condensed, like thermal print); width 100 for ids, labels, numbers |

Scale (rem): 0.75 · 0.875 · 1 · 1.125 · 1.375 · 1.75 · 2.5 · clamp(2.6, 5.4vw, 4.6) for h1. Numbers use `en-IN` grouping and ₹.

### Layout

```
nav  RECOVER ·························· How it works · Evaluation · Audit tape   [Run the live demo]

hero  eyebrow                              ┌───────── printer ─────────┐
      Failed payments,                     │ ▓▓▓▓▓▓▓▓ slot ▓▓▓▓▓▓▓▓▓▓▓ │
      recovered on the record.             └──┬─────────────────────┬──┘
      one paragraph                           │ RECORDED CASE · time │
      [Run the live demo] [See evaluation]    │ AMOUNT ····· ₹2,499  │
      ● health chip                           │ FAILURE  …           │
                                              │      [ STAMP ]       │
                                              └╲╱╲╱╲╱ tear ╲╱╲╱╲╱╲╱──┘
evidence   two slips side by side: REAL (solid edge) | SIMULATED (hatched edge)
statement  the 500-seed evaluation as ledger rows with dotted leaders + the note
how        six controls (a real sequence, so numbered) + the selected control's detail
tape       the recorded case's full audit trail as a receipt tape
footer
```

Max width 1200px; 24px gutters (16px on phones); the hero stacks on narrow screens with the receipt below the text.

## 3. Principles

1. **Evidence first.** Real is green and solid; simulated is amber and hatched or dashed; the two never share a card.
2. **Calm fintech, not casino.** Motion explains a state change; it doesn't decorate.
3. **One system.** Every colour and size comes from tokens; no hardcoded colours in components.
4. **Accessible by default.** WCAG AA contrast, visible focus, keyboard operable, reduced motion respected, receipt text is real DOM text.
5. **Fast.** Animate `transform` and `opacity` only; nothing runs when nothing is changing.
6. **Indian context.** ₹ and `en-IN` formatting throughout.
7. **No fake data, in any layer.** The receipt, tape and statement only show API data, or say that there is none.

## 4. Motion plan (P6-2)

| Where | What | Reduced motion |
|---|---|---|
| Hero receipt | On first load the paper feeds out of the slot in mechanical steps (`steps()` timing, ~1.1 s), then the stamp lands (scale 1.5 → 1 with a slight rotation, 160 ms) and the paper gives a 2 px jolt. Plays once per case id; a refetch of the same case doesn't replay it | Receipt shown fully printed, stamp in place |
| Hero receipt | Pointer tilt on fine pointers: up to 4° on each axis, eased, rAF-throttled | Off (also off on touch) |
| Audit tape | Lines print in as the tape scrolls into view (opacity + 6 px, 50 ms stagger), once | All lines visible |
| Sections | Fade up 12 px on first view | Visible immediately |
| Control board | Selection follows hover, focus or click; **no autoplay** (the old 2.8 s rotation is removed) | Same |
| Background | None. The canvas coin is removed | — |

## 5. 3D centrepiece (P6-3)

**Concept:** the receipt printer, in CSS 3D. A shallow printer body (top face, front face, a dark slot) sits in perspective; the receipt leaves the slot and its torn bottom edge curls towards the viewer. It replaces the "$" coin, which was the wrong currency and drew three blur filters every frame on every page.

**Why CSS 3D and not WebGL:** the receipt has to be real text (readable, selectable, accessible, honest), and CSS transforms give the depth with 0 KB of extra JavaScript on the compositor. A WebGL scene would put the text in a texture and cost about 150 KB gzipped for three.js.

**Budget:** 0 KB extra JS; transforms only; no work after the print animation ends except the pointer tilt (rAF, only while the pointer moves over the hero).

**Fallback:** the same DOM without the curl and tilt under `prefers-reduced-motion`, and a flat layout on narrow screens. No WebGL, so no WebGL fallback is needed.

## 5b. The livelier landing (2026-10-25, after the owner asked for "more attractive and animated")

Same receipt system, more of it alive. Order: hero printer → two kinds of evidence → **one failure, six controls** (scroll story) → **try the policy** → the batch evaluation → the audit tape → FAQ.

| Piece | What it does | Reduced motion |
|---|---|---|
| Hero | Text rises in sequence; "on the record." gets an ink underline; printer LED blinks while printing; the paper sways gently after printing; **Reprint** replays the print; contact shadow under the printer | Static, fully printed |
| Evidence slips | A REAL / SIMULATED stamp lands on each slip as it scrolls in | Stamps shown |
| Scroll story | The agent's six steps on the right; the recorded case's matching line prints on a sticky receipt on the left as each step reaches the middle of the screen; the stamp lands at Verify. Lines come only from the recorded case (`linesFor`). On narrow screens each step shows its own line | All lines printed |
| Try the policy | Pick any documented Razorpay `error_reason` and the failed method; a decision slip prints from `GET /api/policy/preview` (the agent's real rules, nothing paid or sent) | Slip shown without the print |
| Statement | Figures count up when the statement scrolls in; shows the evaluation's generation date | Final figures |
| Dividers | Sections are separated by a receipt perforation | – |

Performance after the change (local preview): Lighthouse mobile 93 / desktop 100, CLS 0, TBT ≈ 20 ms. Fonts are self-hosted (`@fontsource-variable`, width + weight axes) and preloaded; `useCountUp` runs no frame loop when there's nothing to count.

## 5c. Checklist review (2026-10-25)

The owner shared two checklists (website compliance; "20 things to add"). Decisions:

| Item | Decision |
|---|---|
| Privacy policy, T&C | **Added**: one `/legal` page (what is kept and for how long, services involved, DPDP Act rights and contact, terms of use, "not affiliated with Razorpay"), linked from every footer, with a last-updated date |
| Cookies policy / consent, simple cookie banner | **Not needed**: the site sets no cookies and runs no analytics; stated on `/legal`. A banner would imply tracking that doesn't exist |
| Refund policy | **Not applicable**: test mode only, no money moves (stated in the terms) |
| Form consent, collect only necessary data | Already true: no personal data is asked for; Checkout prefill is placeholder data |
| Check tracking, UTM tracking | No tracking by design |
| Third-party embeds | Razorpay Checkout and Cloudflare Turnstile are named on `/legal`; **Google Fonts removed** (self-hosted) |
| Accessibility, contrast, keyboard forms, clear labels, alt text | Already covered (axe-core: 0 violations on every page; no content images) |
| Remove fake reviews / false claims | Done in Phase 3 (no invented figures anywhere) |
| Business details, image copyright | Contact in the footer; fonts are OFL; no stock images |
| Mobile menu | **Added** (the nav links were hidden on phones with no way to open them) |
| Copy button | **Added** for test card numbers and the test UPI ID |
| Expandable FAQ | **Added** (six questions reviewers actually ask) |
| Last updated date | **Added** on `/legal`; the evaluation shows its generation date |
| Loading animations, hover states, sticky header, skip link, form success/error states | Already present |
| Dark mode toggle | **No**: the system is dark by design, with paper as the light element; a second palette would dilute the receipt idea |
| Site search, back-to-top, scroll progress bar, print stylesheet, password toggle, confirmation modals, floating contact button | **No**: a short site with no passwords; these would add clutter without helping anyone |

## 6. Decisions log

| Date | Decision |
|---|---|
| 2026-10-24 | Keep the real / simulated / danger semantic colours whatever the final theme. |
| 2026-10-24 | Motion and 3D work waits until Phases 1–5 are done. |
| 2026-10-25 | Phase 6 system: printed-receipt signature, carbon/paper palette with stamp inks, Archivo + Martian Mono. Replaces both earlier themes. |
| 2026-10-25 | 3D in CSS, not WebGL: the receipt must be real text; 0 KB budget. |
| 2026-10-25 | Control board autoplay removed (distracting; ignored reduced motion). |
| 2026-10-25 | Landing made livelier within the same system: scroll story replaces the control board; interactive policy slip; stamps on slips; reprint; FAQ; `/legal`; self-hosted fonts. |

## 7. What it replaced (state before Phase 6)

`index.css` (~1,330 lines) had two themes stacked: an original warm theme (gold `#d4a35a`, cream, green/amber semantics) and a later violet layer that redefined the same tokens as lavender and mint, with violet glows and `!important`. Type was Instrument Serif, Inter and DM Mono. A full-screen canvas drew a rotating "$" coin with three blur filters every frame on every page. The fixed nav let content show through it on scroll.
