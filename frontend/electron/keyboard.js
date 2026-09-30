// The mini keyboard: lights each key as AURA presses it and spells the word
// out on the horizon line, at the pace she types. Dragged by hand (the window
// can't take focus, so the OS can't drag it for us).
(() => {
  const plate = document.getElementById("plate");
  const text = document.getElementById("text");
  const keys = new Map([...document.querySelectorAll(".k")].map((k) => [k.dataset.k, k]));
  let typing = 0;
  let fade = 0;

  function strike(name) {
    const k = keys.get(name);
    if (!k) return;
    k.classList.remove("lit");
    void k.offsetWidth;               // restart the flash on a repeated letter
    k.classList.add("lit");
  }

  function settle() {
    plate.classList.remove("typing");
    clearTimeout(fade);
    fade = setTimeout(() => plate.classList.add("faded"), 2500);
  }

  window.kb.onEvent((ev) => {
    if (ev.kind === "type") {
      clearInterval(typing);
      clearTimeout(fade);
      plate.classList.remove("faded");
      plate.classList.add("typing");
      text.textContent = "";
      let i = 0;
      typing = setInterval(() => {
        const ch = ev.text[i++];
        text.textContent = ev.text.slice(0, i).slice(-22);
        strike(ch.toLowerCase());
        if (i >= ev.text.length) {
          clearInterval(typing);
          setTimeout(settle, 500);
        }
      }, ev.ms);
    } else if (ev.kind === "press") {
      strike(ev.key);
    } else if (ev.kind === "busy" && !ev.on) {
      settle();
    }
  });

  // drag: screen deltas to the main process, which moves the window
  let from = null;
  plate.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    from = { x: e.screenX, y: e.screenY };
    plate.setPointerCapture(e.pointerId);
    plate.classList.add("dragging");
    window.kb.dragStart();
  });
  plate.addEventListener("pointermove", (e) => {
    if (from) window.kb.dragMove(e.screenX - from.x, e.screenY - from.y);
  });
  const end = () => {
    if (!from) return;
    from = null;
    plate.classList.remove("dragging");
    window.kb.dragEnd();
  };
  plate.addEventListener("pointerup", end);
  plate.addEventListener("pointercancel", end);
  plate.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    window.kb.menu();
  });
})();
