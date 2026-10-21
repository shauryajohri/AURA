# AURA performance — after-black-hole

Measured 2026-10-21T14:27:26 with `tools/perf_baseline.py` on 12 CPU threads / 15.7 GB RAM. CPU % is of the whole machine (all cores), like Task Manager. RAM is private working set. GPU % is the busiest GPU engine, averaged; GPU memory is read at the end of each window.

**Cold start:** window loaded in 0.7 s, brain listening in 2.9 s.

**Home draws:** 1536x816 window at 1.25x pixel ratio; canvases particle-field 1920x1020, bh-canvas 2175x2175, cursor-lens 175x175; videos aura-main.mp4 1672x940, aura-main.mp4 1672x940.

## Per screen

| Scenario | AURA CPU | AURA RAM | AURA GPU | GPU shared mem | Machine CPU | Machine GPU 3D | FPS | p95 frame | Slow frames | Window |
|---|---|---|---|---|---|---|---|---|---|---|
| machine idle (AURA closed) | 0.0% | 0 MB | 0.0% | 0 MB | 12.9% | 0.0% | — | — | — | — |
| Home — idle | 16.2% | 612 MB | 31.7% | 345 MB | 30.4% | 33.7% | 26 | 50.8 ms | 49.2% | visible |
| Home — thinking (simulated) | 15.6% | 614 MB | 25.7% | 348 MB | 32.3% | 28.3% | 20 | 66.7 ms | 77.6% | visible |
| Home — speaking (simulated, no audio) | 16.3% | 649 MB | 29.5% | 391 MB | 34.1% | 31.7% | 19 | 66.9 ms | 84.4% | visible |
| Home — idle, buddy switched off | 15.4% | 644 MB | 27.3% | 384 MB | 29.5% | 32.3% | 21 | 66.7 ms | 72.4% | visible |
| Home — idle, without background video | 15.6% | 658 MB | 25.4% | 417 MB | 33.6% | 27.9% | 21 | 66.8 ms | 71.1% | visible |
| Home — idle, without particle field | 15.3% | 625 MB | 29.7% | 380 MB | 27.5% | 31.2% | 25 | 66.6 ms | 48.7% | visible |
| Home — idle, without black hole | 14.7% | 620 MB | 21.4% | 381 MB | 54.4% | 23.9% | 18 | 83.4 ms | 78.3% | visible |
| Home — idle, without cursor lens | 15.1% | 624 MB | 28.2% | 381 MB | 29.9% | 30.2% | 23 | 66.7 ms | 57.9% | visible |
| Home — idle, all four layers hidden | 15.3% | 638 MB | 23.3% | 403 MB | 35.6% | 26.4% | 21 | 116.6 ms | 50.1% | visible |
| Chats page | 13.5% | 585 MB | 31.5% | 306 MB | 31.0% | 34.2% | 58 | 17.0 ms | 1.0% | visible |
| Memory page | 12.0% | 586 MB | 27.6% | 300 MB | 21.0% | 29.7% | 57 | 17.5 ms | 1.3% | visible |
| Tasks page | 14.0% | 567 MB | 28.9% | 305 MB | 32.0% | 31.8% | 54 | 33.4 ms | 3.6% | visible |
| Models page | 15.8% | 569 MB | 37.1% | 306 MB | 26.3% | 38.6% | 59 | 16.9 ms | 0.5% | visible |
| Settings page | 14.0% | 561 MB | 29.4% | 302 MB | 24.9% | 32.8% | 58 | 17.0 ms | 1.1% | visible |
| Labs page | 12.9% | 557 MB | 29.0% | 301 MB | 33.5% | 30.4% | 56 | 33.4 ms | 3.7% | visible |
| Aura Domain | 18.3% | 699 MB | 50.4% | 421 MB | 30.4% | 52.5% | 49 | 33.5 ms | 10.7% | visible |
| Minimised (buddy still out) | 0.5% | 531 MB | 0.2% | 268 MB | 14.1% | 3.3% | 0 | — | — | hidden |

