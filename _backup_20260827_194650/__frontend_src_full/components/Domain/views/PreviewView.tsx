import { useEffect, useRef, useState } from "react";
import { useLocalStorage } from "../../../hooks/useLocalStorage";

// ============================================================================
// Live Preview — your dev server, inside the Domain.
//
// Point it at whatever your build console is serving (localhost:5173, :3000,
// :8000) and it renders in an iframe next to the code. Device presets frame it
// at phone/tablet/desktop widths; refresh is manual or on a timer, because a
// preview that reloads while you're mid-thought is worse than no preview.
// ============================================================================

const PRESETS = [
  { id: "phone", label: "Phone", w: 390, h: 844 },
  { id: "tablet", label: "Tablet", w: 834, h: 1112 },
  { id: "desktop", label: "Desktop", w: 0, h: 0 }, // 0 = fill
];

const COMMON = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8760"];

export default function PreviewView() {
  const [url, setUrl] = useLocalStorage<string>("aura.domain.previewUrl", "http://localhost:5173");
  const [draft, setDraft] = useState(url);
  const [device, setDevice] = useLocalStorage<string>("aura.domain.previewDevice", "desktop");
  const [autoMs, setAutoMs] = useLocalStorage<number>("aura.domain.previewAuto", 0);
  const [nonce, setNonce] = useState(0);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => { setDraft(url); }, [url]);

  // Auto-refresh, when the user explicitly asks for it.
  useEffect(() => {
    if (!autoMs) return;
    const t = setInterval(() => setNonce((n) => n + 1), autoMs);
    return () => clearInterval(t);
  }, [autoMs]);

  const preset = PRESETS.find((p) => p.id === device) ?? PRESETS[2];
  const framed = preset.w > 0;

  return (
    <div className="dprev">
      <header className="dgit__head">
        <form
          className="dprev__bar"
          onSubmit={(e) => { e.preventDefault(); setUrl(draft.trim()); setNonce((n) => n + 1); }}
        >
          <input
            className="dprev__url"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="http://localhost:5173"
            list="aura-preview-urls"
            spellCheck={false}
          />
          <datalist id="aura-preview-urls">
            {COMMON.map((u) => <option key={u} value={u} />)}
          </datalist>
          <button type="submit" className="dgit__btn dgit__btn--primary">Go</button>
          <button type="button" className="dgit__btn" onClick={() => setNonce((n) => n + 1)}>Reload</button>
        </form>

        <div className="dprev__tools">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              className={"dgit__btn" + (device === p.id ? " dgit__btn--primary" : "")}
              onClick={() => setDevice(p.id)}
            >
              {p.label}
            </button>
          ))}
          <select
            className="dprev__auto"
            value={autoMs}
            onChange={(e) => setAutoMs(Number(e.target.value))}
            title="Auto-refresh"
          >
            <option value={0}>manual</option>
            <option value={2000}>2s</option>
            <option value={5000}>5s</option>
            <option value={15000}>15s</option>
          </select>
        </div>
      </header>

      <div className={"dprev__stage" + (framed ? " dprev__stage--framed" : "")}>
        {url ? (
          <iframe
            key={nonce}
            ref={frameRef}
            className="dprev__frame"
            src={url}
            title="Live preview"
            style={framed ? { width: preset.w, height: preset.h } : undefined}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          />
        ) : (
          <p className="pane-note">Enter the URL your dev server is running on.</p>
        )}
      </div>

      <p className="dprev__hint">
        Start the server in Build or Terminal first — the preview only displays
        it, it never launches anything on its own.
      </p>
    </div>
  );
}
