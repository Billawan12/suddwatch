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

</div>

---

## Abstract

South Sudan is experiencing a deepening humanitarian crisis as annual floods displace hundreds of thousands of people across Jonglei, Unity, and Upper Nile states. The core problem is not a lack of satellite data but the failure to convert that data into actionable alerts that reach vulnerable communities before floodwaters arrive. Current flood assessments reach humanitarian responders three to seven days after a flood occurs, and more than half of displaced households receive no warning at all.

**SuddWatch** bridges this critical information gap. The system automatically downloads free ESA Sentinel-1 C-band SAR imagery, detects flood extent using a six-stage classification pipeline, quantifies human impact against WorldPop 2020 population data and OpenStreetMap infrastructure, and dispatches SMS alerts to village chiefs and HTML situation reports to UN coordinators — all within a 30–60 minute SLA from satellite pass to alert delivery.

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

Conduct a comprehensive literature review and requirements analysis on representative existing systems to identify technical and operational gaps in flood early-warning for Greater Upper Nile.

**Delivered:**
- Seven systems reviewed: Copernicus EMS, DFO, GFM, IGAD, South Africa NFWS, OCHA, REACH
- Three operational gaps identified and mapped to specific design requirements
- Three technical improvements from recent SAR literature incorporated: loose thresholding, TPI filtering, exclusion masking
- Quantified requirements: latency ≤ 60 min, IoU ≥ 0.65, alert delivery > 95%

### Objective 2 — Prototype System Development

Design and develop a prototype flood detection system addressing latency, last-mile alert delivery, and accessibility in infrastructure-poor environments within a Machine Learning System.

**Delivered:**

| Module | Purpose |
|---|---|
| `src/data_acquisition.py` | Copernicus Data Space OData API — automated scene query, download, registry |
| `src/preprocessing.py` | ESA SNAP GPT 6-operator SAR processing chain |
| `src/flood_detection.py` | 6-stage flood classifier with three literature-derived improvements |
| `src/ml_flood_detection.py` | Random Forest classifier as secondary detection method |
| `src/risk_assessment.py` | WorldPop 2020 + OSM spatial intersection for population and infrastructure risk |
| `src/alerts.py` | Twilio SMS + Gmail SMTP dual-channel alert dispatch |
| `src/database.py` | SQLite 6-table schema with full event lifecycle tracking |
| `src/pipeline.py` | Full pipeline orchestrator with per-stage logging and latency tracking |
| `dashboard/app.py` | Streamlit operational dashboard with role-based access |
| `dashboard/db.py` | Dashboard DB reader with real/demo data fallback |
| `dashboard/landing.html` | Public landing page with crisis context and sign-in flow |

### Objective 3 — Testing & Evaluation

Test and evaluate the SuddWatch prototype to assess the extent to which it addresses the identified issues.

**Delivered:**
- 53 automated unit tests across data acquisition (20) and SAR preprocessing (33)
- Performance dashboard tracking IoU scores, end-to-end latency, SLA compliance, per-stage timing
- Evaluation targets: IoU ≥ 0.65, latency ≤ 60 min, alert delivery > 95%
- Audit log recording all pipeline runs, alert dispatches, and system events

---

## 4. System Architecture

