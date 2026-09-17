"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLiveForecast, useLiveStatus, useLocations } from "@/hooks/useHeliosData";
import { heliosApi } from "@/lib/client";
import { useHelios } from "@/store/useHelios";
import { formatValid, spread } from "@/lib/format";
import { NWP_MODELS, type LiveHorizon, type StationLocation } from "@/lib/types";
import { CinematicIntro } from "@/components/intro/CinematicIntro";
import { useStage } from "@/components/stage/useStage";
import { IndiaMap } from "@/components/map/IndiaMap";
import { LocationSearch } from "@/components/map/LocationSearch";
import { ForecastPanel } from "@/components/live/ForecastPanel";
import {
  Arbitration,
  CandidateArbitration,
  WhyResult,
  DevelopmentNotice,
  HeliosOutput,
  ModelTrust,
} from "@/components/live/ForecastSections";

/**
 * HELIOS forecast application (route: /forecast).
 *
 * This is the live forecasting instrument, preserved verbatim from the original
 * single-page app: cinematic opening → India map hero → live forecast, model
 * trust, AI candidates and the calibrated HELIOS output. All values are
 * authoritative backend data; the frontend performs no blending.
 *
 * The opening cinematic is isolated in <CinematicIntro/>: when the real HELIOS
 * opening video becomes available it can be swapped in there without touching
 * the forecast instrument below.
 */
