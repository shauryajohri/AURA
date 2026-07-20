import { useMemo, useRef, useState } from "react";
import { CodeFile, useActiveProject, useDomainStore } from "../../../stores/domainStore";

// ============================================================================
// Code surface — file rail + editor. Zero-dependency highlighting: a <pre>
// painted behind a transparent <textarea>, scroll-synced. Enough to feel like
// an editor without dragging Monaco into the bundle (yet).
// ============================================================================

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const KEYWORDS: Record<string, string[]> = {
  ts: ["import","export","from","const","let","var","function","return","if","else","for","while","class","interface","type","extends","implements","new","async","await","try","catch","throw","default","switch","case","break","continue","in","of","typeof","keyof","readonly","public","private","null","undefined","true","false","this"],
  js: ["import","export","from","const","let","var","function","return","if","else","for","while","class","extends","new","async","await","try","catch","throw","default","switch","case","break","continue","in","of","typeof","null","undefined","true","false","this"],
  py: ["import","from","def","return","if","elif","else","for","while","class","try","except","raise","with","as","pass","break","continue","lambda","yield","global","not","and","or","in","is","None","True","False","self","async","await"],
  css: [], json: [], txt: [],
};

function highlight(code: string, lang: CodeFile["lang"]): string {
  let html = esc(code);
  // strings
  html = html.replace(/(&quot;|"|'|`)((?:\\.|(?!\1).)*?)\1/g, '<i class="tk-str">$1$2$1</i>');
  // comments
  if (lang === "py") html = html.replace(/(#[^\n]*)/g, '<i class="tk-com">$1</i>');
  else if (lang === "ts" || lang === "js" || lang === "css")
    html = html.replace(/(\/\/[^\n]*|\/\*[\s\S]*?\*\/)/g, '<i class="tk-com">$1</i>');
  // numbers
  html = html.replace(/\b(\d+(?:\.\d+)?)\b/g, '<i class="tk-num">$1</i>');
  // keywords
  const kws = KEYWORDS[lang] ?? [];
  if (kws.length) {
    const re = new RegExp(`\\b(${kws.join("|")})\\b`, "g");
    html = html.replace(re, '<i class="tk-kw">$1</i>');
  }
  return html + "\n";
}

export default function CodePane() {
  const project = useActiveProject();
  const addFile = useDomainStore((s) => s.addFile);
  const updateFile = useDomainStore((s) => s.updateFile);

  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const preRef = useRef<HTMLPreElement>(null);

  const file = project?.files.find((f) => f.id === openId) ?? project?.files[0] ?? null;

  const html = useMemo(
    () => (file ? highlight(file.content, file.lang) : ""),
    [file?.content, file?.lang] // eslint-disable-line react-hooks/exhaustive-deps
  );

  if (!project)
    return <div className="dph"><h3>No project open</h3><p>Create one from the Dashboard.</p></div>;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) addFile(name.trim());
    setName("");
    setAdding(false);
  };

  return (
    <div className="dcode">
      <div className="dcode__rail">
        <div className="dcode__railhead">
          <span>FILES</span>
          <button onClick={() => setAdding(true)} title="New file">✚</button>
        </div>
        {adding && (
          <form onSubmit={submit} className="dcode__newfile">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="name.ts"
              onBlur={() => setAdding(false)}
              onKeyDown={(e) => e.key === "Escape" && setAdding(false)}
            />
          </form>
        )}
        {project.files.map((f) => (
          <button
            key={f.id}
            className={"dcode__file" + (file?.id === f.id ? " dcode__file--on" : "")}
            onClick={() => setOpenId(f.id)}
          >
            <span className={"dcode__lang dcode__lang--" + f.lang}>{f.lang}</span>
            {f.name}
          </button>
        ))}
        {project.files.length === 0 && <div className="dcode__empty">No files yet.</div>}
      </div>

      {file ? (
        <div className="dcode__editor">
          <div className="dcode__tab">
            {file.name}
            <span className="dcode__saved">saved</span>
          </div>
          <div className="dcode__surface">
            <pre ref={preRef} aria-hidden="true" dangerouslySetInnerHTML={{ __html: html }} />
            <textarea
              value={file.content}
              spellCheck={false}
              onChange={(e) => updateFile(file.id, e.target.value)}
              onScroll={(e) => {
                if (preRef.current) {
                  preRef.current.scrollTop = e.currentTarget.scrollTop;
                  preRef.current.scrollLeft = e.currentTarget.scrollLeft;
                }
              }}
            />
          </div>
        </div>
      ) : (
        <div className="dph"><h3>No file open</h3><p>Create one in the rail.</p></div>
      )}
    </div>
  );
}
