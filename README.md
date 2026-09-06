# HELIOS

**Weather-Model Blending and Post-Processing Platform**

HELIOS is a professional weather intelligence system that combines multiple Numerical Weather Prediction (NWP) models with historical performance data, reanalysis datasets, and observational weather data to produce more accurate and calibrated forecasts.

## Purpose

HELIOS is NOT an independent NWP model. It is an **ensemble blending and post-processing system** designed to improve forecast accuracy by intelligently combining predictions from multiple trusted NWP sources.

### Target Users

- Agriculture and farming operations
- Aviation and aerial operations
- Logistics and transportation
- Energy sector (solar, wind, grid management)
- Disaster management and emergency response
- Weather-sensitive professional organizations

This is NOT primarily a consumer weather app. The consumer interface is one presentation layer.

## Core Concept

```
Multiple NWP Models → HELIOS ML Blending → Calibrated Forecast
       ↓                    ↓                      ↓
   GFS, ECMWF,        Kernel Regression      Professional
   ICON, UKMO,         XGBoost, MLP         Weather Intelligence
      GEM
```

HELIOS receives forecasts from multiple reputable NWP models and uses machine learning to:

1. **Learn historical model performance** - Track which models perform best under specific conditions
2. **Blend predictions intelligently** - Weight models based on past skill and current uncertainty
3. **Calibrate forecasts** - Correct systematic biases using historical verification data
4. **Quantify confidence** - Provide uncertainty estimates and model agreement metrics

## Architecture Overview

### Data Sources

**NWP Models (Initial Target)**:
- GFS (NOAA Global Forecast System)
- ECMWF IFS (European Centre for Medium-Range Weather Forecasts)
- ICON (German Weather Service)
- UK Met Office Global Model
- GEM (Canadian Meteorological Centre)

**Reference & Auxiliary Data**:
- ERA5 (ECMWF Reanalysis v5) - historical weather conditions
- NASA POWER - satellite-derived meteorological data
- Observational weather data - station observations and weather APIs

### ML Competitors

HELIOS evaluates three machine learning approaches:

1. **Kernel Regression** - Similarity-based weighting of historical situations
2. **XGBoost** - Gradient boosting for tabular weather features
3. **MLP** (Multi-Layer Perceptron) - Neural network approach

**Baselines** for comparison:
- Individual NWP model forecasts
- Simple ensemble mean
- Persistence and climatology where appropriate

### Technology Stack

**Backend**:
- Python 3.10+
- FastAPI (API server)
- PyTorch (neural networks)
- XGBoost (gradient boosting)
- scikit-learn (kernel regression, preprocessing)
- PostgreSQL (structured application data)
- SQLAlchemy (ORM)

**Data Processing**:
- xarray (multi-dimensional arrays)
- NetCDF / GRIB (scientific weather data formats)
- Zarr (chunked array storage)
- Parquet (processed ML datasets)

**Frontend** (Future):
- Next.js
- TypeScript
- React
- Tailwind CSS
- Vercel deployment

**Infrastructure**:
- Docker Compose (local development)
- NVIDIA RTX 5080 (training and inference)
- PostgreSQL database

## Folder Structure

```
HELIOS/
├── backend/          # FastAPI application
├── ai/               # ML models and training
├── nwp/              # NWP data ingestion adapters
├── data/             # Raw and processed datasets
├── database/         # Schema and migrations
├── models/           # Model checkpoints
├── evaluation/       # Verification and metrics
├── scripts/          # Data and training scripts
├── config/           # Configuration files
├── infrastructure/   # Docker and deployment
├── logs/             # Application logs
├── docs/             # Documentation
└── frontend/         # Next.js application (future)
```

## Storage Strategy

**Storage Constraint**: ~220 GB allocated to HELIOS

HELIOS is designed for **storage-aware operation**:

1. Download historical data
2. Preprocess and train
3. Save checkpoint
4. **Delete raw training data**
5. Repeat with larger datasets

Only trained models and essential metadata remain permanently.

## Forecast Verification

**Critical Principle**: Never allow future observations to leak into forecasts.

HELIOS tracks:
- Forecast issue time
- Forecast valid time
- Lead time
- Model name
- Forecast value
- **Later observed value** (after valid time)
- Error metrics (MAE, RMSE, bias)

This allows HELIOS to learn historical model performance and continuously improve.

## Model Versioning

Each trained HELIOS version is independently identifiable:

```
helios-0.1 → helios-0.2 → helios-0.3
```

Each checkpoint contains:
- Model files
- Feature configuration
- Preprocessing parameters
- Hyperparameters
- Training period
- Data source versions
- Evaluation metrics
- Git commit reference

## Continuous Improvement Loop

```
NWP Forecast
     ↓
HELIOS Prediction
     ↓
Actual Observation (later)
     ↓
Calculate Errors
     ↓
Store Verification
     ↓
Training Dataset Grows
     ↓
Periodic Retraining
     ↓
Evaluate New Checkpoint
     ↓
Promote Only If Better
```

## Home AI Server Architecture (Future)

```
Internet User
     ↓
Vercel Frontend (Next.js)
     ↓
Secure Authenticated API
     ↓
Home PC (RTX 5080)
     ↓
FastAPI Backend
     ↓
HELIOS Inference Engine
     ↓
Forecast Result
```

**Note**: Do NOT expose home PC through unsafe port forwarding. Secure tunnel solution to be evaluated later.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 16
- NVIDIA GPU with CUDA support (recommended)
- ~220 GB available storage

### Installation

```bash
# Clone repository
cd /home/agasthya/HELIOS

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys and configuration

# Initialize database
alembic upgrade head
```

### Development

```bash
# Start services
docker-compose up -d

# Run backend
cd backend
uvicorn app.main:app --reload

# Run tests
pytest
```

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **Architecture**: System design and data flow
- **Data**: Data sources, formats, and storage strategy
- **ML**: Model architectures and training procedures
- **API**: Backend API reference
- **Operations**: Deployment and maintenance

## Project Status

**Current Phase**: Scaffold and Foundation

- [x] Project structure created
- [x] Initial documentation
- [ ] NWP data adapters
- [ ] Database schema implementation
- [ ] Baseline ML models
- [ ] Forecast verification system
- [ ] Frontend application
- [ ] Production deployment

## Important Notes

### DO NOT:
- Download large datasets without explicit instruction
- Train models automatically
- Expose home PC through unsafe networking
- Make unsupported accuracy claims without validation
- Modify the separate Aether project (if present)

### Storage Budget:
- Maximum HELIOS working storage: ~220 GB
- Historical data is temporary (delete after training)
- Only checkpoints and metadata persist

## License

MIT License - See LICENSE file for details

## Contact

HELIOS Team - team@helios.example.com

---

**Built with a focus on scientific rigor, storage efficiency, and professional weather intelligence.**
