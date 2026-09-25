"use client";

import { motion, useReducedMotion } from "motion/react";
import { NWP_META, CANDIDATE_META } from "@/lib/constants";
import { NWP_MODELS, type LiveHorizon } from "@/lib/types";
import { AnimatedNumber } from "@/components/ui/primitives";
import { SignalFocus } from "@/components/stage/StateRegion";
import { ArbitrationFlow } from "@/components/live/ArbitrationFlow";
import { CandidateArbitrationFlow } from "@/components/live/CandidateArbitrationFlow";
import { WhyThisResult } from "@/components/live/WhyThisResult";

/* ------------------------------------------------------------ section shell */
function Section({
  index,
  identity,
  title,
  subtitle,
  level,
  children,
}: {
  index: string;
  identity: string;
  title: string;
  subtitle?: string;
  /**
   * Model Arena tier. Making the two levels explicit keeps the science legible:
   * LEVEL 1 are the raw NWP inputs, LEVEL 2 are the candidate blending methods
   * that arbitrate between them.
   */
  level?: { n: 1 | 2; of: string };
  children: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.section
      initial={reduce ? { opacity: 1 } : { opacity: 0, y: 34 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-90px" }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      className="mx-auto w-full max-w-[1200px] px-6 py-24 md:px-12"
    >
      <div className="mb-14 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[12px] tracking-[0.20em] text-[var(--helios-amber)]">{index}</span>
          <span className="h-px w-8 bg-[var(--helios-amber)]/40" />
          <span className="font-mono text-[12px] uppercase tracking-[0.24em] text-[var(--ink-faint)]">{identity}</span>
          {level && (
            <span className="ml-1 inline-flex items-center gap-2.5">
              <span className="surface-inset rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--ink-dim)]">
                Level {level.n} · {level.of}
              </span>
              {/* the arbitration relationship, stated visually: L1 feeds L2 */}
              <span aria-hidden className="hidden items-center gap-1 sm:inline-flex">
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{
                    background: level.n === 1 ? "var(--color-gfs)" : "var(--helios-amber)",
                    boxShadow: `0 0 8px ${level.n === 1 ? "var(--color-gfs)" : "var(--helios-amber)"}`,
                  }}
                />
                <span className="h-px w-5 bg-[rgba(126,165,218,0.35)]" />
                <span className="font-mono text-[11px] tracking-[0.1em] text-[var(--ink-ghost)]">
                  {level.n === 1 ? "inputs" : "arbitration"}
                </span>
              </span>
            </span>
          )}
        </div>
        <h2 className="t-title max-w-3xl text-[clamp(2.2rem,4.4vw,3.4rem)] text-[var(--ink)]">
          {title}
        </h2>
        {subtitle && <p className="attn-recede max-w-[62ch] text-[17px] leading-[1.72] text-[var(--ink-dim)]">{subtitle}</p>}
      </div>
      {children}
    </motion.section>
  );
}

/* ============================================ 02b · ARBITRATION FLOW ===== */

/**
 * The arbitration, shown as it happens: three real model forecasts stream into
 * the HELIOS core and leave as one resolved value. Every dimension of the visual
 * is bound to live API data — see ArbitrationFlow.
 */
export function Arbitration({ horizon }: { horizon: LiveHorizon | null }) {
  return (
    <Section
      index="02"
      identity="Arbitrate"
      title="Three forecasts enter. One leaves."
      subtitle="Each model's stream carries its live weight: thicker and busier means HELIOS is trusting it more for this place and horizon right now. An unavailable model shows as an unlit path — the system never fills in what it does not have."
      level={{ n: 1, of: "NWP model inputs" }}
    >
      <ArbitrationFlow horizon={horizon} className="h-[340px] w-full sm:h-[400px]" />
    </Section>
  );
}

/* =========================================== 04 · WHY THIS RESULT ======== */

/**
 * The system explaining itself with its own arithmetic. Occupies the space freed
 * by the old candidate card grid — deliberately not another grid.
 */
export function WhyResult({
  horizon,
  stationName,
}: {
  horizon: LiveHorizon | null;
  stationName?: string | null;
}) {
  return (
    <Section
      index="04"
      identity="Explain"
      title="Why this number?"
      subtitle="The deployed method's weights are literal blend coefficients, so the published forecast can be reconstructed term by term from the live model values. The residual below is the proof — not an approximation."
    >
      <WhyThisResult horizon={horizon} stationName={stationName} />
    </Section>
  );
}

/* ==================================== 03b · CANDIDATE ARBITRATION ======== */

/**
 * Level 2, made visible. The interesting fact — which was previously buried in
 * three numbers — is that each candidate distributes trust across the SAME three
 * models differently, which is precisely why they disagree.
 */
export function CandidateArbitration({ horizon }: { horizon: LiveHorizon | null }) {
  return (
    <Section
      index="03"
      identity="Select"
      title="Same three models. Three different opinions about them."
      subtitle="Each blending candidate decides for itself how much to trust GFS, IFS and ICON — stream thickness is that candidate's own weighting, taken live from the API. That disagreement is why their forecasts differ, and why only the method validated offline is deployed."
      level={{ n: 2, of: "Candidate blending methods" }}
    >
      <CandidateArbitrationFlow horizon={horizon} className="h-[360px] w-full sm:h-[420px]" />
    </Section>
  );
}

/* ==================================================== 02 · MODEL TRUST ===== */
export function ModelTrust({ horizon }: { horizon: LiveHorizon | null }) {
  const reduce = useReducedMotion();
  const ranked = NWP_MODELS.map((m) => ({
    m,
    w: horizon?.nwp_availability[m] ? (horizon?.nwp_weights[m] ?? 0) : 0,
    avail: horizon?.nwp_availability[m] ?? false,
    t: horizon?.nwp_forecasts_c[m] ?? null,
  })).sort((a, b) => b.w - a.w);

  return (
    <Section
      index="02"
      identity="Trust"
      level={{ n: 1, of: "NWP model inputs" }}
      title="Which models does HELIOS trust right now?"
      subtitle="GFS, IFS and ICON disagree. HELIOS predicts each model's reliability for this exact location and horizon, then weights them dynamically — these are the current inference weights, not historical averages."
    >
      <div className="flex flex-col gap-10">
        {ranked.map(({ m, w, avail, t }, i) => {
          const meta = NWP_META[m];
          return (
            <SignalFocus
              key={m}
              target={m as "gfs" | "ifs" | "icon"}
              focusable
              className="grid cursor-default grid-cols-[auto_1fr_auto] items-center gap-x-6 gap-y-2 rounded-md outline-none transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--helios-amber)]"
            >
              {/* identity */}
              <div className="flex flex-col">
                <span className="font-mono text-[17px] tracking-[0.04em]" style={{ color: avail ? meta.color : "var(--ink-faint)" }}>
                  {meta.label}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink-faint)]/70">
                  {meta.centre}
                </span>
              </div>

              {/* influence track */}
              <div className="relative h-[3px] w-full rounded-full bg-white/[0.06]">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ background: `linear-gradient(90deg, ${meta.color}55, ${meta.color}, ${meta.glow})`, boxShadow: `0 0 18px ${meta.color}55` }}
                  initial={reduce ? false : { width: 0 }}
                  whileInView={{ width: `${w * 100}%` }}
                  viewport={{ once: false }}
                  animate={{ width: `${w * 100}%` }}
                  transition={reduce ? { duration: 0 } : { duration: 0.9, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                >
                  {/* leading node */}
                  <span className="absolute right-0 top-1/2 h-2 w-2 -translate-y-1/2 translate-x-1/2 rounded-full" style={{ background: meta.glow, boxShadow: `0 0 10px ${meta.color}` }} />
                </motion.div>
              </div>

              {/* percentage */}
              <div className="w-24 text-right">
                {avail ? (
                  <AnimatedNumber value={w * 100} digits={1} suffix="%" className="text-2xl font-light text-[var(--ink)]" />
                ) : (
                  <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--ink-faint)]">unavailable</span>
                )}
              </div>

              {/* model value (subordinate) */}
              <div className="col-start-2 -mt-1">
                <span className="tnum font-mono text-[11px] tracking-[0.04em] text-[var(--ink-faint)]/70">
                  {avail && t != null ? `${t.toFixed(1)}°C forecast` : "—"}
                </span>
              </div>
            </SignalFocus>
          );
        })}
      </div>
    </Section>
  );
}

