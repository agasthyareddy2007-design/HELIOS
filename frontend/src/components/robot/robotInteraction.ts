"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

/**
 * Interaction primitives for the HELIOS robot.
 *
 * Pointer state lives in a ref that a DOM listener mutates directly — React
 * never re-renders on mouse movement. The render loop reads the ref each frame
 * and eases the rig toward it, so the robot follows attention without ever
 * snapping to the cursor.
 */

export interface PointerState {
  /** Normalised pointer inside the canvas: -1 (left/bottom) … +1 (right/top). */
  x: number;
  y: number;
  /** 0 at the robot anchor → 1 at the far edge of the canvas. */
  distance: number;
  /** performance.now() of the last real pointer movement. */
  lastMoveAt: number;
  /** A precise pointer (mouse/trackpad) has been seen at least once. */
  active: boolean;
}

/** Exponential smoothing that is independent of frame rate. */
export function damp(current: number, target: number, lambda: number, dt: number): number {
  return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

export function clamp(v: number, min: number, max: number): number {
  return v < min ? min : v > max ? max : v;
}

export const degToRad = (deg: number): number => (deg * Math.PI) / 180;

/** Robot anchor in normalised canvas space; proximity is measured from here. */
export interface Anchor {
  x: number;
  y: number;
}

/**
 * Tracks the pointer relative to `element`. Returns a stable ref — mutating it
 * costs nothing and never triggers a React render.
 */
export function usePointerTracker(
  element: HTMLElement | null,
  anchor: Anchor = { x: 0, y: 0 },
): React.RefObject<PointerState> {
  const state = useRef<PointerState>({
    x: 0,
    y: 0,
    distance: 1,
    lastMoveAt: 0,
    active: false,
  });

  // Depend on the coordinates, not the object: callers may pass an inline anchor
  // every render, but the numbers are stable so the listener is bound once.
  const { x: anchorX, y: anchorY } = anchor;

  useEffect(() => {
    if (!element || typeof window === "undefined") return;

    const onMove = (e: PointerEvent) => {
      // Coarse pointers (touch) must not drive the attention rig.
      if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;

      const r = element.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;

      const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
      // Screen Y grows downward; flip so +1 is up (matches look-up intent).
      const ny = -(((e.clientY - r.top) / r.height) * 2 - 1);

      const s = state.current;
      s.x = clamp(nx, -2, 2);
      s.y = clamp(ny, -2, 2);

      // Normalised radial distance from the robot, softly capped at 1.
      s.distance = clamp(Math.hypot(nx - anchorX, ny - anchorY) / 1.6, 0, 1);
      s.lastMoveAt = performance.now();
      s.active = true;
    };

    const onLeave = () => {
      // Cursor left the window: keep the last pose, let the idle relax handle it.
      state.current.distance = 1;
    };

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerout", onLeave, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerout", onLeave);
    };
  }, [element, anchorX, anchorY]);

  return state;
}

/**
 * Subscribes to a media query as an external store. `useSyncExternalStore` is
 * the right primitive here: matchMedia *is* an external source of truth, and it
 * avoids the effect-then-setState round trip (and its extra render).
 */
function useMediaQuery(query: string, serverValue: boolean): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    [query],
  );

  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  const getServerSnapshot = useCallback(() => serverValue, [serverValue]);

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Live `prefers-reduced-motion` state (SSR-safe, updates if the user changes it). */
export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)", false);
}

/** Motion limits and easing rates, tuned for a heavy, deliberate machine. */
export const RIG = {
  /** Head is the primary responder. */
  headYawDeg: 16,
  headPitchDeg: 11,
  /** Torso answers far less — it reads as mass. */
  torsoYawDeg: 5,
  torsoPitchDeg: 2.4,
  /** Head leads, torso lags slightly behind it. */
  headLambda: 3.4,
  torsoLambda: 1.7,
  /** Emissive/proximity easing. */
  glowLambda: 2.6,
  /** No movement for this long → drift back toward neutral. */
  idleRelaxMs: 2400,
  /** How fast the relax drift pulls the target to centre. */
  relaxLambda: 0.5,
} as const;
