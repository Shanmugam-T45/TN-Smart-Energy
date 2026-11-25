# TN SMART ENERGY

TN Smart Energy is an advisory smart-energy and power-reliability demonstration application. It does not claim a live Tamil Nadu utility connection, provide verified fault conclusions, control electrical equipment, or guarantee uninterrupted power.

## Project structure

- `frontend/`: React, TypeScript and Vite responsive dashboard.
- `backend/`: FastAPI calculations and CSV validation API.
- `sample-data/`: Clearly identified simulated meter records.
- `docs/`: Additional project documentation.
- `backend/Dockerfile` and `docker-compose.yml`: Local/container deployment.
- `render.yaml`: Read-only public demo deployment blueprint.

## Run locally

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Backend:

```powershell
cd backend
C:\<python-path>\python.exe -m pip install -r requirements.txt
C:\<python-path>\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:5173`. API documentation is available at `http://localhost:8000/docs`.

## Uploading meter readings

Use the **Upload data** button in the dashboard and choose a UTF-8 CSV file no larger than 10 MB. The required columns are:

```csv
meter_id,timestamp,energy_kwh
METER-001,2026-11-22T00:00:00Z,12.4
```

Timestamps must include a timezone (`Z` or an offset such as `+05:30`). Optional columns are `voltage`, `current_a`, `active_power_kw`, `power_factor`, `feeder_id`, `transformer_id`, `consumer_category`, `sanctioned_load_kw`, and `transformer_rated_kva`. Ratings imported from CSV initialize the meter/transformer settings; settings can also be edited in the app. Use **CSV template** in the app to download a simulated example.

Valid rows are saved in SQLite at `backend/data/tn_smart_energy.sqlite3` by default. Set `TN_SMART_ENERGY_DB_PATH` to change this path. Partial uploads save valid rows and report rejected rows; an upload with no valid rows is not saved. Select an uploaded dataset in the top bar to see its energy, demand (when `active_power_kw` exists), meter counts and voltage screening on the dashboard. Open **Household meters** to inspect meter histories and configure sanctioned-load thresholds. Uploaded records are user-provided and are not independently verified.

## Connected analytics modules

- **Household meters:** meter-level reading history and advisory screening of the latest `active_power_kw` against the configured sanctioned load.
- **Transformers:** estimates apparent power as `active_power_kw / power_factor` and compares it with an editable rated kVA capacity and configurable screening thresholds. A complete power-factor reading is needed for every meter grouped under the transformer.
- **Demand forecasting:** a scikit-learn `RandomForestRegressor` trained on uploaded aggregate demand, using hour-of-day, day-of-week and elapsed-time features. It requires at least 24 distinct demand timestamps; a chronological holdout MAE is shown when there are at least 40. It is an estimate, not live-grid or dispatch data.
- **Conservation simulator:** uses the selected dataset's measured maximum demand as the baseline and estimates a peak reduction from user-selected shiftable load. Energy savings are shown only when actual kWh reduction is supplied.
- **Voltage analysis:** reports uploaded voltage statistics by feeder; readings below 207 V or above 253 V are screening flags only.
- **Outages:** users can manually log feeder outage times and notes. Events are not automatically detected from meter data or live telemetry.
- **Distribution losses:** users configure one upstream input meter and one or more downstream output meters per feeder. The app compares their summed uploaded kWh; meaningful comparisons require matching time intervals and a correctly configured boundary.
- **Reports:** the Reports page generates a downloadable PDF summary of the selected dataset, voltage screens, transformer screens, manually logged outages and configured feeder balances.

SQLite schema migrations are additive and create supporting profile, asset, outage and feeder-boundary tables; they do not delete uploaded dataset or meter-reading rows. Authentication, live utility integration, automatic outage detection, equipment control and the locality map remain unimplemented.

## Publish a safe public demo

The Render Blueprint deploys the existing frontend and FastAPI backend together from one origin. It enables read-only public-demo mode, seeds a separate SQLite database with synthetic readings, and rejects dataset uploads and saved profile, outage, or feeder-boundary changes. It never uses the normal `TN_SMART_ENERGY_DB_PATH` database. Do not expose a normal local deployment publicly: it has no authentication and may contain private uploaded data.

To publish it, push this project to a Git provider, sign in to Render, choose **New → Blueprint**, and connect the repository containing `render.yaml`. Review and apply the blueprint. Render builds the Docker image and displays the generated public `onrender.com` URL when deployment succeeds. The public URL cannot be assigned until this is deployed from an account you control. The free instance may sleep when idle, and its temporary demo database may be recreated after a restart; the synthetic dataset is reseeded automatically.

## Validation

```powershell
cd frontend
npm run build

cd ..\backend
C:\<python-path>\python.exe -m pytest -q
```
