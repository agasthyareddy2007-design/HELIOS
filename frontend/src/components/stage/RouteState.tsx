"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

/**
 * RouteState — navigation reads as the same system changing state.
 *
 * On a pathname change the incoming view resolves from a slightly compressed,
 * lowered position while the shared atmosphere behind it stays continuous. The
 * environment never reloads, so moving between routes feels like HELIOS shifting
 * mode rather than a page swap.
 *
 * Constraints honoured deliberately:
 *  - total duration is ~340ms and the content is interactive immediately — the
 *    animation never gates input;
 *  - it is a transform/opacity animation only (compositor-friendly);
 *  - under `prefers-reduced-motion` nothing animates at all;
 *  - implemented with a CSS animation keyed off the pathname, so there is no
 *    per-frame JS and no layout thrash.
 */
export function RouteState({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const ref = useRef<HTMLDivElement>(null);
  const first = useRef(true);

  useEffect(() => {
    // Skip the very first paint: the landing entrance choreography owns that.
    if (first.current) {
      first.current = false;
      return;
    }
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    el.classList.remove("route-resolve");
    // force a reflow so the animation restarts on every navigation
    void el.offsetWidth;
    el.classList.add("route-resolve");
  }, [pathname]);

  return (
    <div
      ref={ref}
      className="route-state min-h-[100dvh] w-full"
      onAnimationEnd={(e) => {
        if (e.animationName === "helios-route-resolve") {
          ref.current?.classList.remove("route-resolve");
        }
      }}
    >
      {children}
    </div>
  );
}

export default RouteState;