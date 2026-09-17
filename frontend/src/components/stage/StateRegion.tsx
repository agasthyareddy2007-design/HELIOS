"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { useStage, type FocusTarget, type SectionState } from "@/components/stage/useStage";

/**
 * Primitives that let CONTENT drive the ENVIRONMENT.
 *
 * These are the wires that make HELIOS feel like one system rather than a page:
 * a section announces which state the system is in, and any signal-bearing
 * element can pull the atmosphere onto its own spectral identity when the
 * visitor attends to it. Both write to the stage store, which the WebGL layer
 * reads imperatively inside `useFrame` — so none of this costs a render.
 */

/**
 * Reflects the current attention state onto <html data-attn>, so CSS can
 * restructure the page around whatever the visitor is attending to. One
 * subscription, one attribute write per change — no per-frame work.
 */
export function AttentionReflector() {
  const focus = useStage((s) => s.focus);
  useEffect(() => {
    const el = document.documentElement;
    if (focus) el.dataset.attn = "1";
    else delete el.dataset.attn;
    return () => {
      delete el.dataset.attn;
    };
  }, [focus]);
  return null;
}

/**
 * Declares the narrative state of the environment while this block owns the
 * viewport. Uses an IntersectionObserver (no scroll handler), and the most
 * recently entered section wins.
 */
export function StateRegion({
  state,
  children,
  className = "",
}: {
  state: SectionState;
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          // Only claim the state once the block genuinely owns the view.
          if (e.isIntersecting && e.intersectionRatio > 0.35) {
            useStage.getState().setSection(state);
          }
        }
      },
      { threshold: [0, 0.35, 0.6, 1], rootMargin: "-15% 0px -25% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [state]);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}

/**
 * Broadcasts "the visitor is attending to this signal" on hover/focus, so the
 * atmosphere shifts onto that model's spectral identity. Pointer *and* keyboard,
 * and it always releases on leave/blur so the field settles back.
 */
export function SignalFocus({
  target,
  children,
  className = "",
  as = "div",
  focusable = false,
}: {
  target: FocusTarget;
  children: ReactNode;
  className?: string;
  as?: "div" | "li" | "span";
  /** Make the signal reachable by keyboard, so attention is not mouse-only. */
  focusable?: boolean;
}) {
  const Tag = as;
  const claim = () => useStage.getState().setFocus(target);
  const release = () => {
    // Only release if we are still the active signal, so rapid pointer moves
    // between signals never leave the field blank.
    if (useStage.getState().focus === target) useStage.getState().setFocus(null);
  };

  return (
    <Tag
      className={className}
      tabIndex={focusable ? 0 : undefined}
      aria-label={focusable && target ? `Highlight ${target.toUpperCase()} signal` : undefined}
      onPointerEnter={claim}
      onPointerLeave={release}
      onFocus={claim}
      onBlur={release}
    >
      {children}
    </Tag>
  );
}
