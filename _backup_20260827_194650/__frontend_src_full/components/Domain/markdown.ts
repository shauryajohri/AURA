// Tiny hand-rolled markdown renderer shared by the Domain's document views.
// Headings, bold, italic, inline code, fenced code, quotes, lists, links,
// rules, and task checkboxes. No dependency, no surprises.

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function inline(md: string): string {
  return esc(md)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

export function renderMd(md: string): string {
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

    const task = raw.match(/^\s*[-*]\s+\[([ xX])\]\s+(.*)/);
    if (task) {
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      const done = task[1].toLowerCase() === "x";
      out.push(
        `<li class="md-task${done ? " md-task--done" : ""}">` +
        `<span class="md-box">${done ? "✓" : ""}</span>${inline(task[2])}</li>`
      );
      continue;
    }

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
