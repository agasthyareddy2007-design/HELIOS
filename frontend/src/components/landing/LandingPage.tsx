"use client";

import Link from "next/link";
import { useRef, useState, useSyncExternalStore } from "react";
import {
  motion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";
import { SiteNav } from "@/components/site/SiteNav";
import { MvpStatusBanner } from "@/components/landing/MvpStatusBanner";
import { PerformanceValidation } from "@/components/landing/PerformanceValidation";
import { Button } from "@/components/ui/Button";
import { StateRegion, SignalFocus } from "@/components/stage/StateRegion";
import { ReliabilityEngine } from "@/components/landing/ReliabilityEngine";
import { ModelConvergence } from "@/components/landing/ModelConvergence";
import {
  ScrollStage,
  MaskedHeading,
  useMotionEnabled,
} from "@/components/landing/scroll";

/**
 * HELIOS landing page — scientific-instrument direction with a production-grade,
 * scroll-driven motion layer over the top.
 *
 * The hero ModelConvergence visual (GFS + IFS + ICON → HELIOS → forecast) is
 * PRESERVED exactly; scrolling only makes the hero *recede* to hand off to the
 * story below. The rest of the page reads as one continuous evolving space:
 * a scroll-linked atmospheric field behind everything, glass panels emerging
 * from depth, masked typography reveals, and one pinned verification loop that
 * illuminates as you scroll. All motion runs off Motion values (no per-scroll
 * React state), fully bypassed under prefers-reduced-motion, simplified on
 * mobile. Content/messaging is unchanged.
 */

const MODELS = [
  { id: "gfs", name: "GFS", origin: "NOAA · United States", color: "var(--color-gfs)" },
  { id: "ifs", name: "IFS", origin: "ECMWF · Europe", color: "var(--color-ifs)" },
  { id: "icon", name: "ICON", origin: "DWD · Germany", color: "var(--color-icon)" },
] as const;

const LOOP_STEPS = [
  { title: "Forecast issued", detail: "HELIOS publishes a blended forecast for a place and lead time." },
  { title: "Observations arrive", detail: "Ground truth lands from station and reanalysis records." },
  { title: "Forecast vs actual", detail: "Each model's error is scored against what actually happened." },
  { title: "Reliability updated", detail: "Conditional reliability is revised for that context." },
  { title: "Blending adapts", detail: "The next forecast reweights the models accordingly." },
] as const;

function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

/** Section framing with an instrument eyebrow. */
function Section({
  id,
  eyebrow,
  children,
  className = "",
}: {
  id?: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={`relative mx-auto max-w-[1200px] px-6 md:px-10 ${className}`}>
      {eyebrow && (
        <p className="mb-8 flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--ink-faint)]">
          <span className="inline-block h-px w-8 bg-[var(--color-hairline-bright)]" />
          {eyebrow}
        </p>
      )}
      {children}
    </section>
  );
}

/* ============================ HERO (recede on scroll) ==================== */

function Hero() {
  const enabled = useMotionEnabled();
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  // Progress across the hero as it scrolls out of the top of the viewport.
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const p = useSpring(scrollYProgress, { stiffness: 80, damping: 26, mass: 0.4 });

  // Hero content compresses + recedes; the WHOLE hero (incl. the untouched
  // ModelConvergence) drifts back in depth as the story below takes over.
  const contentY = useTransform(p, [0, 1], [0, -60]);
  const contentOpacity = useTransform(p, [0, 0.7], [1, 0]);
  const stageScale = useTransform(p, [0, 1], [1, 0.92]);
  const stageBlur = useTransform(p, [0, 1], [0, 6]);
  const stageFilter = useTransform(stageBlur, (b) => `blur(${b.toFixed(2)}px)`);

  const heroCopyStyle = enabled ? { y: contentY, opacity: contentOpacity } : undefined;
  const visualStyle = enabled ? { scale: stageScale, filter: stageFilter } : undefined;

  return (
    <section ref={ref} className="relative min-h-screen">
      <div className="relative mx-auto grid min-h-screen max-w-[1200px] items-center gap-8 px-6 pt-28 pb-16 md:px-10 lg:grid-cols-[1.05fr_1fr] lg:pt-20">
        {/* --- hero copy (recedes) --- */}
        <motion.div className="max-w-xl" style={heroCopyStyle}>
          <motion.p
            initial={reduced ? false : { opacity: 0, y: 12 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--ink-faint)]"
          >
            SIH26081 · learned weather-model arbitration
          </motion.p>

          <motion.h1
            initial={reduced ? false : { opacity: 0, y: 18 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.05, ease: [0.16, 1, 0.3, 1] }}
            className="display-hero mt-5 text-[clamp(4rem,10vw,8.5rem)]"
          >
            HELIOS
          </motion.h1>

          <motion.p
            initial={reduced ? false : { opacity: 0, y: 14 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.09, ease: [0.16, 1, 0.3, 1] }}
            className="mt-2.5 max-w-lg text-[14px] leading-relaxed text-[var(--ink-dim)] sm:text-[15px]"
          >
            HELIOS is an AI weather forecast blending model built from scratch using XGBoost, Kernel Regression, and Multilayer Perceptron (MLP).
          </motion.p>

          <motion.p
            initial={reduced ? false : { opacity: 0, y: 16 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.14, ease: [0.16, 1, 0.3, 1] }}
            className="mt-4 font-display text-[clamp(1.35rem,2.6vw,1.9rem)] font-medium leading-snug text-[var(--ink)]"
          >
            Intelligent weather-model blending.
          </motion.p>

          <motion.p
            initial={reduced ? false : { opacity: 0, y: 16 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="mt-3 max-w-md text-[16px] leading-relaxed text-[var(--ink-dim)]"
          >
            Three of the world&apos;s leading weather models rarely agree. HELIOS learns
            how much to trust each one — for a given place, hour and horizon — and blends
            them into a single calibrated forecast.
          </motion.p>

          <motion.div
            initial={reduced ? false : { opacity: 0, y: 16 }}
            animate={reduced ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.26, ease: [0.16, 1, 0.3, 1] }}
            className="mt-8 flex flex-wrap items-center gap-4"
          >
            <Link
              href="/forecast"
              className="group inline-flex items-center gap-3 rounded-full bg-[var(--helios-amber)] px-6 py-3 font-mono text-[12px] uppercase tracking-[0.24em] text-[#1a1205] transition-transform duration-200 hover:scale-[1.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
            >
              Explore forecast
              <span aria-hidden className="transition-transform duration-200 group-hover:translate-x-1">→</span>
            </Link>
            <a
              href="#how"
              className="inline-flex items-center gap-2 rounded-full border border-[var(--color-hairline-bright)] px-5 py-3 font-mono text-[12px] uppercase tracking-[0.24em] text-[var(--ink-dim)] transition-colors hover:border-[var(--ink-faint)] hover:text-[var(--ink)]"
            >
              How it works
            </a>
          </motion.div>

          <motion.ul
            initial={reduced ? false : { opacity: 0 }}
            animate={reduced ? undefined : { opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="mt-12 flex flex-wrap gap-x-6 gap-y-2"
          >
            {MODELS.map((m) => (
              <li key={m.id} className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--ink-faint)]">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.color, boxShadow: `0 0 10px ${m.color}` }} />
                {m.name}
              </li>
            ))}
            <li className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--helios-amber)]">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--helios-amber)]" style={{ boxShadow: "0 0 10px var(--helios-amber)" }} />
              HELIOS
            </li>
          </motion.ul>
        </motion.div>

        {/* --- procedural convergence visual (PRESERVED — only the container
                subtly recedes with scroll; the visual itself is untouched) --- */}
        <motion.div
          className="relative order-first h-[46vh] w-full lg:order-none lg:h-[68vh]"
          style={visualStyle}
        >
          <ModelConvergence className="absolute inset-0 h-full w-full" />
        </motion.div>
      </div>

      {!reduced && (
        <motion.div
          className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center"
          style={enabled ? { opacity: contentOpacity } : undefined}
        >
          <div className="flex flex-col items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.22em] text-[var(--ink-faint)]">
            <span>Scroll to explore HELIOS</span>
            <motion.span
              animate={{ y: [0, 3, 0] }}
              transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
              className="text-[13px] text-[var(--helios-amber)]/80"
            >
              ↓
            </motion.span>
          </div>
        </motion.div>
      )}
    </section>
  );
}

