"use client";

import { useRef, useSyncExternalStore, type ReactNode } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";

/**
 * Scroll-experience primitives for the HELIOS landing page.
 *
 * Design goals (from the UI/UX Pro Max skill — spatial-ui-visionos glass +
 * subtle parallax + scrubbed scroll reveals):
 *  - The whole page reads as ONE continuous visual space, not stacked sections.
 *  - Elements ENTER → PASS → RESOLVE across their own scroll range rather than
 *    fade-in / fade-out.
 *  - All motion runs off Motion VALUES (no per-scroll React state, no scroll
 *    listeners doing React work) → production-grade performance.
 *  - Fully bypassed under prefers-reduced-motion; simplified on mobile.
 */

/* --------------------------------------------------------------- viewport */

/** SSR-safe media-query subscription (no setState-in-effect). */
function useMedia(query: string, serverDefault = false): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(query).matches,
    () => serverDefault,
  );
}

function useIsMobile(): boolean {
  return useMedia("(max-width: 820px)");
}

/** True when scroll choreography should run (motion allowed). */
export function useMotionEnabled(): boolean {
  const reduced = useReducedMotion();
  return !reduced;
}

/* ------------------------------------------------------- section scrolling */

/** Returns a spring-smoothed 0→1 progress for a section relative to viewport. */
function useSectionProgress(
  ref: React.RefObject<HTMLElement | null>,
  offset: [string, string] = ["start end", "end start"],
): MotionValue<number> {
  const { scrollYProgress } = useScroll({
    target: ref,
    // @ts-expect-error offset accepts these string edges at runtime
    offset,
  });
  return useSpring(scrollYProgress, { stiffness: 90, damping: 26, mass: 0.35 });
}

/**
 * ScrollStage — wraps a block so it ENTERS from below+blurred, PASSES sharp
 * and settled while centred, then RESOLVES (lifts + softens) as it leaves.
 * Continuous, scrubbed by the element's own scroll range. Static under
 * reduced motion.
 */
export function ScrollStage({
  children,
  className = "",
  intensity = 1,
}: {
  children: ReactNode;
  className?: string;
  intensity?: number;
}) {
  const enabled = useMotionEnabled();
  const mobile = useIsMobile();
  const ref = useRef<HTMLDivElement>(null);
  const p = useSectionProgress(ref);

  const k = mobile ? 0.5 : 1; // gentler on mobile
  // Gentle: sections rise into place and settle. They do NOT fade or blur out
  // on exit — that created readability dead-zones. Continuity comes from the
  // evolving field, glass emergence, masked headings and the pinned loop.
  const y = useTransform(p, [0, 0.4], [70 * k * intensity, 0]);
  const opacity = useTransform(p, [0, 0.18], [0, 1]);
  const scale = useTransform(p, [0, 0.4], [0.97, 1]);

  if (!enabled) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      ref={ref}
      className={`depth-raise ${className}`}
      style={{ y, opacity, scale }}
    >
      {children}
    </motion.div>
  );
}

/* ------------------------------------------------------- masked typography */

/**
 * MaskedHeading — each line sits behind a clip and lifts into view as the
 * heading enters. Engineered, not flying text: a clean vertical reveal with a
 * micro tracking settle.
 */
export function MaskedHeading({
  lines,
  className = "",
  as: Tag = "h2",
}: {
  lines: ReactNode[];
  className?: string;
  as?: "h1" | "h2" | "h3";
}) {
  const enabled = useMotionEnabled();

  if (!enabled) {
    return (
      <Tag className={className}>
        {lines.map((l, i) => (
          <span key={i} className="block">
            {l}
          </span>
        ))}
      </Tag>
    );
  }

  return (
    <Tag className={className}>
      {lines.map((l, i) => (
        <span key={i} className="mask-line">
          <motion.span
            className="block"
            initial={{ y: "110%", opacity: 0, letterSpacing: "0.04em" }}
            whileInView={{ y: "0%", opacity: 1, letterSpacing: "-0.02em" }}
            viewport={{ once: true, margin: "0px 0px -18% 0px" }}
            transition={{
              duration: 0.9,
              delay: i * 0.08,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            {l}
          </motion.span>
        </span>
      ))}
    </Tag>
  );
}
