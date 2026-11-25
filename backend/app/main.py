from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from contextlib import contextmanager
import csv
import io
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

app = FastAPI(
    title="TN Smart Energy API",
    version="0.1.0",
    description="Advisory smart-energy analysis API. Data quality and source labels must be preserved.",
)

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PUBLIC_DEMO_FILENAME = "PUBLIC_DEMO_simulated_readings.csv"
LOW_VOLTAGE_SCREEN_V = 207.0
HIGH_VOLTAGE_SCREEN_V = 253.0
REQUIRED_METER_COLUMNS = {"meter_id", "timestamp", "energy_kwh"}
DATABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    accepted_rows INTEGER NOT NULL,
    rejected_rows INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS meter_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    meter_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    energy_kwh REAL NOT NULL,
    voltage REAL,
    current_a REAL,
    active_power_kw REAL,
    power_factor REAL,
    feeder_id TEXT,
    transformer_id TEXT,
    consumer_category TEXT,
    UNIQUE(dataset_id, meter_id, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_meter_readings_dataset_timestamp
    ON meter_readings(dataset_id, timestamp);
"""


def apply_migrations(connection: sqlite3.Connection) -> None:
    applied_versions = {
        row["version"]
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    if 1 not in applied_versions:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meter_profiles (
                    meter_id TEXT PRIMARY KEY,
                    sanctioned_load_kw REAL CHECK(sanctioned_load_kw IS NULL OR sanctioned_load_kw > 0),
                    consumer_category TEXT,
                    locality TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transformer_assets (
                    transformer_id TEXT PRIMARY KEY,
                    feeder_id TEXT,
                    location TEXT,
                    rated_capacity_kva REAL CHECK(rated_capacity_kva IS NULL OR rated_capacity_kva > 0),
                    high_loading_threshold_percent REAL NOT NULL DEFAULT 70
                        CHECK(high_loading_threshold_percent >= 0 AND high_loading_threshold_percent <= 100),
                    exceedance_threshold_percent REAL NOT NULL DEFAULT 90
                        CHECK(exceedance_threshold_percent >= 0 AND exceedance_threshold_percent <= 200),
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (1, datetime.now(timezone.utc).isoformat()),
            )
    if 2 not in applied_versions:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    feeder_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    cause TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_outage_events_dataset_started
                    ON outage_events(dataset_id, started_at);
                CREATE TABLE IF NOT EXISTS feeder_meter_roles (
                    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                    feeder_id TEXT NOT NULL,
                    meter_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('input', 'output')),
                    PRIMARY KEY(dataset_id, feeder_id, meter_id)
                );
                CREATE INDEX IF NOT EXISTS idx_feeder_meter_roles_lookup
                    ON feeder_meter_roles(dataset_id, feeder_id, role);
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (2, datetime.now(timezone.utc).isoformat()),
            )


@contextmanager
def database_connection() -> Iterator[sqlite3.Connection]:
    private_path = Path(
        os.environ.get(
            "TN_SMART_ENERGY_DB_PATH",
            str(Path(__file__).resolve().parents[1] / "data" / "tn_smart_energy.sqlite3"),
        )
    )
    if is_public_demo_mode():
        configured_path = os.environ.get("PUBLIC_DEMO_DB_PATH")
        database_path = (
            Path(configured_path)
            if configured_path
            else Path(tempfile.gettempdir()) / "tn_smart_energy_public_demo.sqlite3"
        )
        if database_path.resolve() == private_path.resolve():
            raise RuntimeError("Public demo database must not be the normal application database.")
    else:
        database_path = private_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if is_public_demo_mode():
        validate_public_demo_database(database_path)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(DATABASE_SCHEMA)
        apply_migrations(connection)
        with connection:
            if is_public_demo_mode():
                seed_public_demo_dataset(connection)
            yield connection
    finally:
        connection.close()


def validate_public_demo_database(database_path: Path) -> None:
    if not database_path.exists() or database_path.stat().st_size == 0:
        return
    allowed_tables = {
        "datasets",
        "feeder_meter_roles",
        "meter_profiles",
        "meter_readings",
        "outage_events",
        "schema_migrations",
        "transformer_assets",
    }
    try:
        with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            if not tables.issubset(allowed_tables):
                raise RuntimeError("Public demo database contains unrecognized tables.")
            if "datasets" not in tables:
                return
            datasets = connection.execute("SELECT id, filename FROM datasets").fetchall()
            if not datasets:
                return
            if len(datasets) != 1 or datasets[0][1] != PUBLIC_DEMO_FILENAME:
                raise RuntimeError(
                    "Public demo mode refuses to serve a database containing non-demo datasets."
                )
            if "meter_readings" not in tables:
                raise RuntimeError("Public demo database is missing its synthetic readings.")
            counts = connection.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT meter_id),
                       SUM(CASE WHEN meter_id NOT LIKE 'DEMO-%' THEN 1 ELSE 0 END)
                FROM meter_readings WHERE dataset_id = ?
                """,
                (datasets[0][0],),
            ).fetchone()
            if counts != (192, 4, 0):
                raise RuntimeError("Public demo database does not contain only the seeded sample.")
    except sqlite3.DatabaseError as exc:
        raise RuntimeError("Public demo database is not a valid isolated demo database.") from exc