/* ==================== PINNED VERIFICATION LOOP ========================== */

function VerificationLoop() {
  const enabled = useMotionEnabled();
  // Discrete selection only — one state change per hover/focus, never per frame.
  const [active, setActive] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 75%", "center center"],
  });
  const p = useSpring(scrollYProgress, { stiffness: 80, damping: 28, mass: 0.4 });

  return (
    <section ref={ref} className="relative">
      <Section eyebrow="Verification loop" className="py-16 md:py-20">
        <MaskedHeading
          as="h2"
          className="max-w-2xl display-section text-[clamp(2.4rem,5vw,4rem)]"
          lines={["Every forecast is eventually", "checked against reality."]}
        />

        {/* One continuous rail behind the stages: the loop is a single closed
            process, not five separate cards. */}
        <div className="relative mt-16">
          <div
            aria-hidden
            className="pointer-events-none absolute left-0 right-0 top-[22px] hidden h-px md:block"
            style={{
              background:
                "linear-gradient(90deg, transparent, rgba(126,165,218,0.28) 8%, rgba(255,199,115,0.45) 92%, transparent)",
            }}
          />
          <ol
            className="grid gap-5 md:grid-cols-5"
            onMouseLeave={() => setActive(null)}
          >
            {LOOP_STEPS.map((step, i) => (
              <LoopStep
                key={step.title}
                step={step.title}
                detail={step.detail}
                index={i}
                progress={p}
                pinned={enabled}
                total={LOOP_STEPS.length}
                active={active}
                onActivate={setActive}
              />
            ))}
          </ol>
        </div>

        <p className="attn-recede mt-10 max-w-xl text-[16px] leading-relaxed text-[var(--ink-dim)]">
          The loop is closed and continuous: verified skill feeds straight back into how
          the models are weighted next time.
        </p>

        <PerformanceValidation />
      </Section>
    </section>
  );
}

