# Rare Class Labeler — Design System

Single consolidated reference for this product's visual design: color, type, spacing, radius,
shadow, motion, and the component catalog. This one file *is* the design system, the UI design
system, the design language, and the visual-style/UI-UX reference — deliberately not split into
separate documents for each of those names, since they describe the same thing from different
angles.

Implemented directly as CSS custom properties + component classes in `mockup/index.html`'s
`<style>` block — this document explains the *why* behind each token/component; the CSS is the
enforced source of truth.

**Design principle**: the brief for this product is explicit — "เรียบง่าย, อัตโนมัติ, น่าเชื่อถือ"
(simple, automatic, trustworthy), and explicitly *not* "a scary/complex-looking AI tool." Every
decision below is filtered through that: no gratuitous gradients/glow, no dashboard-of-panels
layout, no settings the user has to understand before they can use the tool.

## Where this came from

Grid, card craft, badge/status-pill patterns, segmented pill controls, gradient metric panels, and
motion/accessibility discipline (`focus-visible`, `prefers-reduced-motion`, dark-mode via
`prefers-color-scheme`) were extracted from a Vite/React/Tailwind reference site the user supplied
(a Pocari Sweat product-catalog site) — **patterns only**. No brand names, copy, colors, imagery,
or code were carried over; the palette and component details below are original to this product.

## Color

Two families of tokens: **neutrals** (backgrounds/text/borders — do almost all the work) and
**two semantic accents** (primary action, rare-class flag). This mirrors the reference site's
"one bold brand color + one reserved semantic color" discipline instead of a rainbow of UI colors.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F3F6FB` | `#0A121F` | Page background — cool, clinical, blue-tinted (not green, not pure gray) |
| `--surface` | `#FFFFFF` | `#111B2C` | Cards |
| `--surface-2` | `#EAF1FA` | `#182437` | Recessed panels (dropzone, tiles, toolbar) |
| `--surface-3` | `#DCE7F5` | `#20304A` | Progress track, deepest recess |
| `--border` | `#D3E0F0` | `#28374F` | All hairlines |
| `--ink` | `#0F1E33` | `#EAF1FB` | Primary text |
| `--ink-muted` | `#55677E` | `#93A5BE` | Secondary text |
| `--ink-faint` | `#8A9AB0` | `#63748F` | Tertiary/label text |
| `--accent` | `#0B63C4` | `#4FA3F0` | Primary action color — used *only* for the primary button, active states, links |
| `--accent-hover` | `#094F9C` | `#6FB6F5` | Hover/active shade of accent |
| `--accent-ink` | `#FFFFFF` | `#052042` | Text/icon color on top of `--accent` |
| `--accent-soft` | `#E3EFFC` | `#16304F` | Tint background for active/selected states |
| `--accent-2` | `#0AA3D9` | `#3FD0F5` | Secondary accent — "live/working" status pulses only, never for static UI |
| `--rare` | `#C2570F` | `#F0A868` | Reserved *only* for the rare-class (`needle`) flag — never decorative |
| `--rare-bg` | `#FDEEE0` | `#2E2013` | Rare badge/tile background |
| `--rare-ink` | `#7A3D0F` | `#F3CB9E` | Rare badge text |

Dark mode is automatic via `prefers-color-scheme` (with `[data-theme]` override hooks kept for
future-proofing) — **no manual light/dark toggle in the UI**. A toggle is a marketing-site
affordance; this tool has one job and shouldn't add a control for it.

## Typography

- **Thai/Latin UI text**: `IBM Plex Sans Thai` (paired `IBM Plex Sans` for pure-Latin runs) — one
  Google Fonts family covering both scripts cleanly, already verified to render Thai correctly.
- **Brand/display** (masthead product name only): `IBM Plex Sans Thai` at 700-800 weight with
  tight letter-spacing — a display *treatment*, not a separate typeface, so the brand doesn't
  introduce a third font just for one line of text.
- **Measured numbers** (frame counts, percentages, timestamps, class names in code form):
  `IBM Plex Mono`, `font-variant-numeric: tabular-nums` — numbers read as "measured," matching the
  reference site's same rationale for `font-mono` on metrics.
- Scale (px): `11` (micro-labels) · `12.5` (secondary/meta) · `14.5` (body) · `16` (card titles) ·
  `20` (section intro) · `26` (page intro heading).

