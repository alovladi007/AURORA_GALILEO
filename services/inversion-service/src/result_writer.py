"""
Result Writer
=============

Serializes inversion results to disk (and optionally MinIO/S3) in NetCDF when
available, falling back to compressed NumPy ``.npz`` and JSON metadata. Returns
URLs that downstream services / the gateway can expose to clients.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Optional NetCDF support.
try:
    from netCDF4 import Dataset  # type: ignore

    _HAS_NETCDF = True
except Exception:  # noqa: BLE001
    _HAS_NETCDF = False

# Optional MinIO/S3 upload.
try:
    from minio import Minio  # type: ignore

    _HAS_MINIO = True
except Exception:  # noqa: BLE001
    _HAS_MINIO = False


class ResultWriter:
    """Writes density/gravity-field results and uploads them if MinIO is set."""

    def __init__(self, base_dir: str = "/app/results"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._minio = self._init_minio()
        self.bucket = os.getenv("MINIO_BUCKET", "galileo-inversions")

    def _init_minio(self) -> Optional["Minio"]:
        if not _HAS_MINIO:
            return None
        endpoint = os.getenv("MINIO_ENDPOINT")
        if not endpoint:
            return None
        try:
            client = Minio(
                endpoint,
                access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            )
            return client
        except Exception as exc:  # noqa: BLE001
            logger.warning("MinIO unavailable, using local storage: %s", exc)
            return None

    def write(self, job_id: str, model: np.ndarray, grid_shape: tuple[int, int],
              metadata: Dict[str, str],
              uncertainties: Optional[np.ndarray] = None) -> Dict[str, str]:
        """Persist the inversion model. Returns dict of artifact URLs."""
        job_dir = os.path.join(self.base_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)

        grid = model.reshape(grid_shape)
        urls: Dict[str, str] = {}

        # Primary gravity/density field.
        if _HAS_NETCDF:
            field_path = os.path.join(job_dir, "field.nc")
            self._write_netcdf(field_path, grid, uncertainties, grid_shape, metadata)
        else:
            field_path = os.path.join(job_dir, "field.npz")
            arrays = {"model": grid}
            if uncertainties is not None:
                arrays["uncertainty"] = uncertainties.reshape(grid_shape)
            np.savez_compressed(field_path, **arrays)
        urls["gravity_field_url"] = self._finalize(field_path, job_id)

        # Coefficients / metadata JSON.
        coeff_path = os.path.join(job_dir, "coefficients.json")
        with open(coeff_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "job_id": job_id,
                    "grid_shape": list(grid_shape),
                    "n_parameters": int(model.size),
                    "model_stats": {
                        "min": float(np.min(model)),
                        "max": float(np.max(model)),
                        "mean": float(np.mean(model)),
                        "l2_norm": float(np.linalg.norm(model)),
                    },
                    "metadata": metadata,
                    "written_at": datetime.utcnow().isoformat(),
                },
                fh,
                indent=2,
            )
        urls["coefficients_url"] = self._finalize(coeff_path, job_id)
        return urls

    def _write_netcdf(self, path, grid, uncertainties, grid_shape, metadata):
        ds = Dataset(path, "w", format="NETCDF4")
        try:
            ds.createDimension("y", grid_shape[0])
            ds.createDimension("x", grid_shape[1])
            var = ds.createVariable("density", "f8", ("y", "x"), zlib=True)
            var[:, :] = grid
            var.units = "kg/m^3 (anomaly)"
            if uncertainties is not None:
                unc = ds.createVariable("uncertainty", "f8", ("y", "x"), zlib=True)
                unc[:, :] = uncertainties.reshape(grid_shape)
            for key, value in metadata.items():
                setattr(ds, key, str(value))
        finally:
            ds.close()

    def _finalize(self, local_path: str, job_id: str) -> str:
        """Upload to MinIO if configured; otherwise return a file URL."""
        object_name = f"{job_id}/{os.path.basename(local_path)}"
        if self._minio is not None:
            try:
                if not self._minio.bucket_exists(self.bucket):
                    self._minio.make_bucket(self.bucket)
                self._minio.fput_object(self.bucket, object_name, local_path)
                return f"s3://{self.bucket}/{object_name}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("MinIO upload failed (%s); using local path", exc)
        return f"file://{local_path}"
