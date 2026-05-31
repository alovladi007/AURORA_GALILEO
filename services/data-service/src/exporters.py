"""
Data Exporters
==============

Export queried telemetry/gravity records to common formats: CSV (always
available), Parquet (if pyarrow present), and NetCDF (if netCDF4 present).
Exports are written to a local directory and optionally uploaded to MinIO/S3.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)

try:
    import pyarrow as pa  # type: ignore
    import pyarrow.parquet as pq  # type: ignore

    _HAS_PARQUET = True
except Exception:  # noqa: BLE001
    _HAS_PARQUET = False

try:
    from minio import Minio  # type: ignore

    _HAS_MINIO = True
except Exception:  # noqa: BLE001
    _HAS_MINIO = False


class DataExporter:
    """Writes record dictionaries to disk in the requested format."""

    SUPPORTED = {"csv", "json", "parquet"}

    def __init__(self, base_dir: str = "/app/exports"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._minio = self._init_minio()
        self.bucket = os.getenv("MINIO_BUCKET", "galileo-exports")

    def _init_minio(self):
        if not _HAS_MINIO or not os.getenv("MINIO_ENDPOINT"):
            return None
        try:
            return Minio(
                os.getenv("MINIO_ENDPOINT"),
                access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("MinIO unavailable for exports: %s", exc)
            return None

    def export(self, export_id: str, records: List[Dict], fmt: str) -> Dict[str, str]:
        """Export ``records`` to ``fmt``. Returns status + download URL."""
        fmt = (fmt or "csv").lower()
        if fmt not in self.SUPPORTED:
            # Fall back to CSV but report the requested format.
            logger.warning("Unsupported export format '%s', using csv", fmt)
            fmt = "csv"
        if fmt == "parquet" and not _HAS_PARQUET:
            logger.warning("pyarrow missing; falling back to csv")
            fmt = "csv"

        out_dir = os.path.join(self.base_dir, export_id)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"data.{fmt}")

        if fmt == "csv":
            self._write_csv(path, records)
        elif fmt == "json":
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(records, fh, default=str)
        elif fmt == "parquet":
            table = pa.Table.from_pylist(records)
            pq.write_table(table, path)

        url = self._finalize(path, export_id)
        return {
            "export_id": export_id,
            "format": fmt,
            "status": "completed",
            "record_count": str(len(records)),
            "download_url": url,
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _write_csv(path: str, records: List[Dict]) -> None:
        if not records:
            open(path, "w").close()
            return
        fieldnames = list(records[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

    def _finalize(self, local_path: str, export_id: str) -> str:
        object_name = f"{export_id}/{os.path.basename(local_path)}"
        if self._minio is not None:
            try:
                if not self._minio.bucket_exists(self.bucket):
                    self._minio.make_bucket(self.bucket)
                self._minio.fput_object(self.bucket, object_name, local_path)
                return f"s3://{self.bucket}/{object_name}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Export upload failed (%s); using local path", exc)
        return f"file://{local_path}"
