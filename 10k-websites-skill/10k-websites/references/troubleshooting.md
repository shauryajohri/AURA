# Troubleshooting: Symptom → Cause → Fix

Every entry happened in a real build. Check here before inventing a diagnosis.

## Generation

| Symptom | Cause | Fix |
|---|---|---|
| Generator suggests a preset instead of generating | It pattern-matched your prompt to a house style | Decline it and retry with your literal prompt; your designed shot beats a house style |
| A real logo or brand mark appears in the generated image | AI slipped a trademark in | Fix with a cheap image edit before animating; never animate a trademarked frame |
| The transformation "looks like two separate videos" | The trajectory broke at the swap | One unbroken vector through the transition (same heading, position, speed), or better, choose a single-subject concept |
| The subject looks frozen or lifeless | The prompt over-stabilized it to protect the path | Lock the path, free the body: keep the trajectory rigid but demand natural motion on the subject and ambient life in the scene |
| A boundary crossing (into water, through glass) looks fake | The pass was too clean | Write the physical lens moment into the prompt: splash, droplets on the lens, a beat of blur |
| The hero product reads as a placeholder | Generic unbranded object at distance | Apply the brand mark via image editing before animating, or write the ending to land close enough that the design carries it |
| Three failed videos on one concept | Concept problem, not prompt problem | Stop iterating the prompt and pivot the concept; the laws predict which concepts land first-try |
| The shot is strong but the ending will not rest (the subject drifts back into motion near the end) | The model overshot the composed arrival and kept animating | Do not re-roll first. Trim the raw to the last steady frame and scrub-encode in one pass (recipe in `ffmpeg-recipes.md`); the page runs on progress, not seconds, so a shorter clip costs nothing |
| The chained journey glitches at a segment join | Segment encode parameters were not identical, or the motion vector broke between segments | Re-encode every segment with the exact same scrub command and re-concat; if the motion itself jumps, the next segment's prompt did not continue the previous heading and speed |
| A visible cut where two chained segments meet, even though the motion continues | Each generation re-imagines fine texture from its start frame, so a rest-to-rest join on specific texture (weave, grain, skin) shows as a cut | Next time, storyboard every seam into motion or a texture-refresh moment (the seam law in `prompt-laws.md`); for the chain you already have, use the crossfade join in `ffmpeg-recipes.md` |
| A job comes back flagged nsfw on an innocent abstract shot | The safety filter misread abstract sensory language (glowing forms, flowing liquid around a shape) | Verify the balance first: flagged jobs are not charged. Then re-roll the same start frame with the prompt rewritten in plain commercial product-photography words: name the product early, describe objects not sensations, keep the same shot design |

## The scrub hero

| Symptom | Cause | Fix |
|---|---|---|
| Scrubbing does nothing on the live site but works locally | Host lacks partial-download (Range) support, so seeks clamp to zero | Fetch the video as a Blob and play the object URL (see `scrub-pipeline.md`); works everywhere |
| Scroll feels choppy at the hero's top and bottom, worse in Chrome | Un-gated seeks piling up plus per-frame DOM writes | Seek gating and delta-gated writes (see `scrub-pipeline.md`) |
| Still choppy after gating and delta-gating | The video's keyframe interval is too long | Re-encode with `-g 8 -keyint_min 8` (see `ffmpeg-recipes.md`) |
| Scrubbing freezes permanently mid-scroll | The seek-busy flag deadlocked (a seek errored and never fired `seeked`) | Reset the flag and clear the pending target in the video's `error` handler; the deadlock-safe pattern is in `scrub-pipeline.md` |
| Phones download the video or poster they never show | Poster set in HTML, or the video load not behind the static-hero gate | Set the poster via JavaScript inside the same gated code path that loads the video |
| The static hero appears on desktop, or the video loads on phones | The five gate conditions differ between CSS and JS | Make the five media queries match EXACTLY in both (see `scrub-pipeline.md`) |
| The page is broken when the video fails to load | No error path | Hide the dead video over the poster background on `error`; the page must be complete without the video |
| Screenshots of the running site show the poster or a blank stage where the scrubbing video should be, but the site works in a real browser | The video's promoted compositor layer does not composite into embedded-browser screenshots | Verify scrub behavior through the DOM instead of pixels: probe the band `--k` variables, word opacities and transforms, and `currentTime` at several scroll positions, or watch it in a real browser window. A blank screenshot of a promoted layer is not a broken site |
| The page looks completely dead in the preview: poster never set, every caption band at opacity 0, the video never seeks, and the pane reports it is hidden | A hidden or non-displayed preview pane stops compositing, so `requestAnimationFrame` never fires. Everything in the scrub hero is driven by that loop, so the DOM freezes too. The DOM-probing advice in the row above cannot help here, because the DOM itself is frozen | Stop using the pane and drive the machine's own installed Chrome headlessly; the full recipe is right below this table |
| The hero goes blank (no poster, no captions) after rotating the device or resizing the window | JS decided static-versus-scrub once at load while the CSS gates stayed live | Arm and disarm the scrub from change listeners on all five gate queries; the live-gate pattern is in `scrub-pipeline.md` |
| Double-clicking `index.html` shows the still hero and the video never loads | Browsers block `fetch` on file:// URLs, so the Blob loader falls back by design | That state is the designed fallback and must look complete. For the full scrub preview, serve the folder with any one-liner (`npx http-server`, `python -m http.server`) and open localhost; the live host serves the scrub normally |

