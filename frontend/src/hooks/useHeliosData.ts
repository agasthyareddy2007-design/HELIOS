"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HeliosApiError, heliosApi } from "@/lib/client";
import type {
  EvaluationResponse,
  LiveForecastResponse,
  LiveStatusResponse,
  ForecastResponse,
  HealthResponse,
  LocationsResponse,
  ModelsResponse,
} from "@/lib/types";

/** Uniform async resource shape consumed by every component. */
export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: HeliosApiError | null;
  reload: () => void;
}

interface InternalState<T> {
  data: T | null;
  error: HeliosApiError | null;
  settled: boolean;
}

/**
 * Generic fetch hook.
 *
 * Reliability properties:
 *  - AbortController cancellation on unmount and on dependency change
 *  - a monotonically increasing request id, so a late response can never
 *    overwrite a newer one (the classic race when scrubbing the timeline)
 *  - typed HeliosApiError values instead of thrown strings
 *  - `loading` is DERIVED, not stored, so no synchronous setState is needed for
 *    the disabled branch
 */
function useResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: ReadonlyArray<unknown>,
  enabled = true,
  initialData?: T,
): Resource<T> {
  const [state, setState] = useState<InternalState<T>>({
    data: initialData ?? null,
    error: null,
    settled: initialData !== undefined,
  });

  const hadInitial = useRef(initialData !== undefined);
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  // Callers build a fresh closure each render; `deps` drives refetching. The ref
  // is updated in an effect (never during render) and is declared BEFORE the
  // fetching effect so it is always current when that effect runs.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    if (!enabled) return;

    if (hadInitial.current) {
      hadInitial.current = false;
      return;
    }

    // FIX: Clear state immediately when deps change so we don't render stale data.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ data: null, error: null, settled: false });

    const controller = new AbortController();
    const id = ++latest.current;

    fetcherRef
      .current(controller.signal)
      .then((res) => {
        if (id !== latest.current || controller.signal.aborted) return;
        setState({ data: res, error: null, settled: true });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || id !== latest.current) return;
        setState({
          data: null,
          error:
            err instanceof HeliosApiError
              ? err
              : new HeliosApiError(
                  "unknown",
                  err instanceof Error ? err.message : "Unknown error",
                ),
          settled: true,
        });
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce]);

  const reload = useCallback(() => {
    setNonce((n) => n + 1);
  }, []);

  return {
    data: state.data,
    error: enabled ? state.error : null,
    loading: enabled && !state.settled,
    reload,
  };
}

export function useHealth(): Resource<HealthResponse> {
  return useResource((s) => heliosApi.health(s), []);
}

export function useModels(): Resource<ModelsResponse> {
  return useResource((s) => heliosApi.models(s), []);
}

export function useEvaluation(): Resource<EvaluationResponse> {
  return useResource((s) => heliosApi.evaluation(s), []);
}

export function useLocations(): Resource<LocationsResponse> {
  return useResource((s) => heliosApi.locations(s), []);
}

export function useIssueTimes(
  station: string | null,
  leadHours: number,
): Resource<string[]> {
  return useResource<string[]>(
    async (s) => {
      const res = await heliosApi.issueTimes(station as string, leadHours, s);
      return res.issue_times;
    },
    [station, leadHours],
    Boolean(station),
  );
}

export function useForecast(
  station: string | null,
  leadHours: number,
  issueTime: string | null,
): Resource<ForecastResponse> {
  return useResource(
    (s) =>
      heliosApi.forecast(
        {
          station: station as string,
          leadTimeHours: leadHours,
          issueTime: issueTime as string,
          arena: true,
        },
        s,
      ),
    [station, leadHours, issueTime],
    Boolean(station && issueTime),
  );
}


/* --------------------------------------------------------------------- live */

export function useLiveStatus(pollMs = 0): Resource<LiveStatusResponse> {
  const res = useResource((s) => heliosApi.liveStatus(s), []);
  // Optional slow poll so the UI notices a newly published cycle or a warm cache.
  useEffect(() => {
    if (!pollMs) return;
    const id = setInterval(res.reload, pollMs);
    return () => clearInterval(id);
  }, [pollMs, res.reload]);
  return res;
}

export const liveForecastPrefetchCache = new Map<string, LiveForecastResponse>();

export function useLiveForecast(
  station: string | null,
  leads?: number[],
): Resource<LiveForecastResponse> {
  const key = leads?.join(",") ?? "";
  const initialData = (station && !leads) ? liveForecastPrefetchCache.get(station) : undefined;
  
  return useResource(
    (s) => heliosApi.liveForecast(station as string, leads, s),
    [station, key],
    Boolean(station),
    initialData
  );
}
