"""
AURA performance baseline
=========================

Launches the real app (production build, Electron + the Python brain),
walks it through every screen, and records what each one costs this machine:
CPU and RAM per process, GPU load, and the main window's frame rate. On Home
it also hides each animated layer in turn, to show which one costs what.
Run it before and after an optimisation and compare the two reports.

Run it from the AURA folder with the venv active, and leave AURA's window
alone while it works (about 8 minutes). Being covered by another window is
fine — Chromium's "window is covered, stop drawing" shortcut is switched off
for the run — but minimising or closing it isn't. A minimised window is
brought back before the next scenario, each scenario records whether the
window was visible, and if AURA closes mid-run you still get the scenarios
measured so far:

    python tools/perf_baseline.py                   # writes docs/perf/<date>-baseline.{json,md}
    python tools/perf_baseline.py --label after-video-fix
    python tools/perf_baseline.py --seconds 10      # quicker, noisier
    python tools/perf_baseline.py --compare docs/perf/A.json docs/perf/B.json

How it drives the app: Electron is started with a local DevTools port
(127.0.0.1 only, for this run only). Through it the script clicks the
sidebar, and fakes the brain's "thinking"/"speaking" state frames on the
window's own socket — so those states are measured without sending a real
message, calling a model, or writing to the chat history.

Side effects, all undone before it exits: the desktop buddy is switched off
for one scenario and back on, and the app is left on Home.

Requires: psutil and websockets (pip install psutil; websockets is already in
requirements-web.txt), and a built face (frontend/dist — AURA.bat builds it).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from contextlib import ExitStack

import psutil
from websockets.sync.client import connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")
ELECTRON = os.path.join(FRONTEND, "node_modules", "electron", "dist", "electron.exe")
BRAIN_PORT = 8760
CDP_PORT = 9222
NCPU = psutil.cpu_count() or 1
MB = 1024 * 1024

PAGES = ["Chats", "Memory", "Tasks", "Models", "Settings", "Labs"]


# ---------------------------------------------------------------------------
# DevTools protocol — just enough of it: evaluate, call a function on an
# object, list live objects of a prototype.
# ---------------------------------------------------------------------------
class Page:
    def __init__(self, ws_url: str, stack: ExitStack) -> None:
        self.ws = stack.enter_context(connect(ws_url, max_size=None, open_timeout=10))
        self._id = 0

    def call(self, method: str, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=60))
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]

    def js(self, expr: str):
        res = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS failed: {res['exceptionDetails'].get('text')} in {expr[:80]}")
        return res["result"].get("value")


def page_targets() -> dict[str, str]:
    """{"main"|"buddy": websocket url} for the app's two windows."""
    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as r:
        targets = json.load(r)
    out = {}
    for t in targets:
        if t.get("type") != "page":
            continue
        if t["url"].endswith("buddy.html"):
            out["buddy"] = t["webSocketDebuggerUrl"]
        elif t["url"].endswith("index.html"):
            out["main"] = t["webSocketDebuggerUrl"]
    return out


# Which page is on screen: the Domain overlay, or the sidebar's active item.
CURRENT_PAGE = """(document.querySelector(".screen--domain") ? "Aura Domain"
  : document.querySelector(".osbar__item--active .osbar__label")?.textContent.trim() ?? null)"""

# Frame timing in the main window: a rAF loop collecting frame gaps.
FPS_START = """(() => {
  const p = window.__auraPerf = { gaps: [], last: performance.now(), t0: performance.now() };
  const f = (t) => { p.gaps.push(t - p.last); p.last = t; p.raf = requestAnimationFrame(f); };
  p.raf = requestAnimationFrame(f);
  return true;
})()"""

