import { useEffect, useRef, useState } from "react";
import { api, type Voice } from "../../api";

/**
 * The voice picker.
 *
 * edge-tts voices are server-side, so choosing one is just storing a name —
 * no downloads, no model files. The roster comes from the backend
 * (modules/voice_output.VOICES) rather than being duplicated here, so the
 * list can never offer a voice the speaking code doesn't know about.
 *
 * Every row previews on demand: you hear the voice saying one of AURA's own
 * lines before you commit to it. Playback happens in the browser, not through
 * AURA's pygame mixer, so a preview can't collide with something she is
 * actually in the middle of saying.
 */

interface Props {
  /** Currently selected edge-tts id ("" = nothing chosen, backend default). */
  value: string;
  onChange: (voiceId: string) => void;
}

export default function VoicePicker({ value, onChange }: Props) {
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [fallback, setFallback] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");     // voice id currently rendering
  const [playing, setPlaying] = useState(""); // voice id currently sounding

  // One audio element for the whole picker: previewing a second voice should
  // interrupt the first, not talk over it.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string>("");
  // Set on unmount so an in-flight render doesn't call setState afterwards.
  const goneRef = useRef(false);

  useEffect(() => {
    api
      .getVoices()
      .then((r) => {
        if (goneRef.current) return;
        setVoices(r.voices);
        setFallback(r.selected);
      })
      .catch(() => {
        if (!goneRef.current) setError("Brain offline — start server.py to choose a voice.");
      });
    return () => {
      goneRef.current = true;
      audioRef.current?.pause();
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  const stop = () => {
    audioRef.current?.pause();
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = "";
    }
    setPlaying("");
  };

  const preview = async (id: string) => {
    if (playing === id) { stop(); return; }
    stop();
    setError("");
    setBusy(id);
    try {
      const url = await api.previewVoice(id);
      if (goneRef.current) { URL.revokeObjectURL(url); return; }
      urlRef.current = url;
      const audio = audioRef.current ?? new Audio();
      audioRef.current = audio;
      audio.src = url;
      audio.onended = () => setPlaying("");
      await audio.play();
      setPlaying(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not play that voice.");
    } finally {
      if (!goneRef.current) setBusy("");
    }
  };

  if (error && !voices) return <p className="vpick__note">{error}</p>;
  if (!voices) return <p className="vpick__note">Loading voices…</p>;

  // "" means the user hasn't picked explicitly — highlight whatever the
  // backend actually resolves to, so the panel never looks like nothing is set.
  const active = value || fallback;

  return (
    <div className="vpick">
      <p className="vpick__lead">
        Press ▶ to hear each one say a line of AURA's before you choose.
      </p>

      <div className="vpick__list">
        {voices.map((v) => {
          const on = v.id === active;
          return (
            <div key={v.id} className={"vpick__row" + (on ? " vpick__row--on" : "")}>
              <button
                type="button"
                className="vpick__pick"
                onClick={() => onChange(v.id)}
                aria-pressed={on}
                title={on ? `${v.name} is AURA's voice` : `Use ${v.name}`}
              >
                <span className="vpick__dot">{on ? "◉" : "○"}</span>
                <span className="vpick__meta">
                  <span className="vpick__name">
                    {v.name}
                    <span className="vpick__tag">{v.accent} · {v.gender}</span>
                  </span>
                  <span className="vpick__char">{v.character}</span>
                </span>
              </button>

              <button
                type="button"
                className={"vpick__play" + (playing === v.id ? " vpick__play--on" : "")}
                onClick={() => preview(v.id)}
                disabled={busy !== "" && busy !== v.id}
                title={playing === v.id ? "Stop" : "Hear this voice"}
                aria-label={playing === v.id ? `Stop ${v.name}` : `Hear ${v.name}`}
              >
                {busy === v.id ? "…" : playing === v.id ? "◼" : "▶"}
              </button>
            </div>
          );
        })}
      </div>

      {error && <p className="vpick__err">{error}</p>}
    </div>
  );
}
