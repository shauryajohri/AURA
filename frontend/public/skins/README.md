# Skin films

Filmed backgrounds for three skins, generated with Higgsfield. Each is a
5-second, 1280×720, silent loop. The video was animated from one still key
frame (Kling 3.0, standard mode) with that same frame as its first and last
frame, so it loops without a seam. The app also crossfades the loop point.

| File | Skin | Higgsfield video job | Key frame job |
|---|---|---|---|
| `supernova.mp4` | Supernova | `485b4eb2-f48f-4eed-8ae1-8de7db4ffd5d` | `96f14d7b-7548-4939-b4ee-56b826efa51b` |
| `gargantua.mp4` | Gargantua | `5042c69a-0e7a-485f-af0b-bc46b9eeff5a` | `785d589b-b53e-4546-a5f9-dd643902ab27` |
| `borealis.mp4` | Borealis | `02c4577a-a5a1-4bfd-b3af-01e3a28fea06` | `28663742-c0c9-4cad-b135-eb90134546bd` |

Download each video from your Higgsfield library and save it here under the
name in the first column. Nothing else needs to change: `src/skins/skins.ts`
(`FILMS`) already points at these paths.

A missing file is fine. That skin falls back to its live procedural sky
(nebula, deep field, aurora), so the app never shows a blank background.

To add another film: drop the `.mp4` here, add an entry to `FILMS` and to
`BACKDROPS` in `src/skins/skins.ts`, and give a skin that `backdrop` id.
Keep the centre of the frame dark and quiet, because the black hole is drawn there.
