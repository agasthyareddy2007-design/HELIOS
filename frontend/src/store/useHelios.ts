"use client";

import { create } from "zustand";
import type { NwpModel, StationLocation } from "@/lib/types";

/**
 * HELIOS interaction state.
 *
 * Deliberately small: it holds only what the user has *chosen*. All server data
 * lives in the data hooks (src/hooks/useHeliosData.ts) so there is one source of
 * truth per resource and no risk of stale duplicated API payloads.
 */
export interface HeliosState {
  /** Currently selected forecast location (null until the user picks one). */
  station: StationLocation | null;
  /** True once the user has actively chosen a location on the map. */
  hasSelection: boolean;
  /**
   * Selected forecast horizon in hours, or null to follow the cycle (the first
   * horizon whose valid time is still in the future).
   */
  leadHours: number | null;
  /** Which NWP model the user is inspecting (hover/focus), for subtle emphasis. */
  focusedModel: NwpModel | null;

  selectStation: (s: StationLocation) => void;
  setLeadHours: (h: number | null) => void;
  setFocusedModel: (m: NwpModel | null) => void;
}

export const useHelios = create<HeliosState>((set) => ({
  station: null,
  hasSelection: false,
  leadHours: null,
  focusedModel: null,

  selectStation: (station) => set({ station, hasSelection: true }),
  setLeadHours: (leadHours) => set({ leadHours }),
  setFocusedModel: (focusedModel) => set({ focusedModel }),
}));