### The headless Chrome recipe (when the preview pane is dead)

When the preview pane itself is hidden or broken, verify through the machine's own installed Chrome instead, driven headlessly over the DevTools protocol (the remote-control channel every Chrome ships with). It needs no installs and no packages:

1. Launch Chrome with `--headless=new --disable-gpu --remote-debugging-port=9222 --user-data-dir=<a temp folder> --hide-scrollbars`.
2. From Node (version 22 and later ships a global WebSocket, so this takes zero dependencies): GET `http://127.0.0.1:9222/json/list`, take the target's `webSocketDebuggerUrl`, and connect to it.
3. Over that socket, drive the page with protocol commands: `Page.navigate`, `Page.captureScreenshot`, `Runtime.evaluate`, `Emulation.setDeviceMetricsOverride`, `Emulation.setTouchEmulationEnabled`, `Emulation.setEmulatedMedia`, `Network.setBlockedURLs`, and `Input.dispatchMouseEvent`.

One gotcha: `Emulation.setTouchEmulationEnabled` rejects a `maxTouchPoints` of 0. Always send 5 and gate the behavior on the `enabled` flag instead.

Beyond rescue duty, this route makes the genuine self-test checks possible (real touch emulation, live media flips, URL blocking, real mouse presses); those are listed with the checklist in `scrub-pipeline.md`.

## The page

| Symptom | Cause | Fix |
|---|---|---|
| An entrance animation never plays, the element just appears | A later rule won the cascade over the animation's starting state | Prefix start and end states with the container class (`.card .part`, `.card.in .part`) and prove every entrance plays |
| Hovers on the 2nd and 3rd items of a staggered grid respond late even after the entrance finished | The cleanup rule that zeroes the stagger `transition-delay` has lower specificity than the nth-child delay rules it retires (`:nth-child` counts as a class), so it silently never applies | Make the cleanup selector match or beat the delay rules (repeat the nth-child in it) or put `!important` on the `0s` delay, then prove it by hovering the later siblings |
| A scroll-driven style stops responding after its entrance | `animation-fill-mode: forwards` overrides it forever | Entrance animation on the parent, dynamic style on a child |
| A background loop flashes or snaps when it starts | Positive animation delay | Negative delays (like `-1.2s`) so every loop is mid-cycle at first paint |
| Letter tails (g, y, p) are cut off | Masked or clipped text with zero breathing room | Em-based padding with matching negative margins on the mask (see `scrub-pipeline.md`) |
| The page can be dragged or shifted sideways | `overflow-x: hidden` alone, or a decoration poking past the edge | `overflow-x: clip` on BOTH `html` and `body`, `hidden` first as fallback |
| Hovers start snapping after a script runs | JavaScript overwrote `el.style.transition` | Toggle a class that declares the full combined transition instead |
| A mobile element sits off-screen with reduced motion on | Blanket `transform: none !important` wiped its positional transform | Re-apply positional transforms per breakpoint inside the reduced-motion block |
| A marquee shows a gap at the loop point | Track shorter than the widest supported screen | Duplicate items until each track exceeds about 2560px |
| Animations run while the tab is hidden or the section is off-screen | Free-running loops | Scope animation rules to a class an IntersectionObserver toggles; on `visibilitychange` toggle one body class with `body.paused *, body.paused *::before, body.paused *::after { animation-play-state: paused !important }`; rAF loops rest when converged |
| A pause written on a container never actually pauses the animations inside it | `animation-play-state` is not an inherited property, so a value set on a parent (or `inherit` on a nested rule) never reaches nested elements or pseudo-elements | The body-class pattern above; it hits every element and pseudo-element directly |

