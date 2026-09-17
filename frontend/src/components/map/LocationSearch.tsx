"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { StationLocation } from "@/lib/types";

/**
 * LOCATION SEARCH — a premium command-style search over supported Indian places.
 *
 * Presents only human place names + coordinates (never internal station IDs).
 * Selecting a result moves the map and updates the forecast (parent-handled).
 */
export function LocationSearch({
  locations,
  onSelect,
}: {
  locations: StationLocation[];
  onSelect: (s: StationLocation) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);

  const named = useMemo(
    () => locations.filter((s) => s.name && s.latitude !== null && s.longitude !== null),
    [locations],
  );
  const results = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) return [];
    return named.filter((s) => (s.name ?? "").toLowerCase().includes(query)).slice(0, 7);
  }, [q, named]);

  return (
    <div className="relative">
      <div
        className="flex items-center gap-3 rounded-2xl px-4 py-3 transition-all duration-300"
        style={{
          background: "linear-gradient(160deg, rgba(16,26,40,0.7), rgba(8,13,22,0.5))",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          border: `1px solid ${focused ? "rgba(255,199,115,0.4)" : "rgba(120,160,210,0.14)"}`,
          boxShadow: focused ? "0 0 0 3px rgba(255,199,115,0.06)" : "none",
        }}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="11" cy="11" r="7" stroke={focused ? "var(--helios-amber)" : "var(--ink-faint)"} strokeWidth="1.6" />
          <path d="M20 20L16.5 16.5" stroke={focused ? "var(--helios-amber)" : "var(--ink-faint)"} strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            setOpen(true);
            setFocused(true);
          }}
          onBlur={() => {
            setTimeout(() => setOpen(false), 150);
            setFocused(false);
          }}
          placeholder="Search a place in India"
          aria-label="Search a supported location in India"
          className="min-h-[44px] w-full bg-transparent font-mono text-[15px] tracking-[0.02em] text-[var(--ink)] placeholder:text-[var(--ink-dim)] focus:outline-none"
        />
        <span className="hidden font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--ink-faint)]/60 sm:inline">
          ⏎
        </span>
      </div>

      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.ul
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18 }}
            className="absolute z-30 mt-2 w-full overflow-hidden rounded-2xl py-1.5"
            style={{
              background: "linear-gradient(160deg, rgba(16,26,40,0.92), rgba(8,13,22,0.85))",
              backdropFilter: "blur(24px)",
              WebkitBackdropFilter: "blur(24px)",
              border: "1px solid rgba(120,160,210,0.16)",
              boxShadow: "0 24px 60px -28px rgba(0,0,0,0.85)",
            }}
          >
            {results.map((s) => (
              <li key={s.station}>
                <button
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onSelect(s);
                    setQ(s.name ?? "");
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[var(--helios-amber)]/[0.06]"
                >
                  <span className="text-[14px] text-[var(--ink)]">{s.name}</span>
                  <span className="tnum font-mono text-[11px] text-[var(--ink-faint)]">
                    {Math.abs(s.latitude as number).toFixed(1)}°N {Math.abs(s.longitude as number).toFixed(1)}°E
                  </span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
