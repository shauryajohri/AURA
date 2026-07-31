import { useState, type ReactNode } from "react";

/**
 * Markdown.tsx — how AURA's words actually reach the screen.
 *
 * Before this, chat rendered `renderMessage()`: fenced code became a real
 * block and EVERYTHING else was dumped as raw text in a `white-space: pre-wrap`
 * div. So when AURA answered "find me some portfolio sites" with a markdown
 * table, shaurya got a wall of pipes and dashes, and the links inside it were
 * dead text he had to retype by hand.
 *
 * Deliberately hand-rolled — no react-markdown, no remark. The chat renders one
 * bubble at a time from a trusted local model, the subset of markdown a chat
 * reply actually uses is small, and adding a parser + sanitiser + their
 * transitive deps to an Electron bundle for that is a bad trade. Nothing here
 * ever builds HTML from a string: every node is a React element, so there is no
 * innerHTML path to inject through.
 *
 * Supported: fenced code, tables, headings, blockquotes, bullet/numbered lists,
 * horizontal rules, and inline **bold** / *italic* / `code` / [links](url) /
 * bare URLs.
 */

/* ── links ─────────────────────────────────────────────────────────────────
 * A plain <a href> inside Electron NAVIGATES THE APP WINDOW — the whole UI is
 * replaced by the website and the WebSocket to the brain dies with it. Every
 * link therefore goes through the preload bridge to the real browser, and the
 * click handler always preventDefault()s.
 */
export function openUrl(url: string): void {
  const bridge = (window as unknown as {
    aura?: { openExternal?: (u: string) => void };
  }).aura;
  if (bridge?.openExternal) {
    bridge.openExternal(url);
    return;
  }
  // Dev mode in a normal browser (vite serve) — no preload bridge exists.
  window.open(url, "_blank", "noopener,noreferrer");
}

/** Only ever hand http(s) to the opener. */
function safeUrl(raw: string): string | null {
  let url = raw.trim().replace(/[),.;:]+$/, "");
  if (/^www\./i.test(url)) url = "https://" + url;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

/** A clickable link with its own copy button — shaurya asked for both. */
function MdLink({ href, label }: { href: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    navigator.clipboard?.writeText(href).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      },
      () => {},
    );
  };
  return (
    <span className="mdlink">
      <a
        className="mdlink__a"
        href={href}
        title={href}
        onClick={(e) => {
          e.preventDefault();
          openUrl(href);
        }}
      >
        {label}
      </a>
      <button
        className={"mdlink__copy" + (copied ? " is-copied" : "")}
        onClick={copy}
        title={copied ? "Copied" : "Copy link"}
        aria-label="Copy link"
      >
        {copied ? "✓" : "⧉"}
      </button>
    </span>
  );
}

/* ── fenced code ───────────────────────────────────────────────────────── */
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(code).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      },
      () => {},
    );
  };
  return (
    <div className="codeblock">
      <div className="codeblock__bar">
        <span className="codeblock__lang">{lang || "code"}</span>
        <button className="codeblock__copy" onClick={copy} title="Copy code">
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre className="codeblock__pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* ── inline ────────────────────────────────────────────────────────────── */
// One pass, longest-token-first: [label](url) before a bare URL, ** before *.
const INLINE_RE = new RegExp(
  [
    /\[([^\]\n]+)\]\(([^)\s]+)\)/.source,          // 1 label, 2 href
    /(`+)([^`]+?)\3/.source,                        // 3 ticks, 4 code
    /\*\*([^*\n]+)\*\*/.source,                     // 5 bold
    /__([^_\n]+)__/.source,                         // 6 bold
    /(?<![*\w])\*([^*\n]+)\*(?!\*)/.source,         // 7 italic
    /\bhttps?:\/\/[^\s<>()\[\]"']+/.source,         // bare url
    /\bwww\.[^\s<>()\[\]"']+/.source,               // bare www
  ].join("|"),
  "g",
);

export function renderInline(text: string, keyBase = ""): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;

  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const [whole, label, href, , code, bold1, bold2, italic] = m;

    if (label !== undefined && href !== undefined) {
      const safe = safeUrl(href);
      out.push(
        safe
          ? <MdLink key={keyBase + "l" + k++} href={safe} label={label} />
          : label,
      );
    } else if (code !== undefined) {
      out.push(<code key={keyBase + "c" + k++} className="md-code">{code}</code>);
    } else if (bold1 !== undefined || bold2 !== undefined) {
      out.push(<strong key={keyBase + "b" + k++}>{bold1 ?? bold2}</strong>);
    } else if (italic !== undefined) {
      out.push(<em key={keyBase + "i" + k++}>{italic}</em>);
    } else {
      // A bare URL. The label is the URL itself, trimmed of trailing
      // punctuation that belonged to the sentence, not the address.
      const safe = safeUrl(whole);
      if (safe) {
        const shown = whole.replace(/[),.;:]+$/, "");
        out.push(<MdLink key={keyBase + "u" + k++} href={safe} label={shown} />);
        const trailing = whole.slice(shown.length);
        if (trailing) out.push(trailing);
      } else {
        out.push(whole);
      }
    }
    last = m.index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/* ── blocks ────────────────────────────────────────────────────────────── */