/* ================================================== 03 · AI CANDIDATES ===== */
/* =================================================== 04 · HELIOS OUTPUT ==== */
export function HeliosOutput({ horizon }: { horizon: LiveHorizon | null }) {
  const reduce = useReducedMotion();
  const t = horizon?.helios_temperature_c ?? null;
  const selected = horizon?.selected_candidate ?? "xgboost";
  const method = CANDIDATE_META[selected]?.label ?? "MLP";

  return (
    <section className="relative mx-auto w-full max-w-[1200px] px-6 py-28 md:px-12">
      <motion.div
        initial={reduce ? { opacity: 1 } : { opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-90px" }}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        className="relative flex flex-col items-center text-center"
      >
        {/* converging lines from the three candidates into the result */}
        <svg className="pointer-events-none absolute -top-4 left-1/2 h-24 w-[340px] -translate-x-1/2" viewBox="0 0 340 96" fill="none" aria-hidden="true">
          {[40, 170, 300].map((x, i) => (
            <motion.path
              key={x}
              d={`M${x} 0 C ${x} 48, 170 48, 170 92`}
              stroke="url(#converge)"
              strokeWidth="1"
              initial={reduce ? { pathLength: 1, opacity: 0.5 } : { pathLength: 0, opacity: 0 }}
              whileInView={{ pathLength: 1, opacity: 0.5 }}
              viewport={{ once: true }}
              transition={{ duration: 1, delay: 0.2 + i * 0.15 }}
            />
          ))}
          <defs>
            <linearGradient id="converge" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(120,160,210,0.05)" />
              <stop offset="100%" stopColor="var(--helios-amber)" />
            </linearGradient>
          </defs>
        </svg>

        <div
          className="pointer-events-none absolute top-10 h-72 w-72 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(255,199,115,0.14), transparent 68%)" }}
        />

        <span className="font-mono text-[13px] uppercase tracking-[0.55em] text-[var(--helios-amber)]/85">
          04 · Decide
        </span>
        <span className="mt-4 font-mono text-[12px] uppercase tracking-[0.20em] text-[var(--ink-faint)]">
          HELIOS final forecast
        </span>

        <div className="mt-3 flex items-start">
          {t != null ? (
            <>
              <AnimatedNumber
                value={t}
                digits={1}
                className="text-[9rem] font-thin leading-[0.82] tracking-[-0.05em] text-gradient-helios sm:text-[12rem]"
                duration={0.9}
              />
              <span className="mt-6 ml-1 font-mono text-4xl font-light text-[var(--helios-amber)]/60">°</span>
            </>
          ) : (
            <span className="text-7xl font-thin text-[var(--ink-faint)]">—</span>
          )}
        </div>

        <div className="mt-6 flex items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--ink-faint)]">selected method</span>
          <span className="rounded-full bg-white/[0.04] px-3 py-1 font-mono text-[12px] tracking-[0.06em] text-[var(--helios-amber)]">
            {method}
          </span>
        </div>
      </motion.div>
    </section>
  );
}