function ForecastPageContent() {
  const locations = useLocations();
  const liveStatus = useLiveStatus(60_000);
  const { station, leadHours, setLeadHours, selectStation } = useHelios();

  const live = useLiveForecast(station?.station ?? null);

  const deepLinkApplied = useRef(false);
  useEffect(() => {
    if (deepLinkApplied.current || !locations.data?.locations?.length) return;
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const place = params.get("place");
    const lead = params.get("lead");
    if (!place && !lead) {
      deepLinkApplied.current = true;
      return;
    }
    if (place) {
      const q = place.toLowerCase();
      const match = locations.data.locations.find(
        (s) => (s.name ?? "").toLowerCase() === q || (s.name ?? "").toLowerCase().includes(q),
      );
      if (match) selectStation(match);
    }
    if (lead) {
      const n = Number(lead);
      if ([6, 24, 48, 72, 120].includes(n)) setLeadHours(n);
    }
    deepLinkApplied.current = true;
  }, [locations.data, selectStation, setLeadHours]);

  const horizon: LiveHorizon | null = useMemo(() => {
    const hs = live.data?.horizons ?? [];
    if (!hs.length) return null;
    if (leadHours !== null) {
      const picked = hs.find((h) => h.lead_time_hours === leadHours);
      if (picked) return picked;
    }
    return hs.find((h) => h.is_future) ?? hs[hs.length - 1] ?? null;
  }, [live.data, leadHours]);

  const atmosphere = useMemo(() => {
    if (!horizon) return { weights: null, disagreementC: null };
    const weights = {
      gfs: horizon.nwp_availability.gfs ? horizon.nwp_weights.gfs : 0,
      ifs: horizon.nwp_availability.ifs ? horizon.nwp_weights.ifs : 0,
      icon: horizon.nwp_availability.icon ? horizon.nwp_weights.icon : 0,
    };
    const temps = NWP_MODELS.filter((m) => horizon.nwp_availability[m]).map(
      (m) => horizon.nwp_forecasts_c[m],
    );
    return { weights, disagreementC: spread(temps) };
  }, [horizon]);

  const resolveAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    useStage.getState().setMode("instrument");
    return () => useStage.getState().setMode("cinematic");
  }, []);

  useEffect(() => {
    useStage.getState().setLive(atmosphere.weights, atmosphere.disagreementC);
    return () => useStage.getState().clearLive();
  }, [atmosphere.weights, atmosphere.disagreementC]);
  const handleResolve = useCallback(
    async (lat: number, lon: number) => {
      resolveAbort.current?.abort();
      const ac = new AbortController();
      resolveAbort.current = ac;
      try {
        const res = await heliosApi.resolve(lat, lon, 1, ac.signal);
        selectStation(res.resolved);
        setLeadHours(null);
      } catch {
      }
    },
    [selectStation, setLeadHours],
  );

  const handleSearchSelect = useCallback(
    (s: StationLocation) => {
      selectStation(s);
      setLeadHours(null);
    },
    [selectStation, setLeadHours],
  );

  return (
    <>
      
      <main className="relative min-h-screen">
        {/* ===================== SECTION 1 · LIVE FORECAST ===================== */}
        <section className="relative min-h-screen px-6 pb-16 pt-8 md:px-10">
          {/* header */}
          <header className="mx-auto mb-6 flex max-w-[1500px] items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/" className="group inline-flex min-h-[44px] items-center gap-3 rounded-full pr-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]" aria-label="HELIOS — home">
                <span className="relative flex h-5 w-5 items-center justify-center">
                  <span className="absolute inset-0 rounded-md border border-[var(--helios-amber)]/50 transition-colors group-hover:border-[var(--helios-amber)]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--helios-amber)]" />
                </span>
                <span className="font-display text-[16px] font-semibold uppercase tracking-[0.30em] text-[var(--ink)]">Helios</span>
              </Link>
              <span className="hidden h-3 w-px bg-[var(--color-hairline-bright)] sm:inline-block" />
              <nav className="hidden items-center gap-3 sm:flex" aria-label="Primary">
                <Link href="/" className="inline-flex min-h-[44px] items-center font-mono text-[12px] uppercase tracking-[0.14em] text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]">
                  Home
                </Link>
                <span className="inline-flex min-h-[44px] items-center font-mono text-[12px] uppercase tracking-[0.14em] text-[var(--helios-amber)]" aria-current="page">
                  Forecast
                </span>
                <Link href="/contact" className="inline-flex min-h-[44px] items-center font-mono text-[12px] uppercase tracking-[0.14em] text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)]">
                  Contact
                </Link>
              
                <button 
                  onClick={async () => {
                    await fetch("/api/auth/logout", { method: "POST" });
                    window.location.reload();
                  }}
                  className="inline-flex min-h-[44px] items-center font-mono text-[12px] uppercase tracking-[0.14em] text-[var(--ink-dim)] transition-colors hover:text-[var(--ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--helios-amber)] ml-4"
                >
                  Logout
                </button>
  </nav>
            </div>
            {/* System state readout: the instrument reports its own condition. */}
            <div className="flex items-center gap-2.5" role="status" aria-live="polite">
              <span className="relative flex h-2 w-2 items-center justify-center">
                {liveStatus.data?.live_available && (
                  <span
                    aria-hidden
                    className="absolute inset-0 rounded-full animate-pulse-soft"
                    style={{ background: "var(--color-signal)", opacity: 0.45 }}
                  />
                )}
                <span
                  className="relative h-1.5 w-1.5 rounded-full"
                  style={{
                    background: liveStatus.data?.live_available
                      ? "var(--color-signal)"
                      : "var(--color-warn)",
                    boxShadow: liveStatus.data?.live_available
                      ? "0 0 10px var(--color-signal)"
                      : "none",
                  }}
                />
              </span>
              <span className="font-mono text-[12px] uppercase tracking-[0.12em] text-[var(--ink-dim)]">
                {liveStatus.data?.live_available
                  ? `live · ${liveStatus.data.selected_cycle ? formatValid(liveStatus.data.selected_cycle) : ""}`
                  : liveStatus.data
                    ? "live feed unavailable"
                    : "connecting…"}
              </span>
            </div>
          </header>

          {/* map (hero) + forecast panel — one composition, not two cards */}
          <div className="mx-auto grid max-w-[1500px] items-stretch gap-8 lg:grid-cols-[1.75fr_1fr]">
            <div className="relative">
              <div
                className="surface overflow-hidden rounded-[1.75rem]"
                style={{ boxShadow: "inset 0 0 0 1px rgba(126,165,218,0.14), inset 0 0 90px -20px rgba(0,0,0,0.65), 0 40px 90px -44px rgba(0,0,0,0.85)" }}
              >
                <IndiaMap
                  modelPoints={horizon?.model_grid_points}
                  className="h-[60vh] w-full overflow-hidden rounded-[1.75rem] lg:h-[74vh]"
                  selected={station}
                  onResolveCoordinate={handleResolve}
                />
              </div>
              {/* floating search over the map */}
              <div className="absolute left-5 top-5 z-20 w-[min(320px,70%)]">
                <LocationSearch
                  locations={locations.data?.locations ?? []}
                  onSelect={handleSearchSelect}
                />
              </div>
              {/* subtle hint until first selection */}
              {!station && (
                <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
                  <span className="rounded-full bg-black/40 px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.20em] text-[var(--helios-amber)]/90 backdrop-blur-md">
                    click anywhere in India
                  </span>
                </div>
              )}
            </div>

            {/* forecast — floating information, thin divider, no boxy card */}
            <div className="relative py-4 lg:border-l lg:border-white/[0.06] lg:pl-10">
              <ForecastPanel
                station={station}
                live={live.data}
                loading={live.loading}
                error={live.error}
                onRetry={() => {
                  live.reload();
                  liveStatus.reload();
                }}
                horizon={horizon}
                onSelectLead={setLeadHours}
              />
            </div>
          </div>
        </section>

        {/* Secondary sections only appear once a location is chosen. */}
        {station && !live.error && (
          <>
            <Arbitration horizon={horizon} />
            <ModelTrust horizon={horizon} />
            <CandidateArbitration horizon={horizon} />
            <WhyResult horizon={horizon} stationName={station?.name ?? null} />
            <HeliosOutput horizon={horizon} />
          </>
        )}

        <DevelopmentNotice />
      </main>
    </>
  );
}

