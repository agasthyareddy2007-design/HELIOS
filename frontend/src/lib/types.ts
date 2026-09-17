/**
 * HELIOS V1 API contracts.
 *
 * These types mirror the ACTUAL responses of the HELIOS V1 API
 * (backend/app/api/v1_app.py + backend/app/services/helios_v1_service.py).
 * Nothing here is aspirational — every field was verified against live
 * responses. Optional/nullable fields reflect genuine backend behaviour
 * (e.g. a candidate whose artifact cannot be loaded reports
 * `forecast_available: false` and `forecast_c: null`).
 */

/** The three NWP models that participate in V1. */
export type NwpModel = "gfs" | "ifs" | "icon";
export const NWP_MODELS: readonly NwpModel[] = ["gfs", "ifs", "icon"] as const;

/** HELIOS arbitration candidates (LEVEL 2 competition). */
export type CandidateKey = "kernel" | "xgboost" | "mlp";
export const CANDIDATE_KEYS: readonly CandidateKey[] = ["kernel", "xgboost", "mlp"] as const;

/**
 * Candidate status as reported by the backend.
 * `validated_live_strategy` = the frozen V1 serving strategy (MLP).
 * `validated_candidate`     = a legitimate candidate that was NOT selected.
 */
export type CandidateStatus = "validated_live_strategy" | "validated_candidate";

export type PerModel<T> = Record<NwpModel, T>;

/* ------------------------------------------------------------------ health */

export interface HealthResponse {
  status: string;
  version: string;
  variable: string;
  units: string;
  live_strategy: string;
  frozen_selection_present: boolean;
  trains_on_startup: boolean;
  recomputes_test: boolean;
}

/* ------------------------------------------------------------------ models */

export interface HeliosCandidateSummary {
  name: string;
  key: CandidateKey;
  type: string;
  status: CandidateStatus;
}

export interface ModelsResponse {
  nwp_models: string[];
  helios_candidates: HeliosCandidateSummary[];
  baseline: string;
  live_strategy: string;
  live_strategy_key: CandidateKey;
  variables: string[];
  units: string;
  selection_basis: string | null;
  note: string;
}

/* -------------------------------------------------------------- evaluation */

export interface WalkForwardCandidate {
  name: string;
  key: CandidateKey;
  mean_mae_c: number | null;
  std_c: number | null;
  improvement_vs_simple_average_pct: number | null;
  folds_beating_simple_average: number | null;
  status: CandidateStatus;
}

export interface WalkForwardBlock {
  simple_average: { mean_mae_c: number | null; std_c: number | null };
  candidates: WalkForwardCandidate[];
  n_folds: number | null;
  criterion: string | null;
}

export interface LockedTestMetric {
  mae_c: number | null;
  rmse_c: number | null;
  bias_c: number | null;
  median_abs_error_c: number | null;
  p90_c: number | null;
  p95_c: number | null;
  p99_c: number | null;
  n_rows: number | null;
}

/** Locked-test result keys: the NWP models, the baseline, and helios_<candidate>. */
export type LockedTestResultKey = NwpModel | "simple_average" | `helios_${CandidateKey}`;

export interface LockedTestBlock {
  n_test_samples: number | null;
  test_issue_range: [string, string] | null;
  evaluated_once: boolean | null;
  results: Partial<Record<LockedTestResultKey, LockedTestMetric>>;
  helios_vs_simple_average: { absolute: number; pct: number } | null;
  best_individual_model: string | null;
  helios_vs_best_individual: { absolute: number; pct: number } | null;
  correlated_data_note: string | null;
  model_availability_on_test: Partial<Record<NwpModel, number>> | null;
}

export interface EvaluationResponse {
  protocol: string;
  source_artifacts: {
    frozen_selection: string | null;
    walkforward: string | null;
    locked_test: string | null;
  };
  recomputed: boolean;
  test_accessed_for_new_computation: boolean;
  walk_forward: WalkForwardBlock;
  locked_test: LockedTestBlock;
  live_strategy: string;
  interpretation: string;
}

/* ------------------------------------------------------------- model arena */

export interface ArenaCandidate {
  name: string;
  key: CandidateKey;
  walk_forward_mae_c: number | null;
  walk_forward_std_c: number | null;
  improvement_vs_simple_average_pct: number | null;
  status: CandidateStatus;
  forecast_available: boolean;
  forecast_c: number | null;
  /** Present only when a forecast context was supplied. */
  nwp_weights?: PerModel<number>;
}

