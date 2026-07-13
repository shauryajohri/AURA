# Backgrounds

Drop your nebula image here to replace the CSS fallback.

- File name: **`nebula.jpg`** (or change the URL in `src/styles.css` -> `.nebula`)
- Path: `frontend/public/nebula.jpg`
- Vite serves everything in `public/` at the site root, so this file is
  reachable at `/nebula.jpg` (that's exactly what the `.nebula` CSS references).

The image is anchored to the **left** and masked so it fades into deep space
toward the center/right (matching the mockup). To extend the background across
the whole app later, widen the mask in `.nebula` (raise the `transparent` stop
from 60% toward 100%).

No restart needed — Vite hot-reloads. Just refresh (Ctrl+R) after adding the file.
