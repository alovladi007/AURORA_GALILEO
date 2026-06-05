"""
Data Service gRPC implementation

Aligned with proto/data_service.proto:
  - Batch ingestion (repeated telemetry / measurements)
  - Scalar gravity_value (mGal) + uncertainty + string quality_flag
  - Page/page_size pagination, PaginationResponse with total_items/pages
  - common.Response with status_code/message/metadata

Adds real validation, Kafka (+ in-process) streaming and data export.
"""

import grpc
import threading
import uuid
from datetime import datetime
import logging

from src.gen import data_service_pb2, data_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from src.database import db, SatelliteTelemetryModel, GravityMeasurementModel
from src.validation import validate_telemetry, validate_gravity
from src.streaming import broker, TOPIC_TELEMETRY, TOPIC_GRAVITY
from src.exporters import DataExporter

logger = logging.getLogger(__name__)

exporter = DataExporter()


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def timestamp_to_datetime(ts: Timestamp) -> datetime:
    return ts.ToDatetime()


def ok_response(message: str, metadata: dict = None) -> common_pb2.Response:
    return common_pb2.Response(
        status_code=200,
        message=message,
        timestamp=datetime_to_timestamp(datetime.utcnow()),
        metadata={k: str(v) for k, v in (metadata or {}).items()},
    )


def error_response(code: int, message: str) -> common_pb2.Response:
    return common_pb2.Response(
        status_code=code,
        message=message,
        timestamp=datetime_to_timestamp(datetime.utcnow()),
    )


def _page_params(pagination):
    """Return (offset, limit, page, page_size) from a PaginationRequest."""
    page = getattr(pagination, "page", 0) or 1
    page_size = getattr(pagination, "page_size", 0) or 100
    page = max(page, 1)
    page_size = max(min(page_size, 10000), 1)
    return (page - 1) * page_size, page_size, page, page_size


