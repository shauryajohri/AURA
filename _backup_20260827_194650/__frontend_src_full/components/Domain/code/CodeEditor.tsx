import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { highlight } from "./highlight";

// ============================================================================
// The editor surface.
//
// The whole thing lives in ONE scroll container: gutter, highlight layer and
// textarea scroll together as a single unit, so nothing can drift out of
// alignment — no scroll-sync listeners, no jitter on fast scrolling. The
// highlighted <pre> sizes the box; the transparent <textarea> is stretched
// over it and owns the caret and selection.
//
// Editing niceties: Tab/Shift+Tab indent (selection-aware), auto-indent on
// Enter, bracket and quote auto-close, wrap-selection, and Ctrl+/ comment.
// ============================================================================

const LINE_H = 20;

interface Props {
  value: string;
  lang: string;
  onChange: (next: string) => void;
  onSave: () => void;
  onCursor?: (pos: { line: number; col: number; sel: number }) => void;
  wrap?: boolean;
}

const COMMENT: Record<string, string> = {
  ts: "//", js: "//", c: "//", cpp: "//", java: "//", go: "//", rust: "//",
  css: "//", json: "//", sql: "--", py: "#", sh: "#", yaml: "#", toml: "#", md: "",
};

const PAIRS: Record<string, string> = {
  "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`",
};

export default function CodeEditor({ value, lang, onChange, onSave, onCursor, wrap }: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const [caretLine, setCaretLine] = useState(0);

  const lines = useMemo(() => value.split("\n"), [value]);
  const html = useMemo(() => highlight(value, lang), [value, lang]);

  // ---- caret reporting ----------------------------------------------------
  const report = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    const upto = ta.value.slice(0, ta.selectionStart);
    const line = upto.split("\n").length;
    const col = upto.length - upto.lastIndexOf("\n");
    setCaretLine(line - 1);
    onCursor?.({ line, col, sel: ta.selectionEnd - ta.selectionStart });
  }, [onCursor]);

  useEffect(() => { report(); }, [value, report]);

  // Keep the textarea exactly the size of the highlighted text, so the single
  // outer scroller covers both and long lines scroll horizontally as one.
  useLayoutEffect(() => {
    const ta = taRef.current;
    const pre = preRef.current;
    if (!ta || !pre) return;
    ta.style.height = pre.scrollHeight + "px";
    ta.style.width = wrap ? "100%" : pre.scrollWidth + "px";
  }, [html, wrap]);

  // ---- editing behaviours -------------------------------------------------
  const apply = (next: string, selStart: number, selEnd = selStart) => {
    onChange(next);
    requestAnimationFrame(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.selectionStart = selStart;
      ta.selectionEnd = selEnd;
      report();
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const ta = e.currentTarget;
    const { selectionStart: s, selectionEnd: en, value: v } = ta;
    const mod = e.ctrlKey || e.metaKey;

    if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); onSave(); return; }

    // Ctrl+/ — toggle line comments across the selection
    if (mod && e.key === "/") {
      e.preventDefault();
      const token = COMMENT[lang] ?? "//";
      if (!token) return;
      const startLine = v.lastIndexOf("\n", s - 1) + 1;
      const endLine = v.indexOf("\n", en) === -1 ? v.length : v.indexOf("\n", en);
      const block = v.slice(startLine, endLine);
      const rows = block.split("\n");
      const allOn = rows.every((r) => !r.trim() || r.trimStart().startsWith(token));
      const next = rows
        .map((r) => {
          if (!r.trim()) return r;
          if (allOn) return r.replace(new RegExp(`(\\s*)${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} ?`), "$1");
          const indent = r.match(/^\s*/)?.[0] ?? "";
          return indent + token + " " + r.slice(indent.length);
        })
        .join("\n");
      apply(v.slice(0, startLine) + next + v.slice(endLine), startLine, startLine + next.length);
      return;
    }

    // Tab / Shift+Tab — indent, selection-aware
    if (e.key === "Tab") {
      e.preventDefault();
      const multi = v.slice(s, en).includes("\n");
      if (!multi && !e.shiftKey) {
        apply(v.slice(0, s) + "  " + v.slice(en), s + 2);
        return;
      }
      const startLine = v.lastIndexOf("\n", s - 1) + 1;
      const endLine = v.indexOf("\n", en) === -1 ? v.length : v.indexOf("\n", en);
      const rows = v.slice(startLine, endLine).split("\n");
      const next = rows
        .map((r) => (e.shiftKey ? r.replace(/^ {1,2}/, "") : "  " + r))
        .join("\n");
      apply(v.slice(0, startLine) + next + v.slice(endLine), startLine, startLine + next.length);
      return;
    }

    // Enter — keep the current indent, and open a block for a trailing brace
    if (e.key === "Enter") {
      const lineStart = v.lastIndexOf("\n", s - 1) + 1;
      const indent = (v.slice(lineStart, s).match(/^\s*/) ?? [""])[0];
      const before = v[s - 1];
      const after = v[s];
      const opensBlock = /[{[(:]/.test(before ?? "");
      const extra = opensBlock ? "  " : "";
      e.preventDefault();
      if (opensBlock && after && PAIRS[before!] === after) {
        // caret between a pair — put the closer on its own line
        const ins = "\n" + indent + extra + "\n" + indent;
        apply(v.slice(0, s) + ins + v.slice(en), s + 1 + indent.length + extra.length);
      } else {
        const ins = "\n" + indent + extra;
        apply(v.slice(0, s) + ins + v.slice(en), s + ins.length);
      }
      return;
    }

    // Auto-close, or wrap the selection
    if (PAIRS[e.key]) {
      const close = PAIRS[e.key];
      if (s !== en) {
        e.preventDefault();
        const sel = v.slice(s, en);
        apply(v.slice(0, s) + e.key + sel + close + v.slice(en), s + 1, en + 1);
        return;
      }
      const next = v[s];
      const isQuote = e.key === close;
      if (!isQuote || !next || /[\s)\]},;]/.test(next)) {
        e.preventDefault();
        apply(v.slice(0, s) + e.key + close + v.slice(en), s + 1);
        return;
      }
    }

    // Typing the closer when it's already there — step over it
    if ([")", "]", "}", '"', "'", "`"].includes(e.key) && v[s] === e.key && s === en) {
      e.preventDefault();
      apply(v, s + 1);
      return;
    }

    // Backspace between an empty pair — delete both
    if (e.key === "Backspace" && s === en && s > 0) {
      const before = v[s - 1];
      if (PAIRS[before] && v[s] === PAIRS[before]) {
        e.preventDefault();
        apply(v.slice(0, s - 1) + v.slice(s + 1), s - 1);
        return;
      }
    }
  };

  return (
    <div className="vsc-ed">
      <div className="vsc-ed__scroll">
        <div className="vsc-ed__inner">
          <div className="vsc-ed__gutter" aria-hidden="true">
            {lines.map((_, i) => (
              <div
                key={i}
                className={"vsc-ed__ln" + (i === caretLine ? " vsc-ed__ln--on" : "")}
              >
                {i + 1}
              </div>
            ))}
          </div>

          <div className={"vsc-ed__code" + (wrap ? " vsc-ed__code--wrap" : "")}>
            <div
              className="vsc-ed__activeline"
              style={{ transform: `translateY(${caretLine * LINE_H}px)` }}
            />
            <pre ref={preRef} aria-hidden="true" dangerouslySetInnerHTML={{ __html: html }} />
            <textarea
              ref={taRef}
              value={value}
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              wrap={wrap ? "soft" : "off"}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={onKeyDown}
              onKeyUp={report}
              onClick={report}
              onSelect={report}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