FPS_STOP = """(() => {
  const CURRENT_PAGE = """ + CURRENT_PAGE + """;
  const p = window.__auraPerf; if (!p) return null;
  cancelAnimationFrame(p.raf);
  const secs = (performance.now() - p.t0) / 1000;
  const g = p.gaps.slice(1).sort((a, b) => a - b);
  const pct = (q) => g.length ? g[Math.min(g.length - 1, Math.floor(q * g.length))] : null;
  return {
    fps: g.length / secs,
    frame_ms_p50: pct(0.5), frame_ms_p95: pct(0.95), frame_ms_max: g.length ? g[g.length - 1] : null,
    slow_frames_pct: g.length ? 100 * g.filter((x) => x > 33.4).length / g.length : null,
    visible: document.visibilityState, focused: document.hasFocus(), page: CURRENT_PAGE,
    js_heap_mb: performance.memory ? performance.memory.usedJSHeapSize / 1048576 : null,
    dom_nodes: document.getElementsByTagName("*").length,
    dpr: window.devicePixelRatio,
    viewport: `${innerWidth}x${innerHeight}`,
    videos_playing: [...document.querySelectorAll("video")].filter((v) => !v.paused)
      .map((v) => `${v.currentSrc.split("/").pop()} ${v.videoWidth}x${v.videoHeight}`),
    canvases: [...document.querySelectorAll("canvas")]
      .map((c) => `${c.className.split(" ")[0] || "canvas"} ${c.width}x${c.height}`),
  };
})()"""

# The Home screen's layers, for the "which one costs what" scenarios. Hidden
# with CSS: the layer stops being composited, but its JS loop keeps running,
# so these numbers are an approximation of each layer's share.
LAYERS = {
    "background video": ".universe-bg",
    "particle field": ".particle-field",
    "black hole": ".bh-wrap",
    "cursor lens": ".cursor-lens",
}


def hide(page: Page, selector: str | None) -> None:
    css = f"{selector} {{ display: none !important; }}" if selector else ""
    page.js(f"""(() => {{
      let s = document.getElementById("__perf_hide");
      if (!s) {{ s = document.createElement("style"); s.id = "__perf_hide"; document.head.append(s); }}
      s.textContent = {json.dumps(css)};
    }})()""")

# Fake one brain "state" frame on the window's open socket.
FAKE_STATE = """function (state) {
  const ws = this.find((w) => w.readyState === 1 && String(w.url).includes(":8760"));
  if (!ws) return false;
  ws.dispatchEvent(new MessageEvent("message",
    { data: JSON.stringify({ type: "state", payload: { state } }) }));
  return true;
}"""


def fake_state(page: Page, state: str) -> bool:
    proto = page.call("Runtime.evaluate", expression="WebSocket.prototype")["result"]["objectId"]
    arr = page.call("Runtime.queryObjects", prototypeObjectId=proto)["objects"]["objectId"]
    res = page.call("Runtime.callFunctionOn", objectId=arr, functionDeclaration=FAKE_STATE,
                    arguments=[{"value": state}], returnByValue=True)
    return bool(res["result"].get("value"))


def click_nav(page: Page, label: str) -> bool:
    return page.js(f"""(() => {{
      const el = [...document.querySelectorAll(".osbar__item")]
        .find((b) => b.querySelector(".osbar__label")?.textContent.trim() === {json.dumps(label)});
      if (!el) return false; el.click(); return true;
    }})()""")


# ---------------------------------------------------------------------------
# Process tree and per-process sampling
# ---------------------------------------------------------------------------
def classify(p: psutil.Process, buddy_pid: int | None) -> str:
    try:
        name = p.name().lower()
        cmd = " ".join(p.cmdline())
    except psutil.Error:
        return "gone"
    if name.startswith("python"):
        return "brain (python)"
    if "--type=renderer" in cmd:
        return "buddy window" if p.pid == buddy_pid else "main window"
    if "--type=gpu-process" in cmd:
        return "gpu process"
    if "--type=utility" in cmd:
        if "NetworkService" in cmd:
            return "network"
        if "AudioService" in cmd:
            return "audio"
        return "utility"
    if "--type=crashpad" in cmd:
        return "crashpad"
    if "--type=" not in cmd and name.startswith("electron"):
        return "electron main"
    return name


def tree(root: psutil.Process) -> list[psutil.Process]:
    try:
        return [root] + root.children(recursive=True)
    except psutil.Error:
        return []