```
╔══════════════════════════════════════════════════════════════════╗
║                    AUTOMATED PIPELINE                           ║
║            Triggered by cron every 6 days (Sentinel-1 cycle)    ║
╚══════════════════════════════════════════════════════════════════╝

  Copernicus Data Space (ESA)
          │  OData API — query new IW GRD scenes, 5°–12°N, 29°–35°E
          ↓
  ┌─────────────────────────┐
  │   data_acquisition.py   │  Download .zip · Update scene registry
  └───────────┬─────────────┘
              │  data/raw/
              ↓
  ┌─────────────────────────┐
  │    preprocessing.py     │  ESA SNAP GPT · 6 operators · ~8–15 min
  └───────────┬─────────────┘
              │  data/processed/*.tif
              ↓
  ┌─────────────────────────┐
  │   flood_detection.py    │  6-stage classifier · IoU scored
  └───────────┬─────────────┘
              │  data/flood_masks/
              ↓
  ┌─────────────────────────┐
  │   risk_assessment.py    │  WorldPop 2020 + OSM intersection
  └───────────┬─────────────┘
              ↓
      ┌───────┴────────┐
      ↓                ↓
  ┌──────────┐   ┌────────────┐
  │ alerts   │   │ database   │
  │ SMS      │   │ SQLite     │
  │ Email    │   │ 6 tables   │
  └──────────┘   └─────┬──────┘
                       ↓
              ┌────────────────┐
              │ dashboard/db.py│  Real DB → seed data fallback
              └────────┬───────┘
                       ↓
              ┌────────────────┐
              │ dashboard/     │  Role-based Streamlit dashboard
              │ app.py         │
              └────────────────┘
```

---

## 5. Technical Implementation

### 5.1 SAR Processing Pipeline (ESA SNAP GPT)

```
1. Apply Orbit File          → Corrects satellite orbital parameters
2. Thermal Noise Removal     → Removes IW GRD thermal noise pattern
3. Radiometric Calibration   → Converts DN to sigma-naught (σ°) in dB
4. Speckle Filter (Lee 5×5)  → Reduces multiplicative SAR speckle noise
5. Range-Doppler TC (SRTM)   → Terrain correction at 10m resolution
6. Linear to dB              → Logarithmic scale for thresholding
```

### 5.2 Flood Detection Algorithm (6 Stages)

```
Stage 1: Change Detection
  → Compare VH backscatter vs. dry-season baseline
  → Pixels with decrease > 2 dB flagged as potential flood

Stage 2: Otsu Thresholding
  → Optimal binary threshold from VH band histogram

Stage 3: Loose Threshold Refinement  [Hansen et al., 2025]
  → Cluster density analysis reduces false positives by > 50%

Stage 4: TPI Filtering               [Hansen et al., 2025]
  → Exclude TPI > 0.5 (ridges, hillslopes — flooding impossible here)

Stage 5: Exclusion Masking           [Wagner et al., 2026]
  → Remove permanent water bodies and urban areas

Stage 6: Morphological Cleaning
  → Remove isolated pixels, fill holes in flood polygons
```

**Quality metric:** IoU ≥ 0.65 target.

### 5.3 Risk Assessment

| Layer | Source | Output |
|---|---|---|
| WorldPop 2020 (1km grid) | University of Southampton | Total population within flood extent |
| OSM Villages | OpenStreetMap | Named settlements at risk; flood risk % |
| OSM Roads | OpenStreetMap | Flooded/at-risk road segments |
| OSM Health Facilities | OpenStreetMap | Hospitals and clinics at risk |

### 5.4 Alert System

**SMS (Twilio) — 160 chars, any GSM handset:**
```
SUDDWATCH ALERT | EVT-2026-047
Flood: Bor South, Jonglei
Area: 1,200 ha | Pop: 5,000
Roads cut: 3 | Facilities: 2
ID: SW-2026-047-001
```

**Email (Gmail SMTP)** — Full HTML situation report with village breakdown, road matrix, facility status, and recommended response actions.

### 5.5 Database Schema

```sql
events               -- One record per detection event
flood_masks          -- GeoTIFF path + IoU + extent ha
affected_populations -- One record per affected village
infrastructure_impacts -- Roads and health facilities
alerts               -- Alert dispatch log (SMS/email)
processing_logs      -- Per-stage timing for every run
```

---

## 6. Dashboard

The operational dashboard (`dashboard/app.py`) is built with Streamlit 1.58. It uses **role-based navigation** — Users and Admins see different pages tailored to their responsibilities. The dashboard operates in two modes: **real data mode** when the pipeline has populated the SQLite database, and **demo data mode** with realistic seed data when the database is empty.

