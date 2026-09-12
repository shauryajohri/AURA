/* =====================================================================
   site.js — renders content.js into index.html.
   ---------------------------------------------------------------------
   There is no content in this file. If you are here to change a word,
   you are in the wrong file: open content.js.
   ===================================================================== */
(function () {
  "use strict";

  var C = window.AURA_CONTENT;
  if (!C) return;

  /* ---------------------------------------------------------- helpers */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function el(id) { return document.getElementById(id); }
  function set(id, html) { var n = el(id); if (n) n.innerHTML = html; }

  /* shell comments are dimmed so the command itself reads first */
  function shell(code) {
    return esc(code).replace(/(#[^\n]*)/g, '<span class="c">$1</span>');
  }
  function pathTag(code) {
    return code ? '<div class="path">' + esc(code) + "</div>" : "";
  }
  /* a figure renders only if content.js still has a key for it */
  function figure(mountId, key) {
    var f = (C.figures || {})[key];
    if (!f) return;
    set(mountId,
      '<figure class="figure"><img src="' + esc(f.src) + '" alt="' + esc(f.alt) +
      '" loading="lazy"><figcaption>' + esc(f.caption) + "</figcaption></figure>");
  }

  /* --------------------------------------------------- derived counts */
  /* Nothing below is written down anywhere. It is all counted from the
     capabilities list, which is why adding one row keeps the page true. */
  var caps = C.capabilities || [];
  var order = Object.keys(C.states);
  var byState = {};
  order.forEach(function (k) { byState[k] = caps.filter(function (c) { return c.status === k; }); });
  var total = caps.length;
  var liveN = (byState.live || []).length;
  var formN = (byState.forming || []).length;
  var pct = total ? Math.round((liveN / total) * 100) : 0;

  /* ------------------------------------------------------------- hero */
  set("hero",
    '<p class="kicker reveal">' + esc(C.hero.kicker) + "</p>" +
    '<h1 class="reveal">' + esc(C.hero.headline) + "</h1>" +
    '<p class="lede measure reveal">' + esc(C.hero.lede) + "</p>" +
    '<div class="hero__actions reveal">' +
      C.hero.actions.map(function (a) {
        var ext = /^https?:/.test(a.href);
        return '<a class="btn btn--' + esc(a.kind) + '" href="' + esc(a.href) + '"' +
               (ext ? ' rel="noopener"' : "") + ">" + esc(a.label) + "</a>";
      }).join("") +
    "</div>"
  );

  var src = el("nav-src");
  if (src) src.href = C.meta.repo;

  /* --------------------------------------- the status strip (the ask) */
  set("strip",
    "<dl><dt>Stage</dt><dd>" + esc(C.meta.stage) + "</dd></dl>" +
    "<dl><dt>Running</dt><dd>" + liveN + " of " + total + " capabilities</dd></dl>" +
    '<div class="meter" role="img" aria-label="' + liveN + " of " + total +
      ' capabilities running, ' + formN + ' being built">' +
      '<b class="m-live" style="width:' + pct + '%"></b>' +
      '<b class="m-forming" style="width:' +
        (total ? Math.round((formN / total) * 100) : 0) + '%"></b>' +
    "</div>" +
    "<dl><dt>Last updated</dt><dd>" + esc(C.meta.updated) + "</dd></dl>"
  );

  /* ---------------------------------------------------- the complaints */
  set("problem-head",
    '<p class="label">What it is</p>' +
    "<h2>" + esc(C.problems.title) + "</h2>"
  );
  set("problem-rows", C.problems.items.map(function (it) {
    return '<div class="row">' +
      '<p class="quote">' + esc(it.quote) + "</p>" +
      "<div><h3>" + esc(it.answer) + "</h3>" +
      '<p class="measure" style="margin-top:10px">' + esc(it.body) + "</p>" +
      pathTag(it.code) + "</div></div>";
  }).join(""));

  /* --------------------------------------------------- a single turn */
  set("turn-head",
    '<p class="label">How it works</p>' +
    "<h2>" + esc(C.pipeline.title) + "</h2>" +
    '<p class="measure">' + esc(C.pipeline.lede) + "</p>"
  );
  set("turn-rows", C.pipeline.steps.map(function (s) {
    return '<div class="row">' +
      "<div><h3>" + esc(s.n) + " " + esc(s.title) + "</h3>" +
      '<p style="margin-top:8px">' + esc(s.question) + "</p></div>" +
      '<div><p class="measure">' + esc(s.body) + "</p>" + pathTag(s.code) + "</div>" +
      "</div>";
  }).join(""));
  figure("fig-problem", "problem");
  figure("fig-turn", "turn");

  /* --------------------------------------------------- the two halves */
  set("halves-head",
    '<p class="label">What you get</p>' +
    "<h2>Two halves, one brain.</h2>"
  );
  set("halves-grid", C.halves.map(function (h) {
    var mine = caps.filter(function (c) { return c.half === h.key; });
    return '<div class="half"><h3>' + esc(h.name) + "</h3>" +
      "<p>" + esc(h.body) + "</p><ul>" +
      mine.slice(0, 8).map(function (c) {
        return '<li data-status="' + esc(c.status) + '">' + esc(c.name) + "</li>";
      }).join("") + "</ul></div>";
  }).join(""));
  figure("fig-halves", "halves");

  /* ============================== THE LEDGER — the spine of the page = */
  set("stage-head",
    '<p class="label">Current stage</p>' +
    "<h2>Everything it can do, and what it cannot do yet.</h2>" +
    '<p class="measure">This list is the project’s own record, not a summary of it. ' +
    "When a capability ships, one line changes in <code>content.js</code> and this " +
    "section, the counts above and the progress bar all move with it.</p>"
  );

  var filters = [{ k: "all", label: "Everything (" + total + ")" }].concat(
    order.filter(function (k) { return byState[k].length; }).map(function (k) {
      return { k: k, label: C.states[k].label + " (" + byState[k].length + ")" };
    })
  );
  set("stage-filters", filters.map(function (f, i) {
    return '<button type="button" data-f="' + esc(f.k) + '" aria-pressed="' +
      (i === 0) + '">' + esc(f.label) + "</button>";
  }).join(""));

  function ledgerHTML(filter) {
    return C.halves.map(function (h) {
      var rows = caps.filter(function (c) {
        return c.half === h.key && (filter === "all" || c.status === filter);
      });
      if (!rows.length) return "";
      return '<div class="ledger__group"><h3>' + esc(h.name) + "</h3>" +
        "<p>" + rows.length + (rows.length === 1 ? " capability" : " capabilities") + "</p>" +
        rows.map(function (c) {
          var st = C.states[c.status];
          return '<div class="lrow" data-status="' + esc(c.status) + '">' +
            '<span class="lrow__dot" aria-hidden="true"></span>' +
            '<span class="lrow__name">' + esc(c.name) + "</span>" +
            '<span class="lrow__blurb">' + esc(c.blurb) + "</span>" +
            '<span class="lrow__state">' + esc(st.label) + "</span>" +
            (c.code ? '<span class="lrow__code path">' + esc(c.code) + "</span>" : "") +
            "</div>";
        }).join("") + "</div>";
    }).join("");
  }
  set("ledger", ledgerHTML("all"));

  var fbar = el("stage-filters");
  if (fbar) fbar.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-f]");
    if (!b) return;
    fbar.querySelectorAll("button").forEach(function (x) {
      x.setAttribute("aria-pressed", String(x === b));
    });
    set("ledger", ledgerHTML(b.getAttribute("data-f")));
  });

  /* ------------------------------------------------------- the ladder */
  set("ladder-head",
    '<p class="label">The permission ladder</p>' +
    "<h2>" + esc(C.ladder.title) + "</h2>" +
    '<p class="measure">' + esc(C.ladder.body) + "</p>"
  );
  var rungs = C.ladder.rungs;
  set("ladder-rungs", rungs.map(function (r, i) {
    return '<div class="rung" data-i="' + (i + 1) + '" data-on="0">' +
      '<span class="rung__n">' + (i + 1) + "</span>" +
      '<span class="rung__name">' + esc(r.name) + "</span>" +
      '<span class="rung__grants">' + esc(r.grants) +
        (r.note ? " — " + esc(r.note) : "") + "</span>" +
      "</div>";
  }).join(""));

  var range = el("rung-range"), out = el("rung-out");
  function paintLadder() {
    var v = Number(range.value);
    document.querySelectorAll(".rung").forEach(function (n) {
      n.setAttribute("data-on", Number(n.getAttribute("data-i")) <= v ? "1" : "0");
    });
    var r = rungs[v - 1];
    out.textContent = "Set to " + r.name.toLowerCase() + ". She can " + r.grants +
      ", and nothing above it.";
  }
  if (range) { range.max = String(rungs.length); range.addEventListener("input", paintLadder); paintLadder(); }

  /* ------------------------------------------------------ get started */
  set("install-head",
    '<p class="label">Getting started</p>' +
    "<h2>" + esc(C.install.title) + "</h2>" +
    '<p class="measure">' + esc(C.install.lede) + "</p>"
  );
  set("install-steps", C.install.steps.map(function (s, i) {
    return '<div class="step"><p class="step__n">' + (i + 1) + "</p>" +
      "<h3>" + esc(s.name) + "</h3>" +
      "<pre><code>" + shell(s.code) + "</code></pre>" +
      (s.note ? '<p class="measure">' + esc(s.note) + "</p>" : "") + "</div>";
  }).join(""));
  set("install-req", esc(C.install.requires));

  /* --------------------------------------------------------------- faq */
  set("faq-head",
    '<p class="label">Before you clone it</p>' +
    "<h2>" + esc(C.faq.title) + "</h2>"
  );
  set("faq-list", C.faq.items.map(function (q) {
    return "<details><summary>" + esc(q.q) + "</summary>" +
      '<div class="a measure">' + esc(q.a) + "</div></details>";
  }).join(""));

  /* ------------------------------------------------------------- close */
  set("close-in",
    "<h2>" + esc(C.close.title) + "</h2>" +
    '<p class="measure">' + esc(C.close.body) + "</p>" +
    '<div class="hero__actions">' +
      '<a class="btn btn--go" href="' + esc(C.meta.repo) + '" rel="noopener">Clone the repository</a>' +
      '<a class="btn btn--ghost" href="#stage">See what runs today</a>' +
    "</div>"
  );
  set("footer",
    "<span>" + esc(C.close.footnote) + "</span>" +
    '<a href="' + esc(C.meta.repo) + '" rel="noopener">Source</a>' +
    "<span>Built by Shaurya.</span>"
  );

  /* -------------------------------------------------------- the spine */
  var marks = [
    ["problem", "What it is"], ["turn", "How it works"], ["halves", "Two halves"],
    ["stage", "Current stage"], ["ladder", "Permissions"], ["install", "Install"],
    ["faq", "Questions"]
  ];
  set("rail", marks.map(function (m) {
    return '<a href="#' + m[0] + '" data-sec="' + m[0] + '"><i></i><span>' + m[1] + "</span></a>";
  }).join(""));

  var links = Array.prototype.slice.call(document.querySelectorAll(".rail a"));
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        links.forEach(function (a) {
          a.classList.toggle("on", a.getAttribute("data-sec") === en.target.id);
        });
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    marks.forEach(function (m) { var n = el(m[0]); if (n) io.observe(n); });
  }

  /* the single orchestrated moment: the hero settles once, on load */
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { document.body.classList.add("loaded"); });
  });
})();
