// ============================================================================
// Skins — whole-world designs for AURA.
//
// A skin is one coherent look: which black-hole design sits at the core, what
// fills the full-screen background, and the colours everything else wears
// (glass borders, highlights, particles, the cursor). The renderers never hold
// colours of their own any more; they read the active skin, so a new skin is
// one object in SKINS below and every surface follows it.
//
// The background and the core can each be overridden on top of a skin
// ("Gargantua's disk on the Aurora sky"), so a user is not limited to the
// combinations listed here.
//
// Colours are "r,g,b" strings because every canvas renderer builds rgba()
// with a live alpha; the CSS side gets the same triplets as --*-rgb vars.
// ============================================================================

import type { SkyKind } from "./backdrops";

export type CoreFormId = "horizon" | "gargantua" | "eclipse" | "quasar" | "wormhole";
export type FilmId = "film-supernova" | "film-gargantua" | "film-borealis";
export type BackdropId = "video" | "cosmos" | SkyKind | FilmId;

/**
 * Filmed backgrounds: seamless loops generated with Higgsfield (a still key
 * frame, animated with that same frame as first and last, so the loop has no
 * seam). They live in frontend/public/skins/. If a file is missing or won't
 * decode, the procedural sky in `fallback` takes over, so a skin never
 * depends on its film being present.
 */
export const FILMS: Record<FilmId, { src: string; fallback: SkyKind }> = {
  "film-supernova": { src: "./skins/supernova.mp4", fallback: "nebula" },
  "film-gargantua": { src: "./skins/gargantua.mp4", fallback: "starfield" },
  "film-borealis": { src: "./skins/borealis.mp4", fallback: "aurora" },
};

export const isFilm = (b: string): b is FilmId => Object.prototype.hasOwnProperty.call(FILMS, b);

/** The core's light. Roles match the original violet constants in BlackHole. */
export interface CorePalette {
  main: string;   // outer halo, bloom, haze
  inner: string;  // bright band, orbit guides
  photon: string; // near-white ring light
  soft: string;   // pale wisps
  deep: string;   // node glows
  white: string;  // white-hot sparks, beam cores
  accent: string; // contrast colour: speaking ring, drag highlight
  hot: string;    // the hottest gas (disk forms)
}

export interface Skin {
  id: string;
  name: string;
  tagline: string;
  core: CoreFormId;
  backdrop: BackdropId;
  pal: CorePalette;
  /** Background scene hues: [base tone, primary gas, secondary gas, highlight]. */
  sky: [string, string, string, string];
  /** Interface colours, written onto :root as CSS variables. */
  ui: { violet: string; bright: string; cyan: string; border: string };
  /** Free-floating dust (ParticleField). Derived from `pal` when omitted. */
  dust?: string[];
}

