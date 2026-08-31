import { useCallback, useEffect, useState } from "react";
import {
  api,
  type MistakeRow,
  type SessionSummary,
  type TrendRow,
} from "../api";
import type { V3Event } from "../types";

/**
 * The V3 intelligence panel — the UI face of the two engines in
 * modules/error_intelligence and modules/developer_state.
 *
 * Three things AURA now knows and never had anywhere to say:
 *   1. how this coding session is actually going (state + confidence),
 *   2. what you got wrong today (the mistake tracker),
 *   3. whether that's better or worse than last week (trends).
 *
 * Data arrives two ways. /api/v3/snapshot gives the full picture on mount and
 * on the poll; live announcements stream in over the websocket as `v3` frames
 * and are passed down as `events` so the feed updates the instant something
 * happens rather than on the next poll tick.
 */

const POLL_MS = 15000;

// Severity → accent. Matches the Level enum in error_intelligence/models.py.
const LEVEL_TONE: Record<string, string> = {
  SILLY: "intel-chip--silly",
  MEDIUM: "intel-chip--medium",
  CONCEPTUAL: "intel-chip--concept",
  DANGEROUS: "intel-chip--danger",
};

function confidenceTone(c: number): string {
  if (c >= 88) return "intel-gauge--hot";
  if (c >= 65) return "intel-gauge--good";
  if (c >= 40) return "intel-gauge--fair";
  return "intel-gauge--low";
}

function trendLabel(t: TrendRow): { text: string; cls: string } {
  if (t.direction === "new") return { text: "new", cls: "intel-trend--new" };
  if (t.delta_pct === null) return { text: "—", cls: "" };
  const pct = Math.round(Math.abs(t.delta_pct));
  if (t.direction === "down") return { text: `down ${pct}%`, cls: "intel-trend--down" };
  if (t.direction === "up") return { text: `up ${pct}%`, cls: "intel-trend--up" };
  return { text: "steady", cls: "" };
}

function clockTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

interface Props {
  /** Live events from the websocket, newest last. */
  events?: V3Event[];
}

