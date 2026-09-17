"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { NWP_META, INDIA_BOUNDS } from "@/lib/constants";
import { useStage } from "@/components/stage/useStage";
import { projectIndia, unprojectIndia } from "@/lib/format";
import type { NwpModel, StationLocation } from "@/lib/types";

/**
 * INDIA MAP — the hero (SVG, reliable-by-design, GPU-independent).
 *
 * Renders real geography from the repository's own assets:
 *  - national outline (`/geo/india.json`) — visually strongest,
 *  - state/UT boundaries + names (`/geo/india_states.json`, real simplified GADM
 *    geometry with polylabel interior label points) — subtle, subordinate.
 *
 * Behaviour is unchanged: the station network is invisible; clicking anywhere
 * resolves the coordinate; pan/zoom; a single elegant "lock-on" marker for the
 * selected location. No WebGL, no tiles, no station dots.
 */

const VB = { w: 1000, h: 1000 };
const MIN_ZOOM = 1;
const MAX_ZOOM = 6;

interface IndiaGeo {
  rings: Array<Array<[number, number]>>;
}
interface StateFeature {
  name: string;
  label: string;
  labelPoint: [number, number] | null;
  area: number;
  rings: Array<Array<[number, number]>>;
}
interface StatesGeo {
  states: StateFeature[];
}

function toSvg(lat: number, lon: number) {
  const { x, y } = projectIndia(lat, lon);
  return { x: x * VB.w, y: y * VB.h };
}