export interface ModelArenaResponse {
  candidates: ArenaCandidate[];
  baseline: { name: string; walk_forward_mae_c: number | null };
  level: string;
  note: string;
}

/* ---------------------------------------------------------------- forecast */

/** The grid point of one NWP model, and its offset from the anchor station. */
export interface ModelGridPoint {
  latitude: number | null;
  longitude: number | null;
  distance_to_station_km: number | null;
}

/**
 * Spatial provenance of a forecast.
 *
 * V1 is station-anchored: each model is sampled at its own nearest grid point to
 * the anchor station and nothing is interpolated. This block exists so the UI can
 * state that plainly instead of implying arbitrary-coordinate accuracy.
 */
export interface SpatialBlock {
  support: string;
  anchor_station: string;
  model_grid_points: Partial<Record<NwpModel, ModelGridPoint>>;
  selection_rule: string;
  interpolated: boolean;
  note: string;
}

export interface ForecastResponse {
  issue_time: string;
  valid_time: string;
  lead_time_hours: number;
  /** REAL station coordinates + place name. `evaluation_zone` is metadata only. */
  location: {
    latitude: number | null;
    longitude: number | null;
    name?: string | null;
    elevation_m?: number | null;
    station?: string;
    coordinate_source?: string | null;
    evaluation_zone?: ZoneKey | null;
  };
  variable: string;
  units: string;
  live_strategy: string;
  /** Blended HELIOS temperature. `null` if no available model contributed. */
  helios_temperature_c: number | null;
  /** Per-NWP temperature; `null` means the model is UNAVAILABLE (never zero). */
  nwp_forecasts_c: PerModel<number | null>;
  nwp_availability: PerModel<boolean>;
  /** MLP-derived blending weights (TRUST). Not probabilities/accuracy. */
  nwp_weights: PerModel<number>;
  nwp_weights_note: string;
  live_strategy_locked_test_mae_c?: number;
  model_arena?: ModelArenaResponse;
  station?: string;
  spatial?: SpatialBlock;
}

/** Backend error envelope (e.g. no data for the requested key). */
export interface ApiErrorBody {
  error: string;
  message?: string;
  detail?: string;
}

/* --------------------------------------------------------------- locations */

/**
 * Evaluation stratification regions.
 *
 * IMPORTANT: a zone is a STATISTICAL EVALUATION REGION, not a forecast location.
 * Zones may appear in evaluation/regional-performance context; they must never
 * stand in for coordinates in the forecast UI.
 */
export type ZoneKey =
  | "north_himalaya"
  | "north_plains"
  | "central"
  | "south_plateau"
  | "south_coastal";

/** Distance from a model's nearest grid point to the anchor station, in km. */
export type NearestGridKm = Partial<Record<NwpModel, number | null>>;

/**
 * A supported V1 forecast point.
 *
 * `latitude`/`longitude` are the REAL station coordinates (NOAA ISD station
 * history), NOT NWP grid coordinates. They may be `null` if ISD metadata is
 * unavailable for a station — in that case the point is not plotted rather than
 * being given a fabricated position.
 */
export interface StationLocation {
  station: string;
  /** Geographic place name — presentation metadata (e.g. "Srinagar"). */
  name: string | null;
  latitude: number | null;
  longitude: number | null;
  elevation_m: number | null;
  country: string | null;
  /** Evaluation stratification only. NOT the location. */
  evaluation_zone: ZoneKey | null;
  /** NWP models that actually have rows for this station. */
  models: NwpModel[];
  /** Per-model distance from station to that model's nearest grid point. */
  nearest_grid_km: NearestGridKm;
  n_rows: number;
  coordinate_source: string | null;
}

export interface LocationsResponse {
  locations: StationLocation[];
  count: number;
  lead_time_hours: number[];
  spatial_support: string;
  coordinate_source: string;
  spatial_note: string;
}

/** Result of resolving an arbitrary coordinate to the nearest supported point. */
export interface ResolveResponse {
  requested: { latitude: number; longitude: number };
  resolved: StationLocation;
  distance_km: number;
  resolution: string;
  note: string;
}

