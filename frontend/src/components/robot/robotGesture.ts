/**
 * HELIOS robot — occasional greeting.
 *
 * The robot should *occasionally notice the visitor*, not perform. So the gesture
 * is scheduled, not looped:
 *
 *   - it only becomes eligible once a real pointer has been seen (a visitor is
 *     present) and the pointer is reasonably near the figure;
 *   - it waits a randomised interval with a hard cooldown between gestures;
 *   - it never starts while the visitor is actively moving the pointer, so it
 *     cannot interrupt an interaction — it fires in the quiet moments;
 *   - it is skipped entirely under `prefers-reduced-motion`.
 *
 * The envelope is deliberately anatomical rather than cartoonish:
 *   raise (anticipation) → two unhurried oscillations → settle back to idle.
 */

export interface GestureConfig {
  /** Earliest possible first greeting, ms after mount. */
  firstDelayMs: number;
  /** Random interval range between eligibility checks, ms. */
  minIntervalMs: number;
  maxIntervalMs: number;
  /** Probability a given eligibility check actually fires. */
  chance: number;
  /** Total gesture length, ms. */
  durationMs: number;
}

export const GESTURE: GestureConfig = {
  firstDelayMs: 4200,
  minIntervalMs: 16000,
  maxIntervalMs: 34000,
  chance: 0.6,
  durationMs: 2600,
};

export interface GestureState {
  /** 0 = arm at rest, 1 = fully raised. */
  raise: number;
  /** Signed wave oscillation, −1…1, only meaningful while raised. */
  wave: number;
  /** True while a gesture is playing. */
  active: boolean;
}

interface Internal {
  nextAt: number;
  startedAt: number | null;
  state: GestureState;
}

export function createGestureRunner(now: number) {
  const g: Internal = {
    nextAt: now + GESTURE.firstDelayMs,
    startedAt: null,
    state: { raise: 0, wave: 0, active: false },
  };

  /** Smooth 0→1→0 envelope with a flat hold in the middle. */
  const envelope = (p: number): number => {
    if (p < 0.22) {
      const k = p / 0.22;
      return k * k * (3 - 2 * k); // ease-in-out raise
    }
    if (p > 0.74) {
      const k = (1 - p) / 0.26;
      return k * k * (3 - 2 * k); // ease-out lower
    }
    return 1;
  };

  /**
   * Advance the gesture. `visitorPresent` gates eligibility; `pointerIdleMs` is
   * how long since the visitor last moved, so we only greet in a lull.
   */
  function update(
    now: number,
    visitorPresent: boolean,
    pointerIdleMs: number,
    enabled: boolean,
  ): GestureState {
    const st = g.state;

    if (!enabled) {
      st.raise = 0;
      st.wave = 0;
      st.active = false;
      return st;
    }

    if (g.startedAt !== null) {
      const p = (now - g.startedAt) / GESTURE.durationMs;
      if (p >= 1) {
        g.startedAt = null;
        st.raise = 0;
        st.wave = 0;
        st.active = false;
        g.nextAt =
          now +
          GESTURE.minIntervalMs +
          Math.random() * (GESTURE.maxIntervalMs - GESTURE.minIntervalMs);
      } else {
        st.raise = envelope(p);
        // two unhurried oscillations across the held portion
        st.wave = Math.sin(p * Math.PI * 4.4) * st.raise;
        st.active = true;
      }
      return st;
    }

    // Eligible? Visitor present, in a lull, and past the scheduled time.
    if (now >= g.nextAt) {
      const lull = pointerIdleMs > 700;
      if (visitorPresent && lull && Math.random() < GESTURE.chance) {
        g.startedAt = now;
      } else {
        // re-check soon rather than burning the slot
        g.nextAt = now + 2500;
      }
    }
    return st;
  }

  return { update };
}