def _pagination_response(total, page, page_size):
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return common_pb2.PaginationResponse(
        total_items=total,
        total_pages=total_pages,
        current_page=page,
        page_size=page_size,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


class DataServicer(data_service_pb2_grpc.DataServiceServicer):
    """Data Service implementation."""

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    def IngestTelemetry(self, request, context):
        """Batch-ingest satellite telemetry with validation and streaming."""
        session = db.get_session()
        ingested, failed, errors = 0, 0, []
        try:
            for record in request.telemetry:
                validation = validate_telemetry(record)
                if not validation.valid:
                    failed += 1
                    errors.append(f"{record.satellite_id}: " + "; ".join(validation.errors))
                    continue

                telemetry = SatelliteTelemetryModel(
                    satellite_id=record.satellite_id,
                    timestamp=timestamp_to_datetime(record.timestamp),
                    latitude=record.location.latitude,
                    longitude=record.location.longitude,
                    altitude=record.location.altitude,
                    velocity_x=record.velocity_x,
                    velocity_y=record.velocity_y,
                    velocity_z=record.velocity_z,
                    temperature=record.temperature,
                    battery_level=record.battery_level,
                    sensors=dict(record.sensors) if record.sensors else {},
                )
                session.add(telemetry)
                session.flush()  # populate id

                broker.publish_telemetry(record.satellite_id, {
                    "record_id": telemetry.id,
                    "satellite_id": record.satellite_id,
                    "timestamp": timestamp_to_datetime(record.timestamp).isoformat(),
                    "latitude": record.location.latitude,
                    "longitude": record.location.longitude,
                    "altitude": record.location.altitude,
                    "velocity_x": record.velocity_x,
                    "velocity_y": record.velocity_y,
                    "velocity_z": record.velocity_z,
                    "temperature": record.temperature,
                    "battery_level": record.battery_level,
                    "quality_flag": validation.quality_flag,
                })
                ingested += 1

            session.commit()
            logger.info("Ingested %d telemetry records (%d failed)", ingested, failed)
            return data_service_pb2.IngestTelemetryResponse(
                records_ingested=ingested,
                records_failed=failed,
                error_messages=errors,
                response=ok_response(f"Ingested {ingested} telemetry records"),
            )
        except Exception as e:
            session.rollback()
            logger.error("Error ingesting telemetry: %s", e)
            return data_service_pb2.IngestTelemetryResponse(
                records_ingested=ingested,
                records_failed=failed + 1,
                error_messages=errors + [str(e)],
                response=error_response(500, f"Error: {e}"),
            )
        finally:
            session.close()

    def QueryTelemetry(self, request, context):
        """Query telemetry data with pagination."""
        session = db.get_session()
        try:
            query = session.query(SatelliteTelemetryModel)
            if request.satellite_ids:
                query = query.filter(
                    SatelliteTelemetryModel.satellite_id.in_(request.satellite_ids)
                )
            if request.time_range and request.time_range.start_time.seconds:
                query = query.filter(
                    SatelliteTelemetryModel.timestamp >= timestamp_to_datetime(request.time_range.start_time)
                )
            if request.time_range and request.time_range.end_time.seconds:
                query = query.filter(
                    SatelliteTelemetryModel.timestamp <= timestamp_to_datetime(request.time_range.end_time)
                )

            total = query.count()
            offset, limit, page, page_size = _page_params(request.pagination)
            results = (query.order_by(SatelliteTelemetryModel.timestamp.desc())
                       .offset(offset).limit(limit).all())

            telemetry_list = [
                data_service_pb2.SatelliteTelemetry(
                    satellite_id=r.satellite_id,
                    timestamp=datetime_to_timestamp(r.timestamp),
                    location=common_pb2.GeoLocation(
                        latitude=r.latitude, longitude=r.longitude, altitude=r.altitude
                    ),
                    velocity_x=r.velocity_x or 0.0,
                    velocity_y=r.velocity_y or 0.0,
                    velocity_z=r.velocity_z or 0.0,
                    temperature=r.temperature or 0.0,
                    battery_level=r.battery_level or 0.0,
                    sensors=r.sensors or {},
                )
                for r in results
            ]
            logger.info("Queried %d telemetry records", len(telemetry_list))
            return data_service_pb2.QueryTelemetryResponse(
                telemetry=telemetry_list,
                pagination=_pagination_response(total, page, page_size),
                response=ok_response("OK"),
            )
        except Exception as e:
            logger.error("Error querying telemetry: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return data_service_pb2.QueryTelemetryResponse(response=error_response(500, str(e)))
        finally:
            session.close()

    def StreamTelemetry(self, request, context):
        """Stream telemetry: backfill recent history, then live broker feed."""
        backfill = self.QueryTelemetry(request, context)
        for telemetry in backfill.telemetry:
            yield telemetry

        wanted = set(request.satellite_ids) if request.satellite_ids else None
        stop_event = threading.Event()

        def _watch():
            while context.is_active() and not stop_event.is_set():
                stop_event.wait(0.5)
            stop_event.set()

        threading.Thread(target=_watch, daemon=True).start()
        for payload in broker.stream(TOPIC_TELEMETRY, stop_event):
            if not context.is_active():
                break
            if wanted and payload.get("satellite_id") not in wanted:
                continue
            ts = Timestamp()
            try:
                ts.FromDatetime(datetime.fromisoformat(payload["timestamp"]))
            except Exception:  # noqa: BLE001
                ts.FromDatetime(datetime.utcnow())
            yield data_service_pb2.SatelliteTelemetry(
                satellite_id=payload.get("satellite_id", ""),
                timestamp=ts,
                location=common_pb2.GeoLocation(
                    latitude=payload.get("latitude", 0.0),
                    longitude=payload.get("longitude", 0.0),
                    altitude=payload.get("altitude", 0.0),
                ),
                velocity_x=payload.get("velocity_x", 0.0),
                velocity_y=payload.get("velocity_y", 0.0),
                velocity_z=payload.get("velocity_z", 0.0),
                temperature=payload.get("temperature", 0.0),
                battery_level=payload.get("battery_level", 0.0),
            )

    # ------------------------------------------------------------------
    # Gravity
    # ------------------------------------------------------------------
    def IngestGravity(self, request, context):
        """Batch-ingest gravity measurements with validation and streaming."""
        session = db.get_session()
        ingested, failed, errors = 0, 0, []
        try:
            for m in request.measurements:
                validation = validate_gravity(m)
                if not validation.valid:
                    failed += 1
                    errors.append(f"{m.satellite_id}: " + "; ".join(validation.errors))
                    continue

                # Combine client quality flag with validation outcome.
                quality_flag = m.quality_flag or ("good" if validation.quality_flag == 0 else "flagged")

                gravity = GravityMeasurementModel(
                    measurement_id=m.measurement_id or uuid.uuid4().hex,
                    satellite_id=m.satellite_id,
                    timestamp=timestamp_to_datetime(m.timestamp),
                    latitude=m.location.latitude,
                    longitude=m.location.longitude,
                    altitude=m.location.altitude,
                    gravity_value=m.gravity_value,
                    uncertainty=m.uncertainty,
                    quality_flag=quality_flag,
                    measurement_metadata=dict(m.metadata) if m.metadata else {},
                )
                session.add(gravity)
                session.flush()

                broker.publish_gravity(m.satellite_id, {
                    "record_id": gravity.id,
                    "measurement_id": gravity.measurement_id,
                    "satellite_id": m.satellite_id,
                    "timestamp": timestamp_to_datetime(m.timestamp).isoformat(),
                    "latitude": m.location.latitude,
                    "longitude": m.location.longitude,
                    "altitude": m.location.altitude,
                    "gravity_value": m.gravity_value,
                    "uncertainty": m.uncertainty,
                    "quality_flag": quality_flag,
                })
                ingested += 1

            session.commit()
            logger.info("Ingested %d gravity measurements (%d failed)", ingested, failed)
            return data_service_pb2.IngestGravityResponse(
                records_ingested=ingested,
                records_failed=failed,
                error_messages=errors,
                response=ok_response(f"Ingested {ingested} gravity measurements"),
            )
        except Exception as e:
            session.rollback()
            logger.error("Error ingesting gravity: %s", e)
            return data_service_pb2.IngestGravityResponse(
                records_ingested=ingested,
                records_failed=failed + 1,
                error_messages=errors + [str(e)],
                response=error_response(500, f"Error: {e}"),
            )
        finally:
            session.close()

    def QueryGravity(self, request, context):
        """Query gravity measurements with bounding-box and pagination."""
        session = db.get_session()
        try:
            query = session.query(GravityMeasurementModel)
            if request.satellite_ids:
                query = query.filter(
                    GravityMeasurementModel.satellite_id.in_(request.satellite_ids)
                )
            if request.time_range and request.time_range.start_time.seconds:
                query = query.filter(
                    GravityMeasurementModel.timestamp >= timestamp_to_datetime(request.time_range.start_time)
                )
            if request.time_range and request.time_range.end_time.seconds:
                query = query.filter(
                    GravityMeasurementModel.timestamp <= timestamp_to_datetime(request.time_range.end_time)
                )
            # Bounding box (only applied when a non-degenerate box is provided).
            if request.min_latitude or request.max_latitude or \
               request.min_longitude or request.max_longitude:
                query = query.filter(
                    GravityMeasurementModel.latitude >= request.min_latitude,
                    GravityMeasurementModel.latitude <= request.max_latitude,
                    GravityMeasurementModel.longitude >= request.min_longitude,
                    GravityMeasurementModel.longitude <= request.max_longitude,
                )
            if request.quality_filter:
                query = query.filter(
                    GravityMeasurementModel.quality_flag == request.quality_filter
                )

            total = query.count()
            offset, limit, page, page_size = _page_params(request.pagination)
            results = (query.order_by(GravityMeasurementModel.timestamp.desc())
                       .offset(offset).limit(limit).all())

            measurements = [
                data_service_pb2.GravityMeasurement(
                    measurement_id=r.measurement_id or "",
                    satellite_id=r.satellite_id,
                    timestamp=datetime_to_timestamp(r.timestamp),
                    location=common_pb2.GeoLocation(
                        latitude=r.latitude, longitude=r.longitude, altitude=r.altitude
                    ),
                    gravity_value=r.gravity_value,
                    uncertainty=r.uncertainty or 0.0,
                    quality_flag=r.quality_flag or "",
                    metadata=r.measurement_metadata or {},
                )
                for r in results
            ]
            logger.info("Queried %d gravity measurements", len(measurements))
            return data_service_pb2.QueryGravityResponse(
                measurements=measurements,
                pagination=_pagination_response(total, page, page_size),
                response=ok_response("OK"),
            )
        except Exception as e:
            logger.error("Error querying gravity: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return data_service_pb2.QueryGravityResponse(response=error_response(500, str(e)))
        finally:
            session.close()

    def StreamGravity(self, request, context):
        """Stream gravity: backfill recent history, then live broker feed."""
        backfill = self.QueryGravity(request, context)
        for measurement in backfill.measurements:
            yield measurement

        wanted = set(request.satellite_ids) if request.satellite_ids else None
        stop_event = threading.Event()

        def _watch():
            while context.is_active() and not stop_event.is_set():
                stop_event.wait(0.5)
            stop_event.set()

        threading.Thread(target=_watch, daemon=True).start()
        for payload in broker.stream(TOPIC_GRAVITY, stop_event):
            if not context.is_active():
                break
            if wanted and payload.get("satellite_id") not in wanted:
                continue
            ts = Timestamp()
            try:
                ts.FromDatetime(datetime.fromisoformat(payload["timestamp"]))
            except Exception:  # noqa: BLE001
                ts.FromDatetime(datetime.utcnow())
            yield data_service_pb2.GravityMeasurement(
                measurement_id=payload.get("measurement_id", ""),
                satellite_id=payload.get("satellite_id", ""),
                timestamp=ts,
                location=common_pb2.GeoLocation(
                    latitude=payload.get("latitude", 0.0),
                    longitude=payload.get("longitude", 0.0),
                    altitude=payload.get("altitude", 0.0),
                ),
                gravity_value=payload.get("gravity_value", 0.0),
                uncertainty=payload.get("uncertainty", 0.0),
                quality_flag=payload.get("quality_flag", ""),
            )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def ExportData(self, request, context):
        """Export queried data to CSV/JSON/Parquet, returning a download URL."""
        try:
            export_id = f"export_{uuid.uuid4().hex[:12]}"
            export_type = (request.export_type or "gravity").lower()

            records = []
            if export_type == "telemetry":
                q = data_service_pb2.QueryTelemetryRequest(
                    satellite_ids=request.satellite_ids,
                    time_range=request.time_range,
                )
                resp = self.QueryTelemetry(q, context)
                for t in resp.telemetry:
                    records.append({
                        "satellite_id": t.satellite_id,
                        "timestamp": t.timestamp.ToDatetime().isoformat(),
                        "latitude": t.location.latitude,
                        "longitude": t.location.longitude,
                        "altitude": t.location.altitude,
                        "velocity_x": t.velocity_x,
                        "velocity_y": t.velocity_y,
                        "velocity_z": t.velocity_z,
                        "temperature": t.temperature,
                        "battery_level": t.battery_level,
                    })
            else:
                q = data_service_pb2.QueryGravityRequest(
                    satellite_ids=request.satellite_ids,
                    time_range=request.time_range,
                )
                resp = self.QueryGravity(q, context)
                for m in resp.measurements:
                    records.append({
                        "measurement_id": m.measurement_id,
                        "satellite_id": m.satellite_id,
                        "timestamp": m.timestamp.ToDatetime().isoformat(),
                        "latitude": m.location.latitude,
                        "longitude": m.location.longitude,
                        "altitude": m.location.altitude,
                        "gravity_value": m.gravity_value,
                        "uncertainty": m.uncertainty,
                        "quality_flag": m.quality_flag,
                    })

            result = exporter.export(export_id, records, request.format)
            return data_service_pb2.ExportDataResponse(
                export_id=export_id,
                download_url=result["download_url"],
                file_size=0,
                expires_at=datetime_to_timestamp(datetime.utcnow()),
                response=ok_response(
                    f"Exported {result['record_count']} records as {result['format']}",
                    {"record_count": result["record_count"], "format": result["format"]},
                ),
            )
        except Exception as e:
            logger.error("Error exporting data: %s", e)
            return data_service_pb2.ExportDataResponse(
                response=error_response(500, f"Export failed: {e}")
            )

    # ------------------------------------------------------------------
    # Streaming (server-side)
    # ------------------------------------------------------------------
    def StreamTelemetry(self, request, context):
        """Stream telemetry records in real-time (gRPC server-side streaming)."""
        stop_event = threading.Event()

        try:
            logger.info("Client connected to telemetry stream")

            # Register context cancellation
            context.add_callback(lambda: stop_event.set())

            # Stream from the broker
            for record in broker.stream(TOPIC_TELEMETRY, stop_event):
                # Filter by request parameters
                sat_id = record.get("satellite_id")
                if request.satellite_ids and sat_id not in request.satellite_ids:
                    continue

                # Convert to protobuf message
                telemetry = data_service_pb2.SatelliteTelemetry(
                    satellite_id=sat_id,
                    location=common_pb2.GeoLocation(
                        latitude=record.get("latitude", 0.0),
                        longitude=record.get("longitude", 0.0),
                        altitude=record.get("altitude", 0.0),
                    ),
                    temperature=record.get("temperature", 0.0),
                    battery_level=record.get("battery_level", 0.0),
                )
                # Set timestamp from record
                if "timestamp" in record:
                    telemetry.timestamp.FromJsonString(record["timestamp"])

                yield telemetry

        except Exception as e:
            logger.error("Error streaming telemetry: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
        finally:
            stop_event.set()
            logger.info("Telemetry stream closed")

    def StreamGravity(self, request, context):
        """Stream gravity measurements in real-time (gRPC server-side streaming)."""
        stop_event = threading.Event()

        try:
            logger.info("Client connected to gravity stream")

            # Register context cancellation
            context.add_callback(lambda: stop_event.set())

            # Stream from the broker
            for record in broker.stream(TOPIC_GRAVITY, stop_event):
                # Filter by request parameters
                sat_id = record.get("satellite_id")
                if request.satellite_ids and sat_id not in request.satellite_ids:
                    continue

                # Filter by bounding box
                lat = record.get("latitude")
                lon = record.get("longitude")
                if lat is not None and lon is not None:
                    if request.min_latitude and lat < request.min_latitude:
                        continue
                    if request.max_latitude and lat > request.max_latitude:
                        continue
                    if request.min_longitude and lon < request.min_longitude:
                        continue
                    if request.max_longitude and lon > request.max_longitude:
                        continue

                # Convert to protobuf message
                measurement = data_service_pb2.GravityMeasurement(
                    measurement_id=record.get("measurement_id", ""),
                    satellite_id=sat_id,
                    gravity_value=record.get("gravity_value", 0.0),
                    uncertainty=record.get("uncertainty", 0.0),
                    quality_flag=record.get("quality_flag", "unknown"),
                    location=common_pb2.GeoLocation(
                        latitude=lat or 0.0,
                        longitude=lon or 0.0,
                        altitude=record.get("altitude", 0.0),
                    ),
                )
                if "timestamp" in record:
                    measurement.timestamp.FromJsonString(record["timestamp"])

                yield measurement

        except Exception as e:
            logger.error("Error streaming gravity: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
        finally:
            stop_event.set()
            logger.info("Gravity stream closed")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def HealthCheck(self, request, context):
        try:
            from sqlalchemy import text
            session = db.get_session()
            session.execute(text("SELECT 1"))
            session.close()
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING
            )
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                details={"error": str(e)},
            )