function ringToPath(ring: Array<[number, number]>): string {
  return (
    ring
      .map((c, i) => {
        const p = toSvg(c[1], c[0]);
        return `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      })
      .join(" ") + " Z"
  );
}

export function IndiaMap({
  selected,
  onResolveCoordinate,
  modelPoints,
  className,
}: {
  selected: StationLocation | null;
  onResolveCoordinate: (lat: number, lon: number) => void;
  /**
   * The grid cell each model ACTUALLY sampled for this forecast, straight from
   * the API. Rendering these turns the map from a picker into an observation
   * surface: you can see that three different models resolved three different
   * nearby cells. Never synthesised — absent models simply do not appear.
   */
  modelPoints?: Partial<Record<NwpModel, { latitude: number; longitude: number; distance_to_station_km: number }>>;
  className?: string;
}) {
  const reduce = useReducedMotion();
  /** Which model the visitor is attending to, so the map can answer. */
  const stageFocus = useStage((st) => st.focus);
  const svgRef = useRef<SVGSVGElement>(null);
  const [geo, setGeo] = useState<IndiaGeo | null>(null);
  const [states, setStates] = useState<StatesGeo | null>(null);
  const [view, setView] = useState({ zoom: 1, cx: VB.w / 2, cy: VB.h / 2 });
  const [cursor, setCursor] = useState<{ lat: number; lon: number } | null>(null);
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const moved = useRef(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch("/geo/india.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: IndiaGeo | null) => alive && d?.rings && setGeo(d))
      .catch(() => {});
    fetch("/geo/india_states.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d: StatesGeo | null) => alive && d?.states && setStates(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const nationalPaths = useMemo(() => (geo ? geo.rings.map(ringToPath) : []), [geo]);
  const statePaths = useMemo(
    () =>
      states
        ? states.states.map((s) => ({
            name: s.name,
            d: s.rings.map(ringToPath).join(" "),
          }))
        : [],
    [states],
  );

  const graticule = useMemo(() => {
    const lines: string[] = [];
    for (let lat = 10; lat <= 35; lat += 5) {
      const a = toSvg(lat, INDIA_BOUNDS.lonMin);
      const b = toSvg(lat, INDIA_BOUNDS.lonMax);
      lines.push(`M${a.x},${a.y} L${b.x},${b.y}`);
    }
    for (let lon = 70; lon <= 95; lon += 5) {
      const a = toSvg(INDIA_BOUNDS.latMin, lon);
      const b = toSvg(INDIA_BOUNDS.latMax, lon);
      lines.push(`M${a.x},${a.y} L${b.x},${b.y}`);
    }
    return lines;
  }, []);

  const vb = useMemo(() => {
    const w = VB.w / view.zoom;
    const h = VB.h / view.zoom;
    const x = Math.min(Math.max(view.cx - w / 2, 0), VB.w - w);
    const y = Math.min(Math.max(view.cy - h / 2, 0), VB.h - h);
    return { x, y, w, h };
  }, [view]);

  const clientToViewBox = useCallback(
    (clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) return null;
      const r = svg.getBoundingClientRect();
      const nx = (clientX - r.left) / r.width;
      const ny = (clientY - r.top) / r.height;
      return { x: vb.x + nx * vb.w, y: vb.y + ny * vb.h };
    },
    [vb],
  );
  const vbToCoord = (x: number, y: number) => unprojectIndia(x / VB.w, y / VB.h);

  const onWheel = useCallback(
    (e: React.WheelEvent<SVGSVGElement>) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
      setView((v) => {
        const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * factor));
        const at = clientToViewBox(e.clientX, e.clientY);
        return at ? { zoom, cx: at.x, cy: at.y } : { ...v, zoom };
      });
    },
    [clientToViewBox],
  );

  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy };
    moved.current = false;
    setDragging(true);
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const at = clientToViewBox(e.clientX, e.clientY);
    if (at) setCursor(vbToCoord(at.x, at.y));
    if (!drag.current) return;
    const svg = svgRef.current;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const dx = ((e.clientX - drag.current.x) / r.width) * vb.w;
    const dy = ((e.clientY - drag.current.y) / r.height) * vb.h;
    if (Math.abs(e.clientX - drag.current.x) + Math.abs(e.clientY - drag.current.y) > 3) moved.current = true;
    setView((v) => ({ ...v, cx: drag.current!.cx - dx, cy: drag.current!.cy - dy }));
  };
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    const wasDrag = moved.current;
    drag.current = null;
    setDragging(false);
    if (wasDrag) return;
    const at = clientToViewBox(e.clientX, e.clientY);
    if (!at) return;
    const { lat, lon } = vbToCoord(at.x, at.y);
    onResolveCoordinate(lat, lon);
  };

  const zoomBy = (f: number) =>
    setView((v) => ({ ...v, zoom: Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * f)) }));
  const reset = () => setView({ zoom: 1, cx: VB.w / 2, cy: VB.h / 2 });

  const sel =
    selected && selected.latitude !== null && selected.longitude !== null
      ? toSvg(selected.latitude, selected.longitude)
      : null;
  const markerR = 5 / view.zoom;

  // Label sizing scales inversely with zoom so on-screen size stays stable.
  // 11.5 SVG units divided by zoom keeps the rendered label a constant ~11.5px
  const labelSize = 11.5 / view.zoom;
  // Only show state labels for states large enough at the current zoom, and hide
  // the smallest ones when zoomed out to avoid clutter / overlap.
  const areaThreshold = view.zoom >= 3 ? 0.4 : view.zoom >= 2 ? 1.5 : 4;

  return (
    <div className={className} style={{ position: "relative" }}>
      <svg
        ref={svgRef}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        className="h-full w-full touch-none select-none"
        style={{ cursor: dragging ? "grabbing" : "crosshair", display: "block" }}
        role="application"
        aria-label="Interactive map of India. Click anywhere to get its forecast."
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => {
          drag.current = null;
          setDragging(false);
          setCursor(null);
        }}
        onDoubleClick={reset}
      >
        <defs>
          <radialGradient id="ocean" cx="50%" cy="28%" r="95%">
            <stop offset="0%" stopColor="#0a1626" />
            <stop offset="55%" stopColor="#070d18" />
            <stop offset="100%" stopColor="#04070c" />
          </radialGradient>
          <radialGradient id="land-glow" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor="rgba(90,150,220,0.12)" />
            <stop offset="100%" stopColor="rgba(90,150,220,0)" />
          </radialGradient>
          <filter id="coast-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* ocean + atmospheric wash */}
        <rect x={0} y={0} width={VB.w} height={VB.h} fill="url(#ocean)" />
        <rect x={0} y={0} width={VB.w} height={VB.h} fill="url(#land-glow)" />

        {/* graticule */}
        <g opacity={0.5}>
          {graticule.map((d, i) => (
            <path key={i} d={d} stroke="rgba(120,160,200,0.08)" strokeWidth={0.7 / view.zoom} fill="none" />
          ))}
        </g>

        {/* national landmass — outer glow + fill (strongest identity) */}
        {nationalPaths.map((d, i) => (
          <g key={`n${i}`}>
            <path d={d} fill="none" stroke="rgba(60,130,210,0.35)" strokeWidth={5 / view.zoom} filter="url(#coast-glow)" />
            <path d={d} fill="#0f2436" fillOpacity={0.96} />
          </g>
        ))}

        {/* state/UT boundaries — subtle, subordinate to the national outline */}
        <g>
          {statePaths.map((s) => (
            <path
              key={s.name}
              d={s.d}
              fill="rgba(30,70,110,0.08)"
              stroke="rgba(120,170,220,0.22)"
              strokeWidth={0.6 / view.zoom}
              strokeLinejoin="round"
            />
          ))}
        </g>

        {/* national coastline on top — crisp */}
        {nationalPaths.map((d, i) => (
          <path
            key={`c${i}`}
            d={d}
            fill="none"
            stroke="#7cc0f5"
            strokeWidth={1.2 / view.zoom}
            strokeLinejoin="round"
            opacity={0.7}
          />
        ))}

        {/* state names at robust interior label points */}
        <g>
          {states?.states.map((s) => {
            if (!s.labelPoint || s.area < areaThreshold) return null;
            const p = toSvg(s.labelPoint[1], s.labelPoint[0]);
            return (
              <text
                key={s.name}
                x={p.x}
                y={p.y}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={labelSize}
                fontFamily="var(--font-jetbrains), monospace"
                letterSpacing={0.4 / view.zoom}
                fill="rgba(190,214,240,0.62)"
                style={{ textTransform: "uppercase", pointerEvents: "none" }}
              >
                {s.label}
              </text>
            );
          })}
        </g>

        {/* ---- model observation cells (real API grid points) ------------- */}
        {sel && modelPoints && (
          <g>
            {(Object.keys(modelPoints) as NwpModel[]).map((m) => {
              const gp = modelPoints[m];
              if (!gp) return null;
              const pt = toSvg(gp.latitude, gp.longitude);
              const meta = NWP_META[m];
              const attended = stageFocus === m;
              const dimmed = stageFocus !== null && stageFocus !== m && stageFocus !== "helios";
              const o = dimmed ? 0.2 : attended ? 1 : 0.7;
              return (
                <g key={m} opacity={o}>
                  {/* the model reached from its cell to the requested point */}
                  <line
                    x1={pt.x}
                    y1={pt.y}
                    x2={sel.x}
                    y2={sel.y}
                    stroke={meta.color}
                    strokeWidth={(attended ? 1.1 : 0.7) / view.zoom}
                    strokeDasharray={`${2 / view.zoom} ${2.5 / view.zoom}`}
                  />
                  {/* the sampled cell itself */}
                  <rect
                    x={pt.x - markerR * 1.5}
                    y={pt.y - markerR * 1.5}
                    width={markerR * 3}
                    height={markerR * 3}
                    fill={meta.color}
                    fillOpacity={attended ? 0.35 : 0.16}
                    stroke={meta.color}
                    strokeWidth={(attended ? 1.2 : 0.8) / view.zoom}
                  />
                  {!reduce && attended && (
                    <motion.rect
                      x={pt.x - markerR * 1.5}
                      y={pt.y - markerR * 1.5}
                      width={markerR * 3}
                      height={markerR * 3}
                      fill="none"
                      stroke={meta.glow}
                      strokeWidth={1 / view.zoom}
                      initial={{ opacity: 0.9, scale: 1 }}
                      animate={{ opacity: [0.9, 0, 0], scale: [1, 2.1, 2.1] }}
                      transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
                      style={{ transformOrigin: `${pt.x}px ${pt.y}px` }}
                    />
                  )}
                </g>
              );
            })}
          </g>
        )}

        {/* selected "lock-on" marker */}
        {sel && (
          <g>
            {!reduce && (
              <motion.circle
                cx={sel.x}
                cy={sel.y}
                fill="none"
                stroke="var(--helios-amber)"
                strokeWidth={1.3 / view.zoom}
                initial={{ r: markerR, opacity: 0.9 }}
                animate={{ r: [markerR, markerR * 4.5, markerR * 4.5], opacity: [0.85, 0, 0] }}
                transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut" }}
              />
            )}
            <circle cx={sel.x} cy={sel.y} r={markerR * 2} fill="var(--helios-amber)" opacity={0.2} />
            <circle cx={sel.x} cy={sel.y} r={markerR} fill="var(--helios-amber-core)" stroke="var(--helios-amber)" strokeWidth={1 / view.zoom} />
          </g>
        )}
      </svg>

      {/* What the coloured cells mean. Appears only when they exist; plain type
          on the map surface, no panel. */}
      {sel && modelPoints && Object.keys(modelPoints).length > 0 && (
        <div className="pointer-events-auto absolute bottom-3 left-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--ink-faint)]">
            sampled cells
          </span>
          {(Object.keys(modelPoints) as NwpModel[]).map((m) => {
            const gp = modelPoints[m];
            if (!gp) return null;
            const meta = NWP_META[m];
            const attended = stageFocus === m;
            return (
              <button
                key={m}
                type="button"
                onPointerEnter={() => useStage.getState().setFocus(m)}
                onPointerLeave={() =>
                  useStage.getState().focus === m && useStage.getState().setFocus(null)
                }
                onFocus={() => useStage.getState().setFocus(m)}
                onBlur={() =>
                  useStage.getState().focus === m && useStage.getState().setFocus(null)
                }
                aria-label={`Highlight ${meta.label} sampled cell, ${gp.distance_to_station_km.toFixed(0)} km away`}
                className="inline-flex min-h-[44px] items-center gap-1.5 rounded-full px-1 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]"
              >
                <span
                  className="h-2 w-2"
                  style={{
                    background: meta.color,
                    opacity: attended ? 1 : 0.55,
                    boxShadow: attended ? `0 0 9px ${meta.color}` : "none",
                  }}
                />
                <span
                  className="font-mono text-[11px] tracking-[0.06em]"
                  style={{ color: attended ? meta.color : "var(--ink-faint)" }}
                >
                  {meta.label}
                </span>
                <span className="tnum font-mono text-[11px] text-[var(--ink-ghost)]">
                  {gp.distance_to_station_km.toFixed(0)}km
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* live cursor coordinate */}
      {cursor && (
        <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/45 px-3 py-1 backdrop-blur-md">
          <span className="tnum font-mono text-[11px] text-[var(--ink-dim)]">
            {Math.abs(cursor.lat).toFixed(2)}°N {Math.abs(cursor.lon).toFixed(2)}°E
          </span>
        </div>
      )}

      {/* zoom controls */}
      <div className="absolute bottom-4 right-4 flex flex-col overflow-hidden rounded-full border border-white/10 bg-black/40 backdrop-blur-md">
        <button onClick={() => zoomBy(1.35)} aria-label="Zoom in" className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center font-mono text-[16px] leading-none text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]">
          +
        </button>
        <span className="h-px bg-white/10" />
        <button onClick={() => zoomBy(1 / 1.35)} aria-label="Zoom out" className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center font-mono text-[16px] leading-none text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]">
          −
        </button>
      </div>
    </div>
  );
}
