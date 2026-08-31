// ============================================================================
// Zero-dependency syntax highlighting.
//
// One tokenizing pass instead of chained .replace() calls — chaining is what
// makes naive highlighters paint keywords inside strings and comments, because
// each pass can't see what an earlier one already claimed. Here strings,
// comments and numbers are consumed first and everything else is matched
// against the language's keyword set.
// ============================================================================

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const KEYWORDS: Record<string, string[]> = {
  ts: ["import","export","from","as","const","let","var","function","return","if","else","for","while","do","class","interface","type","enum","extends","implements","new","async","await","try","catch","finally","throw","default","switch","case","break","continue","in","of","typeof","instanceof","keyof","readonly","public","private","protected","static","get","set","yield","delete","void","null","undefined","true","false","this","super"],
  js: ["import","export","from","as","const","let","var","function","return","if","else","for","while","do","class","extends","new","async","await","try","catch","finally","throw","default","switch","case","break","continue","in","of","typeof","instanceof","yield","delete","void","null","undefined","true","false","this","super"],
  py: ["import","from","as","def","return","if","elif","else","for","while","class","try","except","finally","raise","with","pass","break","continue","lambda","yield","global","nonlocal","assert","del","not","and","or","in","is","None","True","False","self","cls","async","await","match","case"],
  c: ["int","char","float","double","long","short","unsigned","signed","void","struct","union","enum","typedef","return","if","else","for","while","do","switch","case","break","continue","goto","sizeof","const","static","extern","volatile","include","define","ifdef","ifndef","endif","NULL"],
  cpp: ["int","char","float","double","long","short","bool","void","class","struct","union","enum","public","private","protected","virtual","override","return","if","else","for","while","do","switch","case","break","continue","new","delete","template","typename","namespace","using","const","constexpr","static","auto","nullptr","true","false","this","try","catch","throw","include"],
  go: ["package","import","func","return","if","else","for","range","type","struct","interface","map","var","const","go","defer","chan","select","switch","case","default","break","continue","nil","true","false","make","new","len","cap","append"],
  rust: ["fn","let","mut","const","static","struct","enum","impl","trait","use","pub","mod","match","if","else","for","while","loop","return","break","continue","self","Self","where","as","dyn","ref","move","async","await","Some","None","Ok","Err","true","false"],
  java: ["public","private","protected","class","interface","abstract","extends","implements","static","final","synchronized","void","int","long","double","float","boolean","char","String","return","if","else","for","while","do","switch","case","break","continue","new","try","catch","finally","throw","throws","import","package","this","super","null","true","false"],
  css: ["important","media","import","keyframes","supports","from","to","root","hover","focus","active","before","after","not","is","where"],
  sh: ["if","then","elif","else","fi","for","in","do","done","while","until","case","esac","function","export","local","return","echo","cd","source","alias","set","unset"],
  sql: ["select","from","where","insert","into","values","update","set","delete","join","left","right","inner","outer","on","group","by","order","having","limit","offset","create","table","view","index","drop","alter","add","primary","key","foreign","references","not","null","and","or","as","distinct","count","sum","avg","min","max"],
  json: ["true","false","null"],
  yaml: ["true","false","null","yes","no"],
  toml: ["true","false"],
  md: [],
  txt: [],
};

/** How each language marks comments. */
const LINE_COMMENT: Record<string, string> = {
  ts: "//", js: "//", c: "//", cpp: "//", java: "//", go: "//", rust: "//",
  css: "", json: "", sql: "--", py: "#", sh: "#", yaml: "#", toml: "#",
};

const BLOCK = new Set(["ts", "js", "c", "cpp", "java", "go", "rust", "css"]);
const TRIPLE = new Set(["py"]);

export function highlight(code: string, lang: string): string {
  const kw = new Set(KEYWORDS[lang] ?? []);
  const line = LINE_COMMENT[lang] ?? "";
  const block = BLOCK.has(lang);
  const triple = TRIPLE.has(lang);

  let out = "";
  let i = 0;
  const n = code.length;

  const push = (cls: string, text: string) =>
    (out += cls ? `<i class="tk-${cls}">${esc(text)}</i>` : esc(text));

  while (i < n) {
    const ch = code[i];
    const rest = code.slice(i);

    // block comment
    if (block && ch === "/" && code[i + 1] === "*") {
      const end = code.indexOf("*/", i + 2);
      const stop = end === -1 ? n : end + 2;
      push("com", code.slice(i, stop));
      i = stop;
      continue;
    }

    // line comment
    if (line && rest.startsWith(line)) {
      const end = code.indexOf("\n", i);
      const stop = end === -1 ? n : end;
      push("com", code.slice(i, stop));
      i = stop;
      continue;
    }

    // python docstrings
    if (triple && (rest.startsWith('"""') || rest.startsWith("'''"))) {
      const q = rest.slice(0, 3);
      const end = code.indexOf(q, i + 3);
      const stop = end === -1 ? n : end + 3;
      push("str", code.slice(i, stop));
      i = stop;
      continue;
    }

    // strings (single line, escape-aware)
    if (ch === '"' || ch === "'" || ch === "`") {
      let j = i + 1;
      while (j < n) {
        if (code[j] === "\\") { j += 2; continue; }
        if (code[j] === ch) { j++; break; }
        if (code[j] === "\n" && ch !== "`") break;
        j++;
      }
      push("str", code.slice(i, j));
      i = j;
      continue;
    }

    // numbers
    if (/[0-9]/.test(ch) && !/[\w$]/.test(code[i - 1] ?? "")) {
      const m = /^(?:0[xXbBoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(rest);
      if (m) { push("num", m[0]); i += m[0].length; continue; }
    }

    // words: keyword, function call, or plain identifier
    if (/[A-Za-z_$@#]/.test(ch)) {
      const m = /^[A-Za-z_$@#][\w$-]*/.exec(rest)!;
      const word = m[0];
      const after = code.slice(i + word.length);
      if (kw.has(word)) push("kw", word);
      else if (/^\s*\(/.test(after) && lang !== "css") push("fn", word);
      else if (/^[A-Z]/.test(word) && lang !== "css") push("type", word);
      else push("", word);
      i += word.length;
      continue;
    }

    // css / markdown flourishes
    if (lang === "css" && ch === "#") {
      const m = /^#[0-9a-fA-F]{3,8}\b/.exec(rest);
      if (m) { push("num", m[0]); i += m[0].length; continue; }
    }
    if (lang === "md") {
      if (ch === "#" && (i === 0 || code[i - 1] === "\n")) {
        const end = code.indexOf("\n", i);
        const stop = end === -1 ? n : end;
        push("kw", code.slice(i, stop));
        i = stop;
        continue;
      }
    }

    if (/[{}()[\];,.:]/.test(ch)) { push("punc", ch); i++; continue; }
    if (/[+\-*/%=<>!&|^~?]/.test(ch)) { push("op", ch); i++; continue; }

    push("", ch);
    i++;
  }

  // trailing newline keeps the last line's height in the <pre>
  return out + "\n";
}

export const LANG_LABEL: Record<string, string> = {
  ts: "TypeScript", js: "JavaScript", py: "Python", css: "CSS", json: "JSON",
  md: "Markdown", html: "HTML", yaml: "YAML", toml: "TOML", sh: "Shell",
  c: "C", cpp: "C++", java: "Java", go: "Go", rust: "Rust", sql: "SQL",
  xml: "XML", csv: "CSV", txt: "Plain Text",
};
