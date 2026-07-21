import { useEffect, useState } from "react";
import { domainApi, type Connector } from "../../../domainApi";
import {
  ALL_SECTIONS,
  SECTION_META,
  STATUS_META,
  useDomainStore,
  type DomainSection,
  type ProjectStatus,
} from "../../../stores/domainStore";

// ============================================================================
// Domain Settings — the whole workspace is editable from here.
//
//   Layout      show/hide + reorder nav sections, panel widths, density,
//               corner radius, glass strength, background mode, accent
//   Projects    status, GitHub repo, local folder, tags, delete
//   Connectors  OAuth client credentials for Figma / Microsoft / GitHub
// ============================================================================

type Tab = "layout" | "projects" | "connectors";

const ACCENTS = ["#8b5cff", "#38e1ff", "#f472b6", "#35e08f", "#ff8c42", "#ff5a5a"];

// ------------------------------------------------------------------ layout
function LayoutTab() {
  const layout = useDomainStore((s) => s.layout);
  const setLayout = useDomainStore((s) => s.setLayout);
  const toggleSection = useDomainStore((s) => s.toggleSection);
  const moveSection = useDomainStore((s) => s.moveSection);
  const resetLayout = useDomainStore((s) => s.resetLayout);

  const order: DomainSection[] = [
    ...layout.navOrder.filter((s) => ALL_SECTIONS.includes(s)),
    ...ALL_SECTIONS.filter((s) => !layout.navOrder.includes(s)),
  ];

  return (
    <div className="dset">
      <div className="dset__group">
        <div className="dset__gtitle">Navigation</div>
        <p className="dset__hint">
          Drag-free reordering: use the arrows. Hidden sections disappear from the rail
          (Dashboard and Settings always stay).
        </p>
        <div className="dset__sections">
          {order.map((s, i) => {
            const hidden = layout.hidden.includes(s);
            const locked = s === "dashboard" || s === "settings";
            return (
              <div key={s} className={"dset__srow" + (hidden ? " dset__srow--off" : "")}>
                <span className="dset__sicon">{SECTION_META[s].icon}</span>
                <span className="dset__slabel">{SECTION_META[s].label}</span>
                <button onClick={() => moveSection(s, -1)} disabled={i === 0} title="Up">↑</button>
                <button onClick={() => moveSection(s, 1)} disabled={i === order.length - 1} title="Down">↓</button>
                <button
                  className={"dset__vis" + (hidden ? "" : " dset__vis--on")}
                  onClick={() => toggleSection(s)}
                  disabled={locked}
                  title={locked ? "Always visible" : hidden ? "Show" : "Hide"}
                >
                  {hidden ? "hidden" : "shown"}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <div className="dset__group">
        <div className="dset__gtitle">Panels</div>

        <label className="dset__field">
          <span>Nav width <em>{layout.navWidth}px</em></span>
          <input
            type="range" min={64} max={320} value={layout.navWidth}
            onChange={(e) => setLayout({ navWidth: Number(e.target.value) })}
          />
        </label>

        <label className="dset__field">
          <span>Chat width <em>{layout.chatWidth}px</em></span>
          <input
            type="range" min={260} max={560} value={layout.chatWidth}
            onChange={(e) => setLayout({ chatWidth: Number(e.target.value) })}
          />
        </label>

        <label className="dset__field">
          <span>Corner radius <em>{layout.radius}px</em></span>
          <input
            type="range" min={0} max={32} value={layout.radius}
            onChange={(e) => setLayout({ radius: Number(e.target.value) })}
          />
        </label>

        <label className="dset__field">
          <span>Glass blur <em>{layout.glass}px</em></span>
          <input
            type="range" min={0} max={40} value={layout.glass}
            onChange={(e) => setLayout({ glass: Number(e.target.value) })}
          />
        </label>

        <div className="dset__toggles">
          <button
            className={layout.showChat ? "on" : ""}
            onClick={() => setLayout({ showChat: !layout.showChat })}
          >
            AURA chat rail
          </button>
          <button
            className={layout.showHeader ? "on" : ""}
            onClick={() => setLayout({ showHeader: !layout.showHeader })}
          >
            Header bar
          </button>
        </div>
      </div>

      <div className="dset__group">
        <div className="dset__gtitle">Feel</div>

        <div className="dset__field">
          <span>Density</span>
          <div className="dset__seg">
            {(["cosy", "normal", "compact"] as const).map((d) => (
              <button
                key={d}
                className={layout.density === d ? "on" : ""}
                onClick={() => setLayout({ density: d })}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        <div className="dset__field">
          <span>Background</span>
          <div className="dset__seg">
            {(["video", "gradient", "flat"] as const).map((b) => (
              <button
                key={b}
                className={layout.background === b ? "on" : ""}
                onClick={() => setLayout({ background: b })}
              >
                {b}
              </button>
            ))}
          </div>
        </div>

        <div className="dset__field">
          <span>Accent</span>
          <div className="dset__swatches">
            {ACCENTS.map((c) => (
              <button
                key={c}
                className={"dset__sw" + (layout.accent === c ? " dset__sw--on" : "")}
                style={{ background: c, boxShadow: layout.accent === c ? `0 0 14px ${c}` : undefined }}
                onClick={() => setLayout({ accent: c })}
              />
            ))}
          </div>
        </div>

        <button className="dset__reset" onClick={resetLayout}>Reset layout to defaults</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- projects
function ProjectsTab() {
  const projects = useDomainStore((s) => s.projects);
  const patchProject = useDomainStore((s) => s.patchProject);
  const deleteProject = useDomainStore((s) => s.deleteProject);
  const setStatus = useDomainStore((s) => s.setStatus);

  return (
    <div className="dset">
      {projects.map((p) => (
        <div key={p.id} className="dset__project" style={{ ["--accent" as string]: p.accent }}>
          <div className="dset__phead">
            <input
              className="dset__pname"
              value={p.name}
              onChange={(e) => patchProject(p.id, { name: e.target.value })}
            />
            <select
              value={p.status}
              onChange={(e) => setStatus(p.id, e.target.value as ProjectStatus)}
              style={{ color: STATUS_META[p.status].color }}
            >
              {(Object.keys(STATUS_META) as ProjectStatus[]).map((s) => (
                <option key={s} value={s}>{STATUS_META[s].label}</option>
              ))}
            </select>
            <button className="dset__pdel" onClick={() => {
              if (confirm(`Delete "${p.name}"? Its tasks, docs and notes go with it.`))
                deleteProject(p.id);
            }}>✕</button>
          </div>

          <input
            className="dset__pfield"
            value={p.blurb}
            placeholder="One line about this project"
            onChange={(e) => patchProject(p.id, { blurb: e.target.value })}
          />
          <input
            className="dset__pfield"
            value={p.repoUrl ?? ""}
            placeholder="GitHub repo — https://github.com/owner/repo"
            onChange={(e) => patchProject(p.id, { repoUrl: e.target.value })}
          />
          <input
            className="dset__pfield"
            value={p.folder ?? ""}
            placeholder="Local folder — C:\\path\\to\\project (Code pane opens here)"
            onChange={(e) => patchProject(p.id, { folder: e.target.value })}
          />
          <input
            className="dset__pfield"
            value={p.tags.join(", ")}
            placeholder="tags, comma, separated"
            onChange={(e) =>
              patchProject(p.id, {
                tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean),
              })
            }
          />
        </div>
      ))}
    </div>
  );
}

// -------------------------------------------------------------- connectors
function ConnectorsTab() {
  const [list, setList] = useState<Connector[]>([]);
  const [teams, setTeams] = useState("");
  const [draft, setDraft] = useState<Record<string, { id: string; secret: string }>>({});
  const [msg, setMsg] = useState("");

  const load = () =>
    domainApi
      .connectors()
      .then((r) => { setList(r.connectors); setTeams(r.figma_teams); })
      .catch(() => setMsg("bridge offline — start server.py"));

  useEffect(() => { load(); }, []);

  const save = async (id: string) => {
    const d = draft[id];
    if (!d) return;
    const r = await domainApi.configureConnector(id, d.id, d.secret, id === "figma" ? teams : undefined);
    setMsg(r.ok ? "saved" : r.error ?? "could not save");
    setTimeout(() => setMsg(""), 2000);
    load();
  };

  const connect = async (id: string) => {
    const r = await domainApi.connectorAuthUrl(id);
    if (!r.ok || !r.url) { setMsg(r.error ?? "not configured"); return; }
    window.open(r.url, "_blank", "width=620,height=760");
    setTimeout(load, 4000);
  };

  return (
    <div className="dset">
      <p className="dset__hint">
        Register each app in its own developer console, paste the client ID and secret here,
        then hit Connect. Use the redirect URI shown on each card — it must match exactly.
      </p>
      {msg && <div className="dset__msg">{msg}</div>}

      {list.map((c) => (
        <div key={c.id} className="dset__conn" style={{ ["--pc" as string]: c.color }}>
          <div className="dset__connhead">
            <span className="dset__connicon">{c.icon}</span>
            <div>
              <div className="dset__connlabel">{c.label}</div>
              <div className="dset__connblurb">{c.blurb}</div>
            </div>
            <span className={"dset__pill" + (c.connected ? " dset__pill--on" : "")}>
              {c.connected ? c.account ?? "connected" : c.configured ? "configured" : "needs credentials"}
            </span>
          </div>

          <div className="dset__connbody">
            <input
              placeholder="Client ID"
              defaultValue=""
              onChange={(e) =>
                setDraft((d) => ({ ...d, [c.id]: { ...(d[c.id] ?? { id: "", secret: "" }), id: e.target.value } }))
              }
            />
            <input
              placeholder="Client secret"
              type="password"
              onChange={(e) =>
                setDraft((d) => ({ ...d, [c.id]: { ...(d[c.id] ?? { id: "", secret: "" }), secret: e.target.value } }))
              }
            />
            {c.id === "figma" && (
              <input
                placeholder="Figma team IDs (comma separated)"
                value={teams}
                onChange={(e) => setTeams(e.target.value)}
              />
            )}

            <div className="dset__connrow">
              <code className="dset__redirect" title="Register this exact redirect URI">
                {c.redirect_uri}
              </code>
              <a href={c.docs} target="_blank" rel="noreferrer">docs ↗</a>
            </div>

            <div className="dset__connbtns">
              <button onClick={() => save(c.id)}>Save credentials</button>
              <button className="dset__go" onClick={() => connect(c.id)} disabled={!c.configured}>
                {c.connected ? "Reconnect" : "Connect"}
              </button>
              {c.connected && (
                <button onClick={() => domainApi.disconnectConnector(c.id).then(load)}>
                  Disconnect
                </button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// -------------------------------------------------------------------- shell
export default function DomainSettings() {
  const [tab, setTab] = useState<Tab>("layout");

  return (
    <div className="ddocs">
      <div className="ddocs__tabs">
        {([["layout", "Layout"], ["projects", "Projects"], ["connectors", "Connectors"]] as [Tab, string][])
          .map(([id, label]) => (
            <button
              key={id}
              className={"ddocs__tab" + (tab === id ? " ddocs__tab--on" : "")}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
      </div>
      <div className="ddocs__body ddocs__body--scroll">
        {tab === "layout" && <LayoutTab />}
        {tab === "projects" && <ProjectsTab />}
        {tab === "connectors" && <ConnectorsTab />}
      </div>
    </div>
  );
}