def find_buddy_pid(buddy: Page, procs: list[psutil.Process]) -> int | None:
    """Burn 1.5 s of CPU inside the buddy page; the renderer that jumps is it."""
    renderers = [p for p in procs if "--type=renderer" in " ".join(p.cmdline())]
    before = {p.pid: sum(p.cpu_times()[:2]) for p in renderers}
    buddy.js("(() => { const t = performance.now(); while (performance.now() - t < 1500) {} return 1; })()")
    jumps = {p.pid: sum(p.cpu_times()[:2]) - before[p.pid] for p in renderers}
    return max(jumps, key=jumps.get) if jumps else None


# Engine load every second; GPU memory once, at the end of the window (it
# barely moves, and reading it every second tripled the sampler's output).
GPU_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
function Emit($set) {{
  $ts = $set.Timestamp.ToString('o')
  foreach ($s in $set.CounterSamples) {{ if ($s.CookedValue -gt 0) {{ "$ts`t$($s.Path)`t$($s.CookedValue)" }} }}
}}
foreach ($set in Get-Counter -Counter '\GPU Engine(*)\Utilization Percentage' -SampleInterval 1 -MaxSamples {n}) {{ Emit $set }}
Emit (Get-Counter -Counter '\GPU Process Memory(*)\Shared Usage','\GPU Process Memory(*)\Dedicated Usage')
"""


def start_gpu_sampler(seconds: int) -> subprocess.Popen:
    return subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", GPU_PS.format(n=seconds)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def parse_gpu(raw: str, expected: int) -> dict:
    """Per pid: mean 'GPU %' (busiest engine type, as Task Manager shows it),
    mean 3D and video-decode %, and shared/dedicated memory at the end of the
    window. Plus the whole machine's 3D load. A second where no engine was
    busy prints nothing, so the mean divides by the samples asked for."""
    util = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # ts -> pid -> engtype -> %
    mem = defaultdict(lambda: {"shared_mb": 0.0, "dedicated_mb": 0.0})
    stamps = set()
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ts, path, val = parts[0], parts[1].lower(), float(parts[2])
        inst = path[path.find("(") + 1:path.rfind(")")]
        if not inst.startswith("pid_"):
            continue
        pid = int(inst.split("_")[1])
        if "gpu engine" in path:
            stamps.add(ts)
            eng = inst.rsplit("engtype_", 1)[-1]
            util[ts][pid][eng] += val
        elif "shared usage" in path:
            mem[pid]["shared_mb"] = max(mem[pid]["shared_mb"], val / MB)
        elif "dedicated usage" in path:
            mem[pid]["dedicated_mb"] = max(mem[pid]["dedicated_mb"], val / MB)
    n = max(1, len(stamps), expected)
    per_pid = defaultdict(lambda: {"gpu_pct": 0.0, "3d_pct": 0.0, "video_decode_pct": 0.0})
    machine_3d = [0.0] * (n - len(stamps))  # the idle seconds that printed nothing
    for ts in stamps:
        total_3d = 0.0
        for pid, engs in util[ts].items():
            per_pid[pid]["gpu_pct"] += min(100.0, max(engs.values())) / n
            per_pid[pid]["3d_pct"] += min(100.0, engs.get("3d", 0.0)) / n
            per_pid[pid]["video_decode_pct"] += min(100.0, engs.get("videodecode", 0.0)) / n
            total_3d += engs.get("3d", 0.0)
        machine_3d.append(min(100.0, total_3d))
    for pid, m in mem.items():
        per_pid[pid].update(m)
    return {"samples": len(stamps), "per_pid": dict(per_pid),
            "machine_3d_pct": statistics.mean(machine_3d) if machine_3d else None}


def measure(label: str, seconds: int, root: psutil.Process | None, buddy_pid: int | None,
            main: Page | None) -> dict:
    print(f"  measuring {label!r} for {seconds}s ...", flush=True)
    gpu = start_gpu_sampler(seconds)
    procs = tree(root) if root else []
    ours = {p.pid for p in procs}
    # Everything else on the machine too, to see what AURA makes *other*
    # processes do (the Windows compositor, the graphics driver) — and what
    # this script itself costs.
    me = {os.getpid(), gpu.pid}
    others = [p for p in psutil.process_iter() if p.pid not in ours and p.pid != 0]
    for p in procs + others:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    psutil.cpu_percent(None)
    if main:
        main.js(FPS_START)
    cpu = defaultdict(list)
    machine_cpu = []
    for _ in range(seconds):
        time.sleep(1)
        machine_cpu.append(psutil.cpu_percent(None))
        for p in procs:
            try:
                cpu[p.pid].append(p.cpu_percent(None) / NCPU)
            except psutil.Error:
                pass
    # The rest of the machine is read once, as an average over the window:
    # reading ~400 processes costs about a second (protected ones take a slow
    # path), which per-second sampling would pay fifteen times over.
    for p in others:
        try:
            cpu[p.pid].append(p.cpu_percent(None) / NCPU)
        except psutil.Error:
            pass
    frames = main.js(FPS_STOP) if main else None
    try:
        out, _ = gpu.communicate(timeout=seconds + 60)
    except subprocess.TimeoutExpired:
        gpu.kill()
        out = ""
    g = parse_gpu(out, seconds if out else 0)

    by_name = defaultdict(float)
    for p in others:
        if not cpu[p.pid]:
            continue
        try:
            name = "(this script)" if p.pid in me else p.name()
        except psutil.Error:
            continue
        by_name[name] += statistics.mean(cpu[p.pid])
    top_others = dict(sorted(by_name.items(), key=lambda kv: -kv[1])[:6])

    per_proc = {}
    for p in procs:
        try:
            role = classify(p, buddy_pid)
            mem = p.memory_full_info()
        except psutil.Error:
            continue
        gp = g["per_pid"].get(p.pid, {})
        row = per_proc.setdefault(role, defaultdict(float))
        row["count"] += 1
        row["cpu_pct"] += statistics.mean(cpu[p.pid]) if cpu[p.pid] else 0.0
        row["cpu_pct_peak"] += max(cpu[p.pid]) if cpu[p.pid] else 0.0
        row["ram_mb"] += mem.uss / MB            # private working set (Task Manager "Memory")
        row["commit_mb"] += mem.private / MB     # private bytes
        for k in ("gpu_pct", "3d_pct", "video_decode_pct", "shared_mb", "dedicated_mb"):
            row[k] += gp.get(k, 0.0)
    per_proc = {k: dict(v) for k, v in per_proc.items()}

    vm = psutil.virtual_memory()
    result = {
        "label": label,
        "seconds": seconds,
        "aura": {
            "cpu_pct": sum(r["cpu_pct"] for r in per_proc.values()),
            "ram_mb": sum(r["ram_mb"] for r in per_proc.values()),
            "gpu_pct": sum(r["gpu_pct"] for r in per_proc.values()),
            "gpu_shared_mb": sum(r["shared_mb"] for r in per_proc.values()),
            "processes": sum(int(r["count"]) for r in per_proc.values()),
        },
        "per_process": per_proc,
        "machine": {
            "cpu_pct": statistics.mean(machine_cpu),
            "gpu_3d_pct": g["machine_3d_pct"],
            "ram_used_mb": (vm.total - vm.available) / MB,
            "gpu_samples": g["samples"],
            "top_other_cpu_pct": top_others,
        },
        "frames": frames,
    }
    a = result["aura"]
    fr = f", {frames['fps']:.0f} fps, {frames['visible']}" if frames else ""
    print(f"    AURA: cpu {a['cpu_pct']:.1f}%  ram {a['ram_mb']:.0f} MB  gpu {a['gpu_pct']:.1f}%{fr}",
          flush=True)
    return result


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(cond, timeout: float, what: str):
    t = time.time()
    while time.time() - t < timeout:
        try:
            v = cond()
            if v:
                return v
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {what}")


def run(args, report: dict) -> None:
    print("1/4 machine idle, before AURA starts")
    report["scenarios"].append(measure("machine idle (AURA closed)", args.seconds, None, None, None))

    print("2/4 cold start")
    t0 = time.time()
    env = {**os.environ, "AURA_PROD": "1"}
    app = subprocess.Popen(
        [ELECTRON, ".", f"--remote-debugging-port={CDP_PORT}",
         # Keep drawing while another window covers AURA's, so a stray click
         # elsewhere doesn't turn a scenario into a measurement of nothing.
         "--disable-features=CalculateNativeWinOcclusion"],
        cwd=FRONTEND, env=env)
    root = psutil.Process(app.pid)
    main = buddy = None
    buddy_was_on = True
    stack = ExitStack()
    try:
        wait_for(lambda: port_open(CDP_PORT) and "main" in page_targets(), 60, "the window")
        targets = page_targets()
        main = Page(targets["main"], stack)
        wait_for(lambda: main.js("document.readyState") == "complete", 60, "the page to load")
        window_s = time.time() - t0
        wait_for(lambda: port_open(BRAIN_PORT), 120, "the brain")
        brain_s = time.time() - t0
        # Opened behind another window, the page counts as hidden and its
        # video never starts — bring it forward first.
        if "buddy" in targets and main.js("document.visibilityState") != "visible":
            print("    window opened hidden — bringing it forward", flush=True)
            buddy = Page(targets["buddy"], stack)
            buddy.js("window.aura.buddy.openMain()")
        try:
            wait_for(lambda: main.js(
                "[...document.querySelectorAll('video')].some(v => !v.paused)"), 30, "the background video")
        except TimeoutError:
            print(f"    page: visible={main.js('document.visibilityState')} screenX={main.js('window.screenX')} "
                  f"videos={main.js('document.querySelectorAll(\"video\").length')}", flush=True)
            raise
        paint = main.js("""(() => { const p = performance.getEntriesByName('first-contentful-paint')[0];
                                    return p ? p.startTime / 1000 : null; })()""")
        report["startup"] = {"window_loaded_s": window_s, "brain_listening_s": brain_s,
                             "first_paint_in_page_s": paint}
        print(f"    window {window_s:.1f}s, brain {brain_s:.1f}s")
        time.sleep(args.settle)

        if "buddy" in targets:
            buddy = buddy or Page(targets["buddy"], stack)
            buddy_was_on = bool(buddy.js("document.visibilityState === 'visible'"))
        buddy_pid = find_buddy_pid(buddy, tree(root)) if buddy else None

        def scenario(label: str, settle: float = 4.0, seconds: int | None = None,
                     restore: bool = True, page: str | None = "Home") -> None:
            if app.poll() is not None:
                raise RuntimeError(f"AURA closed during the run, before {label!r}")
            if restore and buddy and main.js("document.visibilityState") != "visible":
                print("    window was minimised — bringing it back", flush=True)
                buddy.js("window.aura.buddy.openMain()")
                settle += 2
            # AURA's window is full-screen on top: a click meant for another
            # app can land on her sidebar. Measure the page the label says.
            if page and main.js(CURRENT_PAGE) != page:
                print(f"    on {main.js(CURRENT_PAGE)!r}, not {page!r} — going back", flush=True)
                click_nav(main, page)
                settle += 2
            time.sleep(settle)
            res = measure(label, seconds or args.seconds, root, buddy_pid, main)
            on = (res["frames"] or {}).get("page")
            if page and on != page:
                res["page_mismatch"] = on
                print(f"    ⚠ ended on {on!r} — this row didn't measure {page!r}", flush=True)
            report["scenarios"].append(res)

        print("3/4 screens")
        click_nav(main, "Home")
        scenario("Home — idle", settle=2)
        if fake_state(main, "thinking"):
            scenario("Home — thinking (simulated)", settle=2)
            fake_state(main, "speaking")
            scenario("Home — speaking (simulated, no audio)", settle=2)
            fake_state(main, "idle")
        else:
            print("    (couldn't reach the socket — thinking/speaking skipped)")
        if buddy:
            main.js("window.aura.buddy.setEnabled(false)")
            scenario("Home — idle, buddy switched off")
            main.js("window.aura.buddy.setEnabled(true)")
        for layer, selector in LAYERS.items():
            hide(main, selector)
            scenario(f"Home — idle, without {layer}", settle=3)
        hide(main, ", ".join(LAYERS.values()))
        scenario("Home — idle, all four layers hidden", settle=3)
        hide(main, None)
        for label in PAGES:
            if click_nav(main, label):
                scenario(f"{label} page", page=label)
        click_nav(main, "Home")
        time.sleep(2)
        if click_nav(main, "Aura Domain"):
            scenario("Aura Domain", settle=8, page="Aura Domain")
        main.js("window.aura.minimize()")
        scenario("Minimised (buddy still out)", settle=5, restore=False, page=None)
        print("4/4 closing")
        if buddy:
            buddy.js("window.aura.buddy.openMain()")
            time.sleep(1)
    finally:
        try:
            if main:
                main.js("window.aura.buddy.setEnabled(true)" if buddy_was_on else "true")
                click_nav(main, "Home")
                main.js("window.aura.close()")
        except Exception:  # noqa: BLE001
            pass
        try:
            stack.close()
        except Exception:  # noqa: BLE001 — the window closing drops the sockets first
            pass
        try:
            app.wait(timeout=15)
        except subprocess.TimeoutExpired:
            for p in reversed(tree(root)):
                try:
                    p.kill()
                except psutil.Error:
                    pass
        time.sleep(2)
        for p in psutil.process_iter(["name", "cmdline"]):  # the brain, if Electron missed it
            try:
                if p.info["name"].lower().startswith("python") and "server.py" in (p.info["cmdline"] or []) \
                        and os.path.samefile(p.cwd(), ROOT):
                    p.kill()
            except (psutil.Error, OSError):
                pass


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt(v, spec=".0f", unit=""):
    return "—" if v is None else f"{v:{spec}}{unit}"


def markdown(r: dict) -> str:
    m = r["machine"]
    lines = [
        f"# AURA performance — {r['label']}",
        "",
        f"Measured {r['when']} with `tools/perf_baseline.py` on {m['cpu_threads']} CPU threads / "
        f"{m['ram_gb']} GB RAM. CPU % is of the whole machine (all cores), like Task Manager. "
        "RAM is private working set. GPU % is the busiest GPU engine, averaged; GPU memory is read "
        "at the end of each window.",
        "",
    ]
    if r.get("aborted"):
        lines += [f"**Incomplete run** — stopped early: {r['aborted']}.", ""]
    s = r.get("startup")
    if s:
        lines += [f"**Cold start:** window loaded in {s['window_loaded_s']:.1f} s, brain listening in "
                  f"{s['brain_listening_s']:.1f} s.", ""]
    home = next((sc["frames"] for sc in r["scenarios"] if sc["label"] == "Home — idle"), None)
    if home:
        lines += [f"**Home draws:** {home['viewport']} window at {home['dpr']}x pixel ratio; "
                  f"canvases {', '.join(home['canvases']) or 'none'}; "
                  f"videos {', '.join(home['videos_playing']) or 'none'}.", ""]
    lines += [
        "## Per screen",
        "",
        "| Scenario | AURA CPU | AURA RAM | AURA GPU | GPU shared mem | Machine CPU | Machine GPU 3D | FPS | p95 frame | Slow frames | Window |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for sc in r["scenarios"]:
        a, mc, fr = sc["aura"], sc["machine"], sc["frames"] or {}
        lines.append(
            f"| {sc['label']} | {fmt(a['cpu_pct'], '.1f', '%')} | {fmt(a['ram_mb'], '.0f', ' MB')} | "
            f"{fmt(a['gpu_pct'], '.1f', '%')} | {fmt(a['gpu_shared_mb'], '.0f', ' MB')} | "
            f"{fmt(mc['cpu_pct'], '.1f', '%')} | {fmt(mc['gpu_3d_pct'], '.1f', '%')} | "
            f"{fmt(fr.get('fps'), '.0f')} | {fmt(fr.get('frame_ms_p95'), '.1f', ' ms')} | "
            f"{fmt(fr.get('slow_frames_pct'), '.1f', '%')} | {fr.get('visible', '—')}"
            + (f" ⚠ was on {sc['page_mismatch']}" if sc.get("page_mismatch") else "") + " |"
        )
    lines += ["", "## Where it goes (per process)", ""]
    roles = ["main window", "buddy window", "gpu process", "brain (python)", "electron main",
             "network", "audio", "utility", "crashpad"]
    head = "| Scenario | " + " | ".join(roles) + " |"
    lines += [head, "|" + "---|" * (len(roles) + 1)]
    for sc in r["scenarios"]:
        pp = sc["per_process"]
        if not pp:
            continue
        cells = []
        for role in roles:
            x = pp.get(role)
            if not x:
                cells.append("—")
                continue
            g = f", {x['gpu_pct']:.0f}% gpu" if x.get("gpu_pct", 0) >= 0.5 else ""
            cells.append(f"{x['cpu_pct']:.1f}% · {x['ram_mb']:.0f} MB{g}")
        lines.append(f"| {sc['label']} | " + " | ".join(cells) + " |")
    lines += ["", "Cells: CPU % · RAM (· GPU % when it uses any).", ""]
    lines += ["## Busiest other processes", "",
              "What else was using CPU meanwhile. dwm.exe is the Windows compositor — it works "
              "harder when AURA's window does; (this script) is the measuring itself.", "",
              "| Scenario | Top other processes (CPU %) |", "|---|---|"]
    for sc in r["scenarios"]:
        top = sc["machine"].get("top_other_cpu_pct") or {}
        cells = ", ".join(f"{name} {v:.1f}%" for name, v in top.items())
        lines.append(f"| {sc['label']} | {cells or '—'} |")
    lines.append("")
    return "\n".join(lines)


def compare(before_path: str, after_path: str) -> str:
    """Markdown before → after table for the scenarios both runs measured."""
    with open(before_path, encoding="utf-8") as f:
        before = {sc["label"]: sc for sc in json.load(f)["scenarios"]}
    with open(after_path, encoding="utf-8") as f:
        after = json.load(f)
    pair = lambda a, b, spec, unit="": f"{fmt(a, spec, unit)} → **{fmt(b, spec, unit)}**"  # noqa: E731
    lines = [
        "| Scenario | FPS | AURA GPU | AURA CPU | AURA RAM | p95 frame |",
        "|---|---|---|---|---|---|",
    ]
    for sc in after["scenarios"]:
        b = before.get(sc["label"])
        if not b or not sc["per_process"]:
            continue
        fb, fa = b["frames"] or {}, sc["frames"] or {}
        lines.append(
            f"| {sc['label']} | {pair(fb.get('fps'), fa.get('fps'), '.0f')} | "
            f"{pair(b['aura']['gpu_pct'], sc['aura']['gpu_pct'], '.0f', '%')} | "
            f"{pair(b['aura']['cpu_pct'], sc['aura']['cpu_pct'], '.1f', '%')} | "
            f"{pair(b['aura']['ram_mb'], sc['aura']['ram_mb'], '.0f', ' MB')} | "
            f"{pair(fb.get('frame_ms_p95'), fa.get('frame_ms_p95'), '.0f', ' ms')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--seconds", type=int, default=15, help="sampling time per scenario")
    ap.add_argument("--settle", type=float, default=10.0, help="wait after start before measuring")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "perf"))
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE.json", "AFTER.json"),
                    help="print a before → after table from two earlier runs, and exit")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # scenario labels use "—"
    if args.compare:
        print(compare(*args.compare))
        return
    if port_open(BRAIN_PORT):
        sys.exit("A brain is already running on :8760 — close AURA first, so this run measures a cold start.")
    if not os.path.exists(os.path.join(FRONTEND, "dist", "index.html")):
        sys.exit("frontend/dist is missing — build the face first (cd frontend && npm run build).")

    report = {
        "label": args.label,
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "machine": {
            "cpu_threads": NCPU,
            "ram_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        },
        "scenarios": [],
    }
    try:
        run(args, report)
    except Exception as e:  # noqa: BLE001 — keep what was measured before it broke
        report["aborted"] = f"{type(e).__name__}: {e}"
        print(f"\nrun stopped early — {report['aborted']}")
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, f"{dt.date.today().isoformat()}-{args.label}")
    with open(stem + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(markdown(report))
    print(f"\nwrote {stem}.md and .json")


if __name__ == "__main__":
    main()