### Authentication

The landing page (`dashboard/landing.html`) presents the public-facing site. Users sign in via the Sign In tab. Access requests are submitted via the Request Access tab and approved by an Admin.

**Demo credentials for SWE3090 evaluation:**

| Email | Password | Role |
|---|---|---|
| `admin@suddwatch.org` | `admin123` | Admin |
| `coord@ocha.org` | `ocha2025` | User |
| `analyst@reach.org` | `reach2025` | User |

> These are demonstration credentials for academic evaluation only. A production deployment would use a proper authentication database with hashed passwords.

### Login Page

A full-screen split layout — the left half displays the SuddWatch branding, system capabilities (30–60 min SLA, SAR cloud penetration, SMS delivery), and project credit. The right half contains the sign-in and access request forms.

### User Role — Navigation & Pages

Users are humanitarian coordinators and field analysts. They see:

| Page | Content |
|---|---|
| **Home** | Live event banner (event ID, location, hectares, population at risk, IoU, timestamp) · 6 KPI cards with sparklines · 10-layer interactive flood map (Folium/OpenStreetMap) · Satellite acquisition timeline |
| **History** | Season peak event callout · Event archive with state and date filters · Pagination — *charts and heatmaps hidden for Users* |
| **Export** | 3-step wizard: Scope → Format & Layers → Generate · Formats: GeoJSON, Shapefile, CSV, GeoTIFF, PDF · Download history |
| **Intelligence** | Affected villages table · Road accessibility table · Health facilities table · Recent system alerts · Data sources · Field Evidence & Media · Humanitarian Intelligence Feed (ReliefWeb) |

### Admin Role — Navigation & Pages

Admins are system operators. They see:

| Page | Content |
|---|---|
| **History** | Full history — KPI strip, response latency timeline with SLA lines, flood recurrence heatmap (states × months), monthly trend chart, event archive *(landing page after sign-in)* |
| **Performance** | Pipeline timing · Detection quality (IoU tracking) · SLA compliance rate · Stage duration heatmap |
| **User Management** | Active accounts · Pending access requests with Approve/Reject |
| **Alert Config** | SMS recipient list · Email recipient list · Alert thresholds (extent, population, IoU) · Test alert dispatch |
| **Pipeline** | Stage health (6 stages) · Manual pipeline run with scene ID and dry-run option · Calibration sliders |
| **Audit Log** | Chronological system event log · CSV export |
| **System Health** | External service connectivity · Storage usage · Season management · Cache management |

### Interactive Flood Map — 10 Toggleable Layers

| Layer | Description |
|---|---|
| Flood Zones | Historical SAR-derived extents — Jonglei, Unity, Upper Nile |
| Flood Severity | 3 rings (severe/moderate/minor) scaled from event hectares |
| Major Waterways | White Nile, Sobat River, Bahr el Ghazal, Pibor River |
| Villages | DB-driven pins: red=High, amber=Medium, green=Low risk |
| Health Facilities | Red cross=at risk, green cross=safe |
| IDP Camps | Bentiu PoC (113K), Malakal PoC, Bor, Akobo, Leer |
| UN/NGO Sites | OCHA, WFP, MSF, IRC, UNICEF coordination points |
| Roads | Red=flooded, amber=at risk, green=passable |
| Alert Recipients | SMS dispatch markers |
| Satellite Coverage | Sentinel-1 IW swath boundary (250km width) |

---

## 7. Installation & Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | Tested on 3.12.13 |
| ESA SNAP 9.0+ | `gpt` at `/Applications/esa-snap/bin/gpt` (macOS) |
| Copernicus Data Space account | Free at https://dataspace.copernicus.eu |
| Twilio account | SMS-capable number required |
| Gmail App Password | Enable 2FA, then create App Password |

### Setup

