"""
Extended REST routes for the API Gateway (Phase 2 W2.4).

Exposes the gRPC RPCs that already existed in the services but were
never mounted on the gateway - the root cause of the UI's "phantom
endpoint" drift. Every route here calls a real service stub; responses
are protobuf->JSON via MessageToDict.

The router is built by ``build_extended_router`` so it can borrow the
gateway's channel manager and auth dependency without circular imports.
"""

from typing import Any, Callable, Dict, List, Optional

import grpc
from fastapi import APIRouter, Depends, HTTPException, Query, status
from google.protobuf.json_format import MessageToDict
from google.protobuf.timestamp_pb2 import Timestamp

from gen.python.proto import (
    common_pb2,
    control_service_pb2,
    data_service_pb2,
    inversion_service_pb2,
    ml_service_pb2,
)


def _ts(iso: str) -> Timestamp:
    t = Timestamp()
    t.FromJsonString(iso)
    return t


def _grpc_http_error(e: grpc.RpcError, service: str) -> HTTPException:
    if e.code() == grpc.StatusCode.NOT_FOUND:
        return HTTPException(status_code=404, detail=e.details())
    if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
        return HTTPException(status_code=422, detail=e.details())
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{service} error: {e.details()}",
    )


def build_extended_router(grpc_manager, get_user_context: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["extended"])

    # ── Data service: gravity + export ────────────────────────────────
    @router.post("/data/gravity")
    async def ingest_gravity(
        body: Dict[str, Any],
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            measurements = []
            for m in body.get("measurements", []):
                meas = data_service_pb2.GravityMeasurement(
                    satellite_id=m["satellite_id"],
                    location=common_pb2.GeoLocation(
                        latitude=m["location"]["latitude"],
                        longitude=m["location"]["longitude"],
                        altitude=m["location"].get("altitude", 0.0),
                    ),
                    gravity_value=m["gravity_value"],
                    uncertainty=m.get("uncertainty", 0.0),
                    quality_flag=m.get("quality_flag", ""),
                )
                if "timestamp" in m:
                    meas.timestamp.CopyFrom(_ts(m["timestamp"]))
                measurements.append(meas)
            resp = await grpc_manager.stubs["data"].IngestGravity(
                data_service_pb2.IngestGravityRequest(
                    measurements=measurements, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "data service")
        except KeyError as e:
            raise HTTPException(status_code=422, detail=f"missing field {e}")

    @router.get("/data/gravity")
    async def query_gravity(
        satellite_ids: Optional[List[str]] = Query(None),
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        min_latitude: float = -90.0,
        max_latitude: float = 90.0,
        min_longitude: float = -180.0,
        max_longitude: float = 180.0,
        page: int = 1,
        page_size: int = 100,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            req = data_service_pb2.QueryGravityRequest(
                satellite_ids=satellite_ids or [],
                min_latitude=min_latitude,
                max_latitude=max_latitude,
                min_longitude=min_longitude,
                max_longitude=max_longitude,
                pagination=common_pb2.PaginationRequest(
                    page=page, page_size=page_size
                ),
                user_context=user_context,
            )
            if start_time and end_time:
                # TimeRange fields are protobuf Timestamps, not strings
                req.time_range.start_time.FromJsonString(start_time)
                req.time_range.end_time.FromJsonString(end_time)
            resp = await grpc_manager.stubs["data"].QueryGravity(req)
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "data service")

    @router.post("/data/export")
    async def export_data(
        body: Dict[str, Any],
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            req = data_service_pb2.ExportDataRequest(
                export_type=body["export_type"],
                satellite_ids=body.get("satellite_ids", []),
                format=body.get("format", "csv"),
                user_context=user_context,
            )
            if body.get("start_time") and body.get("end_time"):
                req.time_range.CopyFrom(
                    common_pb2.TimeRange(
                        start_time=body["start_time"], end_time=body["end_time"]
                    )
                )
            resp = await grpc_manager.stubs["data"].ExportData(req)
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "data service")
        except KeyError as e:
            raise HTTPException(status_code=422, detail=f"missing field {e}")

    # ── ML service: model lifecycle ───────────────────────────────────
    @router.get("/models")
    async def list_models(
        model_type: str = "",
        status_filter: str = Query("", alias="status"),
        page: int = 1,
        page_size: int = 50,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["ml"].ListModels(
                ml_service_pb2.ListModelsRequest(
                    model_type=model_type,
                    status=status_filter,
                    pagination=common_pb2.PaginationRequest(
                        page=page, page_size=page_size
                    ),
                    user_context=user_context,
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "ml service")

    @router.get("/models/train/{job_id}")
    async def get_training_status(
        job_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["ml"].GetTrainingStatus(
                ml_service_pb2.TrainingStatusRequest(job_id=job_id)
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "ml service")

    @router.post("/models/{model_id}/deploy")
    async def deploy_model(
        model_id: str,
        body: Dict[str, Any],
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["ml"].DeployModel(
                ml_service_pb2.DeployModelRequest(
                    model_id=model_id,
                    deployment_name=body.get("deployment_name", model_id),
                    num_replicas=body.get("num_replicas", 1),
                    instance_type=body.get("instance_type", ""),
                    user_context=user_context,
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "ml service")

    @router.delete("/models/{model_id}")
    async def delete_model(
        model_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["ml"].DeleteModel(
                ml_service_pb2.DeleteModelRequest(
                    model_id=model_id, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "ml service")

    # ── Inversion service: list / results / cancel ────────────────────
    @router.get("/inversions")
    async def list_inversions(
        status_filter: str = Query("", alias="status"),
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            req = inversion_service_pb2.ListInversionsRequest(
                status=status_filter,
                pagination=common_pb2.PaginationRequest(
                    page=page, page_size=page_size
                ),
                user_context=user_context,
            )
            if start_time and end_time:
                # TimeRange fields are protobuf Timestamps, not strings
                req.time_range.start_time.FromJsonString(start_time)
                req.time_range.end_time.FromJsonString(end_time)
            resp = await grpc_manager.stubs["inversion"].ListInversions(req)
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "inversion service")

    @router.get("/inversions/{job_id}/results")
    async def get_inversion_results(
        job_id: str,
        format: str = "netcdf",
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["inversion"].GetInversionResults(
                inversion_service_pb2.GetInversionResultsRequest(
                    job_id=job_id, format=format, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "inversion service")

    @router.get("/inversions/{job_id}/model")
    async def get_inversion_model(
        job_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        """Georeferenced inversion model grid for map rendering."""
        try:
            resp = await grpc_manager.stubs["inversion"].GetDensityModel(
                inversion_service_pb2.GetDensityModelRequest(
                    job_id=job_id, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "inversion service")

    @router.delete("/inversions/{job_id}")
    async def cancel_inversion(
        job_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["inversion"].CancelInversion(
                inversion_service_pb2.CancelInversionRequest(
                    job_id=job_id, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "inversion service")

    # ── Control service: satellite status / commands / orbit ──────────
    @router.get("/satellites/{satellite_id}")
    async def get_satellite_status(
        satellite_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["control"].GetSatelliteStatus(
                control_service_pb2.GetSatelliteStatusRequest(
                    satellite_id=satellite_id, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "control service")

    @router.get("/commands/{command_id}")
    async def get_command_status(
        command_id: str,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["control"].GetCommandStatus(
                control_service_pb2.GetCommandStatusRequest(
                    command_id=command_id, user_context=user_context
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "control service")

    @router.get("/satellites/{satellite_id}/orbit")
    async def get_orbit_prediction(
        satellite_id: str,
        start_time: str,
        end_time: str,
        time_step_seconds: int = 60,
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ):
        try:
            resp = await grpc_manager.stubs["control"].GetOrbitPrediction(
                control_service_pb2.GetOrbitPredictionRequest(
                    satellite_id=satellite_id,
                    start_time=_ts(start_time),
                    end_time=_ts(end_time),
                    time_step_seconds=time_step_seconds,
                    user_context=user_context,
                )
            )
            return MessageToDict(resp, preserving_proto_field_name=True)
        except grpc.RpcError as e:
            raise _grpc_http_error(e, "control service")

    return router
