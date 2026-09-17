"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, type ReactNode } from "react";
import clsx from "clsx";
import type { HeliosApiError } from "@/lib/client";

/* --------------------------------------------------------------- Panel */

/**
 * Instrument panel. Uses the shared optical `surface` material so the forecast
 * application sits inside the same liquid/optical environment as the rest of the
 * site, while keeping its instrument identity: hairline header, corner ticks and
 * square-ish geometry rather than a rounded SaaS card.
 */
export function Panel({
  children,
  className,
  label,
  aside,
  flush,
  raised,
}: {
  children: ReactNode;
  className?: string;
  label?: string;
  aside?: ReactNode;
  flush?: boolean;
  /** Promote the primary readout on a page to the raised material tier. */
  raised?: boolean;
}) {
  return (
    <section
      className={clsx(
        "surface rounded-[14px]",
        raised && "surface-raised",
        className,
      )}
    >
      {/* corner ticks */}
      <CornerTicks />
      {(label || aside) && (
        <header className="flex items-center justify-between gap-4 border-b border-[rgba(126,165,218,0.10)] px-4 py-2.5">
          {label && <h3 className="label label-bright">{label}</h3>}
          {aside}
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function CornerTicks() {
  const base =
    "pointer-events-none absolute h-2 w-2 border-[var(--color-hairline-bright)]";
  return (
    <>
      <span className={clsx(base, "left-0 top-0 border-l border-t")} />
      <span className={clsx(base, "right-0 top-0 border-r border-t")} />
      <span className={clsx(base, "bottom-0 left-0 border-b border-l")} />
      <span className={clsx(base, "bottom-0 right-0 border-b border-r")} />
    </>
  );
}

/* ----------------------------------------------------------- AnimatedNumber */

/**
 * Interpolates between numeric values so a changing measurement reads as a
 * physical instrument settling, not a React re-render. Respects reduced-motion.
 */
export function AnimatedNumber({
  value,
  digits = 1,
  suffix = "",
  prefix = "",
  className,
  duration = 0.7,
}: {
  value: number | null | undefined;
  digits?: number;
  suffix?: string;
  prefix?: string;
  className?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef<number | null>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (value === null || value === undefined || !Number.isFinite(value)) {
      el.textContent = "—";
      prev.current = null;
      return;
    }
    const from = prev.current;
    prev.current = value;

    if (reduce || from === null) {
      el.textContent = `${prefix}${value.toFixed(digits)}${suffix}`;
      return;
    }
    const controls = animate(from, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = `${prefix}${v.toFixed(digits)}${suffix}`;
      },
    });
    return () => controls.stop();
  }, [value, digits, suffix, prefix, duration, reduce]);

  return <span ref={ref} className={clsx("tnum", className)} />;
}

/* ------------------------------------------------------------------- Tag */

export function Tag({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "live" | "candidate" | "baseline" | "warn" | "planned";
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "border-[var(--color-hairline-bright)] text-[var(--color-ink-dim)]",
    live: "border-[var(--color-helios)]/60 text-[var(--color-helios)] bg-[var(--color-helios)]/8",
    candidate: "border-[var(--color-ink-ghost)] text-[var(--color-ink-faint)]",
    baseline: "border-[var(--color-baseline)]/50 text-[var(--color-baseline)]",
    warn: "border-[var(--color-warn)]/50 text-[var(--color-warn)]",
    planned:
      "border-dashed border-[var(--color-ink-ghost)] text-[var(--color-ink-ghost)]",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 border px-2 py-[3px] font-mono text-[11px] uppercase tracking-[0.14em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------- Skeleton */

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "relative overflow-hidden bg-[var(--color-raised)]",
        className,
      )}
      aria-hidden="true"
    >
      <div className="animate-sweep absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/[0.06] to-transparent" />
    </div>
  );
}

/* ------------------------------------------------------------ ErrorState */

/**
 * Honest failure surface. Every distinct failure mode gets specific, actionable
 * copy — we never silently substitute placeholder science.
 */
export function ErrorState({
  error,
  onRetry,
  compact,
}: {
  error: HeliosApiError;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const copy: Record<string, { title: string; body: string }> = {
    unauthorized: {
      title: "API key rejected",
      body: "The HELIOS API returned 401. Set a valid HELIOS_API_KEY in frontend/.env.local and restart the dev server.",
    },
    offline: {
      title: "HELIOS API unreachable",
      body: "The V1 API is not responding. Start it with: python -m backend.app.api.v1_app --port 8011",
    },
    timeout: {
      title: "Request timed out",
      body: "The API did not respond in time. It may be loading the frozen model artifacts.",
    },
    not_found: {
      title: "No data for this selection",
      body: "The V1 dataset has no forecast rows for this station, cycle and horizon combination.",
    },
    misconfigured: {
      title: "Server not configured",
      body: "HELIOS_API_KEY is missing on the frontend server.",
    },
    bad_data: {
      title: "Malformed response",
      body: "The API response did not match the expected V1 contract.",
    },
    unknown: { title: "Unexpected error", body: error.message },
  };
  const c = copy[error.kind] ?? copy.unknown!;

  return (
    <div
      role="alert"
      className={clsx(
        "flex flex-col items-start gap-2 border border-[var(--color-alert)]/30 bg-[var(--color-alert)]/[0.04]",
        compact ? "px-3 py-2" : "p-4",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 shrink-0 bg-[var(--color-alert)]" />
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--color-alert)]">
          {c.title}
        </span>
      </div>
      <p className="max-w-prose text-xs leading-relaxed text-[var(--color-ink-dim)]">
        {c.body}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 border border-[var(--color-hairline-bright)] px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-dim)] transition-colors hover:border-[var(--color-ink-faint)] hover:text-[var(--color-ink)]"
        >
          Retry
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ Unavailable */

/** Used wherever the backend explicitly reports data as unavailable. */
export function Unavailable({ reason }: { reason?: string }) {
  return (
    <span
      className="font-mono text-[11px] uppercase tracking-[0.12em] text-[var(--color-ink-ghost)]"
      title={reason}
    >
      unavailable
    </span>
  );
}

/* ---------------------------------------------------------------- Metric */

export function Metric({
  label,
  children,
  hint,
  className,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-col gap-1", className)}>
      <span className="label" title={hint}>
        {label}
      </span>
      <span className="tnum text-[var(--color-ink)]">{children}</span>
    </div>
  );
}

/* -------------------------------------------------------------- SectionHead */

export function SectionHead({
  index,
  title,
  lede,
  aside,
}: {
  index: string;
  title: string;
  lede?: string;
  aside?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        <div className="mb-3 flex items-center gap-3">
          <span className="font-mono text-[11px] tracking-[0.2em] text-[var(--color-helios)]">
            {index}
          </span>
          <span className="h-px w-12 bg-gradient-to-r from-[var(--color-helios)]/60 to-transparent" />
        </div>
        <h2 className="text-balance text-2xl font-semibold tracking-[-0.02em] text-[var(--color-ink)] md:text-[2rem] md:leading-[1.15]">
          {title}
        </h2>
        {lede && (
          <p className="mt-3 max-w-2xl text-pretty text-sm leading-relaxed text-[var(--color-ink-dim)]">
            {lede}
          </p>
        )}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </div>
  );
}
