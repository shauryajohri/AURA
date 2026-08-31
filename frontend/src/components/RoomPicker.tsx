import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type Chat, type ChatMessage, type Room } from "../api";

/**
 * The room selector that lives in the Home dock.
 *
 * A room carries a BRIEF ("teach, don't just answer" / "stay technical and
 * concrete") that a chat title can't. Picking a room here calls /enter, which
 * moves AURA's context into that room's most recent chat and resets her
 * in-RAM history — so the next answer is shaped by that room, not whatever
 * was open before. Expanding a room lets you jump straight to one of its
 * chats (Coding → DSA) or start a fresh one there.
 *
 * The popover is portalled to <body> and positioned with fixed coords: the
 * dock clips its own overflow (rounded glass), so an in-flow popover taller
 * than the short default dock would lose its header off the top edge.
 */

interface Props {
  /** Replace the dock transcript with the entered room/chat's messages. */
  onLoad: (messages: ChatMessage[]) => void;
  /** Empty the dock transcript (a brand-new chat). */
  onClear: () => void;
}

interface PopPos {
  left: number;
  /** Distance from the viewport bottom to the popover's bottom edge. */
  bottom: number;
  /** Hard ceiling so the popover never runs past the top of the screen. */
  maxHeight: number;
}

export default function RoomPicker({ onLoad, onClear }: Props) {
  const [open, setOpen] = useState(false);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [chatsByRoom, setChatsByRoom] = useState<Record<number, Chat[]>>({});
  const [activeRoom, setActiveRoom] = useState<number | null>(null);
  const [activeChat, setActiveChat] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pos, setPos] = useState<PopPos | null>(null);
  const pillRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    try {
      const [r, c] = await Promise.all([api.getRooms(), api.getChats()]);
      setRooms(r.rooms);
      setActiveRoom(r.active);
      setActiveChat(c.active);
      const pairs = await Promise.all(
        r.rooms.map((rm) => api.getRoomChats(rm.id).then((cs) => [rm.id, cs] as const)),
      );
      setChatsByRoom(Object.fromEntries(pairs));
      setErr("");
    } catch {
      setErr("Brain offline — start server.py.");
    }
  };

  // Load once so the pill shows the current room even while closed.
  useEffect(() => { load(); }, []);
  useEffect(() => { if (open) load(); }, [open]);

  // Anchor the popover above the pill. Recomputed on open and whenever the
  // window resizes, so it tracks the dock as it's dragged taller/shorter.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const el = pillRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setPos({
        left: Math.max(8, r.left),
        bottom: window.innerHeight - r.top + 8,
        maxHeight: Math.max(160, r.top - 16),
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  // Click-away — the popover lives in a portal, so check both the pill and
  // the popover before closing.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (pillRef.current?.contains(t) || popRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const enterRoom = async (id: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.enterRoom(id);
      if (r.ok) {
        setActiveRoom(id);
        setActiveChat(r.active);
        setExpanded(id);
        onLoad(r.messages || []);
        load();
      } else {
        setErr(r.error || "Couldn't enter that room.");
      }
    } catch {
      setErr("Couldn't enter that room.");
    } finally {
      setBusy(false);
    }
  };

  const openChat = async (id: number, roomId: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.openChat(id);
      if (r.ok) {
        setActiveChat(r.active);
        setActiveRoom(roomId);
        onLoad(r.messages || []);
        setOpen(false);
      } else {
        setErr(r.error || "Couldn't open that chat.");
      }
    } catch {
      setErr("Couldn't open that chat.");
    } finally {
      setBusy(false);
    }
  };

  const newChatIn = async (roomId: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.newChat();
      await api.setChatRoom(r.id, roomId);
      await api.openChat(r.id);
      setActiveChat(r.id);
      setActiveRoom(roomId);
      onClear();
      setOpen(false);
      load();
    } catch {
      setErr("Couldn't start a chat.");
    } finally {
      setBusy(false);
    }
  };

  const room = rooms.find((r) => r.id === activeRoom) || null;

  const popover = open && pos && (
    <div
      className="roompick__pop"
      role="dialog"
      aria-label="Rooms"
      ref={popRef}
      style={{ left: pos.left, bottom: pos.bottom, maxHeight: pos.maxHeight }}
    >
      <div className="roompick__head">
        <span className="roompick__htitle">Work in…</span>
        <button type="button" className="roompick__x" onClick={() => setOpen(false)} title="Close">✕</button>
      </div>

      {err && <p className="roompick__err">{err}</p>}
      {!err && rooms.length === 0 && <p className="roompick__note">No rooms yet — make one in Chats.</p>}

      <div className="roompick__list">
        {rooms.map((r) => (
          <div key={r.id} className="roompick__group">
            <button
              type="button"
              className={"roompick__room" + (r.id === activeRoom ? " roompick__room--on" : "")}
              style={{ ["--chan" as string]: r.accent } as React.CSSProperties}
              onClick={() => enterRoom(r.id)}
              disabled={busy}
              title={r.topic || r.name}
            >
              <span className="roompick__icon">{r.icon}</span>
              <span className="roompick__meta">
                <span className="roompick__name">{r.name}</span>
                <span className="roompick__topic">{r.topic || "—"}</span>
              </span>
              <span
                className="roompick__exp"
                role="button"
                tabIndex={-1}
                title={expanded === r.id ? "Hide chats" : "Show chats"}
                onClick={(e) => { e.stopPropagation(); setExpanded(expanded === r.id ? null : r.id); }}
              >
                {expanded === r.id ? "▾" : (r.chats || 0)}
              </span>
            </button>

            {expanded === r.id && (
              <div className="roompick__chats">
                {(chatsByRoom[r.id] || []).map((c) => (
                  <button
                    type="button"
                    key={c.id}
                    className={"roompick__chat" + (c.id === activeChat ? " roompick__chat--on" : "")}
                    onClick={() => openChat(c.id, r.id)}
                    disabled={busy}
                    title={c.title}
                  >
                    <span className="roompick__cdot">◆</span>
                    <span className="roompick__cname">{c.title}</span>
                    {c.message_count > 0 && <span className="roompick__ccount">{c.message_count}</span>}
                  </button>
                ))}
                <button
                  type="button"
                  className="roompick__newchat"
                  onClick={() => newChatIn(r.id)}
                  disabled={busy}
                >
                  + New chat in {r.name}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="roompick__hint">
        Picking a room loads its brief — AURA answers in that room's style until you switch.
      </p>
    </div>
  );

  return (
    <div className="roompick">
      <button
        type="button"
        ref={pillRef}
        className={"roompick__pill" + (open ? " roompick__pill--on" : "")}
        style={room ? ({ ["--chan" as string]: room.accent } as React.CSSProperties) : undefined}
        onClick={() => setOpen((v) => !v)}
        title="Choose the room AURA works in — it loads that room's brief"
        aria-expanded={open}
      >
        <span className="roompick__picon">{room?.icon ?? "◇"}</span>
        <span className="roompick__pname">{room?.name ?? "No room"}</span>
        <span className="roompick__pcy">{open ? "▾" : "▸"}</span>
      </button>

      {popover && createPortal(popover, document.body)}
    </div>
  );
}
