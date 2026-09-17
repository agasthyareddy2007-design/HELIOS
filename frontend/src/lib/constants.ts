import type { CandidateKey, NwpModel, ZoneKey } from "./types";

/** Canonical presentation metadata for the three NWP models. */
export const NWP_META: Record<
  NwpModel,
  { label: string; full: string; centre: string; color: string; glow: string }
> = {
  gfs: {
    label: "GFS",
    full: "Global Forecast System",
    centre: "NOAA · United States",
    color: "#4da3ff",
    glow: "#8fc9ff",
  },
  ifs: {
    label: "IFS",
    full: "Integrated Forecasting System",
    centre: "ECMWF · Europe",
    color: "#8b7cff",
    glow: "#b6acff",
  },
  icon: {
    label: "ICON",
    full: "Icosahedral Nonhydrostatic",
    centre: "DWD · Germany",
    color: "#2fd6b4",
    glow: "#7ef0d8",
  },
};

/** Presentation metadata for HELIOS arbitration candidates. */
export const CANDIDATE_META: Record<
  CandidateKey,
  { label: string; short: string; family: string; color: string }
> = {
  kernel: {
    label: "Kernel Regression",
    short: "Kernel",
    family: "Similarity-weighted local regression",
    color: "#e07a9a",
  },
  xgboost: {
    label: "XGBoost",
    short: "XGBoost",
    family: "Gradient-boosted decision trees",
    color: "#f0a55e",
  },
  mlp: {
    label: "MLP",
    short: "MLP",
    family: "Multi-layer perceptron",
    color: "#ffc773",
  },
};

export const HELIOS_COLOR = "#ffc773";
export const BASELINE_COLOR = "#6b7b8f";

/**
 * EVALUATION STRATIFICATION REGIONS — not forecast locations.
 *
 * These zones exist so evaluation can be broken down regionally. A zone is a
 * statistical grouping; it must never be presented as the location of a forecast.
 * The forecast UI uses real coordinates + station anchor + place name instead.
 */
export const ZONE_META: Record<ZoneKey, { label: string; short: string }> = {
  north_himalaya: { label: "Northern Himalaya", short: "N-HIM" },
  north_plains: { label: "Northern Plains", short: "N-PLN" },
  central: { label: "Central India", short: "CENT" },
  south_plateau: { label: "Southern Plateau", short: "S-PLT" },
  south_coastal: { label: "Southern Coastal", short: "S-CST" },
};

/**
 * India map viewport bounds. Padded to include the full national claim shown by
 * the DataMeet (Survey-of-India-aligned) geometry — the northern disputed
 * territory (POK / Ladakh) reaches ~37.1 deg N, so latMax gives it headroom.
 * The V1 forecast dataset itself covers lat 7.66-34.51, lon 68.39-95.88 (from
 * the DB); the northern territory is a geographic backdrop with no stations.
 */
export const INDIA_BOUNDS = {
  latMin: 6.5,
  latMax: 37.3,
  lonMin: 67.5,
  lonMax: 97.0,
} as const;

/** Human labels for forecast horizons. */
export function leadLabel(hours: number): string {
  return `+${hours}h`;
}

/**
 * The single most important wording guard in the product.
 * Weights are BLENDING WEIGHTS (trust), never probability/accuracy/confidence.
 */
export const TRUST_DISCLAIMER =
  "Blending weights derived by the frozen MLP over available models. These are model-trust weights — not probabilities, accuracy scores, or confidence intervals.";

export const V1_SCOPE_NOTE =
  "V1 is validated for 2 m temperature only. Humidity, wind, precipitation and derived indices are not validated and are not served.";

/**
 * The spatial claim V1 is actually entitled to make. Used wherever the UI must
 * avoid implying arbitrary-coordinate hyperlocal accuracy.
 */
export const SPATIAL_SCOPE_NOTE =
  "V1 is station-anchored: forecasts are served at supported station points using each NWP model's nearest grid point. Arbitrary coordinates are resolved to the nearest supported point and the distance is disclosed. Spatial interpolation/regridding for arbitrary coordinates is V2 work.";

/** Zones are evaluation regions; this string guards against misuse. */
export const ZONE_SEMANTICS_NOTE =
  "Evaluation zones are statistical stratification regions used for regional performance analysis. A zone is not a forecast location.";