```bash
# 1. Clone
git clone https://github.com/Billawan12/suddwatch.git
cd suddwatch

# 2. Virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Credentials
cp .env.example .env
# Edit .env with all values (see below)

# 5. Verify config
python3 -c "from src.config import Config; Config(); print('OK')"

# 6. Launch dashboard
streamlit run dashboard/app.py
```

### Environment Variables (`.env`)

```bash
# Copernicus Data Space
COPERNICUS_USER=your_email@example.com
COPERNICUS_PASSWORD=your_password

# Twilio SMS
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx

# Gmail SMTP (App Password — not account password)
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Alert recipients
SMS_RECIPIENTS=+211921000001,+211921000002
EMAIL_RECIPIENTS=coord@ocha.org,analyst@reach.org

# Bounding box (Greater Upper Nile)
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
# http://localhost:8501
```

The dashboard auto-detects whether real pipeline data exists. If the database is empty it serves realistic seed data — full functionality is available for evaluation without running the pipeline.

### Full Pipeline Run

```bash
source venv/bin/activate
python3 run_pipeline.py
```

### Automated Scheduling

See [`CRON_SETUP.md`](CRON_SETUP.md) for full scheduling instructions.

```bash
# Runs at 06:00 UTC every 6 days (Sentinel-1 revisit cycle)
0 6 */6 * * /path/to/venv/bin/python3 /path/to/run_pipeline.py >> logs/pipeline.log 2>&1
```

### Restoring a Previous Version

The pre-UX-refactor stable version is tagged:
```bash
git checkout stable-pre-ux-refactor -- dashboard/app.py
```

---

## 9. Testing & Evaluation

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Test Coverage

| File | Tests | Areas |
|---|---|---|
| `test_data_acquisition.py` | 20 | Registry I/O, API token refresh, scene filtering, download validation |
| `test_preprocessing.py` | 33 | SNAP path validation, graph construction (all 6 operators), error handling |
| `test_pipeline.py` | — | Full pipeline integration with mock Copernicus responses |

### Evaluation Metrics

| Metric | Target | Measured By |
|---|---|---|
| IoU Score | ≥ 0.65 | Intersection over Union vs. reference flood mask |
| End-to-end latency | ≤ 60 min | `processing_end_time − satellite_acquisition_time` |
| Alert delivery rate | > 95% | Twilio delivery receipts / total dispatched |

---

## 10. Repository Structure

```
suddwatch/
│
├── src/                         # Automated pipeline backend
│   ├── config.py                # Central configuration (reads .env)
│   ├── data_acquisition.py      # Copernicus OData API + scene download
│   ├── preprocessing.py         # ESA SNAP GPT SAR processing
│   ├── flood_detection.py       # 6-stage flood classifier
│   ├── ml_flood_detection.py    # Random Forest alternative classifier
│   ├── risk_assessment.py       # Population + infrastructure impact
│   ├── alerts.py                # Twilio SMS + Gmail SMTP dispatch
│   ├── database.py              # SQLite schema + write operations
│   └── pipeline.py              # Pipeline orchestrator
│
├── dashboard/                   # Streamlit role-based dashboard
│   ├── app.py                   # Main application (~4,800 lines)
│   │                            #   Pages: Home, History, Performance,
│   │                            #          Export, Intelligence,
│   │                            #          User Management, Alert Config,
│   │                            #          Pipeline, Audit Log, System Health
│   ├── db.py                    # DB reader (real + demo fallback)
│   ├── styles.py                # Design system (colours, CSS, components)
│   ├── landing.html             # Public landing page
│   └── requirements.txt         # Dashboard-only dependencies
│
├── tests/                       # 53 automated tests
│   ├── conftest.py
│   ├── test_data_acquisition.py
│   ├── test_preprocessing.py
│   └── test_pipeline.py
│
├── config/
│   └── snap_preprocess_test_scene.xml
│
├── data/                        # Runtime data (gitignored)
│   ├── raw/                     # Downloaded Sentinel-1 scenes
│   ├── processed/               # SNAP output GeoTIFFs
│   ├── flood_masks/             # Detection masks + JSON summaries
│   ├── dem/                     # Copernicus DEM 30m
│   ├── worldpop/                # WorldPop 2020 population grid
│   ├── osm/                     # villages, roads, health_facilities GeoJSON
│   ├── database/                # suddwatch.db (SQLite)
│   └── downloaded_scenes.json   # Scene registry
│
├── models/                      # ML models (gitignored)
│   └── random_forest.pkl
│
├── logs/                        # Pipeline logs (gitignored)
├── run_pipeline.py              # Pipeline entry point
├── requirements.txt             # Full pipeline dependencies (local)
├── CRON_SETUP.md                # Scheduling guide
├── .env.example                 # Credential template
├── .python-version              # Python 3.12 pin
├── runtime.txt                  # Python 3.12 for cloud environments
└── .gitignore
```

