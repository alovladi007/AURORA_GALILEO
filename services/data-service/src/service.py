"""
Data Service gRPC implementation
"""

import grpc
from datetime import datetime
from typing import Iterator
import logging

from gen import data_service_pb2, data_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from .database import db, SatelliteTelemetryModel, GravityMeasurementModel

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def timestamp_to_datetime(ts: Timestamp) -> datetime:
    """Convert protobuf Timestamp to datetime"""
    return ts.ToDatetime()


class DataServicer(data_service_pb2_grpc.DataServiceServicer):
    """Data Service implementation"""

    def IngestTelemetry(self, request, context):
        """Ingest satellite telemetry data"""
        try:
            session = db.get_session()

            # Create telemetry record
            telemetry = SatelliteTelemetryModel(
                satellite_id=request.satellite_id,
                timestamp=timestamp_to_datetime(request.timestamp),
                latitude=request.location.latitude,
                longitude=request.location.longitude,
                altitude=request.location.altitude,
                velocity_x=request.velocity_x,
                velocity_y=request.velocity_y,
                velocity_z=request.velocity_z,
                temperature=request.temperature,
                battery_level=request.battery_level,
                sensors=dict(request.sensors) if request.sensors else {}
            )

            session.add(telemetry)
            session.commit()

            logger.info(f"Ingested telemetry for satellite {request.satellite_id}")

            return common_pb2.Response(
                success=True,
                message=f"Telemetry ingested for {request.satellite_id}",
                data={"record_id": str(telemetry.id)}
            )

        except Exception as e:
            logger.error(f"Error ingesting telemetry: {e}")
            session.rollback()
            return common_pb2.Response(
                success=False,
                message=f"Error: {str(e)}",
                error=common_pb2.Error(
                    code="INGEST_ERROR",
                    message=str(e)
                )
            )
        finally:
            session.close()

    def QueryTelemetry(self, request, context):
        """Query telemetry data"""
        try:
            session = db.get_session()

            # Build query
            query = session.query(SatelliteTelemetryModel)

            # Filter by satellite IDs
            if request.satellite_ids:
                query = query.filter(
                    SatelliteTelemetryModel.satellite_id.in_(request.satellite_ids)
                )

            # Filter by time range
            if request.time_range and request.time_range.start_time:
                query = query.filter(
                    SatelliteTelemetryModel.timestamp >= timestamp_to_datetime(request.time_range.start_time)
                )

            if request.time_range and request.time_range.end_time:
                query = query.filter(
                    SatelliteTelemetryModel.timestamp <= timestamp_to_datetime(request.time_range.end_time)
                )

            # Pagination
            if request.pagination:
                query = query.offset(request.pagination.offset)
                query = query.limit(request.pagination.limit)

            # Order by timestamp
            query = query.order_by(SatelliteTelemetryModel.timestamp.desc())

            # Execute query
            results = query.all()

            # Convert to protobuf
            telemetry_list = []
            for record in results:
                telemetry_list.append(
                    data_service_pb2.SatelliteTelemetry(
                        satellite_id=record.satellite_id,
                        timestamp=datetime_to_timestamp(record.timestamp),
                        location=common_pb2.GeoLocation(
                            latitude=record.latitude,
                            longitude=record.longitude,
                            altitude=record.altitude
                        ),
                        velocity_x=record.velocity_x or 0.0,
                        velocity_y=record.velocity_y or 0.0,
                        velocity_z=record.velocity_z or 0.0,
                        temperature=record.temperature or 0.0,
                        battery_level=record.battery_level or 0.0,
                        sensors=record.sensors or {}
                    )
                )

            logger.info(f"Queried {len(telemetry_list)} telemetry records")

            return data_service_pb2.TelemetryQueryResponse(
                telemetry=telemetry_list,
                pagination=common_pb2.PaginationResponse(
                    total=query.count(),
                    offset=request.pagination.offset if request.pagination else 0,
                    limit=request.pagination.limit if request.pagination else len(telemetry_list)
                )
            )

        except Exception as e:
            logger.error(f"Error querying telemetry: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return data_service_pb2.TelemetryQueryResponse()
        finally:
            session.close()

    def StreamTelemetry(self, request, context):
        """Stream telemetry data in real-time"""
        # For now, just return existing data
        # In production, this would use a pub/sub system
        response = self.QueryTelemetry(request, context)
        for telemetry in response.telemetry:
            yield telemetry

    def IngestGravity(self, request, context):
        """Ingest gravity measurement data"""
        try:
            session = db.get_session()

            # Create gravity record
            gravity = GravityMeasurementModel(
                satellite_id=request.satellite_id,
                timestamp=timestamp_to_datetime(request.timestamp),
                latitude=request.location.latitude,
                longitude=request.location.longitude,
                altitude=request.location.altitude,
                gravity_x=request.gravity_x,
                gravity_y=request.gravity_y,
                gravity_z=request.gravity_z,
                gravity_magnitude=request.magnitude,
                accuracy=request.accuracy,
                quality_flag=request.quality_flag
            )

            session.add(gravity)
            session.commit()

            logger.info(f"Ingested gravity measurement for satellite {request.satellite_id}")

            return common_pb2.Response(
                success=True,
                message=f"Gravity measurement ingested for {request.satellite_id}",
                data={"record_id": str(gravity.id)}
            )

        except Exception as e:
            logger.error(f"Error ingesting gravity: {e}")
            session.rollback()
            return common_pb2.Response(
                success=False,
                message=f"Error: {str(e)}",
                error=common_pb2.Error(
                    code="INGEST_ERROR",
                    message=str(e)
                )
            )
        finally:
            session.close()

    def QueryGravity(self, request, context):
        """Query gravity measurement data"""
        try:
            session = db.get_session()

            # Build query
            query = session.query(GravityMeasurementModel)

            # Filter by satellite IDs
            if request.satellite_ids:
                query = query.filter(
                    GravityMeasurementModel.satellite_id.in_(request.satellite_ids)
                )

            # Filter by time range
            if request.time_range and request.time_range.start_time:
                query = query.filter(
                    GravityMeasurementModel.timestamp >= timestamp_to_datetime(request.time_range.start_time)
                )

            if request.time_range and request.time_range.end_time:
                query = query.filter(
                    GravityMeasurementModel.timestamp <= timestamp_to_datetime(request.time_range.end_time)
                )

            # Filter by region (bounding box)
            if request.region:
                query = query.filter(
                    GravityMeasurementModel.latitude >= request.region.min_latitude,
                    GravityMeasurementModel.latitude <= request.region.max_latitude,
                    GravityMeasurementModel.longitude >= request.region.min_longitude,
                    GravityMeasurementModel.longitude <= request.region.max_longitude
                )

            # Pagination
            if request.pagination:
                query = query.offset(request.pagination.offset)
                query = query.limit(request.pagination.limit)

            # Order by timestamp
            query = query.order_by(GravityMeasurementModel.timestamp.desc())

            # Execute query
            results = query.all()

            # Convert to protobuf
            measurements = []
            for record in results:
                measurements.append(
                    data_service_pb2.GravityMeasurement(
                        satellite_id=record.satellite_id,
                        timestamp=datetime_to_timestamp(record.timestamp),
                        location=common_pb2.GeoLocation(
                            latitude=record.latitude,
                            longitude=record.longitude,
                            altitude=record.altitude
                        ),
                        gravity_x=record.gravity_x,
                        gravity_y=record.gravity_y,
                        gravity_z=record.gravity_z,
                        magnitude=record.gravity_magnitude,
                        accuracy=record.accuracy or 0.0,
                        quality_flag=record.quality_flag or 0
                    )
                )

            logger.info(f"Queried {len(measurements)} gravity measurements")

            return data_service_pb2.GravityQueryResponse(
                measurements=measurements,
                pagination=common_pb2.PaginationResponse(
                    total=query.count(),
                    offset=request.pagination.offset if request.pagination else 0,
                    limit=request.pagination.limit if request.pagination else len(measurements)
                )
            )

        except Exception as e:
            logger.error(f"Error querying gravity: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return data_service_pb2.GravityQueryResponse()
        finally:
            session.close()

    def StreamGravity(self, request, context):
        """Stream gravity measurements in real-time"""
        # For now, just return existing data
        response = self.QueryGravity(request, context)
        for measurement in response.measurements:
            yield measurement

    def ExportData(self, request, context):
        """Export data in specified format"""
        # Simplified implementation
        return common_pb2.Response(
            success=True,
            message="Data export initiated",
            data={
                "export_id": "export_001",
                "format": request.format,
                "status": "processing"
            }
        )

    def HealthCheck(self, request, context):
        """Health check endpoint"""
        try:
            # Test database connection
            session = db.get_session()
            session.execute("SELECT 1")
            session.close()

            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING,
                message="Data Service is healthy"
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                message=f"Unhealthy: {str(e)}"
            )
