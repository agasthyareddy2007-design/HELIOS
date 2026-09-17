"use client";

import { motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { formatValid, validIST } from "@/lib/format";
import type { LiveForecastResponse, LiveHorizon, StationLocation } from "@/lib/types";
import type { HeliosApiError } from "@/lib/client";
import { AnimatedNumber } from "@/components/ui/primitives";

const LEADS = [6, 24, 48, 72, 120] as const;

/** Short date for a timeline node, from the horizon's own valid_time (IST). */
function nodeDate(validTime: string): string {
  const d = new Date(validTime.replace("Z", "+00:00"));
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("day")} ${get("month").toUpperCase()}`;
}

/**
 * SECTION 01 · FORECAST — typography-first detail beside the map hero.
 *
 * Not a card of labels: a large HELIOS temperature dominates, the location is
 * prominent-but-secondary, metadata is restrained, and the horizon selector is a
 * horizontal scientific timeline. All values are LIVE and belong to the same
 * location + selected horizon; the frontend performs no blending.
 *
 * Frozen logic preserved exactly: horizons are selected by `lead_time_hours`
 * (never by index); labels are the true lead (+6H … +120H, never "NOW"); the
 * disabled state is driven only by `is_future`.
 */
export function ForecastPanel({
  station,
  live,
  loading,
  error,
  onRetry,
  horizon,
  onSelectLead,
}: {
  station: StationLocation | null;
  live: LiveForecastResponse | null;
  loading: boolean;
  error: HeliosApiError | null;
  onRetry: () => void;
  horizon: LiveHorizon | null;
  onSelectLead: (lead: number) => void;
}) {
  const reduce = useReducedMotion();
  const firstFuture = live?.first_future_lead_hours ?? null;

  if (!station) {
    return (
      <div className="flex h-full flex-col justify-center">
        <div className="surface surface-raised rounded-[18px] p-7">
          <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-[var(--helios-amber)]/85">
            Observe
          </span>
          <h2 className="t-title mt-4 text-[1.75rem] text-[var(--ink)]">
            Select a location
          </h2>
          <p className="mt-3 max-w-xs text-[16px] leading-relaxed text-[var(--ink-dim)]">
            Click anywhere in India, or search a place, to see its live HELIOS forecast.
          </p>

          {/* What the instrument will resolve, stated before any data arrives. */}
          <div className="mt-7 border-t border-[rgba(126,165,218,0.10)] pt-5">
            <p className="t-meta">Resolves</p>
            <ul className="mt-3 flex flex-col gap-2">
              {[
                { k: "gfs", label: "GFS", note: "NOAA" },
                { k: "ifs", label: "IFS", note: "ECMWF" },
                { k: "icon", label: "ICON", note: "DWD" },
              ].map((m) => (
                <li key={m.k} className="flex items-center gap-3">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: `var(--color-${m.k})`, boxShadow: `0 0 10px var(--color-${m.k})` }}
                  />
                  <span className="font-mono text-[12px] tracking-[0.14em] text-[var(--ink-dim)]">{m.label}</span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">{m.note}</span>
                </li>
              ))}
              <li className="mt-1 flex items-center gap-3">
                <span
                  className="h-1.5 w-1.5 rounded-full bg-[var(--helios-amber)]"
                  style={{ boxShadow: "0 0 10px var(--helios-amber)" }}
                />
                <span className="font-mono text-[12px] tracking-[0.14em] text-[var(--helios-amber)]">HELIOS</span>
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                  arbitrated forecast
                </span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col justify-center gap-4">
        <span className="font-mono text-[11px] uppercase tracking-[0.20em] text-[var(--color-warn)]">
          Live forecast temporarily unavailable
        </span>
        <p className="max-w-xs text-[15px] leading-relaxed text-[var(--ink-dim)]">
          Current model data could not be retrieved. HELIOS does not substitute historical
          data — the forecast is always live.
        </p>
        <button
          onClick={onRetry}
          className="w-fit rounded-full border border-[var(--color-warn)]/50 px-5 py-2 font-mono text-[12px] uppercase tracking-[0.14em] text-[var(--color-warn)] transition-colors hover:bg-[var(--color-warn)]/10"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col justify-between gap-10">
      {/* identity + temperature */}
      <div>
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-signal)]" />
          <span className="font-mono text-[11px] uppercase tracking-[0.20em] text-[var(--ink-faint)]">
            01 · live forecast
          </span>
        </div>

        <h2 className="mt-5 text-3xl font-light tracking-[-0.015em] text-[var(--ink)]">
          {station.name ?? "Selected location"}
        </h2>
        <p className="tnum mt-1.5 font-mono text-[13px] tracking-[0.04em] text-[var(--ink-faint)]">
          {station.latitude?.toFixed(2)}°N · {station.longitude?.toFixed(2)}°E
        </p>

        <div className="mt-10 flex items-start">
          {loading && !live ? (
            <div className="h-24 w-52 animate-pulse rounded-3xl bg-white/[0.04]" />
          ) : horizon?.helios_temperature_c != null ? (
            <div className="flex items-start">
              <AnimatedNumber
                value={horizon.helios_temperature_c}
                digits={1}
                className="text-[7rem] font-thin leading-[0.85] tracking-[-0.05em] text-gradient-helios sm:text-[8.5rem]"
                duration={0.8}
              />
              <span className="mt-3 ml-1 font-mono text-3xl font-light text-[var(--helios-amber)]/60">°</span>
            </div>
          ) : (
            <span className="text-6xl font-thin text-[var(--ink-faint)]">—</span>
          )}
        </div>

        {/* explicit, unambiguous identity of the DISPLAYED horizon */}
        <div className="mt-5 flex flex-col gap-1">
          <span className="font-mono text-[14px] tracking-[0.12em] text-[var(--helios-amber)]">
            {horizon ? `+${horizon.lead_time_hours} HOURS` : "—"}
            {horizon && !horizon.is_future && (
              <span className="ml-2 text-[var(--ink-faint)]">· elapsed</span>
            )}
          </span>
          <span className="tnum text-[15px] text-[var(--ink)]">
            {horizon ? validIST(horizon.valid_time) : "—"}
          </span>
          <span className="tnum font-mono text-[11px] tracking-[0.06em] text-[var(--ink-faint)]">
            valid {horizon ? formatValid(horizon.valid_time) : "—"} · HELIOS forecast
          </span>
        </div>
      </div>

      {/* horizon timeline */}
      <div>
        <span className="font-mono text-[11px] uppercase tracking-[0.20em] text-[var(--ink-faint)]">
          Forecast horizon
        </span>
        <div className="relative mt-6">
          {/* connecting line */}
          <div className="absolute left-0 right-0 top-[7px] h-px bg-white/10" />
          <div className="relative flex justify-between" role="radiogroup" aria-label="Forecast horizon">
            {LEADS.map((h) => {
              const hz = live?.horizons.find((x) => x.lead_time_hours === h);
              const exists = Boolean(hz);
              const elapsed = hz ? !hz.is_future : false;
              const active = horizon?.lead_time_hours === h;
              const isFirstFuture = firstFuture === h;
              const disabled = !exists || elapsed;
              return (
                <button
                  key={h}
                  role="radio"
                  aria-checked={active}
                  disabled={disabled}
                  onClick={() => onSelectLead(h)}
                  className={clsx(
                    "group relative flex flex-col items-center gap-2.5",
                    disabled ? "cursor-not-allowed" : "cursor-pointer",
                  )}
                  title={
                    elapsed
                      ? `${h}h lead — valid time already elapsed for the current run`
                      : isFirstFuture
                        ? `${h}h lead — earliest future horizon`
                        : `${h}h lead`
                  }
                >
                  {/* node */}
                  <span className="relative flex h-3.5 w-3.5 items-center justify-center">
                    {active && !reduce && (
                      <motion.span
                        layoutId="horizon-node-glow"
                        className="absolute h-4 w-4 rounded-full bg-[var(--helios-amber)]/30"
                        transition={{ type: "spring", stiffness: 340, damping: 30 }}
                      />
                    )}
                    <span
                      className={clsx(
                        "h-2 w-2 rounded-full transition-all duration-300",
                        active
                          ? "scale-150 bg-[var(--helios-amber-core)] shadow-[0_0_12px_var(--helios-amber)]"
                          : disabled
                            ? "bg-white/15"
                            : "bg-white/40 group-hover:bg-white/70",
                      )}
                    />
                    {isFirstFuture && !active && (
                      <span className="absolute -right-0.5 -top-0.5 h-1 w-1 rounded-full bg-[var(--color-signal)]" />
                    )}
                  </span>
                  {/* label */}
                  <span
                    className={clsx(
                      "font-mono text-[12px] tracking-[0.04em] transition-colors",
                      active
                        ? "text-[var(--helios-amber)]"
                        : disabled
                          ? "text-[var(--ink-faint)]/45"
                          : "text-[var(--ink-dim)] group-hover:text-[var(--ink)]",
                    )}
                  >
                    +{h}H
                  </span>
                  <span
                    className={clsx(
                      "tnum font-mono text-[11px] tracking-[0.04em]",
                      active ? "text-[var(--ink-dim)]" : "text-[var(--ink-faint)]/60",
                    )}
                  >
                    {hz ? nodeDate(hz.valid_time) : "—"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        {live && (
          <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]/70">
            from the {live.cycle} model run · valid times in India Standard Time
          </p>
        )}
      </div>
    </div>
  );
}
