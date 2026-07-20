import { useMemo, useState } from "react";
import { useActiveProject, useDomainStore } from "../../../stores/domainStore";

// ============================================================================
// Notes / Documents — split markdown editor with live preview.
// Tiny hand-rolled renderer (headings, bold, italic, code, quotes, lists,
// links, rules). No dependency, no surprises.
// ============================================================================

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function inline(md: string): string {
  return esc(md)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

function renderMd(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let list: "ul" | "ol" | null = null;
  let inCode = false;

  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };

  for (const raw of lines) {
    if (raw.trim().startsWith("```")) {
      closeList();
      out.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(esc(raw)); continue; }

    const h = raw.match(/^(#{1,4})\s+(.*)/);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(raw)) { closeList(); out.push("<hr/>"); continue; }
    const q = raw.match(/^>\s?(.*)/);
    if (q) { closeList(); out.push(`<blockquote>${inline(q[1])}</blockquote>`); continue; }
    const ul = raw.match(/^\s*[-*]\s+(.*)/);
    if (ul) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push(`<li>${inline(ul[1])}</li>`);
      continue;
    }
    const ol = raw.match(/^\s*\d+\.\s+(.*)/);
    if (ol) {
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push(`<li>${inline(ol[1])}</li>`);
      continue;
    }
    closeList();
    if (raw.trim() === "") continue;
    out.push(`<p>${inline(raw)}</p>`);
  }
  closeList();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

export default function MarkdownPane() {
  const project = useActiveProject();
  const addDoc = useDomainStore((s) => s.addDoc);
  const updateDoc = useDomainStore((s) => s.updateDoc);

  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  const doc = project?.docs.find((d) => d.id === openId) ?? project?.docs[0] ?? null;
  const html = useMemo(() => (doc ? renderMd(doc.content) : ""), [doc?.content]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) addDoc(name.trim());
    setName("");
    setAdding(false);
  };

  return (
    <div className="dmd">
      <div className="dcode__rail">
        <div className="dcode__railhead">
          <span>DOCS</span>
          <button onClick={() => setAdding(true)} title="New doc">✚</button>
        </div>
        {adding && (
          <form onSubmit={submit} className="dcode__newfile">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Doc name"
              onBlur={() => setAdding(false)}
              onKeyDown={(e) => e.key === "Escape" && setAdding(false)}
            />
          </form>
        )}
        {project.docs.map((d) => (
          <button
            key={d.id}
            className={"dcode__file" + (doc?.id === d.id ? " dcode__file--on" : "")}
            onClick={() => setOpenId(d.id)}
          >
            <span className="dcode__lang dcode__lang--md">md</span>
            {d.name}
          </button>
        ))}
        {project.docs.length === 0 && <div className="dcode__empty">No docs yet.</div>}
      </div>

      {doc ? (
        <div className="dmd__split">
          <textarea
            className="dmd__editor"
            value={doc.content}
            spellCheck={false}
            onChange={(e) => updateDoc(doc.id, e.target.value)}
          />
          <div className="dmd__preview" dangerouslySetInnerHTML={{ __html: html }} />
        </div>
      ) : (
        <div className="dph"><h3>No doc open</h3><p>Create one in the rail.</p></div>
      )}
    </div>
  );
}
