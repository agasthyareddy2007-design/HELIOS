"""
HELIOS Acquisition Plan Tests

Verifies ml/acquisition_plan.py encodes the verified GFS/ICON findings correctly
and safely. No network calls; pure structure/identity checks.

Coverage:
1.  GFS correctly identified as DETERMINISTIC GFS (not ensemble)
2.  GEFS is never mislabeled as GFS (identity text is explicit)
3.  ICON is not falsely marked as directly available via DWD open data
    (direct route UNAVAILABLE; TIGGE route VERIFIED, deterministic, with RISK)
4.  Unverified/risk fields are represented as such (Status vocabulary)
5.  No download action occurs (downloads_performed / bulk_download_performed False)
6.  2-cycle and 4-cycle configurations represented correctly
7.  Acquisition plan is deterministic (repeated calls identical)
8.  Size estimates present and internally consistent (2-cycle < 4-cycle)
9.  ICON alternatives are each explicitly classified; proxy/derived flagged
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from ml.acquisition_plan import (
    acquisition_plan, gfs_plan, icon_plan, gfs_size_estimate,
    Status, CYCLES_2, CYCLES_4, V1_LEADS_HOURS,
)


def test_gfs_is_deterministic_not_ensemble():
    print("TEST: GFS identified as deterministic (not ensemble)")
    g = gfs_plan()
    assert g["availability"] == Status.VERIFIED.value
    assert g["is_deterministic"] is True
    assert g["is_ensemble"] is False
    idy = g["model_identity"].lower()
    assert "deterministic" in idy
    print("  ✓ GFS deterministic, not ensemble")
    print()
    return True


def test_gefs_not_mislabeled_as_gfs():
    print("TEST: GEFS is not mislabeled as GFS")
    g = gfs_plan()
    idy = g["model_identity"].upper()
    # Identity must explicitly exclude GEFS.
    assert "NOT GEFS" in idy
    # Endpoint bucket is the deterministic GFS bucket, not a GEFS bucket.
    assert "noaa-gfs-bdp-pds" in g["endpoints"]["s3_bucket"]
    assert "gefs" not in g["endpoints"]["s3_bucket"].lower()
    print("  ✓ GEFS explicitly excluded; deterministic GFS bucket used")
    print()
    return True


def test_gfs_variable_mapping_verified():
    print("TEST: GFS variable mapping verified")
    g = gfs_plan()
    assert g["variable_mapping_status"] == Status.VERIFIED.value
    assert g["variable_mapping"]["temperature_2m_c"] == "TMP:2 m above ground"
    # spatial subsetting verified (Accept-Ranges byte-range).
    assert g["spatial_subsetting_status"] == Status.VERIFIED.value
    assert g["verified_probe"]["accept_ranges_bytes"] is True
    print("  ✓ 2m temp -> 'TMP:2 m above ground'; byte-range subsetting verified")
    print()
    return True


def test_icon_not_falsely_available_direct():
    print("TEST: ICON not falsely marked directly available")
    i = icon_plan()
    # Direct DWD open-data historical route is UNAVAILABLE.
    assert i["direct_dwd_open_data"]["availability"] == Status.UNAVAILABLE.value
    # TIGGE route is VERIFIED but carries an explicit RISK.
    assert i["recommended_route"]["route"].startswith("ECMWF TIGGE")
    assert i["recommended_route"]["availability"] == Status.VERIFIED.value
    assert i["acquisition_risk"] == Status.RISK.value
    assert i["acquisition_risk_level"] in ("LOW", "MEDIUM", "HIGH")
    # ICON is deterministic hi-res, explicitly not ensemble/proxy.
    assert i["is_deterministic"] is True and i["is_ensemble"] is False
    assert "not a proxy" in i["model_identity"].lower() or "not a" in i["model_identity"].lower()
    print("  ✓ direct DWD UNAVAILABLE; TIGGE VERIFIED + RISK; deterministic hi-res")
    print()
    return True


def test_status_vocabulary_used():
    print("TEST: VERIFIED/UNVERIFIED/UNAVAILABLE/RISK vocabulary")
    vocab = {"VERIFIED", "UNVERIFIED", "UNAVAILABLE", "RISK"}
    assert {s.value for s in Status} == vocab
    p = acquisition_plan()
    # Each model exposes an availability drawn from the vocabulary.
    assert p["gfs"]["availability"] in vocab
    assert p["icon"]["availability"] in vocab
    assert p["icon"]["direct_dwd_open_data"]["availability"] in vocab
    assert p["icon"]["acquisition_risk"] in vocab
    print("  ✓ status vocabulary present and used")
    print()
    return True


def test_no_download_action():
    print("TEST: no download action")
    p = acquisition_plan()
    assert p["downloads_performed"] is False
    assert p["bulk_download_performed"] is False
    assert p["gfs"]["acquired"] is False
    assert p["icon"]["acquired"] is False
    print("  ✓ no downloads; GFS/ICON not acquired")
    print()
    return True


def test_2cycle_and_4cycle_configs():
    print("TEST: 2-cycle and 4-cycle configurations")
    assert CYCLES_2 == ["00Z", "12Z"]
    assert CYCLES_4 == ["00Z", "06Z", "12Z", "18Z"]
    g = gfs_plan()
    assert g["cycles_available"] == CYCLES_4
    assert g["cycles_recommended_v1"] == CYCLES_2
    i = icon_plan()
    # DWD ICON hi-res deterministic in TIGGE runs 00/12Z ONLY (verified).
    assert i["recommended_route"]["cycles"] == CYCLES_2
    assert i["recommended_route"]["cycles_recommended_v1"] == CYCLES_2
    p = acquisition_plan()
    assert p["cycle_recommendation"]["recommended"] == "2_cycles_per_day"
    assert p["cycle_recommendation"]["not_chosen_for_size_alone"] is True
    print("  ✓ 2-cycle (00Z/12Z) and 4-cycle (00/06/12/18Z) both represented")
    print()
    return True


def test_size_estimates_consistent():
    print("TEST: size estimates consistent (2-cycle < 4-cycle)")
    e2 = gfs_size_estimate(28, 2, len(V1_LEADS_HOURS))
    e4 = gfs_size_estimate(28, 4, len(V1_LEADS_HOURS))
    assert e2["lead_files"] == 28 * 2 * 5 == 280
    assert e4["lead_files"] == 28 * 4 * 5 == 560
    assert e2["total_GB"] < e4["total_GB"]
    assert e4["total_GB"] == round(e2["total_GB"] * 2, 3) or abs(e4["total_GB"] - 2 * e2["total_GB"]) < 0.01
    # temp-only is smaller than 5-var.
    et = gfs_size_estimate(28, 2, len(V1_LEADS_HOURS), temp_only=True)
    assert et["total_GB"] < e2["total_GB"]
    print(f"  ✓ 28d 2cyc {e2['total_GB']}GB < 4cyc {e4['total_GB']}GB; temp-only {et['total_GB']}GB")
    print()
    return True


def test_plan_deterministic():
    print("TEST: acquisition plan deterministic")
    import json
    a = json.dumps(acquisition_plan(), sort_keys=True, default=str)
    b = json.dumps(acquisition_plan(), sort_keys=True, default=str)
    assert a == b
    print("  ✓ repeated calls identical")
    print()
    return True


def test_icon_alternatives_classified():
    print("TEST: ICON alternatives each classified")
    i = icon_plan()
    alts = i["alternatives"]
    classes = {a["classification"] for a in alts}
    assert "genuine_direct_icon" in classes
    assert "icon_derived_or_proxy" in classes
    assert "not_a_forecast_model" in classes
    # The recommended genuine direct ICON is acceptable; proxy/ERA5 are not.
    by_class = {a["classification"]: a for a in alts}
    assert by_class["genuine_direct_icon"]["acceptable_for_helios"] is True
    assert by_class["icon_derived_or_proxy"]["acceptable_for_helios"] is False
    assert by_class["not_a_forecast_model"]["acceptable_for_helios"] is False
    print("  ✓ genuine/derived/proxy/reanalysis classified; proxy & ERA5 rejected")
    print()
    return True


def test_icon_capability_verified_and_ready_with_caveat():
    print("TEST: ICON capability verified + READY_WITH_CAVEAT")
    i = icon_plan()
    # Readiness decision.
    assert i["readiness"] == "READY_WITH_CAVEAT"
    assert i["acquisition_risk_level"] == "LOW"
    cc = i["capability_check"]
    # No retrieval was performed (metadata-only verification).
    assert cc["retrieval_probe_performed"] is False
    assert cc["probe_file_bytes"] == 0
    # Core capability items VERIFIED.
    for k in ["product_identity_status", "type_fc_deterministic_status",
              "leads_status", "cycles_status", "param_2t_status",
              "units_kelvin_status", "spatial_subset_status",
              "coverage_jan2025_status"]:
        assert cc[k] == Status.VERIFIED.value, k
    # The single caveat is UNVERIFIED (ECDS credential validity).
    assert cc["ecds_credential_validity_status"] == Status.UNVERIFIED.value
    print("  ✓ product/type/leads/cycles/param/units/area/coverage VERIFIED; "
          "ECDS cred UNVERIFIED; READY_WITH_CAVEAT")
    print()
    return True


def test_icon_verified_request_and_identity():
    print("TEST: ICON verified request + deterministic identity")
    rr = icon_plan()["recommended_route"]
    req = rr["verified_request"]
    # Exact request identity (deterministic hi-res ICON).
    assert req["dataset"] == "tigge-forecasts"
    assert req["origin"] == "dwd"
    assert req["type"] == "fc"           # deterministic hi-res, NOT cf/pf ensemble
    assert req["param"] == "2t"
    assert req["levtype"] == "sfc"
    assert req["step"] == [6, 24, 48, 72, 120]
    assert req["time"] == ["00:00", "12:00"]     # 00Z + 12Z only
    assert req["area"] == [38, 68, 6, 97]        # N, W, S, E (India)
    assert req["format"] == "grib"
    assert rr["mars_origin_id"] == "edzw"
    # Cycles verified as 00/12Z ONLY for DWD ICON (aligns with IFS).
    assert rr["cycles"] == ["00Z", "12Z"]
    assert rr["units_returned"].startswith("K")
    print("  ✓ origin=dwd type=fc 2t sfc, steps 6/24/48/72/120, 00/12Z, area N/W/S/E")
    print()
    return True


def test_icon_v1_workload_estimate():
    print("TEST: ICON V1 workload estimate present + sane")
    i = icon_plan()
    w = i["v1_workload_estimate"]
    assert w["days"] == 28 and w["cycles_per_day"] == 2
    assert w["leads"] == [6, 24, 48, 72, 120]
    lo, hi = w["size_range_MB"]
    assert 0 < lo < hi <= 100  # single-digit-to-low-tens MB range
    assert "224 requests" in w["comparison_to_ifs"]
    print(f"  ✓ 280 requests, size range {lo}-{hi} MB, IFS-order-of-magnitude")
    print()
    return True
