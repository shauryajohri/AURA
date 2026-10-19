import { useEffect, useState } from "react";
import { api, PhoneReportPreview, Settings } from "../../api";

// ============================================================================
// Phone report settings. AURA rings your phone and reads out what's waiting on
// you, what's coming up, and how each project is doing.
//
// Two halves, like Voice: the controls edit the settings DRAFT (saved with the
// rest), while the status / preview / "call me now" block talks to the brain
// directly — it's an action, not a setting.
// ============================================================================

const E164 = /^\+[1-9]\d{7,14}$/;

interface ControlsProps {
  draft: Settings;
  set: (k: string, v: number | boolean | string) => void;
}

export function PhoneReportControls({ draft, set }: ControlsProps) {
  const str = (k: string) => String(draft[k] ?? "");
  const on = (k: string) => Boolean(draft[k]);
  const number = str("phone.number").replace(/[\s\-().]/g, "");

  const toggle = (k: string, label: string) => (
    <div className="setov__row">
      <span className="setov__label">{label}</span>
      <button className={"san-toggle" + (on(k) ? " san-toggle--on" : "")} onClick={() => set(k, !on(k))}>
        <span className="san-toggle__knob" />
      </button>
    </div>
  );
  const time = (k: string) => (
    <input
      className="setov__input setov__input--time"
      type="time"
      value={str(k)}
      onChange={(e) => set(k, e.target.value)}
    />
  );

  return (
    <div className="setov__controls">
      <div className="setov__row">
        <span className="setov__label">Your phone number</span>
        <input
          className="setov__input"
          type="tel"
          placeholder="+919876543210"
          value={str("phone.number")}
          onChange={(e) => set("phone.number", e.target.value)}
        />
      </div>
      {number !== "" && !E164.test(number) && (
        <p className="setov__hint">
          Use the international form: a plus sign, country code, then the number.
        </p>
      )}

      {toggle("phone.enabled", "Automatic calls")}

      <div className="setov__row">
        <span className="setov__label">Daily report</span>
        {on("phone.daily") && time("phone.daily_time")}
        <button
          className={"san-toggle" + (on("phone.daily") ? " san-toggle--on" : "")}
          onClick={() => set("phone.daily", !on("phone.daily"))}
        >
          <span className="san-toggle__knob" />
        </button>
      </div>

      {toggle("phone.milestones", "Call on milestones")}

      <div className="setov__row">
        <span className="setov__label">Call before a meeting</span>
        {on("phone.meeting_alert") && (
          <>
            <input
              className="setov__input setov__input--num"
              type="number" min={1} max={120}
              value={Number(draft["phone.meeting_lead"]) || 15}
              onChange={(e) => set("phone.meeting_lead", Number(e.target.value) || 15)}
            />
            <span className="setov__val">min</span>
          </>
        )}
        <button
          className={"san-toggle" + (on("phone.meeting_alert") ? " san-toggle--on" : "")}
          onClick={() => set("phone.meeting_alert", !on("phone.meeting_alert"))}
        >
          <span className="san-toggle__knob" />
        </button>
      </div>

      <div className="setov__row">
        <span className="setov__label">Quiet hours</span>
        {time("phone.quiet_start")}
        <span className="setov__val">to</span>
        {time("phone.quiet_end")}
      </div>
      <p className="setov__hint">
        Milestones are a feature or project reaching 100%, or a task becoming
        blocked. Automatic calls never ring during quiet hours — a call you ask
        for always does.
      </p>
    </div>
  );
}

const CALENDAR_NOTE: Record<string, string> = {
  not_connected: "No calendar connected — meetings come from Microsoft 365 (Domain → Settings → Connectors). Reminders and due tasks are still read out.",
  needs_reconnect: "Microsoft 365 was connected before calendar access was added — reconnect it to include meetings.",
  error: "Couldn't read the calendar just now; the call will go ahead without meetings.",
};

/** Status, what the call would say, and the button that places it. */
export function PhoneReportActions({ dirty }: { dirty: boolean }) {
  const [data, setData] = useState<PhoneReportPreview | null>(null);
  const [offline, setOffline] = useState(false);
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<"idle" | "calling" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getPhoneReport().then(setData).catch(() => setOffline(true));
  }, []);

  const call = async () => {
    setPhase("calling");
    try {
      const r = await api.callPhoneReport();
      setPhase(r.ok ? "done" : "error");
      setMsg(r.ok ? `Calling ${r.to} now.` : r.error ?? "The call couldn't be placed.");
    } catch {
      setPhase("error");
      setMsg("Couldn't reach the brain — is server.py running?");
    }
  };

  if (offline) {
    return <p className="setov__hint">Brain offline — start server.py to preview or place a call.</p>;
  }
  if (!data) return <p className="setov__hint">Building the report…</p>;

  const st = data.status;
  return (
    <div className="setov__phone">
      {!st.twilio_configured && (
        <p className="setov__hint">
          Calls go out through Twilio. Add <code>{st.missing_env.join(", ")}</code> to{" "}
          <code>.env</code> next to server.py and restart the brain.
        </p>
      )}
      {CALENDAR_NOTE[data.report.calendar] && (
        <p className="setov__hint">{CALENDAR_NOTE[data.report.calendar]}</p>
      )}
      {st.last && (
        <p className="setov__hint">
          Last call: {st.last.kind}, {st.last.when.replace("T", " ")} —{" "}
          {st.last.ok ? "placed" : st.last.error}
        </p>
      )}

      <div className="setov__dangerrow">
        <button className="setov__cancel" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Preview"} what she'll say
        </button>
        <button
          className="setov__save"
          onClick={call}
          disabled={!st.ready || dirty || phase === "calling"}
          title={dirty ? "Save your changes first" : st.ready ? "" : "Needs a saved number and Twilio keys"}
        >
          {phase === "calling" ? "Calling…" : `Call ${st.number || "me"} now`}
        </button>
        {dirty && <span className="setov__hint">Save first — the call uses the saved number.</span>}
        {(phase === "done" || phase === "error") && <span className="setov__hint">{msg}</span>}
      </div>

      {open && (
        <div className="setov__script">
          {data.script.map((p, i) => <p key={i}>{p}</p>)}
        </div>
      )}
    </div>
  );
}
