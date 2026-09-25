"use client";

import { motion } from "motion/react";

interface ModelMetric {
  name: string;
  key: string;
  rmse: number;
  color: string;
  isHelios?: boolean;
}

const METRICS: ModelMetric[] = [
  { name: "GFS", key: "gfs", rmse: 3.78, color: "var(--color-gfs)" },
  { name: "ICON", key: "icon", rmse: 2.89, color: "var(--color-icon)" },
  { name: "IFS", key: "ifs", rmse: 2.61, color: "var(--color-ifs)" },
  { name: "HELIOS", key: "helios", rmse: 2.45, color: "var(--helios-amber)", isHelios: true },
];

const MAX_SCALE = 4.0;

export function PerformanceValidation() {
  return (
    <div className="surface mx-auto my-12 max-w-3xl overflow-hidden rounded-2xl border border-[rgba(126,165,218,0.18)] p-6 sm:p-8">
      <div className="flex flex-col gap-1 text-center sm:text-left">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--helios-amber)]">
          HELIOS Performance Validation
        </p>
        <h3 className="font-display text-xl font-semibold tracking-tight text-[var(--ink)] sm:text-2xl">
          Root Mean Square Error (RMSE) Comparison
        </h3>
        <p className="mt-1 font-mono text-[12px] text-[var(--ink-faint)]">
          Evaluated on 493,473 operational holdout station-forecast records across India
        </p>
      </div>

      <div className="mt-8 space-y-4">
        {METRICS.map((m) => {
          const widthPct = Math.round((m.rmse / MAX_SCALE) * 100);
          return (
            <div key={m.key} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs sm:text-sm font-mono">
                <span
                  className="font-semibold tracking-wide"
                  style={{ color: m.isHelios ? "var(--helios-amber)" : "var(--ink)" }}
                >
                  {m.name}
                  {m.isHelios && (
                    <span className="ml-2 rounded-full border border-[var(--helios-amber)]/40 bg-[var(--helios-amber)]/10 px-2 py-0.5 text-[10px] text-[var(--helios-amber)]">
                      Learned Blend
                    </span>
                  )}
                </span>
                <span className="font-mono font-medium text-[var(--ink)]">
                  {m.rmse.toFixed(2)} °C
                </span>
              </div>

              <div className="relative h-4 w-full overflow-hidden rounded-full bg-white/[0.05]">
                <motion.div
                  initial={{ width: 0 }}
                  whileInView={{ width: `${widthPct}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                  className="h-full rounded-full"
                  style={{
                    backgroundColor: m.color,
                    boxShadow: m.isHelios ? `0 0 12px ${m.color}` : "none",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex flex-col items-center justify-between gap-2 border-t border-[rgba(126,165,218,0.12)] pt-4 sm:flex-row">
        <span className="font-mono text-[11px] font-medium text-[var(--helios-amber)] sm:text-xs">
          ↓ Lower RMSE = Better Forecast Error
        </span>
        <span className="font-mono text-[11px] text-[var(--ink-dim)] sm:text-xs">
          8.6% improvement over simple multi-model average
        </span>
      </div>
    </div>
  );
}
