# The AURA site

A demo first, then the facts. The page opens with an interactive AURA: pick one
of her five natures, ask her something, and watch the real pipeline that would
have produced the answer. Below that, only useful information: what she does,
exactly how far along she is, the permission ladder, and how to install her.

No build step, no framework, no CDN except the webfont.

```
website/
  index.html          the shell — mount points, nothing else
  content.js          ← everything you will ever need to edit
  site.js             renders content.js into the shell
  styles.css          the design system
  assets/*.webp       the images that ship
```

## The demo is scripted, and the page says so

There is no model in a browser tab. The replies in `content.js` under `demo` are
written by hand; the routing shown beside them is real, copied from the app:

| Shown on the page | Read from |
|---|---|
| the five natures and their overlay text | `core/nature.py` |
| the model for each intent | `core/model_router.py` |
| the style and its sentence cap | `core/response_composer.py` |
| what the guard strips | `core/response_composer.py` |

Those four blocks are quoted, not paraphrased, which is why the nature overlays
keep their original punctuation. If you change any of those files, change the
matching block here or the page starts lying.

To add a question, push one object onto `demo.questions` with a reply for every
nature key. A missing reply renders as blank, so add all five.

## Updating it when AURA moves forward

This is the whole point of the split. Open `content.js` and find `capabilities`:

```js
{ half: "domain", status: "planned", name: "Roadmap view",
  blurb: "The timeline forward, not just the history backward." },
```

- **Shipped it?** Change `status` to `"live"`.
- **Started it?** Change `status` to `"forming"`.
- **Built something new?** Add one more object to the array.
- **Nothing else.** The ledger rows, the group counts, the filter pill counts,
  the "18 of 22 capabilities" line and the progress meter under the hero are
  all derived at render time. There is no second place to keep in sync.

`status` must be a key of the `states` object above it (`live`, `forming`,
`planned`). Add a fourth state there if you want one; the page will pick it up.

The other fields worth knowing:

| Key | What it drives |
|---|---|
| `meta.stage` | the "Stage" value in the strip under the hero |
| `meta.updated` | the "Last updated" value in that strip |
| `meta.repo` | every link to the source |
| `figures` | the three images; delete a key and that image disappears |
| `ladder.rungs` | the permission ladder and its slider |
| `faq.items` | the questions at the bottom |

## Running it

Any static server. From this folder:

```bash
python -m http.server 8777
```

Then open <http://127.0.0.1:8777>. Opening `index.html` as a `file://` URL also
works in most browsers, but a server is closer to how it will be deployed.

## Design notes

The palette is sampled from the app's own tokens in `frontend/src/styles.css`,
so the site and the product are the same object rather than a theme invented to
describe one. One rule governs the colour:

- **violet** `#8B5CFF` — AURA's presence, and anything interactive
- **cyan** `#38E1FF` — a capability that runs today
- **amber** `#F5A623` — a capability being built
- nothing is coloured for decoration

Monospace is reserved for real file paths and real commands. It is never used
as a decorative label. The hero is a still rather than a loop, because a site
arguing that AURA stays quiet unless motion carries information should not open
with motion that carries none. A scroll-scrubbed video version exists in the
project's working tree if you ever want the moving hero back.

## Regenerating the images

They came from Higgsfield (`gpt_image_2_5`, 1 credit each), prompted for a
near-black ground with violet/cyan/amber light. Only the shipped WebP files are
committed; the PNG originals are kept out of the repo for weight. They were
compressed with:

```bash
cwebp -q 82 horizon.png -o assets/horizon.webp
```

That step takes the five images from 5.5 MB to 231 KB, which is why they are
small enough to sit in the repo at all.
