import { useEffect, useRef, useState } from "react";
import { api, type Chat } from "../api";

/**
 * The chat history drawer.
 *
 * Opening a chat here is not just a UI change — it calls /activate, which
 * moves AURA's CONTEXT to that conversation. The next thing she reads is that
 * chat's history, so picking up a thread from last week actually works
 * instead of leaving her talking about whatever was open before.
 *
 * Titles are auto-derived from the first message and editable in place, so
 * the list stays readable without anyone having to name anything by hand.
 */

interface Props {
  open: boolean;
  onClose: () => void;
  /** Replace the visible transcript with the opened chat's messages. */
  onOpenChat: (messages: { role: string; text: string; created_at: string | null }[]) => void;
  /** Clear the transcript for a brand-new chat. */
  onNewChat: () => void;
}

function whenLabel(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const mins = Math.floor((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function ChatHistory({ open, onClose, onOpenChat, onNewChat }: Props) {
  const [chats, setChats] = useState<Chat[] | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = () => {
    api.getChats()
      .then((r) => { setChats(r.chats); setActive(r.active); setError(""); })
      .catch(() => setError("Brain offline — start server.py to see your chats."));
  };

  useEffect(() => { if (open) load(); }, [open]);
  useEffect(() => { if (editing !== null) inputRef.current?.select(); }, [editing]);

  if (!open) return null;

  const openChat = async (id: number) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.openChat(id);
      if (r.ok) {
        setActive(r.active);
        onOpenChat(r.messages || []);
        onClose();
      } else {
        setError(r.error || "Could not open that chat.");
      }
    } catch {
      setError("Could not open that chat.");
    } finally {
      setBusy(false);
    }
  };

  const startNew = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.newChat();
      setChats(r.chats);
      setActive(r.id);
      onNewChat();
      onClose();
    } catch {
      setError("Could not start a new chat.");
    } finally {
      setBusy(false);
    }
  };

  const commitRename = async (id: number) => {
    const title = editText.trim();
    setEditing(null);
    if (!title) return;             // blank keeps the existing name
    try {
      const r = await api.renameChat(id, title);
      if (r.ok) setChats(r.chats);
    } catch {
      setError("Rename failed.");
    }
  };

  const remove = async (id: number) => {
    try {
      const r = await api.deleteChat(id);
      setChats(r.chats);
      setActive(r.active);
      // Deleting the chat you're looking at leaves the transcript stale.
      if (id === active) onNewChat();
    } catch {
      setError("Delete failed.");
    }
  };

  return (
    <div className="chist" role="dialog" aria-label="Chat history">
      <div className="chist__head">
        <span className="chist__title">Chats</span>
        <button className="chist__new" onClick={startNew} disabled={busy}>+ New chat</button>
        <button className="chist__close" onClick={onClose} title="Close">✕</button>
      </div>

      {error && <p className="chist__err">{error}</p>}
      {!chats && !error && <p className="chist__note">Loading…</p>}
      {chats?.length === 0 && <p className="chist__note">No saved chats yet.</p>}

      <div className="chist__list">
        {chats?.map((c) => (
          <div key={c.id} className={"chist__row" + (c.id === active ? " chist__row--on" : "")}>
            {editing === c.id ? (
              <input
                ref={inputRef}
                className="chist__edit"
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                onBlur={() => commitRename(c.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename(c.id);
                  if (e.key === "Escape") setEditing(null);
                }}
                autoFocus
              />
            ) : (
              <button
                className="chist__open"
                onClick={() => openChat(c.id)}
                disabled={busy}
                title="Open this chat — AURA picks up its context"
              >
                <span className="chist__name">{c.title}</span>
                <span className="chist__meta">
                  {c.message_count} message{c.message_count === 1 ? "" : "s"}
                  {whenLabel(c.updated_at) && ` · ${whenLabel(c.updated_at)}`}
                </span>
              </button>
            )}

            <button
              className="chist__act"
              onClick={() => { setEditing(c.id); setEditText(c.title); }}
              title="Rename"
              aria-label={`Rename ${c.title}`}
            >
              ✎
            </button>
            <button
              className="chist__act chist__act--del"
              onClick={() => remove(c.id)}
              title="Delete this chat"
              aria-label={`Delete ${c.title}`}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
