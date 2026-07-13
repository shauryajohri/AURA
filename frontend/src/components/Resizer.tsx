import { useCallback, useEffect, useRef } from "react";

interface Props {
  onResize: (nextChatWidth: number) => void;
  min?: number;
  max?: number;
}

/**
 * Vertical drag handle between the center stage and the chat panel.
 * Reports the desired chat-panel width (measured from the right edge).
 */
export default function Resizer({ onResize, min = 340, max = 760 }: Props) {
  const draggingRef = useRef(false);

  const onMove = useCallback(
    (e: MouseEvent) => {
      if (!draggingRef.current) return;
      // 16px is the app's right padding.
      const width = Math.min(max, Math.max(min, window.innerWidth - e.clientX - 16));
      onResize(width);
    },
    [onResize, min, max]
  );

  const stop = useCallback(() => {
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", stop);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", stop);
    };
  }, [onMove, stop]);

  const start = () => {
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  return <div className="resizer" onMouseDown={start} title="Drag to resize chat" />;
}
