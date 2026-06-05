"""
Data Service Integration Tests
==============================

Tests the DataServicer against real generated protobuf stubs and an isolated
SQLite database. Covers batch ingestion, validation, querying, pagination,
export, streaming, and health checks.
"""

import time
import threading
from datetime import datetime, timedelta

import pytest

from src.gen import data_service_pb2, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp


def _ts(dt: datetime) -> Timestamp:
    t = Timestamp()
    t.FromDatetime(dt)
    return t


def _gravity(sat_id="SAT001", value=12.5, lat=10.0, lon=20.0, alt=450000.0,
             uncertainty=0.1, quality="good", mid=""):
    return data_service_pb2.GravityMeasurement(
        measurement_id=mid,
        satellite_id=sat_id,
        timestamp=_ts(datetime.utcnow()),
        location=common_pb2.GeoLocation(latitude=lat, longitude=lon, altitude=alt),
        gravity_value=value,
        uncertainty=uncertainty,
        quality_flag=quality,
    )


def _telemetry(sat_id="SAT001", lat=10.0, lon=20.0, alt=450000.0,
               temp=25.0, battery=85.0):
    return data_service_pb2.SatelliteTelemetry(
        satellite_id=sat_id,
        timestamp=_ts(datetime.utcnow()),
        location=common_pb2.GeoLocation(latitude=lat, longitude=lon, altitude=alt),
        velocity_x=7500.0, velocity_y=100.0, velocity_z=10.0,
        temperature=temp, battery_level=battery,
    )


# ---------------------------------------------------------------------------
# Gravity ingestion + query
# ---------------------------------------------------------------------------
class TestGravityIngestion:

    def test_ingest_valid_measurements(self, servicer, context):
        req = data_service_pb2.IngestGravityRequest(
            measurements=[_gravity(value=10.0), _gravity(value=15.0, sat_id="SAT002")]
        )
        resp = servicer.IngestGravity(req, context)
        assert resp.records_ingested == 2
        assert resp.records_failed == 0
        assert resp.response.status_code == 200

    def test_out_of_range_gravity_is_flagged(self, servicer, context):
        # gravity_value beyond +/-1000 mGal is a non-fatal warning: the record
        # is still ingested, but with an empty incoming quality_flag it is
        # marked "flagged" rather than "good".
        sid = f"FLAG_{int(time.time()*1000)}"
        req = data_service_pb2.IngestGravityRequest(
            measurements=[_gravity(sat_id=sid, value=999999.0, quality="")]
        )
        resp = servicer.IngestGravity(req, context)
        assert resp.records_ingested == 1
        assert resp.records_failed == 0

        q = data_service_pb2.QueryGravityRequest(satellite_ids=[sid])
        q.pagination.page = 1
        q.pagination.page_size = 10
        out = servicer.QueryGravity(q, context)
        assert out.measurements[0].quality_flag == "flagged"

    def test_ingest_rejects_bad_location(self, servicer, context):
        req = data_service_pb2.IngestGravityRequest(
            measurements=[_gravity(lat=200.0)]  # latitude out of [-90, 90]
        )
        resp = servicer.IngestGravity(req, context)
        assert resp.records_failed == 1

    def test_query_returns_ingested(self, servicer, context):
        # Ingest a uniquely-tagged satellite then query it back.
        sid = f"QSAT_{int(time.time()*1000)}"
        servicer.IngestGravity(
            data_service_pb2.IngestGravityRequest(
                measurements=[_gravity(sat_id=sid, value=42.0)]
            ),
            context,
        )
        q = data_service_pb2.QueryGravityRequest(satellite_ids=[sid])
        q.pagination.page = 1
        q.pagination.page_size = 100
        resp = servicer.QueryGravity(q, context)
        assert len(resp.measurements) == 1
        assert resp.measurements[0].satellite_id == sid
        assert resp.measurements[0].gravity_value == pytest.approx(42.0)

    def test_query_bounding_box(self, servicer, context):
        sid = f"BBOX_{int(time.time()*1000)}"
        servicer.IngestGravity(
            data_service_pb2.IngestGravityRequest(
                measurements=[
                    _gravity(sat_id=sid, lat=5.0, lon=5.0, value=1.0),
                    _gravity(sat_id=sid, lat=80.0, lon=80.0, value=2.0),
                ]
            ),
            context,
        )
        q = data_service_pb2.QueryGravityRequest(
            satellite_ids=[sid],
            min_latitude=0.0, max_latitude=10.0,
            min_longitude=0.0, max_longitude=10.0,
        )
        q.pagination.page = 1
        q.pagination.page_size = 100
        resp = servicer.QueryGravity(q, context)
        # Only the (5,5) measurement falls in the box.
        assert len(resp.measurements) == 1
        assert resp.measurements[0].gravity_value == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Telemetry ingestion + query + pagination