export const SKINS: Skin[] = [
  {
    id: "aura",
    name: "Aura",
    tagline: "The original. A violet horizon split by a blade of light.",
    core: "horizon",
    backdrop: "video",
    pal: {
      main: "125,60,255", inner: "167,109,255", photon: "243,217,255", soft: "196,150,255",
      deep: "139,101,255", white: "255,252,255", accent: "56,225,255", hot: "255,214,250",
    },
    sky: ["10,6,30", "125,60,255", "56,120,255", "243,217,255"],
    ui: { violet: "139,92,255", bright: "177,139,255", cyan: "56,225,255", border: "150,125,255" },
    // The exact dust the app shipped with, so the default skin is unchanged.
    dust: ["139,92,255", "125,60,255", "177,139,255", "217,200,255",
           "167,109,255", "255,255,255", "255,255,255", "56,225,255"],
  },
  {
    id: "gargantua",
    name: "Gargantua",
    tagline: "A tilted disk of molten gold, bent up over the top of the void.",
    core: "gargantua",
    backdrop: "film-gargantua",
    pal: {
      main: "255,138,40", inner: "255,190,92", photon: "255,236,204", soft: "255,172,112",
      deep: "222,112,42", white: "255,250,240", accent: "140,210,255", hot: "255,246,220",
    },
    sky: ["14,8,4", "255,150,64", "110,90,190", "255,230,190"],
    ui: { violet: "236,150,52", bright: "255,196,112", cyan: "130,205,255", border: "220,160,92" },
  },
  {
    id: "totality",
    name: "Totality",
    tagline: "A moon across the sun: pearl corona and one diamond of light.",
    core: "eclipse",
    backdrop: "void",
    pal: {
      main: "170,190,255", inner: "214,224,255", photon: "250,250,255", soft: "190,200,236",
      deep: "140,150,200", white: "255,255,255", accent: "255,120,150", hot: "255,108,92",
    },
    sky: ["4,5,10", "120,140,200", "60,70,120", "230,235,255"],
    ui: { violet: "150,165,222", bright: "205,214,246", cyan: "255,140,165", border: "170,180,222" },
  },
  {
    id: "quasar",
    name: "Quasar",
    tagline: "Twin jets fired from a white-hot disk while the stars streak past.",
    core: "quasar",
    backdrop: "warp",
    pal: {
      main: "40,120,255", inner: "80,190,255", photon: "210,245,255", soft: "120,200,255",
      deep: "50,100,230", white: "245,252,255", accent: "255,90,200", hot: "230,250,255",
    },
    sky: ["2,6,20", "60,150,255", "150,90,255", "220,245,255"],
    ui: { violet: "64,140,255", bright: "120,195,255", cyan: "255,110,210", border: "90,150,240" },
  },
  {
    id: "supernova",
    name: "Supernova",
    tagline: "A crimson horizon wrapped in the gas of a dying star.",
    core: "horizon",
    backdrop: "film-supernova",
    pal: {
      main: "255,40,90", inner: "255,100,130", photon: "255,222,215", soft: "255,140,160",
      deep: "220,50,100", white: "255,250,245", accent: "255,190,80", hot: "255,200,120",
    },
    sky: ["16,2,10", "255,50,100", "120,40,200", "255,170,90"],
    ui: { violet: "240,60,110", bright: "255,130,160", cyan: "255,190,90", border: "230,100,140" },
  },
  {
    id: "borealis",
    name: "Borealis",
    tagline: "An emerald disk turning slowly under the northern lights.",
    core: "gargantua",
    backdrop: "film-borealis",
    pal: {
      main: "40,220,160", inner: "110,255,200", photon: "220,255,240", soft: "120,230,200",
      deep: "30,170,140", white: "245,255,250", accent: "190,120,255", hot: "210,255,236",
    },
    sky: ["2,10,14", "40,230,160", "120,90,255", "200,255,235"],
    ui: { violet: "40,200,150", bright: "120,240,200", cyan: "180,130,255", border: "70,190,160" },
  },
  {
    id: "wormhole",
    name: "Wormhole",
    tagline: "A tunnel through spacetime, with another sky waiting at the end.",
    core: "wormhole",
    backdrop: "cosmos",
    pal: {
      main: "200,60,255", inner: "240,110,255", photon: "255,220,255", soft: "220,150,255",
      deep: "150,70,230", white: "255,250,255", accent: "90,230,255", hot: "255,170,240",
    },
    sky: ["10,4,24", "200,60,255", "60,120,255", "255,210,255"],
    ui: { violet: "190,80,255", bright: "230,140,255", cyan: "90,230,255", border: "180,110,240" },
  },
  {
    id: "abyss",
    name: "Abyss",
    tagline: "Monochrome and near-silent. Pure black, white light, nothing else.",
    core: "horizon",
    backdrop: "void",
    pal: {
      main: "150,150,165", inner: "200,200,212", photon: "245,245,250", soft: "175,175,190",
      deep: "130,130,145", white: "255,255,255", accent: "255,255,255", hot: "232,232,238",
    },
    sky: ["0,0,0", "120,120,135", "80,80,95", "230,230,240"],
    ui: { violet: "160,160,175", bright: "215,215,225", cyan: "235,235,245", border: "150,150,165" },
  },
];

export const DEFAULT_SKIN = SKINS[0];

export const CORE_FORMS: Array<{ id: CoreFormId; name: string; desc: string }> = [
  { id: "horizon", name: "Horizon", desc: "White-hot ring, crackling filaments, a blade of light" },
  { id: "gargantua", name: "Accretion disk", desc: "A tilted disk lensed up over the shadow" },
  { id: "eclipse", name: "Eclipse", desc: "Corona streamers and a diamond-ring flare" },
  { id: "quasar", name: "Quasar", desc: "Bright disk with twin relativistic jets" },
  { id: "wormhole", name: "Wormhole", desc: "Rings falling into a tunnel with light at the end" },
];

