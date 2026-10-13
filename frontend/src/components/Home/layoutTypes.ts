// Shared Sanctuary layout types — used by SettingsOverlay.

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
    left: ["tasks", "music"],
    center: ["memory"],
    right: ["links", "portfolio", "settings"],
  },
  hidden: [],
  sizes: {},
  preset: "default",
};

export const CARD_TITLES: Record<string, string> = {
  tasks: "Tasks", memory: "Memory", music: "Music",
  links: "Quick Shortcuts", portfolio: "Portfolio", settings: "Settings",
};
