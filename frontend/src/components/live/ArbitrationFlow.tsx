"use client";

import { useEffect, useRef } from "react";
import { NWP_META } from "@/lib/constants";
import { NWP_MODELS, type LiveHorizon, type NwpModel } from "@/lib/types";
import { useStage } from "@/components/stage/useStage";

/**
 * ARBITRATION FLOW — the moment HELIOS actually does its job, made spatial.
 *
 * Three real model forecasts enter from the left, travel as signals along curved
 * paths whose thickness and particle density are set by the model's REAL live
 * weight, converge on the arbitration core, and leave as one resolved forecast.
 *
 * Everything geometric is data-bound:
 *   stream thickness   ∝ nwp_weights[model]
 *   particle density   ∝ nwp_weights[model]
 *   particle speed     ∝ 0.35 + weight
 *   unavailable model  → dim, dashed, no particles (an honest absence)
 *   core intensity     ∝ how many models are actually contributing
 *   output value       = helios_temperature_c (never recomputed here)
 *
 * Nothing is invented: if the API has no value, the visual says so.
 *
 * Implementation notes:
 *  - a single 2D canvas (no extra WebGL context) with DPR capped at 2;
 *  - one rAF loop, paused when off-screen via IntersectionObserver and when the
 *    tab is hidden, so it costs nothing when unseen;
 *  - all text lives in the DOM above the canvas — crisp, selectable, readable by
 *    assistive tech — positioned from the same normalised layout the canvas uses;
 *  - reads the shared attention store imperatively, so hovering a model
 *    elsewhere on the page brightens its stream here without a React render;
 *  - under prefers-reduced-motion the geometry draws once, with no particles.
 */

/** Normalised layout shared by canvas and DOM so they always agree. */
const NODES: Record<NwpModel, { x: number; y: number }> = {
  gfs: { x: 0.085, y: 0.18 },
  ifs: { x: 0.085, y: 0.5 },
  icon: { x: 0.085, y: 0.82 },
};
const CORE = { x: 0.56, y: 0.5 };
const OUT = { x: 0.945, y: 0.5 };

interface Particle {
  m: NwpModel;
  t: number;
  speed: number;
}

