# SuddWatch — Changes from the November 2026 review

This file lists every problem found when the project was reviewed end to end,
what caused it, and how it was fixed. Originals of all changed files were
saved in `_backup_before_fixes/` (and git history has them too).

Test suite after the fixes: **242 passed, 5 skipped** (the 5 are live
Copernicus/Twilio/Gmail tests, run with `pytest -m integration`).

---

## 1. Flood detection (`src/flood_detection.py`, new `src/raster_utils.py`)

| # | Problem | Effect | Fix |
|---|---|---|---|
| 1.1 | TPI was computed as `dem − (outer_mean − inner_mean)`. The two means almost cancel, so "TPI" was really the raw elevation (~400 m), always above the 0.5 threshold. | **Every flood pixel was deleted** whenever the DEM was present. The old logs show `Initial flood mask: 3500 pixels` → `TPI filtering removed 3500` → `Final flood mask: 0 pixels`. | TPI = elevation − mean elevation of the ring between the inner and outer windows (computed with masked sums). Regression tests: flat floodplain keeps its flood; a 10 m mound is removed. |
| 1.2 | DEM, baseline and exclusion masks were read with `read(out_shape=scene_shape)`, which squeezes the **whole file** into the scene's pixel count instead of cutting out the scene's area. | Overlays compared unrelated places. | `raster_utils.align_to_grid()` and `compute_tpi_on_grid()` reproject by location (`rasterio.warp.reproject`). The DEM is read only for the scene area, at a coarse enough resolution for kilometre-scale windows. |
| 1.3 | Flood area assumed square pixels of `(deg × 111 km)²`. | Small error at 6–10 °N (longitude degrees are shorter). | Per-row pixel area using each row's latitude (`mask_area_ha`). |
| 1.4 | Otsu and the GMM were fitted to every pixel. | A full scene (~400 M pixels) would take a very long time in the GMM. | Thresholds are estimated from a reproducible random sample of 1 M pixels. |
| 1.5 | Comments claimed `min(Otsu, GMM)` is "more inclusive". | Misleading documentation. | Corrected: the lower threshold is the *stricter* one; the relaxation factor (< 1) makes detection more inclusive. |
| 1.6 | No-data pixels were saved as 0 ("dry"). | Edges of the swath counted as dry land. | No-data pixels are saved as 255 (the mask's no-data value). |
| 1.7 | A configured dry-season baseline was never loaded by the pipeline. | Change detection never ran. | `FloodDetector` loads `config.baseline_path` (`DRY_SEASON_BASELINE_PATH`) automatically if the file exists. |

## 2. Risk assessment (`src/risk_assessment.py`)

| # | Problem | Effect | Fix |
|---|---|---|---|
| 2.1 | Villages, roads and clinics were matched against the mask's **bounding box**, not the flooded pixels. | Every road in the scene rectangle was reported "inaccessible"; every village in it was listed (20 %/45 %/90 %). | Each point is checked against the actual flood pixels (flooded → 90 %, within `NEAR_FLOOD_BUFFER_M` → 50 %, otherwise not listed). Roads are densified and sampled pixel by pixel; flooded length is reported. |
| 2.2 | WorldPop (people per 1 km cell) was resampled *down* to the 10 m mask grid and summed. | Each person counted roughly 10,000 times; the raster was also stretched (see 1.2). | Flood fraction is averaged *up* onto the WorldPop grid; affected = Σ people × flooded fraction. Test: a fully flooded cell of 100 people gives ~100. |
| 2.3 | `estimated_population` per village was always 0. | Village tables showed 0 people. | Population of the village's WorldPop 1 km cell. |
| 2.4 | Village state was read from an `is_in` field that the OSM file does not have. | State always "South Sudan". | Optional state-boundary file (`data/admin/south_sudan_states.geojson`); otherwise "Unknown". |
| 2.5 | Missing OSM names became the text "nan". | "nan" villages. | Readable fallbacks ("Unnamed settlement", …). |

## 3. Pipeline, database, alerts (`src/pipeline.py`, `src/database.py`, `src/alerts.py`, `run_pipeline.py`)

| # | Problem | Effect | Fix |
|---|---|---|---|
| 3.1 | IoU returned a hard-coded **0.71** when no reference mask existed (always). | Reported IoU was invented. | Returns `None` ("not validated"); real IoU is computed when `data/reference_masks/<scene>_reference.tif` exists (aligned to the prediction first). |
| 3.2 | "Latency" was the sum of processing times, not satellite pass → alert. | The 60-minute SLA was not actually measured. | Sensing time comes from the Copernicus metadata (or the file name). Stored: `processing_seconds` and end-to-end `total_latency_seconds`. |
| 3.3 | `update_event()` ignored `flood_extent_ha` / `iou_score` (they live in `flood_masks`) and overwrote unrelated columns with NULL. | Results were silently lost. | Partial updates of allowed columns only; flood results are stored in `flood_masks`. |
| 3.4 | The pipeline passed the **scene name** as `event_id` to the alert module. | Alert rows didn't link to their event. | Integer `event_id` for the database; readable label `EVT-YYYY-NNN` in messages. |
| 3.5 | Processing logs were written with key `stage` but the table expects `stage_name`. | Stage names stored as NULL. | Fixed (both keys accepted). |
| 3.6 | Road/clinic rows were written with keys that don't exist in the table. | Type, length and status were NULL. | Correct fields, plus new `flooded_length_km`. |
| 3.7 | Alert success rate counted status `sent`, but alerts were saved as `delivered`. | Success rate always 0 %. | Status is now `sent` (accepted by Twilio/SMTP — honest wording) and the metric counts it. |
| 3.8 | SMS/email linked to `http://localhost:8501`. | Useless on a recipient's phone. | Link only included if `DASHBOARD_URL` is set. |
| 3.9 | Alert thresholds were read with `getattr(config, …, default)` but never defined in `Config`. | Could not be changed. | `ALERT_FLOOD_THRESHOLD_HA`, `ALERT_POPULATION_THRESHOLD` in `.env`, or from the dashboard. |
| 3.10 | `preprocess()` returning `None` on SNAP failure was passed on to detection. | Confusing "Input image not found: None" errors. | Clear "SNAP preprocessing failed" error; the event is marked failed with the message. |
| 3.11 | No way to (re)process a specific scene, or to test without sending messages. | A downloaded-but-crashed scene could never be processed again. | `run_pipeline.py --scene FILE…` and `--no-alerts` (messages built and logged as `skipped`). Preprocessed `.tif` inputs skip SNAP. |
| 3.12 | `FloodPipeline()` re-configured logging, replacing `run_pipeline.py`'s log file handler. | Daily log files could miss pipeline output. | Logging is only configured if nothing else did. |
| 3.13 | Missing WorldPop crashed pipeline start-up. | — | Warning; population reported as 0. |
| 3.14 | Schema changes would break existing databases. | — | Missing columns are added automatically (`ALTER TABLE`). |

## 4. Preprocessing (`src/preprocessing.py`)

| # | Problem | Fix |
|---|---|---|
| 4.1 | README listed Thermal Noise Removal, but the SNAP graph did not include it. | `ThermalNoiseRemoval` node added between orbit correction and calibration. *(Graph validated by tests; not run against SNAP in this review because SNAP was not available — please run one real scene.)* |
| 4.2 | SNAP path was hard-coded. | `SNAP_GPT_PATH` in `.env`. |

## 5. Configuration and tests (`src/config.py`, `tests/`)

| # | Problem | Effect | Fix |
|---|---|---|---|
| 5.1 | Tests used the real `Config()`. | Tests wrote 15 fake events into `data/database/suddwatch.db` and overwrote `data/downloaded_scenes.json` with fake scene IDs; tests depended on the developer's `.env`. | Every test runs in a temporary project folder (`tests/conftest.py`). `scripts/clean_test_data.py` removes the old leftovers (with backup). |
| 5.2 | `Config` read `.env` at import time into `os.environ`. | `test_config.py` (12 tests) failed; settings leaked between projects. | Values are resolved when `Config()` is created: real environment → `.env` → defaults. |
| 5.3 | Preprocessing tests required SNAP to be installed. | 31 errors on machines without SNAP. | A fake `gpt` is used (GPT itself was already mocked). |
| 5.4 | Risk-assessment `assess()` tests didn't create the WorldPop file they load. | 4 failures. | Fixed fixtures. |
| 5.5 | A database test used a fixed date range ending 2025-12-31. | Started failing in 2026. | Dates relative to "now". |
| 5.6 | Live-service tests ran by default. | Failed without network/credentials. | Skipped unless `pytest -m integration`. |
| 5.7 | `src/database.py` self-test wrote to the real database. | Source of the `TEST_SCENE_001` events. | Uses a temporary database. |
| — | New tests | — | `test_flood_detection.py`, `test_ml_flood_detection.py`, `test_end_to_end.py`, `test_dashboard_backend.py`, and regression tests in the existing files. |

## 6. ML detector (`src/ml_flood_detection.py`)

| # | Problem | Fix |
|---|---|---|
| 6.1 | Model saved under `data/models/` while config said `models/`. | Uses `config.ml_model_path` (falls back to the old location if only that exists). |
| 6.2 | Area used degrees² as m² (≈ 0 ha). | True pixel areas. |
| 6.3 | Features for a whole scene at once (~17 GB for a full scene). | Prediction in 512-row tiles with a halo; identical features, bounded memory. |
| 6.4 | Masks written next to the input instead of `data/flood_masks/`. | Fixed. |
| 6.5 | Not selectable. | `DETECTION_METHOD=random_forest` (experimental). Note: the shipped model was trained on synthetic data only. |

## 7. Dashboard (`dashboard/`)

| # | Problem | Effect | Fix |
|---|---|---|---|
| 7.1 | `db.py` checked `events.iou_score`/`events.flood_extent_ha`, columns that don't exist. | The query always failed, so **the dashboard always showed demo data**, even after real runs. | Checks for a completed event with a flood mask; `data_mode()` reports real/demo. |
| 7.2 | Villages, roads, clinics, alerts, state breakdown, monthly trend always read demo tables. | Real results never shown. | Real-mode adapters for every function, with the same field names the pages expect. |
| 7.3 | Many numbers on Home, History and Performance were typed into the code (e.g. "47 events", "IoU 0.71", "99.2 % uptime", "Cloud cover 0.12"). | Looked like measurements but weren't. | Computed from the database (or from the demo data in demo mode). Cloud cover removed (radar is unaffected by cloud). |
| 7.4 | Admin buttons only showed a success message (save recipients, save thresholds, test alert, run pipeline, apply calibration, approve/reject users). | Nothing actually happened. | `admin_actions.py`: recipients → `.env`; thresholds/calibration → `config/runtime_settings.json` (read by `Config`); real test SMS/email; pipeline started in the background with live log; approve/reject in `auth.db`. |
| 7.5 | Sign-in used plain-text passwords in the code; `auth.db` existed but was unused; access requests were discarded. | — | `auth.py` with salted PBKDF2 hashes (old SHA-256 hashes upgraded on login); Request Access stores requests for Admin review. |
| 7.6 | Audit log, stage status, service status and storage were fixed lists. | — | Built from the database, the audit file, configuration checks and real folder sizes. |
| 7.7 | Exports produced placeholder files (GeoJSON without geometry, text instead of GeoTIFF/Shapefile). | — | `exporter.py`: flood polygons + villages + clinics (GeoJSON), the real mask (GeoTIFF), Shapefile ZIP, villages CSV, text report. |
| 7.8 | The demo database was never created automatically. | A fresh checkout crashed with "no such table". | Created on first use. |
| 7.9 | No indication of demo data. | — | Yellow **DEMO DATA** banner. |
| 7.10 | ~480 lines of an unreachable duplicate Admin page. | — | Removed (old `Admin` links go to User Management). |

## 8. Documentation

* `README.md` rewritten to describe what the code actually does (operators, stage order, risk method, latency definitions, honest evaluation status, limitations).
* `.env.example` lists every setting; `CRON_SETUP.md` corrected (`COPERNICUS_USER`, personal numbers removed, new troubleshooting rows).
