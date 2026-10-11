import { useLayoutEffect, useMemo } from "react";
import { useSettingsStore } from "../stores/settingsStore";
import { applySkinToDocument, resolveSkin, type ResolvedSkin } from "./skins";

/**
 * The skin everything should be wearing right now: the saved choice, with
 * whatever the skin gallery is previewing laid over it.
 */
export function useSkin(): ResolvedSkin {
  const id = useSettingsStore((s) => s.skinPreview?.["skin.id"] ?? s.settings["skin.id"]);
  const core = useSettingsStore((s) => s.skinPreview?.["skin.core"] ?? s.settings["skin.core"]);
  const backdrop = useSettingsStore((s) => s.skinPreview?.["skin.backdrop"] ?? s.settings["skin.backdrop"]);
  return useMemo(() => resolveSkin(id, core, backdrop), [id, core, backdrop]);
}

/** Mount once at the root: keeps :root's colour variables on the active skin. */
export function useSkinDocument(): ResolvedSkin {
  const active = useSkin();
  // layout effect: the variables land before the browser paints, so a
  // cached non-default skin never flashes violet on launch
  useLayoutEffect(() => applySkinToDocument(active.skin), [active.skin]);
  return active;
}
