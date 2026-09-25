"use client";

import { motion } from "motion/react";

/**
 * Floating status notice pinned to the top of the Home page below SiteNav.
 * Retains visibility during scroll while maintaining the HELIOS light-blue and white
 * aesthetic with high-contrast dark text.
 */
export function MvpStatusBanner() {
  return (
    <aside
      aria-label="HELIOS MVP Status"
      className="pointer-events-none fixed inset-x-0 top-[68px] z-40 flex justify-center px-4 md:top-[72px]"
    >
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="pointer-events-auto relative max-w-4xl overflow-hidden rounded-2xl border border-[#9bc4ef] bg-gradient-to-r from-[#d8ebfc]/95 via-[#ebf4fd]/95 to-[#d4e8fb]/95 px-4 py-2.5 shadow-[inset_0_1px_1px_rgba(255,255,255,0.85),0_8px_24px_-6px_rgba(2,10,24,0.3)] backdrop-blur-md sm:rounded-full md:px-5 md:py-2"
      >
        {/* Soft atmospheric ambient glow matching HELIOS light-blue optical theme */}
        <div
          aria-hidden
          className="pointer-events-none absolute -left-10 -top-10 h-28 w-28 rounded-full bg-[#a8d4ff]/40 blur-2xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-10 -right-10 h-28 w-28 rounded-full bg-[#bee0fc]/50 blur-2xl"
        />

        <div className="relative flex items-start gap-2.5 sm:items-center sm:gap-3">
          <span className="relative mt-1 flex h-2 w-2 shrink-0 sm:mt-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#f59b3c] opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-[#f59b3c]" />
          </span>
          <p className="font-mono text-[11px] leading-relaxed text-[#071324] sm:text-[12px]">
            <span className="font-semibold text-[#071324]">MVP — Currently implemented:</span>{" "}
            Dynamic temperature forecasting using blended GFS, IFS and ICON model outputs. Heavy rainfall, heat-wave and high-wind event guidance are actively under development.
          </p>
        </div>
      </motion.div>
    </aside>
  );
}
