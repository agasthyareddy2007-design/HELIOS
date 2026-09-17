"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

/**
 * CINEMATIC INTRO
 * ---------------
 * Plays the HELIOS cinematic intro (public/heliosintro.mp4) full-screen, then
 * fades to black and reveals the forecast application directly. The video
 * already carries the HELIOS identity, so there is NO separate landing/welcome
 * page — when it ends, the app is underneath.
 *
 * - Autoplays muted + inline (browser-safe), skippable at any time.
 * - Respects prefers-reduced-motion (brief title, then reveal).
 * - Plays once per browser session; later navigations reveal the app instantly.
 * - Degrades to an immediate reveal if the asset is missing / autoplay blocked.
 */
const VIDEO_SRC = "/heliosintro.mp4";
const SESSION_KEY = "helios.intro.seen";
const FADE_S = 0.9;

type Phase = "playing" | "fading" | "done";

export function CinematicIntro({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [phase, setPhase] = useState<Phase>("playing");
  const [ready, setReady] = useState(false);
  /**
   * The intro branches on `prefers-reduced-motion`, which the server cannot
   * know. Reporting "not mounted" for the server snapshot and "mounted" on the
   * client removes the server/client divergence that caused a hydration
   * mismatch (React #418) — without a setState-in-effect cascade.
   */
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  /**
   * Whether this visit skips the intro (already seen this session, or
   * `?nointro`). Resolved before first paint so the <video> is never mounted for
   * a skipped visit — previously it mounted, began fetching, and was torn down,
   * which surfaced as an aborted media request.
   */
  const skipIntro = useSyncExternalStore(
    () => () => {},
    () => {
      try {
        if (sessionStorage.getItem(SESSION_KEY) === "1") return true;
      } catch {
        /* storage unavailable — fall through to the query check */
      }
      return new URLSearchParams(window.location.search).has("nointro");
    },
    () => false,
  );
  const done = useRef(false);

  const finish = useCallback(() => {
    if (done.current) return;
    done.current = true;
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      /* non-fatal */
    }
    onDone();
  }, [onDone]);

  const beginFade = useCallback(() => {
    setPhase((p) => (p === "playing" ? "fading" : p));
    const t = setTimeout(finish, FADE_S * 1000);
    return () => clearTimeout(t);
  }, [finish]);

  // Release the video on unmount so an in-flight fetch is torn down cleanly
  // instead of surfacing as an aborted request.
  useEffect(() => {
    const v = videoRef.current;
    return () => {
      if (!v) return;
      try {
        v.pause();
        v.removeAttribute("src");
        v.load();
      } catch {
        /* nothing useful to do if the element is already gone */
      }
    };
  }, []);

  // Skip the intro entirely if already seen this session, or if ?nointro is set.
  useEffect(() => {
    if (!skipIntro) return;
    done.current = true;
    const id = requestAnimationFrame(() => {
      onDone();
      setPhase("done");
    });
    return () => cancelAnimationFrame(id);
  }, [onDone, skipIntro]);

  // Keyboard skip.
  useEffect(() => {
    if (phase === "done") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        beginFade();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, beginFade]);

  // Reduced motion: show a brief title instead of the full cinematic.
  useEffect(() => {
    if (!reduce || phase === "done" || done.current) return;
    const t = setTimeout(beginFade, 1200);
    return () => clearTimeout(t);
  }, [reduce, phase, beginFade]);

  // Try autoplay; degrade to reveal if blocked.
  useEffect(() => {
    if (reduce) return;
    const v = videoRef.current;
    const p = v?.play?.();
    if (p && typeof p.catch === "function") p.catch(() => beginFade());
  }, [reduce, beginFade]);

  if (!mounted || skipIntro || phase === "done") return null;

  return (
    <AnimatePresence>
      <motion.div
        key="intro"
        className="fixed inset-0 z-[200] flex items-center justify-center overflow-hidden bg-black"
        initial={{ opacity: 1 }}
        animate={{ opacity: phase === "fading" ? 0 : 1 }}
        transition={{ duration: FADE_S, ease: [0.16, 1, 0.3, 1] }}
        onAnimationComplete={() => phase === "fading" && setPhase("done")}
        role="img"
        aria-label="HELIOS cinematic introduction"
      >
        {reduce ? (
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="font-mono text-[12px] uppercase tracking-[0.5em] text-[var(--helios-amber)]/85">
              HELIOS
            </span>
            <span className="text-4xl font-extralight tracking-[0.06em] text-white sm:text-6xl">
              Intelligent weather forecast blending
            </span>
          </div>
        ) : (
          <>
            <video
              ref={videoRef}
              className="h-full w-full object-cover"
              src={VIDEO_SRC}
              muted
              playsInline
              autoPlay
              preload="metadata"
              onCanPlay={() => setReady(true)}
              onEnded={beginFade}
              onError={beginFade}
            />
            {!ready && (
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="font-mono text-[11px] uppercase tracking-[0.5em] text-white/50">
                  HELIOS
                </span>
              </div>
            )}
          </>
        )}

        {phase === "playing" && (
          <button
            onClick={beginFade}
            className="absolute bottom-6 right-6 z-10 inline-flex min-h-[44px] items-center rounded-full border border-white/25 bg-black/40 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.2em] text-white/70 backdrop-blur-md transition-colors hover:border-[var(--helios-amber)]/60 hover:text-[var(--helios-amber)]"
            aria-label="Skip the introduction"
          >
            Skip →
          </button>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
