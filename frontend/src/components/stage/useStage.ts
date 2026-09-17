"use client";

import { create } from "zustand";

/**
 * Shared state for the site-wide HELIOS stage.
 *
 * The stage reads this imperatively inside `useFrame` (never as React state), so
 * the forecast application can drive the environment — model trust weights tint
 * the atmosphere, model disagreement raises its turbulence — without causing a
 * single re-render per frame.
 */
export type StageMode = "cinematic" | "subject" | "instrument";

/**
 * Which signal the visitor is attending to.
 *  - `gfs | ifs | icon`      — a Level 1 NWP model input
 *  - `kernel | xgboost | mlp` — a Level 2 blending candidate
 *  - `helios`                 — the resolved, published output
 */
export type FocusTarget =
  | "gfs"
  | "ifs"
  | "icon"
  | "kernel"
  | "xgboost"
  | "mlp"
  | "helios"
  | null;

/**
 * The narrative state the visitor is currently inside. The environment shifts
 * between these, so scrolling reads as the system moving through its own
 * process rather than a page scrolling past.
 */
export type SectionState =
  | "arrival"
  | "divergence"
  | "signals"
  | "reasoning"
  | "verification"
  | "resolution";

export interface StageState {
  /**
   * Material intensity follows what the page is about:
   *   cinematic  — the environment is the subject (landing)
   *   subject    — something else is the subject (the contact robot), so the
   *                environment recedes and stops competing for attention
   *   instrument — dense data is the subject (forecast), so it goes quietest
   */
  mode: StageMode;
  /** Live per-model trust weights (0..1), or null in ambient mode. */
  weights: { gfs: number; ifs: number; icon: number } | null;
  /** 0..1 atmospheric turbulence, derived from model disagreement. */
  turbulence: number;
  /** 0..1 page scroll progress. */
  scroll: number;
  /** The signal the visitor is attending to, or null. */
  focus: FocusTarget;
  /** Current narrative state of the environment. */
  section: SectionState;

  setMode: (m: StageMode) => void;
  setFocus: (f: FocusTarget) => void;
  setSection: (s: SectionState) => void;
  setLive: (weights: StageState["weights"], disagreementC: number | null) => void;
  setScroll: (v: number) => void;
  clearLive: () => void;
}

/** ~3.5 °C spread reads as fully turbulent; gentle curve keeps it subtle. */
function normaliseDisagreement(c: number | null): number {
  if (c === null || !Number.isFinite(c) || c <= 0) return 0.2;
  return Math.min(1, c / 3.5);
}

export const useStage = create<StageState>((set) => ({
  mode: "cinematic",
  weights: null,
  turbulence: 0.25,
  scroll: 0,
  focus: null,
  section: "arrival",

  setMode: (mode) => set({ mode }),
  setLive: (weights, disagreementC) =>
    set({ weights, turbulence: normaliseDisagreement(disagreementC) }),
  setScroll: (scroll) => set({ scroll }),
  setFocus: (focus) => set({ focus }),
  setSection: (section) => set({ section }),
  clearLive: () => set({ weights: null, turbulence: 0.25 }),
}));
