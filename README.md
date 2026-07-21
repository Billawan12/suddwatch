# SuddWatch — Operational Flood Detection & Humanitarian Alert System

<div align="center">

**SWE3090: Software Project 1 · Summer Semester 2026**  
**United States International University – Africa**

**Student:** Madut Chan · **ID:** 671336  
**Supervisor:** Prof. Paul Okanda

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.58-red)](https://streamlit.io)
[![Sentinel-1](https://img.shields.io/badge/Data-Sentinel--1%20SAR-green)](https://dataspace.copernicus.eu)

</div>

---

## Abstract

South Sudan is experiencing a deepening humanitarian crisis as annual floods displace hundreds of thousands of people across Jonglei, Unity, and Upper Nile states. The core of the problem is not a lack of satellite data but the failure to convert that data into actionable alerts that reach vulnerable communities before floodwaters arrive. Current flood assessments reach humanitarian responders three to seven days after a flood occurs, and more than half of displaced households receive no warning at all.

SuddWatch addresses this gap by automating the full chain from satellite data acquisition to alert delivery. The system downloads free ESA Sentinel-1 C-band SAR imagery, detects flood extent using a six-stage classification pipeline, quantifies the human impact against WorldPop 2020 population data and OpenStreetMap infrastructure, and dispatches SMS alerts to village chiefs and HTML situation reports to UN coordinators — all within a 30–60 minute SLA from satellite pass to alert delivery.

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
13. [Acknowledgements](#13-acknowledgements)

---

## 1. Project Background

Greater Upper Nile — comprising Jonglei, Unity, and Upper Nile states — sits at the heart of the Sudd, one of Africa's largest wetlands. Since 2019, rainfall totals have broken century-long records every year. The 2022 flood season was the worst in recorded history: 4.7 million hectares were inundated at peak, displacing over 918,000 people across four simultaneously flooded states.

The existing response ecosystem has three critical gaps, identified through a comparative review of six systems (Copernicus EMS, Dartmouth Flood Observatory, GFM, IGAD FEWS, OCHA Situation Reports, and REACH flood mapping):

| Gap | Existing System Behaviour | Impact |
|---|---|---|
| **Cloud cover** | Optical satellites blind during 90%+ cloud cover in May–November | Flooding goes undetected for weeks |
| **Analysis latency** | REACH maps undergo multi-stage QA review; OCHA reports compiled manually | Assessments arrive 3–7 days after a flood |
| **Last-mile delivery** | Maps distributed as PDF attachments via email and ReliefWeb | Village chiefs with basic mobile phones cannot access the information |

SuddWatch builds directly on the technical methodology demonstrated by REACH — adopting the same SAR preprocessing steps, Otsu thresholding, and change detection concept — but extends it with full automation, last-mile SMS delivery, and a sustainable open-source architecture.

---

## 2. Problem Statement

The gap is not technical feasibility but operational translation. SAR-based flood detection at village-level resolution is demonstrated and achievable. The problem is that existing systems:

- Produce static PDF map products rather than structured, queryable data
- Rely on manual processing workflows that take days, not minutes
- Distribute outputs through internet-dependent channels that exclude the most vulnerable communities
- Lack integration between detection outputs and alert dispatch systems

SuddWatch solves this by treating the entire chain — from satellite pass to SMS delivery — as a single automated pipeline with end-to-end latency as the primary design constraint.

---

## 3. Project Objectives

### Objective 1 — Requirements Analysis
Conduct a comprehensive literature review and requirements analysis on representative existing systems to identify the technical and operational gaps in flood early-warning for Greater Upper Nile.

**How SuddWatch meets this:**
- Six systems reviewed across global, regional (Africa), and local (South Sudan) perspectives
- Technical gaps mapped to specific design requirements: SAR over optical (cloud cover), automated pipeline over manual analysis (latency), SMS over web portals (last-mile delivery)
- Parameters derived from literature: TPI threshold 0.5, Otsu relaxation factor 1.0, IoU target ≥ 0.65, latency SLA 30–60 minutes, alert delivery target >95%
- Bounding box (5°–12°N, 29°–35°E) covers all three target states

### Objective 2 — Prototype Development
Design and develop a prototype flood detection system that addresses latency, last-mile alert delivery, and accessibility in infrastructure-poor environments within a Machine Learning System.

**How SuddWatch meets this:**

| Component | Implementation |
|---|---|
| Data acquisition | Copernicus Data Space OData API — queries for new Sentinel-1 IW GRD scenes, downloads on detection, maintains scene registry |
| SAR preprocessing | ESA SNAP GPT: orbit correction → thermal noise removal → radiometric calibration → speckle filter (Lee, 5×5) → terrain correction (SRTM 3Sec) |
| Flood detection | 6-stage classifier: VH change detection → Otsu thresholding → loose threshold refinement → TPI filtering → exclusion masking → morphological cleaning |
| ML classifier | Random Forest trained on labelled SAR scenes (`src/ml_flood_detection.py`) |
| Risk assessment | Spatial intersection of flood mask with WorldPop 2020 population grid, OSM villages, roads, and health facilities |
| Alert dispatch | Twilio SMS (160-char to village chiefs) + Gmail SMTP (HTML situation report to coordinators) |
| Database | SQLite with 6-table schema: events, flood_masks, affected_populations, infrastructure_impacts, alerts, processing_logs |
| Dashboard | Streamlit operational dashboard with landing page, authentication, and 5 pages |

### Objective 3 — Testing & Evaluation
Test and evaluate the SuddWatch prototype to assess the extent to which it addresses the identified issues.

**How SuddWatch meets this:**
- 53 automated unit tests covering data acquisition (20 tests) and preprocessing (33 tests)
- Performance dashboard tracks IoU, end-to-end latency, SLA compliance rate, and per-stage timing
- Evaluation targets: IoU ≥ 0.65, latency ≤ 60 min, alert delivery success >95%

---

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   AUTOMATED PIPELINE                     │
│               (triggered by cron / manual)               │
└──────────────────────────────────────────────────────────┘

Copernicus Data Space
        │  OData API query
        ↓
┌──────────────────────┐
│  data_acquisition.py │  Downloads new Sentinel-1 IW GRD scenes
└──────────┬───────────┘  Maintains scene registry
           │ .zip → data/raw/
           ↓
┌──────────────────────┐
│  preprocessing.py    │  ESA SNAP GPT — 6 operators, ~8 min/scene
└──────────┬───────────┘
           │ .tif → data/processed/
           ↓
┌──────────────────────┐
│  flood_detection.py  │  Otsu + TPI + change detection → binary mask
└──────────┬───────────┘  IoU scored against reference
           │ flood_mask.tif → data/flood_masks/
           ↓
┌──────────────────────┐
│  risk_assessment.py  │  WorldPop 2020 + OSM intersection
└──────────┬───────────┘  Village / road / facility risk records
           │
           ├──────────────────────────────────────┐
           ↓                                      ↓
┌──────────────────────┐           ┌──────────────────────┐
│  alerts.py           │           │  database.py          │
│  SMS via Twilio      │           │  Writes to SQLite     │
│  Email via Gmail     │           │  data/database/       │
└──────────────────────┘           └──────────┬───────────┘
                                              │
                              ┌───────────────▼──────────────┐
                              │  dashboard/db.py              │
                              │  Reads from pipeline DB       │
                              │  Falls back to seed data      │
                              └───────────────┬──────────────┘
                                              │
                              ┌───────────────▼──────────────┐
                              │  dashboard/app.py (Streamlit) │
                              │  Operational dashboard        │
                              └──────────────────────────────┘
```

---

## 5. Technical Implementation

### 5.1 SAR Processing Pipeline

The preprocessing chain follows standard Sentinel-1 IW GRD methodology:

```
1. Apply Orbit File          → Corrects satellite orbital parameters
2. Thermal Noise Removal     → Removes thermal noise pattern from IW GRD
3. Radiometric Calibration   → Converts DN to sigma-naught (σ°) in dB
4. Speckle Filter (Lee 5×5)  → Reduces multiplicative SAR speckle noise
5. Range-Doppler TC          → Terrain correction using SRTM 3Sec DEM
6. Linear to dB              → Convert to logarithmic scale for thresholding
```

### 5.2 Flood Detection Algorithm

Six-stage classifier based on established SAR flood detection literature:

```
Stage 1: Change Detection
  Compare current VH backscatter against dry-season baseline
  Pixels with decrease > 2 dB flagged as potential flood

Stage 2: Otsu Thresholding
  Apply Otsu method to VH band histogram
  Produces optimal binary threshold separating water from land

Stage 3: Loose Threshold Refinement
  Cluster density analysis to reduce false positives

Stage 4: TPI Filtering
  Compute Topographic Position Index (inner 100px, outer 500px)
  Exclude pixels with TPI > 0.5 (ridges, hillslopes)

Stage 5: Exclusion Masking
  Apply permanent water body mask
  Exclude urban areas where SAR response is ambiguous

Stage 6: Morphological Cleaning
  Remove isolated single-pixel detections
  Fill small holes in flood polygons
```

**Quality metric:** IoU (Intersection over Union) against reference flood mask. Target: ≥ 0.65.

### 5.3 Risk Assessment

Spatial intersection of flood mask with:
- **WorldPop 2020** (1km resolution) — estimates affected population
- **OSM Villages** — identifies named settlements within flood boundary
- **OSM Roads** — identifies road segments classified as flooded/at risk
- **OSM Health Facilities** — identifies health posts and clinics at risk

### 5.4 Alert System

Two channels dispatch simultaneously upon confirmed flood detection:

**SMS (Twilio) — 160 characters**
```
SUDDWATCH ALERT | EVT-2026-047
Flood detected: Bor South, Jonglei
Area: 1,200 ha | Pop: 5,000 at risk
Roads: 3 cut off | Facilities: 2
Alert ID: SW-2026-047-001
```

**Email (Gmail SMTP)** — Full HTML situation report with event summary, village-level breakdown, road accessibility matrix, health facility status, and recommended response actions.

### 5.5 Database Schema

```sql
events               -- One record per detection event
flood_masks          -- GeoTIFF path + IoU + flood extent ha
affected_populations -- One record per affected village
infrastructure_impacts -- Roads and health facilities at risk
alerts               -- Alert dispatch log (SMS/email per recipient)
processing_logs      -- Per-stage timing and status for each run
```

---

## 6. Dashboard

Built with Streamlit 1.58. Serves as the primary interface for humanitarian coordinators and system administrators.

### Pages

| Page | Description |
|---|---|
| **Home** | Live event banner, 6 KPI cards, 10-layer interactive flood map (Folium/OpenStreetMap), satellite acquisition timeline, alert feed, field media section, humanitarian intelligence feed |
| **History** | Season peak event callout, response latency timeline with SLA reference lines, flood recurrence heatmap (states × months), monthly trend chart, event archive with filters |
| **Performance** | Pipeline timing, detection quality (IoU tracking), SLA compliance rate, stage duration heatmap |
| **Export** | 3-step wizard: scope selection → format & layer selection → generation. Formats: GeoJSON, Shapefile, CSV, GeoTIFF, PDF Situation Report |
| **Admin** | User management, alert configuration, pipeline controls (manual trigger), audit log, system health |

### Interactive Map — 10 Toggleable Layers

| Layer | Description |
|---|---|
| Flood Zones | Historical SAR-derived flood extents for all three states |
| Flood Severity | 3 concentric rings (severe/moderate/minor) from active event |
| Major Waterways | White Nile, Sobat River, Bahr el Ghazal, Pibor River |
| Villages | DB-driven pins coloured by risk level (High/Medium/Low) |
| Health Facilities | Red = at risk, Green = safe |
| IDP Camps | Bentiu PoC, Malakal PoC, and active displacement sites |
| UN/NGO Sites | OCHA, WFP, MSF, IRC, UNICEF coordination points |
| Roads | Colour-coded by flood status (flooded/at risk/passable) |
| Alert Recipients | Alert dispatch markers |
| Satellite Coverage | Sentinel-1 IW swath boundary |

### Demo Credentials

| Email | Password | Role |
|---|---|---|
| `admin@suddwatch.org` | `admin123` | Admin |
| `coord@ocha.org` | `ocha2025` | User |
| `analyst@reach.org` | `reach2025` | User |

> These are demonstration credentials for SWE3090 academic evaluation only. A production deployment would use a proper authentication database with hashed passwords.

---

## 7. Installation & Setup

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | |
| ESA SNAP 9.0+ | GPT at `/Applications/esa-snap/bin/gpt` (macOS) |
| Copernicus account | Free: https://dataspace.copernicus.eu |
| Twilio account | SMS gateway |
| Gmail App Password | 2FA must be enabled |

### Setup

```bash
# Clone
git clone https://github.com/Billawan12/suddwatch.git
cd suddwatch

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Dependencies
pip install -r requirements.txt

# Credentials
cp .env.example .env
# Edit .env with your credentials

# Verify configuration
python3 src/config.py

# Launch dashboard
streamlit run dashboard/app.py
```

### Environment Variables

```bash
COPERNICUS_USER=your_email@example.com
COPERNICUS_PASSWORD=your_password
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1xxxxxxxxxx
SMTP_USER=your_gmail@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
SMS_RECIPIENTS=+211921000001,+211921000002
EMAIL_RECIPIENTS=coord@ocha.org,analyst@reach.org
```

---

## 8. Running the System

### Manual Pipeline Run

```bash
source venv/bin/activate
python3 run_pipeline.py
```

### Automated Scheduling

See [`CRON_SETUP.md`](CRON_SETUP.md) for full cron configuration. The pipeline runs every 6 days to match the Sentinel-1 repeat cycle.

```bash
# Example cron — 06:00 every 6 days
0 6 */6 * * /path/to/venv/bin/python3 /path/to/suddwatch/run_pipeline.py >> logs/pipeline.log 2>&1
```

### Dashboard Modes

The dashboard operates in two modes automatically:
- **Real data mode** — when `data/database/suddwatch.db` contains pipeline results
- **Demo data mode** — fallback with realistic seed data when DB is empty

---

## 9. Testing & Evaluation

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

### Test Coverage

| File | Tests | Areas Covered |
|---|---|---|
| `test_data_acquisition.py` | 20 | Registry I/O, API token refresh, scene filtering, download validation |
| `test_preprocessing.py` | 33 | SNAP path validation, graph construction, I/O path handling, error handling |
| `test_pipeline.py` | — | Full pipeline integration with mock Copernicus responses |

### Evaluation Metrics

| Metric | Target | Source |
|---|---|---|
| IoU Score | ≥ 0.65 | Intersection over Union vs. reference mask |
| End-to-end latency | ≤ 60 min | Satellite acquisition → alert delivery |
| Alert delivery rate | > 95% | Twilio/SMTP confirmation rate |

---

## 10. Repository Structure

```
suddwatch/
├── src/                        # Pipeline backend
│   ├── config.py               # Central configuration (reads .env)
│   ├── data_acquisition.py     # Copernicus OData API + download
│   ├── preprocessing.py        # ESA SNAP GPT SAR processing
│   ├── flood_detection.py      # 6-stage flood classifier
│   ├── ml_flood_detection.py   # Random Forest alternative classifier
│   ├── risk_assessment.py      # Population + infrastructure impact
│   ├── alerts.py               # Twilio SMS + Gmail SMTP
│   ├── database.py             # SQLite schema + writes
│   └── pipeline.py             # Pipeline orchestrator
├── dashboard/                  # Streamlit frontend
│   ├── app.py                  # Main application (~4,200 lines)
│   ├── db.py                   # DB reader (real + demo fallback)
│   ├── styles.py               # Design system
│   └── landing.html            # Public landing page
├── tests/                      # 53 automated tests
├── config/                     # SNAP GPT graph XML
├── run_pipeline.py             # Pipeline entry point
├── requirements.txt
├── CRON_SETUP.md
├── .env.example
└── .gitignore
```

---

## 11. Key Design Decisions

**Why Sentinel-1 SAR?**
C-band SAR penetrates cloud cover reliably. During the May–November rainy season, Greater Upper Nile has 90%+ cloud cover for weeks — making optical sensors unusable at exactly the time flood monitoring is most critical. ESA provides Sentinel-1 data free of charge via Copernicus.

**Why 60 minutes?**
OCHA South Sudan and WFP field reports indicate the critical evacuation window — between floodwaters rising and roads becoming impassable — is typically 45–90 minutes. A 60-minute SLA targets the midpoint of this window. REACH flood maps arrive weeks after acquisition, well beyond any evacuation window.

**Why SMS?**
Village chiefs in remote Greater Upper Nile have mobile coverage but no reliable internet. SMS works on any GSM handset, requires no data connection, and costs fractions of a cent per message. The 160-character alert conveys all operationally critical information in a single message.

**Why SQLite?**
The pipeline produces at most one event per 6-day satellite pass. SQLite is more than sufficient, requires zero configuration, and produces a single portable file. This eliminates operational complexity in a resource-constrained humanitarian environment.

**Why Streamlit?**
Allows a full operational dashboard to be built and maintained entirely in Python without a separate frontend framework. Correct trade-off between capability and maintainability for a research prototype.

**Why a demo data fallback?**
The dashboard auto-detects whether real pipeline data exists and falls back to seed data if not. This allows the dashboard to be demonstrated and evaluated independently of whether the full pipeline has been run — critical for academic assessment.

---

## 12. Limitations & Future Work

| Limitation | Impact |
|---|---|
| 6-day Sentinel-1 revisit cycle | Cannot detect flooding that begins and recedes between passes |
| SNAP GPT ~8 min/scene | Reduces available buffer within 60-min SLA on slow hardware |
| ML classifier requires labelled training data | Detection quality depends on availability of validated masks |
| Admin panel is a prototype | Approve/reject buttons do not write to an authentication database |
| Static SMS recipient list | No self-service registration for village chiefs |

**Future work:** Sentinel-1 burst processing (~2 min/scene), MODIS/Landsat fusion for daily monitoring, WhatsApp delivery channel, field validation mobile app, automatic model retraining.

---

## 13. Acknowledgements

I am profoundly grateful to the Almighty for the strength, wisdom, and resilience provided throughout the completion of this project.

My deepest appreciation is extended to my supervisor, **Prof. Paul Okanda**, whose expert guidance and constructive feedback were instrumental in defining the technical direction and quality of the SuddWatch system.

I would also like to recognize the faculty and staff within the School of Science and Technology at USIU-Africa, my classmates and colleagues for insightful discussions, and my family for their unwavering love, prayers, and support.

### Data Sources

| Data | Source | Licence |
|---|---|---|
| Sentinel-1 IW GRD SAR imagery | ESA Copernicus Data Space | Free, open access |
| WorldPop 2020 population grid | WorldPop / University of Southampton | CC BY 4.0 |
| OpenStreetMap roads, villages, health facilities | OpenStreetMap contributors | ODbL |
| SRTM 3Sec DEM | NASA / USGS (via ESA SNAP) | Public domain |

---

*SuddWatch — SWE3090 Software Project 1 · USIU-Africa · Summer Semester 2026*  
*Madut Chan (671336) · Supervised by Prof. Paul Okanda*
