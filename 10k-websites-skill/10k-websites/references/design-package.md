# The Design Package

The single deliverable of the Creative Director's Loop in Phase 5. One document that holds every creative decision, written complete BEFORE any generation, and consumed by the build in Phase 8. Whoever picks it up should need nothing else to build the right page.

Two rules govern it:

- **Every line of copy in the package ships verbatim.** The package is where the writing happens; the build is where the wiring happens. Build passes wire the authored lines in exactly and never paraphrase them.
- **Numbers are starting points.** Band ranges and plateau numbers here are labeled starting points. The flick test in `scrub-pipeline.md` validates them later, and the ranges move if the test says so.

Tier 1 gets the same package, trimmed: fewer bands, same sections.

## 1. The brand premise

One short paragraph built on ONE real word or idea from the subject's world, and the whole site teaches and sells that one idea. Every section, the interactive moment, and the closing line all serve it. If a section does not serve the premise, it does not belong on the page.

## 2. The palette as CSS tokens

Sampled from the world of the footage, so page and video read as one place. Before generation the package names the palette direction from the storyboard's world; the exact token values get finalized from the approved footage after the video gate. Named roles, ready to paste into the build:

```css
:root{
  --canvas:#___;        /* page background, tinted toward the footage's grade, never pure black or white */
  --panel:#___;         /* cards and raised surfaces */
  --accent:#___;        /* the CTA and rare emphasis */
  --accent-hover:#___;  /* the accent's hover state */
  --accent-muted:#___;  /* the accent at whisper level: borders, glows, particles */
  --text-secondary:#___;
  --text-primary:#___;
}
```

## 3. The type trio

A fresh display face, a quiet body face, and a mono for small labels. Never Inter or Roboto as display. Pick faces from the brand's own world rather than a habitual default. Name each face and the exact weights in use.

## 4. The band map

One table, one row per hero band:

| Band | Range (starting point) | Footage moment | Copy (verbatim) | Entrance |
|---|---|---|---|---|
| 1 | 0.00 to 0.14 | what the video is doing | "The exact words." | one named entrance |
| 2 | 0.16 to 0.32 | ... | "..." | ... |

- **Range:** a labeled starting point in scroll progress, validated later by the flick test.
- **Footage moment:** what the video shows while this band is on, so the layout can keep the action lane clear.
- **Copy:** the exact final words, in the brand's register.
- **Entrance:** one named entrance per band, echoing the footage moment (the echo principle in `scrub-pipeline.md`).

## 5. The static-hero copy block

The composed copy for visitors who get the static hero (phones, reduced motion): headline, subline, and CTA, written to stand over the poster or ending frame with no journey behind them.

## 6. The below-fold outline

The sections after the settle, in order, each with its verbatim copy. Every section funnels to ONE call-to-action anchor. The outline includes:

- The one interactive moment and which section it lives in.
- The FAQ, answering the real objections found in research, in the buyers' own words.
- The quotes or testimonials copy.
- The form microcopy: labels, placeholder text, button label, and the success state, plus the form's handling choice on a static site (JS-only success state, mailto link, a free form service, or no form at all; the options live in Phase 8 of the skill).
- The footer, with the fictional-brand disclosure when the brand is invented.

## 7. The vector layer plan

The SVG elements you will draw by hand (motifs, self-drawing lines, dividers), the whisper-level particles, and where each one lives on the page. All of it honors reduced motion: final states shown, drives stopped.

## 8. The engineering list

Name the full standard so the build cannot half-remember it: the Blob fetch with the loading ring, the dt-normalized lerp, gated seeks, delta-gated DOM writes, band pacing with the flick test, the four-layer legibility system, the five static-hero gates kept live with change listeners, complete-without-video, and the quality floor, all in `scrub-pipeline.md`, plus the whole-site-animated standard in Phase 8 of the skill.

## 9. The copy gate line

End the package with the gate, stated so the build inherits it: every viewer-facing line above ships verbatim, and the built page must pass the Phase 9 grep gate (zero em dashes, zero stock words, plus the body-copy sweep for AI tells) before anyone sees it. Deliberate brand devices written in this package (a designed triplet, a planned staccato punch) are craft and stay; the sweep hunts what drifted in uninvited.
