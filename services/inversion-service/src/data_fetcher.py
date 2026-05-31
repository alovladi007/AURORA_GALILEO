"""
Data Fetcher
============

gRPC client that fetches gravity measurements from the Data Service and bins
them onto a regular lat/lon grid suitable for inversion. Used when an inversion
request supplies a ``data_query`` so the inversion runs on real observations
instead of the synthetic forward model.

Degrades gracefully: if the Data Service is unreachable or returns no data, the
caller falls back to the synthetic problem.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import grpc
    from src.gen import data_service_pb2, data_service_pb2_grpc, common_pb2
    from google.protobuf.timestamp_pb2 import Timestamp

    _HAS_GRPC = True
except Exception:  # noqa: BLE001
    _HAS_GRPC = False


class GravityDataFetcher:
    """Fetches and grids gravity observations from the Data Service."""

    def __init__(self, address: Optional[str] = None):
        self.address = address or os.getenv("DATA_SERVICE_ADDR", "data-service:50051")
        self._channel = None
        self._stub = None

    def _stub_or_none(self):
        if not _HAS_GRPC:
            return None
        if self._stub is None:
            self._channel = grpc.insecure_channel(self.address)
            self._stub = data_service_pb2_grpc.DataServiceStub(self._channel)
        return self._stub

    def fetch_grid(self, query: Dict[str, str],
                   timeout: float = 10.0) -> Optional[Tuple[np.ndarray, np.ndarray, Tuple[int, int]]]:
        """Fetch gravity measurements and bin them onto a grid.

        ``query`` keys (all optional):
          satellite_ids (comma-separated), min_latitude, max_latitude,
          min_longitude, max_longitude, grid_rows, grid_cols, page_size.

        Returns (data_vector, cell_count_vector, (rows, cols)) where
        ``data_vector`` is the mean gravity value per grid cell (mGal), or None
        if no data / unavailable.
        """
        stub = self._stub_or_none()
        if stub is None:
            logger.info("gRPC unavailable; cannot fetch real data")
            return None

        rows = int(query.get("grid_rows", 12))
        cols = int(query.get("grid_cols", 12))
        min_lat = float(query.get("min_latitude", -90.0))
        max_lat = float(query.get("max_latitude", 90.0))
        min_lon = float(query.get("min_longitude", -180.0))
        max_lon = float(query.get("max_longitude", 180.0))
        sat_ids = [s for s in query.get("satellite_ids", "").split(",") if s]

        try:
            req = data_service_pb2.QueryGravityRequest(
                satellite_ids=sat_ids,
                min_latitude=min_lat,
                max_latitude=max_lat,
                min_longitude=min_lon,
                max_longitude=max_lon,
            )
            req.pagination.page = 1
            req.pagination.page_size = int(query.get("page_size", 5000))
            resp = stub.QueryGravity(req, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Data Service query failed: %s", exc)
            return None

        measurements = list(resp.measurements)
        if not measurements:
            logger.info("Data Service returned no gravity measurements")
            return None

        # Bin measurements onto the grid (mean per cell).
        accum = np.zeros(rows * cols)
        counts = np.zeros(rows * cols)
        lat_span = (max_lat - min_lat) or 1.0
        lon_span = (max_lon - min_lon) or 1.0
        for m in measurements:
            r = int((m.location.latitude - min_lat) / lat_span * (rows - 1))
            c = int((m.location.longitude - min_lon) / lon_span * (cols - 1))
            r = min(max(r, 0), rows - 1)
            c = min(max(c, 0), cols - 1)
            idx = r * cols + c
            accum[idx] += m.gravity_value
            counts[idx] += 1

        with np.errstate(invalid="ignore", divide="ignore"):
            data = np.where(counts > 0, accum / np.maximum(counts, 1), 0.0)

        logger.info("Fetched %d measurements -> %dx%d grid (%d populated cells)",
                    len(measurements), rows, cols, int((counts > 0).sum()))
        return data, counts, (rows, cols)

    def close(self):
        if self._channel is not None:
            self._channel.close()
