import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_conservation_calculation():
    response = client.post("/api/analysis/conservation", json={
        "original_peak_kw": 100,
        "shiftable_load_kw": 18,
    })
    assert response.status_code == 200
    assert response.json()["new_estimated_peak_kw"] == 82
    assert response.json()["peak_reduction_percent"] == 18


def test_transformer_loading():
    response = client.post("/api/analysis/transformer", json={
        "measured_kva": 210,
        "rated_kva": 250,
    })
    assert response.status_code == 200
    assert response.json()["loading_percent"] == 84
    assert response.json()["status"] == "high_loading"


def test_voltage_screen():
    response = client.post("/api/analysis/voltage", json={
        "voltage": 205,
        "nominal_voltage": 230,
        "low_threshold": 207,
    })
    assert response.status_code == 200
    assert response.json()["screening_result"] == "low_voltage_screen"


def test_csv_upload_requires_columns():
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("invalid.csv", b"meter_id,timestamp\nA1,2026-11-22T10:00:00", "text/csv")},
    )
    assert response.status_code == 422


def test_csv_upload_normalizes_headers_persists_rows_and_builds_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "test.sqlite3"))
    content = b"""METER_ID,TIMESTAMP,ENERGY_KWH,VOLTAGE,ACTIVE_POWER_KW
M1,2026-11-22T00:00:00Z,2,206,1
M2,2026-11-22T00:00:00Z,3,230,2
M1,2026-11-22T01:00:00Z,4,220,4
M1,2026-11-22T00:00:00Z,2,206,1
M3,2026-11-22T02:00:00Z,NaN,220,2
"""
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("readings.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    upload = response.json()
    assert upload["accepted_rows"] == 3
    assert upload["rejected_rows"] == 2

    datasets = client.get("/api/datasets")
    assert datasets.status_code == 200
    assert datasets.json()[0]["id"] == upload["id"]

    summary = client.get(f"/api/datasets/{upload['id']}/summary").json()
    assert summary["record_count"] == 3
    assert summary["meter_count"] == 2
    assert summary["total_energy_kwh"] == 9
    assert summary["current_demand_kw"] == 4
    assert summary["maximum_demand_kw"] == 4
    assert summary["average_demand_kw"] == 3.5
    assert summary["low_voltage_reading_count"] == 1

    readings = client.get(f"/api/datasets/{upload['id']}/readings?limit=2").json()
    assert len(readings["readings"]) == 2


def test_upload_requires_timezone_and_does_not_save_empty_dataset(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "test.sqlite3"))
    response = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "readings.csv",
                b"meter_id,timestamp,energy_kwh\nM1,2026-11-22T10:00:00,1\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
    assert "timezone" in response.json()["detail"]["errors"][0]["reason"]
    assert client.get("/api/datasets").json() == []


