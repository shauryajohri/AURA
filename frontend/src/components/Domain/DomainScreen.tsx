import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { uploadToSaved } from "../../lib/files";
import { useSavedStore } from "../../stores/savedStore";
import type { ChatTurn, ConnStatus, LibraryRoot, SavedItem, SavedKind } from "../../types";
import DomainChat from "./DomainChat";
import DomainBoundary from "./DomainBoundary";
import "./domain.css";

// ============================================================================
// AURA Domain — give AURA anything, then ask her to run it.
//
// One box takes a link, a file, a skill or an app. Everything lands in one
// list, and every card has one button: Run. A website opens in its own
// window like an app, a PDF opens to read, an app launches, a skill is
// carried out by AURA in the chat on the right. "open <name>" in any chat
// does the same thing (core/domain_library).
//
// Links and files are Saved Info underneath, so AURA has already read them
// and uses them whenever a conversation touches them. Folders and repos are
// read in place (core/library): AURA searches them on every message, so a
// question about your notes or your code is answered from the files.
// ============================================================================

interface Props {
  onExit: () => void;
  status: ConnStatus;
  turns: ChatTurn[];
  send: (text: string) => void;
}

type Group = "all" | "folder" | "web" | "file" | "skill" | "app";

const GROUP_OF: Record<SavedKind, Exclude<Group, "all">> = {
  link: "web", github: "web", video: "web",
  pdf: "file", doc: "file", image: "file", file: "file",
  skill: "skill", app: "app",
};
const GROUPS: { id: Group; label: string }[] = [
  { id: "all", label: "Everything" },
  { id: "folder", label: "Folders" },
  { id: "web", label: "Websites" },
  { id: "file", label: "Files" },
  { id: "skill", label: "Skills" },
  { id: "app", label: "Apps" },
];
const GLYPH: Record<Exclude<Group, "all">, string> = { folder: "▦", web: "◍", file: "▤", skill: "✦", app: "▣" };
const RUN_LABEL: Record<Exclude<Group, "all" | "folder">, string> = {
  web: "Open", file: "Open", skill: "Run", app: "Launch",
};

const URL_RE = /^(https?:\/\/|www\.)\S+$|^[\w-]+(\.[\w-]+)+(\/\S*)?$/i;
const REPO_RE = /^(https?:\/\/)?(www\.)?github\.com\/[^/\s]+\/[^/\s]+/i;
const PATH_RE = /^([a-z]:[\\/]|\\\\|%\w+%)/i;

function sub(it: SavedItem): string {
  if (it.kind === "app") return "App";
  if (it.kind === "skill") return "Skill";
  if (it.url) {
    try { return new URL(it.url).hostname.replace(/^www\./, ""); } catch { return it.url; }
  }
  return it.file_name || it.kind;
}

