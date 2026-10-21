# AURA performance — after-glow-sprites

Measured 2026-10-21T17:05:31 with `tools/perf_baseline.py` on 12 CPU threads / 15.7 GB RAM. CPU % is of the whole machine (all cores), like Task Manager. RAM is private working set. GPU % is the busiest GPU engine, averaged; GPU memory is read at the end of each window.

**Cold start:** window loaded in 0.7 s, brain listening in 2.9 s.

**Home draws:** 1536x816 window at 1.25x pixel ratio; canvases particle-field 1920x1020, bh-canvas 2175x2175, cursor-lens 175x175; videos aura-main.mp4 1672x940.

## Per screen

| Scenario | AURA CPU | AURA RAM | AURA GPU | GPU shared mem | Machine CPU | Machine GPU 3D | FPS | p95 frame | Slow frames | Window |
|---|---|---|---|---|---|---|---|---|---|---|
| machine idle (AURA closed) | 0.0% | 0 MB | 0.0% | 0 MB | 9.3% | 0.0% | — | — | — | — |
| Home — idle | 15.9% | 609 MB | 42.2% | 345 MB | 28.3% | 43.0% | 40 | 33.6 ms | 23.4% | visible |
| Home — thinking (simulated) | 16.1% | 610 MB | 36.2% | 353 MB | 42.0% | 36.6% | 33 | 50.1 ms | 35.6% | visible |
| Home — speaking (simulated, no audio) | 16.4% | 603 MB | 34.6% | 396 MB | 34.5% | 35.0% | 28 | 50.1 ms | 42.3% | visible |
| Home — idle, buddy switched off | 15.3% | 583 MB | 28.3% | 388 MB | 43.3% | 28.3% | 25 | 66.8 ms | 53.4% | visible |
| Home — idle, without background video | 15.8% | 562 MB | 25.4% | 367 MB | 39.5% | 25.5% | 23 | 66.6 ms | 65.7% | visible |
| Home — idle, without particle field | 15.1% | 561 MB | 27.1% | 419 MB | 32.3% | 28.8% | 25 | 50.2 ms | 45.4% | visible |
| Home — idle, without black hole | 15.6% | 562 MB | 28.4% | 420 MB | 29.3% | 30.2% | 26 | 66.6 ms | 39.3% | visible |
| Home — idle, without cursor lens | 15.9% | 574 MB | 30.4% | 420 MB | 30.0% | 32.8% | 27 | 50.1 ms | 42.2% | visible |
| Home — idle, all four layers hidden | 15.3% | 592 MB | 26.0% | 461 MB | 28.3% | 28.5% | 28 | 83.3 ms | 37.6% | visible |
| Chats page | 16.4% | 602 MB | 29.7% | 292 MB | 42.9% | 32.3% | 49 | 33.4 ms | 3.7% | visible |
| Memory page | 16.5% | 515 MB | 27.4% | 294 MB | 35.0% | 27.5% | 55 | 33.3 ms | 3.2% | visible |
| Tasks page | 13.4% | 502 MB | 28.9% | 289 MB | 20.6% | 28.9% | 59 | 16.9 ms | 0.4% | visible |
| Models page | 17.5% | 497 MB | 36.2% | 292 MB | 28.6% | 38.3% | 52 | 33.4 ms | 4.6% | visible |
| Settings page | 14.5% | 492 MB | 29.7% | 288 MB | 25.4% | 29.7% | 58 | 17.0 ms | 1.2% | visible |
| Labs page | 13.3% | 493 MB | 28.8% | 288 MB | 22.1% | 28.9% | 57 | 33.2 ms | 2.1% | visible |
| Aura Domain | 18.2% | 636 MB | 48.4% | 417 MB | 30.0% | 48.4% | 48 | 33.4 ms | 7.2% | visible |
| Minimised (buddy still out) | 0.3% | 480 MB | 0.3% | 269 MB | 19.0% | 0.7% | 0 | — | — | hidden |