## Where it goes (per process)

| Scenario | main window | buddy window | gpu process | brain (python) | electron main | network | audio | utility | crashpad |
|---|---|---|---|---|---|---|---|---|---|
| Home — idle | 2.7% · 87 MB | 0.3% · 19 MB | 12.7% · 377 MB, 32% gpu | 0.2% · 93 MB | 0.3% · 29 MB | 0.0% · 8 MB | — | — | — |
| Home — thinking (simulated) | 2.8% · 87 MB | 0.1% · 20 MB | 12.5% · 379 MB, 26% gpu | 0.1% · 93 MB | 0.1% · 27 MB | 0.0% · 8 MB | — | — | — |
| Home — speaking (simulated, no audio) | 3.0% · 86 MB | 0.2% · 20 MB | 12.8% · 415 MB, 29% gpu | 0.1% · 93 MB | 0.1% · 27 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, buddy switched off | 2.5% · 83 MB | 0.0% · 18 MB | 12.7% · 415 MB, 27% gpu | 0.1% · 93 MB | 0.0% · 27 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, without background video | 2.4% · 100 MB | 0.2% · 21 MB | 12.6% · 407 MB, 25% gpu | 0.1% · 93 MB | 0.3% · 28 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, without particle field | 1.9% · 97 MB | 0.3% · 21 MB | 12.8% · 379 MB, 30% gpu | 0.2% · 93 MB | 0.2% · 28 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, without black hole | 1.8% · 99 MB | 0.1% · 21 MB | 12.1% · 371 MB, 21% gpu | 0.2% · 93 MB | 0.4% · 28 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, without cursor lens | 2.3% · 96 MB | 0.1% · 21 MB | 12.4% · 378 MB, 28% gpu | 0.1% · 93 MB | 0.2% · 29 MB | 0.0% · 8 MB | — | — | — |
| Home — idle, all four layers hidden | 2.0% · 113 MB | 0.2% · 21 MB | 12.5% · 373 MB, 23% gpu | 0.1% · 93 MB | 0.5% · 29 MB | 0.0% · 8 MB | — | — | — |
| Chats page | 2.0% · 94 MB | 0.1% · 22 MB | 10.8% · 339 MB, 32% gpu | 0.2% · 93 MB | 0.4% · 30 MB | 0.0% · 8 MB | — | — | — |
| Memory page | 1.6% · 99 MB | 0.1% · 22 MB | 9.9% · 334 MB, 28% gpu | 0.1% · 93 MB | 0.2% · 30 MB | 0.0% · 8 MB | — | — | — |
| Tasks page | 2.1% · 76 MB | 0.2% · 21 MB | 11.2% · 339 MB, 29% gpu | 0.1% · 93 MB | 0.4% · 29 MB | 0.0% · 8 MB | — | — | — |
| Models page | 2.1% · 72 MB | 0.2% · 22 MB | 13.1% · 341 MB, 37% gpu | 0.1% · 96 MB | 0.4% · 30 MB | 0.0% · 8 MB | — | — | — |
| Settings page | 1.9% · 75 MB | 0.1% · 22 MB | 11.4% · 329 MB, 29% gpu | 0.2% · 97 MB | 0.5% · 31 MB | 0.0% · 8 MB | — | — | — |
| Labs page | 1.7% · 73 MB | 0.1% · 22 MB | 10.6% · 327 MB, 29% gpu | 0.2% · 97 MB | 0.3% · 31 MB | 0.0% · 8 MB | — | — | — |
| Aura Domain | 3.0% · 79 MB | 0.1% · 22 MB | 14.7% · 461 MB, 50% gpu | 0.1% · 97 MB | 0.4% · 31 MB | 0.0% · 8 MB | — | — | — |
| Minimised (buddy still out) | 0.0% · 78 MB | 0.1% · 22 MB | 0.0% · 294 MB | 0.1% · 97 MB | 0.2% · 31 MB | 0.0% · 8 MB | — | — | — |

Cells: CPU % · RAM (· GPU % when it uses any).

