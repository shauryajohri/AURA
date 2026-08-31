import { useCallback, useEffect, useState } from "react";
import {
  domainApi,
  type Connector,
  type ConnectorDoc,
  type FigmaFile,
  type OfficeDocument,
} from "../../../domainApi";
import { useDomainStore } from "../../../stores/domainStore";

// ============================================================================
// Apps — Figma, Word, PowerPoint and Excel, connected to AURA.
//
// Pick an app, see its real files with when they last changed, open one and
// edit it here: the file is pulled from OneDrive, parsed in its native format,
// and written back on save — so a change made in PowerPoint shows up here, and
// a change made here shows up in PowerPoint.
//
// Figma is read-only (its API has no write surface), so it shows pages, frames
// and thumbnails with a link out.
// ============================================================================

const APPS = [
  { id: "word", label: "Word", provider: "microsoft", icon: "W", color: "#2b7cd3", blurb: "Documents" },
  { id: "powerpoint", label: "PowerPoint", provider: "microsoft", icon: "P", color: "#d24726", blurb: "Decks" },
  { id: "excel", label: "Excel", provider: "microsoft", icon: "X", color: "#21a366", blurb: "Spreadsheets" },
  { id: "figma", label: "Figma", provider: "figma", icon: "◆", color: "#f24e1e", blurb: "Designs" },
] as const;

type AppId = (typeof APPS)[number]["id"];

