import type {
  EvaluationResponse,
  ForecastResponse,
  HealthResponse,
  IssueTimesResponse,
  LocationsResponse,
  ModelArenaResponse,
  ModelsResponse,
  LiveForecastResponse,
  LiveStatusResponse,
  ResolveResponse,
  SamplesResponse,
  UsageResponse,
} from "./types";

/**
 * Typed HELIOS API client (browser side).
 *
 * All requests go to the same-origin proxy at /api/helios/* which injects the
 * API key server-side. Components never talk to fetch() directly — they use the
 * hooks in src/hooks/useHeliosData.ts which wrap this client.
 */

/** Discriminated failure classes so the UI can respond meaningfully. */
export type HeliosErrorKind =
  | "live_unavailable"
  | "unauthorized"
  | "offline"
  | "timeout"
  | "not_found"
  | "misconfigured"
  | "bad_data"
  | "unknown";

export class HeliosApiError extends Error {
  readonly kind: HeliosErrorKind;
  readonly status: number;
  constructor(kind: HeliosErrorKind, message: string, status = 0) {
    super(message);
    this.name = "HeliosApiError";
    this.kind = kind;
    this.status = status;
  }
}

function classify(status: number, body: { error?: string; message?: string }): HeliosApiError {
  const msg = body?.message ?? body?.error ?? `Request failed (HTTP ${status})`;
  switch (status) {
    case 401:
      return new HeliosApiError(
        "unauthorized",
        "HELIOS API rejected the API key. Check HELIOS_API_KEY on the server.",
        401,
      );
    case 404:
      return new HeliosApiError("not_found", msg, 404);
    case 500:
      return new HeliosApiError(
        body?.error === "misconfigured" ? "misconfigured" : "unknown",
        msg,
        500,
      );
    case 503:
      // The live pipeline reports its own 503 when current model data cannot be
      // acquired. That is distinct from the API being offline, and must NEVER be
      // silently replaced with historical January data.
      if (body?.error === "live_unavailable") {
        return new HeliosApiError("live_unavailable", msg, 503);
      }
      return new HeliosApiError("offline", msg, 503);
    case 504:
      return new HeliosApiError("timeout", msg, 504);
    default:
      return new HeliosApiError("unknown", msg, status);
  }
}

async function get<T>(
  endpoint: string,
  params?: Record<string, string | number | boolean | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const qs = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    }
  }
  const query = qs.toString();
  const url = `/api/helios/${endpoint}${query ? `?${query}` : ""}`;

  let res: Response;
  try {
    res = await fetch(url, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new HeliosApiError("offline", "Network request to the HELIOS proxy failed.");
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new HeliosApiError("bad_data", "HELIOS returned malformed JSON.", res.status);
  }

  if (!res.ok) {
    throw classify(res.status, (body ?? {}) as { error?: string; message?: string });
  }

  // Backend can return a 200 with an application-level error envelope.
  const maybeErr = body as { error?: string; detail?: string };
  if (maybeErr && typeof maybeErr === "object" && typeof maybeErr.error === "string") {
    throw new HeliosApiError(
      maybeErr.error === "not_found" ? "not_found" : "bad_data",
      maybeErr.detail ?? maybeErr.error,
      res.status,
    );
  }

  return body as T;
}

export const heliosApi = {
  health: (signal?: AbortSignal) => get<HealthResponse>("health", undefined, signal),
  models: (signal?: AbortSignal) => get<ModelsResponse>("models", undefined, signal),
  evaluation: (signal?: AbortSignal) => get<EvaluationResponse>("evaluation", undefined, signal),
  modelArena: (signal?: AbortSignal) => get<ModelArenaResponse>("model-arena", undefined, signal),
  locations: (signal?: AbortSignal) => get<LocationsResponse>("locations", undefined, signal),
  /** Resolve an arbitrary coordinate to the nearest supported forecast point. */
  resolve: (lat: number, lon: number, requireModels = 1, signal?: AbortSignal) =>
    get<ResolveResponse>(
      "resolve",
      { lat, lon, require_models: requireModels },
      signal,
    ),
  usage: (signal?: AbortSignal) => get<UsageResponse>("usage", undefined, signal),

  /* ----------------------------- LIVE ----------------------------------- */
  /** Which live model cycle is published, and whether the cache is warm. */
  liveStatus: (signal?: AbortSignal) =>
    get<LiveStatusResponse>("live/status", undefined, signal),
  /**
   * LIVE multi-horizon forecast from the current model cycle.
   * Throws HeliosApiError('live_unavailable') rather than returning historical
   * data if live acquisition fails.
   */
  liveForecast: (station: string, leads?: number[], signal?: AbortSignal) =>
    get<LiveForecastResponse>(
      "live/forecast",
      { station, leads: leads && leads.length ? leads.join(",") : undefined },
      signal,
    ),
  samples: (limit = 20, signal?: AbortSignal) =>
    get<SamplesResponse>("samples", { limit }, signal),
  issueTimes: (station: string, leadTimeHours: number, signal?: AbortSignal) =>
    get<IssueTimesResponse>(
      "issue-times",
      { station, lead_time_hours: leadTimeHours },
      signal,
    ),
  forecast: (
    args: {
      issueTime: string;
      leadTimeHours: number;
      station: string;
      arena?: boolean;
    },
    signal?: AbortSignal,
  ) =>
    get<ForecastResponse>(
      "forecast",
      {
        issue_time: args.issueTime,
        lead_time_hours: args.leadTimeHours,
        station: args.station,
        arena: args.arena === false ? 0 : 1,
      },
      signal,
    ),
};