## Busiest other processes

What else was using CPU meanwhile. dwm.exe is the Windows compositor — it works harder when AURA's window does; (this script) is the measuring itself.

| Scenario | Top other processes (CPU %) |
|---|---|
| machine idle (AURA closed) | svchost.exe 2.1%, Code.exe 1.9%, (this script) 1.3%, claude.exe 1.2%, System 1.2%, MsMpEng.exe 1.1% |
| Home — idle | (this script) 2.5%, Code.exe 2.5%, svchost.exe 2.2%, System 1.2%, dwm.exe 0.8%, comet.exe 0.4% |
| Home — thinking (simulated) | comet.exe 4.3%, (this script) 2.3%, svchost.exe 1.6%, System 1.4%, Code.exe 1.3%, GlobalPresenter.exe 1.2% |
| Home — speaking (simulated, no audio) | comet.exe 5.5%, (this script) 2.4%, svchost.exe 1.4%, Code.exe 1.2%, System 1.2%, GlobalPresenter.exe 0.8% |
| Home — idle, buddy switched off | comet.exe 3.3%, (this script) 2.0%, Code.exe 1.6%, System 1.3%, MemCompression 1.3%, svchost.exe 1.1% |
| Home — idle, without background video | comet.exe 6.5%, (this script) 2.1%, Code.exe 1.6%, svchost.exe 1.3%, System 1.2%, GlobalPresenter.exe 1.1% |
| Home — idle, without particle field | (this script) 2.1%, Code.exe 2.1%, comet.exe 1.8%, svchost.exe 1.3%, System 1.2%, dwm.exe 0.7% |
| Home — idle, without black hole | MsMpEng.exe 4.9%, comet.exe 4.3%, System 2.7%, svchost.exe 2.3%, Code.exe 2.2%, (this script) 2.1% |
| Home — idle, without cursor lens | comet.exe 3.1%, (this script) 2.1%, svchost.exe 1.3%, GlobalPresenter.exe 1.3%, System 1.2%, Code.exe 1.0% |
| Home — idle, all four layers hidden | msedgewebview2.exe 4.3%, (this script) 1.9%, Code.exe 1.8%, svchost.exe 1.6%, System 1.6%, comet.exe 1.5% |
| Chats page | comet.exe 2.5%, Code.exe 2.1%, (this script) 2.1%, System 1.9%, msedgewebview2.exe 1.7%, svchost.exe 1.6% |
| Memory page | (this script) 2.0%, comet.exe 1.1%, Code.exe 1.1%, svchost.exe 0.8%, System 0.8%, dwm.exe 0.7% |
| Tasks page | Spotify.exe 6.1%, (this script) 2.7%, System 2.0%, svchost.exe 1.3%, dwm.exe 1.1%, comet.exe 0.4% |
| Models page | (this script) 2.7%, svchost.exe 1.7%, System 1.0%, dwm.exe 0.9%, comet.exe 0.5%, steamwebhelper.exe 0.3% |
| Settings page | (this script) 2.3%, comet.exe 1.7%, dwm.exe 1.2%, svchost.exe 1.0%, System 1.0%, claude.exe 0.3% |
| Labs page | Code.exe 2.6%, (this script) 2.5%, svchost.exe 2.3%, comet.exe 1.6%, System 1.5%, dwm.exe 1.1% |
| Aura Domain | Code.exe 3.1%, (this script) 2.7%, System 1.6%, dwm.exe 1.1%, svchost.exe 0.9%, audiodg.exe 0.5% |
| Minimised (buddy still out) | Code.exe 2.4%, claude.exe 2.2%, svchost.exe 1.3%, (this script) 1.2%, System 1.1%, dwm.exe 0.7% |

## Compared with the baseline (written by hand)

After moving the black hole's glows onto small glow canvases, and pausing it while the Domain covers Home (`frontend/src/components/BlackHole.tsx`). Before → **after**, from `python tools/perf_baseline.py --compare docs/perf/2026-10-21-baseline.json docs/perf/2026-10-21-after-black-hole.json`:

| Scenario | FPS | AURA GPU | AURA CPU | AURA RAM | p95 frame |
|---|---|---|---|---|---|
| Home — idle | 6 → **26** | 85% → **32%** | 8.1% → **16.2%** | 642 MB → **612 MB** | 217 ms → **51 ms** |
| Home — thinking (simulated) | 5 → **20** | 84% → **26%** | 6.3% → **15.6%** | 649 MB → **614 MB** | 217 ms → **67 ms** |
| Home — speaking (simulated, no audio) | 5 → **19** | 82% → **29%** | 7.5% → **16.3%** | 691 MB → **649 MB** | 250 ms → **67 ms** |
| Home — idle, buddy switched off | 6 → **21** | 99% → **27%** | 11.7% → **15.4%** | 649 MB → **644 MB** | 217 ms → **67 ms** |
| Home — idle, without background video | 5 → **21** | 77% → **25%** | 6.3% → **15.6%** | 628 MB → **658 MB** | 250 ms → **67 ms** |
| Home — idle, without particle field | 5 → **25** | 83% → **30%** | 11.2% → **15.3%** | 600 MB → **625 MB** | 233 ms → **67 ms** |
| Home — idle, without black hole | 6 → **18** | 96% → **21%** | 11.4% → **14.7%** | 646 MB → **620 MB** | 234 ms → **83 ms** |
| Home — idle, without cursor lens | 6 → **23** | 94% → **28%** | 11.9% → **15.1%** | 651 MB → **624 MB** | 233 ms → **67 ms** |
| Home — idle, all four layers hidden | 5 → **21** | 80% → **23%** | 10.2% → **15.3%** | 675 MB → **638 MB** | 417 ms → **117 ms** |
| Chats page | 55 → **58** | 31% → **32%** | 15.6% → **13.5%** | 632 MB → **585 MB** | 33 ms → **17 ms** |
| Memory page | 50 → **57** | 27% → **28%** | 16.5% → **12.0%** | 618 MB → **586 MB** | 33 ms → **18 ms** |
| Tasks page | 56 → **54** | 28% → **29%** | 15.3% → **14.0%** | 622 MB → **567 MB** | 33 ms → **33 ms** |
| Models page | 48 → **59** | 38% → **37%** | 17.5% → **15.8%** | 620 MB → **569 MB** | 33 ms → **17 ms** |
| Settings page | 57 → **58** | 30% → **29%** | 14.9% → **14.0%** | 616 MB → **561 MB** | 33 ms → **17 ms** |
| Labs page | 57 → **56** | 30% → **29%** | 13.8% → **12.9%** | 615 MB → **557 MB** | 33 ms → **33 ms** |
| Aura Domain | 6 → **49** | 78% → **50%** | 8.0% → **18.3%** | 812 MB → **699 MB** | 217 ms → **34 ms** |
| Minimised (buddy still out) | 0 → **0** | 0% → **0%** | 0.3% → **0.5%** | 578 MB → **531 MB** | — → **—** |


1. **Home: 6 → 26 fps** idle (19–20 fps thinking/speaking), and the GPU drops from 85% to 32%. That is about the same GPU load as the pages, so the GPU is no longer the limit.
2. **Aura Domain: 6 → 49 fps.** The core no longer draws behind it. It also uses 113 MB less RAM.
3. **Pages unchanged** at 54–59 fps, as expected, since they never had the black hole.
4. **AURA's CPU went up (8% → 16% on Home)** because it now draws ~4× as many frames. The cost of each frame fell a lot, but there are many more of them.
5. **Home is still not smooth.** Frames now take ~33 ms (p50), against a 16.7 ms budget for 60 fps. The main window spends ~12 ms of CPU per frame (2.7% of the machine, at 26 fps). What's left is the black hole's per-frame drawing work itself: ~110 filaments, ~380 ring-dust dots, dashed orbits and ~45 gradients every frame. The look was checked against screenshots before and after (idle and speaking), and it is unchanged.
