"use client";

import { useEffect, useRef } from "react";
import { CANDIDATE_META, NWP_META } from "@/lib/constants";
import {
  CANDIDATE_KEYS,
  NWP_MODELS,
  type CandidateKey,
  type LiveHorizon,
  type NwpModel,
} from "@/lib/types";
import { useStage } from "@/components/stage/useStage";

/**
 * LEVEL 2 — CANDIDATE ARBITRATION.
 *
 * This is the part of HELIOS that is genuinely interesting and was previously
 * invisible: the three blending candidates do not merely produce three numbers,
 * they each distribute trust across the SAME three NWP models *differently*.
 *
 * The API gives us that directly — every candidate carries its own
 * `weights: { gfs, ifs, icon }` — so this view is entirely real:
 *
 *   nine streams  = 3 models × 3 candidates
 *   thickness     ∝ candidate.weights[model]   (that candidate's trust)
 *   candidate temp = candidate.temperature_c   (its actual output)
 *   selected      = candidate.selected         (the deployed strategy)
 *   published     = helios_temperature_c       (equals the selected temp)
 *
 * Reading it: MLP leaning hard on GFS while Kernel leans on ICON is not a
 * decorative difference — it is why they disagree, and why validation picks one.
 *
 * Deliberately quiet: only the SELECTED candidate's streams carry signal
 * particles by default. Attending another candidate (hover/keyboard, anywhere in
 * the product) promotes its streams instead. Without that restraint nine
 * animated streams would be noise rather than information.
 *
 * Shares Level 1's left-hand model coordinates, so the two flows read as one
 * continuous computation rather than two diagrams.
 */

/** Same left-hand model positions as the Level 1 flow: shared coordinate system. */
const MODEL_Y: Record<NwpModel, number> = { gfs: 0.16, ifs: 0.5, icon: 0.84 };
const MODEL_X = 0.075;
const CAND_X = 0.52;
const CAND_Y: Record<CandidateKey, number> = { kernel: 0.16, xgboost: 0.5, mlp: 0.84 };
const OUT = { x: 0.94, y: 0.5 };

interface Particle {
  m: NwpModel;
  c: CandidateKey;
  t: number;
  speed: number;
}