def test_upload_rejects_non_csv():
    response = client.post(
        "/api/datasets/upload",
        files={"file": ("readings.xlsx", b"not a workbook", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_additive_migration_preserves_existing_dataset_rows(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            accepted_rows INTEGER NOT NULL,
            rejected_rows INTEGER NOT NULL
        );
        CREATE TABLE meter_readings (
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
        INSERT INTO datasets(filename, uploaded_at, accepted_rows, rejected_rows)
        VALUES ('existing.csv', '2026-11-22T00:00:00+00:00', 1, 0);
        INSERT INTO meter_readings(dataset_id, meter_id, timestamp, energy_kwh)
        VALUES (1, 'EXISTING-METER', '2026-11-22T00:00:00+00:00', 5.5);
        """
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(database_path))

    response = client.get("/api/datasets")

    assert response.status_code == 200
    assert response.json()[0]["filename"] == "existing.csv"
    with sqlite3.connect(database_path) as migrated:
        assert migrated.execute("SELECT COUNT(*) FROM meter_readings").fetchone()[0] == 1
        assert migrated.execute("SELECT energy_kwh FROM meter_readings").fetchone()[0] == 5.5
        assert migrated.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meter_profiles'"
        ).fetchone()
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='outage_events'"
        ).fetchone()


def test_sanctioned_load_profile_creates_screening_alert(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "meter.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "meter.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw,sanctioned_load_kw\n"
                b"METER-1,2026-11-22T10:00:00Z,1.2,5,4\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    dataset_id = upload.json()["id"]

    meters = client.get(f"/api/datasets/{dataset_id}/meters").json()["meters"]
    assert meters[0]["alert_status"] == "at_or_above_sanctioned_load"

    saved = client.put(
        "/api/meters/METER-1/profile",
        json={"sanctioned_load_kw": 6, "consumer_category": "household", "locality": "Sample locality"},
    )
    assert saved.status_code == 200
    assert saved.json()["sanctioned_load_kw"] == 6
    meters_after_update = client.get(f"/api/datasets/{dataset_id}/meters").json()["meters"]
    assert meters_after_update[0]["alert_status"] == "within_sanctioned_load"

    detail = client.get(f"/api/datasets/{dataset_id}/meters/METER-1").json()
    assert detail["readings"][0]["active_power_kw"] == 5
    assert detail["profile"]["locality"] == "Sample locality"


def test_transformer_monitoring_aggregates_latest_apparent_power(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "transformer.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "transformers.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw,power_factor,transformer_id,transformer_rated_kva\n"
                b"METER-1,2026-11-22T10:00:00Z,1,40,0.8,T-1,100\n"
                b"METER-2,2026-11-22T10:00:00Z,1,20,0.8,T-1,100\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    dataset_id = upload.json()["id"]

    monitored = client.get(f"/api/datasets/{dataset_id}/transformers")
    assert monitored.status_code == 200
    transformer = monitored.json()["transformers"][0]
    assert transformer["measured_apparent_power_kva"] == 75
    assert transformer["loading_percent"] == 75
    assert transformer["status"] == "high_loading"
    assert client.get(f"/api/datasets/{dataset_id}/summary").json()[
        "maximum_transformer_loading_percent"
    ] == 75

    saved = client.put(
        "/api/transformers/T-1/profile",
        json={
            "rated_capacity_kva": 200,
            "feeder_id": "F-1",
            "location": "Sample location",
            "high_loading_threshold_percent": 70,
            "exceedance_threshold_percent": 90,
        },
    )
    assert saved.status_code == 200
    updated = client.get(f"/api/datasets/{dataset_id}/transformers").json()["transformers"][0]
    assert updated["rated_capacity_kva"] == 200
    assert updated["loading_percent"] == 37.5
    assert updated["status"] == "normal"
    assert client.get(f"/api/datasets/{dataset_id}/summary").json()[
        "maximum_transformer_loading_percent"
    ] == 37.5


def test_transformer_monitoring_does_not_infer_kva_without_power_factor(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "no-pf.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "transformers.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw,transformer_id,transformer_rated_kva\n"
                b"METER-1,2026-11-22T10:00:00Z,1,40,T-1,100\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    transformer = client.get(
        f"/api/datasets/{upload.json()['id']}/transformers"
    ).json()["transformers"][0]
    assert transformer["measured_apparent_power_kva"] is None
    assert transformer["loading_percent"] is None
    assert transformer["status"] == "capacity_or_power_factor_not_available"


def test_transformer_load_uses_a_shared_latest_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "aligned-transformer.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "transformers.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw,power_factor,transformer_id,transformer_rated_kva\n"
                b"METER-1,2026-11-22T10:00:00Z,1,40,0.8,T-1,100\n"
                b"METER-2,2026-11-22T10:00:00Z,1,20,0.8,T-1,100\n"
                b"METER-1,2026-11-22T11:00:00Z,1,10,0.8,T-1,100\n",
                "text/csv",
            )
        },
    )
    transformer = client.get(
        f"/api/datasets/{upload.json()['id']}/transformers"
    ).json()["transformers"][0]
    assert transformer["latest_timestamp"] == "2026-11-22T11:00:00+00:00"
    assert transformer["meter_count"] == 1
    assert transformer["measured_apparent_power_kva"] == 12.5
    assert transformer["loading_percent"] == 12.5


def test_demand_forecast_uses_uploaded_hourly_observations(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "forecast.sqlite3"))
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    lines = ["meter_id,timestamp,energy_kwh,active_power_kw"]
    for hour in range(48):
        timestamp = (start + timedelta(hours=hour)).isoformat()
        demand = 10 + (hour % 24)
        lines.append(f"METER-1,{timestamp},1,{demand}")
    upload = client.post(
        "/api/datasets/upload",
        files={"file": ("hourly.csv", "\n".join(lines).encode(), "text/csv")},
    )
    assert upload.status_code == 200

    response = client.get(f"/api/datasets/{upload.json()['id']}/forecast?horizon=12")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "forecast_available"
    assert result["training_observations"] == 48
    assert result["model"].startswith("RandomForestRegressor")
    assert result["validation_mae_kw"] is not None
    assert len(result["forecast"]) == 12
    assert result["forecast"][0]["timestamp"] == "2026-11-03T00:00:00+00:00"
    assert all(point["demand_kw"] >= 0 for point in result["forecast"])


def test_demand_forecast_reports_insufficient_history(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "short-forecast.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "short.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw\n"
                b"METER-1,2026-11-22T00:00:00Z,1,1\n"
                b"METER-1,2026-11-22T01:00:00Z,1,2\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    result = client.get(f"/api/datasets/{upload.json()['id']}/forecast").json()
    assert result["status"] == "insufficient_history"
    assert result["forecast"] == []


def test_voltage_analysis_screens_uploaded_readings_by_feeder(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "voltage.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "voltage.csv",
                b"meter_id,timestamp,energy_kwh,voltage,feeder_id\n"
                b"M1,2026-11-22T00:00:00Z,1,200,F1\n"
                b"M2,2026-11-22T00:00:00Z,1,230,F1\n"
                b"M3,2026-11-22T00:00:00Z,1,260,F2\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    result = client.get(
        f"/api/datasets/{upload.json()['id']}/voltage-analysis"
    ).json()
    assert result["voltage_reading_count"] == 3
    assert result["average_voltage"] == 230
    assert result["low_voltage_count"] == 1
    assert result["high_voltage_count"] == 1
    assert result["within_screen_count"] == 1
    assert result["feeders"][0]["feeder_id"] == "F1"
    assert result["feeders"][0]["low_voltage_count"] == 1


def test_outage_events_are_stored_with_timezone_and_duration(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "outages.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "outage.csv",
                b"meter_id,timestamp,energy_kwh\nM1,2026-11-22T00:00:00Z,1\n",
                "text/csv",
            )
        },
    )
    dataset_id = upload.json()["id"]
    created = client.post(
        f"/api/datasets/{dataset_id}/outages",
        json={
            "feeder_id": "F-1",
            "started_at": "2026-11-22T01:00:00+05:30",
            "ended_at": "2026-11-22T02:30:00+05:30",
            "cause": "Maintenance",
            "notes": "Planned event",
        },
    )
    assert created.status_code == 201
    assert created.json()["duration_minutes"] == 90
    assert created.json()["is_ongoing"] is False

    listed = client.get(f"/api/datasets/{dataset_id}/outages").json()
    assert listed["source"] == "manually_logged"
    assert listed["event_count"] == 1
    assert listed["total_duration_minutes"] == 90
    assert listed["events"][0]["feeder_id"] == "F-1"

    invalid = client.post(
        f"/api/datasets/{dataset_id}/outages",
        json={
            "feeder_id": "F-1",
            "started_at": "2026-11-22T02:00:00Z",
            "ended_at": "2026-11-22T01:00:00Z",
        },
    )
    assert invalid.status_code == 422


def test_distribution_loss_uses_configured_feeder_boundary_meters(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "loss.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "loss.csv",
                b"meter_id,timestamp,energy_kwh,feeder_id\n"
                b"IN,2026-11-22T00:00:00Z,100,F1\n"
                b"OUT-1,2026-11-22T00:00:00Z,30,F1\n"
                b"OUT-2,2026-11-22T00:00:00Z,50,F1\n",
                "text/csv",
            )
        },
    )
    dataset_id = upload.json()["id"]
    unconfigured = client.get(f"/api/datasets/{dataset_id}/loss-analysis").json()
    assert unconfigured["feeders"][0]["analysis_ready"] is False

    configured = client.put(
        f"/api/datasets/{dataset_id}/feeders/F1/meter-roles",
        json={"input_meter_id": "IN", "output_meter_ids": ["OUT-1", "OUT-2"]},
    )
    assert configured.status_code == 200
    result = client.get(f"/api/datasets/{dataset_id}/loss-analysis").json()
    feeder = result["feeders"][0]
    assert feeder["analysis_ready"] is True
    assert feeder["input_energy_kwh"] == 100
    assert feeder["output_energy_kwh"] == 80
    assert feeder["energy_discrepancy_kwh"] == 20
    assert feeder["discrepancy_percent"] == 20

    invalid = client.put(
        f"/api/datasets/{dataset_id}/feeders/F1/meter-roles",
        json={"input_meter_id": "IN", "output_meter_ids": ["MISSING"]},
    )
    assert invalid.status_code == 422
    preserved = client.get(f"/api/datasets/{dataset_id}/loss-analysis").json()["feeders"][0]
    assert preserved["output_meter_ids"] == ["OUT-1", "OUT-2"]


def test_summary_report_returns_a_generated_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(tmp_path / "report.sqlite3"))
    upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "report.csv",
                b"meter_id,timestamp,energy_kwh,active_power_kw,voltage,feeder_id,transformer_id\n"
                b"M1,2026-11-22T00:00:00Z,1,2,230,F1,T1\n",
                "text/csv",
            )
        },
    )
    dataset_id = upload.json()["id"]

    report = client.get(f"/api/datasets/{dataset_id}/reports/summary.pdf")
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.headers["content-disposition"].endswith(
        f'filename="tn-smart-energy-dataset-{dataset_id}-report.pdf"'
    )
    assert report.content.startswith(b"%PDF-")


def test_public_demo_seeds_synthetic_data_without_touching_private_database(tmp_path, monkeypatch):
    private_db = tmp_path / "private.sqlite3"
    public_db = tmp_path / "public-demo.sqlite3"
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "false")
    monkeypatch.setenv("TN_SMART_ENERGY_DB_PATH", str(private_db))
    private_upload = client.post(
        "/api/datasets/upload",
        files={
            "file": (
                "private.csv",
                b"meter_id,timestamp,energy_kwh\nPRIVATE-1,2026-11-22T00:00:00Z,8\n",
                "text/csv",
            )
        },
    )
    assert private_upload.status_code == 200

    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("PUBLIC_DEMO_DB_PATH", str(private_db))
    with pytest.raises(RuntimeError, match="must not be the normal application database"):
        client.get("/api/datasets")

    monkeypatch.setenv("PUBLIC_DEMO_DB_PATH", str(public_db))
    public_datasets = client.get("/api/datasets").json()

    assert len(public_datasets) == 1
    assert public_datasets[0]["filename"] == "PUBLIC_DEMO_simulated_readings.csv"
    assert public_datasets[0]["accepted_rows"] == 192
    dataset_id = public_datasets[0]["id"]
    summary = client.get(f"/api/datasets/{dataset_id}/summary").json()
    assert summary["record_count"] == 192
    assert summary["meter_count"] == 4
    meters = client.get(f"/api/datasets/{dataset_id}/meters").json()["meters"]
    assert all(meter["meter_id"].startswith("DEMO-") for meter in meters)

    with sqlite3.connect(private_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 1
        assert connection.execute(
            "SELECT meter_id FROM meter_readings"
        ).fetchone()[0] == "PRIVATE-1"


def test_public_demo_blocks_persistent_writes_but_allows_calculations(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "true")
    monkeypatch.setenv("PUBLIC_DEMO_DB_PATH", str(tmp_path / "public-demo.sqlite3"))
    dataset = client.get("/api/datasets").json()[0]
    dataset_id = dataset["id"]

    assert client.post(
        "/api/datasets/upload",
        files={"file": ("readings.csv", b"meter_id,timestamp,energy_kwh\nM1,2026-11-22T00:00:00Z,1\n", "text/csv")},
    ).status_code == 403
    assert client.put(
        "/api/meters/DEMO-IN-F1/profile",
        json={"sanctioned_load_kw": 40},
    ).status_code == 403
    assert client.put(
        "/api/transformers/T-DEMO-1/profile",
        json={"rated_capacity_kva": 120},
    ).status_code == 403
    assert client.post(
        f"/api/datasets/{dataset_id}/outages",
        json={"feeder_id": "F-DEMO-1", "started_at": "2026-11-22T00:00:00Z"},
    ).status_code == 403
    assert client.put(
        f"/api/datasets/{dataset_id}/feeders/F-DEMO-1/meter-roles",
        json={"input_meter_id": "DEMO-IN-F1", "output_meter_ids": ["DEMO-OUT-F1"]},
    ).status_code == 403
    assert client.post(
        "/api/analysis/conservation",
        json={"original_peak_kw": 100, "shiftable_load_kw": 10},
    ).status_code == 200


def test_frontend_fallback_serves_spa_routes_without_masking_api_errors(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>TN Smart Energy</html>", encoding="utf-8")
    monkeypatch.setenv("STATIC_WEB_ROOT", str(tmp_path))

    assert client.get("/meters").text == "<html>TN Smart Energy</html>"
    assert client.get("/api/unknown-route").status_code == 404

