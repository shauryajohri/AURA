# The Scrub Pipeline and Engineering Standard

This is the proven standard for the scroll-scrubbed hero and the quality floor around it. Use all of it, every time. Each rule either created the polish or prevented a bug that actually shipped and got caught.

## The hero structure

A tall pinned hero containing a sticky full-viewport stage. Scroll progress through the pinned region maps 0 to 1, and that progress drives the video's time. The page settles exactly when the video reaches its composed resting ending, and the real website begins there.

**Size the hero in scroll distance (vh), not seconds.** A Tier 1 single 6-second shot wants about 400vh of hero. A chained 18-second journey needs about 1000vh, so each beat gets room. Under-sizing a long journey makes every caption flash past no matter how well the bands are tuned; the pacing numbers live in the caption-band section below.

## Fetch the video as a Blob (the Range rule)

Many hosts silently lack partial-download (HTTP Range) support. Without it, every seek clamps to zero and scrubbing does nothing on the live site while working perfectly locally. Fetch the whole file as a Blob (the complete video held in memory) and play the object URL; it works everywhere.

For a small clip (under about 8 MB) the plain form is fine:

```js
const res = await fetch('assets/hero-scrub.mp4');
const blob = await res.blob();
video.src = URL.createObjectURL(blob);
```

Set the poster from JavaScript at the same time, inside the same code path that decides to load the video at all. That way phones and reduced-motion visitors, who get the static hero instead, never download either file.

### The streamed Blob with a loading ring (any video over about 8 MB)

A bare `await fetch().blob()` on a large chained video silently freezes the page's first impression: nothing visibly happens until the whole file lands. Over about 8 MB, stream it instead. The page is fully usable instantly, the poster shows first, an honest progress ring fills while the Blob streams, and the page is complete if the video never arrives.

The video element ships with `preload="none"` and no `src`. The ring is an SVG circle of radius 20 (circumference about 126), driven by one CSS variable:

```html
<video id="hero" preload="none" muted playsinline aria-hidden="true" tabindex="-1"></video>
<svg class="ring" viewBox="0 0 48 48" aria-hidden="true">
  <circle cx="24" cy="24" r="20" fill="none" stroke="currentColor" stroke-width="3"
          stroke-dasharray="126" style="stroke-dashoffset:var(--ld,126)"/>
</svg>
```

```js
const VIDEO_URL = 'assets/hero-scrub.mp4';
const VIDEO_BYTES = 14476000;   // hardcode the real byte size: the fallback when Content-Length is missing
const ring = document.querySelector('.ring');
const posterLayer = document.querySelector('.poster');

// 1. The poster wins the bandwidth race by design: paint it first,
//    and start the blob fetch only once the poster is in (or has failed).
posterLayer.style.backgroundImage = "url('assets/hero-poster.jpg')";
let started = false;
function startBlobFetch() {
  if (started) return;
  started = true;
  loadHeroBlob().catch(failVideo);
}
const posterImg = new Image();
posterImg.onload = startBlobFetch;
posterImg.onerror = startBlobFetch;
posterImg.src = 'assets/hero-poster.jpg';
setTimeout(startBlobFetch, 4000);   // safety: a hung poster never blocks the video forever

async function loadHeroBlob() {
  const ctrl = new AbortController();
  let watchdog = setTimeout(() => ctrl.abort(), 20000);
  // priority:'low' makes the blob yield to critical resources
  const res = await fetch(VIDEO_URL, { priority: 'low', signal: ctrl.signal });
  const total = Number(res.headers.get('Content-Length')) || VIDEO_BYTES;
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0, lastRing = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    clearTimeout(watchdog);                        // re-arm on every chunk:
    watchdog = setTimeout(() => ctrl.abort(), 20000);   // 20s with no progress aborts the stream
    chunks.push(value);
    got += value.length;
    const frac = Math.min(1, got / total);
    const now = performance.now();
    if (now - lastRing > 100 || frac === 1) {      // throttled to 100ms, but the terminal
      lastRing = now;                              // write always lands so the ring completes
      ring.style.setProperty('--ld', Math.round(126 * (1 - frac)));
    }
  }
  clearTimeout(watchdog);
  ring.style.setProperty('--ld', 0);
  video.src = URL.createObjectURL(new Blob(chunks));
  video.load();
  video.addEventListener('canplay', () => {
    requestSeek(heroProgress() * video.duration);  // land on the current scroll position
    stage.classList.add('video-ready');            // CSS fades the video in over the poster
  }, { once: true });
}

function failVideo() {
  ring.replaceWith(makeScrollChevron());  // an honest scroll cue, never a stuck ring
  stage.classList.add('video-failed');    // still-image fallbacks carry the full journey
}
```

