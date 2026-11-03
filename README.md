<div align="center">

# 🌊 SuddWatch

### Operational Flood Detection & Humanitarian Alert System for South Sudan

**SWE3090: Software Project 1 · Summer Semester, 2026**  
**United States International University – Africa · School of Science and Technology**

---

*Student:* **Madut Chan** · *ID:* **671336**  
*Supervisor:* **Prof. Paul Okanda**

---

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.58-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Sentinel-1](https://img.shields.io/badge/ESA-Sentinel--1%20SAR-003247?style=flat-square)](https://dataspace.copernicus.eu)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Tests](https://img.shields.io/badge/tests-242%20passing-2ea44f?style=flat-square)](#9-testing--evaluation)

</div>

---

## Abstract

South Sudan is experiencing a deepening humanitarian crisis as annual floods displace hundreds of thousands of people across Jonglei, Unity, and Upper Nile states. The core problem is not a lack of satellite data but the failure to convert that data into actionable alerts that reach vulnerable communities before floodwaters arrive. Current flood assessments reach humanitarian responders three to seven days after a flood occurs, and more than half of displaced households receive no warning at all.

**SuddWatch** is a prototype that closes this gap. It automatically downloads free ESA Sentinel-1 C-band radar (SAR) imagery, detects flood extent with a six-stage classifier, estimates who and what is affected using WorldPop 2020 population data and OpenStreetMap villages, roads and health facilities, and sends SMS alerts to village chiefs and HTML situation reports to coordinators. The design target is **≤ 60 minutes from satellite pass to alert**; the system records the actual end-to-end latency of every run so this can be checked.

> **Status (November 2026).** The full pipeline runs end-to-end and is covered by 242 automated tests, including an end-to-end test that runs the real pipeline on synthetic data. A run on a real Sentinel-1 scene and validation against a hand-labelled reference mask are the next steps — see [§9](#9-testing--evaluation) and [§12](#12-limitations--future-work). A list of the fixes made in the November 2026 review is in [`CHANGES.md`](CHANGES.md).

---

## Table of Contents

1. [Project Background](#1-project-background)
2. [Problem Statement](#2-problem-statement)
3. [Project Objectives](#3-project-objectives)
4. [System Architecture](#4-system-architecture)
5. [Technical Implementation](#5-technical-implementation)
6. [Dashboard](#6-dashboard)
7. [Installation & Setup](#7-installation--setup)
8. [Running the System](#8-running-the-system)
9. [Testing & Evaluation](#9-testing--evaluation)
10. [Repository Structure](#10-repository-structure)
11. [Key Design Decisions](#11-key-design-decisions)
12. [Limitations & Future Work](#12-limitations--future-work)
13. [Data Sources](#13-data-sources)
14. [Acknowledgements](#14-acknowledgements)

---

## 1. Project Background

Greater Upper Nile — comprising Jonglei, Unity, and Upper Nile states — sits at the heart of the Sudd, one of Africa's largest wetlands (30,000–40,000 km² in the dry season, expanding to over 80,000 km² at peak flood). The White Nile floodplains have gradients less than 0.1%, meaning floodwaters spread laterally for hundreds of kilometres when river banks are overtopped.

Since 2019, rainfall totals have broken century-long records every year. The 2022 flood season was the worst in recorded history: 4.7 million hectares were inundated at peak, displacing over 918,000 people across four simultaneously flooded states. Major settlements most severely affected include:

- **Bor** — capital of Jonglei State, repeatedly flooded, road access cut for weeks
- **Bentiu** — capital of Unity State, home to 100,000+ IDPs, proximity to the Sudd makes it especially vulnerable
- **Malakal** — capital of Upper Nile State, located at the White Nile–Sobat River confluence where backwater flooding causes prolonged inundation

A comparative review of seven existing flood monitoring systems identified three persistent gaps:

| Gap | Current System Behaviour | Humanitarian Consequence |
|---|---|---|
| **Latency** | 3–7 days from flood onset to assessment | Evacuation windows missed; roads impassable before warnings arrive |
| **Last-mile delivery** | Outputs distributed as PDF maps via email and ReliefWeb | 52% of displaced households receive no advance warning |
| **Cloud cover** | Optical satellites blind during 90%+ cloud cover May–November | Flooding goes undetected for weeks during peak rainy season |

---

## 2. Problem Statement

SAR-based flood detection at village-level resolution over South Sudan is demonstrated and achievable. The problem is that existing systems produce static PDF products through internet-dependent channels, rely on manual processing workflows adding 3–7 days of preventable latency, and have no integration between detection outputs and alert dispatch. SuddWatch treats the entire chain — from Sentinel-1 overpass to SMS delivery — as a single automated pipeline, with end-to-end latency as the primary design constraint.

---

## 3. Project Objectives

### Objective 1 — Literature Review & Requirements Analysis

Conduct a literature review and requirements analysis of existing systems to identify technical and operational gaps in flood early warning for Greater Upper Nile.

**Delivered:**
- Seven systems reviewed: Copernicus EMS, DFO, GFM, IGAD, South Africa NFWS, OCHA, REACH
- Three operational gaps identified and mapped to design requirements
- Three techniques from recent SAR literature adopted: a GMM-based second threshold, TPI terrain filtering, and exclusion masking
- Quantified requirements: latency ≤ 60 min, IoU ≥ 0.65, alert delivery > 95%

### Objective 2 — Prototype System Development

Design and develop a prototype flood detection system addressing latency, last-mile alert delivery, and accessibility in infrastructure-poor environments.

**Delivered:**

| Module | Purpose |
|---|---|
| `src/config.py` | All settings: `.env` credentials, paths, thresholds, dashboard overrides |
| `src/data_acquisition.py` | Copernicus Data Space OData API — scene search, download, registry |
| `src/preprocessing.py` | ESA SNAP GPT chain (orbit → thermal noise → calibration → speckle → terrain correction) + dB conversion |
| `src/flood_detection.py` | 6-stage flood classifier |
| `src/raster_utils.py` | Puts DEM / masks / population onto the scene's pixel grid; true pixel areas |
| `src/risk_assessment.py` | Population, villages, roads and health facilities in or near flood water |
| `src/alerts.py` | Twilio SMS + Gmail SMTP dispatch, dry-run mode |
| `src/database.py` | SQLite, 6 tables, automatic schema migration |
| `src/pipeline.py` | Orchestrator: per-stage timing, latency, error handling |
| `src/ml_flood_detection.py` | Experimental Random Forest detector (optional) |
| `dashboard/app.py` | Streamlit dashboard with User and Admin roles |
| `dashboard/db.py` | Dashboard data layer — real pipeline data, or demo data until the first run |
| `dashboard/auth.py` | Accounts and access requests (salted PBKDF2 passwords) |
| `dashboard/admin_actions.py` | What the Admin buttons actually do |
| `dashboard/exporter.py` | Real GeoJSON / GeoTIFF / Shapefile / CSV exports |

### Objective 3 — Testing & Evaluation

Test and evaluate the prototype against the identified issues.

**Delivered:**
- 242 automated tests (plus 5 optional live-service tests) — see [§9](#9-testing--evaluation)
- Every run records per-stage timings, processing time and end-to-end latency (satellite sensing time → alerts sent)
- IoU is computed automatically whenever a reference mask exists for a scene
- Performance page and audit log built from the recorded data

---

## 4. System Architecture

```
╔══════════════════════════════════════════════════════════════════╗
║                       AUTOMATED PIPELINE                         ║
║     run_pipeline.py — every 12 h via cron / launchd / systemd    ║
╚══════════════════════════════════════════════════════════════════╝

  Copernicus Data Space (ESA)
          │  OData API — IW GRD, VV+VH, 5°–12°N, 29°–35°E, last 7 days
          ↓
  ┌─────────────────────────┐
  │   data_acquisition.py   │  download .zip · registry · sensing time
  └───────────┬─────────────┘
              │  data/raw/*.zip
              ↓
  ┌─────────────────────────┐
  │    preprocessing.py     │  SNAP GPT (5 operators) → σ⁰ VH → dB
  └───────────┬─────────────┘
              │  data/processed/*_preprocessed_db.tif
              ↓
  ┌─────────────────────────┐
  │   flood_detection.py    │  6 stages · DEM / baseline / masks aligned
  └───────────┬─────────────┘    to the scene grid (raster_utils.py)
              │  data/flood_masks/*_flood_mask.tif
              ↓
  ┌─────────────────────────┐
  │   risk_assessment.py    │  WorldPop · OSM villages / roads / clinics
  └───────────┬─────────────┘
              │  *_risk_summary.json
      ┌───────┴────────┐
      ↓                ↓
  ┌──────────┐   ┌────────────┐
  │ alerts   │──▶│ database   │  every alert, stage time and result
  │ SMS/Email│   │ SQLite     │  is written here
  └──────────┘   └─────┬──────┘
                       ↓
              ┌────────────────┐        ┌───────────────────────┐
              │ dashboard/db.py│◀──────▶│ dashboard/app.py      │
              │ real ↔ demo    │        │ Admin → Pipeline can  │
              └────────────────┘        │ start run_pipeline.py │
                                        └───────────────────────┘
```

---

## 5. Technical Implementation

### 5.1 SAR preprocessing (ESA SNAP GPT)

`preprocessing.py` writes a SNAP graph and runs it with `gpt`:

```
Read
1. Apply-Orbit-File          precise orbit (auto-download)
2. ThermalNoiseRemoval       removes the IW GRD noise floor (matters most over dark water)
3. Calibration               σ⁰ (sigma-nought), VH polarisation only
4. Speckle-Filter            Lee, 5 × 5
5. Terrain-Correction        Range-Doppler, SRTM 3Sec DEM, 10 m, WGS84
Write  → linear σ⁰ GeoTIFF
then, in Python:  dB = 10 · log10(σ⁰)   (values ≤ 0 → no data)
```

Typical SNAP run time is 8–15 minutes per scene. A scene that is already a preprocessed `.tif` skips this step.

### 5.2 Flood detection (6 stages)

Open water reflects the radar pulse away from the satellite, so it shows up **dark** (low dB).

```
Stage 1  Otsu threshold        best split of the dB histogram into water / land
Stage 2  GMM threshold         mean + 1 σ of the "water" component of a 2-component
                               Gaussian Mixture Model
         Final threshold = min(Otsu, GMM) × relaxation factor
         (the lower value is the stricter one; factor < 1 detects more water)
         Both are estimated from a random sample of 1 million pixels.
Stage 3  Change detection      keep only pixels that became > 2 dB darker than the
                               dry-season baseline (removes permanent water).
                               Runs only if a baseline image is configured.
Stage 4  TPI filter            TPI = elevation − mean elevation of the ring between a
                               1 km and a 5 km window. Pixels > 0.5 m above their
                               surroundings are treated as dry high ground.
Stage 5  Exclusion masks       any GeoTIFF in data/exclusion_masks/ (e.g. JRC permanent
                               water, urban areas) — flagged pixels are removed
Stage 6  Morphological clean   3×3 elliptical closing then opening
```

Every auxiliary raster (DEM, baseline, exclusion masks) is **reprojected onto the scene's own pixel grid** before it is compared with the scene, so pixels match by location. Flood area is computed from the true ground area of each pixel row (pixels get narrower away from the equator).

Output: `data/flood_masks/<scene>_flood_mask.tif` — `1` flood, `0` dry, `255` no data.

### 5.3 Risk assessment

| Output | How it is computed |
|---|---|
| Affected population | For each WorldPop 1 km cell: people × fraction of the cell that is flooded, summed |
| Affected villages | OSM settlement points. **Flooded** (on a flood pixel) → 90 % risk, "Evacuate / relocate". **Near** (flood within 1 km, configurable) → 50 % risk, "Monitor & prepare". Others are not listed. Population shown = people in the village's WorldPop 1 km cell. |
| Inaccessible roads | OSM road lines sampled about once per mask pixel; a road is listed if any sample is flooded. Flooded length = road length × share of flooded samples. |
| Health facilities | OSM points; **flooded** or **at risk** (within the buffer). Type from the OSM `healthcare` / `amenity` tag. |
| State per village | From an optional state-boundary file (`data/admin/south_sudan_states.geojson`); otherwise "Unknown". |

Results are saved as `<mask>_risk_summary.json` and written to the database.

### 5.4 Alerts

An alert is sent when **flood extent ≥ 500 ha OR affected population ≥ 1,000** (both adjustable in `.env` or Admin → Alert Config).

**SMS (Twilio)** — short enough for any GSM handset, e.g.:
```
[SUDDWATCH CRITICAL] EVT-2026-016
Flood: 13,971 ha | Pop at risk: 3,532
Top area: Bor
Roads cut: 3 | Clinics: 1
2026-11-03 16:55 UTC
```
A dashboard link is added only if `DASHBOARD_URL` is set. Severity is CRITICAL when two or more villages are inside flood water.

**Email (Gmail SMTP)** — HTML + plain-text situation report with village, road and health-facility tables.

Every message is recorded in the `alerts` table with status `sent` (accepted by Twilio/SMTP), `failed`, or `skipped` (dry run).

### 5.5 Database (`data/database/suddwatch.db`)

```
events                  one row per scene processed: label (EVT-YYYY-NNN), scene, satellite
                        sensing time, processing start/end, processing_seconds,
                        total_latency_seconds, affected_population, status, error
flood_masks             flood_extent_ha, iou_score (NULL = not validated), GeoTIFF path, method
affected_populations    one row per village (risk %, level, action, population, lat/lon)
infrastructure_impacts  roads (length, flooded length) and health facilities (status, location)
alerts                  one row per recipient per channel
processing_logs         one row per stage per event (start, end, duration, status)
```
New columns are added automatically to older databases on start-up.

**Latency definitions.** *Processing time* = the pipeline's own stages. *End-to-end latency* = satellite sensing time (from the product metadata or file name) → alerts finished; this is the number the 60-minute target refers to and is what `total_latency_seconds` stores when the sensing time is known.

---

## 6. Dashboard

`dashboard/app.py` (Streamlit) has two roles. Users (humanitarian coordinators, analysts) see situational awareness pages; Admins see operations pages.

**Real vs demo data.** `dashboard/db.py` uses the pipeline database as soon as it contains a completed event with a flood mask. Until then it shows example data and a yellow **DEMO DATA** banner at the top of every page.

### Accounts

Accounts are stored in `dashboard/auth.db` with salted PBKDF2 password hashes. On a fresh install three demonstration accounts are created:

| Email | Password | Role |
|---|---|---|
| `admin@suddwatch.org` | `admin123` | Admin |
| `coord@ocha.org` | `ocha2025` | User |
| `analyst@reach.org` | `reach2025` | User |

> Change or remove these before any real deployment. New people use **Request Access**; an Admin approves or rejects them under **User Management**.

### User pages

| Page | Content |
|---|---|
| **Home** | Latest event banner, KPI cards, interactive map (includes the detected flood extent), affected villages / roads / health facilities, alert counts, pipeline status, state breakdown, monthly trend |
| **History** | Event archive with filters; events without a reference mask show IoU as "not validated" |
| **Export** | GeoJSON (flood polygons + villages + clinics), GeoTIFF (flood mask), Shapefile ZIP, CSV (villages), text situation report |
| **Intelligence** | Village / road / facility tables, data sources, live ReliefWeb news feed |

### Admin pages

| Page | What it does |
|---|---|
| **History** | Full history with charts |
| **Performance** | Latency, SLA compliance, IoU (validated events only), alert acceptance rate, per-stage timings — all computed from the database |
| **User Management** | Accounts and pending requests from `auth.db`; Approve/Reject take effect immediately |
| **Alert Config** | Edit SMS/email recipients (saved to `.env`), alert thresholds (saved to `config/runtime_settings.json`), send a real **test** SMS + email |
| **Pipeline** | Stage readiness and history from the database; **Run pipeline now** starts `run_pipeline.py` in the background (optionally for one scene file and/or without sending alerts) and shows its log; calibration sliders saved for the next run |
| **Audit Log** | Pipeline runs, alert records and dashboard actions (logins, config changes, approvals); CSV export |
| **System Health** | Which credentials and data files are configured, real folder sizes, a live Twilio/SMTP login test, cache reset |

---

## 7. Installation & Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Project is pinned to 3.12; the test suite was last run on Python 3.13 |
| ESA SNAP 9.0+ | Needed only for raw `.zip` scenes. Default `gpt` path `/Applications/esa-snap/bin/gpt`; set `SNAP_GPT_PATH` otherwise |
| Copernicus Data Space account | Free at https://dataspace.copernicus.eu |
| Twilio account | SMS-capable number |
| Gmail App Password | Enable 2FA, then create an App Password |

### Setup

```bash
git clone https://github.com/Billawan12/suddwatch.git
cd suddwatch
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in your values
python3 src/config.py         # prints the configuration and any missing items
```

### Static data (not in git)

| File | Source |
|---|---|
| `data/dem/south_sudan_dem.tif` | Copernicus DEM 30 m (used for TPI) |
| `data/worldpop/south_sudan_pop_2020_1km.tif` | WorldPop 2020, 1 km |
| `data/osm/villages.geojson`, `roads.geojson`, `health_facilities.geojson` | OpenStreetMap extract |
| *(optional)* `data/processed/baseline_dry_season_db.tif` | A dry-season (Dec–Feb) scene processed by SuddWatch — enables change detection |
| *(optional)* `data/exclusion_masks/*.tif` | e.g. JRC Global Surface Water permanent water |
| *(optional)* `data/admin/south_sudan_states.geojson` | State boundaries (OCHA COD-AB admin1) — labels villages by state |
| *(optional)* `data/reference_masks/<scene_id>_reference.tif` | Hand-labelled flood mask for a scene — enables IoU |

### Environment variables (`.env`)

Required: `COPERNICUS_USER`, `COPERNICUS_PASSWORD`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `SMTP_USER`, `SMTP_PASSWORD`, `SMS_RECIPIENTS`, `EMAIL_RECIPIENTS`.

Optional (defaults in brackets): `ALERT_FLOOD_THRESHOLD_HA` [500], `ALERT_POPULATION_THRESHOLD` [1000], `DASHBOARD_URL` [none], `SNAP_GPT_PATH`, `DRY_SEASON_BASELINE_PATH`, `NEAR_FLOOD_BUFFER_M` [1000], `SCENE_SEARCH_DAYS` [7], `DETECTION_METHOD` [threshold], `BOUNDING_BOX_*` [5–12 °N, 29–35 °E]. See `.env.example`.

### If you used an earlier version

Earlier versions of the test suite wrote fake events into the real database and fake entries into the scene registry. Remove them once (a backup is made first):

```bash
python scripts/clean_test_data.py           # shows what will be removed
python scripts/clean_test_data.py --apply
```

---

## 8. Running the System

### Dashboard

```bash
source venv/bin/activate
streamlit run dashboard/app.py          # http://localhost:8501
```

### Pipeline

```bash
python run_pipeline.py                  # check Copernicus and process new scenes
python run_pipeline.py --dry-run        # start-up + Twilio/SMTP login test only
python run_pipeline.py --scene data/raw/S1A_IW_GRDH_....zip           # one local raw scene
python run_pipeline.py --scene data/processed/x_preprocessed_db.tif  # skip SNAP
python run_pipeline.py --scene FILE --no-alerts    # full run, messages logged but not sent
python run_pipeline.py --verbose        # DEBUG logging
```

Each run writes `logs/pipeline_YYYYMMDD.log` and `logs/results_*.json`; exit code is 1 if any scene failed.

### Scheduling

Every 12 hours (a new Sentinel-1 pass over the area arrives every few days; frequent checks keep the delay after a pass short). See [`CRON_SETUP.md`](CRON_SETUP.md) for launchd, cron and systemd.

```bash
0 */12 * * * cd /path/to/suddwatch && venv/bin/python run_pipeline.py >> logs/pipeline.log 2>&1
```

### Experimental ML detector

`src/ml_flood_detection.py` is a Random Forest on 11 per-pixel texture features. Set `DETECTION_METHOD=random_forest` to use it; without a trained model it falls back to the threshold detector. The model file in the repository was trained on **synthetic** images only, so its reported 99.99 % accuracy says nothing about real floods — retrain it on validated real masks before using it.

---

## 9. Testing & Evaluation

```bash
pytest tests/                           # 242 tests, ~20 s, no credentials or SNAP needed
pytest tests/ -m integration            # 5 live tests against Copernicus/Twilio/Gmail (.env needed)
pytest tests/ --cov=src --cov-report=term-missing
```

All tests use a temporary project folder, so they never touch your real database, registry or `.env`.

| File | Tests | Covers |
|---|---|---|
| `test_config.py` | 27 | `.env` loading, defaults, paths, logging |
| `test_data_acquisition.py` | 20 (+2 live) | registry, token refresh, scene search, download retries/integrity |
| `test_preprocessing.py` | 33 | SNAP graph (all operators), GPT execution (mocked), dB conversion, output validation |
| `test_flood_detection.py` | 16 | thresholds, detection on synthetic scenes, **TPI regression tests**, raster alignment, pixel area |
| `test_risk_assessment.py` | 34 | data loading, population (no over-counting), villages/roads/clinics by flooded pixels |
| `test_database.py` | 44 | all tables, partial updates, queries, metrics |
| `test_pipeline.py` | 54 (+3 live) | alert thresholds/formatting/dispatch, dry run, IoU, pipeline orchestration and failure handling |
| `test_ml_flood_detection.py` | 4 | feature extraction, tiled prediction, fallback |
| `test_dashboard_backend.py` | 12 | accounts & access requests, recipients/threshold saving, audit log |
| `test_end_to_end.py` | 3 | the real pipeline on a synthetic scene + synthetic DEM/WorldPop/OSM → database → dashboard reader |

### Evaluation metrics

| Metric | Target | How it is measured | Current state |
|---|---|---|---|
| IoU | ≥ 0.65 | Intersection over Union vs `data/reference_masks/<scene>_reference.tif` | Computed automatically when a reference mask exists. **No real scene has been validated yet**; unvalidated events show "not validated". |
| End-to-end latency | ≤ 60 min | satellite sensing time → alerts finished, per event | Recorded for every run |
| Alert acceptance | > 95 % | messages accepted by Twilio/SMTP ÷ messages attempted | Recorded per message. Handset delivery receipts need Twilio status callbacks (future work). |

---

## 10. Repository Structure

```
suddwatch/
├── src/                          # pipeline back end
│   ├── config.py                 # settings (.env + dashboard overrides)
│   ├── data_acquisition.py       # Copernicus search/download
│   ├── preprocessing.py          # SNAP GPT + dB conversion
│   ├── flood_detection.py        # 6-stage detector
│   ├── raster_utils.py           # grid alignment, TPI, pixel areas
│   ├── risk_assessment.py        # population / villages / roads / clinics
│   ├── alerts.py                 # SMS + email
│   ├── database.py               # SQLite
│   ├── pipeline.py               # orchestrator
│   └── ml_flood_detection.py     # experimental Random Forest
├── dashboard/
│   ├── app.py                    # Streamlit app
│   ├── db.py                     # data layer (real / demo)
│   ├── auth.py                   # accounts (auth.db)
│   ├── admin_actions.py          # Admin page actions
│   ├── exporter.py               # export files
│   ├── styles.py                 # design system
│   ├── landing.html              # public landing page
│   └── requirements.txt          # dashboard-only dependencies
├── tests/                        # 247 tests (242 offline + 5 live)
├── scripts/clean_test_data.py    # removes leftovers of the old test suite
├── config/                       # SNAP graphs; runtime_settings.json (dashboard)
├── data/                         # runtime data (gitignored)
│   ├── raw/  processed/  flood_masks/  reference_masks/  exclusion_masks/
│   ├── dem/  worldpop/  osm/  admin/  database/
│   └── downloaded_scenes.json    # scene registry
├── models/random_forest.pkl      # ML model (gitignored)
├── logs/                         # pipeline + dashboard logs (gitignored)
├── run_pipeline.py               # pipeline entry point
├── requirements.txt
├── CRON_SETUP.md                 # scheduling guide
├── CHANGES.md                    # fixes made in the November 2026 review
└── .env.example
```

---

## 11. Key Design Decisions

**Why Sentinel-1 SAR?** C-band radar sees through cloud. During the May–November rainy season Greater Upper Nile is under heavy cloud for weeks, which blinds optical satellites exactly when flood monitoring matters most. ESA provides Sentinel-1 IW GRD data free of charge.

**Why a 60-minute target?** Field reports from OCHA South Sudan and WFP describe an evacuation window of roughly 45–90 minutes between rising water and roads becoming impassable. Existing products arrive 3–7 days later.

**Why SMS?** Village chiefs in remote areas often have mobile coverage but no reliable internet. SMS works on any GSM handset.

**Why role-based navigation?** Coordinators need situational awareness; operators need control and diagnostics. Separating them keeps each view focused.

**Why SQLite?** At most a few events per satellite pass. SQLite needs no server and is a single portable file.

**Why a demo-data fallback?** So the dashboard can be shown before the pipeline has processed a real scene. It is clearly labelled and disappears automatically once real results exist.

**Why align every raster to the scene grid?** The DEM, population grid, baseline and exclusion masks all have different extents and resolutions. Comparing them pixel-by-pixel without reprojection compares unrelated places.

---

## 12. Limitations & Future Work

| Limitation | Impact |
|---|---|
| Not yet validated on a real scene | IoU and latency targets have not been demonstrated on real data. Next step: process one real flood scene and compare with a hand-labelled or Copernicus EMS reference mask. |
| Sentinel-1 revisit (several days) | Floods that start and recede between passes can be missed |
| SNAP takes ~8–15 min per scene | Uses a large share of the 60-minute budget |
| Full scenes are large (~25,000 × 17,000 px) | The detector holds the scene in memory (several GB). A machine with ≥ 16 GB RAM is recommended. |
| TPI threshold (0.5 m) not calibrated | With DEM noise of ~1–2 m this may remove some genuine flood pixels; tune it (Admin → Pipeline → Calibration) once reference masks exist |
| Village population = WorldPop 1 km cell | Approximates the village's population, not a census figure |
| No state labels without boundaries file | Villages show "Unknown" state until `data/admin/south_sudan_states.geojson` is added |
| Alternative routes not computed | Roads list flooded length only |
| Alert "sent" ≠ delivered | Twilio status callbacks would give handset delivery receipts |
| ML model trained on synthetic data | Experimental; not used by default |
| Map base tiles and ReliefWeb feed need internet | The dashboard works offline except for these |
| Export wizard preview and download history are illustrative | The downloaded files themselves are real (in real-data mode) |
| Single machine | Dashboard, pipeline and database run on one computer |

**Future work:** Sentinel-1 burst processing (~2 min/scene), MODIS/Landsat fusion for daily monitoring, Twilio delivery receipts, WhatsApp channel, village-chief self-registration, field validation app, retraining the ML model on validated masks, cloud deployment.

---

## 13. Data Sources

| Dataset | Source | Licence |
|---|---|---|
| Sentinel-1 IW GRD SAR imagery | ESA Copernicus Data Space | Free, open access |
| WorldPop 2020 population grid (1 km) | University of Southampton | CC BY 4.0 |
| OpenStreetMap (roads, villages, facilities) | OSM contributors | ODbL |
| Copernicus DEM 30 m / SRTM 3Sec | ESA / NASA–USGS | Free / public domain |
| JRC Global Surface Water (optional exclusion mask) | European Commission JRC | Free, non-commercial |
| OCHA COD-AB admin boundaries (optional) | OCHA / HDX | CC BY-IGO |

---

## 14. Acknowledgements

I am profoundly grateful to the Almighty for the strength, wisdom, and resilience provided throughout the completion of this project.

My deepest appreciation is extended to my supervisor, **Prof. Paul Okanda**, whose expert guidance and constructive feedback were instrumental in defining the technical direction and quality of the SuddWatch system. Your patience and motivation provided the necessary clarity to bring this system to life during the intensive development phases.

I would also like to recognize the faculty and staff within the School of Science and Technology at USIU-Africa, my classmates and colleagues for insightful discussions, and my family for their unwavering love, prayers, and support throughout my entire academic journey.

---

<div align="center">

*SuddWatch — SWE3090 Software Project 1 · USIU-Africa · Summer Semester 2026*  
*Madut Chan (671336) · Supervised by Prof. Paul Okanda*

</div>