export const BACKDROPS: Array<{ id: BackdropId; name: string; desc: string }> = [
  { id: "video", name: "Universe video", desc: "The filmed cosmos AURA shipped with" },
  { id: "film-supernova", name: "Supernova film", desc: "Crimson remnant gas drifting at the edges of the frame" },
  { id: "film-gargantua", name: "Gargantua film", desc: "A golden galactic band crossing the sky" },
  { id: "film-borealis", name: "Borealis film", desc: "Aurora rising over a dark planet, seen from orbit" },
  { id: "cosmos", name: "Cosmic web", desc: "Constellations, pillars and a lattice funnel" },
  { id: "starfield", name: "Deep field", desc: "Layered stars drifting past a galactic band" },
  { id: "nebula", name: "Nebula", desc: "Slow clouds of glowing gas" },
  { id: "aurora", name: "Aurora", desc: "Curtains of light rippling across the sky" },
  { id: "warp", name: "Warp drive", desc: "Stars streaking past; faster when she thinks" },
  { id: "void", name: "Void", desc: "Near-black and still. Easy on eyes and battery" },
];

/** Settings keys. Overrides are "" when the skin's own choice applies. */
export const SKIN_KEYS = ["skin.id", "skin.core", "skin.backdrop"] as const;

export interface ResolvedSkin {
  skin: Skin;
  core: CoreFormId;
  backdrop: BackdropId;
}

const isCore = (v: unknown): v is CoreFormId => CORE_FORMS.some((c) => c.id === v);
const isBackdrop = (v: unknown): v is BackdropId => BACKDROPS.some((b) => b.id === v);

export function findSkin(id: unknown): Skin {
  return SKINS.find((s) => s.id === id) ?? DEFAULT_SKIN;
}

/** Skin + overrides → what actually renders. Unknown values fall back safely. */
export function resolveSkin(id: unknown, core: unknown, backdrop: unknown): ResolvedSkin {
  const skin = findSkin(id);
  return {
    skin,
    core: isCore(core) ? core : skin.core,
    backdrop: isBackdrop(backdrop) ? backdrop : skin.backdrop,
  };
}

export const rgba = (c: string, a: number) => `rgba(${c},${a < 0 ? 0 : a > 1 ? 1 : a})`;

/** The dust colours for the particle field. */
export function dustOf(skin: Skin): string[] {
  const p = skin.pal;
  return skin.dust ?? [p.deep, p.main, p.soft, p.photon, p.inner, p.white, p.white, p.accent];
}

// ---- document-level application -------------------------------------------

// The pointer is a tiny black hole drawn by the OS (zero latency), so its
// colours live in an SVG data URI. These mirror the originals in styles.css.
const svgUri = (svg: string) => `url('data:image/svg+xml,${svg.replace(/#/g, "%23")}')`;

function cursorDefault(p: CorePalette): string {
  return svgUri(
    `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 26 26">` +
    `<circle cx="13" cy="13" r="10.5" fill="none" stroke="rgba(${p.main},0.35)" stroke-width="1"/>` +
    `<circle cx="13" cy="13" r="8" fill="none" stroke="rgba(${p.inner},0.6)" stroke-width="1"/>` +
    `<circle cx="13" cy="13" r="5.4" fill="rgba(${p.deep},0.28)"/>` +
    `<circle cx="13" cy="13" r="4.4" fill="black" stroke="rgb(${p.photon})" stroke-width="1.3"/></svg>`,
  ) + " 13 13, auto";
}

function cursorPoint(p: CorePalette): string {
  return svgUri(
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">` +
    `<circle cx="14" cy="14" r="11.5" fill="none" stroke="rgba(${p.accent},0.45)" stroke-width="1"/>` +
    `<circle cx="14" cy="14" r="8.6" fill="none" stroke="rgba(${p.accent},0.7)" stroke-width="1.1"/>` +
    `<circle cx="14" cy="14" r="6" fill="rgba(${p.accent},0.2)"/>` +
    `<circle cx="14" cy="14" r="4.8" fill="black" stroke="rgb(${p.accent})" stroke-width="1.4"/></svg>`,
  ) + " 14 14, pointer";
}

/**
 * Write the skin's interface colours onto :root. styles.css and domain.css
 * read every accent through these variables, so this one call re-tints the
 * sidebar, glass panels, chat, settings, the Domain workspace and the cursor.
 */
export function applySkinToDocument(skin: Skin) {
  const st = document.documentElement.style;
  const { ui, pal } = skin;
  st.setProperty("--violet", `rgb(${ui.violet})`);
  st.setProperty("--violet-bright", `rgb(${ui.bright})`);
  st.setProperty("--cyan", `rgb(${ui.cyan})`);
  st.setProperty("--violet-rgb", ui.violet);
  st.setProperty("--violet-bright-rgb", ui.bright);
  st.setProperty("--cyan-rgb", ui.cyan);
  st.setProperty("--border-rgb", ui.border);
  st.setProperty("--cursor-default", cursorDefault(pal));
  st.setProperty("--cursor-point", cursorPoint(pal));
  document.documentElement.dataset.skin = skin.id;
}