The watchdog matters: without it, a hung stream freezes the ring forever, which is worse than no ring. With it, a stall for 20 seconds aborts into the still-image fallback and the site simply works as a still site.

The trade this pattern buys: even a chained journey weighing a dozen MB streams in quietly behind the ring over some seconds, while the page itself is usable almost instantly.

## Lerp the displayed time (a rAF loop that rests)

Never write scroll position straight into `currentTime`; ease toward it. The loop must go idle when converged and when the hero is off-screen. Loops that free-run from page load waste battery and mark the build as amateur.

```js
let target = 0;      // 0..1, set by the scroll handler
let shown = 0;       // what we are displaying
let rafId = null;
let lastTick = 0;

function tick(now) {
  const dt = Math.min(100, now - (lastTick || now));   // ms since last frame, capped
  lastTick = now;
  const k = 0.16;    // smoothing per 60fps frame; a starting point, tune by feel while scrubbing
  shown += (target - shown) * (1 - Math.pow(1 - k, dt / 16.667));
  if (Math.abs(target - shown) < 0.0005) {
    shown = target;
    rafId = null;
    lastTick = 0;                     // converged: rest
  } else {
    rafId = requestAnimationFrame(tick);
  }
  requestSeek(shown * video.duration);
  updateCaptions(shown);
}

function onScroll() {
  target = heroProgress();            // 0..1 through the pinned hero
  if (rafId === null && heroOnScreen) rafId = requestAnimationFrame(tick);
}
```

The `Math.pow` line is what makes the feel frame-rate independent: the exponent normalizes the smoothing to a 60fps reference, so every refresh rate converges at the same speed. A plain per-frame constant (`shown += (target - shown) * 0.18`) converges twice as fast on a 120Hz screen as on a 60Hz one, and the site feels different per machine.

Track `heroOnScreen` with an IntersectionObserver so the loop never runs while the hero is scrolled past.

## Gate the seeks (the deadlock-safe pattern)

Never write `currentTime` while a previous seek is still in flight. Un-gated seeks pile up and this is the difference between smooth and choppy in Chrome. Coalesce to the newest target, issue exactly one follow-up when the seek completes, and reset the busy flag on error so the gate can never deadlock:

```js
let seekBusy = false;
let pendingTime = null;

function requestSeek(t) {
  if (!video.duration) return;
  if (seekBusy) { pendingTime = t; return; }   // coalesce: keep only newest
  seekBusy = true;
  video.currentTime = t;
}

video.addEventListener('seeked', () => {
  seekBusy = false;
  if (pendingTime !== null) {
    const t = pendingTime;
    pendingTime = null;
    requestSeek(t);                            // exactly one follow-up
  }
});

video.addEventListener('error', () => {        // the deadlock escape
  seekBusy = false;
  pendingTime = null;
});
```

Under stress this pattern produces one completion per seek and zero overlaps. If scrubbing still feels rough with gating in place, the video's keyframe interval is too long: re-encode with `-g 8` (see `ffmpeg-recipes.md`).

## Write to the DOM only on change

Per-frame DOM writes are the other half of choppy. Delta-gate everything:

- Captions, scrims, and state classes: compute the desired state, compare against a cached value, and touch the DOM only when it differs. Never toggle a class every frame.
- Any text that updates with scroll (counters, depth readouts, progress labels): throttle to about 10Hz AND only write when the string actually changed.

```js
let lastLabel = '';
let lastLabelAt = 0;

function updateLabel(text, now) {
  if (now - lastLabelAt < 100) return;   // ~10Hz
  if (text === lastLabel) return;        // only on change
  lastLabel = text;
  lastLabelAt = now;
  labelEl.textContent = text;
}
```

Promote the video to its own compositor layer (`will-change: transform` or `transform: translateZ(0)` on the video element) so its repaints never drag the rest of the page.

## The caption-band pattern (paced in scroll distance)

Each caption owns a band of scroll progress, for example `[0.12, 0.30]`. Captions live in the footage's negative space, planned back in the concept phase, and the action lane stays clear. Nothing snaps.

Pace every band in vh (viewport heights of scroll), never in seconds, because a scroll site is read in flicks. The standard:

- **Every beat gets a fully-visible plateau of roughly 80 to 130vh**, with eased ramps of around 20vh at each edge. Starting points, validated by the flick test below. The plateau is most of the band; the ramps are trim.
- **Compute the ramps in progress units.** For a band `[a, b]`: `const f = Math.min(0.02, (b - a) / 3)`. On a 900vh scroll range (scroll range = hero height minus the 100vh viewport), 0.02 of progress is 18vh.
- **Opacity** uses smoothstep at both edges:

```js
const smoothstep = (p, e0, e1) => {
  const t = Math.min(1, Math.max(0, (p - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};
const f = Math.min(0.02, (b - a) / 3);
const opacity = smoothstep(p, a, a + f) * (1 - smoothstep(p, b - f, b));
```

The first band skips the ease-in and the last band skips the ease-out, so the journey starts and ends with text already settled.

- **Text assembly progress** (the `--k` variable the choreography section below runs on) settles roughly 20vh into the band, leaving the long fully-settled plateau:

```js
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const k = clamp((p - a) / (ramp || Math.min(0.025, (b - a) * 0.35)), 0, 1);
```

`ramp` is the band's optional `data-ramp` override, described in the choreography section. Apply all of it with delta-gated writes, like every other scroll-driven DOM touch.

**The flick test (how a beat map is validated):** simulate wheel steps of 120px (a normal flick), 240px, and 360px (an aggressive double-flick). Every beat must remain readable for 5 to 6 normal flicks, and no beat may be skippable even at 360px steps. Slow dragging proves nothing; real visitors flick. If a caption fails the test, merge it into a neighbor. Never shrink the ramps to squeeze a failing beat in.

The harness is a small loop run on the page through the browser tool (or pasted into the console), one step size per run:

```js
// flick(120, 12), then flick(240, 8), then flick(360, 6). Start from the top each run.
async function flick(step, count) {
  for (let i = 0; i < count; i++) {
    window.scrollBy(0, step);
    await new Promise(r => setTimeout(r, 400));   // a beat between flicks, like a real reader
    const bands = [...document.querySelectorAll('.band')]
      .map((b, n) => n + ':' + getComputedStyle(b).opacity);
    console.log('y=' + Math.round(scrollY), bands.join('  '));
  }
}
```

Read the logged opacities between steps. A band that never reaches full opacity anywhere in the 360px run is a skippable beat. A band that holds full opacity for fewer than 5 consecutive 120px steps is too short to read.

## The legibility system (text over live footage)

Law 10 in `prompt-laws.md`: live video behind type is a moving background you do not control frame to frame. Every hero text band gets all four layers below, then passes the audit.

**1. The global base scrim.** One soft radial darkening (a scrim is a translucent dark layer) over the whole video, always on, so no frame is ever raw behind the page:

```css
.scrim{position:absolute;inset:0;pointer-events:none;background:radial-gradient(ellipse 120% 90% at 50% 45%,rgba(10,10,18,0) 35%,rgba(10,10,18,.62) 100%)}
```

**2. The per-band scrim.** Each band's `::before` carries a radial scrim that rides the band's JS-driven opacity and deepens with the band's `--k` progress variable, so the footage dims exactly while that band's text is on and nowhere else. Dim, never flatten: the gradient dies out by 76 percent so the corners stay live. The working shape:

```css
.band::before{content:"";position:absolute;inset:-4%;pointer-events:none;opacity:calc(.25 + .75*var(--k,1));background:radial-gradient(ellipse 74% 62% at 50% 50%,rgba(5,5,10,.66) 0%,rgba(5,5,10,.44) 46%,rgba(5,5,10,0) 76%)}
```

Tune the peak alpha per band against that band's actual frames. The proven range: 0.62 for quiet beats up to 0.72 for the hook. These peak alphas are also the constants to nudge when the user asks for the footage to read brighter.

**The two-sided variant for centered-action compositions.** The single centered radial above assumes the subject sits off-center with the text flanking it. When the subject is centered and text columns sit on BOTH sides of it (a natural request), never stretch one scrim across the middle. Use two: one pseudo-element anchored on the left column and one on the right, each an ellipse centered on its own column, with the center lane left completely alone so the subject stays bright. The settle band, where the columns converge, gets a single upper-centered ellipse instead. This variant is not a compromise: a real build measured 7.17 to 1 worst-pixel contrast with it.

**3. The text-shadow token.** Three layers (a tight edge, a mid glow, a wide falloff), applied to every hero band and turned off on buttons, where a shadowed label reads as grime:

```css
:root{--tshadow:0 1px 2px rgba(5,5,10,.95),0 3px 12px rgba(5,5,10,.78),0 10px 44px rgba(5,5,10,.8)}
.band{text-shadow:var(--tshadow)}
.band .btn{text-shadow:none}
```

