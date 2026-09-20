import { INDIA_BOUNDS } from "./constants";

const EM_DASH = "—";

/** Temperature with fixed decimals; honest placeholder when unavailable. */
export function degC(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return `${v.toFixed(digits)}°`;
}

/** Bare number, no unit. */
export function num(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return v.toFixed(digits);
}

/** MAE-style value in °C with 4 significant decimals (matches artifacts). */
export function mae(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return `${v.toFixed(digits)}°C`;
}

/** Weight as a percentage string. */
export function weightPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return `${(v * 100).toFixed(digits)}%`;
}

/** Signed percentage, used for improvements. */
export function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return `${v.toFixed(digits)}%`;
}

/** Signed bias value. */
export function signed(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${s}${Math.abs(v).toFixed(digits)}`;
}

export function int(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return v.toLocaleString("en-IN");
}

/**
 * Parse the backend datetime strings, which arrive in two shapes:
 *   "2025-01-01 00:00:00.000000"  (DB rows / samples / issue-times)
 *   "2025-01-01T00:00:00"         (forecast response, ISO)
 *   "2025-01-01T00:00:00Z"        (explicit UTC)
 * They are UTC timestamps (NWP model cycles are UTC).
 */
export function parseApiDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const str = s.trim();
  const iso = str.includes("T") ? str : str.replace(" ", "T");
  const withZ = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(withZ);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** e.g. "01 Jan 2025 · 00:00Z" */
export function formatCycle(s: string | null | undefined): string {
  const d = parseApiDate(s);
  if (!d) return EM_DASH;
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" }).slice(0, 3);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  return `${day} ${month} ${d.getUTCFullYear()} · ${hh}:00Z`;
}

/** e.g. "00Z" / "12Z" — the model run cycle. */
export function cycleTag(s: string | null | undefined): string {
  const d = parseApiDate(s);
  if (!d) return EM_DASH;
  return `${String(d.getUTCHours()).padStart(2, "0")}Z`;
}

/** e.g. "Wed 01 Jan · 06:00Z" for valid times. */
export function formatValid(s: string | null | undefined): string {
  const d = parseApiDate(s);
  if (!d) return EM_DASH;
  const wd = d.toLocaleString("en-GB", { weekday: "short", timeZone: "UTC" });
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = d.toLocaleString("en-GB", { month: "short", timeZone: "UTC" }).slice(0, 3);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  return `${wd} ${day} ${month} · ${hh}:00Z`;
}

/**
 * The valid time rendered in India local time, e.g. "12 SEP 2026 · 05:30 IST".
 * IMPORTANT: this is presentation only. Lead time is ALWAYS taken from the
 * backend `lead_time_hours`, never inferred from this calendar date.
 */
export function validIST(s: string | null | undefined): string {
  const d = parseApiDate(s);
  if (!d) return EM_DASH;
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const month = get("month").toUpperCase().slice(0, 3);
  return `${get("day")} ${month} ${get("year")} · ${get("hour")}:${get("minute")} IST`;
}

/**
 * Equirectangular projection of lat/lon into normalised [0,1] map space,
 * clamped to the V1 India bounds. Simple and predictable — the station field is
 * a data instrument, not a cartographic basemap.
 */
export function projectIndia(lat: number, lon: number): { x: number; y: number } {
  const { latMin, latMax, lonMin, lonMax } = INDIA_BOUNDS;
  const x = (lon - lonMin) / (lonMax - lonMin);
  const y = 1 - (lat - latMin) / (latMax - latMin);
  return { x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
}

/**
 * Inverse of `projectIndia`: normalised [0,1] map space back to lat/lon.
 * Used to turn a click anywhere on the map into a real geographic coordinate,
 * which is then resolved against the supported station set by the API.
 */
export function unprojectIndia(x: number, y: number): { lat: number; lon: number } {
  const { latMin, latMax, lonMin, lonMax } = INDIA_BOUNDS;
  const lon = lonMin + clamp(x, 0, 1) * (lonMax - lonMin);
  const lat = latMin + (1 - clamp(y, 0, 1)) * (latMax - latMin);
  return { lat, lon };
}

/** Great-circle distance in km — same formula as the backend (WGS84 mean radius). */
export function haversineKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371.0;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const dPhi = toRad(lat2 - lat1);
  const dLmb = toRad(lon2 - lon1);
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLmb / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** Format a coordinate pair in a precise, instrument-like way. */
export function coord(lat: number | null | undefined, lon: number | null | undefined): string {
  if (lat === null || lat === undefined || lon === null || lon === undefined) return EM_DASH;
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(3)}°${ns} ${Math.abs(lon).toFixed(3)}°${ew}`;
}

/** Distance in km with sensible precision. */
export function km(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return EM_DASH;
  return v < 10 ? `${v.toFixed(2)} km` : `${v.toFixed(1)} km`;
}

/** Linear interpolation helper. */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Map a temperature to a 0–1 ramp position for the thermal colour scale. */
export function tempToRamp(c: number, min = -8, max = 38): number {
  return clamp((c - min) / (max - min), 0, 1);
}

/**
 * HELIOS thermal ramp: deep blue → cyan → warm amber → hot rose.
 * Used for station colouring and the temperature field.
 */
export function thermalColor(t01: number): [number, number, number] {
  const stops: Array<[number, [number, number, number]]> = [
    [0.0, [0.16, 0.34, 0.72]],
    [0.25, [0.18, 0.68, 0.82]],
    [0.5, [0.55, 0.82, 0.62]],
    [0.7, [0.98, 0.78, 0.45]],
    [0.86, [0.95, 0.52, 0.31]],
    [1.0, [0.85, 0.27, 0.38]],
  ];
  const t = clamp(t01, 0, 1);
  for (let i = 0; i < stops.length - 1; i++) {
    const cur = stops[i]!;
    const nxt = stops[i + 1]!;
    if (t >= cur[0] && t <= nxt[0]) {
      const f = (t - cur[0]) / (nxt[0] - cur[0]);
      return [
        lerp(cur[1][0], nxt[1][0], f),
        lerp(cur[1][1], nxt[1][1], f),
        lerp(cur[1][2], nxt[1][2], f),
      ];
    }
  }
  return stops[stops.length - 1]![1];
}

export function rgbToCss([r, g, b]: [number, number, number], alpha = 1): string {
  const to255 = (v: number) => Math.round(clamp(v, 0, 1) * 255);
  return `rgba(${to255(r)}, ${to255(g)}, ${to255(b)}, ${alpha})`;
}

/** Standard deviation across the available NWP forecasts = model disagreement. */
export function spread(values: Array<number | null | undefined>): number | null {
  const v = values.filter((x): x is number => x !== null && x !== undefined && Number.isFinite(x));
  if (v.length < 2) return null;
  const mean = v.reduce((a, b) => a + b, 0) / v.length;
  const variance = v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length;
  return Math.sqrt(variance);
}

/** Max minus min across available forecasts. */
export function range(values: Array<number | null | undefined>): number | null {
  const v = values.filter((x): x is number => x !== null && x !== undefined && Number.isFinite(x));
  if (v.length < 2) return null;
  return Math.max(...v) - Math.min(...v);
}
