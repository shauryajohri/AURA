import { useMemo, useState } from "react";
import { api } from "../api";
import type { InstallProposal, Job, ProposalModel } from "../types";
import { useRosterStore } from "../stores/rosterStore";

/**
 * The install card — what AURA shows after you paste an API key or an
 * "install <link>". It asks only what it can't work out itself: which
 * service (when the key has no telltale prefix), the key (when you pasted a
 * link), which models become planets and what each one is for. AURA's own
 * guess is pre-ticked; Install test-calls every ticked model first.
 */

const JOBS: Job[] = ["Coding", "Research", "Chat", "Vision", "Background"];
const JOB_HINT: Record<Job, string> = {
  Coding: "Writes and fixes code",
  Research: "Research, plans and long explanations",
  Chat: "Everyday conversation",
  Vision: "Looks at images and your screen",
  Background: "Quick background jobs — sorting messages, memory, nudges",
};
const SHOW = 6;

interface Props {
  proposal: InstallProposal;
  /** Tighter layout for the chat bubble. */
  inChat?: boolean;
}

function initialPicks(models: ProposalModel[]): Record<string, Job[]> {
  const out: Record<string, Job[]> = {};
  for (const m of models) if (m.selected && !m.existing) out[m.id] = m.jobs.length ? m.jobs : m.best_for.slice(0, 1);
  return out;
}