**4. The chip scrim for small text.** HUD lines, readouts, and small labels over footage do not get the big radial. They get a chip, a small blurred backing pill:

```css
.chip{background:rgba(8,8,15,.55);border:1px solid rgba(96,96,126,.3);border-radius:10px;backdrop-filter:blur(10px);text-shadow:0 1px 3px rgba(5,5,10,.85)}
```

**The worst-frame audit (what makes the system honest).** Extract each band's frames, canvas-sample the pixels under the text zone WITH the scrim applied, and require worst-pixel contrast of at least 3.5:1 for every band. Well-tuned bands land well clear of that floor. Tune scrim alphas against the worst frame, never the average. The average frame lies; the worst frame is the one a visitor will be mid-read on.

**The preferred method, when a controllable browser exists** (the headless Chrome route in `troubleshooting.md`): inject `visibility: hidden` on the split text spans, screenshot the real composited page at that scroll position, and find the lightest pixel inside the text's bounding box. This measures every scrim layer and the radial falloff exactly as the visitor sees them, and it is conservative, because hiding the glyphs also removes their text shadow. The frame-plus-math procedure below is the fallback when no browser can be driven.

The procedure, concretely:

1. Convert each band's range to video time (`time = progress * duration`) and extract three or four frames across it with ffmpeg: `ffmpeg -ss <t> -i assets/hero-scrub.mp4 -frames:v 1 review/band2-a.png`.
2. For each frame, composite the band's scrim at its peak alpha over the text zone and find the worst pixel. For light text that is the lightest surviving pixel. This snippet does the whole step:

```js
// auditFrame('audit/band2-a.png', {x:420,y:300,w:600,h:200}, 0.66, [244,242,236])
// zone is the text's pixel box in the frame, alpha is the band scrim's peak, textColor is RGB
async function auditFrame(src, zone, scrimAlpha, textColor) {
  const img = await createImageBitmap(await (await fetch(src)).blob());
  const c = new OffscreenCanvas(img.width, img.height).getContext('2d');
  c.drawImage(img, 0, 0);
  const d = c.getImageData(zone.x, zone.y, zone.w, zone.h).data;
  const lum = ([r, g, b]) => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const scrim = [5, 5, 10];                      // the scrim's base color
  let worst = 0;
  for (let i = 0; i < d.length; i += 4) {
    const px = [0, 1, 2].map(j => d[i + j] * (1 - scrimAlpha) + scrim[j] * scrimAlpha);
    worst = Math.max(worst, lum(px));            // lightest pixel, the worst case for light text
  }
  const lt = lum(textColor);
  const hi = Math.max(lt, worst), lo = Math.min(lt, worst);
  return (hi + 0.05) / (lo + 0.05);              // must be at least 3.5
}
```

Run it through the browser tool on the previewed page. If fetching from `review/` is blocked, copy the frames into `assets/audit/` for the audit and delete that folder before anything is zipped.

3. Every band's returned ratio must be at least 3.5:1. A failing band gets a deeper peak alpha on its scrim, then a re-audit against the same worst frame.

## Text choreography (an entrance personality per beat)

**The echo principle:** every hero beat gets its own entrance, and the entrance echoes what the footage is doing at that moment. Words drift down while something falls. A word punches in as an impact lands. Characters scatter-assemble while ink gathers. Entrance and footage read as one event, which is what makes the page feel directed instead of decorated.

The engineering is the fixed part, for every entrance including ones you invent: all effects are `transform` and `opacity` only, scroll-scrubbed off the band's `--k` custom property (0 to 1 assembly progress, written by the drive loop and delta-gated at 0.008 so converged bands cost nothing), and fully reversible (scroll up and they disassemble; band one's one-time load ramp is the single designed exception).

**The first band opens settled, characters included.** The band pattern above already skips band one's opacity ease-in, but that alone is not enough: at scroll zero the band's `--k` is still 0, so its characters sit unassembled and the hero opens on footage with no words until the user scrolls. Give band one a one-time, time-based assembly ramp on load that hands over to scroll: drive its entrance with `k = max(scrollK, loadK)`, where `loadK` eases from 0 to 1 over the first moments after the page appears. Once `loadK` reaches 1 the max holds band one assembled, which is right for the opening beat: there is nothing above it to scroll back to. Every later band stays purely scroll-driven and reversible.

**Splitting, done once at load.** Split headline text into word and character spans in JS with a seeded pseudo-random generator, so the "random" offsets are identical on every load:

```js
function rng(seed) {
  let s = seed >>> 0;
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
}
```