## Spacing scale

`4 · 8 · 12 · 16 · 24 · 32 · 48 · 64` px — as `--space-1` … `--space-8`. All padding/gap/margin
values in the component CSS are drawn from this list; nothing is a one-off pixel value.

## Radius scale

`--radius-sm: 8px` (small controls, badges) · `--radius-md: 12px` (buttons, inputs) ·
`--radius-lg: 16px` (cards, tiles) · `--radius-xl: 22px` (hero/intro panel) ·
`--radius-full: 999px` (pills, dots, progress bar).

## Shadow scale

`--shadow-xs` → `--shadow-lg`, each a two-layer shadow (tight contact shadow + soft ambient
falloff), scaling from resting-card elevation up to hover-lift elevation — same two-layer
technique the reference site uses (`shadow-sm` → `shadow-2xl` on hover), just tuned lighter to
fit a utility tool rather than a marketing page.

## Motion

- Card/tile hover: `translateY(-2px)` + shadow step-up, 200ms ease.
- Step reveal: fade + `translateY(8px → 0)`, 320ms ease-out, triggered when a step becomes visible.
- Progress fill: `width` transition 300ms ease.
- "Live" status pulse (processing indicator, output-video badge): a 2px dot with a soft
  `box-shadow` pulse animation, 1.6s loop.
- Everything above is wrapped in `@media (prefers-reduced-motion: reduce)` → instant, no loops.
- `:focus-visible` gets a 2px accent outline with offset on every interactive element —
  never suppressed.

## Component catalog

- **Topbar** — sticky, translucent + `backdrop-filter: blur`, brand mark (inline SVG, not emoji)
  + title + tagline, a status pill on the right (currently "Mockup").
- **Step rail** — numbered circle + connecting line down the left edge; circle fills solid accent
  once a step is active/done. This *is* the primary navigation model (a pipeline, not a wizard) —
  kept from the original mockup, whose rationale still holds.
- **Card** — `surface` background, `radius-lg`, `shadow-xs` resting; the container for every step.
- **Dropzone** — dashed border, `surface-2` fill, upload-cloud icon; drag-over and hover both shift
  to `accent` border + `accent-soft` fill with a small scale-up (1.01) for tactile feedback.
- **Progress bar + live status pill** — track (`surface-3`) + fill (`accent`), paired with a
  pulsing-dot status pill showing the current rotating Thai status line in mono.
- **Class tile** — the results-grid card. Icon swatch top (color-coded, gradient-tinted
  background), class name, mono frame count, **custom checkbox** (hidden native input + styled
  box + checkmark icon, so focus/keyboard/screen-reader semantics stay native while the visual is
  fully custom). Checked state: `accent` border + `accent-soft` fill. The rare tile
  (`needle`) additionally gets a corner badge (icon + "หายาก") and an `--rare` ring — flagged at a
  glance, not just in its text.
- **Segmented toolbar** — "เลือกทั้งหมด / ไม่เลือกเลย" as a two-pill segmented control, plus a mono
  "เลือกไว้ x / 9" counter badge.
- **Gradient metric panel** — the download section's summary: soft gradient background, two big
  mono stat tiles (classes selected, total frames), and a small icon-led list of zip contents
  (instead of a paragraph) so the real Phase 6 zip structure is scannable, not a wall of text.
- **History row** — clock icon + mono timestamp + class-name chips (reusing the small pill style)
  + a ghost "โหลดค่ากลับ" action.
- **Toast** — bottom-center pill, dark surface, icon + message, fade/slide in.
- **Icon set** — hand-authored inline SVG (stroke 1.8, `currentColor`, 20–24px viewBox): logo mark,
  upload-cloud, film, check-circle, alert (rare flag), download, clock, chevron-right. Zero
  dependency, consistent across browsers/OS — deliberately not an emoji set (inconsistent
  rendering) and not an icon-font/CDN (violates the no-new-dependency, self-contained constraint).

## Explicitly out of scope (confirmed a third time this session)

No confidence/IoU control of any kind — slider, toggle, or hidden "advanced" panel. No model
picker. No free-text class entry. Detection thresholds are fixed in the backend
(`conf=0.25, iou=0.7`, per `rare_class_plan.md`'s Phase 2 spec) and never surfaced in this UI.