def is_public_demo_mode() -> bool:
    return os.environ.get("PUBLIC_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def require_writable_mode() -> None:
    if is_public_demo_mode():
        raise HTTPException(
            status_code=403,
            detail="This public demonstration is read-only; data changes are disabled.",
        )


def seed_public_demo_dataset(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
    existing = connection.execute("SELECT id, filename FROM datasets").fetchall()
    if existing:
        if len(existing) != 1 or existing[0]["filename"] != PUBLIC_DEMO_FILENAME:
            raise RuntimeError(
                "Public demo mode refuses to serve a database containing non-demo datasets."
            )
        reading_count = connection.execute(
            "SELECT COUNT(*) FROM meter_readings WHERE dataset_id = ?",
            (existing[0]["id"],),
        ).fetchone()[0]
        if reading_count != 192:
            raise RuntimeError("Public demo database does not contain only the seeded sample.")
        return

    uploaded_at = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO datasets(filename, uploaded_at, accepted_rows, rejected_rows)
        VALUES (?, ?, ?, 0)
        """,
        (PUBLIC_DEMO_FILENAME, uploaded_at, 48 * 4),
    )
    dataset_id = cursor.lastrowid
    meter_config = {
        "DEMO-IN-F1": ("F-DEMO-1", "T-DEMO-1", 35.0),
        "DEMO-OUT-F1": ("F-DEMO-1", "T-DEMO-1", 30.0),
        "DEMO-IN-F2": ("F-DEMO-2", "T-DEMO-2", 25.0),
        "DEMO-OUT-F2": ("F-DEMO-2", "T-DEMO-2", 22.0),
    }
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=47)
    readings = []
    for hour in range(48):
        timestamp = (start + timedelta(hours=hour)).isoformat()
        daily_hour = hour % 24
        wave = math.sin(2 * math.pi * (daily_hour - 8) / 24)
        powers = {
            "DEMO-IN-F1": 24 + 5 * wave,
            "DEMO-OUT-F1": 22 + 4.4 * wave,
            "DEMO-IN-F2": 17 + 4 * wave,
            "DEMO-OUT-F2": 15.5 + 3.4 * wave,
        }
        for meter_id, active_power in powers.items():
            feeder_id, transformer_id, _ = meter_config[meter_id]
            voltage = 230 + 4 * math.sin(2 * math.pi * daily_hour / 24)
            if meter_id == "DEMO-OUT-F1" and daily_hour == 8:
                voltage = 205
            elif meter_id == "DEMO-OUT-F2" and daily_hour == 18:
                voltage = 255
            readings.append(
                (
                    dataset_id,
                    meter_id,
                    timestamp,
                    round(active_power, 3),
                    round(voltage, 2),
                    round(active_power, 3),
                    0.9,
                    feeder_id,
                    transformer_id,
                    "simulated_household",
                )
            )
    connection.executemany(
        """
        INSERT INTO meter_readings(
            dataset_id, meter_id, timestamp, energy_kwh, voltage, active_power_kw,
            power_factor, feeder_id, transformer_id, consumer_category
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        readings,
    )
    for meter_id, (feeder_id, transformer_id, sanctioned_load_kw) in meter_config.items():
        connection.execute(
            """
            INSERT INTO meter_profiles(
                meter_id, sanctioned_load_kw, consumer_category, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (meter_id, sanctioned_load_kw, "simulated_household", uploaded_at),
        )
    for transformer_id, feeder_id, capacity in (
        ("T-DEMO-1", "F-DEMO-1", 100.0),
        ("T-DEMO-2", "F-DEMO-2", 80.0),
    ):
        connection.execute(
            """
            INSERT INTO transformer_assets(
                transformer_id, feeder_id, location, rated_capacity_kva, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (transformer_id, feeder_id, "Simulated service area", capacity, uploaded_at),
        )
    connection.executemany(
        """
        INSERT INTO feeder_meter_roles(dataset_id, feeder_id, meter_id, role)
        VALUES (?, ?, ?, ?)
        """,
        [
            (dataset_id, "F-DEMO-1", "DEMO-IN-F1", "input"),
            (dataset_id, "F-DEMO-1", "DEMO-OUT-F1", "output"),
            (dataset_id, "F-DEMO-2", "DEMO-IN-F2", "input"),
            (dataset_id, "F-DEMO-2", "DEMO-OUT-F2", "output"),
        ],
    )


class ConservationInput(BaseModel):
    original_peak_kw: float = Field(gt=0)
    shiftable_load_kw: float = Field(ge=0)
    actual_reduction_kwh: float | None = Field(default=None, ge=0)


class TransformerInput(BaseModel):
    measured_kva: float = Field(ge=0)
    rated_kva: float = Field(gt=0)
    high_loading_threshold: float = Field(default=70, ge=0, le=100)
    exceedance_threshold: float = Field(default=90, ge=0, le=200)


class VoltageInput(BaseModel):
    voltage: float = Field(gt=0)
    nominal_voltage: float = Field(default=230, gt=0)
    low_threshold: float = Field(default=207, gt=0)


class LossInput(BaseModel):
    input_kwh: float = Field(ge=0)
    output_kwh: float = Field(ge=0)


class MeterProfileInput(BaseModel):
    sanctioned_load_kw: float = Field(gt=0)
    consumer_category: str | None = None
    locality: str | None = None


class TransformerProfileInput(BaseModel):
    rated_capacity_kva: float = Field(gt=0)
    feeder_id: str | None = None
    location: str | None = None
    high_loading_threshold_percent: float = Field(default=70, ge=0, le=100)
    exceedance_threshold_percent: float = Field(default=90, ge=0, le=200)


class OutageEventInput(BaseModel):
    feeder_id: str = Field(min_length=1)
    started_at: str = Field(min_length=1)
    ended_at: str | None = None
    cause: str = Field(default="Unspecified", min_length=1)
    notes: str | None = None


class FeederMeterRolesInput(BaseModel):
    input_meter_id: str = Field(min_length=1)
    output_meter_ids: list[str] = Field(min_length=1)


@app.get("/api/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/dashboard")
def dashboard():
    return {
        "data_source": "simulated_demonstration",
        "warning": "Do not interpret these values as live Tamil Nadu utility readings.",
        "total_energy_kwh": 6482,
        "current_demand_kw": 78.4,
        "maximum_demand_kw": 96.8,
        "average_demand_kw": 68.1,
        "transformer_loading_percent": 68.3,
        "low_voltage_reading_count": 12,
        "uploaded_meter_readings": 156,
    }


def dataset_metadata(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "uploaded_at": row["uploaded_at"],
        "accepted_rows": row["accepted_rows"],
        "rejected_rows": row["rejected_rows"],
    }


@app.get("/api/datasets")
def list_datasets():
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT id, filename, uploaded_at, accepted_rows, rejected_rows "
            "FROM datasets ORDER BY id DESC"
        ).fetchall()
    return [dataset_metadata(row) for row in rows]


@app.get("/api/datasets/{dataset_id}/meters")
def list_dataset_meters(dataset_id: int):
    with database_connection() as connection:
        exists = connection.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        rows = connection.execute(
            """
            SELECT r.meter_id,
                   COUNT(*) AS record_count,
                   SUM(r.energy_kwh) AS total_energy_kwh,
                   MAX(r.timestamp) AS latest_timestamp,
                   p.sanctioned_load_kw,
                   p.consumer_category,
                   p.locality,
                   (
                       SELECT active_power_kw FROM meter_readings latest
                       WHERE latest.dataset_id = r.dataset_id AND latest.meter_id = r.meter_id
                       ORDER BY latest.timestamp DESC LIMIT 1
                   ) AS latest_active_power_kw,
                   (
                       SELECT voltage FROM meter_readings latest
                       WHERE latest.dataset_id = r.dataset_id AND latest.meter_id = r.meter_id
                       ORDER BY latest.timestamp DESC LIMIT 1
                   ) AS latest_voltage
            FROM meter_readings r
            LEFT JOIN meter_profiles p ON p.meter_id = r.meter_id
            WHERE r.dataset_id = ?
            GROUP BY r.meter_id, p.sanctioned_load_kw, p.consumer_category, p.locality
            ORDER BY r.meter_id
            """,
            (dataset_id,),
        ).fetchall()

    meters = []
    for row in rows:
        sanctioned_load = row["sanctioned_load_kw"]
        latest_power = row["latest_active_power_kw"]
        if sanctioned_load is None:
            alert_status = "sanctioned_load_not_configured"
        elif latest_power is None:
            alert_status = "active_power_not_available"
        elif latest_power >= sanctioned_load:
            alert_status = "at_or_above_sanctioned_load"
        else:
            alert_status = "within_sanctioned_load"
        meters.append(
            {
                "meter_id": row["meter_id"],
                "record_count": row["record_count"],
                "total_energy_kwh": round(row["total_energy_kwh"], 3),
                "latest_timestamp": row["latest_timestamp"],
                "latest_active_power_kw": latest_power,
                "latest_voltage": row["latest_voltage"],
                "sanctioned_load_kw": sanctioned_load,
                "consumer_category": row["consumer_category"],
                "locality": row["locality"],
                "alert_status": alert_status,
            }
        )
    return {"dataset_id": dataset_id, "meters": meters}


@app.get("/api/datasets/{dataset_id}/meters/{meter_id}")
def get_dataset_meter(dataset_id: int, meter_id: str):
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        profile = connection.execute(
            "SELECT meter_id, sanctioned_load_kw, consumer_category, locality, updated_at "
            "FROM meter_profiles WHERE meter_id = ?",
            (meter_id,),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT timestamp, energy_kwh, voltage, current_a, active_power_kw, power_factor
            FROM meter_readings WHERE dataset_id = ? AND meter_id = ?
            ORDER BY timestamp DESC LIMIT 168
            """,
            (dataset_id, meter_id),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Meter not found in this dataset.")
    return {
        "dataset_id": dataset_id,
        "meter_id": meter_id,
        "profile": dict(profile) if profile else None,
        "readings": [dict(row) for row in reversed(rows)],
    }


@app.put("/api/meters/{meter_id}/profile")
def save_meter_profile(meter_id: str, payload: MeterProfileInput):
    require_writable_mode()
    if not meter_id.strip():
        raise HTTPException(status_code=422, detail="meter_id must not be empty.")
    updated_at = datetime.now(timezone.utc).isoformat()
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO meter_profiles(
                meter_id, sanctioned_load_kw, consumer_category, locality, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(meter_id) DO UPDATE SET
                sanctioned_load_kw = excluded.sanctioned_load_kw,
                consumer_category = COALESCE(excluded.consumer_category, meter_profiles.consumer_category),
                locality = COALESCE(excluded.locality, meter_profiles.locality),
                updated_at = excluded.updated_at
            """,
            (
                meter_id.strip(),
                payload.sanctioned_load_kw,
                payload.consumer_category,
                payload.locality,
                updated_at,
            ),
        )
        profile = connection.execute(
            "SELECT meter_id, sanctioned_load_kw, consumer_category, locality, updated_at "
            "FROM meter_profiles WHERE meter_id = ?",
            (meter_id.strip(),),
        ).fetchone()
    return dict(profile)


def transformer_loading_screen(
    measured_kva: float,
    rated_kva: float,
    high_threshold: float,
    exceedance_threshold: float,
) -> tuple[float, str, str]:
    loading = measured_kva / rated_kva * 100
    if loading >= exceedance_threshold:
        status = "potential_capacity_exceedance"
        recommendation = "Request qualified utility review and verify the operating conditions."
    elif loading >= high_threshold:
        status = "high_loading"
        recommendation = "Investigate flexible demand and verify phase balance."
    else:
        status = "normal"
        recommendation = "Continue normal monitoring."
    return round(loading, 3), status, recommendation


@app.get("/api/datasets/{dataset_id}/transformers")
def list_dataset_transformers(dataset_id: int):
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        rows = connection.execute(
            """
            WITH latest_transformer_times AS (
                    SELECT transformer_id, MAX(timestamp) AS latest_timestamp
                    FROM meter_readings
                    WHERE dataset_id = ?
                      AND transformer_id IS NOT NULL
                    GROUP BY transformer_id
            )
            SELECT r.meter_id, r.timestamp, r.transformer_id, r.feeder_id,
                   r.active_power_kw, r.power_factor,
                   a.feeder_id AS asset_feeder_id, a.location,
                   a.rated_capacity_kva, a.high_loading_threshold_percent,
                   a.exceedance_threshold_percent
            FROM meter_readings r
            JOIN latest_transformer_times latest
              ON latest.transformer_id = r.transformer_id
             AND latest.latest_timestamp = r.timestamp
            LEFT JOIN transformer_assets a ON a.transformer_id = r.transformer_id
            WHERE r.dataset_id = ?
            ORDER BY r.transformer_id, r.meter_id
            """,
            (dataset_id, dataset_id),
        ).fetchall()

    grouped = {}
    for row in rows:
        asset = grouped.setdefault(
            row["transformer_id"],
            {
                "transformer_id": row["transformer_id"],
                "feeder_id": row["asset_feeder_id"] or row["feeder_id"],
                "location": row["location"],
                "rated_capacity_kva": row["rated_capacity_kva"],
                "high_loading_threshold_percent": (
                    row["high_loading_threshold_percent"]
                    if row["high_loading_threshold_percent"] is not None
                    else 70
                ),
                "exceedance_threshold_percent": (
                    row["exceedance_threshold_percent"]
                    if row["exceedance_threshold_percent"] is not None
                    else 90
                ),
                "latest_timestamp": row["timestamp"],
                "meters": [],
                "apparent_power_values": [],
                "active_power_values": [],
            },
        )
        asset["latest_timestamp"] = max(asset["latest_timestamp"], row["timestamp"])
        asset["meters"].append(row["meter_id"])
        asset["active_power_values"].append(row["active_power_kw"])
        if (
            row["active_power_kw"] is not None
            and row["power_factor"] is not None
            and row["power_factor"] > 0
        ):
            asset["apparent_power_values"].append(row["active_power_kw"] / row["power_factor"])

    transformers = []
    for asset in grouped.values():
        meter_count = len(asset["meters"])
        active_values = asset.pop("active_power_values")
        apparent_values = asset.pop("apparent_power_values")
        measured_kw = (
            round(sum(active_values), 3)
            if active_values and all(value is not None for value in active_values)
            else None
        )
        measured_kva = (
            round(sum(apparent_values), 3)
            if len(apparent_values) == meter_count
            else None
        )
        rated_kva = asset["rated_capacity_kva"]
        loading_percent = (
            measured_kva / rated_kva * 100
            if measured_kva is not None and rated_kva is not None
            else None
        )
        if loading_percent is None:
            status = "capacity_or_power_factor_not_available"
            recommendation = "Configure transformer capacity and provide active power with power factor."
        else:
            loading_percent, status, recommendation = transformer_loading_screen(
                measured_kva,
                rated_kva,
                asset["high_loading_threshold_percent"],
                asset["exceedance_threshold_percent"],
            )
        transformers.append(
            {
                "transformer_id": asset["transformer_id"],
                "feeder_id": asset["feeder_id"],
                "location": asset["location"],
                "rated_capacity_kva": rated_kva,
                "high_loading_threshold_percent": asset["high_loading_threshold_percent"],
                "exceedance_threshold_percent": asset["exceedance_threshold_percent"],
                "latest_timestamp": asset["latest_timestamp"],
                "meter_count": meter_count,
                "measured_active_power_kw": measured_kw,
                "measured_apparent_power_kva": measured_kva,
                "loading_percent": loading_percent,
                "status": status,
                "recommendation": recommendation,
            }
        )
    return {"dataset_id": dataset_id, "transformers": transformers}


@app.put("/api/transformers/{transformer_id}/profile")
def save_transformer_profile(transformer_id: str, payload: TransformerProfileInput):
    require_writable_mode()
    if not transformer_id.strip():
        raise HTTPException(status_code=422, detail="transformer_id must not be empty.")
    updated_at = datetime.now(timezone.utc).isoformat()
    with database_connection() as connection:
        connection.execute(
            """
            INSERT INTO transformer_assets(
                transformer_id, feeder_id, location, rated_capacity_kva,
                high_loading_threshold_percent, exceedance_threshold_percent, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transformer_id) DO UPDATE SET
                feeder_id = COALESCE(excluded.feeder_id, transformer_assets.feeder_id),
                location = COALESCE(excluded.location, transformer_assets.location),
                rated_capacity_kva = excluded.rated_capacity_kva,
                high_loading_threshold_percent = excluded.high_loading_threshold_percent,
                exceedance_threshold_percent = excluded.exceedance_threshold_percent,
                updated_at = excluded.updated_at
            """,
            (
                transformer_id.strip(),
                payload.feeder_id,
                payload.location,
                payload.rated_capacity_kva,
                payload.high_loading_threshold_percent,
                payload.exceedance_threshold_percent,
                updated_at,
            ),
        )
        asset = connection.execute(
            """
            SELECT transformer_id, feeder_id, location, rated_capacity_kva,
                   high_loading_threshold_percent, exceedance_threshold_percent, updated_at
            FROM transformer_assets WHERE transformer_id = ?
            """,
            (transformer_id.strip(),),
        ).fetchone()
    return dict(asset)


@app.get("/api/datasets/{dataset_id}/readings")
def get_dataset_readings(dataset_id: int, limit: int = 1000, offset: int = 0):
    if limit < 1 or limit > 5000 or offset < 0:
        raise HTTPException(status_code=422, detail="Limit must be 1–5000 and offset must be non-negative.")
    with database_connection() as connection:
        exists = connection.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        rows = connection.execute(
            "SELECT meter_id, timestamp, energy_kwh, voltage, current_a, active_power_kw, "
            "power_factor, feeder_id, transformer_id, consumer_category "
            "FROM meter_readings WHERE dataset_id = ? ORDER BY timestamp, meter_id LIMIT ? OFFSET ?",
            (dataset_id, limit, offset),
        ).fetchall()
    return {
        "dataset_id": dataset_id,
        "limit": limit,
        "offset": offset,
        "readings": [dict(row) for row in rows],
    }


@app.get("/api/datasets/{dataset_id}/summary")
def get_dataset_summary(dataset_id: int):
    with database_connection() as connection:
        metadata = connection.execute(
            "SELECT id, filename, uploaded_at, accepted_rows, rejected_rows "
            "FROM datasets WHERE id = ?",
            (dataset_id,),
        ).fetchone()
        if not metadata:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        totals = connection.execute(
            """
            SELECT COUNT(*) AS record_count,
                   COUNT(DISTINCT meter_id) AS meter_count,
                   COUNT(DISTINCT feeder_id) AS feeder_count,
                   COUNT(DISTINCT transformer_id) AS transformer_count,
                   COALESCE(SUM(energy_kwh), 0) AS total_energy_kwh,
                   SUM(CASE WHEN voltage < ? THEN 1 ELSE 0 END) AS low_voltage_reading_count
            FROM meter_readings WHERE dataset_id = ?
            """,
            (LOW_VOLTAGE_SCREEN_V, dataset_id),
        ).fetchone()
        demand_stats = connection.execute(
            """
            SELECT AVG(demand_kw) AS average_demand_kw, MAX(demand_kw) AS maximum_demand_kw
            FROM (
                SELECT timestamp, SUM(active_power_kw) AS demand_kw
                FROM meter_readings
                WHERE dataset_id = ? AND active_power_kw IS NOT NULL
                GROUP BY timestamp
            )
            """,
            (dataset_id,),
        ).fetchone()
        demand_rows = connection.execute(
            """
            SELECT timestamp, SUM(active_power_kw) AS demand_kw
            FROM meter_readings
            WHERE dataset_id = ? AND active_power_kw IS NOT NULL
            GROUP BY timestamp ORDER BY timestamp DESC LIMIT 168
            """,
            (dataset_id,),
        ).fetchall()
        consumption_rows = connection.execute(
            """
            SELECT substr(timestamp, 1, 10) AS date, SUM(energy_kwh) AS energy_kwh
            FROM meter_readings WHERE dataset_id = ?
            GROUP BY substr(timestamp, 1, 10) ORDER BY date DESC LIMIT 7
            """,
            (dataset_id,),
        ).fetchall()

    demand_series = [
        {"timestamp": row["timestamp"], "demand_kw": round(row["demand_kw"], 3)}
        for row in reversed(demand_rows)
    ]
    consumption_series = [
        {"date": row["date"], "energy_kwh": round(row["energy_kwh"], 3)}
        for row in reversed(consumption_rows)
    ]
    transformer_loadings = [
        transformer_item["loading_percent"]
        for transformer_item in list_dataset_transformers(dataset_id)["transformers"]
        if transformer_item["loading_percent"] is not None
    ]
    return {
        **dataset_metadata(metadata),
        "data_source": "user_uploaded",
        "record_count": totals["record_count"],
        "meter_count": totals["meter_count"],
        "feeder_count": totals["feeder_count"],
        "transformer_count": totals["transformer_count"],
        "total_energy_kwh": round(totals["total_energy_kwh"], 3),
        "current_demand_kw": demand_series[-1]["demand_kw"] if demand_series else None,
        "maximum_demand_kw": round(demand_stats["maximum_demand_kw"], 3)
        if demand_stats["maximum_demand_kw"] is not None
        else None,
        "maximum_transformer_loading_percent": max(transformer_loadings)
        if transformer_loadings
        else None,
        "average_demand_kw": round(demand_stats["average_demand_kw"], 3)
        if demand_stats["average_demand_kw"] is not None
        else None,
        "low_voltage_reading_count": totals["low_voltage_reading_count"] or 0,
        "low_voltage_threshold_v": LOW_VOLTAGE_SCREEN_V,
        "demand_series": demand_series,
        "consumption_series": consumption_series,
        "limitation": "Uploaded readings are user-provided and are not independently verified.",
    }


@app.get("/api/datasets/{dataset_id}/voltage-analysis")
def get_dataset_voltage_analysis(dataset_id: int):
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        totals = connection.execute(
            """
            SELECT COUNT(*) AS reading_count,
                   AVG(voltage) AS average_voltage,
                   MIN(voltage) AS minimum_voltage,
                   MAX(voltage) AS maximum_voltage,
                   SUM(CASE WHEN voltage < ? THEN 1 ELSE 0 END) AS low_count,
                   SUM(CASE WHEN voltage > ? THEN 1 ELSE 0 END) AS high_count
            FROM meter_readings
            WHERE dataset_id = ? AND voltage IS NOT NULL
            """,
            (LOW_VOLTAGE_SCREEN_V, HIGH_VOLTAGE_SCREEN_V, dataset_id),
        ).fetchone()
        feeders = connection.execute(
            """
            SELECT COALESCE(feeder_id, 'Unassigned') AS feeder_id,
                   COUNT(*) AS reading_count,
                   AVG(voltage) AS average_voltage,
                   MIN(voltage) AS minimum_voltage,
                   MAX(voltage) AS maximum_voltage,
                   SUM(CASE WHEN voltage < ? THEN 1 ELSE 0 END) AS low_count,
                   SUM(CASE WHEN voltage > ? THEN 1 ELSE 0 END) AS high_count
            FROM meter_readings
            WHERE dataset_id = ? AND voltage IS NOT NULL
            GROUP BY COALESCE(feeder_id, 'Unassigned')
            ORDER BY feeder_id
            """,
            (LOW_VOLTAGE_SCREEN_V, HIGH_VOLTAGE_SCREEN_V, dataset_id),
        ).fetchall()
    reading_count = totals["reading_count"]
    low_count = totals["low_count"] or 0
    high_count = totals["high_count"] or 0
    return {
        "dataset_id": dataset_id,
        "voltage_reading_count": reading_count,
        "average_voltage": round(totals["average_voltage"], 3)
        if totals["average_voltage"] is not None
        else None,
        "minimum_voltage": totals["minimum_voltage"],
        "maximum_voltage": totals["maximum_voltage"],
        "low_voltage_count": low_count,
        "high_voltage_count": high_count,
        "within_screen_count": max(0, reading_count - low_count - high_count),
        "low_threshold_v": LOW_VOLTAGE_SCREEN_V,
        "high_threshold_v": HIGH_VOLTAGE_SCREEN_V,
        "feeders": [
            {
                "feeder_id": row["feeder_id"],
                "reading_count": row["reading_count"],
                "average_voltage": round(row["average_voltage"], 3),
                "minimum_voltage": row["minimum_voltage"],
                "maximum_voltage": row["maximum_voltage"],
                "low_voltage_count": row["low_count"] or 0,
                "high_voltage_count": row["high_count"] or 0,
            }
            for row in feeders
        ],
        "limitation": "Voltage thresholds are illustrative screening levels; uploaded records alone do not establish an equipment fault or regulatory violation.",
    }


def parse_utc_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must include a timezone, such as Z or +05:30.",
        )
    return parsed.astimezone(timezone.utc)


@app.get("/api/datasets/{dataset_id}/outages")
def list_dataset_outages(dataset_id: int):
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        rows = connection.execute(
            """
            SELECT id, feeder_id, started_at, ended_at, cause, notes, created_at
            FROM outage_events WHERE dataset_id = ?
            ORDER BY started_at DESC, id DESC
            """,
            (dataset_id,),
        ).fetchall()
    current_time = datetime.now(timezone.utc)
    events = []
    for row in rows:
        started = datetime.fromisoformat(row["started_at"])
        ended = datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else current_time
        events.append(
            {
                **dict(row),
                "duration_minutes": round(max(0.0, (ended - started).total_seconds() / 60), 1),
                "is_ongoing": row["ended_at"] is None,
            }
        )
    return {
        "dataset_id": dataset_id,
        "event_count": len(events),
        "ongoing_count": sum(1 for event in events if event["is_ongoing"]),
        "total_duration_minutes": round(sum(event["duration_minutes"] for event in events), 1),
        "source": "manually_logged",
        "events": events,
        "limitation": "Events are manually recorded; this application does not detect outages from live grid telemetry.",
    }


@app.post("/api/datasets/{dataset_id}/outages", status_code=201)
def create_dataset_outage(dataset_id: int, payload: OutageEventInput):
    require_writable_mode()
    feeder_id = payload.feeder_id.strip()
    if not feeder_id:
        raise HTTPException(status_code=422, detail="feeder_id must not be empty.")
    started_at = parse_utc_timestamp(payload.started_at, "started_at")
    ended_at = parse_utc_timestamp(payload.ended_at, "ended_at") if payload.ended_at else None
    if ended_at is not None and ended_at < started_at:
        raise HTTPException(status_code=422, detail="ended_at must be at or after started_at.")
    created_at = datetime.now(timezone.utc)
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        cursor = connection.execute(
            """
            INSERT INTO outage_events(dataset_id, feeder_id, started_at, ended_at, cause, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                feeder_id,
                started_at.isoformat(),
                ended_at.isoformat() if ended_at else None,
                payload.cause.strip() or "Unspecified",
                payload.notes.strip() if payload.notes else None,
                created_at.isoformat(),
            ),
        )
        event_id = cursor.lastrowid
    return {
        "id": event_id,
        "dataset_id": dataset_id,
        "feeder_id": feeder_id,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat() if ended_at else None,
        "cause": payload.cause.strip() or "Unspecified",
        "notes": payload.notes.strip() if payload.notes else None,
        "created_at": created_at.isoformat(),
        "duration_minutes": round(
            max(0.0, ((ended_at or created_at) - started_at).total_seconds() / 60), 1
        ),
        "is_ongoing": ended_at is None,
    }


def distribution_loss_calculation(input_kwh: float, output_kwh: float) -> dict:
    discrepancy = input_kwh - output_kwh
    percentage = discrepancy / input_kwh * 100 if input_kwh else 0.0
    return {
        "energy_discrepancy_kwh": round(discrepancy, 3),
        "discrepancy_percent": round(percentage, 3),
        "warnings": [
            "Check meter reading intervals",
            "Check meter accuracy",
            "Check unmetered loads",
            "Check auxiliary consumption",
            "Check data gaps",
        ],
        "limitation": "A discrepancy does not by itself confirm technical loss or electricity theft.",
    }


@app.get("/api/datasets/{dataset_id}/loss-analysis")
def get_dataset_loss_analysis(dataset_id: int):
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        meter_rows = connection.execute(
            """
            SELECT feeder_id, meter_id, SUM(energy_kwh) AS energy_kwh
            FROM meter_readings
            WHERE dataset_id = ? AND feeder_id IS NOT NULL
            GROUP BY feeder_id, meter_id
            ORDER BY feeder_id, meter_id
            """,
            (dataset_id,),
        ).fetchall()
        role_rows = connection.execute(
            """
            SELECT feeder_id, meter_id, role
            FROM feeder_meter_roles WHERE dataset_id = ?
            ORDER BY feeder_id, role, meter_id
            """,
            (dataset_id,),
        ).fetchall()

    feeders = {}
    for row in meter_rows:
        feeder = feeders.setdefault(
            row["feeder_id"],
            {
                "feeder_id": row["feeder_id"],
                "meter_ids": [],
                "meter_energy": {},
                "input_meter_id": None,
                "output_meter_ids": [],
            },
        )
        feeder["meter_ids"].append(row["meter_id"])
        feeder["meter_energy"][row["meter_id"]] = row["energy_kwh"] or 0
    for row in role_rows:
        feeder = feeders.setdefault(
            row["feeder_id"],
            {
                "feeder_id": row["feeder_id"],
                "meter_ids": [],
                "meter_energy": {},
                "input_meter_id": None,
                "output_meter_ids": [],
            },
        )
        if row["role"] == "input":
            feeder["input_meter_id"] = row["meter_id"]
        else:
            feeder["output_meter_ids"].append(row["meter_id"])

    results = []
    for feeder in feeders.values():
        input_meter_id = feeder["input_meter_id"]
        output_meter_ids = feeder["output_meter_ids"]
        analysis_ready = input_meter_id is not None and bool(output_meter_ids)
        input_kwh = feeder["meter_energy"].get(input_meter_id, 0) if input_meter_id else 0
        output_kwh = sum(feeder["meter_energy"].get(meter_id, 0) for meter_id in output_meter_ids)
        calculation = distribution_loss_calculation(input_kwh, output_kwh) if analysis_ready else None
        results.append(
            {
                "feeder_id": feeder["feeder_id"],
                "meter_ids": feeder["meter_ids"],
                "input_meter_id": input_meter_id,
                "output_meter_ids": output_meter_ids,
                "analysis_ready": analysis_ready,
                "input_energy_kwh": round(input_kwh, 3) if analysis_ready else None,
                "output_energy_kwh": round(output_kwh, 3) if analysis_ready else None,
                "energy_discrepancy_kwh": calculation["energy_discrepancy_kwh"] if calculation else None,
                "discrepancy_percent": calculation["discrepancy_percent"] if calculation else None,
            }
        )
    return {
        "dataset_id": dataset_id,
        "feeders": results,
        "source": "uploaded_meter_energy_and_user_configured_boundaries",
        "limitation": "Input/output meter roles are user-configured. Comparisons are meaningful only when meters cover the same feeder boundary and time interval.",
    }


@app.put("/api/datasets/{dataset_id}/feeders/{feeder_id}/meter-roles")
def save_feeder_meter_roles(
    dataset_id: int, feeder_id: str, payload: FeederMeterRolesInput
):
    require_writable_mode()
    feeder_id = feeder_id.strip()
    input_meter_id = payload.input_meter_id.strip()
    output_meter_ids = [meter_id.strip() for meter_id in payload.output_meter_ids]
    if not feeder_id or not input_meter_id or any(not meter_id for meter_id in output_meter_ids):
        raise HTTPException(status_code=422, detail="Feeder and meter IDs must not be empty.")
    if len(set(output_meter_ids)) != len(output_meter_ids):
        raise HTTPException(status_code=422, detail="Output meter IDs must be unique.")
    if input_meter_id in output_meter_ids:
        raise HTTPException(status_code=422, detail="The input meter cannot also be an output meter.")
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        available_meter_ids = {
            row["meter_id"]
            for row in connection.execute(
                "SELECT DISTINCT meter_id FROM meter_readings WHERE dataset_id = ? AND feeder_id = ?",
                (dataset_id, feeder_id),
            ).fetchall()
        }
        requested = {input_meter_id, *output_meter_ids}
        missing = sorted(requested - available_meter_ids)
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Meter(s) not found on feeder {feeder_id}: {', '.join(missing)}.",
            )
        connection.execute(
            "DELETE FROM feeder_meter_roles WHERE dataset_id = ? AND feeder_id = ?",
            (dataset_id, feeder_id),
        )
        connection.executemany(
            "INSERT INTO feeder_meter_roles(dataset_id, feeder_id, meter_id, role) VALUES (?, ?, ?, ?)",
            [
                (dataset_id, feeder_id, input_meter_id, "input"),
                *[
                    (dataset_id, feeder_id, meter_id, "output")
                    for meter_id in output_meter_ids
                ],
            ],
        )
    return {
        "dataset_id": dataset_id,
        "feeder_id": feeder_id,
        "input_meter_id": input_meter_id,
        "output_meter_ids": output_meter_ids,
    }


@app.get("/api/datasets/{dataset_id}/reports/summary.pdf")
def download_dataset_report(dataset_id: int):
    summary = get_dataset_summary(dataset_id)
    voltage = get_dataset_voltage_analysis(dataset_id)
    transformer_result = list_dataset_transformers(dataset_id)
    outage_result = list_dataset_outages(dataset_id)
    loss_result = get_dataset_loss_analysis(dataset_id)

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="TN Smart Energy Dataset Report",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.alignment = TA_LEFT

    def pdf_text(value: object) -> str:
        return escape(str(value).encode("cp1252", "replace").decode("cp1252"))

    story = [
        Paragraph("TN Smart Energy - Dataset Report", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"Dataset: {pdf_text(summary['filename'])}", styles["Heading2"]),
        Paragraph(f"Generated: {datetime.now(timezone.utc).isoformat()}", body_style),
        Spacer(1, 12),
    ]

    def add_table(title: str, rows: list[list[str]]) -> None:
        story.append(Paragraph(escape(title), styles["Heading2"]))
        table = Table(rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf3ef")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#29483a")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dce6e1")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8faf9")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([table, Spacer(1, 10)])

    add_table(
        "Dataset summary",
        [
            ["Measure", "Value"],
            ["Uploaded readings", str(summary["record_count"])],
            ["Distinct meters", str(summary["meter_count"])],
            ["Feeders / transformers", f"{summary['feeder_count']} / {summary['transformer_count']}"],
            ["Total energy", f"{summary['total_energy_kwh']} kWh"],
            ["Average / maximum demand", f"{summary['average_demand_kw']} / {summary['maximum_demand_kw']} kW"],
        ],
    )
    add_table(
        "Voltage screening",
        [
            ["Readings", "Low (<207 V)", "Within screen", "High (>253 V)", "Average (V)"],
            [
                str(voltage["voltage_reading_count"]),
                str(voltage["low_voltage_count"]),
                str(voltage["within_screen_count"]),
                str(voltage["high_voltage_count"]),
                str(voltage["average_voltage"]),
            ],
        ],
    )
    transformer_rows = [["Transformer", "Capacity (kVA)", "Loading (%)", "Status"]]
    for item in transformer_result["transformers"][:50]:
        transformer_rows.append(
            [
                pdf_text(item["transformer_id"]),
                str(item["rated_capacity_kva"] or "Not configured"),
                str(item["loading_percent"] if item["loading_percent"] is not None else "Unavailable"),
                pdf_text(item["status"]),
            ]
        )
    if len(transformer_rows) == 1:
        transformer_rows.append(["No transformer data", "—", "—", "—"])
    add_table("Transformer loading screening", transformer_rows)
    add_table(
        "Manually logged outages",
        [
            ["Events", "Ongoing", "Total recorded duration (minutes)", "Source"],
            [
                str(outage_result["event_count"]),
                str(outage_result["ongoing_count"]),
                str(outage_result["total_duration_minutes"]),
                "Manually logged",
            ],
        ],
    )
    loss_rows = [["Feeder", "Input energy (kWh)", "Output energy (kWh)", "Difference (kWh)", "Difference (%)"]]
    for item in loss_result["feeders"][:50]:
        loss_rows.append(
            [
                pdf_text(item["feeder_id"]),
                str(item["input_energy_kwh"] if item["input_energy_kwh"] is not None else "Not configured"),
                str(item["output_energy_kwh"] if item["output_energy_kwh"] is not None else "Not configured"),
                str(item["energy_discrepancy_kwh"] if item["energy_discrepancy_kwh"] is not None else "—"),
                str(item["discrepancy_percent"] if item["discrepancy_percent"] is not None else "—"),
            ]
        )
    if len(loss_rows) == 1:
        loss_rows.append(["No feeder data", "—", "—", "—", "—"])
    add_table("Configured feeder energy balance", loss_rows)
    story.extend(
        [
            Paragraph(
                "This report summarizes user-uploaded data and user-configured asset boundaries. Screening indicators are not fault diagnoses, official utility measurements, or evidence of theft.",
                styles["Italic"],
            )
        ]
    )
    document.build(story)
    filename = f"tn-smart-energy-dataset-{dataset_id}-report.pdf"
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def demand_features(timestamp: datetime, origin: datetime) -> list[float]:
    elapsed_hours = (timestamp - origin).total_seconds() / 3600
    hour = timestamp.hour + timestamp.minute / 60
    weekday = timestamp.weekday()
    return [
        elapsed_hours,
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        math.sin(2 * math.pi * weekday / 7),
        math.cos(2 * math.pi * weekday / 7),
    ]


@app.get("/api/datasets/{dataset_id}/forecast")
def forecast_dataset_demand(dataset_id: int, horizon: int = 24):
    if horizon < 1 or horizon > 168:
        raise HTTPException(status_code=422, detail="Forecast horizon must be between 1 and 168 hours.")
    with database_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        rows = connection.execute(
            """
            SELECT timestamp, SUM(active_power_kw) AS demand_kw
            FROM meter_readings
            WHERE dataset_id = ? AND active_power_kw IS NOT NULL
            GROUP BY timestamp ORDER BY timestamp
            """,
            (dataset_id,),
        ).fetchall()
    observations = [
        (datetime.fromisoformat(row["timestamp"]), float(row["demand_kw"]))
        for row in rows
    ]
    if len(observations) < 24:
        return {
            "dataset_id": dataset_id,
            "status": "insufficient_history",
            "minimum_observations": 24,
            "training_observations": len(observations),
            "horizon_hours": horizon,
            "forecast": [],
            "limitation": "At least 24 distinct timestamped demand observations are required for the model.",
        }

    observations = observations[-2016:]
    timestamps = [item[0] for item in observations]
    demand = np.asarray([item[1] for item in observations], dtype=float)
    origin = timestamps[0]
    features = np.asarray([demand_features(timestamp, origin) for timestamp in timestamps])
    model_options = {
        "n_estimators": 120,
        "max_depth": 8,
        "min_samples_leaf": 2,
        "random_state": 42,
        "n_jobs": 1,
    }

    validation_mae = None
    if len(observations) >= 40:
        split_index = max(24, int(len(observations) * 0.8))
        validation_model = RandomForestRegressor(**model_options)
        validation_model.fit(features[:split_index], demand[:split_index])
        validation_prediction = validation_model.predict(features[split_index:])
        validation_mae = round(
            float(np.mean(np.abs(validation_prediction - demand[split_index:]))), 3
        )

    model = RandomForestRegressor(**model_options)
    model.fit(features, demand)
    last_timestamp = timestamps[-1]
    future_timestamps = [
        last_timestamp + timedelta(hours=step) for step in range(1, horizon + 1)
    ]
    future_features = np.asarray(
        [demand_features(timestamp, origin) for timestamp in future_timestamps]
    )
    tree_predictions = np.asarray(
        [tree.predict(future_features) for tree in model.estimators_]
    )
    forecast = []
    for index, timestamp in enumerate(future_timestamps):
        prediction = max(0.0, float(np.mean(tree_predictions[:, index])))
        lower, upper = np.percentile(tree_predictions[:, index], [10, 90])
        forecast.append(
            {
                "timestamp": timestamp.isoformat(),
                "demand_kw": round(prediction, 3),
                "lower_bound_kw": round(max(0.0, float(lower)), 3),
                "upper_bound_kw": round(max(0.0, float(upper)), 3),
            }
        )
    return {
        "dataset_id": dataset_id,
        "status": "forecast_available",
        "model": "RandomForestRegressor (hour-of-day, day-of-week and elapsed-time features)",
        "training_observations": len(observations),
        "last_observed_timestamp": last_timestamp.isoformat(),
        "horizon_hours": horizon,
        "validation_mae_kw": validation_mae,
        "validation_method": "chronological 80/20 holdout" if validation_mae is not None else None,
        "forecast": forecast,
        "limitation": "Statistical estimates from uploaded active-power readings; not a live-grid prediction or operational dispatch instruction.",
    }


@app.post("/api/analysis/conservation")
def conservation(payload: ConservationInput):
    new_peak = max(0.0, payload.original_peak_kw - payload.shiftable_load_kw)
    reduction = ((payload.original_peak_kw - new_peak) / payload.original_peak_kw) * 100
    return {
        "original_peak_kw": payload.original_peak_kw,
        "shiftable_load_kw": payload.shiftable_load_kw,
        "new_estimated_peak_kw": round(new_peak, 3),
        "peak_reduction_percent": round(reduction, 3),
        "kwh_energy_savings": payload.actual_reduction_kwh,
        "interpretation": "Load shifting reduces peak kW; it is not energy saving unless measured kWh reduction is provided.",
        "data_source": "simulated_or_user_supplied",
    }


@app.post("/api/analysis/transformer")
def transformer(payload: TransformerInput):
    loading, status, recommendation = transformer_loading_screen(
        payload.measured_kva,
        payload.rated_kva,
        payload.high_loading_threshold,
        payload.exceedance_threshold,
    )
    return {
        "loading_percent": round(loading, 3),
        "status": status,
        "recommendation": recommendation,
        "limitation": "Screening level is configurable and is not a universal safety limit.",
    }


@app.post("/api/analysis/voltage")
def voltage(payload: VoltageInput):
    low = payload.voltage < payload.low_threshold
    return {
        "voltage": payload.voltage,
        "nominal_voltage": payload.nominal_voltage,
        "low_threshold": payload.low_threshold,
        "screening_result": "low_voltage_screen" if low else "within_configured_screen",
        "recommendation": "Investigate with additional readings." if low else "Continue monitoring.",
        "limitation": "One reading cannot establish a transformer or feeder fault.",
    }


@app.post("/api/analysis/loss")
def loss(payload: LossInput):
    return distribution_loss_calculation(payload.input_kwh, payload.output_kwh)


@app.post("/api/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)):
    require_writable_mode()
    name = file.filename or ""
    if not name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV uploads are supported in this version.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB upload limit.")
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.")

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV header row is missing.")
    normalized_headers = [column.strip().lower() for column in reader.fieldnames]
    normalized = set(normalized_headers)
    if len(normalized_headers) != len(normalized):
        raise HTTPException(status_code=422, detail="CSV contains duplicate column names.")
    missing = sorted(REQUIRED_METER_COLUMNS - normalized)
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required columns: {', '.join(missing)}")

    accepted_rows = []
    rejected = []
    seen = set()
    meter_ratings = {}
    transformer_ratings = {}
    for line_number, row in enumerate(reader, start=2):
        try:
            if None in row and row[None]:
                raise ValueError("row contains more fields than the header")
            normalized_row = {
                key.strip().lower(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            meter_id = normalized_row.get("meter_id", "")
            timestamp_value = normalized_row.get("timestamp", "")
            if not timestamp_value:
                raise ValueError("timestamp is empty")
            timestamp = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("timestamp must include a timezone, such as Z or +05:30")
            timestamp_utc = timestamp.astimezone(timezone.utc).isoformat()
            energy = float(normalized_row.get("energy_kwh", ""))
            if not math.isfinite(energy):
                raise ValueError("energy_kwh must be a finite number")
            if not meter_id:
                raise ValueError("meter_id is empty")
            if energy < 0:
                raise ValueError("energy_kwh must not be negative")
            key = (meter_id, timestamp_utc)
            if key in seen:
                raise ValueError("duplicate meter reading")
            optional_values = {}
            for column in (
                "voltage",
                "current_a",
                "active_power_kw",
                "power_factor",
                "sanctioned_load_kw",
                "transformer_rated_kva",
            ):
                value = normalized_row.get(column, "")
                parsed_value = float(value) if value else None
                if parsed_value is not None and not math.isfinite(parsed_value):
                    raise ValueError(f"{column} must be a finite number")
                optional_values[column] = parsed_value
            if optional_values["voltage"] is not None and optional_values["voltage"] <= 0:
                raise ValueError("voltage must be greater than zero")
            if optional_values["current_a"] is not None and optional_values["current_a"] < 0:
                raise ValueError("current_a must not be negative")
            power_factor = optional_values["power_factor"]
            if power_factor is not None and abs(power_factor) > 1:
                raise ValueError("power_factor must be between -1 and 1")
            sanctioned_load = optional_values["sanctioned_load_kw"]
            if sanctioned_load is not None and sanctioned_load <= 0:
                raise ValueError("sanctioned_load_kw must be greater than zero")
            transformer_rated_kva = optional_values["transformer_rated_kva"]
            if transformer_rated_kva is not None and transformer_rated_kva <= 0:
                raise ValueError("transformer_rated_kva must be greater than zero")
            if sanctioned_load is not None and meter_id in meter_ratings and meter_ratings[meter_id] != sanctioned_load:
                raise ValueError("sanctioned_load_kw conflicts with another row for this meter")
            transformer_id = normalized_row.get("transformer_id") or None
            if (
                transformer_id
                and transformer_rated_kva is not None
                and transformer_id in transformer_ratings
                and transformer_ratings[transformer_id] != transformer_rated_kva
            ):
                raise ValueError("transformer_rated_kva conflicts with another row for this transformer")
            accepted_rows.append(
                (
                    meter_id,
                    timestamp_utc,
                    energy,
                    optional_values["voltage"],
                    optional_values["current_a"],
                    optional_values["active_power_kw"],
                    optional_values["power_factor"],
                    normalized_row.get("feeder_id") or None,
                    transformer_id,
                    normalized_row.get("consumer_category") or None,
                    sanctioned_load,
                    transformer_rated_kva,
                )
            )
            seen.add(key)
            if sanctioned_load is not None:
                meter_ratings[meter_id] = sanctioned_load
            if transformer_id and transformer_rated_kva is not None:
                transformer_ratings[transformer_id] = transformer_rated_kva
        except (ValueError, TypeError) as exc:
            rejected.append({"row": line_number, "reason": str(exc)})

    if not accepted_rows:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "No valid readings were found; the dataset was not saved.",
                "accepted_rows": 0,
                "rejected_rows": len(rejected),
                "errors": rejected[:100],
            },
        )

    uploaded_at = datetime.now(timezone.utc).isoformat()
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO datasets(filename, uploaded_at, accepted_rows, rejected_rows) VALUES (?, ?, ?, ?)",
            (name, uploaded_at, len(accepted_rows), len(rejected)),
        )
        dataset_id = cursor.lastrowid
        connection.executemany(
            """
            INSERT INTO meter_readings(
                dataset_id, meter_id, timestamp, energy_kwh, voltage, current_a,
                active_power_kw, power_factor, feeder_id, transformer_id, consumer_category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(dataset_id, *reading[:10]) for reading in accepted_rows],
        )
        for reading in accepted_rows:
            meter_id, feeder_id, transformer_id = reading[0], reading[7], reading[8]
            consumer_category, sanctioned_load = reading[9], reading[10]
            transformer_rated_kva = reading[11]
            connection.execute(
                """
                INSERT INTO meter_profiles(
                    meter_id, sanctioned_load_kw, consumer_category, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(meter_id) DO UPDATE SET
                    sanctioned_load_kw = COALESCE(excluded.sanctioned_load_kw, meter_profiles.sanctioned_load_kw),
                    consumer_category = COALESCE(excluded.consumer_category, meter_profiles.consumer_category),
                    updated_at = excluded.updated_at
                """,
                (meter_id, sanctioned_load, consumer_category, uploaded_at),
            )
            if transformer_id:
                connection.execute(
                    """
                    INSERT INTO transformer_assets(
                        transformer_id, feeder_id, rated_capacity_kva, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(transformer_id) DO UPDATE SET
                        feeder_id = COALESCE(excluded.feeder_id, transformer_assets.feeder_id),
                        rated_capacity_kva = COALESCE(excluded.rated_capacity_kva, transformer_assets.rated_capacity_kva),
                        updated_at = excluded.updated_at
                    """,
                    (transformer_id, feeder_id, transformer_rated_kva, uploaded_at),
                )

    return {
        "id": dataset_id,
        "filename": name,
        "uploaded_at": uploaded_at,
        "accepted_rows": len(accepted_rows),
        "rejected_rows": len(rejected),
        "errors": rejected[:100],
    }


@app.get("/{requested_path:path}", include_in_schema=False)
def serve_frontend(requested_path: str = ""):
    if requested_path == "api" or requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found.")

    web_root = Path(
        os.environ.get(
            "STATIC_WEB_ROOT",
            str(Path(__file__).resolve().parents[1] / "frontend-dist"),
        )
    ).resolve()
    requested_file = (web_root / requested_path).resolve()
    try:
        requested_file.relative_to(web_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.")

    if requested_file.is_file():
        return FileResponse(requested_file)
    index_file = web_root / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Frontend build is not available.")
