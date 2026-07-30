# Add Scroll Animations

This plan details how we will introduce scroll-triggered animations to your website's static elements (text, cards, and sections) to make it feel alive and dynamic as the user scrolls.

## Proposed Changes

Since the `motion` (Framer Motion) library is already installed in your project, we will use it to easily and beautifully animate elements as they come into the viewport.

### [MODIFY] `src/components/Hero.tsx`

- Wrap the main headline and subtext in `<motion.div>` or `<motion.h1>`.
- Add a smooth fade-up animation that triggers immediately on load.

### [MODIFY] `src/components/Cards.tsx`

- Wrap the main grid or individual cards in `<motion.div>`.
- Use `staggerChildren` or individual delays so that the cards fade and slide up sequentially (a "waterfall" effect) when scrolled into view.

### [MODIFY] `src/components/TrustedBrands.tsx` & `StudioSection.tsx` & `FeatureGridSection.tsx`

- Wrap the main container or inner text blocks with `<motion.div>`.
- Use the `whileInView={{ opacity: 1, y: 0 }}` prop with `viewport={{ once: true, margin: "-100px" }}` to trigger a smooth fade-in-up animation exactly when the user scrolls to that section.

### [MODIFY] `src/components/TestimonialSection.tsx`

- Animate the testimonial container and the carousel items.
- Ensure the transition feels premium (e.g. `transition={{ duration: 0.6, ease: 'easeOut' }}`).

## User Review Required

> [!NOTE]
> We will apply a unified "fade up and in" animation pattern across the components to maintain a premium feel. The animations will trigger once per section (`once: true`) so they don't distract the user when scrolling back up.

Please approve this plan so I can proceed with implementing the animations!
