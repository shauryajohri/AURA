import { useMemo } from "react";
import type { Settings } from "../api";
import PageShell from "./PageShell";
import SkinGallery, { type SkinChoice } from "../components/Home/SkinGallery";
import { useSettingsStore } from "../stores/settingsStore";

/**
 * Themes — the skin gallery as its own sidebar destination. It is the same
 * gallery as Settings → Skins, but a pick here is worn and saved at once, like
 * the top bar's quick switch, instead of waiting as a draft behind Save.
 */

function GalleryPane() {
  const settings = useSettingsStore((s) => s.settings);
  const apply = useSettingsStore((s) => s.apply);
  const value = useMemo<SkinChoice>(() => ({
    "skin.id": String(settings["skin.id"] ?? "aura"),
    "skin.core": String(settings["skin.core"] ?? ""),
    "skin.backdrop": String(settings["skin.backdrop"] ?? ""),
  }), [settings]);

  return <SkinGallery value={value} onChange={(patch) => apply(patch as Settings)} />;
}

export default function ThemesPage() {
  return (
    <PageShell
      title="Themes"
      tagline="Whole designs for AURA's world: the black hole, the sky behind it, and the colours of everything else."
      storeKey="aura.page.themes"
      tabs={[{ id: "gallery", label: "Gallery", body: <GalleryPane /> }]}
    />
  );
}