## Where it goes (per process)

| Scenario | main window | buddy window | gpu process | brain (python) | electron main | network | audio | utility | crashpad |
|---|---|---|---|---|---|---|---|---|---|
| Home — idle | 2.8% · 89 MB | 0.1% · 18 MB | 12.4% · 373 MB, 42% gpu | 0.2% · 93 MB | 0.4% · 28 MB | 0.0% · 8 MB | — | — | — |
| Home — thinking (simulated) | 3.2% · 79 MB | 0.2% · 18 MB | 12.4% · 387 MB, 36% gpu | 0.3% · 93 MB | 0.0% · 26 MB | 0.0% · 8 MB | — | — | — |
| Home — speaking (simulated, no audio) | 3.2% · 76 MB | 0.2% · 16 MB | 12.8% · 397 MB, 35% gpu | 0.2% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, buddy switched off | 2.5% · 63 MB | 0.0% · 16 MB | 12.6% · 391 MB, 28% gpu | 0.1% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, without background video | 2.3% · 74 MB | 0.1% · 15 MB | 13.1% · 359 MB, 25% gpu | 0.2% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, without particle field | 2.0% · 70 MB | 0.2% · 16 MB | 12.9% · 362 MB, 27% gpu | 0.1% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, without black hole | 2.4% · 69 MB | 0.2% · 15 MB | 12.8% · 363 MB, 28% gpu | 0.1% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, without cursor lens | 2.5% · 74 MB | 0.2% · 16 MB | 13.0% · 370 MB, 30% gpu | 0.1% · 90 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Home — idle, all four layers hidden | 1.9% · 91 MB | 0.1% · 16 MB | 13.1% · 370 MB, 26% gpu | 0.1% · 91 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Chats page | 2.4% · 71 MB | 0.2% · 16 MB | 13.7% · 398 MB, 30% gpu | 0.1% · 91 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Memory page | 2.5% · 71 MB | 0.0% · 16 MB | 13.8% · 311 MB, 27% gpu | 0.2% · 92 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Tasks page | 1.6% · 69 MB | 0.1% · 16 MB | 11.6% · 300 MB, 29% gpu | 0.1% · 92 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Models page | 2.5% · 56 MB | 0.0% · 16 MB | 14.9% · 306 MB, 36% gpu | 0.1% · 94 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Settings page | 1.7% · 55 MB | 0.1% · 16 MB | 12.7% · 302 MB, 30% gpu | 0.1% · 95 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Labs page | 1.7% · 56 MB | 0.0% · 16 MB | 11.4% · 301 MB, 29% gpu | 0.1% · 95 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Aura Domain | 2.8% · 62 MB | 0.1% · 16 MB | 15.1% · 438 MB, 48% gpu | 0.1% · 96 MB | 0.0% · 20 MB | 0.0% · 4 MB | — | — | — |
| Minimised (buddy still out) | 0.0% · 61 MB | 0.1% · 16 MB | 0.1% · 282 MB | 0.0% · 96 MB | 0.0% · 21 MB | 0.0% · 4 MB | — | — | — |

Cells: CPU % · RAM (· GPU % when it uses any).

## Busiest other processes

What else was using CPU meanwhile. dwm.exe is the Windows compositor — it works harder when AURA's window does; (this script) is the measuring itself.

