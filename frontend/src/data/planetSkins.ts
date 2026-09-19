// The planet library — every surface a model's planet can wear.
// Rendered with Higgsfield (Seedream 4.5), cut to transparent 512px sprites
// lit from the left; the scene turns each one so its lit side faces the core.

export interface PlanetSkin {
  id: string;
  name: string;
  /** One plain line for the Planets page. */
  about: string;
  /** Glow and label colour — sampled from the render. */
  glow: string;
}

export const SKINS: PlanetSkin[] = [
  { id: "circuit",  name: "Lattice",  about: "Black glass wrapped in a live hexagonal grid", glow: "#5CE1FF" },
  { id: "amethyst", name: "Amethyst", about: "A crust of faceted violet crystal",            glow: "#C9A6FF" },
  { id: "solaris",  name: "Solaris",  about: "Gold and sulphur storms around a red eye",     glow: "#FFB547" },
  { id: "tide",     name: "Tide",     about: "One deep teal ocean under spiral clouds",      glow: "#4FE3D2" },
  { id: "glacier",  name: "Glacier",  about: "Ice sheets split by blue crevasses",           glow: "#BFD8FF" },
  { id: "rose",     name: "Rose",     about: "Soft coral and lilac cloud bands",             glow: "#FF9CC2" },
  { id: "verdant",  name: "Verdant",  about: "Green continents, blue seas, white weather",   glow: "#6FD3FF" },
  { id: "dune",     name: "Dune",     about: "Rust dunes and dry canyons",                   glow: "#FF8A5C" },
  { id: "venom",    name: "Venom",    about: "Acid-lime cloud decks",                        glow: "#C8F25A" },
  { id: "ember",    name: "Ember",    about: "Basalt split by rivers of magma",              glow: "#FF7A3D" },
  { id: "selene",   name: "Selene",   about: "Silver craters, no air",                       glow: "#E4E6F2" },
  { id: "nyx",      name: "Nyx",      about: "A violet gas giant with one great storm",      glow: "#A98BFF" },
  { id: "aurora",   name: "Aurora",   about: "A night world ringed by polar light",          glow: "#6BFFB8" },
];

export const skinById = (id: string | undefined) => SKINS.find((s) => s.id === id);

export const skinUrl = (id: string) => `./planets/${id}.webp`;

// What each built-in model wears until you pick something else — chosen to
// sit near the model's own colour so nothing familiar changes hue.
const DEFAULTS: Record<string, string> = {
  north: "circuit",
  laguna: "amethyst",
  qwen: "solaris",
  nemotron: "tide",
  dots: "glacier",
  gemma: "rose",
  nex: "verdant",
  omni: "dune",
  ling: "venom",
  llama: "ember",
  llama8b: "selene",
};
// Installed planets cycle through the ones no built-in model wears.
const SPARE = ["nyx", "aurora", "amethyst", "tide", "rose"];

export function defaultSkin(modelId: string, index: number): string {
  return DEFAULTS[modelId] ?? SPARE[index % SPARE.length];
}