# ---------------------------------------------------------------------------
class TestTelemetry:

    def test_ingest_and_query(self, servicer, context):
        sid = f"TSAT_{int(time.time()*1000)}"
        servicer.IngestTelemetry(
            data_service_pb2.IngestTelemetryRequest(
                telemetry=[_telemetry(sat_id=sid), _telemetry(sat_id=sid)]
            ),
            context,
        )
        q = data_service_pb2.QueryTelemetryRequest(satellite_ids=[sid])
        q.pagination.page = 1
        q.pagination.page_size = 100
        resp = servicer.QueryTelemetry(q, context)
        assert len(resp.telemetry) == 2
        assert all(t.satellite_id == sid for t in resp.telemetry)

    def test_pagination(self, servicer, context):
        sid = f"PSAT_{int(time.time()*1000)}"
        servicer.IngestTelemetry(
            data_service_pb2.IngestTelemetryRequest(
                telemetry=[_telemetry(sat_id=sid) for _ in range(5)]
            ),
            context,
        )
        q = data_service_pb2.QueryTelemetryRequest(satellite_ids=[sid])
        q.pagination.page = 1
        q.pagination.page_size = 2
        resp = servicer.QueryTelemetry(q, context)
        assert len(resp.telemetry) == 2
        assert resp.pagination.page_size == 2
        assert resp.pagination.total_items == 5
        assert resp.pagination.total_pages == 3
        assert resp.pagination.has_next is True
        assert resp.pagination.has_previous is False


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------
class TestStreaming:

    def test_stream_gravity_receives_published(self, servicer, context):
        """Records ingested after a stream starts should reach the stream."""
        sid = f"STREAM_{int(time.time()*1000)}"
        q = data_service_pb2.QueryGravityRequest(satellite_ids=[sid])

        received = []

        def consume():
            for msg in servicer.StreamGravity(q, context):
                received.append(msg)
                break  # one message is enough for the test

        t = threading.Thread(target=consume, daemon=True)
        t.start()
        time.sleep(0.2)  # let the subscriber register

        servicer.IngestGravity(
            data_service_pb2.IngestGravityRequest(
                measurements=[_gravity(sat_id=sid, value=7.0)]
            ),
            context,
        )

        t.join(timeout=3.0)
        context.trigger_cancel()
        assert len(received) == 1
        assert received[0].satellite_id == sid
        assert received[0].gravity_value == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
class TestExport:

    def test_export_gravity_csv(self, servicer, context):
        sid = f"EXP_{int(time.time()*1000)}"
        servicer.IngestGravity(
            data_service_pb2.IngestGravityRequest(
                measurements=[_gravity(sat_id=sid)]
            ),
            context,
        )
        req = data_service_pb2.ExportDataRequest(
            export_type="gravity", satellite_ids=[sid], format="csv"
        )
        resp = servicer.ExportData(req, context)
        assert resp.response.status_code == 200
        assert resp.download_url  # some URL (file:// or s3://)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class TestHealth:

    def test_health_check_serving(self, servicer, context):
        resp = servicer.HealthCheck(common_pb2.HealthCheckRequest(), context)
        assert resp.status == common_pb2.HealthCheckResponse.SERVING
