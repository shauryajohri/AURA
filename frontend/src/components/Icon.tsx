/**
 * AURA's icon set — one stroke weight, one grid (24px), drawn for this app so
 * the chrome stops mixing emoji, dingbats and fonts.
 */
const PATHS: Record<string, string> = {
  home: "M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z",
  chats: "M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15h0A2 2 0 0 1 5 13z",
  domain: "M9 8 5 12l4 4M15 8l4 4-4 4M13 6l-2 12",
  saved: "M7 4h10a1 1 0 0 1 1 1v15l-6-3.8L6 20V5a1 1 0 0 1 1-1z",
  memory: "M12 4v3M12 17v3M4 12h3M17 12h3M6.3 6.3l2.1 2.1M15.6 15.6l2.1 2.1M6.3 17.7l2.1-2.1M15.6 8.4l2.1-2.1M12 9.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z",
  tasks: "M4.5 12.5 9 17l10.5-10.5",
  models: "M12 9.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6zM3.5 12c0-2 3.8-3.6 8.5-3.6s8.5 1.6 8.5 3.6-3.8 3.6-8.5 3.6-8.5-1.6-8.5-3.6z",
  planets: "M12 6.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11zM4.2 17.8c-1.3-1.3 1.7-5.2 6.1-9.5s8.2-7.4 9.5-6.1",
  settings: "M5 7h9M18 7h1M5 17h1M10 17h9M16 5v4M8 15v4",
  labs: "M9.5 4h5M10.5 4v5.2L5.6 17.8A1.5 1.5 0 0 0 6.9 20h10.2a1.5 1.5 0 0 0 1.3-2.2L13.5 9.2V4M8 14h8",
  upgrade: "M12 19.5V6M7 11l5-5 5 5M5 4h14",
  bell: "M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.5H5zM10 20h4",
  focus: "M12 4v3M12 17v3M4 12h3M17 12h3M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
  core: "M12 7.5a4.5 4.5 0 1 1 0 9 4.5 4.5 0 0 1 0-9zM3 12h3.5M17.5 12H21",
  minimize: "M6 12h12",
  close: "M7 7l10 10M17 7 7 17",
  mic: "M12 4a2.5 2.5 0 0 1 2.5 2.5v5a2.5 2.5 0 0 1-5 0v-5A2.5 2.5 0 0 1 12 4zM6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v3",
  send: "M12 19V6M6.5 11.5 12 6l5.5 5.5",
  attach: "M16.5 11.5 11 17a3.5 3.5 0 0 1-5-5l6.5-6.5a2.3 2.3 0 0 1 3.3 3.3L9.4 15.2a1.1 1.1 0 0 1-1.6-1.6l5.7-5.7",
  history: "M5 7h14M5 12h14M5 17h9",
  speaker: "M5 9.5h3l4-3.5v12l-4-3.5H5zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11",
  mute: "M5 9.5h3l4-3.5v12l-4-3.5H5zM16 10l4 4M20 10l-4 4",
  up: "M7 14l5-5 5 5",
  down: "M7 10l5 5 5-5",
  left: "M14 7l-5 5 5 5",
  right: "M10 7l5 5-5 5",
  plus: "M12 6v12M6 12h12",
  check: "M6 12.5 10 16.5 18 8.5",
  spark: "M12 4c.6 3.6 2.4 5.4 6 6-3.6.6-5.4 2.4-6 6-.6-3.6-2.4-5.4-6-6 3.6-.6 5.4-2.4 6-6z",
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={"icon" + (className ? " " + className : "")}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