export default function InstallCard({ proposal, inChat = false }: Props) {
  const [prop, setProp] = useState<InstallProposal>(proposal);
  const [picks, setPicks] = useState<Record<string, Job[]>>(() => initialPicks(proposal.models));
  const [position, setPosition] = useState<"first" | "backup">(proposal.position || "backup");
  const [provider, setProvider] = useState(proposal.provider || "");
  const [key, setKey] = useState("");
  const [base, setBase] = useState(proposal.base_url || "");
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState<"" | "check" | "install">("");
  const [err, setErr] = useState("");
  const [dismissed, setDismissed] = useState(false);
  const reloadRoster = useRosterStore((s) => s.load);

  const adopt = (p: InstallProposal) => {
    setProp(p);
    setPicks(initialPicks(p.models));
    setProvider(p.provider || "");
    setBase(p.base_url || "");
    setShowAll(false);
  };

  const check = async (overrides: { provider?: string } = {}) => {
    setBusy("check");
    setErr("");
    try {
      const res = await api.identifyInstall(prop.id, {
        provider: overrides.provider ?? (provider !== prop.provider ? provider : undefined),
        key: key.trim() || undefined,
        base_url: base.trim() && base.trim() !== prop.base_url ? base.trim() : undefined,
      });
      if (!res.ok || !res.proposal) throw new Error(res.error || "that didn't work");
      setKey("");
      adopt(res.proposal);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };

  const install = async () => {
    setBusy("install");
    setErr("");
    try {
      const models = Object.entries(picks).map(([id, jobs]) => ({ id, jobs }));
      const res = await api.confirmInstall(prop.id, {
        models, position,
        search_jobs: prop.kind === "search" ? ["Research", "Search"] : undefined,
      });
      if (res.proposal) setProp(res.proposal);
      if (!res.ok) throw new Error(res.error || res.message || "nothing was installed");
      void reloadRoster();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };

  const skip = async () => {
    setDismissed(true);
    try { await api.dismissInstall(prop.id); } catch { /* the card is gone either way */ }
  };

  const togglePick = (m: ProposalModel) => {
    if (m.existing) return;
    setPicks((cur) => {
      const next = { ...cur };
      if (next[m.id]) delete next[m.id];
      else next[m.id] = m.best_for.slice(0, 2);
      return next;
    });
  };

  const toggleJob = (m: ProposalModel, job: Job) => {
    if (m.existing) return;
    setPicks((cur) => {
      const jobs = cur[m.id] ?? [];
      const has = jobs.includes(job);
      const nextJobs = has ? jobs.filter((j) => j !== job) : JOBS.filter((j) => j === job || jobs.includes(j));
      const next = { ...cur };
      if (nextJobs.length) next[m.id] = nextJobs;
      else delete next[m.id];
      return next;
    });
  };

  const models = prop.models ?? [];
  const visible = useMemo(() => {
    if (showAll) return models;
    const first = models.slice(0, SHOW);
    // never hide a ticked model behind "show more"
    const ticked = models.slice(SHOW).filter((m) => picks[m.id]);
    return [...first, ...ticked];
  }, [models, showAll, picks]);
  const chosen = Object.keys(picks).length;

  if (dismissed) {
    return <div className="icard icard--done"><p className="icard__line">Skipped — nothing was installed.</p></div>;
  }

  const keyLine = prop.key_from
    ? `Using your ${prop.key_from} from .env`
    : prop.key_masked
      ? `Key ${prop.key_masked}`
      : prop.provider === "ollama" || prop.provider === "lmstudio"
        ? "Runs on this PC — no key needed"
        : "";

  const needsKeyField = prop.stage === "need_key" || prop.stage === "need_provider"
    || (prop.stage === "error" && !prop.key_from);
  const serviceField = prop.stage === "need_provider" || prop.stage === "error";

  return (
    <div className={"icard" + (inChat ? " icard--chat" : "") + (prop.stage === "installed" ? " icard--done" : "")}>
      <header className="icard__head">
        <span className={"icard__orb icard__orb--" + (prop.kind === "search" ? "search" : "llm")} aria-hidden />
        <div className="icard__title">
          <strong>{prop.label}</strong>
          {(keyLine || prop.cost) && (
            <span className="icard__sub">
              {keyLine}
              {keyLine && prop.cost && prop.cost !== "unknown" ? ", " : ""}
              {prop.cost && prop.cost !== "unknown" ? prop.cost : ""}
            </span>
          )}
        </div>
      </header>

      {/* In chat, AURA's own line already said the first error — only repeat newer ones. */}
      {prop.stage === "error" && prop.error && !(inChat && prop.error === proposal.error) && (
        <p className="icard__err" role="alert">{prop.error}</p>
      )}

      {/* ── which service / key / base URL ─────────────────────────────── */}
      {(serviceField || needsKeyField || prop.stage === "need_base_url") && prop.stage !== "installed" && (
        <form className="icard__ask" onSubmit={(e) => { e.preventDefault(); void check(); }}>
          {serviceField && (
            <label className="icard__field">
              <span>Which service is this for?</span>
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="" disabled>Pick a service</option>
                {prop.providers.filter((p) => p.kind === "llm").map((p) => (
                  <option key={p.id} value={p.id}>{p.label}{p.cost && p.cost !== "unknown" ? ` (${p.cost})` : ""}</option>
                ))}
                <optgroup label="Web search">
                  {prop.providers.filter((p) => p.kind === "search").map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </optgroup>
              </select>
            </label>
          )}
          {(prop.stage === "need_base_url" || provider === "custom") && (
            <label className="icard__field">
              <span>Its base URL</span>
              <input value={base} onChange={(e) => setBase(e.target.value)} placeholder="https://api.example.com/v1"
                     spellCheck={false} autoComplete="off" />
            </label>
          )}
          {needsKeyField && provider !== "ollama" && provider !== "lmstudio" && (
            <label className="icard__field">
              <span>{prop.stage === "need_key" ? `Your ${prop.label} API key` : "API key (only if it changed)"}</span>
              <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
                     placeholder="Paste it here — it stays on this PC" autoComplete="off" spellCheck={false} />
            </label>
          )}
          <div className="icard__actions">
            <button type="submit" className="icard__btn icard__btn--go"
                    disabled={busy !== "" || (serviceField && !provider) || (prop.stage === "need_key" && !key.trim())}>
              {busy === "check" ? "Checking…" : "Check it"}
            </button>
            <button type="button" className="icard__btn" onClick={skip} disabled={busy !== ""}>Not now</button>
          </div>
        </form>
      )}

      {/* ── models → planets ───────────────────────────────────────────── */}
      {prop.stage === "choose" && prop.kind === "llm" && (
        <>
          <p className="icard__q">Tick the models that should become planets, and what each one is for.</p>
          <ul className="icard__models">
            {visible.map((m) => {
              const on = !!picks[m.id];
              const jobs = picks[m.id] ?? [];
              return (
                <li key={m.id} className={"icard__model" + (on ? " is-on" : "") + (m.existing ? " is-existing" : "")}>
                  <label className="icard__pick">
                    <input type="checkbox" checked={on} disabled={m.existing} onChange={() => togglePick(m)} />
                    <span className="icard__name" title={m.desc || m.id}>{m.name}</span>
                    <span className="icard__meta">
                      {m.existing ? "already a planet" : [
                        m.cost, m.context, m.vision ? "sees images" : "",
                      ].filter(Boolean).join(" · ")}
                    </span>
                  </label>
                  {!m.existing && (
                    <div className="icard__jobs" role="group" aria-label={`Jobs for ${m.name}`}>
                      {JOBS.map((j) => (
                        <button key={j} type="button" aria-pressed={jobs.includes(j)}
                                className={"icard__job" + (jobs.includes(j) ? " is-on" : "")
                                  + (m.best_for.includes(j) ? " is-best" : "")}
                                title={`${j}: ${JOB_HINT[j]}` + (m.best_for.includes(j) ? " — AURA thinks it's good at this" : "")}
                                onClick={() => toggleJob(m, j)}>
                          {j}
                        </button>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {models.length > SHOW && (
            <button type="button" className="icard__more" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "Show fewer" : `Show all ${models.length} I checked (of ${prop.total_models})`}
            </button>
          )}
          <fieldset className="icard__pos">
            <legend>When should I use {chosen === 1 ? "it" : "them"}?</legend>
            <label className={position === "backup" ? "is-on" : ""}>
              <input type="radio" name={`pos-${prop.id}`} checked={position === "backup"} onChange={() => setPosition("backup")} />
              As a backup, after my current models
            </label>
            <label className={position === "first" ? "is-on" : ""}>
              <input type="radio" name={`pos-${prop.id}`} checked={position === "first"} onChange={() => setPosition("first")} />
              First, before my current models
            </label>
          </fieldset>
          <div className="icard__actions">
            <button type="button" className="icard__btn icard__btn--go" onClick={install}
                    disabled={busy !== "" || chosen === 0}>
              {busy === "install"
                ? `Testing ${chosen} model${chosen === 1 ? "" : "s"}…`
                : chosen === 0 ? "Tick a model to install" : `Install ${chosen} planet${chosen === 1 ? "" : "s"}`}
            </button>
            <button type="button" className="icard__btn" onClick={skip} disabled={busy !== ""}>Not now</button>
          </div>
        </>
      )}

      {/* ── a web search API ───────────────────────────────────────────── */}
      {prop.stage === "choose" && prop.kind === "search" && (
        <>
          <p className="icard__q">{prop.about ? `${prop.about}. ` : ""}Once it's installed, I'll search the web
            when you ask research or look-up questions.</p>
          <div className="icard__actions">
            <button type="button" className="icard__btn icard__btn--go" onClick={install} disabled={busy !== ""}>
              {busy === "install" ? "Running a test search…" : "Install web search"}
            </button>
            <button type="button" className="icard__btn" onClick={skip} disabled={busy !== ""}>Not now</button>
          </div>
        </>
      )}

      {/* ── outcome ────────────────────────────────────────────────────── */}
      {prop.results?.length > 0 && (
        <ul className="icard__results">
          {prop.results.map((r) => (
            <li key={r.id} className={r.ok ? "is-ok" : "is-bad"}>
              <span className="icard__mark" aria-hidden>{r.ok ? "✓" : "✕"}</span>
              <span className="icard__rname">{r.name}</span>
              <span className="icard__rwhy">
                {r.ok
                  ? [r.jobs?.join(" & "), r.ms ? `answered in ${(r.ms / 1000).toFixed(1)}s` : "", r.why].filter(Boolean).join(", ")
                  : r.why}
              </span>
            </li>
          ))}
        </ul>
      )}
      {prop.stage === "installed" && (
        <p className="icard__line">
          {prop.kind === "search" ? "Web search is on." : "Orbiting the core now — look for it on Home."}
        </p>
      )}

      {err && <p className="icard__err" role="alert">{err}</p>}
    </div>
  );
}
