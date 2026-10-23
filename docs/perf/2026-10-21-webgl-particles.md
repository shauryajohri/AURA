# AURA performance — particle field on WebGL

The particle field's ~1,400 dots (and the comets' trailing dots) are now drawn by WebGL in
one call (`frontend/src/components/ParticleField.tsx`). The shooting stars, comet heads and
speaking rings stay on a 2D canvas above. If WebGL is unavailable or its context is lost,
the dots go back to the 2D canvas, drawn exactly as before.

## Same look

The shader uses the 2D canvas's own circle anti-aliasing and its additive ("lighter") blend.
Two checks, both run inside AURA's Electron:

- **Dot by dot** (a grid of dots at 13 sizes × 49 sub-pixel positions, in a hidden test
  window). From 1.25 device px up, the dots matched the canvas's exactly when Chromium drew
  an exact circle. But Chromium draws almost every `arc()` as a polygon, whose edge comes out
  ~0.04 device px fatter. Without a correction, small dots were 7–14% dimmer. The shader now
  adds that 0.04 px. Light per dot is then within ±4% at every size, and equal on average.
- **300 random dots, in the app:** the total light is 2D 367,033 vs WebGL 368,552 (+0.4%),
  with a mean per-pixel difference of 2.7/255. What remains is the shape of 1–2 px dots,
  where Chromium's polygon is slightly lopsided.
- **Screenshot of the sky beside the core:** the mean colour is 16.5/8.9/40.0 before and
  16.5/9.0/40.4 after.

## Faster — measured A/B in the same run

The WebGL context was deliberately lost and restored to switch between the two (losing it
makes AURA draw the old 2D dots). The window stayed on Home, visible, with nothing else running.

| Run | WebGL dots | Old 2D dots | WebGL dots, black hole off |
|---|---|---|---|
| 1 (laptop warm) | 25–35 fps · 42–60 ms | 18–28 fps · 54–86 ms | 60 fps · 24 ms |
| 2 (laptop cool, quiet) | **46–54 fps** · 27–30 ms | 41–42 fps · 36–37 ms | 60 fps · 14 ms |

ms = GPU-process CPU time per frame. The gain is consistent: about +25–40% frames per
second, and 8–30 ms less GPU-process work per frame. Absolute numbers swing with the
laptop's temperature and power state, so only compare rows from the same run.

## What's left

With the dots on WebGL, Home's remaining gap to 60 fps is the black hole: ~15 ms of
GPU-process work per frame (29 ms with it, 14 ms without). The biggest single costs are its
ring glow layer (six blurred strokes redrawn every frame) and its 110 filament strands,
which Chromium triangulates on the CPU every frame.

A full `tools/perf_baseline.py` run was not repeated for this build.
