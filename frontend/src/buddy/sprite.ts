// The pixel pal. A 16×14 body drawn into a 20×20 grid; the spare rows above
// the head hold the "thinking" dots and the sleepy z's. Pixels are drawn at an
// integer device-pixel size so edges stay crisp at any display scaling.

export const GRID = 20;
const OX = 2; // body's top-left inside the grid
const OY = 6;

const PAL: Record<string, string> = {
  o: "#1a0b3d", // outline
  b: "#7d3cff", // body — AURA's electric purple
  h: "#c3a2ff", // highlight
  s: "#5b23d6", // shade
  w: "#f3d9ff", // eyes, dots — the photon-ring white
  d: "#1a0b3d", // closed eyes, mouth
  c: "#d65ad8", // blush
};

const BODY = [
  "....oooooooo....",
  "..oobbbbbbbboo..",
  ".obhhbbbbbbbbbo.",
  ".obhbbbbbbbbbbo.",
  "obhbbbbbbbbbbbbo",
  "obbbbbbbbbbbbbbo",
  "obbbbbbbbbbbbbbo",
  "obbbbbbbbbbbbbbo",
  "obbbbbbbbbbbbbbo",
  "obbbbbbbbbbbbbbo",
  ".osbbbbbbbbbbso.",
  "..oossssssssoo..",
];

export type Feet = "stand" | "walkA" | "walkB" | "dangle" | "sit";
const FEET: Record<Feet, [string, string]> = {
  stand:  ["...obo....obo...", "...ooo....ooo..."],
  walkA:  ["..obo.....obo...", "..ooo..........."],
  walkB:  ["...obo.....obo..", "...........ooo.."],
  dangle: ["....o......o....", "....o......o...."],
  sit:    ["................", "..oooo....oooo.."],
};

// Closed, smiling eyes (^ ^), body coordinates.
const HAPPY = [[3, 6], [4, 5], [5, 5], [6, 6], [9, 6], [10, 5], [11, 5], [12, 6]];
const Z = [[0, 0], [1, 0], [2, 0], [1, 1], [0, 2], [1, 2], [2, 2]];

export interface Pose {
  feet: Feet;
  eyes: "open" | "blink" | "shut" | "happy" | "wide";
  look: -1 | 0 | 1;        // eyes shifted left/right (screen space)
  up: boolean;              // eyes raised — thinking
  mouth: "none" | "small" | "open";
  bob: 0 | 1;               // body lifted one pixel
  flip: boolean;            // facing left
  dots: number;             // 0–3 thinking dots
  z: number;                // sleep animation phase, -1 when awake
}

export function drawBuddy(ctx: CanvasRenderingContext2D, p: Pose, cell: number): void {
  ctx.clearRect(0, 0, GRID * cell, GRID * cell);
  const dot = (gx: number, gy: number, c: string) => {
    ctx.fillStyle = PAL[c];
    ctx.fillRect(gx * cell, gy * cell, cell, cell);
  };
  // A body pixel. The body and feet mirror with the facing direction; the
  // face is symmetric, so it's drawn unmirrored and `look` stays screen-true.
  const px = (x: number, y: number, c: string, mirror = true) =>
    dot(OX + (mirror && p.flip ? 15 - x : x), OY + y, c);
  const row = (line: string, y: number) => {
    for (let x = 0; x < 16; x++) if (line[x] !== ".") px(x, y, line[x]);
  };

  const sitting = p.feet === "sit";
  const top = (sitting ? 1 : 0) - p.bob; // sitting lowers the body a row
  const feetTop = sitting ? 13 : 12;
  const feet = sitting ? [FEET.sit[1]] : FEET[p.feet];
  feet.forEach((line, i) => row(line, feetTop + i));
  for (let y = top + 12; y < feetTop; y++) row(feet[0], y); // legs stretch under a bob
  BODY.forEach((line, i) => row(line, top + i));

  // eyes
  const ey = top + (p.up ? 4 : 5);
  for (const ex of [4, 10]) {
    const x = ex + p.look;
    const fill = (y0: number, h: number, c: string) => {
      for (let k = 0; k < h; k++) { px(x, y0 + k, c, false); px(x + 1, y0 + k, c, false); }
    };
    if (p.eyes === "open") fill(ey, 3, "w");
    else if (p.eyes === "wide") fill(ey - 1, 4, "w");
    else if (p.eyes === "blink") fill(ey + 1, 1, "d");
    else if (p.eyes === "shut") fill(top + 7, 1, "d");
  }
  if (p.eyes === "happy") for (const [x, y] of HAPPY) px(x, top + y, "w", false);

  // blush + mouth
  for (const x of [2, 3, 12, 13]) px(x, top + 8, "c", false);
  if (p.mouth !== "none") {
    px(7, top + 9, "d", false); px(8, top + 9, "d", false);
    if (p.mouth === "open") { px(7, top + 10, "d", false); px(8, top + 10, "d", false); }
  }

  // thinking dots, above the head
  for (let i = 0; i < p.dots; i++) {
    const gx = OX + 3 + i * 4, gy = OY - 4;
    dot(gx, gy, "w"); dot(gx + 1, gy, "w"); dot(gx, gy + 1, "w"); dot(gx + 1, gy + 1, "w");
  }

  // two z's drifting up and to the right while asleep
  if (p.z >= 0) {
    for (let i = 0; i < 2; i++) {
      const q = (p.z + i * 6) % 12;
      if (q < 2 || q > 10) continue;
      const zx = 15 + Math.floor(q / 4), zy = 6 - Math.floor(q / 2);
      for (const [x, y] of Z) dot(zx + x, zy + y, "h");
    }
  }
}
