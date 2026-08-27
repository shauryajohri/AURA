import { useCallback, useEffect, useState } from "react";
import { api, Chat, ChatMessage, Room } from "../api";
import { renderMarkdown } from "../components/Markdown";

// ============================================================================
// Chats — rooms on the left, the open chat on the right.
//
// A chat is a boundary you can name. A ROOM is what that boundary is about,
// and it is the room that tells AURA how to behave: "teach, don't just
// answer" belongs to Japanese Study, not to any single conversation inside
// it. So rooms hold chats, and every chat inherits its room's brief.
//
// Entering a room resumes its most recent chat rather than being a
// conversation of its own — messages always live in a chat.
// ============================================================================

const ICONS = ["◈", "⌥", "あ", "❋", "◆", "✦", "❖", "◉", "▣", "⚗", "♪", "⌘"];
const ACCENTS = ["#6C6BFF", "#38E1FF", "#FF6BA8", "#9B8CFF", "#4ADE80", "#FFB86B", "#FF6B6B"];
const BLANK: Partial<Room> = {
  name: "", icon: "◈", accent: "#6C6BFF", topic: "",
  keywords: [], system_hint: "", auto_switch: true,
};

interface Props {
  /** Send a message on the shared socket — one conversation, two places. */
  onSend?: (text: string) => void;
}

