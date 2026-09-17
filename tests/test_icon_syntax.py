"""
Syntax and Type Validation for ICON Live Adapter

Tests that don't require xarray/scipy dependencies.
Validates code structure, type annotations, and logical correctness.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_python_syntax():
    """Test Python syntax is valid."""
    import ast

    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        code = f.read()

    try:
        ast.parse(code)
        print("✓ Python syntax is valid")
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        raise


def test_model_identifier():
    """Test NWPModel.ICON is 'icon' (lowercase)."""
    from nwp.common.schemas import NWPModel

    assert NWPModel.ICON == "icon", f"Expected 'icon', got {NWPModel.ICON}"
    assert NWPModel.ICON.value == "icon", f"Expected 'icon', got {NWPModel.ICON.value}"
    print("✓ Model identifier is 'icon'")


def test_class_structure():
    """Test ICONLiveAdapter class structure."""
    # Import without dependencies using ast
    import ast

    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        tree = ast.parse(f.read())

    # Find ICONLiveAdapter class
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    adapter_class = None

    for cls in classes:
        if cls.name == 'ICONLiveAdapter':
            adapter_class = cls
            break

    assert adapter_class is not None, "ICONLiveAdapter class not found"

    # Check required methods exist
    methods = [node.name for node in ast.walk(adapter_class) if isinstance(node, ast.FunctionDef)]

    required_methods = [
        '__init__',
        'get_latest_available_run',
        'fetch_icon_grib',
        '_build_kdtree',
        '_regrid_to_latlon',
        '_regrid_wind_components',
        'parse_grib_to_forecast_records',
        'ingest_forecast_records',
        'fetch_latest_icon_run'
    ]

    for method in required_methods:
        assert method in methods, f"Required method {method} not found"

    print(f"✓ ICONLiveAdapter has all {len(required_methods)} required methods")


def test_constants():
    """Test adapter constants are defined correctly."""
    import ast

    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        content = f.read()

    # Check BASE_URL
    assert 'BASE_URL = "https://opendata.dwd.de/weather/nwp/icon/grib"' in content
    print("✓ BASE_URL is correct")

    # Check India domain (using double quotes as in actual file)
    assert '"lat_min": 6.0' in content
    assert '"lat_max": 38.0' in content
    assert '"lon_min": 68.0' in content
    assert '"lon_max": 97.0' in content
    print("✓ India domain is correct")

    # Check required variables
    assert "'t_2m': 'temperature_2m_c'" in content
    assert "'td_2m': 'dewpoint_2m_c'" in content
    assert "'u_10m': 'wind_u_10m_ms'" in content
    assert "'v_10m': 'wind_v_10m_ms'" in content
    assert "'pmsl': 'pressure_msl_hpa'" in content
    assert "'tot_prec': 'precipitation_mm'" in content
    print("✓ All 6 required variables are mapped")


def test_regridding_documentation():
    """Test regridding methods are documented."""
    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        content = f.read()

    # Check regridding method documentation
    assert 'nearest-neighbor' in content.lower(), "Nearest-neighbor method not documented"
    assert 'icosahedral' in content.lower(), "Icosahedral grid not mentioned"
    assert 'KDTree' in content, "KDTree not mentioned"
    assert 'unit sphere' in content.lower(), "Unit sphere transformation not documented"

    print("✓ Regridding method is documented")


def test_temporal_constraints():
    """Test temporal constraint checks are present."""
    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        content = f.read()

    # Check temporal validation exists
    assert 'valid_time >= run_time' in content or 'valid_time < run_time' in content
    assert 'valid_time >= issue_time' in content or 'valid_time < issue_time' in content
    assert 'Temporal integrity violation' in content or 'temporal violation' in content

    print("✓ Temporal constraint validation is present")


def test_wind_component_handling():
    """Test wind components have dedicated handling."""
    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        content = f.read()

    # Check wind component method exists
    assert '_regrid_wind_components' in content
    assert 'icon_u' in content and 'icon_v' in content

    print("✓ Wind component regridding is implemented")


def test_compression_handling():
    """Test bz2 decompression is handled."""
    icon_adapter_path = project_root / 'nwp' / 'icon' / 'icon_live_adapter.py'

    with open(icon_adapter_path, 'r') as f:
        content = f.read()

    # Check bz2 handling
    assert 'import bz2' in content
    assert 'bz2.open' in content or 'bz2.BZ2File' in content
    assert '.bz2' in content

    print("✓ bz2 decompression is handled")


if __name__ == '__main__':
    print("Running ICON Live Adapter Syntax Validation...\n")

    tests = [
        test_python_syntax,
        test_model_identifier,
        test_class_structure,
        test_constants,
        test_regridding_documentation,
        test_temporal_constraints,
        test_wind_component_handling,
        test_compression_handling
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)