const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isTableRule = (l: string) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(l) && l.includes("-");

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

/**
 * A markdown table → a real <table>. This is the specific thing that made
 * AURA's answer unreadable: a five-column comparison of portfolio sites
 * arrived as `| Platform | Why it's a good fit | ... |---|---|` run together
 * with the prose.
 */
function Table({ rows, k }: { rows: string[][]; k: string }) {
  const [head, ...body] = rows;
  return (
    <div className="md-tablewrap" key={k}>
      <table className="md-table">
        <thead>
          <tr>{head.map((c, i) => <th key={i}>{renderInline(c, `${k}h${i}`)}</th>)}</tr>
        </thead>
        <tbody>
          {body.map((r, ri) => (
            <tr key={ri}>
              {head.map((_, ci) => <td key={ci}>{renderInline(r[ci] ?? "", `${k}${ri}-${ci}`)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderBlocks(text: string, keyBase: string): ReactNode[] {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let k = 0;
  const key = () => `${keyBase}b${k++}`;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i++; continue; }

    // Table: a pipe row followed by the |---|---| rule.
    if (isTableRow(line) && i + 1 < lines.length && isTableRule(lines[i + 1])) {
      const rows: string[][] = [splitRow(line)];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push(<Table key={key()} k={keyBase + "t" + i} rows={rows} />);
      continue;
    }

    // Horizontal rule.
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      out.push(<hr className="md-hr" key={key()} />);
      i++;
      continue;
    }

    // Heading.
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      const level = Math.min(h[1].length, 6);
      out.push(
        <div className={"md-h md-h" + level} key={key()}>
          {renderInline(h[2], keyBase + "h" + i)}
        </div>,
      );
      i++;
      continue;
    }

    // Blockquote.
    if (/^\s*>\s?/.test(line)) {
      const buf: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      out.push(
        <blockquote className="md-quote" key={key()}>
          {renderInline(buf.join("\n"), keyBase + "q" + i)}
        </blockquote>,
      );
      continue;
    }

    // Lists. Ordered and unordered are the same shape; only the tag differs.
    const bullet = /^\s*[-*•]\s+(.*)$/;
    const numbered = /^\s*\d+[.)]\s+(.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const re = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && re.test(lines[i])) {
        items.push(re.exec(lines[i])![1]);
        i++;
        // A wrapped continuation line belongs to the item above it.
        while (i < lines.length && lines[i].trim() && !re.test(lines[i]) &&
               !bullet.test(lines[i]) && !numbered.test(lines[i]) &&
               /^\s{2,}\S/.test(lines[i])) {
          items[items.length - 1] += " " + lines[i].trim();
          i++;
        }
      }
      // Written out rather than <Tag> with a union-typed variable: TS refuses
      // `"ol" | "ul"` as a JSX element type.
      const kids = items.map((it, n) => (
        <li key={n}>{renderInline(it, `${keyBase}li${n}`)}</li>
      ));
      out.push(
        ordered
          ? <ol className="md-list" key={key()}>{kids}</ol>
          : <ul className="md-list" key={key()}>{kids}</ul>,
      );
      continue;
    }

    // Paragraph: everything up to the next blank line or block starter.
    const buf: string[] = [];
    while (i < lines.length && lines[i].trim() &&
           !isTableRow(lines[i]) && !/^(#{1,6})\s/.test(lines[i]) &&
           !/^\s*>\s?/.test(lines[i]) && !bullet.test(lines[i]) &&
           !numbered.test(lines[i])) {
      buf.push(lines[i]);
      i++;
    }
    if (buf.length) {
      out.push(
        <p className="md-p" key={key()}>{renderInline(buf.join("\n"), keyBase + "p" + i)}</p>,
      );
    }
  }
  return out;
}

/**
 * Split on fenced code first, then block-parse the prose between fences.
 *
 * Handles an UNTERMINATED fence, which matters while a reply is streaming: the
 * closing ``` hasn't arrived yet, so a naive regex fails to match and the
 * half-written code flashes as flat prose — fence, language tag and source all
 * on one running line.
 */
export function renderMarkdown(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const fence = /```([\w+#-]*)[ \t]*\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;

  while ((m = fence.exec(text)) !== null) {
    if (m.index > last) out.push(...renderBlocks(text.slice(last, m.index), `s${key++}-`));
    out.push(<CodeBlock key={"code" + key++} lang={m[1]} code={m[2].replace(/\n$/, "")} />);
    last = m.index + m[0].length;
  }

  const tail = text.slice(last);
  const open = tail.indexOf("```");
  if (open !== -1) {
    if (open > 0) out.push(...renderBlocks(tail.slice(0, open), `s${key++}-`));
    const rest = tail.slice(open + 3);
    const nl = rest.indexOf("\n");
    const lang = nl === -1 ? rest.trim() : rest.slice(0, nl).trim();
    const body = nl === -1 ? "" : rest.slice(nl + 1);
    out.push(<CodeBlock key={"code" + key++} lang={lang} code={body} />);
  } else if (tail) {
    out.push(...renderBlocks(tail, `s${key++}-`));
  }
  return out;
}

export default renderMarkdown;