import { AuthGate } from "@/components/auth/AuthGate";
import { ForecastErrorBoundary } from "@/components/live/ForecastErrorBoundary";
import { createPortal } from "react-dom";

export default function ForecastPage() {
  const [authStatus, setAuthStatus] = useState<"checking" | "authenticated" | "unauthenticated">("checking");
  const [introDone, setIntroDone] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    let canceled = false;
    setMounted(true);
    window.scrollTo(0, 0);
    document.body.style.overflow = 'hidden';

    fetch("/api/auth/me")
      .then((r) => r.json())
      .then((d) => {
        if (!canceled) {
          setAuthStatus(d.authenticated ? "authenticated" : "unauthenticated");
        }
      })
      .catch(() => {
        if (!canceled) setAuthStatus("unauthenticated");
      });

    return () => {
      canceled = true;
      document.body.style.overflow = '';
    };
  }, []);

  useEffect(() => {
    if (authStatus === "authenticated" && introDone) {
      document.body.style.overflow = '';
    } else {
      document.body.style.overflow = 'hidden';
    }
  }, [authStatus, introDone]);

  return (
    <>
      {mounted && createPortal(
        <>
          {authStatus === "checking" && (
            <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black">
              <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--helios-amber)] animate-pulse">
                Authenticating...
              </span>
            </div>
          )}

          {authStatus === "unauthenticated" && (
            <AuthGate 
              show={true}
              onAuthenticated={() => {
                setAuthStatus("authenticated");
              }} 
            />
          )}

          {authStatus === "authenticated" && !introDone && (
            <CinematicIntro onDone={() => setIntroDone(true)} />
          )}
        </>,
        document.body
      )}

      {authStatus === "authenticated" && introDone && (
        <ForecastErrorBoundary>
          <ForecastPageContent />
        </ForecastErrorBoundary>
      )}
    </>
  );
}
