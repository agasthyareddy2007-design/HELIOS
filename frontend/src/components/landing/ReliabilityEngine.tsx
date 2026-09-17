"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { SignalFocus } from "@/components/stage/StateRegion";

/**
 * ReliabilityEngine — conditional reliability, shown as a process.
 *
 * The section used to *state* that HELIOS learns when to trust each model. This
 * shows it: the context cycles through real forecast conditions (coast / inland,
 * hour of day, lead time) and the three model weights redistribute accordingly,
 * with the blend bar recomputing live.
 *
 * HONESTY: these weights are an ILLUSTRATION of the mechanism, not live model
 * inference — the label says so. The real learned weights are served by the API
 * and shown on /forecast. Nothing here claims to be a HELIOS prediction.
 *
 * Implementation: one interval advances a discrete context index (no per-frame
 * React state); Motion springs interpolate the bars, so the redistribution reads
 * as physical settling rather than a CSS width jump.
 */

type Weights = { gfs: number; ifs: number; icon: number };

interface Scenario {
  context: string;
  detail: string;
  weights: Weights;
}

/**
 * Illustrative contexts. The pattern reflects the *kind* of conditioning HELIOS
 * learns (location regime, diurnal phase, forecast lead) without asserting any
 * specific verified skill number.
 */
const SCENARIOS: Scenario[] = [
  {
    context: "Coastal · 06 UTC · +24 h",
    detail: "Short lead, land–sea breeze regime.",
    weights: { gfs: 0.28, ifs: 0.48, icon: 0.24 },
  },
  {
    context: "Inland plateau · 12 UTC · +48 h",
    detail: "Daytime convection, medium lead.",
    weights: { gfs: 0.34, ifs: 0.30, icon: 0.36 },
  },
  {
    context: "Himalayan foothills · 00 UTC · +72 h",
    detail: "Complex terrain, longer lead.",
    weights: { gfs: 0.22, ifs: 0.52, icon: 0.26 },
  },
  {
    context: "Central India · 18 UTC · +12 h",
    detail: "Evening cooling, very short lead.",
    weights: { gfs: 0.44, ifs: 0.28, icon: 0.28 },
  },
];

const MODEL_META = [
  { id: "gfs" as const, name: "GFS", color: "var(--color-gfs)" },
  { id: "ifs" as const, name: "IFS", color: "var(--color-ifs)" },
  { id: "icon" as const, name: "ICON", color: "var(--color-icon)" },
];

export function ReliabilityEngine() {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  const paused = useRef(false);

  useEffect(() => {
    if (reduce) return;
    const id = setInterval(() => {
      if (!paused.current) setI((v) => (v + 1) % SCENARIOS.length);
    }, 4200);
    return () => clearInterval(id);
  }, [reduce]);

  const s = SCENARIOS[i]!;

  return (
    <div
      className="mt-16"
      onPointerEnter={() => (paused.current = true)}
      onPointerLeave={() => (paused.current = false)}
    >
      {/* the condition the system is reasoning about */}
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
        <span className="t-meta">Context</span>
        <motion.span
          key={s.context}
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={reduce ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="font-mono text-[15px] tracking-[0.04em] text-[var(--ink)]"
        >
          {s.context}
        </motion.span>
        <motion.span
          key={s.detail}
          initial={reduce ? false : { opacity: 0 }}
          animate={reduce ? undefined : { opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-[15px] text-[var(--ink-faint)]"
        >
          {s.detail}
        </motion.span>
      </div>

      {/* weights redistributing — the actual thing HELIOS learns */}
      <div className="mt-9 space-y-6">
        {MODEL_META.map((m) => {
          const w = s.weights[m.id];
          return (
            <SignalFocus key={m.id} target={m.id} className="block cursor-default">
              <div className="flex items-baseline justify-between gap-4">
                <span
                  className="font-display text-[1.5rem] font-semibold tracking-[-0.01em]"
                  style={{ color: m.color }}
                >
                  {m.name}
                </span>
                <motion.span
                  className="tnum font-mono text-[15px] text-[var(--ink-dim)]"
                  key={`${m.id}-${w}`}
                  initial={reduce ? false : { opacity: 0.4 }}
                  animate={reduce ? undefined : { opacity: 1 }}
                  transition={{ duration: 0.4 }}
                >
                  {(w * 100).toFixed(0)}%
                </motion.span>
              </div>
              {/* the reliability track */}
              <div className="relative mt-3 h-[3px] w-full overflow-hidden rounded-full bg-[rgba(126,165,218,0.12)]">
                <motion.span
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ background: m.color, boxShadow: `0 0 14px ${m.color}` }}
                  animate={{ width: `${w * 100}%` }}
                  transition={
                    reduce
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 90, damping: 20, mass: 0.7 }
                  }
                />
              </div>
            </SignalFocus>
          );
        })}
      </div>

      {/* the resolved blend */}
      <SignalFocus target="helios" className="mt-10 block cursor-default">
        <div className="flex items-baseline justify-between gap-4">
          <span className="font-display text-[1.5rem] font-semibold tracking-[-0.01em] text-[var(--helios-amber)]">
            HELIOS
          </span>
          <span className="font-mono text-[13px] uppercase tracking-[0.12em] text-[var(--ink-faint)]">
            weighted blend
          </span>
        </div>
        {/* one bar, composed of the three contributions in proportion */}
        <div className="mt-3 flex h-[6px] w-full overflow-hidden rounded-full">
          {MODEL_META.map((m) => (
            <motion.span
              key={m.id}
              style={{ background: m.color }}
              animate={{ width: `${s.weights[m.id] * 100}%` }}
              transition={
                reduce
                  ? { duration: 0 }
                  : { type: "spring", stiffness: 90, damping: 20, mass: 0.7 }
              }
            />
          ))}
        </div>
      </SignalFocus>

      <p className="mt-7 max-w-[62ch] text-[14px] leading-[1.6] text-[var(--ink-faint)]">
        Illustrative contexts, shown to make the mechanism legible. Live learned
        weights for a real location and horizon are served by the HELIOS API on the
        forecast page.
      </p>
    </div>
  );
}

export default ReliabilityEngine;