export default function DomainScreen({ onExit, status, turns, send }: Props) {
  const items = useSavedStore((s) => s.items);
  const upsert = useSavedStore((s) => s.upsert);
  const remove = useSavedStore((s) => s.remove);

  const [text, setText] = useState("");
  const [ask, setAsk] = useState<null | "choose" | "skill">(null);
  const [skillName, setSkillName] = useState("");
  const [skillBody, setSkillBody] = useState("");
  const [group, setGroup] = useState<Group>("all");
  const [note, setNote] = useState("");
  const [dragging, setDragging] = useState(false);
  const [running, setRunning] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [roots, setRoots] = useState<LibraryRoot[]>([]);

  // Folders AURA can read. Polled while one is being read, so the count
  // climbs on the card instead of the page going quiet for a minute.
  const loadRoots = useCallback(() => {
    api.library().then((r) => setRoots(r.roots ?? [])).catch(() => {});
  }, []);
  useEffect(() => { loadRoots(); }, [loadRoots]);
  const busyRoots = roots.some((r) => r.indexing || r.status === "indexing" || r.status === "idle");
  useEffect(() => {
    if (!busyRoots) return;
    const id = setInterval(loadRoots, 1500);
    return () => clearInterval(id);
  }, [busyRoots, loadRoots]);

  const shown = useMemo(
    () => items.filter((it) => group === "all" || GROUP_OF[it.kind] === group),
    [items, group],
  );
  const counts = useMemo(() => {
    const c: Record<Group, number> = {
      all: items.length + roots.length, folder: roots.length, web: 0, file: 0, skill: 0, app: 0,
    };
    for (const it of items) c[GROUP_OF[it.kind] ?? "file"]++;
    return c;
  }, [items, roots]);

  const done = (it: SavedItem, msg: string) => {
    upsert(it);
    setNote(msg);
    setText("");
    setAsk(null);
  };

  const addLink = async (raw: string) => {
    const res = await api.saveLink(raw);
    if (!res.ok || !res.item) throw new Error(res.error || "couldn't save that link");
    done(res.item, "Saved — AURA is reading it now.");
  };

  // A folder on this PC, or a GitHub repo (cloned, then read like a folder).
  // Returns false when the path isn't a folder, so the caller can try an app.
  const addFolder = async (target: string): Promise<boolean> => {
    const res = await api.addLibrary(target);
    if (res.not_folder) return false;
    if (!res.ok || !res.root) throw new Error(res.error || "couldn't open that folder");
    const root = res.root;
    setRoots((rs) => [...rs.filter((r) => r.id !== root.id), root]);
    setNote(res.already
      ? `AURA already reads ${root.label}. Checking it for changes.`
      : `AURA is reading ${root.label}. Ask about anything in it once the count settles.`);
    setText("");
    setAsk(null);
    loadRoots();
    return true;
  };

  const pickFolders = () => {
    const pick = window.aura?.pickFolders;
    if (!pick) {
      setNote("Paste the folder's path in the box, like C:\\Users\\you\\Documents.");
      return;
    }
    void attempt(async () => {
      for (const p of await pick()) await addFolder(p);
    });
  };

  const addApp = async (target: string) => {
    const res = await api.addDomainItem("app", "", target);
    if (!res.ok || !res.item) throw new Error(res.error || "couldn't add that app");
    done(res.item, `Added. Say "open ${res.item.title}" any time.`);
  };

  const addSkill = async () => {
    const res = await api.addDomainItem("skill", skillName, skillBody);
    if (!res.ok || !res.item) throw new Error(res.error || "couldn't save that skill");
    setSkillName("");
    setSkillBody("");
    done(res.item, `Skill saved. Say "run ${res.item.title}" and AURA follows it.`);
  };

  const attempt = async (fn: () => Promise<void>) => {
    setNote("");
    try { await fn(); } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
  };

  // One box: a repo link or a folder path gives AURA read access, any other
  // link saves, another path adds an app, anything else asks what it is.
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = text.trim().replace(/^"(.*)"$/, "$1");
    if (!raw) return;
    if (REPO_RE.test(raw)) void attempt(async () => { await addFolder(raw); });
    else if (URL_RE.test(raw)) void attempt(() => addLink(raw));
    else if (PATH_RE.test(raw)) void attempt(async () => { if (!(await addFolder(raw))) await addApp(raw); });
    else setAsk("choose");
  };

  // ✕ on a folder only stops AURA reading it; the files stay where they are.
  const dropRoot = async (r: LibraryRoot) => {
    const key = -r.id;          // negative ids keep folder confirms apart from items
    if (confirming !== key) {
      setConfirming(key);
      setTimeout(() => setConfirming((id) => (id === key ? null : id)), 3000);
      return;
    }
    const res = await api.removeLibrary(r.id);
    if (res.ok) setRoots((rs) => rs.filter((x) => x.id !== r.id));
  };

  const addFiles = (files: FileList | null) => {
    if (!files?.length) return;
    void attempt(async () => {
      for (const f of Array.from(files).slice(0, 8)) {
        const it = await uploadToSaved(f, "domain");
        done(it, "Saved — AURA is reading it now.");
      }
    });
  };

  const run = async (it: SavedItem) => {
    setRunning(it.id);
    setNote("");
    try {
      const r = await api.runDomainItem(it.id);
      if (r.chat) send(r.chat);
      else if (r.reply) setNote(r.reply);
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setTimeout(() => setRunning((id) => (id === it.id ? null : id)), 900);
    }
  };

  // ✕ asks first: removing also deletes a dropped file's stored copy.
  const del = async (it: SavedItem) => {
    if (confirming !== it.id) {
      setConfirming(it.id);
      setTimeout(() => setConfirming((id) => (id === it.id ? null : id)), 3000);
      return;
    }
    const res = await api.deleteSaved(it.id);
    if (res.ok) remove(it.id);
  };

  return (
    <div
      className={"domain" + (dragging ? " domain--drop" : "")}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
      onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
    >
      <div className="domain__grid">
        <section className="dlib">
          <header className="dlib__top">
            <button className="dlib__back" onClick={onExit} title="Back to Sanctuary">← Sanctuary</button>
            <span className="winctl">
              <button className="winctl__btn" title="Minimize" onClick={() => window.aura?.minimize?.()}>—</button>
              <button className="winctl__btn winctl__btn--close" title="Close" onClick={() => window.aura?.close?.()}>✕</button>
            </span>
          </header>

          <DomainBoundary resetKey="library">
            <div className="dlib__body">
              <h1 className="dlib__title">Domain</h1>
              <p className="dlib__lede">
                Give AURA a folder, a repo, a link, a file, a skill or an app. She reads it, uses it
                when your conversation touches it, and runs it when you ask — here or by saying <em>“open …”</em>.
              </p>

              <form className="dlib__add" onSubmit={submit}>
                <input
                  value={text}
                  onChange={(e) => { setText(e.target.value); setAsk(null); }}
                  placeholder="Paste a link, a repo, a folder or an app path…"
                  aria-label="Link, repo, folder or app path"
                />
                <button type="submit" className="dlib__btn dlib__btn--main" disabled={!text.trim()}>Add</button>
                <button type="button" className="dlib__btn" onClick={pickFolders}>Folder</button>
                <button type="button" className="dlib__btn" onClick={() => fileRef.current?.click()}>File</button>
                <button type="button" className="dlib__btn" onClick={() => setAsk(ask === "skill" ? null : "skill")}>Skill</button>
                <input
                  ref={fileRef} type="file" multiple hidden
                  onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
                />
              </form>

              {ask === "choose" && (
                <div className="dlib__choose">
                  <span>What is “{text.trim()}”?</span>
                  <button className="dlib__btn" onClick={() => void attempt(() => addApp(text.trim()))}>An app on this PC</button>
                  <button className="dlib__btn" onClick={() => { setSkillBody(text.trim()); setText(""); setAsk("skill"); }}>A skill</button>
                </div>
              )}

              {ask === "skill" && (
                <form className="dlib__skill" onSubmit={(e) => { e.preventDefault(); void attempt(addSkill); }}>
                  <input
                    value={skillName}
                    onChange={(e) => setSkillName(e.target.value)}
                    placeholder="Name — e.g. Morning brief"
                    aria-label="Skill name"
                  />
                  <textarea
                    value={skillBody}
                    onChange={(e) => setSkillBody(e.target.value)}
                    placeholder="What should AURA do when you run it? Write it like you'd tell a person."
                    rows={4}
                    aria-label="Skill instructions"
                  />
                  <div className="dlib__skillbtns">
                    <button type="button" className="dlib__btn" onClick={() => setAsk(null)}>Cancel</button>
                    <button type="submit" className="dlib__btn dlib__btn--main" disabled={!skillBody.trim()}>Save skill</button>
                  </div>
                </form>
              )}

              {note && <p className="dlib__note" role="status">{note}</p>}

              {items.length + roots.length > 0 && (
                <nav className="dlib__tabs">
                  {GROUPS.filter((g) => g.id === "all" || counts[g.id] > 0).map((g) => (
                    <button
                      key={g.id}
                      className={"dlib__tab" + (group === g.id ? " dlib__tab--on" : "")}
                      onClick={() => setGroup(g.id)}
                    >
                      {g.label} <span>{counts[g.id]}</span>
                    </button>
                  ))}
                </nav>
              )}

              {items.length + roots.length === 0 ? (
                <div className="dlib__empty">
                  <p>Nothing here yet.</p>
                  <p>Start with a folder you work from, like your college notes or a project repo:
                    press <strong>Folder</strong>, or paste its path or GitHub link. Then ask AURA about
                    anything in it. Websites, PDFs, skills and apps go in the same box, and you can drop
                    files anywhere on this page.</p>
                </div>
              ) : (
                <ul className="dlib__grid">
                  {(group === "all" || group === "folder") && roots.map((r) => {
                    const reading = r.indexing || r.status === "indexing" || r.status === "idle";
                    return (
                      <li key={"root" + r.id} className="dcard dcard--folder">
                        <div className="dcard__head">
                          <span className="dcard__glyph" aria-hidden>{GLYPH.folder}</span>
                          <div className="dcard__name">
                            <strong title={r.path}>{r.label}</strong>
                            <span title={r.path}>{r.kind === "repo" ? "Repo" : "Folder"} · {r.path}</span>
                          </div>
                        </div>
                        <p className={"dcard__sum" + (reading ? " dcard__sum--live" : "")}>
                          {reading ? (r.detail || "Reading files…")
                            : r.status === "error" ? r.detail
                            : `${r.files} file${r.files === 1 ? "" : "s"} she can read: ${r.detail}`}
                        </p>
                        <div className="dcard__btns">
                          <button className="dlib__btn dlib__btn--main"
                                  onClick={() => void api.openLibrary(r.id).then((x) => { if (!x.ok) setNote(x.error ?? ""); })}>
                            Open
                          </button>
                          <button className="dlib__btn" disabled={status !== "open" || reading}
                                  onClick={() => send(`What's in my ${r.label} ${r.kind === "repo" ? "repo" : "folder"}? Give me the lay of the land.`)}>
                            Ask
                          </button>
                          <button
                            className={"dlib__btn dlib__btn--quiet" + (confirming === -r.id ? " dlib__btn--warn" : "")}
                            onClick={() => void dropRoot(r)}
                            title="Stop AURA reading this folder (your files stay put)"
                          >
                            {confirming === -r.id ? "Remove?" : "✕"}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                  {group !== "folder" && shown.map((it) => {
                    const g = (GROUP_OF[it.kind] ?? "file") as Exclude<Group, "all" | "folder">;
                    return (
                      <li key={it.id} className={"dcard dcard--" + g}>
                        <div className="dcard__head">
                          <span className="dcard__glyph" aria-hidden>{GLYPH[g]}</span>
                          <div className="dcard__name">
                            <strong title={it.title}>{it.title}</strong>
                            <span>{sub(it)}</span>
                          </div>
                        </div>
                        <p className="dcard__sum">
                          {it.status === "scanning" ? "Reading…" : it.status === "error" ? it.error : it.summary}
                        </p>
                        <div className="dcard__btns">
                          <button
                            className="dlib__btn dlib__btn--main"
                            onClick={() => void run(it)}
                            disabled={running === it.id}
                          >
                            {running === it.id ? "…" : RUN_LABEL[g]}
                          </button>
                          {g !== "app" && (
                            <button
                              className="dlib__btn"
                              disabled={status !== "open"}
                              onClick={() => send(g === "skill"
                                ? `What does my skill "${it.title}" do?`
                                : `What's in "${it.title}" that I saved?`)}
                            >
                              Ask
                            </button>
                          )}
                          <button
                            className={"dlib__btn dlib__btn--quiet" + (confirming === it.id ? " dlib__btn--warn" : "")}
                            onClick={() => void del(it)}
                            title="Remove"
                          >
                            {confirming === it.id ? "Remove?" : "✕"}
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </DomainBoundary>
        </section>

        <DomainChat status={status} turns={turns} send={send} />
      </div>
      {dragging && <div className="domain__dropveil">Drop to give it to AURA</div>}
    </div>
  );
}
