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
[![License](https://img.shields.io/badge/License-Academic-orange?style=flat-square)](LICENSE)

</div>

---

## Abstract

South Sudan is experiencing a deepening humanitarian crisis as annual floods displace hundreds of thousands of people across Jonglei, Unity, and Upper Nile states. The core of the problem is not a lack of satellite data but the failure to convert that data into actionable alerts that reach vulnerable communities before floodwaters arrive. Current flood assessments reach humanitarian responders three to seven days after a flood occurs, and more than half of displaced households receive no warning at all. This delay leads directly to loss of life, destruction of property, and the disruption of essential aid operations.

**SuddWatch** bridges this critical information gap. The system automatically downloads free ESA Sentinel-1 C-band SAR imagery, detects flood extent using a six-stage classification pipeline incorporating Otsu thresholding, loose threshold refinement through cluster density analysis, Topographic Position Index (TPI) filtering, change detection, exclusion masking, and morphological cleaning. It then quantifies the human impact by overlaying detected flood extent against WorldPop 2020 population data and OpenStreetMap infrastructure layers. The entire process — from satellite overpass to SMS delivery to village chiefs — is designed to complete within 30 to 60 minutes.

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

South Sudan's topography — characterised by the vast Sudd wetland (30,000–40,000 km² in the dry season, expanding to over 80,000 km² at peak flood) and the expansive White Nile floodplains with gradients less than 0.1% — creates an environment where seasonal flooding is not merely possible but an expected annual occurrence. When heavy rains fall in the Ethiopian Highlands and Ugandan catchment areas, waters flow downstream into South Sudan, where flat terrain offers virtually no resistance to the lateral spread of inundation across hundreds of kilometres of agricultural land, settlements, and transportation networks.

Since 2019, rainfall totals have broken century-long records every year. The 2022 flood season was the worst in recorded history: 4.7 million hectares were inundated at peak, displacing over 918,000 people across four simultaneously flooded states. The 2023, 2024, and 2025 seasons followed similar trajectories. Major settlements most severely affected include:

- **Bor** — capital of Jonglei State, repeatedly flooded, road access cut for weeks
- **Bentiu** — capital of Unity State, home to 100,000+ IDPs, proximity to the Sudd makes it especially vulnerable
- **Malakal** — capital of Upper Nile State, located at the confluence of the Sobat River and the White Nile where backwater flooding creates prolonged inundation lasting months

A comparative review of seven existing flood monitoring systems — Copernicus EMS, Dartmouth Flood Observatory (DFO), Global Flood Monitoring (GFM), IGAD Flood Early Warning System, South African National Flood Warning System, UN OCHA Situation Reports, and the REACH Initiative flood mapping programme — identified three persistent and unresolved gaps:

| Gap | Current System Behaviour | Humanitarian Consequence |
|---|---|---|
| **Latency** | 3–7 days from flood onset to assessment reaching responders | Evacuation windows missed; roads impassable before warnings arrive |
| **Last-mile delivery** | Outputs distributed as PDF maps via email and ReliefWeb | 52% of displaced households receive no warning before floodwaters arrive (IFRC) |
| **Cloud cover** | Optical satellites blind during 90%+ cloud cover in May–November | Flooding goes undetected for weeks during the peak rainy season |

SuddWatch builds directly on the technical methodology demonstrated by REACH — adopting the same SAR preprocessing steps and Otsu thresholding approach — but extends it with full automation, last-mile SMS delivery, and a sustainable open-source architecture that requires no specialized hardware.

---

## 2. Problem Statement

The gap is not technical feasibility. SAR-based flood detection at village-level resolution over South Sudan is demonstrated and achievable. The problem is that existing systems:

- Produce static PDF map products distributed through internet-dependent institutional channels
- Rely on manual processing workflows requiring trained analysts — adding 3–7 days of preventable latency
- Require manual activation (Copernicus EMS) or produce outputs only consumable by remote sensing experts (DFO, GFM)
- Have broken institutional pathways that prevent alerts from reaching the communities who need them most
- Lack integration between detection outputs and alert dispatch — meaning that even when maps exist, they do not generate warnings

SuddWatch solves this by treating the entire chain — from Sentinel-1 overpass to SMS delivery to a village chief's mobile phone — as a single automated pipeline, with end-to-end latency as the primary design constraint.

---

## 3. Project Objectives

### Objective 1 — Literature Review & Requirements Analysis

Conduct a comprehensive literature review and requirements analysis on representative existing systems to identify the technical and operational gaps in flood early-warning for Greater Upper Nile, and derive specific, measurable system requirements from these findings.

**Delivered:**
- Seven systems reviewed across global (Copernicus EMS, DFO, GFM), regional/Africa (IGAD, South Africa), and local/South Sudan (OCHA, REACH) perspectives
- Three operational gaps identified and mapped to specific design requirements
- Three technical improvements from recent SAR literature incorporated: loose thresholding (Hansen et al., 2025), TPI filtering (Hansen et al., 2025), exclusion masking (Wagner et al., 2026)
- Quantified requirements established: latency ≤ 60 min, IoU ≥ 0.65, alert delivery > 95%, false positive reduction > 50% vs. basic Otsu

### Objective 2 — Prototype System Development

Design and develop a prototype flood detection system that addresses latency, last-mile alert delivery, and accessibility in infrastructure-poor environments within a Machine Learning System.

**Delivered:**

| Module | Purpose |
|---|---|
| `src/data_acquisition.py` | Copernicus Data Space OData API — automated scene query, download, and scene registry management |
| `src/preprocessing.py` | ESA SNAP GPT 6-operator SAR processing chain |
| `src/flood_detection.py` | 6-stage flood classifier including three literature-derived improvements |
| `src/ml_flood_detection.py` | Random Forest classifier as secondary detection method |
| `src/risk_assessment.py` | WorldPop 2020 + OSM spatial intersection for population and infrastructure risk |
| `src/alerts.py` | Twilio SMS + Gmail SMTP dual-channel alert dispatch |
| `src/database.py` | SQLite 6-table schema with full event lifecycle tracking |
| `src/pipeline.py` | Full pipeline orchestrator with per-stage logging and latency tracking |
| `dashboard/app.py` | Streamlit operational dashboard (~4,200 lines) |
| `dashboard/db.py` | Dashboard DB reader with intelligent real/demo data fallback |
| `dashboard/landing.html` | Public landing page with crisis context and system information |

### Objective 3 — Testing & Evaluation

Test and evaluate the SuddWatch prototype to assess the extent to which it addresses the issues identified in the literature review.

**Delivered:**
- 53 automated unit tests across data acquisition (20 tests) and SAR preprocessing (33 tests)
- Performance dashboard tracking IoU scores, end-to-end latency, SLA compliance rate, and per-stage timing
- Evaluation framework with defined targets: IoU ≥ 0.65, latency ≤ 60 min, alert delivery > 95%
- Audit log recording all pipeline runs, alert dispatches, and system events

---

## 4. System Architecture

```
╔══════════════════════════════════════════════════════════════════╗
║                    AUTOMATED PIPELINE                           ║
║            Triggered by cron every 6 days (Sentinel-1 cycle)    ║
╚══════════════════════════════════════════════════════════════════╝

  Copernicus Data Space (ESA)
          │  OData API — query new IW GRD scenes over 5°–12°N, 29°–35°E
          ↓
  ┌─────────────────────────┐
  │   data_acquisition.py   │  Download .zip · Update scene registry
  └───────────┬─────────────┘
              │  data/raw/S1A_IW_GRDH_*.zip
              ↓
  ┌─────────────────────────┐
  │    preprocessing.py     │  ESA SNAP GPT · 6 operators · ~8–15 min
  └───────────┬─────────────┘
              │  data/processed/*.tif (σ° in dB, terrain corrected)
              ↓
  ┌─────────────────────────┐
  │   flood_detection.py    │  6-stage classifier · IoU scored
  └───────────┬─────────────┘
              │  data/flood_masks/*.tif + risk_summary.json
              ↓
  ┌─────────────────────────┐
  │   risk_assessment.py    │  WorldPop 2020 + OSM intersection
  └───────────┬─────────────┘
              │  Village/road/facility risk records
              ↓
      ┌───────┴────────┐
      ↓                ↓
  ┌──────────┐   ┌────────────┐
  │ alerts   │   │ database   │
  │ .py      │   │ .py        │
  │          │   │            │
  │ SMS      │   │ SQLite     │
  │ (Twilio) │   │ 6 tables   │
  │ Email    │   │            │
  │ (Gmail)  │   └─────┬──────┘
  └──────────┘         │
                       ↓
              ┌────────────────┐
              │  dashboard/    │
              │  db.py         │  Real data → dashboard
              │                │  No data  → seed data
              └────────┬───────┘
                       ↓
              ┌────────────────┐
              │  dashboard/    │
              │  app.py        │  Streamlit operational dashboard
              └────────────────┘
```

---

## 5. Technical Implementation

### 5.1 SAR Processing Pipeline

The preprocessing chain follows standard Sentinel-1 IW GRD methodology, implemented using ESA SNAP GPT:

```
Operator 1: Apply Orbit File
  → Corrects satellite orbital parameters using precise orbit files
  → Essential for accurate geolocation of all subsequent products

Operator 2: Thermal Noise Removal
  → Removes the thermal noise pattern inherent to IW GRD products
  → Prevents stripes from appearing at subswath boundaries

Operator 3: Radiometric Calibration
  → Converts raw digital numbers to sigma-naught (σ°) backscatter values
  → Enables physically meaningful comparison between scenes

Operator 4: Speckle Filter (Lee, 5×5 window)
  → Reduces multiplicative SAR speckle noise
  → Lee filter selected as the standard method for flood detection applications

Operator 5: Range-Doppler Terrain Correction
  → Orthorectifies imagery using SRTM 3 Sec DEM
  → Projects to WGS84 / UTM coordinates at 10m resolution

Operator 6: Linear to dB Conversion
  → Converts σ° to logarithmic scale
  → Provides better dynamic range for thresholding operations
```

### 5.2 Flood Detection Algorithm

The detection pipeline implements a 6-stage classifier incorporating three technical improvements from the current SAR flood detection literature:

```
Stage 1: Change Detection
  → Compare current VH backscatter against dry-season baseline composite
  → Pixels showing decrease > 2 dB flagged as potential flood
  → Reduces dependence on absolute threshold values

Stage 2: Otsu Thresholding
  → Apply Otsu's method to the VH band histogram
  → Produces optimal binary threshold separating open water from land
  → Standard method demonstrated effective for South Sudan by REACH

Stage 3: Loose Threshold Refinement [Literature improvement — Hansen et al., 2025]
  → Cluster density analysis identifies thresholded regions
  → Refines threshold where Otsu produces oversegmentation
  → Reduces false positives by > 50% compared to standard Otsu alone

Stage 4: TPI Filtering [Literature improvement — Hansen et al., 2025]
  → Compute Topographic Position Index (inner radius 100px, outer 500px)
  → Pixels with TPI > 0.5 excluded (ridges, hillslopes, upland areas)
  → Physically meaningful exclusion — flooding cannot occur on topographic highs

Stage 5: Exclusion Masking [Literature improvement — Wagner et al., 2026]
  → Apply permanent water body mask from JRC Global Surface Water
  → Exclude urban areas where SAR double-bounce creates false signals
  → Prevents reclassification of permanent water as new flood

Stage 6: Morphological Cleaning
  → Remove isolated single-pixel detections (likely speckle artefacts)
  → Fill small holes within flood polygons using binary morphology
  → Produces clean, contiguous flood extent polygons
```

**Quality metric:** Intersection over Union (IoU) between detected and reference flood mask. Target: ≥ 0.65.

### 5.3 Machine Learning Classifier

`src/ml_flood_detection.py` implements a Random Forest classifier as a secondary detection method:
- 11 input features derived from the preprocessed SAR scene (VH σ°, VV σ°, VH/VV ratio, texture metrics, terrain attributes)
- Trained on labelled flood/non-flood pixel samples from historical South Sudan scenes
- Out-of-bag validation score: 0.9999 on training set
- Deployed as an alternative to the rule-based classifier when sufficient training data is available
- Pre-trained model stored at `data/models/random_forest.pkl`

### 5.4 Risk Assessment

`src/risk_assessment.py` performs spatial intersection of the detected flood mask with three data layers:

| Layer | Source | Metric Produced |
|---|---|---|
| WorldPop 2020 (1 km grid) | University of Southampton | Total population within flood extent |
| OSM Villages | OpenStreetMap | Named settlements at risk; flood risk percentage per village |
| OSM Roads | OpenStreetMap | Road segments flooded or at risk; length affected |
| OSM Health Facilities | OpenStreetMap | Hospitals, clinics, health posts within or adjacent to flood |

### 5.5 Alert System

Two channels dispatch simultaneously upon confirmed flood detection:

**SMS (Twilio) — 160 characters, any GSM handset, no internet required:**
```
SUDDWATCH ALERT | EVT-2026-047
Flood: Bor South, Jonglei
Area: 1,200 ha | Pop: 5,000
Roads cut: 3 | Facilities: 2
ID: SW-2026-047-001
```

**Email (Gmail SMTP) — Full HTML situation report:**
Complete report includes event summary table, village-level breakdown with population figures, road accessibility matrix, health facility status, and recommended response actions. Sent to UN coordinators, OCHA, and NGO leads.

### 5.6 Database Schema

```sql
-- One record per confirmed flood detection event
events (
    event_id, event_timestamp, satellite_acquisition_time,
    processing_start_time, processing_end_time, total_latency_seconds,
    scene_id, scene_path, flood_extent_ha, affected_population,
    states_affected, location_description, iou_score
)

-- GeoTIFF flood mask files
flood_masks (event_id, mask_path, iou_score, flood_extent_ha, creation_time)

-- One record per affected village
affected_populations (
    event_id, village_name, state, county, estimated_population,
    flood_risk_percentage, latitude, longitude
)

-- Roads and health facilities impacted
infrastructure_impacts (
    event_id, infrastructure_type, name, facility_type,
    status, coordinates
)

-- Alert dispatch log
alerts (
    event_id, alert_type, recipient, status,
    sent_at, delivered_at, message_content
)

-- Per-stage timing for each pipeline run
processing_logs (
    event_id, stage, started_at, completed_at,
    duration_seconds, status, details
)
```

---

## 6. Dashboard

The operational dashboard (`dashboard/app.py`) is built with Streamlit 1.58 and serves as the primary interface for humanitarian coordinators and system administrators. It operates in two modes: **real data mode** when the pipeline has populated the SQLite database, and **demo data mode** with realistic seed data when the database is empty — ensuring the dashboard is always meaningful regardless of whether the pipeline has been run.

### Pages

| Page | Key Features |
|---|---|
| **Home** | Live event banner (event ID, location, hectares, population, IoU, timestamp) · 6 KPI cards with sparklines · 10-layer interactive flood map (Folium/OpenStreetMap) · Satellite acquisition timeline · Alert delivery feed · Field media section · Humanitarian intelligence feed (ReliefWeb API) |
| **History** | Season peak event callout · Response latency timeline with SLA reference lines at 45 and 60 min · Flood recurrence heatmap (3 states × 12 months) · Monthly trend chart · Event archive with state and date filters and pagination |
| **Performance** | Pipeline timing tab (per-stage latency) · Detection quality tab (IoU tracking) · SLA compliance tab (monthly compliance rate) · Stage duration heatmap across all runs |
| **Export** | 3-step wizard: Scope → Format & Layers → Generate · Formats: GeoJSON, Shapefile (ZIP), CSV, GeoTIFF, PDF Situation Report · Layer selection · Download history |
| **Admin** | User Management · Alert Configuration (SMS/email recipients, thresholds) · Pipeline Controls (manual trigger, dry run, calibration) · Audit Log · System Health (service connectivity, storage, cache management) |

### Interactive Map — 10 Toggleable Layers

| Layer | Data Source | Description |
|---|---|---|
| Flood Zones | Historical SAR | State-level historical flood extents (Jonglei, Unity, Upper Nile) |
| Flood Severity | Active event DB | 3 concentric rings — severe, moderate, minor — scaled from event hectares |
| Major Waterways | OSM | White Nile, Sobat River, Bahr el Ghazal, Pibor River |
| Villages | DB / OSM fallback | Pins coloured by risk level (red=High, amber=Medium, green=Low) |
| Health Facilities | DB / OSM fallback | Cross markers: red=at risk, green=safe |
| IDP Camps | Static | Bentiu PoC (113K people), Malakal PoC, Bor, Akobo, Leer |
| UN/NGO Sites | Static | OCHA, WFP, MSF, IRC, UNICEF coordination points |
| Roads | DB / static | Colour-coded: red=flooded, amber=at risk, green=passable |
| Alert Recipients | DB | Dashed rings showing where SMS alerts were dispatched |
| Satellite Coverage | Static | Sentinel-1 IW swath boundary (250 km width) |

### Demo Credentials

| Email | Password | Role |
|---|---|---|
| `admin@suddwatch.org` | `admin123` | Admin — full system access |
| `coord@ocha.org` | `ocha2025` | User — read access, exports |
| `analyst@reach.org` | `reach2025` | User — read access, exports |

> These are demonstration credentials for SWE3090 academic evaluation. A production deployment would use a proper authentication database with bcrypt-hashed passwords and session tokens.

### Theme

The dashboard supports full dark and light modes, switchable from the topbar. Dark mode is the operational default, optimised for field environments and low-light conditions.

---

## 7. Installation & Setup

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | Tested on 3.12.13 |
| ESA SNAP | 9.0+ | `gpt` at `/Applications/esa-snap/bin/gpt` (macOS) |
| Copernicus Data Space account | — | Free: https://dataspace.copernicus.eu |
| Twilio account | — | SMS gateway with SMS-capable number |
| Gmail account | — | App Password required (2FA must be enabled) |

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Billawan12/suddwatch.git
cd suddwatch

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Open .env and fill in all required values (see below)

# 5. Verify SNAP installation
/Applications/esa-snap/bin/gpt --help

# 6. Test configuration
python3 -c "from src.config import Config; c = Config(); print('Config OK')"

# 7. Launch dashboard
streamlit run dashboard/app.py
```

### Environment Variables

Copy `.env.example` to `.env` and populate all values:

```bash
# ── Copernicus Data Space (ESA) ───────────────────────────────────────
# Free account at https://dataspace.copernicus.eu
COPERNICUS_USER=your_email@example.com
COPERNICUS_PASSWORD=your_password

# ── Twilio SMS ────────────────────────────────────────────────────────
# Dashboard at https://console.twilio.com
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx

# ── Gmail SMTP ────────────────────────────────────────────────────────
# Use App Password, not your account password
# Enable 2FA then create App Password at https://myaccount.google.com/apppasswords
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx

# ── GitHub (for flood output commits) ────────────────────────────────
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# ── Alert Recipients ──────────────────────────────────────────────────
SMS_RECIPIENTS=+211921000001,+211921000002,+211921000003
EMAIL_RECIPIENTS=coord@ocha.org,analyst@reach.org

# ── Bounding Box (Greater Upper Nile — defaults cover all 3 states) ──
BOUNDING_BOX_MIN_LAT=5.0
BOUNDING_BOX_MIN_LON=29.0
BOUNDING_BOX_MAX_LAT=12.0
BOUNDING_BOX_MAX_LON=35.0
```

---

## 8. Running the System

### Dashboard Only (no pipeline required)

```bash
source venv/bin/activate
streamlit run dashboard/app.py
# Opens at http://localhost:8501
```

The dashboard auto-detects whether real pipeline data exists in `data/database/suddwatch.db`. If the database is empty, it serves realistic seed data automatically — full dashboard functionality is available for evaluation without running the pipeline.

### Full Pipeline Run

```bash
source venv/bin/activate
python3 run_pipeline.py
```

The pipeline will:
1. Query Copernicus Data Space for new Sentinel-1 IW GRD scenes over Greater Upper Nile
2. Download any new scenes not already in the registry
3. Run the SNAP GPT preprocessing chain (~8–15 minutes per scene)
4. Execute the 6-stage flood detection algorithm
5. Assess population and infrastructure risk
6. Write all results to SQLite
7. Dispatch SMS alerts via Twilio and email via Gmail SMTP

### Automated Scheduling

The pipeline runs every 6 days to match the Sentinel-1 revisit cycle. See [`CRON_SETUP.md`](CRON_SETUP.md) for complete scheduling instructions.

```bash
# Example cron entry — 06:00 UTC every 6 days
0 6 */6 * * /path/to/suddwatch/venv/bin/python3 /path/to/suddwatch/run_pipeline.py >> /path/to/suddwatch/logs/pipeline.log 2>&1
```

---

## 9. Testing & Evaluation

### Running Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run individual modules
pytest tests/test_data_acquisition.py -v   # 20 tests
pytest tests/test_preprocessing.py -v      # 33 tests
pytest tests/test_pipeline.py -v           # Integration tests
```

### Test Coverage

| Test File | Tests | Areas Covered |
|---|---|---|
| `test_data_acquisition.py` | 20 | Scene registry (load/save/corruption), API token refresh, scene query filtering by date and state, download validation, registry summary format |
| `test_preprocessing.py` | 33 | SNAP GPT path validation, graph XML construction for all 6 operators, input/output path handling, output raster validation, error handling for missing inputs |
| `test_pipeline.py` | — | Full pipeline integration with mocked Copernicus API responses and test scenes |
| `conftest.py` | — | Shared fixtures: mock config, test scene paths, sample DB records, mock Twilio client |

### Evaluation Targets & Metrics

| Metric | Target | How Measured |
|---|---|---|
| **IoU Score** | ≥ 0.65 | Intersection over Union between detected and reference flood mask |
| **End-to-end latency** | ≤ 60 min | `processing_end_time − satellite_acquisition_time` logged per event |
| **Alert delivery rate** | > 95% | Twilio delivery receipts / total SMS dispatched |
| **False positive reduction** | > 50% | Compare flood extent with TPI+loose threshold vs. basic Otsu only |

All four metrics are tracked and visualised in the **Performance** page of the dashboard, with historical trend charts and SLA compliance indicators.

---

## 10. Repository Structure

```
suddwatch/
│
├── src/                            # Automated pipeline backend
│   ├── __init__.py
│   ├── config.py                   # Central configuration (reads from .env)
│   ├── data_acquisition.py         # Copernicus OData API + scene download
│   │                               #   · SentinelDownloader class
│   │                               #   · Scene registry management
│   │                               #   · Token refresh handling
│   ├── preprocessing.py            # ESA SNAP GPT SAR processing
│   │                               #   · SARPreprocessor class
│   │                               #   · 6-operator processing graph
│   │                               #   · Output validation
│   ├── flood_detection.py          # 6-stage flood classifier
│   │                               #   · FloodDetector class
│   │                               #   · Otsu + TPI + change detection
│   │                               #   · IoU quality scoring
│   ├── ml_flood_detection.py       # Random Forest alternative classifier
│   │                               #   · 11-feature extraction
│   │                               #   · OOB score: 0.9999
│   ├── risk_assessment.py          # Population + infrastructure impact
│   │                               #   · RiskAssessor class
│   │                               #   · WorldPop 2020 intersection
│   │                               #   · OSM village/road/facility overlay
│   ├── alerts.py                   # Dual-channel alert dispatch
│   │                               #   · AlertManager class
│   │                               #   · Twilio SMS (160-char messages)
│   │                               #   · Gmail SMTP (HTML situation reports)
│   ├── database.py                 # SQLite schema + write operations
│   │                               #   · DatabaseManager class
│   │                               #   · 6-table schema
│   │                               #   · Full event lifecycle tracking
│   └── pipeline.py                 # Full pipeline orchestrator
│                                   #   · Calls all modules in sequence
│                                   #   · Per-stage logging + timing
│                                   #   · Error recovery
│
├── dashboard/                      # Streamlit operational dashboard
│   ├── app.py                      # Main application (~4,200 lines)
│   │                               #   · Landing page + auth gate
│   │                               #   · 5 pages: Home, History, Performance, Export, Admin
│   │                               #   · Dark/light theme switching
│   ├── db.py                       # Dashboard DB reader
│   │                               #   · 19 functions
│   │                               #   · Real DB → seed data fallback
│   ├── styles.py                   # Design system
│   │                               #   · Colour tokens
│   │                               #   · CSS helpers
│   │                               #   · Reusable HTML components
│   ├── landing.html                # Public landing page
│   │                               #   · Crisis context and statistics
│   │                               #   · Sign in / Sign up / Request Access
│   │                               #   · Dark + light mode
│   └── requirements.txt            # Dashboard-only dependencies (no GDAL)
│
├── tests/                          # Automated test suite
│   ├── conftest.py                 # Shared fixtures and mocks
│   ├── test_data_acquisition.py    # 20 unit tests
│   ├── test_preprocessing.py       # 33 unit tests
│   └── test_pipeline.py            # Integration tests
│
├── config/
│   └── snap_preprocess_test_scene.xml   # SNAP GPT graph for test scenes
│
├── data/                           # Runtime data (gitignored)
│   ├── raw/                        # Downloaded Sentinel-1 .zip files
│   ├── processed/                  # SNAP GPT output GeoTIFFs
│   ├── flood_masks/                # Detection output masks + JSON summaries
│   ├── dem/                        # Copernicus DEM 30m (south_sudan_dem.tif)
│   ├── worldpop/                   # WorldPop 2020 (1 km, south_sudan_pop_2020_1km.tif)
│   ├── osm/                        # OpenStreetMap vectors
│   │   ├── villages.geojson
│   │   ├── roads.geojson
│   │   └── health_facilities.geojson
│   ├── database/                   # suddwatch.db (SQLite, gitignored)
│   └── downloaded_scenes.json      # Scene registry
│
├── models/                         # ML model files (gitignored)
│   └── random_forest.pkl           # Trained Random Forest classifier
│
├── logs/                           # Pipeline execution logs (gitignored)
│   └── pipeline.log
│
├── run_pipeline.py                 # Pipeline entry point (cron target)
├── requirements.txt                # Full pipeline dependencies (local)
├── CRON_SETUP.md                   # Automated scheduling guide
├── .env.example                    # Credential template
├── .env                            # Local credentials (gitignored)
├── .python-version                 # Python 3.12 pin
├── runtime.txt                     # Python 3.12 for cloud environments
└── .gitignore                      # Excludes .db, data/, venv/, logs/
```

---

## 11. Key Design Decisions

### Why Sentinel-1 SAR?

C-band SAR penetrates cloud cover reliably at all times of day and night. During the May–November rainy season, Greater Upper Nile experiences over 90% cloud cover for weeks at a time — making all optical sensors (Landsat, Sentinel-2, MODIS) effectively unusable at exactly the time when flood monitoring is most critical. ESA provides Sentinel-1 IW GRD data free of charge through the Copernicus Data Space programme with no usage restrictions, making it the only viable satellite sensor for a sustainable, zero-cost operational system in this context.

### Why 30–60 Minutes?

Field reports from OCHA South Sudan and WFP logistics teams document that the critical evacuation window — the period between floodwaters beginning to rise and roads becoming impassable — is typically 45–90 minutes in Greater Upper Nile. A 30–60 minute SLA from satellite pass to alert delivery targets the beginning of this window, giving communities maximum time to act. Existing systems that take 3–7 days arrive after roads are already cut, making the warning operationally useless.

### Why SMS as Primary Alert Channel?

Village chiefs and community leaders in remote areas of Jonglei, Unity, and Upper Nile states commonly have mobile phone coverage but no reliable internet connectivity. SMS works on any GSM handset, does not require a data connection or smartphone, costs fractions of a cent per message, and is universally understood. The 160-character SuddWatch alert is designed to convey all operationally critical information — event ID, location, flood extent in hectares, estimated population at risk, road access status — within a single message.

### Why SQLite?

The SuddWatch pipeline produces at most one event per 6-day satellite pass cycle. SQLite handles this workload comfortably, requires zero configuration or administration, produces a single portable `.db` file that can be backed up with a simple file copy, and eliminates all dependency on a database server — critical for a system intended to run on a standard laptop in a resource-constrained environment.

### Why Streamlit?

Streamlit allows a full operational dashboard to be built and maintained entirely in Python without requiring a separate frontend framework, JavaScript expertise, or a complex deployment architecture. For a research prototype that may eventually be handed to a humanitarian organisation with limited technical capacity, a Python-only codebase is substantially more maintainable than a React/FastAPI/PostgreSQL stack.

### Why a Demo Data Fallback?

`dashboard/db.py` automatically detects whether real pipeline data exists and falls back to realistic seed data if the database is empty. This design ensures the dashboard can be demonstrated and evaluated at any time — including in an academic assessment environment where running the full pipeline (which requires Copernicus credentials, SNAP, and Twilio) may not be practical.

---

## 12. Limitations & Future Work

### Current Limitations

| Limitation | Impact |
|---|---|
| 6-day Sentinel-1 revisit cycle over Greater Upper Nile | Floods that begin and recede between passes may be missed entirely |
| SNAP GPT preprocessing ~8–15 min per scene | Reduces available time budget within 60-min SLA on slower hardware |
| Random Forest classifier requires labelled training data | ML detection quality is limited by the volume of validated historical masks |
| Admin panel is a functional prototype | Approve/reject buttons show confirmation but do not write to an authentication database |
| Export page generates structured demo data | Real exports require a complete pipeline run with actual detected flood masks |
| SMS recipients are static configuration | No self-service registration mechanism for village chiefs |
| Dashboard deployed locally | Cloud deployment requires resolving Streamlit 1.60 / geospatial dependency compatibility |

### Future Work

- **Sentinel-1 burst processing** — process individual bursts rather than full scenes to reduce preprocessing time from ~8–15 min to ~2–3 min, giving substantially more headroom within the 60-min SLA
- **MODIS/Landsat fusion** — integrate optical sensors for daily monitoring during clear-sky periods between SAR passes
- **IDP movement correlation** — integrate UNHCR displacement registration data to correlate flood events with population movement patterns
- **Automatic model retraining** — pipeline-triggered Random Forest retraining when new validated flood masks are added to the database
- **WhatsApp Business API** — add WhatsApp as an alternative alert channel for recipients with smartphones, enabling richer content including map images
- **Field validation mobile app** — a lightweight app for community reporters to submit flood observations that feed back into the system as ground truth
- **Cloud deployment** — resolve dependency conflicts for public hosting at a stable URL accessible to humanitarian partners

---

## 13. Data Sources

| Dataset | Source | Licence | Usage |
|---|---|---|---|
| Sentinel-1 IW GRD SAR imagery | ESA Copernicus Data Space | Free, open access | Primary flood detection input |
| WorldPop 2020 population grid (1 km) | WorldPop / University of Southampton | CC BY 4.0 | Population at risk estimation |
| OpenStreetMap roads, villages, health facilities | OpenStreetMap contributors | ODbL | Infrastructure risk assessment |
| SRTM 3Sec DEM | NASA / USGS (via ESA SNAP) | Public domain | Terrain correction + TPI |
| JRC Global Surface Water | European Commission JRC | Free for non-commercial | Permanent water body exclusion mask |
| Administrative boundaries | Humanitarian Data Exchange (HDX) | CC BY | Geographic reference |

---

## 14. Acknowledgements

I am profoundly grateful to the Almighty for the strength, wisdom, and resilience provided to me throughout the successful completion of this project.

My deepest appreciation is extended to my supervisor, **Prof. Paul Okanda**, whose expert guidance and constructive feedback were instrumental in defining the technical direction and quality of the SuddWatch system. Your patience and motivation provided the necessary clarity to bring this system to life during the intensive development phases.

I would also like to recognize the faculty and staff within the School of Science and Technology at the United States International University – Africa (USIU-A). The knowledge and technical skills acquired through the curriculum enabled the successful research and implementation of this flood monitoring solution.

Special thanks to my classmates, colleagues, and friends. Our insightful discussions and your moral encouragement were of great assistance as I navigated the complexities of creating the system.

Lastly, I offer my heartfelt thanks to my family for their unwavering love, prayers, and support. Your constant encouragement has been my greatest source of strength throughout my entire academic journey.

---

<div align="center">

*SuddWatch — SWE3090 Software Project 1 · USIU-Africa · Summer Semester 2026*

*Madut Chan (671336) · Supervised by Prof. Paul Okanda*

</div>