export interface IssueTimesResponse {
  issue_times: string[];
}

export interface SampleRequest {
  issue_time: string;
  valid_time: string;
  lead_time_hours: number;
  station: string;
}

export interface SamplesResponse {
  samples: SampleRequest[];
}

export interface UsageResponse {
  key_id: string;
  requests: number;
}

/* ------------------------------------------------------------------- live */

/**
 * LIVE forecast contracts.
 *
 * The live path is strictly separate from the historical January 2025 path.
 * A live response describes the CURRENT published model cycle and FUTURE valid
 * times. It never contains historical evaluation records, and a live failure is
 * never substituted with historical data.
 */

export interface LiveModelStatus {
  available: boolean;
  run?: string;
  cycle?: string;
  leads?: number[];
  leads_missing?: number[];
  error?: string;
}

export interface LiveStatusResponse {
  generated_at: string;
  models: Partial<Record<NwpModel, LiveModelStatus>>;
  models_online: NwpModel[];
  n_models_online: number;
  live_available: boolean;
  /** The single cycle all contributing models share. */
  selected_cycle: string | null;
  selected_cycle_models: NwpModel[];
  cycle_alignment: string;
  supported_leads: number[];
  variable: string;
  units: string;
  cache_entries: number;
  cache_warm: boolean;
  warming: boolean;
}

/** Live grid provenance for one model at one horizon. */
export interface LiveGridPoint {
  latitude: number;
  longitude: number;
  distance_to_station_km: number;
  grid_note: string;
  run: string;
}

export interface LiveHorizon {
  lead_time_hours: number;
  valid_time: string;
  nwp_forecasts_c: PerModel<number | null>;
  nwp_availability: PerModel<boolean>;
  nwp_weights: PerModel<number>;
  helios_temperature_c: number | null;
  model_grid_points: Partial<Record<NwpModel, LiveGridPoint>>;
  model_errors: Partial<Record<NwpModel, string>>;
  /**
   * Real per-candidate outputs (Kernel / XGBoost / MLP) computed by the backend
   * on the SAME live feature vector. The `selected` one's temperature equals
   * `helios_temperature_c` (deployed strategy). Never fabricated in the browser.
   */
  candidate_forecasts?: Partial<
    Record<
      CandidateKey,
      {
        temperature_c: number | null;
        weights: PerModel<number> | null;
        available: boolean;
        selected: boolean;
      }
    >
  > | null;
  /** Deployed candidate key (e.g. "mlp"). */
  selected_candidate?: CandidateKey;
  /**
   * False when this horizon's valid time has already elapsed. The earliest lead
   * of a published cycle can be in the past (00Z run +6h is valid at 06Z), and
   * such a horizon must not be presented as a forecast of the future.
   */
  is_future: boolean;
}

/** Provenance of the optional 7-day reliability features for a live cycle. */
export interface ReliabilityFeatureInfo {
  window_start: string;
  window_end_exclusive: string;
  source: string;
  available: boolean;
  n_rows: number;
  imputed_by_frozen_preprocessing: boolean;
  note: string;
  error?: string;
}

export interface LiveForecastResponse {
  mode: "live";
  /** The published model cycle this forecast was issued from. */
  issue_time: string;
  cycle: string;
  generated_at: string;
  model_runs: Partial<Record<NwpModel, string>>;
  cycle_models: NwpModel[];
  cycle_alignment: string;
  variable: string;
  units: string;
  live_strategy: string;
  live_strategy_locked_test_mae_c: number | null;
  location: {
    station: string;
    name: string | null;
    latitude: number;
    longitude: number;
    elevation_m: number | null;
    coordinate_source: string | null;
    evaluation_zone: ZoneKey | null;
  };
  spatial: {
    support: string;
    anchor_station: string;
    selection_rule: string;
    interpolated: boolean;
    note: string;
  };
  reliability_features: ReliabilityFeatureInfo;
  horizons: LiveHorizon[];
  /** Earliest horizon whose valid time is still ahead of now. */
  first_future_lead_hours: number | null;
  n_future_horizons: number;
  temporal_safety: {
    issue_time_is_published_cycle: boolean;
    valid_times_relative_to: string;
    elapsed_horizons_flagged: boolean;
    uses_future_observations: boolean;
    reliability_window: string;
  };
}