## Deploy

| Symptom | Cause | Fix |
|---|---|---|
| Live site shows a directory listing or 404 | The zip contains the project folder, not its contents | Re-zip with `index.html` at the zip's top level |
| Images look soft on the live site but sharp locally | The host resizes and recompresses images server-side | Upload larger and cleaner (about 1920px wide, one high-quality pass) so the host's pass is the only lossy step |
| Link previews show no image or the wrong URL | og tags still carry the placeholder | Patch `og:image` and `og:url` with the live absolute URL at the `<!-- DEPLOY STEP -->` comment, re-zip, re-deploy |
| The live site still shows the old version after a re-deploy | Cache | Hard-refresh, or verify against a string you know changed |
| Raw videos or review files appear on the live site | They were inside the deploy folder when it was zipped | Keep raws and review copies OUTSIDE the deploy folder, always |
| Special characters turn to gibberish after a scripted find-and-replace (arrows and ordinal marks become mojibake) | A shell command read the UTF-8 file with the wrong default encoding and wrote the damage back | Never patch site files with plain shell read and write: use the editor tool for the og patch and any text change, or read and write with explicit UTF-8. Recovery if it already happened: read the damaged file as UTF-8, encode that text to Windows-1252 bytes, decode those bytes as UTF-8, save as UTF-8, verify the characters, redeploy |

## Setup

| Symptom | Cause | Fix |
|---|---|---|
| Hostinger tools missing after adding the connector, or the sign-in page never opens | A freshly added local connector sometimes loads only on the next app start | Close Claude Code completely, reopen, return to the same chat, and trigger the sign-in again |
| The site looks frozen or broken in the app's side preview pane | The built-in pane struggles with scroll-video pages | Open the localhost link in a real web browser; that is the true preview |
| The Hostinger connector command fails on Windows | `npx` instead of `npx.cmd` | Windows uses `claude mcp add hostinger -- npx.cmd -y hostinger-api-mcp` |
| The Hostinger sign-in seems to go nowhere | The authorization opened in a different browser than the user normally uses | Warn them in advance and have them check their other browsers |
| Higgsfield tools missing right after connecting | A freshly added connector sometimes loads only on the next app start | Close Claude Code completely, reopen, return to the same chat, and verify again |
| The Higgsfield connector shows it needs authentication | The sign-in did not complete during the add | Finish it in the connectors panel: the browser opens to Higgsfield to authorize once, then re-verify with a balance call |
| Higgsfield tools present but calls fail | Connector added but not authorized, or no credits | Re-run the sign-in flow; verify with a balance call, which should return real numbers |
| The user says a setup step is done but the next step fails | "Done" was taken as verification | It never is; re-check the system yourself after every step before advancing |
| ffmpeg or Node.js fails to install on a Mac | Homebrew is not installed, so brew commands cannot run, and macOS security often blocks a downloaded binary instead | Have the user install Homebrew first: the one command from brew.sh, pasted into Terminal, which asks for their Mac password. Then run the installs again and verify |
| Claude skips the setup checklist and jumps straight to brand or design questions | The skill zip was never extracted and fully read (common when the zip was dragged into the chat: the project folder stays empty and the skill's files never entered the conversation) | Extract the zip into the project workspace, read SKILL.md and every reference top to bottom, and restart at Phase 1. The checklist message is always the first thing the user sees |
| Every hosting call hangs during a long session and a browser sign-in tab keeps opening | The hosting connector lost its signed-in state mid-session, so every call silently waits on a fresh sign-in | Complete the sign-in once in the tab that opens. If the popup misbehaves, one full app restart plus one sign-in fixes it cleanly. Files and the live site are never affected |

**The two-hang rule (the subsystem rule, for any tool):** a second consecutive hang on the same tool or subsystem means it is down. Stop retrying, name it out loud, and restart. Never make a third call into a hung subsystem. This is different from a slow render: a job that reports progress is working, however long it takes; a call that hangs with no response at all is the one this rule covers.