function LoopStep({
  step,
  detail,
  index,
  progress,
  pinned,
  total,
  active,
  onActivate,
}: {
  step: string;
  detail: string;
  index: number;
  progress: MotionValue<number>;
  pinned: boolean;
  total: number;
  active: number | null;
  onActivate: (i: number | null) => void;
}) {
  // Each stage illuminates as the section settles, and again on hover/focus so
  // the visitor can step through the process at their own pace (keyboard too).
  const start = 0.15 + (index / total) * 0.6;
  const end = start + 0.12;
  // Scroll drives the stage's *entrance* emphasis; hover/focus drives dominance.
  // Keeping them on separate properties avoids Motion arbitrating one value from
  // two sources (which previously made dominance a no-op).
  const scrollLit = useTransform(progress, [start - 0.05, start, end], [0.42, 1, 1]);

  // When any stage is selected, it becomes dominant and the others recede: the
  // system is showing you the stage it is "in", not just highlighting a card.
  const isActive = active === index;
  const isDimmed = active !== null && !isActive;

  return (
    <motion.li
      tabIndex={0}
      aria-label={`Stage ${index + 1}: ${step}. ${detail}`}
      aria-current={isActive || undefined}
      onMouseEnter={() => onActivate(index)}
      onFocus={() => onActivate(index)}
      onBlur={() => onActivate(null)}
      className="group relative rounded-[14px] outline-none"
      animate={
        pinned
          ? { scale: isActive ? 1.035 : isDimmed ? 0.985 : 1, opacity: isDimmed ? 0.45 : 1 }
          : undefined
      }
      initial={pinned ? false : { opacity: 0, y: 22 }}
      whileInView={pinned ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={
        pinned
          ? { type: "spring", stiffness: 260, damping: 26, mass: 0.6 }
          : { duration: 0.6, delay: index * 0.08, ease: [0.16, 1, 0.3, 1] }
      }
    >
      {/* node on the rail */}
      <span
        aria-hidden
        className={`relative z-[1] hidden h-[9px] w-[9px] rounded-full border transition-all duration-300 md:block ${
          isActive
            ? "scale-[1.5] border-[var(--helios-amber)] bg-[var(--helios-amber)]"
            : "border-[rgba(126,165,218,0.45)] bg-[var(--color-void)]"
        }`}
        style={{
          marginTop: "18px",
          marginBottom: "18px",
          boxShadow: isActive ? "0 0 16px 2px rgba(255,199,115,0.55)" : "none",
        }}
      />
      {/* No panel: a hairline carries the stage, and it brightens when the
          system is showing you this step. */}
      <motion.div
        className="relative pl-4"
        style={pinned ? { opacity: scrollLit } : undefined}
      >
        <span
          aria-hidden
          className="absolute left-0 top-0 h-full w-px transition-all duration-300"
          style={{
            background: isActive
              ? "linear-gradient(180deg, var(--helios-amber), rgba(255,199,115,0))"
              : "linear-gradient(180deg, rgba(126,165,218,0.35), rgba(126,165,218,0))",
          }}
        />
        <span
          className="font-mono text-[12px] tracking-[0.14em]"
          style={{ color: isActive ? "var(--helios-amber)" : "var(--ink-ghost)" }}
        >
          0{index + 1}
        </span>
        <p className="mt-2.5 text-[16px] font-medium leading-snug text-[var(--ink)]">{step}</p>
        <p
          className="mt-2 text-[14px] leading-[1.6] transition-colors duration-300"
          style={{ color: isActive ? "var(--ink-dim)" : "var(--ink-faint)" }}
        >
          {detail}
        </p>
      </motion.div>
    </motion.li>
  );
}

/* ================================= PAGE ================================= */
export default function LandingPage() {
  return (
    <>
      <SiteNav variant="overlay" />
      <MvpStatusBanner />

      <main className="relative overflow-hidden text-[var(--color-ink)]">
        {/* ---------------------------- HERO ---------------------------- */}
        <StateRegion state="arrival">
          <Hero />
        </StateRegion>

        {/* --------------------------- PROBLEM -------------------------- */}
        <StateRegion state="divergence">
        <ScrollStage>
          <Section eyebrow="The problem" className="py-16 md:py-20">
            <div className="grid gap-10 md:grid-cols-[1.2fr_1fr] md:items-center">
              <MaskedHeading
                as="h2"
                className="display-section text-[clamp(2.4rem,5vw,4rem)]"
                lines={["No single weather model", "is reliably right."]}
              />
              <p className="text-[16px] leading-relaxed text-[var(--ink-dim)]">
                Every operational model encodes different physics, resolution and data
                assimilation. One is sharper over coastlines; another handles a heatwave
                better; a third wins at longer range. Pick one model and you inherit its
                blind spots — everywhere, all the time.
              </p>
            </div>
          </Section>
        </ScrollStage>
        </StateRegion>

        {/* ------------------------- THREE MODELS ----------------------- */}
        <StateRegion state="signals">
        <ScrollStage>
          <Section id="how" eyebrow="Three models" className="py-16 md:py-20">
            <MaskedHeading
              as="h2"
              className="max-w-2xl display-section text-[clamp(2.4rem,5vw,4rem)]"
              lines={["Three world-class forecasts.", "They disagree constantly."]}
            />
            {/* The three models as SIGNALS, not cards: a hairline column each,
                carrying its own spectral identity. No containers. */}
            <div className="mt-16 grid gap-x-10 gap-y-12 sm:grid-cols-3">
              {MODELS.map((m, i) => (
                <SignalFocus
                  key={m.id}
                  focusable
                  target={m.id as "gfs" | "ifs" | "icon"}
                  className="relative rounded-lg outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-[var(--helios-amber)]"
                >
                <motion.div
                  className="group relative"
                  initial={{ opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-12% 0px -12% 0px" }}
                  transition={{ duration: 0.7, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                >
                  {/* the signal: a vertical spectral line that brightens on hover */}
                  <span
                    aria-hidden
                    className="absolute -left-5 top-1 h-[calc(100%-0.25rem)] w-px transition-opacity duration-300"
                    style={{
                      background: `linear-gradient(180deg, ${m.color}, transparent)`,
                      opacity: 0.55,
                    }}
                  />
                  <div className="flex items-baseline gap-3">
                    <h3
                      className="font-display text-[2.4rem] font-semibold leading-none tracking-[-0.02em] transition-[text-shadow] duration-300"
                      style={{ color: m.color }}
                    >
                      {m.name}
                    </h3>
                    <span
                      aria-hidden
                      className="h-1.5 w-1.5 rounded-full transition-all duration-300 group-hover:scale-150"
                      style={{ background: m.color, boxShadow: `0 0 12px ${m.color}` }}
                    />
                  </div>
                  <p className="mt-3 font-mono text-[12px] uppercase tracking-[0.12em] text-[var(--ink-faint)]">
                    {m.origin}
                  </p>
                </motion.div>
                </SignalFocus>
              ))}
            </div>

            <p className="attn-recede mt-10 max-w-xl text-[16px] leading-relaxed text-[var(--ink-dim)]">
              On any given day, for any given place, their 2-metre temperature forecasts can
              spread by several degrees. The hard question is not <em>what</em> they predict —
              it is <em>which one to believe, and when.</em>
            </p>
          </Section>
        </ScrollStage>

        </StateRegion>

        {/* --------------------- WHAT HELIOS LEARNS --------------------- */}
        <StateRegion state="reasoning">
        <ScrollStage>
          <Section eyebrow="What HELIOS learns" className="py-16 md:py-20">
            <MaskedHeading
              as="h2"
              className="display-section max-w-4xl text-[clamp(2.4rem,5vw,4rem)]"
              lines={[
                "HELIOS does not learn the weather.",
                <span key="a" className="text-[var(--helios-amber)]">It learns which model to trust.</span>,
              ]}
            />

            <p className="attn-recede mt-8 max-w-[62ch] text-[19px] leading-[1.65] text-[var(--ink-dim)]">
              The models already simulate the atmosphere, at enormous computational cost.
              HELIOS learns something different and much smaller:{" "}
              <span className="text-[var(--ink)]">how reliable each model tends to be</span>{" "}
              for a specific place, hour and forecast lead — then weights them accordingly.
            </p>

            {/* The learning chain as a propagating computation: each term is a
                stage the signal passes through, and the last one resolves to the
                HELIOS colour because weighting is the output. */}
            <div className="relative mt-16">
              <div
                aria-hidden
                className="pointer-events-none absolute left-0 right-0 top-[7px] hidden h-px lg:block"
                style={{
                  background:
                    "linear-gradient(90deg, rgba(77,163,255,0.30), rgba(139,124,255,0.30) 35%, rgba(47,214,180,0.30) 62%, rgba(255,199,115,0.60))",
                }}
              />
              <ol className="grid gap-y-12 sm:grid-cols-2 lg:grid-cols-5 lg:gap-x-5">
                {[
                  { k: "Signal", d: "Three model forecasts for the same target.", c: "var(--color-gfs)" },
                  { k: "Context", d: "Where, what hour, how far ahead.", c: "var(--color-ifs)" },
                  { k: "Error", d: "How each model actually performed there.", c: "var(--color-icon)" },
                  { k: "Reliability", d: "A learned expectation of trustworthiness.", c: "var(--color-icon)" },
                  { k: "Weighting", d: "Trust becomes the blend, per forecast.", c: "var(--helios-amber)" },
                ].map((item, i, arr) => {
                  const last = i === arr.length - 1;
                  return (
                    <motion.li
                      key={item.k}
                      className="relative"
                      initial={{ opacity: 0, y: 16 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, margin: "-15% 0px -15% 0px" }}
                      transition={{
                        duration: 0.65,
                        delay: i * 0.13,
                        ease: [0.16, 1, 0.3, 1],
                      }}
                    >
                      {/* the signal node on the chain */}
                      <motion.span
                        aria-hidden
                        className="absolute -top-[24px] left-0 hidden h-[15px] w-[15px] rounded-full lg:block"
                        style={{
                          background: item.c,
                          boxShadow: `0 0 ${last ? 22 : 12}px ${last ? 4 : 1}px ${item.c}`,
                        }}
                        initial={{ scale: 0.2, opacity: 0 }}
                        whileInView={{ scale: last ? 1 : 0.62, opacity: 1 }}
                        viewport={{ once: true, margin: "-15% 0px -15% 0px" }}
                        transition={{
                          duration: 0.5,
                          delay: i * 0.13 + 0.1,
                          ease: [0.16, 1, 0.3, 1],
                        }}
                      />
                      <div className="flex items-baseline gap-3">
                        <span className="font-mono text-[12px] tracking-[0.14em] text-[var(--ink-ghost)]">
                          0{i + 1}
                        </span>
                        <h3
                          className="font-display text-[1.45rem] font-semibold tracking-[-0.012em]"
                          style={{ color: last ? "var(--helios-amber)" : "var(--ink)" }}
                        >
                          {item.k}
                        </h3>
                      </div>
                      <p className="mt-3 max-w-[28ch] text-[15px] leading-[1.62] text-[var(--ink-faint)]">
                        {item.d}
                      </p>
                    </motion.li>
                  );
                })}
              </ol>
            </div>

            {/* The mechanism, demonstrated: context changes, weights follow. */}
            <ReliabilityEngine />

            <p className="attn-recede mt-16 max-w-[58ch] text-[17px] leading-[1.7] text-[var(--ink-dim)]">
              That distinction is the whole design. HELIOS is a context-aware arbitration
              layer, not a weather model: it reweights existing forecasts and never invents
              one of its own.
            </p>
          </Section>
        </ScrollStage>

        </StateRegion>

        {/* --------------------- VERIFICATION (in-view) ------------------ */}
        <StateRegion state="verification">
          <VerificationLoop />
        </StateRegion>

        {/* ----------------------------- RESULT ------------------------- */}
        <StateRegion state="resolution">
        <ScrollStage intensity={1.2}>
          <Section eyebrow="The result" className="py-16 md:py-20">
            <div className="flex flex-col items-center text-center">
              <div className="flex items-center gap-3 font-display text-xl font-medium tracking-tight">
                {MODELS.map((m, i) => (
                  <SignalFocus
                    key={m.id}
                    as="span"
                    target={m.id as "gfs" | "ifs" | "icon"}
                    className="flex cursor-default items-center gap-3"
                  >
                    <span style={{ color: m.color }}>{m.name}</span>
                    {i < MODELS.length - 1 && <span className="text-[var(--ink-ghost)]">+</span>}
                  </SignalFocus>
                ))}
              </div>
              <span aria-hidden className="my-6 text-2xl text-[var(--ink-ghost)]">↓</span>
              <MaskedHeading
                as="h2"
                className="display-section text-[clamp(2.4rem,5.4vw,4rem)] text-[var(--helios-amber)]"
                lines={["One calibrated forecast"]}
              />
              <p className="mt-6 max-w-md text-[16px] leading-relaxed text-[var(--ink-dim)]">
                A single, defensible number for any location in India — with the model
                agreement behind it always kept visible.
              </p>
            </div>
          </Section>
        </ScrollStage>

        {/* --------------------------- FORECAST CTA --------------------- */}
        <ScrollStage intensity={1.3}>
          <Section className="py-16 md:py-20">
            {/* No container: the closing statement stands in the atmosphere. A
                single hairline above it provides the only structure needed. */}
            <div className="relative py-6 text-center">
              <span
                aria-hidden
                className="mx-auto mb-14 block h-px w-full max-w-[520px]"
                style={{
                  background:
                    "linear-gradient(90deg, transparent, rgba(255,199,115,0.45), transparent)",
                }}
              />
              <MaskedHeading
                as="h2"
                className="display-section mx-auto max-w-[24ch] text-[clamp(2.6rem,5.4vw,4.2rem)]"
                lines={["See HELIOS in action."]}
              />
              <p className="mx-auto mt-6 max-w-[52ch] text-[18px] leading-[1.66] text-[var(--ink-dim)]">
                Pick any point in India and watch the live model trust, candidate forecasts
                and the calibrated HELIOS output resolve in real time.
              </p>
              <div className="mt-11 flex justify-center">
                <Button href="/forecast" variant="primary" size="lg" trailing="→">
                  Open forecast
                </Button>
              </div>
            </div>
          </Section>
        </ScrollStage>

        </StateRegion>

        {/* ----------------------------- FOOTER ------------------------- */}
        <footer className="relative border-t border-[rgba(126,165,218,0.10)]">
          <Section className="flex flex-col items-start justify-between gap-8 py-16 md:flex-row md:items-center">
            <div>
              <p className="font-display text-[16px] font-semibold uppercase tracking-[0.24em]">Helios</p>
              <p className="mt-2 max-w-sm text-[14px] leading-relaxed text-[var(--ink-faint)]">
                A learned weather-model arbitration layer, built for SIH26081.
              </p>
              <p className="mt-4 max-w-sm font-mono text-[11px] leading-relaxed text-[var(--ink-ghost)]">
                MVP: Temperature forecasting is currently implemented. Rainfall prediction, disaster tracking, and additional weather capabilities are actively under development.
              </p>
            </div>
            <nav className="flex items-center gap-3" aria-label="Footer">
              <Button href="/forecast" variant="ghost" size="md">
                Forecast
              </Button>
              <Button href="/contact" variant="secondary" size="md" trailing="→">
                Project &amp; contact
              </Button>
            </nav>
          </Section>
        </footer>
      </main>
    </>
  );
}
