import React, { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";

/**
 * PortalMenu — renders an action dropdown into document.body so it can never be
 * clipped by parent `overflow-hidden` containers (table cards, sidebars, etc).
 *
 * Anchored to a trigger element via `anchorRef`; recomputes position on open and
 * on window scroll/resize. Closes on outside click or Escape.
 *
 * Usage:
 *   const triggerRef = useRef(null);
 *   const [open, setOpen] = useState(false);
 *   <button ref={triggerRef} onClick={() => setOpen(o => !o)}>...</button>
 *   <PortalMenu open={open} anchorRef={triggerRef} onClose={() => setOpen(false)}>
 *     <button>Item 1</button>
 *     <button>Item 2</button>
 *   </PortalMenu>
 */
export default function PortalMenu({
  open,
  anchorRef,
  onClose,
  children,
  align = "right",        // "right" | "left"  — which edge of the trigger to align to
  width = 168,            // menu width in px
  offset = 6,             // gap between trigger and menu
  className = "",
}) {
  const [pos, setPos] = useState({ top: 0, left: 0 });

  const compute = useCallback(() => {
    const el = anchorRef?.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const top = r.bottom + offset;
    const left = align === "right" ? r.right - width : r.left;
    // Clamp to viewport
    const maxLeft = window.innerWidth - width - 8;
    setPos({ top, left: Math.max(8, Math.min(left, maxLeft)) });
  }, [anchorRef, align, width, offset]);

  useEffect(() => {
    if (!open) return;
    compute();
    const onScroll = () => compute();
    const onResize = () => compute();
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    const onDocClick = (e) => {
      // Ignore clicks on the trigger itself; let it toggle.
      if (anchorRef?.current?.contains(e.target)) return;
      // Ignore clicks inside the menu (caller handles those via item onClicks).
      if (e.target.closest?.("[data-portal-menu]")) return;
      onClose?.();
    };
    window.addEventListener("scroll", onScroll, true);   // capture-phase: catches inner scrolls too
    window.addEventListener("resize", onResize);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDocClick);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDocClick);
    };
  }, [open, compute, onClose, anchorRef]);

  if (!open) return null;

  return createPortal(
    <div
      data-portal-menu
      className={`fixed z-[1000] bg-white dark:bg-[#2A2929] border border-gray-100 dark:border-white/10 rounded-xl shadow-[0_8px_28px_rgba(0,0,0,0.16)] py-1 ${className}`}
      style={{ top: pos.top, left: pos.left, width }}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </div>,
    document.body
  );
}
