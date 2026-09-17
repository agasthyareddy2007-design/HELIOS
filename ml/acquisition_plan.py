"""
HELIOS Historical NWP Acquisition Plan (PLANNING / VERIFICATION ONLY — NO DOWNLOADS)

Machine-readable record of the VERIFIED historical data-access findings for GFS
and ICON, used to decide the future GFS+IFS+ICON acquisition. This module records
intent and verified endpoint facts only. It DOWNLOADS NOTHING.

STATUS VOCABULARY (per field / per model)
-----------------------------------------
- VERIFIED     : confirmed from an authoritative source (and, for GFS, a
                 metadata-only HTTP/S3 check that downloaded NO forecast data).
- UNVERIFIED   : plausible/planning assumption not yet confirmed; confirm before
                 acquisition.
- UNAVAILABLE  : confirmed NOT available by the intended route.
- RISK         : a flagged risk requiring verification before/at acquisition.

CRITICAL IDENTITY RULES (must remain accurate in any HELIOS paper/demo)
----------------------------------------------------------------------
- GFS  != GEFS (GFS is the deterministic Global Forecast System; GEFS is the
  ensemble). This plan targets DETERMINISTIC GFS only.
- ICON != a generic DWD model, and an ICON proxy != direct ICON.
- ERA5 / reanalysis is NOT a forecast model and is not an acceptable substitute.
- NOAA ISD observations are the verification truth; they are NOT reanalysis and
  are NOT replaced.

VERIFICATION PROVENANCE (this task; no bulk download performed)
---------------------------------------------------------------
- GFS: NOAA Open Data Dissemination registry (noaa-gfs-bdp-pds) + a metadata-only
  S3 REST listing, an HTTP HEAD (size + Accept-Ranges), and the tiny .idx text
  index for gfs.20250101/00/atmos/gfs.t00z.pgrb2.0p25.f024. NO forecast GRIB was
  downloaded. Corroborated by NCAR RDA d084001 and NOMADS docs.
- ICON: ECMWF TIGGE authoritative wiki (model additions/history) + DWD Open Data
  retention behaviour. No ICON data downloaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Tuple


class Status(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    UNAVAILABLE = "UNAVAILABLE"
    RISK = "RISK"


# India domain (same as IFS V1) and target window.
INDIA_DOMAIN = {"north": 38.0, "south": 6.0, "west": 68.0, "east": 97.0}
V1_TARGET_PERIOD = "2025-01-01 .. 2025-01-28"
V1_LEADS_HOURS = [6, 24, 48, 72, 120]
CYCLES_2 = ["00Z", "12Z"]
CYCLES_4 = ["00Z", "06Z", "12Z", "18Z"]

# Canonical HELIOS feature-contract variables (temperature is the V1 target;
# the others are contract-mapped for future multi-variable expansion).
FEATURE_CONTRACT_VARIABLES = [
    "temperature_2m_c",   # PRIMARY (V1)
    "dewpoint_2m_c",
    "wind_u_10m_ms",
    "wind_v_10m_ms",
    "pressure_msl_hpa",
]


# =====================================================================
# IFS (already acquired) — alignment target
# =====================================================================
IFS_V1_ALIGNMENT: Dict[str, Any] = {
    "status": Status.VERIFIED.value,
    "acquired": True,
    "note_provenance": "helios_fact (in-repo V1 dataset)",
    "source": "ECMWF TIGGE (historical)",
    "product": "IFS 2 m temperature (2t, param 167) historical forecast",
    "period": V1_TARGET_PERIOD,
    "cycles": CYCLES_2,
    "leads_hours": V1_LEADS_HOURS,
    "variables": ["temperature_2m_c"],
    "spatial_subset": INDIA_DOMAIN,
    "spatial_handling": "station-anchored to NOAA ISD stations (353 stations)",
    "verification": "NOAA ISD-Lite 2 m temperature (100% matched for V1)",
    "access": "ECMWF TIGGE archive/API (MARS / ecmwf-api-client)",
    "alignment_requirement": (
        "GFS and ICON MUST align to these identity axes "
        "(issue_time, valid_time, latitude, longitude, variable) so DatasetBuilder "
        "can pivot canonical examples per (issue,valid,lat,lon,variable). Same "
        "India domain, same 2 m temperature in degC, same NOAA ISD verification "
        "stations/valid_times, cycles 00Z+12Z."
    ),
}


# =====================================================================
# GFS — VERIFIED
# =====================================================================
def gfs_variable_mapping() -> Dict[str, str]:
    """
    Map HELIOS feature-contract variables to EXACT GFS GRIB2 identifiers,
    confirmed from the real gfs.t00z.pgrb2.0p25.f024.idx index (metadata only).
    """
    return {
        "temperature_2m_c": "TMP:2 m above ground",     # PRIMARY (V1)
        "dewpoint_2m_c": "DPT:2 m above ground",
        "wind_u_10m_ms": "UGRD:10 m above ground",
        "wind_v_10m_ms": "VGRD:10 m above ground",
        "pressure_msl_hpa": "PRMSL:mean sea level",
    }


# Per-lead byte-range sizes (bytes) measured from the real .idx (global GRIB2
# messages; India crop is applied client-side after byte-range extraction).
GFS_PER_MESSAGE_BYTES = {
    "TMP:2 m above ground": 863145,
    "DPT:2 m above ground": 907669,
    "UGRD:10 m above ground": 959202,
    "VGRD:10 m above ground": 937161,
    "PRMSL:mean sea level": 990166,
}
GFS_FULL_GLOBAL_FILE_BYTES = 539500154  # one (cycle,lead) global pgrb2.0p25 file


def _mb(n_bytes: float) -> float:
    return round(n_bytes / (1024.0 * 1024.0), 3)


def _gb(n_bytes: float) -> float:
    return round(n_bytes / (1024.0 * 1024.0 * 1024.0), 3)


def gfs_size_estimate(days: int, cycles_per_day: int, n_leads: int,
                      variables: Tuple[str, ...] = tuple(FEATURE_CONTRACT_VARIABLES),
                      temp_only: bool = False) -> Dict[str, Any]:
    """
    Estimate GFS byte-range download workload. Downloads whole GRIB messages per
    variable per (cycle, lead); India crop is client-side and does not reduce the
    downloaded message size materially.
    """
    mapping = gfs_variable_mapping()
    if temp_only:
        vars_ids = [mapping["temperature_2m_c"]]
    else:
        vars_ids = [mapping[v] for v in variables if v in mapping]
    per_lead_bytes = sum(GFS_PER_MESSAGE_BYTES[v] for v in vars_ids)
    lead_files = days * cycles_per_day * n_leads
    total_bytes = lead_files * per_lead_bytes
    # Requests: one .idx fetch + one ranged GRIB fetch per (cycle,lead), or a
    # single multi-range request per lead. Upper bound uses 2 per lead-file.
    return {
        "days": days,
        "cycles_per_day": cycles_per_day,
        "n_leads": n_leads,
        "variables": vars_ids,
        "lead_files": lead_files,
        "per_lead_MB": _mb(per_lead_bytes),
        "total_GB": _gb(total_bytes),
        "approx_http_requests_upper_bound": lead_files * 2,
    }


def gfs_plan() -> Dict[str, Any]:
    est_28_2 = gfs_size_estimate(28, 2, len(V1_LEADS_HOURS))
    est_28_4 = gfs_size_estimate(28, 4, len(V1_LEADS_HOURS))
    est_2025_2 = gfs_size_estimate(365, 2, len(V1_LEADS_HOURS))
    est_2025_4 = gfs_size_estimate(365, 4, len(V1_LEADS_HOURS))
    est_28_2_temp = gfs_size_estimate(28, 2, len(V1_LEADS_HOURS), temp_only=True)
    est_28_4_temp = gfs_size_estimate(28, 4, len(V1_LEADS_HOURS), temp_only=True)
    return {
        "model": "gfs",
        "availability": Status.VERIFIED.value,
        "acquired": False,
        "model_identity": ("Deterministic Global Forecast System (GFS), NCEP, "
                           "FV3 dynamical core. NOT GEFS (ensemble). NOT GDAS "
                           "analysis."),
        "is_deterministic": True,
        "is_ensemble": False,
        "authoritative_source": "NOAA Open Data Dissemination (NODD)",
        "endpoints": {
            "s3_bucket": "s3://noaa-gfs-bdp-pds  (us-east-1, --no-sign-request, public/no-auth)",
            "https_host": "https://noaa-gfs-bdp-pds.s3.amazonaws.com/",
            "key_pattern": "gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fLLL (+ .fLLL.idx sidecar)",
            "corroboration": ["NCAR RDA d084001 (GFS 0.25 historical archive)",
                              "NOMADS (near-real-time, get_grib filter)"],
        },
        "resolution": "0.25 degree (pgrb2.0p25)",
        "cycles_available": CYCLES_4,           # 00/06/12/18Z
        "cycles_recommended_v1": CYCLES_2,      # align to IFS 00Z+12Z
        "leads_hours_available": "hourly 0-120h, 3-hourly 120-240h, 12-hourly 240-384h",
        "leads_hours_v1": V1_LEADS_HOURS,       # +6/+24/+48/+72/+120 all available
        "leads_note": "+6h IS available (GFS is hourly to +120h); no substitute needed.",
        "variables_v1": ["temperature_2m_c"],
        "variable_mapping": gfs_variable_mapping(),
        "variable_mapping_status": Status.VERIFIED.value,
        "spatial_subset": INDIA_DOMAIN,
        "spatial_subsetting_capability": (
            "Server-side HTTP byte-range on S3 (Accept-Ranges: bytes CONFIRMED) "
            "using .idx offsets to fetch only the needed GRIB message(s); India "
            "crop applied client-side. NOMADS get_grib offers subregion filtering "
            "for recent data but the S3 byte-range path is the durable historical "
            "route."
        ),
        "spatial_subsetting_status": Status.VERIFIED.value,
        "data_format": "GRIB2 (one file per (cycle,lead); leads are separate files)",
        "verified_probe": {
            "note": "metadata-only; NO forecast GRIB downloaded",
            "probed_key": "gfs.20250101/00/atmos/gfs.t00z.pgrb2.0p25.f024",
            "full_global_file_bytes": GFS_FULL_GLOBAL_FILE_BYTES,
            "idx_bytes": 41250,
            "accept_ranges_bytes": True,
        },
        "size_estimates": {
            "28d_2cycle_5var": est_28_2,
            "28d_4cycle_5var": est_28_4,
            "28d_2cycle_temp_only": est_28_2_temp,
            "28d_4cycle_temp_only": est_28_4_temp,
            "full2025_2cycle_5var": est_2025_2,
            "full2025_4cycle_5var": est_2025_4,
        },
        "storage_note": ("Estimates cover FORECAST leads (pgrb2 fLLL) that HELIOS "
                         "needs. The ~14.3 GB 'analysis-only' figure refers to "
                         "GDAS/analysis and does NOT apply here."),
        "acquisition_risks": [
            "planning_default: 00Z/12Z cycle subset to align with IFS V1.",
            "K -> degC conversion required (GRIB TMP is in Kelvin).",
            "Regrid 0.25deg to NOAA ISD station anchors (bilinear); keep method "
            "consistent with ICON regridding for fair comparison.",
        ],
    }


# =====================================================================
# ICON — VERIFIED via TIGGE (deterministic hi-res); direct DWD open data UNAVAILABLE
# =====================================================================
def icon_plan() -> Dict[str, Any]:
    return {
        "model": "icon",
        "availability": Status.VERIFIED.value,   # via TIGGE (see route)
        "acquired": False,
        "model_identity": ("DWD ICON global model, DETERMINISTIC high-resolution "
                           "forecast interpolated to the TIGGE ensemble resolution. "
                           "NOT the ICON-EPS ensemble mean; NOT a proxy; NOT a "
                           "generic DWD model."),
        "is_deterministic": True,
        "is_ensemble": False,
        "recommended_route": {
            "route": "ECMWF TIGGE (ECDS: dataset=tigge-forecasts)",
            "availability": Status.VERIFIED.value,
            "authoritative_source": ("ECMWF TIGGE Models table (row DWD/edzw, "
                                     "config 2020-12-17) + TIGGE wiki + ECDS "
                                     "tigge-forecasts page + ECMWF parameter DB"),
            "endpoint": ("ECDS https://ecds.ecmwf.int/api dataset 'tigge-forecasts' "
                         "(cdsapi client) — SAME portal/mechanism used for IFS V1; "
                         "TIGGE catalogue migrated apps.ecmwf.int -> ECDS 2026-05-27"),
            "originating_centre": "Deutscher Wetterdienst (DWD)",
            "mars_origin_id": "edzw",
            "product": ("DWD ICON global HIGH-RESOLUTION DETERMINISTIC forecast "
                        "(MARS type=fc), interpolated to the ensemble resolution"),
            "control_forecast_note": ("DWD has NO control-forecast concept in TIGGE "
                                      "(ensemble = 40 perturbed members, no +1). The "
                                      "deterministic product is the hi-res forecast "
                                      "type=fc — NOT cf, NOT pf ensemble."),
            "resolution": "0.5 x 0.5 deg regular lat/lon (720 x 361); original R3B06 ~26.5 km",
            "cycles": CYCLES_2,                 # DWD ICON in TIGGE runs 00/12Z ONLY
            "cycles_recommended_v1": CYCLES_2,  # 00Z+12Z aligns exactly with IFS
            "cycles_note": ("VERIFIED: DWD ICON in TIGGE runs at 00Z and 12Z ONLY "
                            "(no 06/18Z), so 2-cycle V1 aligns exactly with IFS."),
            "time_range_hours": "0-180 hourly (both 00Z and 12Z runs)",
            "leads_hours_available_all": [6, 24, 48, 72, 120],
            "leads_hours_v1": V1_LEADS_HOURS,
            "leads_status": Status.VERIFIED.value,
            "variables_v1": ["temperature_2m_c"],
            "parameter_mapping": {"temperature_2m_c": "2t (param 167)"},
            "units_returned": "K (Kelvin)",
            "units_conversion": "Kelvin -> Celsius (t_K - 273.15), same as IFS V1",
            "units_status": Status.VERIFIED.value,
            "historical_coverage": ("DWD in TIGGE back-archived from 2020-03-01; "
                                    "ICON specifically from 2020-12-07 => "
                                    "2025-01 COVERED."),
            "spatial_subsetting": "server-side ECDS/MARS area=[N,W,S,E]",
            "spatial_subset_area_NWSE": [INDIA_DOMAIN["north"], INDIA_DOMAIN["west"],
                                         INDIA_DOMAIN["south"], INDIA_DOMAIN["east"]],
            "spatial_subset": INDIA_DOMAIN,
            "spatial_subsetting_status": Status.VERIFIED.value,
            "licensing": "TIGGE research licence (same as IFS V1 already acquired)",
            "data_format": "GRIB2",
            "verified_request": {
                "dataset": "tigge-forecasts",
                "origin": "dwd",
                "type": "fc",
                "levtype": "sfc",
                "param": "2t",
                "time": ["00:00", "12:00"],
                "step": [6, 24, 48, 72, 120],
                "area": [38, 68, 6, 97],   # N, W, S, E
                "format": "grib",
            },
        },
        "capability_check": {
            "method": ("authoritative metadata verification (ECMWF TIGGE Models "
                       "table + wiki + ECDS dataset page + parameter DB). NO "
                       "retrieval performed."),
            "retrieval_probe_performed": False,
            "probe_file_bytes": 0,
            "product_identity_status": Status.VERIFIED.value,
            "type_fc_deterministic_status": Status.VERIFIED.value,
            "leads_status": Status.VERIFIED.value,      # 0-180h hourly => 6/24/48/72/120
            "cycles_status": Status.VERIFIED.value,     # 00Z + 12Z only
            "param_2t_status": Status.VERIFIED.value,
            "units_kelvin_status": Status.VERIFIED.value,
            "spatial_subset_status": Status.VERIFIED.value,
            "coverage_jan2025_status": Status.VERIFIED.value,
            "ecds_credential_validity_status": Status.UNVERIFIED.value,
            "ecds_credential_note": (
                "~/.cdsapirc currently targets the Copernicus CDS "
                "(cds.climate.copernicus.eu), NOT the ECDS TIGGE endpoint. IFS V1 "
                "was acquired via ECDS previously, so ECDS access worked "
                "historically, but current-env credential validity for ECDS was "
                "NOT tested (avoids muddying the capability signal; no credential "
                "creation per project rules). Resolve at acquisition start."
            ),
        },
        "direct_dwd_open_data": {
            "route": "DWD Open Data (opendata.dwd.de)",
            "availability": Status.UNAVAILABLE.value,
            "reason": ("opendata.dwd.de is a ROLLING/LIVE store (~last 24h of "
                       "runs). It is NOT a historical archive; 2025-01 ICON runs "
                       "are no longer present."),
        },
        "acquisition_risk": Status.RISK.value,
        "acquisition_risk_level": "LOW",
        "acquisition_risk_notes": [
            "VERIFIED from authoritative metadata: product identity (ICON hi-res "
            "deterministic, type=fc), leads 6/24/48/72/120 (0-180h hourly), cycles "
            "00Z/12Z, param 2t, units Kelvin, server-side area subset, Jan-2025 "
            "coverage.",
            "UNVERIFIED (single caveat): ECDS credential validity in THIS env "
            "(~/.cdsapirc points at Copernicus CDS, not ECDS). Non-critical: "
            "resolvable at acquisition start; does not affect product availability.",
            "ICON native grid is icosahedral; the TIGGE product is already "
            "interpolated to 0.5deg, so regrid to NOAA ISD station anchors "
            "(bilinear, consistent with GFS); K -> degC.",
        ],
        "v1_workload_estimate": {
            "days": 28,
            "cycles_per_day": 2,
            "leads": V1_LEADS_HOURS,
            "variable": "temperature_2m_c (2t)",
            "requests": ("280 (28 days x 2 cycles x 5 leads) as one-per-(issue,step) "
                         "or fewer if step-lists are batched per request"),
            "size_range_MB": [5, 30],
            "size_note": ("India 0.5deg 2t subset per field is a few KB-tens KB; "
                          "total single-digit-to-low-tens MB. Requests (queue/rate-"
                          "limit), not bytes, dominate."),
            "comparison_to_ifs": ("Same order of magnitude as IFS V1 "
                                  "(~15.4 MB for 224 requests)."),
        },
        "readiness": "READY_WITH_CAVEAT",
        "readiness_rationale": (
            "All target parameters, cycles, leads, product identity, units, and "
            "spatial subset are VERIFIED from authoritative TIGGE metadata. One "
            "non-critical uncertainty remains: ECDS credential validity in this "
            "environment (resolvable at acquisition start). Per the readiness "
            "logic this is READY WITH CAVEAT, not fully READY."
        ),
        "alternatives": icon_alternatives(),
    }


def icon_alternatives() -> List[Dict[str, Any]]:
    """
    Legitimate ICON alternatives, each explicitly CLASSIFIED. Only classes
    'genuine_direct' are first-choice; proxies/derived are flagged as such.
    """
    return [
        {
            "name": "TIGGE DWD ICON hi-res deterministic forecast",
            "classification": "genuine_direct_icon",
            "source": "ECMWF TIGGE",
            "historical_period": "ICON from 2020-12-07 (covers 2025-01)",
            "resolution": "0.5 deg (archived); original R3B06 ~26.5 km",
            "variables": ["2t (temperature_2m_c)"],
            "cycles": CYCLES_2,
            "leads": "0-180h hourly at both 00Z and 12Z (6/24/48/72/120 available)",
            "licensing": "TIGGE research licence (already held for IFS)",
            "acceptable_for_helios": True,
            "why": ("Genuine deterministic ICON (MARS type=fc), same portal/licence "
                    "as IFS, 2025-01 covered, honest model identity. RECOMMENDED."),
        },
        {
            "name": "TIGGE DWD ICON-EPS ensemble (40 members)",
            "classification": "genuine_direct_icon_but_ensemble",
            "source": "ECMWF TIGGE",
            "historical_period": "covers 2025-01",
            "resolution": "~40 km (20 km Europe refinement)",
            "variables": ["2t"],
            "cycles": CYCLES_4,
            "leads": "00/12Z +180h; 06/18Z +120h",
            "licensing": "TIGGE research licence",
            "acceptable_for_helios": True,
            "why": ("Genuine ICON but ENSEMBLE; would require ensemble-mean and "
                    "must be documented as ensemble (different product type than "
                    "the deterministic IFS). Not first choice for a clean "
                    "deterministic 3-model blend."),
        },
        {
            "name": "DWD Open Data live ICON",
            "classification": "genuine_direct_icon_but_unavailable_historically",
            "source": "opendata.dwd.de",
            "historical_period": "UNAVAILABLE for 2025-01 (rolling ~24h retention)",
            "acceptable_for_helios": False,
            "why": "Direct ICON but not archived for the target historical window.",
        },
        {
            "name": "Open-Meteo 'DWD ICON' API",
            "classification": "icon_derived_or_proxy",
            "source": "open-meteo.com",
            "historical_period": "has archived past days",
            "acceptable_for_helios": False,
            "why": ("Reprocessed/regridded/blended ICON-derived product, not the "
                    "raw ICON forecast; unclear exact model identity for a "
                    "scientific paper. Classify as DERIVED/PROXY, not direct ICON."),
        },
        {
            "name": "ERA5 / reanalysis",
            "classification": "not_a_forecast_model",
            "source": "Copernicus C3S",
            "acceptable_for_helios": False,
            "why": "Reanalysis, NOT a forecast model; cannot substitute for ICON.",
        },
    ]


# =====================================================================
# Cycle strategy + full plan
# =====================================================================
def cycle_recommendation() -> Dict[str, Any]:
    return {
        "recommended": "2_cycles_per_day",
        "cycles": CYCLES_2,   # 00Z + 12Z
        "rationale": (
            "IFS V1 is 00Z+12Z. A 2-cycle GFS/ICON acquisition aligns all three "
            "models at IDENTICAL issue_times, which is what the reliability blend "
            "needs; 4-cycle GFS/ICON at 06Z/18Z would have NO matching IFS and be "
            "wasted for blending in V1. 2-cycle also halves storage, request "
            "count, and rate-limit exposure, and ICON hi-res at 06/18Z only "
            "reaches +120h anyway. 4 cycles/day is deferred to post-V1 if/when IFS "
            "is extended to 06Z/18Z."
        ),
        "not_chosen_for_size_alone": True,
    }


def acquisition_strategy() -> Dict[str, Any]:
    return {
        "order": [
            "Confirm exact TIGGE ICON hi-res retrieval params (origin/type/2t/leads) "
            "with a metadata/capability check (no bulk download).",
            "Acquire GFS (2 cycles/day, 00Z+12Z) via S3 byte-range for the V1 window "
            "and India domain; regrid to NOAA ISD stations; K->degC.",
            "Acquire ICON hi-res deterministic (2 cycles/day) via TIGGE MARS area "
            "subset for the V1 window; regrid to NOAA ISD stations; K->degC.",
            "Align GFS+ICON to IFS identity axes; verify against NOAA ISD; run "
            "DatasetBuilder leakage checks.",
        ],
        "verification_source": "NOAA ISD-Lite (unchanged; NOT replaced).",
        "consistent_regridding": "Same bilinear-to-station method for GFS and ICON.",
    }


def acquisition_plan() -> Dict[str, Any]:
    """Full structured, machine-readable acquisition plan. NO DOWNLOADS."""
    return {
        "downloads_performed": False,
        "bulk_download_performed": False,
        "note": (
            "Verification/planning only. GFS and ICON are NOT acquired. Only the "
            "IFS/TIGGE V1 dataset exists. GFS availability VERIFIED via NOAA NODD "
            "(metadata-only probe). ICON deterministic hi-res VERIFIED available "
            "via ECMWF TIGGE; direct DWD open-data historical is UNAVAILABLE."
        ),
        "india_domain": INDIA_DOMAIN,
        "target_period_v1": V1_TARGET_PERIOD,
        "alignment_target_ifs_v1": dict(IFS_V1_ALIGNMENT),
        "gfs": gfs_plan(),
        "icon": icon_plan(),
        "cycle_recommendation": cycle_recommendation(),
        "acquisition_strategy": acquisition_strategy(),
        "scale_note": (
            "V1 window (28 days) is MVP scope. Sizes/cadence are parameters; the "
            "plan scales to larger post-V1 periods without code changes."
        ),
    }
