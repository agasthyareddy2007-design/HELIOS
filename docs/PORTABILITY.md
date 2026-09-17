# HELIOS V1 — Portability Guide

How to move the entire `/home/agasthya/HELIOS` folder to an SSD and run it on
another Linux machine (target: **CachyOS**, ~4 GB RAM, NVIDIA 4 GB VRAM) with as
few reinstalled dependencies as practical.

This document describes the **V1 runtime only** (serving the site + live blended
forecasts). It does not cover retraining or evaluation.

---

## Target environment

- OS: CachyOS (Arch-based, rolling), Linux desktop
- Arch: **x86_64** (required — see native binaries below)
- libc: **glibc** (CachyOS uses glibc; the bundled native extensions are glibc builds)
- RAM: ~4 GB; GPU: NVIDIA 4 GB VRAM (not required for V1 serving — see GPU note)

Build machine this was audited on: glibc 2.44, Python 3.14.7, Node v26.8.1,
wgrib2 3.8.0, x86_64.

---

## Exact commands after copying

From inside the copied `HELIOS` folder (scripts resolve their own location, so
they work from any path / any cwd):

```
# start (production stack, detached): API :8011 + website :3100, opens browser
./start_helios.sh

# stop (graceful; frees ports 8011 and 3100)
./stop_helios.sh
```

- Website: http://127.0.0.1:3100/
- API health: http://127.0.0.1:8011/v1/health
- Frontend runs **production** mode (`next build` once if `.next` is absent, then
  `next start -p 3100`). No dev/HMR.
- API key: `start_helios.sh` sets a local default `HELIOS_API_KEYS` if you have
  not exported one. Export your own before starting if desired.

---

## What is bundled inside HELIOS (copies with the folder)

- **Application code** (backend + frontend source).
- **SQLite database** `data/helios.db` (~2.44 GB) — this IS the V1 database,
  opened **read-only** (`mode=ro`). No database server needed at runtime.
  Rows: forecasts 2,731,930 / verification 1,592,635.
- **Python packages** in `.venv/` (~5.9 GB, incl. torch ~1.2 GB, numpy, pandas,
  scikit-learn, scipy, xgboost, xarray, **cfgrib + eccodes/eccodeslib** so GRIB
  decoding is self-contained). 335 native `*.cpython-314-x86_64-linux-gnu.so`.
- **Node modules** `frontend/node_modules/` (~545 MB) incl. native linux-x64-gnu
  addons (Next SWC, tailwind-oxide, sharp).
- **Prebuilt frontend** `frontend/.next/` (~475 MB) — no rebuild needed if Node
  is present and compatible.
- **Frozen ML/eval artifacts** under `ml/artifacts/` and the geo map assets.

Total folder size ~12 GB.

---

## What must remain OS-level on the laptop (install these)

1. **Python 3.14 at `/usr/bin/python3`** — REQUIRED for `.venv` reuse. The venv
   does **not** bundle an interpreter; `.venv/bin/python` symlinks to the system
   `python3`, and all 335 native extensions are compiled for the CPython **3.14**
   ABI (`cpython-314`). If the target `/usr/bin/python3` is a different minor
   (e.g. 3.13), the venv will not import and must be rebuilt with
   `python3.14 -m venv` + `pip install` of the pinned versions.
2. **Node.js (compatible with the pinned Next.js) + npm** — OS-level; not vendored
   inside HELIOS. Audited on Node v26.x. Native `.node` addons are linux-x64-gnu.
3. **wgrib2** — REQUIRED for LIVE forecasts. The live NWP path shells out to
   `wgrib2` to crop GFS GRIB2 to India (`live_nwp_service.py`). Without it live
   GFS acquisition fails. (eccodes/cfgrib for other models are in the venv.)
4. **curl** — the live path uses `curl` for byte-range GRIB fetches.
5. **A web browser** — for `xdg-open` to open the site (optional; you can visit
   the URL manually). `xdg-open` is desktop-standard.
6. **glibc + x86_64** — the bundled native code assumes these. CachyOS satisfies
   both. glibc must be >= what the binaries need (torch GLIBC_2.2.5, Next SWC
   GLIBC_2.30) — any modern rolling glibc is newer, so this is fine.

---

## Dependency classification

Legend: **A** = safely bundled · **B** = vendored but with a runtime caveat ·
**C** = must remain OS-level · **D** = not required for V1 runtime.

