"use client";

import { useEffect, useRef } from "react";

/**
 * CursorLight — one soft light that trails the pointer across the whole site.
 *
 * Purpose: make the atmosphere feel like a physical medium that responds to
 * presence. It is not a custom cursor (the real cursor is untouched, so
 * usability and accessibility are unaffected).
 *
 * Implementation notes:
 *  - position is written to `transform` inside a single rAF loop, with inertial
 *    smoothing, so pointer movement never causes a React render;
 *  - the element is inert (`pointer-events: none`, aria-hidden);
 *  - fine-pointer only, and CSS removes it entirely under reduced motion or on
 *    touch/coarse pointers, so no work is done where it isn't wanted.
 */
export function CursorLight() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const fine = window.matchMedia("(pointer: fine)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || reduce) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let x = targetX;
    let y = targetY;
    let raf = 0;
    let active = false;

    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      targetX = e.clientX;
      targetY = e.clientY;
      if (!active) {
        active = true;
        el.dataset.active = "true";
      }
    };
    const onLeave = () => {
      active = false;
      el.dataset.active = "false";
    };

    const tick = () => {
      // inertial follow — the light lags the pointer slightly, which reads as
      // a physical medium rather than a stuck-on overlay
      x += (targetX - x) * 0.085;
      y += (targetY - y) * 0.085;
      el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0)`;
      raf = requestAnimationFrame(tick);
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    raf = requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <div ref={ref} aria-hidden className="helios-cursor" data-active="false" />;
}

export default CursorLight;