export function ArbitrationFlow({
  horizon,
  className = "",
}: {
  horizon: LiveHorizon | null;
  className?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Latest data, read by the animation loop without re-creating it. Synced from
  // an effect (never written during render) so React's rules stay satisfied.
  const dataRef = useRef<LiveHorizon | null>(null);
  useEffect(() => {
    dataRef.current = horizon;
  }, [horizon]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let w = 0;
    let h = 0;
    let dpr = 1;
    const resize = () => {
      const r = wrap.getBoundingClientRect();
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, Math.floor(r.width));
      h = Math.max(1, Math.floor(r.height));
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);

    // ---- geometry helpers -------------------------------------------------
    const px = (n: { x: number; y: number }) => ({ x: n.x * w, y: n.y * h });
    /** Control points that bend each stream into the core. */
    const ctrl = (a: { x: number; y: number }, b: { x: number; y: number }) => [
      { x: a.x + (b.x - a.x) * 0.55, y: a.y },
      { x: b.x - (b.x - a.x) * 0.35, y: b.y },
    ];
    const bezier = (
      p0: { x: number; y: number },
      p1: { x: number; y: number },
      p2: { x: number; y: number },
      p3: { x: number; y: number },
      t: number,
    ) => {
      const u = 1 - t;
      return {
        x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
        y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
      };
    };

    // ---- particles: density is a function of real weight -----------------
    /**
     * A resolution event: fired only when the PUBLISHED value actually changes
     * (new location, new horizon, new cycle). This is a real event in the
     * system's life, not an idle animation — so it earns a moment.
     */
    let lastPublished: number | null = null;
    let resolveAt = -1;

    const particles: Particle[] = [];
    const seed = () => {
      particles.length = 0;
      const hz = dataRef.current;
      for (const m of NWP_MODELS) {
        const avail = hz?.nwp_availability[m] ?? false;
        const weight = avail ? (hz?.nwp_weights[m] ?? 0) : 0;
        // 3..16 particles per stream, proportional to contribution
        const n = avail ? Math.max(3, Math.round(weight * 34)) : 0;
        for (let i = 0; i < n; i++) {
          particles.push({ m, t: i / n, speed: 0.35 + weight * 1.15 });
        }
      }
    };
    seed();
    let lastWeightKey = "";

    let raf = 0;
    let visible = true;
    let time = 0;

    const io = new IntersectionObserver(
      (e) => {
        visible = e.some((x) => x.isIntersecting);
      },
      { threshold: 0.05 },
    );
    io.observe(wrap);

    const draw = (dt: number) => {
      const hz = dataRef.current;
      const focus = useStage.getState().focus;
      time += dt;

      // reseed only when the real contribution pattern changes
      const key = NWP_MODELS.map(
        (m) =>
          `${hz?.nwp_availability[m] ? 1 : 0}:${(hz?.nwp_weights[m] ?? 0).toFixed(3)}`,
      ).join("|");
      if (key !== lastWeightKey) {
        lastWeightKey = key;
        seed();
      }

      // detect a genuine publication
      const published = hz?.helios_temperature_c ?? null;
      if (published !== null && published !== lastPublished) {
        if (lastPublished !== null) resolveAt = time; // not the first paint
        lastPublished = published;
      }

      ctx.clearRect(0, 0, w, h);
      const core = px(CORE);
      const out = px(OUT);

      const contributing = NWP_MODELS.filter((m) => hz?.nwp_availability[m]).length;

      // ---- streams -------------------------------------------------------
      for (const m of NWP_MODELS) {
        const meta = NWP_META[m];
        const avail = hz?.nwp_availability[m] ?? false;
        const weight = avail ? (hz?.nwp_weights[m] ?? 0) : 0;
        const a = px(NODES[m]);
        const [c1, c2] = ctrl(a, core);
        if (!c1 || !c2) continue;

        const attended = focus === m;
        const dimmed = focus !== null && focus !== m && focus !== "helios";

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, core.x, core.y);

        if (!avail) {
          // Honest absence: a dashed, unlit path carrying nothing.
          ctx.setLineDash([3, 7]);
          ctx.strokeStyle = "rgba(126,165,218,0.20)";
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.restore();
          continue;
        }

        const grad = ctx.createLinearGradient(a.x, a.y, core.x, core.y);
        grad.addColorStop(0, meta.color);
        grad.addColorStop(1, "rgba(255,199,115,0.85)");
        ctx.strokeStyle = grad;
        // thickness carries the weight — the visual IS the arbitration
        ctx.lineWidth = (0.8 + weight * 5.2) * (attended ? 1.5 : 1);
        ctx.globalAlpha = dimmed ? 0.22 : attended ? 1 : 0.6;
        if (attended) {
          ctx.shadowColor = meta.color;
          ctx.shadowBlur = 14;
        }
        ctx.stroke();
        ctx.restore();
      }

      // ---- signal particles ---------------------------------------------
      if (!reduce) {
        for (const p of particles) {
          const meta = NWP_META[p.m];
          const a = px(NODES[p.m]);
          const [c1, c2] = ctrl(a, core);
          if (!c1 || !c2) continue;
          p.t += dt * p.speed * 0.22;
          if (p.t > 1) p.t -= 1;

          const attended = focus === p.m;
          const dimmed = focus !== null && focus !== p.m && focus !== "helios";
          const pos = bezier(a, c1, c2, core, p.t);

          // fade in from the source and into the core: signals arrive, they
          // don't just appear
          const fade = Math.sin(p.t * Math.PI);
          ctx.save();
          ctx.globalAlpha = (dimmed ? 0.18 : attended ? 1 : 0.72) * fade;
          ctx.fillStyle = meta.glow ?? meta.color;
          ctx.shadowColor = meta.color;
          ctx.shadowBlur = attended ? 12 : 7;
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, attended ? 2.5 : 1.9, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      }

      // ---- arbitration core ----------------------------------------------
      const heliosAttended = focus === "helios";
      const breath = reduce ? 0.5 : 0.5 + 0.5 * Math.sin(time * 1.5);
      const intensity = contributing === 0 ? 0.15 : 0.45 + contributing * 0.18;

      const halo = ctx.createRadialGradient(
        core.x,
        core.y,
        0,
        core.x,
        core.y,
        34 + breath * 8 + (heliosAttended ? 12 : 0),
      );
      halo.addColorStop(0, `rgba(255,199,115,${0.30 * intensity})`);
      halo.addColorStop(1, "rgba(255,199,115,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(core.x, core.y, 46 + breath * 10, 0, Math.PI * 2);
      ctx.fill();

      // the arbitration ring: closed only when models are actually contributing
      ctx.save();
      ctx.strokeStyle = `rgba(255,199,115,${heliosAttended ? 0.95 : 0.6})`;
      ctx.lineWidth = heliosAttended ? 2 : 1.4;
      ctx.beginPath();
      ctx.arc(core.x, core.y, 13 + breath * 1.6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      ctx.fillStyle = "#fff2d6";
      ctx.beginPath();
      ctx.arc(core.x, core.y, 4.2 + breath * 0.8, 0, Math.PI * 2);
      ctx.fill();

      // ---- resolution event: the forecast being published ------------------
      if (!reduce && resolveAt >= 0) {
        const age = time - resolveAt;
        const DUR = 1.15;
        if (age < DUR) {
          const k = age / DUR;
          const ease = 1 - Math.pow(1 - k, 3);
          ctx.save();
          // a single ring leaving the core: resolution propagating outward
          ctx.globalAlpha = (1 - k) * 0.85;
          ctx.strokeStyle = "rgba(255,242,214,0.95)";
          ctx.lineWidth = 2.2 * (1 - k) + 0.4;
          ctx.beginPath();
          ctx.arc(core.x, core.y, 13 + ease * 78, 0, Math.PI * 2);
          ctx.stroke();
          // and the core briefly brightens as it commits
          ctx.globalAlpha = (1 - k) * 0.5;
          ctx.fillStyle = "#fff2d6";
          ctx.beginPath();
          ctx.arc(core.x, core.y, 6 + (1 - k) * 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        } else {
          resolveAt = -1;
        }
      }

      // ---- resolved output ------------------------------------------------
      const hasOut = (hz?.helios_temperature_c ?? null) !== null;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(core.x + 15, core.y);
      ctx.lineTo(out.x, out.y);
      if (hasOut) {
        const og = ctx.createLinearGradient(core.x, core.y, out.x, out.y);
        og.addColorStop(0, "rgba(255,242,214,0.95)");
        og.addColorStop(1, "rgba(255,199,115,0.55)");
        ctx.strokeStyle = og;
        ctx.lineWidth = 2.4;
        ctx.shadowColor = "rgba(255,199,115,0.6)";
        ctx.shadowBlur = 10;
      } else {
        ctx.setLineDash([3, 7]);
        ctx.strokeStyle = "rgba(126,165,218,0.22)";
        ctx.lineWidth = 1;
      }
      ctx.stroke();
      ctx.restore();

      // a single pulse travelling out: the forecast being published
      if (!reduce && hasOut) {
        const pt = (time * 0.32) % 1;
        const x = core.x + 15 + (out.x - core.x - 15) * pt;
        ctx.save();
        ctx.globalAlpha = Math.sin(pt * Math.PI);
        ctx.fillStyle = "#fff2d6";
        ctx.shadowColor = "rgba(255,199,115,0.9)";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.arc(x, core.y, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    };

    let prev = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      if (visible && !document.hidden) draw(dt);
      raf = requestAnimationFrame(loop);
    };

    if (reduce) {
      draw(0); // one static frame: full geometry, no motion
    } else {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
    };
  }, []);

  const hz = horizon;
  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${v.toFixed(1)}°`;

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <canvas ref={canvasRef} className="absolute inset-0" aria-hidden />

      {/* All labels in the DOM: crisp, selectable, screen-reader friendly. */}
      {NWP_MODELS.map((m) => {
        const meta = NWP_META[m];
        const avail = hz?.nwp_availability[m] ?? false;
        const weight = avail ? (hz?.nwp_weights[m] ?? 0) : 0;
        const node = NODES[m];
        return (
          <div
            key={m}
            className="pointer-events-none absolute -translate-y-1/2"
            style={{ left: `${node.x * 100}%`, top: `${node.y * 100}%`, transform: "translate(-50%,-50%)" }}
          >
            <div className="flex flex-col items-center">
              <span
                className="font-display text-[1.15rem] font-semibold leading-none tracking-[-0.01em]"
                style={{ color: avail ? meta.color : "var(--ink-ghost)" }}
              >
                {meta.label}
              </span>
              <span className="tnum mt-1.5 font-mono text-[13px] text-[var(--ink-dim)]">
                {avail ? fmt(hz?.nwp_forecasts_c[m]) : "n/a"}
              </span>
              {avail && (
                <span className="tnum mt-0.5 font-mono text-[11px] text-[var(--ink-faint)]">
                  {(weight * 100).toFixed(0)}%
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* arbitration label */}
      <div
        className="pointer-events-none absolute"
        style={{ left: `${CORE.x * 100}%`, top: `${CORE.y * 100}%`, transform: "translate(-50%, 44px)" }}
      >
        <span className="t-meta whitespace-nowrap">Arbitration</span>
      </div>

      {/* resolved output */}
      <div
        className="pointer-events-none absolute"
        style={{ left: `${OUT.x * 100}%`, top: `${OUT.y * 100}%`, transform: "translate(-50%,-50%)" }}
      >
        <div className="flex flex-col items-center">
          <span className="font-display text-[1.15rem] font-semibold leading-none tracking-[-0.01em] text-[var(--helios-amber)]">
            HELIOS
          </span>
          <span className="tnum mt-1.5 font-mono text-[17px] text-[var(--ink)]">
            {fmt(hz?.helios_temperature_c)}
          </span>
        </div>
      </div>

      {/* Accessible equivalent of the whole visual. */}
      <p className="sr-only">
        {hz
          ? `Model arbitration: ${NWP_MODELS.filter((m) => hz.nwp_availability[m])
              .map(
                (m) =>
                  `${NWP_META[m].label} ${hz.nwp_forecasts_c[m]?.toFixed(1) ?? "unavailable"} degrees at ${(
                    hz.nwp_weights[m] * 100
                  ).toFixed(0)} percent weight`,
              )
              .join("; ")}. Resolved HELIOS forecast ${
              hz.helios_temperature_c?.toFixed(1) ?? "unavailable"
            } degrees.`
          : "Model arbitration diagram. Select a location to populate it."}
      </p>
    </div>
  );
}

export default ArbitrationFlow;