Wrap a visually-hidden span holding the full sentence for screen readers, plus an `aria-hidden="true"` visual copy built of `.w` word spans containing `.c` character spans. Assign each span its custom properties (`--th`, `--jx`, `--jy`, `--jr`) from the seeded generator at split time.

**The menu (worked examples, each named with the footage moment it echoes):**

**(a) Scatter.** Per-character fly-in from seeded random offsets; echoes ink gathering, particles assembling, debris settling. Each `.c` gets `--th` (a random threshold, 0 to 0.55) and `--jx`/`--jy`/`--jr` jitter values:

```css
.c{--kc:clamp(0,(var(--k,0) - var(--th,0))*2.6,1);opacity:var(--kc);
   transform:translate(calc((1 - var(--kc))*var(--jx,0px)),calc((1 - var(--kc))*var(--jy,0px)))
             rotate(calc((1 - var(--kc))*var(--jr,0deg)))}
```

**(b) Grid snap-align.** Characters slide horizontally into place in reading order. Same CSS as scatter with horizontal-only jitter, but the threshold is ordered instead of random: `--th: charIndex / total * spread + rng() * 0.06`, so the spread value controls how long the stagger runs.

**(c) Blur-to-sharp.** The entrance for the quiet beat; echoes mist clearing or focus arriving. Two stacked copies of the text crossfaded by opacity only. The soft copy carries a STATIC `filter: blur(10px)`; never animate `filter` itself, it is not compositor-friendly. The sharp copy fades in with `--k`, the soft copy fades out.

**(d) Word-punch with overshoot.** Echoes an impact landing. Word-level pop (`--kc`) and a slower settle (`--ks`); the word scales past 1 and eases back:

```css
.w{--kc:clamp(0,(var(--k,0) - var(--th,0))*3,1);
   --ks:clamp(0,(var(--k,0) - var(--th,0) - var(--sd,.1))*var(--ss,3.2),1);
   opacity:var(--kc);
   transform:scale(calc(0.6 + (0.4 + var(--ov,.12))*var(--kc) - var(--ov,.12)*var(--ks)))}
.w.em{--ov:0.24;--sd:0.16;--ss:2.6}
```

Emphasized words (`.em`) get the bigger overshoot with the later, slower settle, so they hang in the overshoot a beat longer.

**(e) Word-by-word rise into a staged settle.** The proven ending entrance, matching the footage's arrival at rest. Headline words rise in reading order (`--th` per word), then the subline fades via `--ks: clamp(0, (var(--k) - 0.66) * 4, 1)`, then the CTA row via `--kb: clamp(0, (var(--k) - 0.78) * 5, 1)`. Three arrivals, one band.

**(f) Drift-down.** Echoes a fall or a pour. Each word starts above its resting spot and drifts down into place:

```css
.w{--kc:clamp(0,(var(--k,0) - var(--th,0))*2.8,1);opacity:var(--kc);
   transform:translateY(calc((1 - var(--kc))*-24px))}
```

**(g) Approach-from-depth.** Echoes a tunnel or a forward push. The line starts slightly small and grows into place as if approaching the camera: `transform: scale(calc(0.82 + 0.18 * var(--kc)))` with opacity riding `--kc`. Stack a static-blur soft copy under it (the blur-to-sharp pattern) when the approach should also sharpen.

**(h) Halves parting.** Echoes folds opening or curtains parting. Split the headline into two halves; each starts pulled toward the center line and slides outward to rest as `--kc` rises, opposite signs of `--jx` per half.

**(i) Weave.** Echoes threads crossing or strands interleaving. Characters arrive alternating from above and below: the scatter CSS with vertical-only jitter and `--jy` signs alternating by character index.

**This menu is examples, not a closed set.** Inventing a new entrance to fit this footage is the job. Take the moment the band sits on, ask what the footage is physically doing, and build the entrance that does the same thing to the words. Every invention keeps the fixed part: transform and opacity only, scrubbed off the band's `--k`, fully reversible on scroll-up (band one's one-time load ramp is the single designed exception).

**The control pattern (tune a beat without touching band math):** each band takes two optional HTML attributes. `data-ramp` overrides the default assembly window (the default is `Math.min(0.025, bandLength * 0.35)` of progress; `data-ramp="0.036"` savors an assembly about 50 percent longer). `data-spread` sets the character-stagger spread for scatter and grid entrances. Any beat's feel is tuned from its markup, and the drive loop never changes.

## The static-hero gate (five conditions, in CSS AND JS)

Some visitors get a composed static image hero instead of the scrub. The five gates, and they must match EXACTLY in the CSS media queries and the JavaScript decision, or one side loads assets the other side hides:

1. Phones: `(max-width: 720px)`
2. Portrait tablets: `(orientation: portrait) and (max-width: 1024px)`
3. Coarse-pointer portrait: `(orientation: portrait) and (pointer: coarse)`
4. Landscape phones: `(orientation: landscape) and (pointer: coarse) and (max-height: 560px)` (a phone held sideways passes every width check but has no room for the journey)
5. Reduced motion: `(prefers-reduced-motion: reduce)`

**The gate is decided live, not once at load.** The CSS media queries re-evaluate on every rotation, resize, and preference flip. A one-shot JS check leaves a blank multi-viewport hero the moment a tablet rotates from portrait to landscape, a snapped window gets maximized past 720px, or reduced motion is switched off mid-session: the CSS un-hides the scrub stage, but no poster, no video, and no scroll listener exist on the JS side. Wire the change event of all five queries to one function that arms and disarms the scrub:

```js
const GATES = [
  '(max-width: 720px)',
  '(orientation: portrait) and (max-width: 1024px)',
  '(orientation: portrait) and (pointer: coarse)',
  '(orientation: landscape) and (pointer: coarse) and (max-height: 560px)',
  '(prefers-reduced-motion: reduce)'
];
let scrubOn = false;
function enableScrub(){
  if (scrubOn) return; scrubOn = true;
  initHeroOnce();                       // wrap the poster paint and the startBlobFetch flow from the Blob loader section above in one run-once function; this call is that wrapper
  addEventListener('scroll', onScroll, {passive:true});
  bands.forEach(b => { b.op = -1; b.k = -1 });   // reset caches so stale pinned styles get rewritten
  unpinFinalStates();                   // undo whatever pinToFinalStates applied, so lines, counters, and holds go back to being scroll-driven
  updateCaptions(heroProgress());
  onScroll();                           // re-seek the video to the current scroll position; without this the frame sits stale until the user scrolls
}
function disableScrub(){
  if (!scrubOn) return; scrubOn = false;
  removeEventListener('scroll', onScroll);
  if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
}
function applyHeroMode(){
  if (GATES.some(q => matchMedia(q).matches)) disableScrub();
  else enableScrub();
}
const MQLS = GATES.map(q => matchMedia(q));   // keep the query lists referenced; unreferenced ones have historically lost their listeners in old browsers
MQLS.forEach(m => m.addEventListener('change', applyHeroMode));
applyHeroMode();
```

All five strings must be character-for-character identical in both places, and the poster and Blob fetch still live ONLY inside the gated path.

A related guard for scrub-capable screens that are merely short (a shallow desktop window, not a phone): keep the scrub but hide whatever small scroll-driven overlays the page has (cues, readouts, tickers), which have no room. An example with one build's class names; use your own:

```css
@media (max-height:560px){.cue,.hud,.feed{display:none}}
```

The static hero is a designed layout, not a fallback apology: the poster or ending frame composed with the captions visible. A mobile decision is made consciously per project. Static hero is the default. Consider a cover-cropped mobile scrub only when all three hold: the encoded video is small (under about 8 MB), the composition still reads when cover-cropped to portrait (the action lane survives the crop), and the result is verified on a real phone. When any of the three fails, ship the static hero proudly.

## Complete without the video

The page must be complete and beautiful if the video never loads. Wire the video's `error` event to hide the dead video element over the poster background. Every caption, every section, and the call to action must work with a still image behind them. Test this state on purpose by renaming the video file and loading the page.

## The motion system around the hero

- **Nothing snaps.** Every appearance, hover, and state change eases. Define two easing curves as tokens and use them everywhere. Even the page itself eases in.
- **Entrances are choreography.** IntersectionObserver adds an `.in` class; children arrive in sequence with 60 to 150ms stagger steps. Entrance start and end states must be prefixed with the container class (`.card .part`, `.card.in .part`) so they win the cascade; a later rule can otherwise silently cancel the animation. And when the entrance is done, RETIRE the stagger delays: the cleanup rule that zeroes `transition-delay` must match or beat the specificity of the nth-child delay rules it retires (`:nth-child` counts as a class), or it silently never applies and every hover on the later siblings lags by the stagger forever. Prove the retirement by hovering the second and third items after the entrance finishes.
- **Never put a dynamic style on an element that also has a `forwards` entrance animation.** The animation's final value wins permanently. Entrance on the parent, dynamic style on a child.
- **One living element per section** at whisper level after its entrance: a slow cycle or soft glow pulse, four seconds or longer. Give looping animations negative delays (like `-1.2s`) so they are mid-cycle at first paint. Pause them off-screen by scoping the animation rules to a class an IntersectionObserver toggles, and pause everything on hidden tabs with one body class. `animation-play-state` is not an inherited property, so setting it on a container silently never reaches nested elements or pseudo-elements. The pattern that cannot miss: `body.paused *, body.paused *::before, body.paused *::after { animation-play-state: paused !important }`, toggled on `visibilitychange`.
- **One designed interactive moment per site.** Designed, not decorative; the proven shape has its own section below.
- **Animate only `transform` and `opacity`.** For glow pulses, put the shadow on a pseudo-element at full strength and animate its opacity.
- **Masked text needs descender room:** any `overflow: hidden` reveal gets em-based padding/negative-margin breathing room or g, y, and p get their tails cut.
- **Never overwrite `el.style.transition` in JavaScript.** Toggle a class that declares the full combined transition.