| Dependency | Class | Notes |
|---|---|---|
| Application code | A | Copies with the folder. |
| SQLite DB `data/helios.db` | A | Single file, read-only at runtime; no DB server. |
| Python packages (`.venv`) | B | Bundled, but require system `/usr/bin/python3` == Python 3.14, x86_64, glibc. |
| Python interpreter | C | NOT bundled; must be OS-level Python 3.14. |
| torch (1.2 GB) | A/B | Bundled in venv; lazily imported; needs the same Py 3.14 ABI. |
| cfgrib + eccodes/eccodeslib | A | GRIB decode self-contained in the venv. |
| Node modules (`node_modules`) | B | Bundled, but native addons need linux-x64-gnu + compatible Node. |
| Prebuilt `.next` | A | Bundled; rebuildable with `npm run build` if missing/incompatible. |
| Node.js + npm | C | Must be OS-level; not vendored. |
| wgrib2 | C | Must be OS-level; required for live GFS. |
| curl | C | Must be OS-level; used by live acquisition. |
| Browser / xdg-open | C | OS-level; only to auto-open the site (optional). |
| NVIDIA GPU / CUDA | D | Not required for V1 serving (see GPU note). |
| PostgreSQL | D | NOT used by V1 runtime — `docker-compose.yml`, `.env.example`, and |
| | | `database/connection.py` PostgreSQL support are unused scaffolding. |
| Docker | D | Not required for V1 runtime. |

---

## Can the current `.venv` / `node_modules` be reused?

- **`.venv`: YES, if** the laptop's `/usr/bin/python3` is **Python 3.14 (x86_64,
  glibc)**. The app launches via `.venv/bin/python -m ...` (never sources
  `activate`) and the venv's internal symlinks are relative, so it runs from any
  copied path. Caveat: `.venv/bin/activate` and the `pip`/console-script shebangs
  still contain the original absolute path `/home/agasthya/HELIOS/.venv`; these
  matter only if you `source activate` or run `pip` from the copy — the runtime
  does not. If the target Python minor differs, rebuild the venv with the pinned
  versions (do not upgrade packages — preserve exact versions).
- **`node_modules`: YES, if** the laptop is linux-x64-gnu with a compatible Node.
  The native addons (SWC, oxide, sharp) are linux-x64-gnu builds. If Node is
  incompatible, run `npm ci` (same lockfile → same versions) then `npm run build`.

Do not delete `node_modules` or `.venv` to save space — they are the whole point
of the "copy and run" strategy.

---

## ~4 GB RAM assessment

- The V1 **serving** path is FastAPI + SQLite (read-only) + a bounded live
  acquisition fan-out. Reasonable for ~4 GB.
- **torch** is imported lazily (only when the MLP candidate is needed for a blend)
  and is the single largest memory contributor. It is required for scientific
  correctness of the blend and is **not** removed.
- Live acquisition concurrency is capped by `HELIOS_LIVE_MAX_CONCURRENCY`
  (default **2**) via a `BoundedSemaphore` — this rapid-selection protection is
  **kept intact** and also bounds peak memory. You may lower it to `1` on a
  constrained laptop (env var only, no code change) but do not remove it.
- The frontend serves the prebuilt production bundle (`next start`), far lighter
  than dev/HMR. No training/evaluation runs at serve time.

### GPU note
V1 serving does not require the NVIDIA GPU. The frontend's atmospheric background
uses WebGL where available with a CSS fallback (handled by the browser); torch
runs on CPU for the small MLP candidate. A 4 GB VRAM GPU is sufficient but unused
for serving.

---

## Known limitations

- **Python 3.14 dependency** is the hardest reuse constraint (above).
- **Node is OS-level** and was audited on a very new major (v26). Ensure the
  target Node runs the pinned Next.js; otherwise `npm ci` + `npm run build`.
- **wgrib2 + curl** must exist for LIVE forecasts; DB-backed historical responses
  do not need them, but the live pipeline does.
- This audit ran on the build machine; the actual CachyOS laptop was not
  available, so cross-machine reuse of the compiled `.venv`/`node_modules` is
  reasoned from ABI/arch/glibc analysis, not observed on CachyOS. If the target
  Python minor or Node major differs, use the documented rebuild fallback.

---

## How to verify the copied project on the laptop

1. `./start_helios.sh` — wait for "HELIOS is running".
2. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8011/v1/health` → `200`.
3. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3100/` → `200`.
4. Open http://127.0.0.1:3100/ and confirm the map + a live forecast selection
   works (live requires wgrib2 + curl + network).
5. DevTools / view-source: confirm no API key string appears in the DOM.
6. `./stop_helios.sh` — confirm it reports ports 8011 and 3100 free.
7. Optional integrity: `.venv/bin/python run_api_v1_tests.py` (expect 23/23) and
   `.venv/bin/python run_live_pipeline_tests.py` (expect 9/9, needs network).