/* ============================================= DEVELOPMENT NOTICE ========== */
export function DevelopmentNotice() {
  return (
    <footer className="mx-auto w-full max-w-[1200px] px-6 pb-24 md:px-12">
      <div className="border-t border-white/[0.06] pt-8">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-[var(--helios-amber)]">
            MVP Status
          </span>
          <span className="h-px w-6 bg-[var(--helios-amber)]/40" />
          <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-[var(--ink-faint)]">
            Development notice
          </span>
        </div>
        <p className="mt-3 max-w-3xl font-mono text-[13px] leading-relaxed text-[var(--ink)]">
          MVP: Temperature forecasting is currently implemented. Rainfall prediction, disaster tracking, and additional weather capabilities are actively under development.
        </p>
        <p className="mt-3 max-w-3xl text-[14px] leading-relaxed text-[var(--ink-faint)]">
          HELIOS is an actively evolving forecasting system. Its performance is expected to
          improve with additional historical data, observations and continued training. Early
          evaluation has produced promising results despite the limited initial training
          dataset; these results are preliminary and should not be considered final
          operational accuracy. Forecasts are experimental and intended for demonstration and
          research.
        </p>
        <div className="mt-6 flex items-center gap-2">
          <span className="h-1 w-1 rounded-full bg-[var(--helios-amber)]" />
          <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--ink-faint)]/70">
            HELIOS · SIH26081 · live GFS · IFS · ICON → learned trust
          </span>
        </div>
      </div>
    </footer>
  );
}