## The one interactive moment (the proven shape)

One per site, on-theme, performed mid-journey. The shape that has worked repeatedly: an action that mirrors the product's own story. A press-and-hold that lets a scent settle. A press-and-hold that pulls a thread and stitches a seam closed. The visitor does not just read the brand's one idea; they perform it.

The mechanics that make it feel designed rather than gimmicky:

- Progress builds while the visitor holds.
- Releasing early eases the progress back down; it never snaps to zero.
- Completing it lights up the section's content in sequence, so the visitor's action earns something real.
- Reduced motion gets the instant final state, no hold required.

The hold is an example, not a law. Any interaction works if it enacts the brand's one idea.

## Overflow and reduced motion

- `overflow-x: clip` on BOTH `html` and `body`, with `hidden` declared first as a fallback. `hidden` alone still lets code scroll the page sideways, and one anchor link can leave the whole page shifted.
- Reduced motion is honored COMPLETELY: kill animations and transitions on elements and on `::before`/`::after`, zero every `transition-delay`, show every choreographed element in its final finished state, and re-apply positional transforms per breakpoint (a blanket `transform: none !important` can throw a mobile-positioned element off screen). The video is not loaded at all (it is one of the five static-hero gates).
- Reduced motion is honored LIVE, in BOTH directions. Listen for the media query's change event. On a flip in, pin every scroll-drawn element to its final drawn state and stop the JS drives: self-drawing lines finish, counters jump to their targets, hold interactions complete. On a flip back out, re-arm the scrub through the same gate function the five queries use, so the caches reset and the captions recompute instead of staying pinned. And undo everything pinToFinalStates applied: remove the pinned classes or inline styles from the drawn lines, the counters, and the hold interactions, so the scroll drives own them again. Re-arming the hero while leaving the rest of the page pinned is the half-fix that looks done and is not.

```js
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', e => {
  if (e.matches) pinToFinalStates();   // lines drawn, counters at target, holds done, drives stopped
  else applyHeroMode();                // motion is back: re-arm the scrub, never leave the pins behind
});
```

## Design direction (what expensive means)

The engineering floor keeps the site from breaking. This bar keeps it from looking like AI made it:

- **Commit to ONE direction pulled from the subject's world** and let it drive palette, type, motion, and imagery together, so the page and the footage read as one world.
- **Invent one signature element** unique to this site and spend the boldness budget there. Everything else stays quiet so the signature reads. Then test its loudness: if the signature were removed, would the page meaningfully change? If it would barely change, it is not a signature. Spend the boldness budget on something whose absence would be noticed.
- **No two adjacent sections share a layout skeleton.** If two neighbors both open kicker, headline, lede over the same grid, reshape one. A visitor should never feel the same template stamped twice in a row.
- **Ban the looks that scream "AI made this,"** unless the user explicitly briefs one: cream canvas with a serif and terracotta accent, near-black with acid-green, near-black with a warm amber accent and a high-contrast serif (the next default down whenever anyone says dark, rich, or cinematic), and hairline-border brutalism. One carve-out: these are banned as default reaches, not as subjects. When one of them genuinely IS the subject's own material world (a pottery studio really does live in cream and terracotta), committing to the subject's world wins. Earn it: sample the tones from the footage itself, invent the signature element, and stay clear of the stock template layout, so the page reads as this brand's world and not the default look. Say the deviation out loud.
- **The accent appears in rare doses:** the call to action, focus states, and one or two moments of emphasis. An accent that is everywhere is not an accent.
- **The canvas is never pure `#000` or `#fff`.** Tint it toward the footage's grade.
- **Make the page one environment:** one fixed background layer behind everything (a slow drift, grain, or soft glow in the footage's world), cycling at 60 seconds or longer, so scrolling feels like moving through a place instead of past stacked sections.

## The quality floor (all of it, every time)

- Fonts trimmed to only the weights in use, with `preconnect`. Display face with real character, quiet body face, mono for small labels. Never Inter or Roboto as display.
- Size text blocks in `ch` units on the text element itself, never on a container. A `ch` resolves against the font the element inherits, not the display face inside it, so a container's `ch` cap is measured in the wrong font. Containers get `px` or `min()`. A real build capped a settle block to the body font's `ch` and the headline broke to three lines.
- Real contrast on the canvas: compute it, don't guess. 4.5:1 body text, 3:1 large text and interface borders. Hairline colors usually fail for interactive borders; give those their own stronger value.
- Semantic landmarks: `<nav>`, `<main id="main" tabindex="-1">`, `<footer>`, a skip link to `#main`, a real heading hierarchy, and `aria-hidden="true"` on decorations.
- The scrub video is decorative, so treat it that way: `aria-hidden="true"` on the video element, no `controls` attribute, and keep it out of the tab order (`tabindex="-1"` on the video, or `inert` on the sticky stage's decorative layer) so screen reader and keyboard users land on the captions and content instead.
- `:focus-visible` styled in the accent. Touch targets at least 44px under `(pointer: coarse)`, added without changing layout: `@media (pointer:coarse){ .btn { min-height:44px; display:inline-flex; align-items:center; justify-content:center } }`. Never swap an element's display type without re-declaring its alignment; a bare `display:inline-flex` left-aligns button labels and shrinks full-width rows to their text.
- Real `<title>`, meta description, `theme-color`, and an inline SVG favicon of the brand mark.
- `og:image` and `og:url` need absolute URLs, which do not exist until deploy. Leave a clearly marked `<!-- DEPLOY STEP -->` comment and patch them with the live URL at deploy time (see `deploy.md`).
- Decorations never collide with content: absolutely positioned elements get reserved space and hide on short screens with a `max-height` media query.
- Rows of text align on the baseline (`align-items: baseline`), not centered boxes.

## The self-testing checklist (run before showing the user anything)

Audit adversarially. Prove it, don't assume it:

1. Screenshot the built site at desktop size and at phone widths (375px wide at minimum; check 1280x800, 1440x900, 375x812, 375x667).
2. Exercise every button and link. Submit the form and confirm its response state.
3. Scrub the hero at the top, the middle, and the bottom. Then scrub fast. Watch for choppiness, especially in Chrome.
4. Run the flick test on the beat map: wheel steps of 120px, 240px, and 360px. Every caption readable for 5 to 6 normal flicks, no beat skippable at 360px.
5. Run the worst-frame legibility audit: every band's worst pixel under the text, with the scrim applied, at 3.5:1 contrast or better.
6. Prove every entrance actually plays (cascade order can silently kill them).
7. Try to force the page sideways: anchor links, wide decorations, narrow widths.
8. Run with reduced motion on: final states visible, no video request made. Then flip reduced motion ON while the page is open, not just before loading it: every scroll-drawn element pins to its final state and the JS drives stop.
9. Load with the video missing: page still complete over the poster.
10. Check the browser console at desktop and phone sizes: zero errors.
11. Check letter tails (g, y, p) in every masked or clipped text at 100 percent zoom.
12. **The fresh-eyes pass, last.** Put the checklist down and look at the page as a first-time visitor with zero context. Does every element have its place, or does anything float unexplained? Is any parallel element unequal: a step without an image, a card styled differently from its siblings? Does the page read as premium and custom-made for this one brand, or does any stretch read as filler? Fix what the fresh eye catches before the user ever sees it. This is a different act from auditing, and it catches what audits cannot.

**When a controllable browser exists, run the real checks, not approximations.** The headless Chrome route in `troubleshooting.md` gives full control of a real browser, and four of the checks above can only be tested genuinely that way: touch emulation makes `(pointer: coarse)` actually match, the only true test of three of the five static-hero gates; emulated media flips `prefers-reduced-motion` live mid-session, the only true test of the both-directions requirement in step 8; blocking the video's URL with `Network.setBlockedURLs` tests complete-without-video without renaming any file; and a real mouse press and release, with a gap between them, tests the press-and-hold moment as a visitor performs it.

If the environment can field independent reviewers (a second agent, a fresh pair of eyes), aim them at the finished build as well. The checklist proves what you thought to check; adversaries find what you did not think to.

Report what you found and what you fixed. The user's last check is theirs, but they should never be the one to find your bugs.