| Scenario | Top other processes (CPU %) |
|---|---|
| machine idle (AURA closed) | svchost.exe 1.9%, (this script) 1.5%, System 0.9%, claude.exe 0.8%, MemCompression 0.7%, comet.exe 0.4% |
| Home — idle | (this script) 2.6%, Code.exe 2.5%, svchost.exe 1.4%, System 1.1%, Spotify.exe 0.7%, dwm.exe 0.7% |
| Home — thinking (simulated) | claude.exe 3.9%, (this script) 3.2%, svchost.exe 2.5%, MsMpEng.exe 2.1%, System 2.0%, Code.exe 1.9% |
| Home — speaking (simulated, no audio) | svchost.exe 4.5%, (this script) 3.0%, System 2.1%, Code.exe 1.7%, claude.exe 0.8%, comet.exe 0.8% |
| Home — idle, buddy switched off | msedgewebview2.exe 7.8%, Code.exe 2.8%, claude.exe 2.8%, (this script) 2.3%, System 1.6%, MsMpEng.exe 1.3% |
| Home — idle, without background video | (this script) 2.4%, Code.exe 1.6%, svchost.exe 1.4%, System 1.4%, claude.exe 1.1%, MsMpEng.exe 1.0% |
| Home — idle, without particle field | claude.exe 6.9%, (this script) 2.0%, Code.exe 1.8%, svchost.exe 1.4%, System 1.2%, MsMpEng.exe 0.5% |
| Home — idle, without black hole | Code.exe 4.0%, claude.exe 3.8%, (this script) 2.4%, svchost.exe 1.3%, System 1.0%, comet.exe 0.5% |
| Home — idle, without cursor lens | claude.exe 4.3%, (this script) 1.9%, Code.exe 1.9%, svchost.exe 1.1%, System 0.9%, dwm.exe 0.4% |
| Home — idle, all four layers hidden | claude.exe 4.0%, (this script) 2.2%, Code.exe 1.4%, svchost.exe 1.4%, System 1.1%, MsMpEng.exe 0.4% |
| Chats page | claude.exe 4.9%, explorer.exe 4.8%, GlobalPresenter.exe 3.0%, (this script) 2.7%, Code.exe 2.1%, System 1.4% |
| Memory page | GlobalPresenter.exe 4.0%, comet.exe 2.5%, (this script) 2.0%, Code.exe 1.8%, System 1.7%, svchost.exe 1.4% |
| Tasks page | (this script) 1.6%, Code.exe 1.2%, svchost.exe 1.0%, claude.exe 0.7%, System 0.7%, comet.exe 0.6% |
| Models page | claude.exe 3.6%, (this script) 1.8%, svchost.exe 1.1%, System 0.8%, MsMpEng.exe 0.5%, dwm.exe 0.4% |
| Settings page | claude.exe 4.2%, (this script) 1.8%, svchost.exe 1.2%, System 0.8%, dwm.exe 0.5%, MsMpEng.exe 0.2% |
| Labs page | claude.exe 2.1%, (this script) 1.7%, svchost.exe 1.1%, System 0.8%, comet.exe 0.5%, dwm.exe 0.4% |
| Aura Domain | Code.exe 2.8%, (this script) 2.5%, System 1.3%, claude.exe 1.3%, svchost.exe 1.2%, comet.exe 0.7% |
| Minimised (buddy still out) | claude.exe 2.3%, svchost.exe 1.9%, System 1.5%, Code.exe 1.2%, (this script) 1.1%, MsMpEng.exe 1.0% |

## Compared with the baseline (written by hand)

This build adds, on top of the first black hole fix: the planet rim glows pre-blurred into sprites, ring dust batched by colour, and the backing, orbit guides, slot orbits and planet halos cached until a setting changes. Before → **after**:

| Scenario | FPS | AURA GPU | AURA CPU | AURA RAM | p95 frame |
|---|---|---|---|---|---|
| Home — idle | 6 → **40** | 85% → **42%** | 8.1% → **15.9%** | 642 MB → **609 MB** | 217 ms → **34 ms** |
| Home — thinking (simulated) | 5 → **33** | 84% → **36%** | 6.3% → **16.1%** | 649 MB → **610 MB** | 217 ms → **50 ms** |
| Home — speaking (simulated, no audio) | 5 → **28** | 82% → **35%** | 7.5% → **16.4%** | 691 MB → **603 MB** | 250 ms → **50 ms** |
| Home — idle, buddy switched off | 6 → **25** | 99% → **28%** | 11.7% → **15.3%** | 649 MB → **583 MB** | 217 ms → **67 ms** |
| Home — idle, without background video | 5 → **23** | 77% → **25%** | 6.3% → **15.8%** | 628 MB → **562 MB** | 250 ms → **67 ms** |
| Home — idle, without particle field | 5 → **25** | 83% → **27%** | 11.2% → **15.1%** | 600 MB → **561 MB** | 233 ms → **50 ms** |
| Home — idle, without black hole | 6 → **26** | 96% → **28%** | 11.4% → **15.6%** | 646 MB → **562 MB** | 234 ms → **67 ms** |
| Home — idle, without cursor lens | 6 → **27** | 94% → **30%** | 11.9% → **15.9%** | 651 MB → **574 MB** | 233 ms → **50 ms** |
| Home — idle, all four layers hidden | 5 → **28** | 80% → **26%** | 10.2% → **15.3%** | 675 MB → **592 MB** | 417 ms → **83 ms** |
| Chats page | 55 → **49** | 31% → **30%** | 15.6% → **16.4%** | 632 MB → **602 MB** | 33 ms → **33 ms** |
| Memory page | 50 → **55** | 27% → **27%** | 16.5% → **16.5%** | 618 MB → **515 MB** | 33 ms → **33 ms** |
| Tasks page | 56 → **59** | 28% → **29%** | 15.3% → **13.4%** | 622 MB → **502 MB** | 33 ms → **17 ms** |
| Models page | 48 → **52** | 38% → **36%** | 17.5% → **17.5%** | 620 MB → **497 MB** | 33 ms → **33 ms** |
| Settings page | 57 → **58** | 30% → **30%** | 14.9% → **14.5%** | 616 MB → **492 MB** | 33 ms → **17 ms** |
| Labs page | 57 → **57** | 30% → **29%** | 13.8% → **13.3%** | 615 MB → **493 MB** | 33 ms → **33 ms** |
| Aura Domain | 6 → **48** | 78% → **48%** | 8.0% → **18.2%** | 812 MB → **636 MB** | 217 ms → **33 ms** |
| Minimised (buddy still out) | 0 → **0** | 0% → **0%** | 0.3% → **0.3%** | 578 MB → **480 MB** | — → **—** |


1. **Home is 40 fps for the first minute, then ~25–28 fps sustained.** The Home rows fall steadily through the run (40 → 33 → 28 → 25), while the pages measured after them recover to 49–59 fps. That fits the laptop's short power boost ending, not AURA slowing down. A separate clean as-is vs black-hole-off test on this build agreed: Home held 28–29 fps; with the black hole off it reached 40–53.
2. **Aura Domain: 6 → 48 fps. Pages are unchanged at 49–59 fps.** RAM is down on every screen (Domain 812 → 636 MB; pages ~620 → ~500 MB).
3. **What's left is drawing-command count, in the GPU process.** A Skia-level trace of Home showed its main thread 99% busy at ~30 ms per frame:
   - ~10 ms of overhead for ~1,100 separate shape draws, mostly the particle field's ~1,400 dots, plus the black hole's ~600 commands;
   - ~4 ms triangulating ~200 complex shapes on the CPU (the black hole's 110 filament strands and the batched dust);
   - ~3 ms for simple round shapes, and ~4 ms for rectangles, images and compositing.
4. **Next levers.** Both change *how* things are drawn, not what they look like:
   - draw the particle field with WebGL (one GPU draw instead of ~1,400 canvas commands; it would help every screen);
   - and/or redraw the black hole at 30 fps while the video, particles and cursor stay at 60.

**Measuring lessons from today:** don't measure right after a build (Windows Defender scans the 256 MB of videos it copies), close any other AURA first, and expect the first minute after launch to be faster than sustained use.
