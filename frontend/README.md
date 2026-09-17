# HELIOS V1 — web interface

The public-facing interface for HELIOS: a learned arbitration layer over the GFS,
IFS and ICON numerical weather models.

> HELIOS does not learn the weather. It learns the conditional reliability of the
> weather models.

Everything scientific on screen is fetched live from the HELIOS V1 API and read
from frozen artifacts. Nothing is hard-coded, mocked, or synthesised.

---

## Running it

The V1 API must be running first (it serves the frozen model + January 2025 data).

From the repository root, the stack controller starts both processes:

```bash
./scripts/helios-stack.sh start     # API on :8011, web on :3100
./scripts/helios-stack.sh status
./scripts/helios-stack.sh stop
./scripts/helios-stack.sh restart-web   # rebuild + restart the web app
```

Then open **http://127.0.0.1:3100**

Manually, if you prefer:

```bash
# 1) API (from repo root)
export HELIOS_API_KEYS="demo:sk_local_demo_inspect_0001"
.venv/bin/python -m backend.app.api.v1_app --host 127.0.0.1 --port 8011

# 2) web (from frontend/)
npm install
npm run build && npm run start        # http://127.0.0.1:3100
```

### Configuration

`frontend/.env.local` (see `.env.example`):

```bash
HELIOS_API_BASE=http://127.0.0.1:8011
HELIOS_API_KEY=sk_local_demo_inspect_0001
HELIOS_API_TIMEOUT_MS=15000
```

These are **server-side only**. They are deliberately not `NEXT_PUBLIC_*`.

---

## Architecture

```
browser ──► /api/helios/*  (Next route handler, server-side)
                │  injects X-API-Key, enforces timeout, whitelists endpoints
                ▼
           HELIOS V1 API :8011  ──► frozen MLP + January 2025 data
```

**Why the proxy?** The V1 API is protected by `X-API-Key`. If the browser sent
that header directly the key would have to ship inside client JavaScript and be
extractable from devtools. Instead every browser request hits a same-origin route
handler that attaches the key server-side. Verified: the key appears in **zero**
client-delivered assets (HTML and all JS chunks).

### Layout

```
src/
  app/
    page.tsx                 composition of the five sections
    layout.tsx               fonts, metadata, skip-link
    globals.css              design tokens (HELIOS visual language)
    icon.svg                 app mark
    api/helios/[...path]/    server-side API proxy
  lib/
    types.ts                 typed API contracts (mirror real responses)
    client.ts                typed fetch layer + error classification
    format.ts                measurement formatting, projection, thermal ramp
    constants.ts             model identity, zones, wording guards
    random.ts                deterministic PRNG (reproducible particle field)
  hooks/useHeliosData.ts     resource hooks: abort, race-safety, typed errors
  store/useHelios.ts         user selections + demo state (zustand)
  shaders/                   GLSL as TS template strings
    chunks.ts                simplex noise, fBm, bezier, thermal ramp
    atmosphere.ts            hero atmospheric field (decorative)
    streams.ts               arbitration streams + HELIOS core (data-driven)
  components/
    gl/GLStage.tsx           hardened WebGL host (probe, boundary, context-loss)
    gl/AtmosphericField.tsx  hero backdrop
    gl/ArbitrationChamber.tsx  weight-driven particle streams
    forecast/                station field map, trust ledger, readout, selectors
    arena/                   walk-forward chart, locked test, candidates
    method/                  the HELIOS loop, two-level architecture
    demo/GuidedDemo.tsx      presenter flow for a live demonstration
    chrome/Nav.tsx           navigation + system status
    ui/primitives.tsx        panels, animated values, error/empty states
```

### Live vs historical (the primary distinction)

The interface leads with the **live** product and keeps historical validation as a
clearly-labelled evidence layer:

| Section | Data |
| --- | --- |
| `01 · LIVE FORECAST` | current GFS/IFS/ICON cycle → frozen MLP → future horizons |
| `02 · MODEL ARENA` | historical candidate competition (January 2025) |
| `03 · LOCKED TEST` | frozen evaluation verdict |
| `04 · VALIDATION REPLAY` | explicit January 2025 replay explorer |
| `05 · METHOD`, `06 · STATUS` | methodology and scope |

