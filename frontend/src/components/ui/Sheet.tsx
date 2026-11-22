"use client";

// A large modal window: backdrop, Esc to close, focus moved inside, scroll locked.
import { useEffect, useRef, type ReactNode } from "react";

export default function Sheet({ open, onClose, title, eyebrow, accent, children }: {
  open: boolean; onClose: () => void; title: ReactNode; eyebrow?: ReactNode; accent?: string; children: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    box.current?.focus();
    return () => {
      window.removeEventListener("keydown", key);
      document.body.style.overflow = overflow;
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="sh-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sh-box" role="dialog" aria-modal="true" tabIndex={-1} ref={box}
        style={accent ? ({ "--sh-accent": accent } as React.CSSProperties) : undefined}>
        <header className="sh-head">
          <div>
            {eyebrow && <div className="sh-eyebrow">{eyebrow}</div>}
            <h2 className="sh-title">{title}</h2>
          </div>
          <button type="button" className="sh-close" onClick={onClose} aria-label="Chiudi">✕</button>
        </header>
        <div className="sh-body">{children}</div>
      </div>
    </div>
  );
}
