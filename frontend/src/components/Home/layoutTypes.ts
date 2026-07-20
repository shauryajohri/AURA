// Shared Sanctuary layout types — used by SanctuarySection and SettingsOverlay.

export type ColId = "left" | "center" | "right";
export type Preset = "default" | "compact" | "custom";
export type Size = "normal" | "tall";

export interface Layout {
  cols: Record<ColId, string[]>;
  hidden: string[];
  sizes: Record<string, Size>;
  preset: Preset;
}

export const DEFAULT_LAYOUT: Layout = {
  cols: {
    left: ["tasks", "memory", "music"],
    center: ["domain"],
    right: ["links", "portfolio", "settings"],
  },
  hidden: [],
  sizes: {},
  preset: "default",
};

export const CARD_TITLES: Record<string, string> = {
  tasks: "Tasks", memory: "Memory", music: "Music",
  domain: "AURA Domain", links: "Quick Shortcuts", portfolio: "Portfolio", settings: "Settings",
};
