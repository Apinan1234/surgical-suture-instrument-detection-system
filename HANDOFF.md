# Handoff: Smooth Scroll Animation — React Website Integration

**Date:** 2026-07-30  
**Conversation ID:** `9375fbca-2898-44c5-9cc8-8a390b13c2c9`  
**Project:** AI Surgical Instrument Detection System — Scroll-based Marketing Site  
**Dev Server:** `http://localhost:3000/`

---

## 1. Project Overview

This is a **React + Vite + TypeScript + TailwindCSS v4** website (located in `02_web-app/`) for an AI surgical instrument detection research project. The website uses a **scroll-scrubbing video animation** as a fixed full-screen background layer, with marketing/research sections layered on top using glassmorphism-style transparent cards.

The 300 JPEG frames that drive the scroll animation were extracted from a surgical video and placed in:
```
02_web-app/public/frames/ezgif-frame-001.jpg  →  ezgif-frame-300.jpg
```

---

## 2. Architecture Summary

### Key Files

| File | Purpose |
|---|---|
| [`02_web-app/src/components/ScrollAnimation.tsx`](file:///c:/Users/USER/OneDrive/Documents/BEAM/VideoFrameExtractor/02_web-app/src/components/ScrollAnimation.tsx) | Canvas-based scroll animation component. Renders as `fixed z-[-1]` background layer. Preloads all 300 frames, scrubs through them proportional to page scroll, uses native DPR scaling + manual `cover` math for sharpness. |
| [`02_web-app/src/App.tsx`](file:///c:/Users/USER/OneDrive/Documents/BEAM/VideoFrameExtractor/02_web-app/src/App.tsx) | Root component. Mounts `<ScrollAnimation />` then stacks 5 content sections. All section containers use `bg-transparent` so the background animation shows through. Also includes a "View the Research" modal with email capture. |
| `02_web-app/src/components/Hero.tsx` | Banner headline (3-line break: "See Every Suture. / Understand / Every Step."), subtext, and CTA button. Centered with `max-w-md` to avoid overlapping the plane window in the animation frame. Framer Motion: fade-up on load. |
| `02_web-app/src/components/Cards.tsx` | 6-card grid (problem/solution breakdown). Framer Motion stagger waterfall on scroll. |
| `02_web-app/src/components/TrustedBrands.tsx` | Section 2 — branded partner logos row. Framer Motion fade-up. |
| `02_web-app/src/components/StudioSection.tsx` | Section 3 — 4 agency-style cards with `bg-gradient-to-b from-transparent to-[#0C1B3A]/90` gradient. Framer Motion fade-up. |
| `02_web-app/src/components/TestimonialSection.tsx` | Section 4 — 3-slide testimonial carousel with portrait, quote, and stats. Framer Motion fade-up. |
| `02_web-app/src/components/FeatureGridSection.tsx` | Section 5 — 2 left cards slide in from left, 2 right cards slide in from right. Empty centre column reserved for future visual. |

### Design Decisions

- **Transparency:** All `bg-black` values were replaced with `bg-transparent`. Earlier pass also removed `border-white/10` from section wrappers to make frames invisible. Only individual child cards retain `bg-white/10 backdrop-blur-md` for glassmorphism.
- **Studio Section cards (Section 3):** Use `bg-gradient-to-b from-transparent to-[#0C1B3A]/90` to match the dark-bottom style of Section 4 (Testimonial), as the user requested.
- **Animations:** Use `motion/react` (Framer Motion v12, already in `package.json`). All scroll triggers use `whileInView` with `viewport={{ once: true, margin: "-100px" }}`. Feature Grid uses `x` slide-in instead of `y`.

---

## 3. Development Environment

```bash
# Install & run
cd 02_web-app
npm install
npm run dev         # → http://localhost:3000/  (--host=0.0.0.0 --port=3000)
```

**Key dependencies (already installed):**
- `motion` v12.x (Framer Motion)
- `tailwindcss` v4
- `lucide-react`
- `vite` + `@vitejs/plugin-react`

---

## 4. Current Status

### ✅ Completed
- [x] Scroll animation (300 frames, Canvas, DPR-sharp, cover math)
- [x] React port of scroll animation as fixed background layer
- [x] All 5 content sections mounted and transparent
- [x] Glassmorphism styling and blue gradient on Studio cards
- [x] Framer Motion scroll animations on all sections and cards
- [x] Hero headline split into 3 lines, centred to avoid overlapping animation plane window
- [x] Mobile optimisation (viewport meta, no zoom, native resolution)

### 🔲 Outstanding / Open Considerations
- The Hero `max-w-md` centering was a layout workaround for the specific animation frame — may need tweaking if the video/frames change.
- The **centre column** of `FeatureGridSection` is intentionally empty (comment: "Reserved for future visuals"). Could hold a diagram, video loop, or interactive model viewer.
- The **Research modal email capture** (`App.tsx` L64–163) currently does NOT actually send an email — it's a UI-only confirmation flow. A backend endpoint or service (e.g., Resend, Mailchimp API) should be wired in if real email delivery is needed.
- Testimonial portrait images are loaded from `/src/assets/images/` — not public assets — so they won't work in a production build without moving them to `/public/`.

---

## 5. Artifacts from Previous Session

| Artifact | Path |
|---|---|
| Implementation Plan | [`C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/implementation_plan.md`](file:///C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/implementation_plan.md) |
| Task Checklist | [`C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/task.md`](file:///C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/task.md) |
| Walkthrough | [`C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/walkthrough.md`](file:///C:/Users/USER/.gemini/antigravity-ide/brain/9375fbca-2898-44c5-9cc8-8a390b13c2c9/walkthrough.md) |
| In-workspace plan copy | [`02_web-app/src/implementation_plan.md`](file:///c:/Users/USER/OneDrive/Documents/BEAM/VideoFrameExtractor/02_web-app/src/implementation_plan.md) |

---

## 6. Suggested Next Steps (for the next agent)

If continuing this project, likely focus areas are:

1. **Wire up email capture** — the modal form in `App.tsx` needs a real backend. Consider using Resend (`npm install resend`) or a simple Netlify/Vercel function.
2. **Fix testimonial image paths** — move portrait images from `src/assets/images/` to `public/assets/images/` and update the import paths in `TestimonialSection.tsx` L4–6 so they work in production builds.
3. **Fill the FeatureGrid centre column** — this is the most obvious visual gap on desktop. Could use an interactive 3D model, a looping video clip of detection output, or an annotated frame from the surgical footage.
4. **Footer / Navigation** — the `Header.tsx` tab navigation (Overview, Research, Dataset, Demo) does not currently route to different views. Implementing tab-switching content or smooth-scroll anchors would make the navigation functional.
5. **Performance** — 300 JPEG frames are preloaded eagerly. Consider lazy-loading batches, or using a video element with `playbackRate=0` and `currentTime` scrubbing instead to reduce the total asset size.

---

## 7. Suggested Skills

The following skills may be useful in the next session:

- **`modern-web-guidance-plugin`** — for React, Vite, TailwindCSS v4 best practices.
- **`workflow-skill-creator`** — if the user wants to package the scroll animation pattern as a reusable skill.
- **`credentials`** — if wiring in an email API key (Resend, SendGrid, etc.), use this skill to handle secrets safely.

---

*This handoff was generated from conversation `9375fbca-2898-44c5-9cc8-8a390b13c2c9`. No API keys, passwords, or PII were present in the session.*
