# HELIOS V2

**Weather-Model Blending and Post-Processing Platform**

> *"HELIOS does not learn the weather. It learns when to trust each model."*

HELIOS V2 is a model post-processing and ensemble blending system for numerical weather prediction. Rather than simulating atmospheric physics directly, HELIOS uses machine learning to evaluate the conditional reliability of major operational weather models and compute dynamic, error-weighted ensemble forecasts.

---

## Overview

Numerical Weather Prediction (NWP) models exhibit varying regional and situational biases across different lead times, geographic features, and seasonal regimes. HELIOS ingests raw forecasts from leading global models:

- **GFS** (NOAA Global Forecast System)
- **IFS** (ECMWF Integrated Forecasting System)
- **ICON** (Deutscher Wetterdienst)

Using an inverse-error weighted blending strategy driven by trained gradient-boosted decision trees (XGBoost), HELIOS dynamically weights model contributions based on predicted forecast error to produce an optimal blended output.

---

## Core Architecture

### Blending Pipeline

```text
GFS (NOAA)  ──┐
IFS (ECMWF) ──┼──→ HELIOS V2 XGBoost Blender ──→ Calibrated Blended Forecast
ICON (DWD)  ──┘
```

### Live Serving Architecture

```text
User / Web Browser
      │
      ▼
Vercel (Next.js 16 App Router)
      │
      ▼
Server-Side API Proxy (`/api/helios/[...path]`)
      │  (Secured with HTTP-only session cookies)
      ▼
Tailscale Funnel (Public HTTPS Ingress)
      │
      ▼
HELIOS Inference Host (FastAPI on Port 8011)
      │
      ▼
HELIOS V2 Engine (`HeliosV2Service` / `helios.pkl`)
```

---

## V2 Evaluation & Benchmark

HELIOS V2 was evaluated on a strictly held-out historical test set that was never exposed during model fitting or feature parameter tuning.

### Held-Out Test Results

| System | Mean Absolute Error (MAE) | Relative MAE Reduction |
| :--- | :---: | :---: |
| **Statistical Average Baseline** | 1.780°C | — |
| **HELIOS V2 (XGBoost)** | **1.626°C** | **8.65%** |

*Evaluation domain and parameters:*
- **Evaluation Dataset**: 493,473 strictly held-out verification samples.
- **Domain**: India ($6^\circ\text{N}\text{--}38^\circ\text{N}, 68^\circ\text{E}\text{--}97^\circ\text{E}$).
- **Canonical Resolution**: $0.5^\circ \times 0.5^\circ$ grid.
- **Target Variable**: 2-meter surface temperature (`temperature_2m_c`).

> *Note on evaluation metrics*: On the strictly held-out V2 test set, HELIOS reduced MAE by 8.65% relative to the Statistical Average baseline. This figure represents empirical performance over the held-out sample partition and does not claim uniform geographic improvement across all atmospheric phenomena or statistical independence of samples.

---

## Frozen Model Artifact

The active HELIOS V2 model is frozen and tracked in the repository for deployment:

- **File**: `ml/artifacts/lockedtest_v2_20260915_184718/helios.pkl`
- **Architecture**: XGBoost error-prediction ensemble
- **SHA256**: `b9ddcf428fea41f27a329e8e00dcc4b197ad9c71c634c8b64deb2f36877d2af2`

*(Raw training datasets and historical observational archives are excluded from this repository).*

---

## Repository Structure

```text
HELIOS/
├── backend/          # FastAPI backend, auth mechanisms, and API endpoints
├── database/         # SQLAlchemy schemas and database connection management
├── data/             # Station metadata (GHCNd, ISD) and reference grid indices
├── docs/             # Technical specifications, audit reports, and architecture guides
├── frontend/         # Next.js 16 web application and fluid visual interface
├── ml/               # Feature engineering, candidate interfaces, and locked V2 model
├── tests/            # Automated test suite for data, features, and inference
├── validation/       # Temporal integrity and causal validation utilities
├── pyproject.toml    # Python dependency specifications and pytest configuration
├── start_helios.sh   # Native runtime startup script
└── stop_helios.sh    # Graceful backend shutdown script
```

---

## Security & Privacy

- **API-Key Authentication**: Protected backend endpoints require valid keys validated via PBKDF2 HMAC-SHA256 constant-time comparison.
- **Server-Side Proxying**: Next.js route handlers keep upstream keys securely server-side; browser sessions use `httpOnly` secure cookies.
- **Isolated Storage**: Local SQLite operational databases and dynamic runtime logs are strictly `.gitignore` excluded from the version control history.

---

## Local Development & Setup

### Prerequisites

- Linux (x86_64) or macOS
- Python 3.10+
- Node.js 18+ and npm

### Backend Setup

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies in editable mode:
   ```bash
   pip install -e ".[dev]"
   ```

3. Start the backend service:
   ```bash
   ./start_helios.sh
   ```

4. Verify service health:
   ```bash
   curl http://127.0.0.1:8011/v1/health
   ```

5. Stop the backend cleanly:
   ```bash
   ./stop_helios.sh
   ```

### Frontend Setup

1. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Configure local environment variables:
   ```bash
   cp .env.example .env.local
   ```
   Set `HELIOS_API_BASE=http://127.0.0.1:8011` for direct local development.

3. Run the development server or build for production:
   ```bash
   npm run dev       # Development mode
   npm run build     # Production Next.js build
   ```

### Running Tests

Execute the automated test suite:
```bash
pytest tests/test_dataset_builder.py tests/test_ml_feature_contract.py tests/test_temporal_validator.py tests/test_v2_inference.py
```

---

## Environment Variables

| Variable | Description | Context |
| :--- | :--- | :--- |
| `HELIOS_API_BASE` | Upstream base URL for backend API calls | Frontend (defaults to local or Tailscale Funnel) |
| `HELIOS_API_KEYS` | In-memory API key definitions (`id:secret`) | Backend |
| `HELIOS_ADMIN_BOOTSTRAP_SECRET` | Secret used to initialize the first admin key | Backend |

---

## Deployment

- **Frontend**: Deployed on [Vercel](https://vercel.com) connecting upstream via Next.js server route handlers.
- **Backend Ingress**: [Tailscale Funnel](https://tailscale.com/kb/1223/funnel) providing secure public HTTPS termination to the local FastAPI daemon on port `8011`.
- **Active Endpoint (Development/Staging)**: `https://cachyos-agasthya.tail1cd259.ts.net`  
  *(Note: This represents the active host endpoint; final infrastructure migration will target a dedicated Mini-PC host).*

---

## Status

HELIOS V2 development, model validation, and deployment preparation are complete:

- [x] XGBoost V2 model trained, frozen, and verified (`helios.pkl`)
- [x] Strictly held-out test evaluation completed
- [x] Native FastAPI backend operational with RBAC API-key authentication
- [x] Next.js 16 frontend interface built and verified
- [x] Tailscale Funnel public HTTPS ingress verified
- [x] Repository dependency graph audited and cleaned for release

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