export default function ChatsPage({ onSend }: Props) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeRoom, setActiveRoom] = useState<number | null>(null);
  const [activeChat, setActiveChat] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [editing, setEditing] = useState<Partial<Room> | null>(null);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([api.getRooms(), api.getChats()]);
      setRooms(r.rooms);
      setActiveRoom(r.active);
      setChats(c.chats);
      setActiveChat(c.active);
      setOffline(false);
    } catch {
      setOffline(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Whichever chat is active, show its transcript.
  useEffect(() => {
    if (!activeChat) { setMessages([]); return; }
    let alive = true;
    api.getChatMessages(activeChat)
      .then((m) => { if (alive) setMessages(m); })
      .catch(() => { if (alive) setMessages([]); });
    return () => { alive = false; };
  }, [activeChat]);

  const enterRoom = async (id: number) => {
    try {
      const r = await api.enterRoom(id);
      if (!r.ok) return;
      setActiveRoom(id);
      setActiveChat(r.active);
      setMessages(r.messages || []);
      refresh();
    } catch { setOffline(true); }
  };

  const openChat = async (id: number) => {
    try {
      const r = await api.openChat(id);
      if (!r.ok) return;
      setActiveChat(r.active);
      setMessages(r.messages || []);
      const filed = rooms.find((rm) => chatsOf(rm.id).some((c) => c.id === id));
      setActiveRoom(filed ? filed.id : null);
    } catch { setOffline(true); }
  };

  /** A new chat, filed into the room you made it in. */
  const newChatIn = async (roomId: number | null) => {
    try {
      const r = await api.newChat();
      if (roomId) await api.setChatRoom(r.id, roomId);
      await api.openChat(r.id);
      setActiveChat(r.id);
      setActiveRoom(roomId);
      setMessages([]);
      refresh();
    } catch { setOffline(true); }
  };

  const commitRoom = async () => {
    if (!editing) return;
    const name = (editing.name || "").trim();
    if (!name) { setError("Give the room a name."); return; }
    const patch = {
      ...editing,
      name,
      keywords: Array.isArray(editing.keywords)
        ? editing.keywords
        : String(editing.keywords || "").split(",").map((k) => k.trim()).filter(Boolean),
    };
    try {
      if (editing.id) await api.updateRoom(editing.id, patch);
      else {
        const r = await api.newRoom(patch);
        if (!r.ok) { setError(r.error || "couldn't create that room"); return; }
        if (r.id) await enterRoom(r.id);
      }
      setEditing(null);
      setError("");
      refresh();
    } catch { setOffline(true); }
  };

  const removeRoom = async (id: number) => {
    try {
      await api.deleteRoom(id);
      setEditing(null);
      refresh();
    } catch { setOffline(true); }
  };

  // Chats are filed by room_id server-side; the list endpoint doesn't carry
  // it, so the room's own chat list is the source of truth for grouping.
  const [byRoom, setByRoom] = useState<Record<number, Chat[]>>({});
  useEffect(() => {
    let alive = true;
    Promise.all(rooms.map((r) => api.getRoomChats(r.id).then((cs) => [r.id, cs] as const)))
      .then((pairs) => { if (alive) setByRoom(Object.fromEntries(pairs)); })
      .catch(() => {});
    return () => { alive = false; };
  }, [rooms, chats]);

  const chatsOf = (roomId: number) => byRoom[roomId] || [];
  const filedIds = new Set(Object.values(byRoom).flat().map((c) => c.id));
  const unfiled = chats.filter((c) => !filedIds.has(c.id));

  const room = rooms.find((r) => r.id === activeRoom) || null;
  const chat = chats.find((c) => c.id === activeChat) || null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || !onSend) return;
    onSend(input);
    setInput("");
  };

  if (loading) return <div className="chatspage"><p className="chatspage__note">Loading rooms…</p></div>;

  return (
    <div className="chatspage">
      <header className="chatspage__head">
        <h2>Chats</h2>
        <p>
          Rooms say what a conversation is about — every chat inside one
          inherits its brief, and AURA moves you when the subject changes.
        </p>
      </header>

      {offline && <p className="chatspage__note">Brain offline — start server.py.</p>}

      <div className="chatspage__body">
        <aside className="chatspage__rail">
          <div className="crail">
            <div className="crail__head">
              <span className="crail__title">Rooms</span>
              <button className="crail__add" title="New room"
                      onClick={() => { setError(""); setEditing({ ...BLANK }); }}>+</button>
            </div>

            <div className="crail__list">
              {rooms.map((r) => (
                <div key={r.id} className="crail__group">
                  <button
                    className={"crail__item" + (r.id === activeRoom ? " crail__item--on" : "")}
                    style={{ ["--chan" as string]: r.accent }}
                    onClick={() => enterRoom(r.id)}
                    onDoubleClick={() => { setError(""); setEditing({ ...r }); }}
                    title={r.topic || r.name}
                  >
                    <span className="crail__icon">{r.icon}</span>
                    <span className="crail__meta">
                      <span className="crail__name">{r.name}</span>
                      <span className="crail__topic">{r.topic || "—"}</span>
                    </span>
                    {r.chats > 0 && <span className="crail__count">{r.chats}</span>}
                    <span className="crail__addchat" role="button" tabIndex={-1}
                          title={`New chat in ${r.name}`}
                          onClick={(e) => { e.stopPropagation(); newChatIn(r.id); }}>+</span>
                    <span className="crail__edit" role="button" tabIndex={-1} title="Edit room"
                          onClick={(e) => { e.stopPropagation(); setError(""); setEditing({ ...r }); }}>⋯</span>
                  </button>

                  {chatsOf(r.id).map((c) => (
                    <button
                      key={c.id}
                      className={"crail__item crail__item--chat" + (c.id === activeChat ? " crail__item--on" : "")}
                      style={{ ["--chan" as string]: r.accent }}
                      onClick={() => openChat(c.id)}
                      title={c.title}
                    >
                      <span className="crail__icon">◆</span>
                      <span className="crail__meta"><span className="crail__name">{c.title}</span></span>
                      {c.message_count > 0 && <span className="crail__count">{c.message_count}</span>}
                    </button>
                  ))}
                </div>
              ))}

              {unfiled.length > 0 && (
                <div className="crail__group">
                  <div className="crail__title crail__title--sub">Unfiled</div>
                  {unfiled.map((c) => (
                    <button
                      key={c.id}
                      className={"crail__item crail__item--chat" + (c.id === activeChat ? " crail__item--on" : "")}
                      onClick={() => openChat(c.id)}
                      title={c.title}
                    >
                      <span className="crail__icon">◆</span>
                      <span className="crail__meta"><span className="crail__name">{c.title}</span></span>
                      {c.message_count > 0 && <span className="crail__count">{c.message_count}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>

        <section className="chatspage__room"
                 style={room ? ({ ["--room" as string]: room.accent }) : undefined}>
          <div className="chatspage__roomhead">
            <span className="chatspage__roomicon">{room?.icon ?? "◆"}</span>
            <div className="chatspage__roomtitles">
              {room && <p className="chatspage__crumb"><b>{room.name}</b> / chat</p>}
              <h3>{chat?.title ?? (room ? room.name : "No chat open")}</h3>
              <p>{room?.topic || "Pick a room on the left, or start a chat in one."}</p>
            </div>
            {chat && (
              <span className="chatspage__roomcount">
                {chat.message_count} {chat.message_count === 1 ? "message" : "messages"}
              </span>
            )}
          </div>

          <div className="chatspage__log">
            {messages.length === 0 && (
              <p className="chatspage__note">
                {chat ? "Nothing said here yet." : "No chat open."}
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={"bubble bubble--" + (m.role === "user" ? "user" : "aura")}>
                <span className="bubble__who">{m.role === "user" ? "You" : "AURA"}</span>
                <div className="bubble__text">{renderMarkdown(m.text)}</div>
              </div>
            ))}
          </div>

          {onSend && (
            <form className="composer composer--page" onSubmit={submit}>
              <div className="composer__field">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={chat ? `Message ${chat.title}…` : "Pick a chat first…"}
                  disabled={!chat}
                />
              </div>
              <button type="submit" className="composer__send" disabled={!chat || !input.trim()}>➤</button>
            </form>
          )}
        </section>
      </div>

      {editing && (
        <div className="crail__modal" onClick={(e) => { if (e.target === e.currentTarget) setEditing(null); }}>
          <div className="crail__panel">
            <h3>{editing.id ? "Edit room" : "New room"}</h3>

            <label className="crail__f">
              <span>Name</span>
              <input value={editing.name || ""} autoFocus placeholder="Japanese Study"
                     onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </label>

            <label className="crail__f">
              <span>Topic</span>
              <input value={editing.topic || ""} placeholder="What this room is for — AURA reads this."
                     onChange={(e) => setEditing({ ...editing, topic: e.target.value })} />
            </label>

            <div className="crail__f">
              <span>Icon</span>
              <div className="crail__picks">
                {ICONS.map((i) => (
                  <button key={i} className={"crail__pick" + (editing.icon === i ? " crail__pick--on" : "")}
                          onClick={() => setEditing({ ...editing, icon: i })}>{i}</button>
                ))}
              </div>
            </div>

            <div className="crail__f">
              <span>Colour</span>
              <div className="crail__picks">
                {ACCENTS.map((a) => (
                  <button key={a} className={"crail__swatch" + (editing.accent === a ? " crail__swatch--on" : "")}
                          style={{ background: a }} onClick={() => setEditing({ ...editing, accent: a })} />
                ))}
              </div>
            </div>

            <label className="crail__f">
              <span>Keywords</span>
              <input
                value={Array.isArray(editing.keywords) ? editing.keywords.join(", ") : (editing.keywords || "")}
                placeholder="kanji, grammar, jlpt — what pulls AURA into this room"
                onChange={(e) => setEditing({ ...editing, keywords: e.target.value as never })} />
            </label>

            <label className="crail__f">
              <span>House style</span>
              <input value={editing.system_hint || ""} placeholder="Optional — how she should talk in here."
                     onChange={(e) => setEditing({ ...editing, system_hint: e.target.value })} />
            </label>

            <label className="crail__toggle">
              <button className={"san-toggle" + (editing.auto_switch ? " san-toggle--on" : "")}
                      onClick={() => setEditing({ ...editing, auto_switch: !editing.auto_switch })}>
                <span className="san-toggle__knob" />
              </button>
              <span>
                Let AURA move us here on her own
                <em>She'll say so when she does.</em>
              </span>
            </label>

            <footer className="crail__foot">
              {editing.id
                ? <button className="crail__danger" title="The room goes; its chats stay, unfiled"
                          onClick={() => removeRoom(editing.id!)}>Delete room</button>
                : <span />}
              <div className="crail__spacer" />
              <button className="crail__ghost" onClick={() => setEditing(null)}>Cancel</button>
              <button className="crail__save" onClick={commitRoom}>
                {editing.id ? "Save" : "Create & enter"}
              </button>
            </footer>
            {error && <p className="crail__err">{error}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
