// File-type glyphs for the explorer and tabs.
// Deliberately text glyphs rather than an icon font: no extra bundle weight,
// and they inherit colour so the active/inactive states just work.

const BY_EXT: Record<string, { glyph: string; color: string }> = {
  ts:   { glyph: "TS", color: "#3178c6" },
  tsx:  { glyph: "TS", color: "#3178c6" },
  js:   { glyph: "JS", color: "#f7df1e" },
  jsx:  { glyph: "JS", color: "#f7df1e" },
  mjs:  { glyph: "JS", color: "#f7df1e" },
  py:   { glyph: "PY", color: "#ffd866" },
  css:  { glyph: "#",  color: "#42a5f5" },
  scss: { glyph: "#",  color: "#cf649a" },
  html: { glyph: "<>", color: "#e44d26" },
  json: { glyph: "{}", color: "#cbcb41" },
  md:   { glyph: "M",  color: "#b18bff" },
  yml:  { glyph: "Y",  color: "#cb4b16" },
  yaml: { glyph: "Y",  color: "#cb4b16" },
  toml: { glyph: "T",  color: "#9c4221" },
  sh:   { glyph: ">_", color: "#89e051" },
  bat:  { glyph: ">_", color: "#89e051" },
  ps1:  { glyph: ">_", color: "#89e051" },
  c:    { glyph: "C",  color: "#659ad2" },
  h:    { glyph: "H",  color: "#659ad2" },
  cpp:  { glyph: "C+", color: "#f34b7d" },
  hpp:  { glyph: "H+", color: "#f34b7d" },
  java: { glyph: "J",  color: "#b07219" },
  go:   { glyph: "GO", color: "#00add8" },
  rs:   { glyph: "RS", color: "#dea584" },
  sql:  { glyph: "DB", color: "#e38c00" },
  xml:  { glyph: "<>", color: "#8bc34a" },
  csv:  { glyph: "▦",  color: "#21a366" },
  txt:  { glyph: "≡",  color: "#8b8fca" },
  env:  { glyph: "⚙",  color: "#ecd53f" },
  lock: { glyph: "🔒", color: "#8b8fca" },
};

const BY_NAME: Record<string, { glyph: string; color: string }> = {
  "package.json": { glyph: "📦", color: "#cbcb41" },
  "tsconfig.json": { glyph: "TS", color: "#3178c6" },
  ".gitignore": { glyph: "⎇", color: "#f14e32" },
  "dockerfile": { glyph: "🐳", color: "#2496ed" },
  "readme.md": { glyph: "📖", color: "#b18bff" },
  "requirements.txt": { glyph: "PY", color: "#ffd866" },
};

export function fileMeta(name: string): { glyph: string; color: string } {
  const lower = name.toLowerCase();
  if (BY_NAME[lower]) return BY_NAME[lower];
  const ext = lower.includes(".") ? lower.split(".").pop()! : "";
  return BY_EXT[ext] ?? { glyph: "▪", color: "#8b8fca" };
}

export function fileIcon(name: string) {
  const { glyph, color } = fileMeta(name);
  return <span style={{ color }}>{glyph}</span>;
}