export default function IntelligenceView({ events = [] }: Props) {
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [mistakes, setMistakes] = useState<MistakeRow[]>([]);
  const [trends, setTrends] = useState<TrendRow[]>([]);
  const [history, setHistory] = useState<V3Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  // Ad-hoc classifier — paste an error, see what the knowledge base makes of
  // it. Sent with record=false so experimenting here can't skew today's count.
  const [probe, setProbe] = useState("");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);

  const load = useCallback(() => {
    api
      .getV3Snapshot()
      .then((s) => {
        setSession(s.session);
        setMistakes(s.mistakes || []);
        setTrends(s.trends || []);
        setHistory(s.events || []);
        setOffline(false);
        setLoading(false);
      })
      .catch(() => {
        setOffline(true);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  // A live error event changes the counts, so refresh rather than guess.
  useEffect(() => {
    const last = events[events.length - 1];
    if (last && (last.kind === "error" || last.kind === "build")) load();
  }, [events, load]);

  const runProbe = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!probe.trim() || probing) return;
    setProbing(true);
    try {
      const r = await api.explainError(probe.trim(), false);
      setProbeResult(
        r.matched
          ? `${r.emoji} ${r.label} — ${r.category}/${r.level}. ${r.explanation}`
          : "Not in the knowledge base — AURA would ask a model for this one.",
      );
    } catch {
      setProbeResult("Bridge unreachable.");
    } finally {
      setProbing(false);
    }
  };

  // Merge polled history with the live tail, newest first, de-duped by ts+text.
  const feed = (() => {
    const seen = new Set<string>();
    return [...history, ...events]
      .filter((e) => {
        const k = `${e.ts}|${e.text}`;
        if (seen.has(k)) return false;
        seen.add(k);
        return Boolean(e.text);
      })
      .sort((a, b) => b.ts - a.ts)
      .slice(0, 25);
  })();

  const totalToday = mistakes.reduce((n, m) => n + m.count, 0);

  return (
    <div className="view">
      <div className="view__head">
        <h2>Intelligence</h2>
        <span className="view__count">
          {session ? `${session.state_emoji} ${session.state}` : "—"}
        </span>
      </div>
      <p className="view__hint">
        What AURA notices while you work — and mostly keeps to herself.
      </p>

      {loading && <p className="view__empty">Reading the session...</p>}
      {offline && !loading && (
        <p className="view__empty">
          Bridge offline — start AURA's brain to see session intelligence.
        </p>
      )}

      {!loading && !offline && session && (
        <>
          {/* ── Session state + confidence ──────────────────────────────── */}
          <section className="intel-session">
            <div className={"intel-gauge " + confidenceTone(session.confidence)}>
              <span className="intel-gauge__num">{session.confidence}</span>
              <span className="intel-gauge__cap">confidence</span>
              <div className="intel-gauge__bar">
                <span style={{ width: `${Math.max(2, session.confidence)}%` }} />
              </div>
            </div>

            <div className="intel-stats">
              <Stat label="Session" value={`${Math.round(session.session_minutes)}m`} />
              <Stat label="Flow" value={`${Math.round(session.flow_minutes)}m`} />
              <Stat
                label="Builds"
                value={`${session.builds_success}/${session.builds_total}`}
              />
              <Stat label="Success" value={`${session.success_rate}%`} />
              <Stat label="Open errors" value={String(session.errors_now)} />
              <Stat label="Debugging" value={`${Math.round(session.debug_minutes)}m`} />
            </div>
          </section>

          {/* ── Today's mistakes ────────────────────────────────────────── */}
          <div className="intel-sec">
            <h3 className="intel-sec__title">
              Today&apos;s mistakes
              <span className="intel-sec__count">{totalToday}</span>
            </h3>
            {mistakes.length === 0 ? (
              <p className="intel-empty">Nothing logged today. Suspiciously clean.</p>
            ) : (
              <ul className="intel-list">
                {mistakes.map((m) => {
                  const t = trends.find((x) => x.id === m.id);
                  const tl = t ? trendLabel(t) : null;
                  return (
                    <li key={m.id} className="intel-row">
                      <span className="intel-row__label">{m.label}</span>
                      {tl && <span className={"intel-trend " + tl.cls}>{tl.text}</span>}
                      <span className="intel-row__count">{m.count}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* ── Trends (7-day) ──────────────────────────────────────────── */}
          {trends.length > 0 && (
            <div className="intel-sec">
              <h3 className="intel-sec__title">This week vs last</h3>
              <ul className="intel-list">
                {trends.map((t) => {
                  const tl = trendLabel(t);
                  return (
                    <li key={t.id} className="intel-row">
                      <span className="intel-row__label">{t.label}</span>
                      <span className="intel-row__sub">
                        {t.previous} → {t.recent}
                      </span>
                      <span className={"intel-trend " + tl.cls}>{tl.text}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* ── Live feed ───────────────────────────────────────────────── */}
          <div className="intel-sec">
            <h3 className="intel-sec__title">What she noticed</h3>
            {feed.length === 0 ? (
              <p className="intel-empty">Quiet so far. That&apos;s the point.</p>
            ) : (
              <ul className="intel-feed">
                {feed.map((e, i) => (
                  <li key={`${e.ts}-${i}`} className="intel-event">
                    <span className="intel-event__time">{clockTime(e.ts)}</span>
                    {e.level && (
                      <span className={"intel-chip " + (LEVEL_TONE[e.level] || "")}>
                        {e.level}
                      </span>
                    )}
                    <span className="intel-event__text">{e.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* ── Ad-hoc classifier ───────────────────────────────────────── */}
          <div className="intel-sec">
            <h3 className="intel-sec__title">Ask the knowledge base</h3>
            <form className="taskadd" onSubmit={runProbe}>
              <input
                value={probe}
                onChange={(e) => setProbe(e.target.value)}
                placeholder="Paste an error to classify (not recorded)..."
              />
              <button type="submit" disabled={probing}>
                {probing ? "..." : "Classify"}
              </button>
            </form>
            {probeResult && <p className="intel-probe">{probeResult}</p>}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="intel-stat">
      <span className="intel-stat__value">{value}</span>
      <span className="intel-stat__label">{label}</span>
    </div>
  );
}