---

## 11. Key Design Decisions

**Why Sentinel-1 SAR?**
C-band SAR penetrates cloud cover reliably at all times. During the May–November rainy season, Greater Upper Nile has 90%+ cloud cover for weeks — making all optical sensors useless at exactly the time flood monitoring is most critical. ESA provides Sentinel-1 IW GRD data free of charge via Copernicus.

**Why 30–60 minutes?**
Field reports from OCHA South Sudan and WFP document that the critical evacuation window — between floodwaters rising and roads becoming impassable — is typically 45–90 minutes. A 30–60 minute SLA targets the beginning of this window. Existing systems that take 3–7 days arrive after roads are already cut.

**Why SMS?**
Village chiefs in remote Greater Upper Nile have mobile coverage but no reliable internet. SMS works on any GSM handset, requires no data connection, and costs fractions of a cent. The 160-character SuddWatch alert conveys all operationally critical information in one message.

**Why role-based navigation?**
Users (humanitarian coordinators) need situational awareness — the live map, event data, intelligence, and export tools. Admins (system operators) need operational control — full history analytics, performance tracking, and system management. Separating these avoids information overload and keeps each interface focused on its purpose.

**Why SQLite?**
At most one event per 6-day satellite pass. SQLite handles this comfortably with zero configuration, produces a single portable `.db` file, and eliminates database server complexity in resource-constrained environments.

**Why a demo data fallback?**
`dashboard/db.py` auto-detects whether real pipeline data exists and falls back to seed data if not. This ensures the dashboard is always functional for evaluation — including in academic assessment environments where running the full pipeline may not be practical.

---

## 12. Limitations & Future Work

| Limitation | Impact |
|---|---|
| 6-day Sentinel-1 revisit cycle | Floods that begin and recede between passes may be missed |
| SNAP GPT ~8–15 min per scene | Reduces available buffer within 60-min SLA |
| ML classifier needs labelled training data | Detection quality depends on validated historical masks |
| Admin panel is a prototype | User approve/reject does not write to an authentication database |
| Static SMS recipient list | No self-service registration for village chiefs |
| Dashboard runs locally | Cloud deployment requires resolving geospatial dependency conflicts |

**Future work:** Sentinel-1 burst processing (~2 min/scene), MODIS/Landsat fusion for daily monitoring, WhatsApp alert channel, field validation mobile app, automatic model retraining, cloud deployment.

---

## 13. Data Sources

| Dataset | Source | Licence |
|---|---|---|
| Sentinel-1 IW GRD SAR imagery | ESA Copernicus Data Space | Free, open access |
| WorldPop 2020 population grid (1 km) | University of Southampton | CC BY 4.0 |
| OpenStreetMap (roads, villages, facilities) | OSM contributors | ODbL |
| SRTM 3Sec DEM | NASA / USGS via ESA SNAP | Public domain |
| JRC Global Surface Water | European Commission JRC | Free, non-commercial |

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