export function CandidateArbitrationFlow({
  horizon,
  className = "",
}: {
  horizon: LiveHorizon | null;
  className?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
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
    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
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

    const bez = (
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

    const particles: Particle[] = [];
    let lastKey = "";
    const seed = () => {
      particles.length = 0;
      const hz = dataRef.current;
      const cf = hz?.candidate_forecasts ?? null;
      if (!cf) return;
      for (const c of CANDIDATE_KEYS) {
        const cand = cf[c];
        if (!cand?.available || !cand.weights) continue;
        for (const m of NWP_MODELS) {
          if (!hz?.nwp_availability[m]) continue;
          const wgt = cand.weights[m] ?? 0;
          const n = Math.max(2, Math.round(wgt * 12));
          for (let i = 0; i < n; i++) {
            particles.push({ m, c, t: i / n, speed: 0.4 + wgt * 1.1 });
          }
        }
      }
    };
    seed();

    let raf = 0;
    let visible = true;
    let time = 0;
    const io = new IntersectionObserver((e) => (visible = e.some((x) => x.isIntersecting)), {
      threshold: 0.05,
    });
    io.observe(wrap);

    const draw = (dt: number) => {
      const hz = dataRef.current;
      const focus = useStage.getState().focus;
      time += dt;

      const cf = hz?.candidate_forecasts ?? null;
      const selected = (hz?.selected_candidate ?? null) as CandidateKey | null;

      const key = JSON.stringify(
        CANDIDATE_KEYS.map((c) => [c, cf?.[c]?.available, cf?.[c]?.weights]),
      );
      if (key !== lastKey) {
        lastKey = key;
        seed();
      }

      ctx.clearRect(0, 0, w, h);
      const out = { x: OUT.x * w, y: OUT.y * h };

      const modelAttended = (m: NwpModel) => focus === m;
      const candAttended = (c: CandidateKey) => focus === c;
      const anyFocus = focus !== null && focus !== "helios";

      // ---- nine weight streams: each candidate's own trust distribution ----
      for (const c of CANDIDATE_KEYS) {
        const cand = cf?.[c];
        const cMeta = CANDIDATE_META[c];
        const cp = { x: CAND_X * w, y: CAND_Y[c] * h };

        for (const m of NWP_MODELS) {
          const mp = { x: MODEL_X * w, y: MODEL_Y[m] * h };
          const avail = (hz?.nwp_availability[m] ?? false) && (cand?.available ?? false);
          const wgt = avail ? (cand?.weights?.[m] ?? 0) : 0;

          const c1 = { x: mp.x + (cp.x - mp.x) * 0.5, y: mp.y };
          const c2 = { x: cp.x - (cp.x - mp.x) * 0.4, y: cp.y };

          const lit =
            candAttended(c) || modelAttended(m) || (!anyFocus && c === selected);
          const dim = anyFocus && !candAttended(c) && !modelAttended(m);

          ctx.save();
          ctx.beginPath();
          ctx.moveTo(mp.x, mp.y);
          ctx.bezierCurveTo(c1.x, c1.y, c2.x, c2.y, cp.x, cp.y);

          if (!avail) {
            ctx.setLineDash([2, 6]);
            ctx.strokeStyle = "rgba(126,165,218,0.14)";
            ctx.lineWidth = 0.8;
          } else {
            const g = ctx.createLinearGradient(mp.x, mp.y, cp.x, cp.y);
            g.addColorStop(0, NWP_META[m].color);
            g.addColorStop(1, cMeta.color);
            ctx.strokeStyle = g;
            // thickness IS the candidate's trust in that model
            ctx.lineWidth = 0.6 + wgt * 4.4 * (lit ? 1.4 : 1);
            ctx.globalAlpha = dim ? 0.12 : lit ? 0.9 : 0.3;
            if (lit) {
              ctx.shadowColor = cMeta.color;
              ctx.shadowBlur = 10;
            }
          }
          ctx.stroke();
          ctx.restore();
        }
      }

      // ---- signal particles: only the deployed (or attended) candidate ----
      if (!reduce) {
        for (const p of particles) {
          const promoted =
            candAttended(p.c) || modelAttended(p.m) || (!anyFocus && p.c === selected);
          if (!promoted) continue;
          const mp = { x: MODEL_X * w, y: MODEL_Y[p.m] * h };
          const cp = { x: CAND_X * w, y: CAND_Y[p.c] * h };
          const c1 = { x: mp.x + (cp.x - mp.x) * 0.5, y: mp.y };
          const c2 = { x: cp.x - (cp.x - mp.x) * 0.4, y: cp.y };
          p.t += dt * p.speed * 0.2;
          if (p.t > 1) p.t -= 1;
          const pos = bez(mp, c1, c2, cp, p.t);
          ctx.save();
          ctx.globalAlpha = Math.sin(p.t * Math.PI) * 0.95;
          ctx.fillStyle = NWP_META[p.m].glow ?? NWP_META[p.m].color;
          ctx.shadowColor = NWP_META[p.m].color;
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, 1.8, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      }

      // ---- candidate resolution nodes -------------------------------------
      for (const c of CANDIDATE_KEYS) {
        const cand = cf?.[c];
        const cMeta = CANDIDATE_META[c];
        const cp = { x: CAND_X * w, y: CAND_Y[c] * h };
        const isSel = cand?.selected ?? c === selected;
        const attended = candAttended(c);
        const dim = anyFocus && !attended;
        const breath = reduce ? 0.5 : 0.5 + 0.5 * Math.sin(time * 1.4 + CAND_Y[c] * 6);

        ctx.save();
        ctx.globalAlpha = dim ? 0.3 : 1;
        if (cand?.available) {
          const halo = ctx.createRadialGradient(cp.x, cp.y, 0, cp.x, cp.y, isSel ? 26 : 15);
          halo.addColorStop(0, `${cMeta.color}${isSel ? "55" : "2a"}`);
          halo.addColorStop(1, "rgba(0,0,0,0)");
          ctx.fillStyle = halo;
          ctx.beginPath();
          ctx.arc(cp.x, cp.y, isSel ? 30 : 18, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = cMeta.color;
          ctx.lineWidth = isSel || attended ? 1.8 : 1;
          ctx.beginPath();
          ctx.arc(cp.x, cp.y, 8 + (isSel ? breath * 1.4 : 0), 0, Math.PI * 2);
          ctx.stroke();

          if (isSel) {
            ctx.fillStyle = "#fff2d6";
            ctx.beginPath();
            ctx.arc(cp.x, cp.y, 3.2, 0, Math.PI * 2);
            ctx.fill();
          }
        } else {
          ctx.strokeStyle = "rgba(126,165,218,0.22)";
          ctx.setLineDash([2, 4]);
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(cp.x, cp.y, 8, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.restore();

        // ---- publication path: only the validated candidate is deployed ----
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(cp.x + 10, cp.y);
        ctx.bezierCurveTo(
          cp.x + (out.x - cp.x) * 0.5,
          cp.y,
          out.x - (out.x - cp.x) * 0.4,
          out.y,
          out.x,
          out.y,
        );
        if (isSel && cand?.available) {
          const g = ctx.createLinearGradient(cp.x, cp.y, out.x, out.y);
          g.addColorStop(0, cMeta.color);
          g.addColorStop(1, "rgba(255,242,214,0.95)");
          ctx.strokeStyle = g;
          ctx.lineWidth = 2.6;
          ctx.shadowColor = "rgba(255,199,115,0.55)";
          ctx.shadowBlur = 12;
        } else {
          // it ran, it just was not deployed — visible but unlit
          ctx.setLineDash([2, 7]);
          ctx.strokeStyle = "rgba(126,165,218,0.18)";
          ctx.lineWidth = 0.9;
        }
        ctx.stroke();
        ctx.restore();
      }

      // ---- the published forecast -----------------------------------------
      const hasOut = (hz?.helios_temperature_c ?? null) !== null;
      const breath = reduce ? 0.5 : 0.5 + 0.5 * Math.sin(time * 1.6);
      if (hasOut) {
        const halo = ctx.createRadialGradient(out.x, out.y, 0, out.x, out.y, 30 + breath * 8);
        halo.addColorStop(0, "rgba(255,199,115,0.34)");
        halo.addColorStop(1, "rgba(255,199,115,0)");
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(out.x, out.y, 38, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#fff2d6";
        ctx.beginPath();
        ctx.arc(out.x, out.y, 4.4 + breath * 0.7, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    let prev = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.05, (now - prev) / 1000);
      prev = now;
      if (visible && !document.hidden) draw(dt);
      raf = requestAnimationFrame(loop);
    };
    if (reduce) draw(0);
    else raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
    };
  }, []);

  const hz = horizon;
  const cf = hz?.candidate_forecasts ?? null;
  const selected = (hz?.selected_candidate ?? null) as CandidateKey | null;
  const fmt = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${v.toFixed(1)}°`;

  const setFocus = (t: FocusLike) => useStage.getState().setFocus(t);
  const clearFocus = (t: FocusLike) => {
    if (useStage.getState().focus === t) useStage.getState().setFocus(null);
  };

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <canvas ref={canvasRef} className="absolute inset-0" aria-hidden />

      {/* Level 1 inputs — same coordinates as the Level 1 flow */}
      {NWP_MODELS.map((m) => (
        <button
          key={m}
          type="button"
          onPointerEnter={() => setFocus(m)}
          onPointerLeave={() => clearFocus(m)}
          onFocus={() => setFocus(m)}
          onBlur={() => clearFocus(m)}
          aria-label={`Highlight ${NWP_META[m].label} across all candidates`}
          className="absolute inline-flex min-h-[44px] flex-col items-center justify-center rounded-lg px-2 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
          style={{
            left: `${MODEL_X * 100}%`,
            top: `${MODEL_Y[m] * 100}%`,
            transform: "translate(-50%,-50%)",
          }}
        >
          <span
            className="font-display text-[1.05rem] font-semibold leading-none"
            style={{ color: hz?.nwp_availability[m] ? NWP_META[m].color : "var(--ink-ghost)" }}
          >
            {NWP_META[m].label}
          </span>
        </button>
      ))}

      {/* Level 2 candidates — each with its real output */}
      {CANDIDATE_KEYS.map((c) => {
        const cand = cf?.[c];
        const meta = CANDIDATE_META[c];
        const isSel = cand?.selected ?? c === selected;
        return (
          <button
            key={c}
            type="button"
            onPointerEnter={() => setFocus(c)}
            onPointerLeave={() => clearFocus(c)}
            onFocus={() => setFocus(c)}
            onBlur={() => clearFocus(c)}
            aria-label={`Highlight ${meta.label}${isSel ? ", the deployed method" : ""}, ${
              cand?.temperature_c != null ? `${cand.temperature_c.toFixed(1)} degrees` : "unavailable"
            }`}
            className="absolute inline-flex min-h-[44px] flex-col items-center rounded-lg px-2 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
            style={{
              left: `${CAND_X * 100}%`,
              top: `${CAND_Y[c] * 100}%`,
              transform: "translate(-50%, -170%)",
            }}
          >
            <span
              className="font-display text-[1.05rem] font-semibold leading-none"
              style={{ color: cand?.available ? meta.color : "var(--ink-ghost)" }}
            >
              {meta.short}
            </span>
            <span className="tnum mt-1 font-mono text-[12px] text-[var(--ink-dim)]">
              {cand?.available ? fmt(cand.temperature_c) : "n/a"}
            </span>
            {isSel && (
              <span className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--helios-amber)]">
                deployed
              </span>
            )}
          </button>
        );
      })}

      {/* the published forecast */}
      <div
        className="pointer-events-none absolute"
        style={{ left: `${OUT.x * 100}%`, top: `${OUT.y * 100}%`, transform: "translate(-50%,-50%)" }}
      >
        <div className="flex flex-col items-center">
          <span className="font-display text-[1.05rem] font-semibold leading-none text-[var(--helios-amber)]">
            HELIOS
          </span>
          <span className="tnum mt-1 font-mono text-[16px] text-[var(--ink)]">
            {fmt(hz?.helios_temperature_c)}
          </span>
        </div>
      </div>

      <p className="sr-only">
        {cf
          ? `Level two candidate arbitration. ${CANDIDATE_KEYS.map((c) => {
              const cand = cf[c];
              if (!cand?.available) return `${CANDIDATE_META[c].label} unavailable`;
              const wts = cand.weights
                ? NWP_MODELS.map(
                    (m) => `${NWP_META[m].label} ${((cand.weights?.[m] ?? 0) * 100).toFixed(0)} percent`,
                  ).join(", ")
                : "no weights";
              return `${CANDIDATE_META[c].label} predicts ${cand.temperature_c?.toFixed(1) ?? "n/a"} degrees, weighting ${wts}${
                cand.selected ? ", and is the deployed method" : ""
              }`;
            }).join(". ")}.`
          : "Candidate arbitration diagram. Select a location to populate it."}
      </p>
    </div>
  );
}

type FocusLike = "gfs" | "ifs" | "icon" | "kernel" | "xgboost" | "mlp";

export default CandidateArbitrationFlow;
