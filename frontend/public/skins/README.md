# Skin films and plates

Filmed backgrounds for three skins, generated with Higgsfield. Each is a
5-second, 1280×720, silent loop. The video was animated from one still key
frame (Kling 3.0, standard mode) with that same frame as its first and last
frame, so it loops without a seam. The app also crossfades the loop point.

| File | Skin | Higgsfield video job | Key frame job |
|---|---|---|---|
| `supernova.mp4` | Supernova | `485b4eb2-f48f-4eed-8ae1-8de7db4ffd5d` | `96f14d7b-7548-4939-b4ee-56b826efa51b` |
| `gargantua.mp4` | Gargantua | `5042c69a-0e7a-485f-af0b-bc46b9eeff5a` | `785d589b-b53e-4546-a5f9-dd643902ab27` |
| `borealis.mp4` | Borealis | `02c4577a-a5a1-4bfd-b3af-01e3a28fea06` | `28663742-c0c9-4cad-b135-eb90134546bd` |

`src/skins/skins.ts` (`FILMS`) points at these paths.

## From the Event Horizon redesign (Sep 19)

| File | Used as | Source |
|---|---|---|
| `horizon-film.webm` | The **Filmed horizon** core (Event Horizon, Milky Way) | Higgsfield video `0a1af866-95ee-4326-9267-a32479852a59` (Kling 3.0 Turbo) from key frame `e59d07f8-3c6d-4022-9ebf-6a5ca9d43845`, looped and encoded as VP9 WebM with its light as the alpha channel. Taken from `frontend/public/cosmos/core-loop.webm` in commit `56d814e`. |
| `sky-nebula.jpg` | The **Nebula plate** background (Event Horizon) | Higgsfield image `fbb30cca-b380-45aa-91e4-c4e5347682c1` (Seedream 4.5), as `cosmos/space.jpg` in `56d814e` |
| `sky-milkyway.jpg` | The **Milky Way** plate background | Higgsfield image `15f20215-a02d-42fc-b69b-e26ef85a9108` (Seedream 4.5), saved as JPEG |

The film's photon ring sits at (804, 326), radius 173, in its 1600×650
frames; `skins/coreForms.ts` scales it to the core from those numbers.
Plates are listed in `PLATES` in `src/skins/skins.ts`.

## Missing files

A missing file is fine. A film or plate falls back to its live procedural sky
(nebula, deep field, aurora), and the filmed horizon falls back to the drawn
horizon, so the app never shows a blank background or an empty core.

To add another film: drop the `.mp4` here, add an entry to `FILMS` and to
`BACKDROPS` in `src/skins/skins.ts`, and give a skin that `backdrop` id.
A still plate works the same way through `PLATES`. Keep the centre of the
frame dark and quiet, because the black hole is drawn there.