An `EvidenceBanner` marks where the historical layer begins. If live acquisition
fails, `LiveUnavailable` states why and offers the evidence layer as a separate
destination — historical data is **never** shown in the live slot.

Elapsed horizons (a 00Z run's +6h once 06Z has passed) are flagged `elapsed` and
the default selection is the first horizon still in the future.

### Spatial model (coordinate-first)

A location is a **real coordinate pair** with a station anchor and a place name —
never an evaluation zone.

| Concept | Representation |
| --- | --- |
| Forecast point | real station lat/lon (NOAA ISD station history) + `station` id |
| Place name | presentation metadata, e.g. "Srinagar" |
| Evaluation zone | statistical stratification only; a secondary filter + metadata |
| Model sampling | each NWP model's **nearest grid point** to the station, with offset in km |

V1 is **station-anchored**. Clicking empty map space does not invent a hyperlocal
forecast: `GET /v1/resolve` returns the nearest supported point and the UI states
the distance, graded against the dataset's 50 km verification radius
(≤ 25 km representative · 25–100 km caution · > 100 km outside supported coverage).
`SpatialProvenance` shows the per-model grid points and `interpolated: false`.

Stations without published ISD coordinates are **omitted** from the map rather
than plotted at a guessed position.

### The core visualisation

In `ArbitrationChamber`, every visual property of a stream is driven by real API
data — this is the point of the piece, not decoration:

| Visual                              | Source                       |
| ----------------------------------- | ---------------------------- |
| stream density / width / brightness | `nwp_weights[model]`         |
| stream colour                       | model identity + `nwp_forecasts_c` |
| stream present at all               | `nwp_availability[model]`    |
| core brightness                     | how concentrated the weights are |

An **unavailable** model emits nothing at all — mirroring the backend contract
that missing ≠ zero.

### Wording discipline

The weights are **blending weights (trust)**. They are never labelled as
probability, accuracy, or confidence anywhere in the UI. See `TRUST_DISCLAIMER`
in `lib/constants.ts`.

V1 serves **2 m temperature only**. Humidity, wind, precipitation, feels-like and
solar radiation are not validated, are not served, and where mentioned are
explicitly tagged `V2`.

---

## Quality gates

```bash
npm run typecheck    # tsc --noEmit (strict, noUncheckedIndexedAccess)
npm run lint         # eslint flat config (next core-web-vitals + typescript)
npm run build        # production build
```

### Resilience verified

| Condition          | Behaviour                                                    |
| ------------------ | ------------------------------------------------------------ |
| API offline        | "API DOWN" indicator, honest error panels, no fabricated data |
| Invalid API key    | 401 surfaced with actionable remediation copy                 |
| Request timeout    | 504 classified separately from offline                        |
| No WebGL           | SVG fallback renders the same real weights                    |
| WebGL context lost | caught, falls back without blanking the page                  |
| Reduced motion     | decorative motion disabled, all data still rendered           |
| Stale responses    | superseded requests discarded (monotonic request id)          |

---

## Known limitation — dev mode on Node 26

`npm run dev` does **not** hydrate in this environment. The Turbopack dev runtime
stalls because the HMR WebSocket handshake is rejected by the browser
(`net::ERR_INVALID_HTTP_RESPONSE`); all JS chunks download with 200 but the app
never bootstraps, so no API calls are made.

Root cause is an environment mismatch: this machine runs **Node v26.8.1**, while
Next.js 16 targets Node 20/22 LTS. The handshake succeeds over `curl` but Chrome
rejects the server's 101 response. It reproduces with both Turbopack and webpack,
and is unrelated to application code.

**Production is unaffected** — `npm run build && npm run start` has no HMR
transport and works correctly. Use that (the stack script does). If you need HMR,
run the frontend under Node 20 or 22 LTS.
