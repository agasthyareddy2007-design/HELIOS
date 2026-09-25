"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { useLiveStatus } from "@/hooks/useHeliosData";

const REQUIRED_MODELS = [
  { id: "gfs", name: "GFS", origin: "NOAA" },
  { id: "ifs", name: "IFS", origin: "ECMWF" },
  { id: "icon", name: "ICON", origin: "DWD" },
] as const;

interface ConnectionScreenProps {
  onComplete: () => void;
}

export function ConnectionScreen({ onComplete }: ConnectionScreenProps) {
  // Store callback in ref so inline function changes don't re-trigger or cancel effects
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  // Keep track of completion to ensure onComplete is invoked exactly once
  const completedRef = useRef(false);

  // Once all models are connected, we can lock this state to true so subsequent polls don't flicker
  const [allConnected, setAllConnected] = useState(false);

  // Poll live status every 2 seconds until all models are connected.
  // When allConnected is true, polling is no longer needed (pollMs = 0).
  const liveStatus = useLiveStatus(allConnected ? 0 : 2000);

  // Check actual live status of the 3 required models.
  const modelsStatus = {
    gfs: allConnected || Boolean(liveStatus.data?.models?.gfs?.available),
    ifs: allConnected || Boolean(liveStatus.data?.models?.ifs?.available),
    icon: allConnected || Boolean(liveStatus.data?.models?.icon?.available),
  };

  const isNowConnected =
    (Boolean(liveStatus.data?.models?.gfs?.available) &&
      Boolean(liveStatus.data?.models?.ifs?.available) &&
      Boolean(liveStatus.data?.models?.icon?.available)) ||
    Boolean(liveStatus.data?.live_available);

  // Lock allConnected when isNowConnected becomes true
  useEffect(() => {
    if (isNowConnected && !allConnected) {
      setAllConnected(true);
    }
  }, [isNowConnected, allConnected]);

  // When all models are connected, wait ~1.2 seconds and fire onComplete once
  useEffect(() => {
    if (!allConnected || completedRef.current) return;
    completedRef.current = true;

    const timer = setTimeout(() => {
      onCompleteRef.current();
    }, 1200);

    return () => clearTimeout(timer);
  }, [allConnected]);

  const hasError = Boolean(liveStatus.error);

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#070d18]/90 p-6 backdrop-blur-xl">
      {/* Centered clean light-blue / white card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="relative w-full max-w-md overflow-hidden rounded-2xl border border-[#b8d4f0] bg-[#eef5fc] p-8 shadow-2xl shadow-blue-950/40"
      >
        {/* Decorative subtle atmospheric glow inside the card */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-20 -top-20 h-56 w-56 rounded-full bg-[#bfdcfa] opacity-60 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-20 -left-20 h-56 w-56 rounded-full bg-[#d5e8fc] opacity-60 blur-3xl"
        />

        <div className="relative">
          {/* Header */}
          <div className="text-center">
            <div className="inline-flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#f59b3c]" />
              <h1 className="font-display text-2xl font-bold tracking-[0.25em] text-[#0a1526]">
                HELIOS
              </h1>
            </div>
            <p className="mt-1 font-mono text-[12px] uppercase tracking-[0.16em] text-[#4a6585]">
              Initializing System
            </p>
          </div>

          <div className="my-6 h-px w-full bg-[#d0e2f5]" />

          {/* Model connection status rows */}
          <div className="space-y-3.5">
            {REQUIRED_MODELS.map((model) => {
              const isConnected = modelsStatus[model.id] || allConnected;

              return (
                <div
                  key={model.id}
                  className="flex items-center justify-between rounded-lg border border-[#d8e8f8] bg-white/80 px-4 py-3 shadow-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-5 w-5 items-center justify-center">
                      {isConnected ? (
                        <span className="font-mono text-sm font-bold text-[#107c41]">
                          ✓
                        </span>
                      ) : (
                        <span className="relative flex h-2.5 w-2.5">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#f59b3c] opacity-75" />
                          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#f59b3c]" />
                        </span>
                      )}
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono text-sm font-semibold tracking-wider text-[#0c1d36]">
                        {model.name}
                      </span>
                      <span className="font-mono text-[10px] uppercase text-[#6d88a8]">
                        {model.origin}
                      </span>
                    </div>
                  </div>

                  <div>
                    {isConnected ? (
                      <span className="font-mono text-xs font-medium tracking-wide text-[#107c41]">
                        Connected
                      </span>
                    ) : (
                      <span className="font-mono text-xs font-medium tracking-wide text-[#8a6020]">
                        Connecting...
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="my-6 h-px w-full bg-[#d0e2f5]" />

          {/* Status readout footer */}
          <div className="text-center font-mono">
            {allConnected ? (
              <div className="space-y-1">
                <p className="text-xs font-semibold tracking-wide text-[#107c41]">
                  All forecast services connected
                </p>
                <p className="text-[11px] uppercase tracking-[0.16em] text-[#4a6585] animate-pulse">
                  Entering HELIOS...
                </p>
              </div>
            ) : hasError ? (
              <div className="space-y-1">
                <p className="text-xs font-medium text-[#b45309]">
                  Waiting for forecast services...
                </p>
                <p className="text-[10px] text-[#6d88a8]">
                  Retrying automatically...
                </p>
              </div>
            ) : (
              <p className="text-xs text-[#4a6585]">
                Connecting to forecast services...
              </p>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
