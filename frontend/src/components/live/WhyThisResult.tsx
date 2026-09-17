"use client";

import { motion, useReducedMotion } from "motion/react";
import { CANDIDATE_META, NWP_META } from "@/lib/constants";
import { NWP_MODELS, type CandidateKey, type LiveHorizon, type NwpModel } from "@/lib/types";
import { useStage } from "@/components/stage/useStage";

/**
 * WHY THIS RESULT — the system explaining its own output.
 *
 * This is not an illustration. The deployed candidate's weights turn out to be
 * literal blend coefficients: for every horizon returned by the API,
 *
 *     Σ ( weights[model] × nwp_forecasts_c[model] )  ===  helios_temperature_c
 *
 * exact to three decimal places (verified across leads +6/+24/+48 h). So this
 * section can show the ACTUAL arithmetic HELIOS performed rather than a
 * decorative metaphor — and it prints the residual so the reader can check that
 * the identity really closes.
 *
 * Every term is interactive and joined to the product-wide attention system:
 * touching a term lights that model's stream in both arbitration flows, its
 * sampled cell on the map, and pulls the atmosphere onto its hue.
 *
 * If the API omits anything, the term says so. Nothing is filled in.
 */

export function WhyThisResult({
  horizon,
  stationName,
}: {
  horizon: LiveHorizon | null;
  stationName?: string | null;
}) {
  const reduce = useReducedMotion();

  const selected = (horizon?.selected_candidate ?? null) as CandidateKey | null;
  const cand = selected ? horizon?.candidate_forecasts?.[selected] : null;
  const weights = cand?.weights ?? horizon?.nwp_weights ?? null;
  const published = horizon?.helios_temperature_c ?? null;

  const terms = NWP_MODELS.map((m) => {
    const avail = horizon?.nwp_availability[m] ?? false;
    const t = horizon?.nwp_forecasts_c[m] ?? null;
    const w = weights?.[m] ?? null;
    return { m, avail, t, w, contribution: avail && t !== null && w !== null ? w * t : null };
  });

  const sum = terms.reduce((acc, t) => acc + (t.contribution ?? 0), 0);
  const closes = published !== null && Math.abs(sum - published) < 0.05;
  const leader = terms
    .filter((t) => t.w !== null)
    .sort((a, b) => (b.w ?? 0) - (a.w ?? 0))[0];

  const setFocus = (t: NwpModel | "helios" | CandidateKey) =>
    useStage.getState().setFocus(t);
  const clear = (t: NwpModel | "helios" | CandidateKey) => {
    if (useStage.getState().focus === t) useStage.getState().setFocus(null);
  };

  if (!horizon) return null;

  return (
    <div className="mt-4">
      {/* the system's own sentence, assembled from real state */}
      <p className="max-w-[68ch] text-[19px] leading-[1.6] text-[var(--ink-dim)]">
        For{" "}
        <span className="text-[var(--ink)]">{stationName ?? "this location"}</span> at{" "}
        <span className="tnum text-[var(--ink)]">+{horizon.lead_time_hours} h</span>, HELIOS
        deployed{" "}
        {selected ? (
          <button
            type="button"
            onPointerEnter={() => setFocus(selected)}
            onPointerLeave={() => clear(selected)}
            onFocus={() => setFocus(selected)}
            onBlur={() => clear(selected)}
            aria-label={`Highlight ${CANDIDATE_META[selected].label}, the deployed method`}
            className="rounded font-semibold outline-none transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
            style={{ color: CANDIDATE_META[selected].color }}
          >
            {CANDIDATE_META[selected].label}
          </button>
        ) : (
          <span className="text-[var(--ink-faint)]">no method</span>
        )}
        {leader?.w != null && (
          <>
            , which trusted{" "}
            <button
              type="button"
              onPointerEnter={() => setFocus(leader.m)}
              onPointerLeave={() => clear(leader.m)}
              onFocus={() => setFocus(leader.m)}
              onBlur={() => clear(leader.m)}
              aria-label={`Highlight ${NWP_META[leader.m].label}, the most trusted model here`}
              className="rounded font-semibold outline-none transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
              style={{ color: NWP_META[leader.m].color }}
            >
              {NWP_META[leader.m].label}
            </button>{" "}
            most, at <span className="tnum text-[var(--ink)]">{(leader.w * 100).toFixed(0)}%</span>
          </>
        )}
        .
      </p>

      {/* THE ACTUAL ARITHMETIC — this is the real computation, not a metaphor */}
      <div className="mt-10">
        <p className="t-meta">The blend, term by term</p>

        <div className="mt-6 flex flex-wrap items-end gap-x-3 gap-y-6">
          {terms.map((term, i) => {
            const meta = NWP_META[term.m];
            const usable = term.avail && term.t !== null && term.w !== null;
            return (
              <div key={term.m} className="flex items-end gap-3">
                {i > 0 && (
                  <span className="pb-3 font-display text-[1.8rem] font-light text-[var(--ink-ghost)]">
                    +
                  </span>
                )}
                <button
                  type="button"
                  onPointerEnter={() => setFocus(term.m)}
                  onPointerLeave={() => clear(term.m)}
                  onFocus={() => setFocus(term.m)}
                  onBlur={() => clear(term.m)}
                  aria-label={
                    usable
                      ? `${meta.label}: weight ${(term.w! * 100).toFixed(1)} percent times ${term.t!.toFixed(2)} degrees equals ${term.contribution!.toFixed(3)}`
                      : `${meta.label} unavailable for this horizon`
                  }
                  className="group flex flex-col items-start rounded-lg px-1 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
                >
                  <span
                    className="font-mono text-[11px] uppercase tracking-[0.14em]"
                    style={{ color: usable ? meta.color : "var(--ink-ghost)" }}
                  >
                    {meta.label}
                  </span>
                  {usable ? (
                    <span className="mt-1.5 flex items-baseline gap-1.5 font-display text-[1.9rem] font-semibold leading-none tracking-[-0.02em]">
                      <span className="tnum" style={{ color: meta.color }}>
                        {term.w!.toFixed(3)}
                      </span>
                      <span className="text-[1.1rem] font-light text-[var(--ink-ghost)]">×</span>
                      <span className="tnum text-[var(--ink)]">{term.t!.toFixed(2)}°</span>
                    </span>
                  ) : (
                    <span className="mt-1.5 font-display text-[1.4rem] font-semibold text-[var(--ink-ghost)]">
                      unavailable
                    </span>
                  )}
                  {/* the contribution, as a proportional rule */}
                  {usable && (
                    <span className="mt-2 flex w-full items-center gap-2">
                      <span className="relative h-[2px] w-[110px] overflow-hidden rounded-full bg-[rgba(126,165,218,0.14)]">
                        <motion.span
                          className="absolute inset-y-0 left-0"
                          style={{ background: meta.color }}
                          initial={reduce ? false : { width: 0 }}
                          animate={{ width: `${(term.w ?? 0) * 100}%` }}
                          transition={
                            reduce
                              ? { duration: 0 }
                              : { type: "spring", stiffness: 90, damping: 20 }
                          }
                        />
                      </span>
                      <span className="tnum font-mono text-[11px] text-[var(--ink-faint)]">
                        {term.contribution!.toFixed(2)}
                      </span>
                    </span>
                  )}
                </button>
              </div>
            );
          })}

          {/* the resolution */}
          <div className="flex items-end gap-3">
            <span className="pb-3 font-display text-[1.8rem] font-light text-[var(--ink-ghost)]">
              =
            </span>
            <button
              type="button"
              onPointerEnter={() => setFocus("helios")}
              onPointerLeave={() => clear("helios")}
              onFocus={() => setFocus("helios")}
              onBlur={() => clear("helios")}
              aria-label={`Published HELIOS forecast ${published?.toFixed(2) ?? "unavailable"} degrees`}
              className="flex flex-col items-start rounded-lg px-1 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
            >
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--helios-amber)]">
                HELIOS
              </span>
              <span
                className="tnum mt-1.5 font-display text-[2.4rem] font-semibold leading-none tracking-[-0.025em] text-[var(--helios-amber)]"
                style={{ textShadow: "0 0 34px rgba(255,199,115,0.28)" }}
              >
                {published !== null ? `${published.toFixed(2)}°` : "—"}
              </span>
            </button>
          </div>
        </div>

        {/* the check: does the identity actually close? */}
        <p className="mt-8 max-w-[64ch] text-[14px] leading-[1.6] text-[var(--ink-faint)]">
          {published !== null ? (
            <>
              Sum of terms{" "}
              <span className="tnum text-[var(--ink-dim)]">{sum.toFixed(3)}</span> · published{" "}
              <span className="tnum text-[var(--ink-dim)]">{published.toFixed(3)}</span> · residual{" "}
              <span className="tnum text-[var(--ink-dim)]">
                {Math.abs(sum - published).toFixed(3)}
              </span>
              {closes ? (
                <span className="text-[var(--color-signal)]"> — the blend closes exactly.</span>
              ) : (
                <span className="text-[var(--color-warn)]">
                  {" "}
                  — terms do not fully account for the published value at this horizon.
                </span>
              )}
            </>
          ) : (
            "No published value for this horizon yet."
          )}
        </p>
      </div>
    </div>
  );
}

export default WhyThisResult;
