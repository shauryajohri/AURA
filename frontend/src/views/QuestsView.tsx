import { useCallback, useEffect, useState } from "react";
import { api, type Quest, type QuestBoard, type QuestPreset } from "../api";
import type { QuestEvent } from "../types";

/**
 * Quests — the daily board AURA actually verifies.
 *
 * A task is ticked off by hand. A quest fills up only while the work is
 * genuinely on screen: core/quests.py matches the window against the quest's
 * keyword pack every 30 seconds and credits real seconds, so "2h Japanese"
 * means two hours that actually happened.
 *
 * The pressure banner is the other half — when what's left no longer fits in
 * the hours remaining, it says so instead of letting the day quietly run out.
 */

const POLL_MS = 20000;

function fmt(seconds: number): string {
  const m = Math.floor(Math.max(0, seconds) / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm === 0 ? `${h}h` : `${h}h ${mm}m`;
}

const PRESSURE_COPY: Record<string, { label: string; cls: string }> = {
  clear: { label: "Board clear", cls: "qpress--clear" },
  ok: { label: "On track", cls: "qpress--ok" },
  tight: { label: "Tight", cls: "qpress--tight" },
  rush: { label: "Rush", cls: "qpress--rush" },
  impossible: { label: "Won't fit", cls: "qpress--bad" },
  out_of_time: { label: "Day's gone", cls: "qpress--bad" },
  unknown: { label: "—", cls: "" },
};

interface Props {
  /** Latest tracker event from the websocket — triggers an immediate refresh. */
  event?: QuestEvent | null;
}

export default function QuestsView({ event = null }: Props) {
  const [board, setBoard] = useState<QuestBoard | null>(null);
  const [presets, setPresets] = useState<QuestPreset[]>([]);
  const [streaks, setStreaks] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editKeywords, setEditKeywords] = useState("");
  const [editMinutes, setEditMinutes] = useState(60);
  const [editPreset, setEditPreset] = useState("custom");
  const [editPath, setEditPath] = useState("");
  // What AURA is actually watching for — shown so a quest that isn't filling
  // up can be diagnosed instead of the matcher being a black box.
  const [terms, setTerms] = useState<{ anchors: string[]; supporting: string[] } | null>(null);

  const load = useCallback(() => {
    api
      .getQuests()
      .then((b) => {
        setBoard(b);
        setOffline(false);
        setLoading(false);
      })
      .catch(() => {
        setOffline(true);
        setLoading(false);
      });
    api.getQuestHistory(30).then((h) => setStreaks(h.streaks)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    api.getQuestPresets().then(setPresets).catch(() => {});
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  // The tracker just credited time or completed something — don't wait 20s.
  useEffect(() => {
    if (event) load();
  }, [event, load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    // Sent as free text: the backend parses "japanese 2 hrs" into a title,
    // a duration and a matching keyword preset.
    await api.addQuest({ text }).catch(() => setOffline(true));
    load();
  };

  const openEdit = (q: Quest) => {
    setEditing(editing === q.id ? null : q.id);
    setEditKeywords(q.keywords);
    setEditMinutes(q.target_minutes);
    setEditPreset(q.preset);
    setEditPath(q.project_path || "");
    setTerms(null);
    api
      .getQuestTerms(q.id)
      .then((t) => setTerms({ anchors: t.anchors, supporting: t.supporting }))
      .catch(() => setTerms(null));
  };

  const saveEdit = async (q: Quest) => {
    const preset = presets.find((p) => p.id === editPreset);
    await api
      .updateQuest(q.id, {
        keywords: editKeywords,
        target_minutes: editMinutes,
        preset: editPreset,
        project_path: editPath,
        // Follow the pack's colour unless the quest was already customised.
        ...(preset && q.preset !== editPreset ? { color: preset.color } : {}),
      })
      .catch(() => setOffline(true));
    setEditing(null);
    load();
  };

  const quests = board?.quests ?? [];
  // Untimed quests have no goal, so they're not part of "3/5 done".
  const timed = quests.filter((q) => !q.untimed);
  const doneCount = timed.filter((q) => q.completed).length;
  const totalTracked = quests.reduce((n, q) => n + q.seconds, 0);
  const pressure = board?.pressure;
  const pc = PRESSURE_COPY[pressure?.status ?? "unknown"] ?? PRESSURE_COPY.unknown;

  return (
    <div className="view">
      <div className="view__head">
        <h2>Quests</h2>
        <span className="view__count">
          {quests.length === 0
            ? "none yet"
            : timed.length === 0
            ? `${fmt(totalTracked)} tracked`
            : `${doneCount}/${timed.length} done`}
        </span>
      </div>
      <p className="view__hint">
        Daily commitments AURA verifies from your screen — time only counts
        while you're actually doing the thing.
      </p>

      <form className="taskadd" onSubmit={add}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder='"japanese 2 hrs" for a target, or just "aura code base" to only track it'
        />
        <button type="submit">Add</button>
      </form>

      {loading && <p className="view__empty">Loading today's board...</p>}
      {offline && !loading && (
        <p className="view__empty">Brain offline — start AURA to track quests.</p>
      )}

      {!loading && !offline && (
        <>
          {/* ── Pressure banner: does the rest of the day still fit? ──── */}
          {/* Nothing to be under pressure ABOUT when every quest is untimed. */}
          {pressure && timed.length > 0 && (
            <div className={"qpress " + pc.cls}>
              <span className="qpress__tag">{pc.label}</span>
              {pressure.status === "clear" ? (
                <span className="qpress__text">
                  Everything's done. {fmt(totalTracked)} tracked today.
                </span>
              ) : (
                <span className="qpress__text">
                  {fmt(pressure.required_minutes * 60)} of quests left ·{" "}
                  {fmt(pressure.available_minutes * 60)} of day remaining
                  {pressure.deficit_minutes > 0 &&
                    ` · ${fmt(pressure.deficit_minutes * 60)} short`}
                </span>
              )}
            </div>
          )}

          {quests.length === 0 && (
            <p className="view__empty">
              No quests yet. Add one above — AURA will watch for it and count
              the time herself.
            </p>
          )}

          {/* ── The board ─────────────────────────────────────────────── */}
          <ul className="qlist">
            {quests.map((q) => {
              const active = board?.active_quest_id === q.id;
              const streak = streaks[String(q.id)] ?? 0;
              return (
                <li
                  key={q.id}
                  className={
                    "qcard" +
                    (q.completed ? " qcard--done" : "") +
                    (active ? " qcard--active" : "")
                  }
                  style={{ ["--qc" as string]: q.color }}
                >
                  <div className="qcard__top">
                    <span className="qcard__title">{q.title}</span>
                    {active && <span className="qcard__live">tracking now</span>}
                    {streak > 1 && <span className="qcard__streak">{streak}d streak</span>}
                    {q.overtime_seconds > 0 && (
                      <span className="qcard__over">+{fmt(q.overtime_seconds)}</span>
                    )}
                    <span className="qcard__time">
                      {fmt(q.seconds)}
                      {/* An untimed quest has no denominator to show. */}
                      {!q.untimed && <em> / {fmt(q.target_seconds)}</em>}
                    </span>
                  </div>

                  {/* Untimed quests get a flat "always accumulating" rail
                      rather than a progress bar — there's nothing to fill. */}
                  <div className={"qcard__bar" + (q.untimed ? " qcard__bar--open" : "")}>
                    <span style={{ width: q.untimed ? "100%" : `${q.percent}%` }} />
                  </div>

                  <div className="qcard__foot">
                    <span className="qcard__meta">
                      {q.untimed
                        ? "no target · monitored"
                        : q.completed
                        ? q.overtime_seconds > 0
                          ? `complete · ${fmt(q.overtime_seconds)} extra`
                          : "complete"
                        : `${fmt(q.remaining_seconds)} to go`}
                      {q.preset !== "custom" && ` · ${q.preset}`}
                    </span>
                    <span className="qcard__actions">
                      <button onClick={() => api.adjustQuest(q.id, 15).then(load)}>
                        +15m
                      </button>
                      <button
                        onClick={() => api.completeQuest(q.id, q.completed).then(load)}
                      >
                        {q.completed ? "reopen" : "mark done"}
                      </button>
                      <button onClick={() => openEdit(q)}>edit</button>
                      <button onClick={() => api.deleteQuest(q.id).then(load)}>×</button>
                    </span>
                  </div>

                  {editing === q.id && (
                    <div className="qedit">
                      <label>
                        Target (minutes) — leave 0 to just monitor it with no goal
                        <input
                          type="number"
                          min={0}
                          value={editMinutes}
                          onChange={(e) => setEditMinutes(Number(e.target.value))}
                        />
                      </label>
                      <label>
                        Keyword pack — what AURA looks for on screen
                        <select
                          value={editPreset}
                          onChange={(e) => setEditPreset(e.target.value)}
                        >
                          {presets.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.icon} {p.label}
                              {p.keyword_count ? ` — ${p.keyword_count} terms` : ""}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Extra keywords — comma separated. AURA already knows the{" "}
                        <strong>{editPreset}</strong> pack; add anything specific to you.
                        <input
                          value={editKeywords}
                          onChange={(e) => setEditKeywords(e.target.value)}
                          placeholder="e.g. tobira, sakura textbook, my sensei's site"
                        />
                      </label>
                      <label>
                        Project folder — optional. Point this at a codebase and
                        AURA learns its vocabulary (module and folder names), so
                        the quest counts wherever that project comes up: your
                        editor, GitHub, or a Claude conversation about it.
                        <input
                          value={editPath}
                          onChange={(e) => setEditPath(e.target.value)}
                          placeholder="C:\\Users\\shaur\\Downloads\\AURA"
                        />
                      </label>

                      {terms && (
                        <div className="qterms">
                          <span className="qterms__head">
                            AURA counts this quest when she sees:
                          </span>
                          <div className="qterms__row">
                            {terms.anchors.slice(0, 28).map((t) => (
                              <span key={t} className="qterms__chip">{t}</span>
                            ))}
                            {terms.anchors.length > 28 && (
                              <span className="qterms__more">
                                +{terms.anchors.length - 28} more
                              </span>
                            )}
                          </div>
                          {terms.anchors.length === 0 && (
                            <span className="qterms__warn">
                              Nothing distinctive to match on — add a keyword or
                              a project folder, or this quest will never fill.
                            </span>
                          )}
                        </div>
                      )}

                      <div className="qedit__btns">
                        <button onClick={() => saveEdit(q)}>Save</button>
                        <button onClick={() => setEditing(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {/* ── Where the day actually went ───────────────────────────── */}
          {(totalTracked > 0 || (board?.unallocated_seconds ?? 0) > 0) && (
            <div className="qsplit">
              <h3 className="intel-sec__title">Where the day went</h3>
              <div className="qsplit__bar">
                {quests
                  .filter((q) => q.seconds > 0)
                  .map((q) => (
                    <span
                      key={q.id}
                      title={`${q.title} — ${fmt(q.seconds)}`}
                      style={{
                        background: q.color,
                        flexGrow: q.seconds,
                      }}
                    />
                  ))}
                {(board?.unallocated_seconds ?? 0) > 0 && (
                  <span
                    className="qsplit__other"
                    title={`Unallocated — ${fmt(board!.unallocated_seconds)}`}
                    style={{ flexGrow: board!.unallocated_seconds }}
                  />
                )}
              </div>
              <div className="qsplit__legend">
                {quests
                  .filter((q) => q.seconds > 0)
                  .map((q) => (
                    <span key={q.id}>
                      <i style={{ background: q.color }} />
                      {q.title} {fmt(q.seconds)}
                    </span>
                  ))}
                {(board?.unallocated_seconds ?? 0) > 0 && (
                  <span>
                    <i className="qsplit__other" />
                    Unallocated {fmt(board!.unallocated_seconds)}
                  </span>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
