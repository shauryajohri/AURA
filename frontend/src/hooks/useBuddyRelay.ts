import { useEffect, useRef } from "react";
import type { AuraState, ChatTurn, ConnStatus, Presence } from "../types";

/**
 * Feeds the desktop buddy (its own Electron window) from this window's
 * socket, and carries what you type into the buddy back through it. One
 * socket means the brain sees one client and this transcript keeps every
 * exchange, whichever body you talked to. A no-op outside Electron.
 */
export function useBuddyRelay(
  status: ConnStatus,
  auraState: AuraState,
  presence: Presence,
  turns: ChatTurn[],
  send: (text: string) => void,
) {
  const bridge = window.aura?.buddy;

  useEffect(() => { bridge?.relay({ kind: "status", status }); }, [bridge, status]);
  useEffect(() => { bridge?.relay({ kind: "state", state: auraState }); }, [bridge, auraState]);
  useEffect(() => { bridge?.relay({ kind: "presence", presence }); }, [bridge, presence]);

  // Only fresh speech reaches the buddy: a reply we watched stream in, or a
  // push. History loaded from a saved chat has neither, so reopening an old
  // conversation doesn't make the buddy recite its last line. The finished
  // text is sent, not the raw stream, which can still carry backend context.
  const streamed = useRef(new Set<string>());
  const said = useRef(new Set<string>());
  useEffect(() => {
    const last = turns[turns.length - 1];
    if (!bridge || !last || last.role !== "aura") return;
    if (last.streaming) { streamed.current.add(last.id); return; }
    if (said.current.has(last.id)) return;
    if (!streamed.current.has(last.id) && !last.source) return;
    said.current.add(last.id);
    bridge.relay({ kind: "say", id: last.id, text: last.text, source: last.source });
  }, [bridge, turns]);

  useEffect(() => bridge?.onChat((text) => send(text)), [bridge, send]);
}