const ago = (iso?: string) => {
  if (!iso) return "";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  if (d < 2592000) return `${Math.floor(d / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
};

// ---------------------------------------------------------------- editors
function WordEditor({
  doc, edits, setEdits,
}: {
  doc: OfficeDocument;
  edits: Record<string, string>;
  setEdits: (e: Record<string, string>) => void;
}) {
  const paras = doc.content.paragraphs ?? [];
  return (
    <div className="dapp__word">
      {paras.map((p) => (
        <div key={p.i} className={"dapp__para dapp__para--" + p.style.toLowerCase().replace(/\s+/g, "")}>
          <textarea
            value={edits[String(p.i)] ?? p.text}
            placeholder={p.style === "Normal" ? "" : p.style}
            rows={1}
            onChange={(e) => setEdits({ ...edits, [String(p.i)]: e.target.value })}
            onInput={(e) => {
              const ta = e.currentTarget;
              ta.style.height = "auto";
              ta.style.height = ta.scrollHeight + "px";
            }}
            ref={(el) => {
              if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
            }}
          />
        </div>
      ))}
      {paras.length === 0 && <div className="dapp__empty">This document has no text paragraphs.</div>}
    </div>
  );
}

function ExcelEditor({
  doc, edits, setEdits,
}: {
  doc: OfficeDocument;
  edits: Record<string, Record<string, string>>;
  setEdits: (e: Record<string, Record<string, string>>) => void;
}) {
  const sheets = doc.content.sheets ?? [];
  const [active, setActive] = useState(0);
  const sheet = sheets[active];
  if (!sheet) return <div className="dapp__empty">No sheets.</div>;

  const set = (r: number, c: number, v: string) =>
    setEdits({
      ...edits,
      [sheet.name]: { ...(edits[sheet.name] ?? {}), [`${r},${c}`]: v },
    });

  return (
    <div className="dapp__excel">
      {sheets.length > 1 && (
        <div className="dapp__sheets">
          {sheets.map((s, i) => (
            <button key={s.name} className={i === active ? "on" : ""} onClick={() => setActive(i)}>
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="dapp__gridwrap">
        <table className="dapp__grid">
          <tbody>
            {sheet.rows.map((row, r) => (
              <tr key={r}>
                <th>{r + 1}</th>
                {row.map((cell, c) => (
                  <td key={c}>
                    <input
                      value={edits[sheet.name]?.[`${r},${c}`] ?? cell}
                      onChange={(e) => set(r, c, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sheet.truncated && (
        <div className="dapp__note">Showing the first 200 rows × 40 columns.</div>
      )}
    </div>
  );
}

function PowerPointEditor({
  doc, edits, setEdits,
}: {
  doc: OfficeDocument;
  edits: Record<string, Record<string, string>>;
  setEdits: (e: Record<string, Record<string, string>>) => void;
}) {
  const slides = doc.content.slides ?? [];
  const [active, setActive] = useState(0);
  const slide = slides[active];

  const set = (shapeIdx: number, v: string) =>
    setEdits({
      ...edits,
      [String(active)]: { ...(edits[String(active)] ?? {}), [String(shapeIdx)]: v },
    });

  return (
    <div className="dapp__ppt">
      <div className="dapp__slides">
        {slides.map((s, i) => (
          <button
            key={s.i}
            className={"dapp__slidebtn" + (i === active ? " on" : "")}
            onClick={() => setActive(i)}
          >
            <span className="dapp__slidenum">{i + 1}</span>
            <span className="dapp__slidetitle">{s.title}</span>
          </button>
        ))}
      </div>

      <div className="dapp__canvas">
        {slide ? (
          slide.shapes.length ? (
            slide.shapes.map((sh) => (
              <div key={sh.i} className="dapp__shape">
                <label>{sh.name}</label>
                <textarea
                  value={edits[String(active)]?.[String(sh.i)] ?? sh.text}
                  onChange={(e) => set(sh.i, e.target.value)}
                />
              </div>
            ))
          ) : (
            <div className="dapp__empty">This slide has no editable text.</div>
          )
        ) : (
          <div className="dapp__empty">No slides.</div>
        )}
      </div>
    </div>
  );
}

function FigmaViewer({ file }: { file: FigmaFile }) {
  return (
    <div className="dapp__figma">
      <div className="dapp__note">
        Figma's API is read-only — edits happen in Figma, and land here on refresh.
      </div>
      {file.pages.map((page) => (
        <div key={page.id} className="dapp__fpage">
          <div className="ddash__section">{page.name}</div>
          <div className="dapp__frames">
            {page.frames.map((f) => (
              <a
                key={f.id}
                className="dapp__frame"
                href={`${file.url}?node-id=${encodeURIComponent(f.id)}`}
                target="_blank"
                rel="noreferrer"
              >
                {file.thumbnails[f.id] ? (
                  <img src={file.thumbnails[f.id]} alt={f.name} loading="lazy" />
                ) : (
                  <div className="dapp__noimg">{f.type}</div>
                )}
                <span>{f.name}</span>
              </a>
            ))}
            {page.frames.length === 0 && <div className="dapp__empty">Nothing on this page.</div>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------- shell
export default function AppsTab() {
  const log = useDomainStore((s) => s.log);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [app, setApp] = useState<AppId>("word");
  const [files, setFiles] = useState<ConnectorDoc[]>([]);
  const [query, setQuery] = useState("");
  const [listing, setListing] = useState(false);
  const [err, setErr] = useState("");

  const [doc, setDoc] = useState<OfficeDocument | null>(null);
  const [figma, setFigma] = useState<FigmaFile | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState("");

  // edit buffers, shaped per format
  const [wordEdits, setWordEdits] = useState<Record<string, string>>({});
  const [cellEdits, setCellEdits] = useState<Record<string, Record<string, string>>>({});
  const [slideEdits, setSlideEdits] = useState<Record<string, Record<string, string>>>({});

  const meta = APPS.find((a) => a.id === app)!;
  const connector = connectors.find((c) => c.id === meta.provider);
  const dirty =
    Object.keys(wordEdits).length > 0 ||
    Object.keys(cellEdits).length > 0 ||
    Object.keys(slideEdits).length > 0;

  const loadConnectors = useCallback(
    () => domainApi.connectors().then((r) => setConnectors(r.connectors)).catch(() => setErr("bridge offline")),
    []
  );
  useEffect(() => { loadConnectors(); }, [loadConnectors]);

  const clearBuffers = () => { setWordEdits({}); setCellEdits({}); setSlideEdits({}); };

  const listFiles = useCallback(async () => {
    if (!connector?.connected) return;
    setListing(true);
    setErr("");
    const r = await domainApi.connectorDocs(
      meta.provider,
      query,
      meta.provider === "microsoft" ? meta.id : undefined
    );
    setListing(false);
    if (!r.ok) { setErr(r.error ?? "could not list files"); setFiles([]); return; }
    setFiles(r.documents ?? []);
  }, [connector?.connected, meta.provider, meta.id, query]);

  // switching app resets the workspace and re-lists
  useEffect(() => {
    setDoc(null); setFigma(null); setFiles([]); clearBuffers(); setErr("");
    listFiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app, connector?.connected]);

  const open = async (f: ConnectorDoc) => {
    setLoadingDoc(true);
    setErr("");
    clearBuffers();
    setDoc(null);
    setFigma(null);
    if (meta.id === "figma") {
      const r = await domainApi.figmaFile(f.id);
      setLoadingDoc(false);
      if (!r.ok || !r.file) { setErr(r.error ?? "could not open"); return; }
      setFigma(r.file);
      return;
    }
    const r = await domainApi.officeOpen(f.id);
    setLoadingDoc(false);
    if (!r.ok || !r.document) { setErr(r.error ?? "could not open"); return; }
    setDoc(r.document);
  };

  const save = async () => {
    if (!doc || !dirty) return;
    setSaving(true);
    const edits =
      doc.kind === "word" ? { paragraphs: wordEdits }
      : doc.kind === "excel" ? { cells: cellEdits }
      : { slides: slideEdits };
    const r = await domainApi.officeSave(doc.id, edits);
    setSaving(false);
    if (!r.ok) { setErr(r.error ?? "save failed"); return; }

    const changed =
      doc.kind === "word" ? Object.keys(wordEdits).length
      : doc.kind === "excel" ? Object.values(cellEdits).reduce((n, s) => n + Object.keys(s).length, 0)
      : Object.values(slideEdits).reduce((n, s) => n + Object.keys(s).length, 0);
    log("office", `Saved ${doc.name} back to ${meta.label}`,
        `${changed} ${doc.kind === "excel" ? "cells" : doc.kind === "word" ? "paragraphs" : "text boxes"} changed`);

    clearBuffers();
    setDoc({ ...doc, modified: r.modified ?? doc.modified });
    setFlash("saved to " + meta.label);
    setTimeout(() => setFlash(""), 2200);
  };

  const refresh = async () => {
    if (!doc) return;
    if (dirty && !confirm("Reload from the cloud and lose your unsaved edits?")) return;
    setLoadingDoc(true);
    clearBuffers();
    const r = await domainApi.officeOpen(doc.id);
    setLoadingDoc(false);
    if (r.ok && r.document) setDoc(r.document);
  };

  return (
    <div className="dapps">
      {/* app switcher */}
      <div className="dapps__bar">
        {APPS.map((a) => {
          const c = connectors.find((x) => x.id === a.provider);
          return (
            <button
              key={a.id}
              className={"dapps__app" + (app === a.id ? " dapps__app--on" : "")}
              style={{ ["--pc" as string]: a.color }}
              onClick={() => setApp(a.id)}
            >
              <span className="dapps__icon">{a.icon}</span>
              <span className="dapps__label">
                {a.label}
                <em>{c?.connected ? a.blurb : c?.configured ? "not connected" : "needs setup"}</em>
              </span>
              {c?.connected && <span className="dapps__live" />}
            </button>
          );
        })}
      </div>

      {!connector?.connected && (
        <div className="dconn__hint">
          {meta.label} runs through {connector?.label ?? meta.provider}.{" "}
          {connector?.configured
            ? "Connect it from Settings → Connectors and its files appear here."
            : "Add its client ID and secret in Settings → Connectors first."}
        </div>
      )}

      <div className="dapps__body">
        {/* file list */}
        <div className="dapps__files">
          <div className="dapps__filehead">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && listFiles()}
              placeholder={`Search ${meta.label}…`}
              disabled={!connector?.connected}
            />
            <button onClick={listFiles} disabled={!connector?.connected || listing} title="Refresh list">
              {listing ? "…" : "↻"}
            </button>
          </div>

          {files.length === 0 && !listing && (
            <div className="dapps__none">
              {connector?.connected ? "No files found." : "Not connected."}
            </div>
          )}

          {files.map((f) => (
            <button
              key={f.id}
              className={"dapps__file" + (doc?.id === f.id || figma?.name === f.name ? " dapps__file--on" : "")}
              style={{ ["--pc" as string]: meta.color }}
              onClick={() => open(f)}
            >
              <span className="dconn__kind">{meta.icon}</span>
              <span className="dapps__fmeta">
                <span className="dapps__fname">{f.name}</span>
                <span className="dapps__fwhen">changed {ago(f.modified)}</span>
              </span>
            </button>
          ))}
        </div>

        {/* editor surface */}
        <div className="dapps__stage">
          {err && <div className="dcode__err">{err} <button onClick={() => setErr("")}>✕</button></div>}

          {loadingDoc && <div className="dapp__empty">opening…</div>}

          {!loadingDoc && !doc && !figma && (
            <div className="dph">
              <h3>{meta.label}</h3>
              <p>
                Pick a file on the left. Changes made in {meta.label} show up here, and
                {meta.id === "figma" ? " you can jump straight to the frame." : " what you edit here saves back."}
              </p>
            </div>
          )}

          {doc && (
            <>
              <div className="dapp__head">
                <div className="dapp__title">
                  <span className="dconn__kind" style={{ ["--pc" as string]: meta.color }}>{meta.icon}</span>
                  <div>
                    <div className="dapp__name">{doc.name}</div>
                    <div className="dapp__sub">
                      changed {ago(doc.modified)}
                      {doc.modified_by ? ` by ${doc.modified_by}` : ""}
                    </div>
                  </div>
                </div>
                <span className="dcode__spacer" />
                {flash && <span className="dcode__flash">{flash}</span>}
                <a className="dapp__out" href={doc.url} target="_blank" rel="noreferrer">open in {meta.label} ↗</a>
                <button className="dapp__refresh" onClick={refresh} title="Pull the latest version">↻</button>
                <button className="dcode__save" onClick={save} disabled={!dirty || saving}>
                  {saving ? "saving…" : dirty ? "Save back" : "saved"}
                </button>
              </div>

              <div className="dapp__surface">
                {doc.kind === "word" && (
                  <WordEditor doc={doc} edits={wordEdits} setEdits={setWordEdits} />
                )}
                {doc.kind === "excel" && (
                  <ExcelEditor doc={doc} edits={cellEdits} setEdits={setCellEdits} />
                )}
                {doc.kind === "powerpoint" && (
                  <PowerPointEditor doc={doc} edits={slideEdits} setEdits={setSlideEdits} />
                )}
              </div>
            </>
          )}

          {figma && (
            <>
              <div className="dapp__head">
                <div className="dapp__title">
                  <span className="dconn__kind" style={{ ["--pc" as string]: meta.color }}>◆</span>
                  <div>
                    <div className="dapp__name">{figma.name}</div>
                    <div className="dapp__sub">changed {ago(figma.modified)}</div>
                  </div>
                </div>
                <span className="dcode__spacer" />
                <a className="dapp__out" href={figma.url} target="_blank" rel="noreferrer">open in Figma ↗</a>
              </div>
              <div className="dapp__surface"><FigmaViewer file={figma} /></div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
