from minio import Minio
from minio.error import S3Error
import os
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

def get_minio_client() -> Minio:
    """Get MinIO client instance"""
    return Minio(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        secure=False
    )

def upload_to_minio(client: Minio, bucket: str, key: str, data: bytes) -> bool:
    """Upload data to MinIO"""
    try:
        # Ensure bucket exists
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        
        # Upload data
        data_stream = BytesIO(data)
        client.put_object(
            bucket_name=bucket,
            object_name=key,
            data=data_stream,
            length=len(data)
        )
        logger.info(f"Uploaded {key} to bucket {bucket}")
        return True
        
    except S3Error as e:
        logger.error(f"Failed to upload {key} to {bucket}: {e}")
        return False

def download_from_minio(client: Minio, bucket: str, key: str) -> Optional[bytes]:
    """Download data from MinIO"""
    try:
        response = client.get_object(bucket, key)
        data = response.read()
        response.close()
        response.release_conn()
        logger.info(f"Downloaded {key} from bucket {bucket}")
        return data
        
    except S3Error as e:
        logger.error(f"Failed to download {key} from {bucket}: {e}")
        return None

def list_objects(client: Minio, bucket: str, prefix: str = "") -> list:
    """List objects in MinIO bucket"""
    try:
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
        
    except S3Error as e:
        logger.error(f"Failed to list objects in {bucket}: {e}")
        return []

def delete_object(client: Minio, bucket: str, key: str) -> bool:
    """Delete object from MinIO"""
    try:
        client.remove_object(bucket, key)
        logger.info(f"Deleted {key} from bucket {bucket}")
        return True
        
    except S3Error as e:
        logger.error(f"Failed to delete {key} from {bucket}: {e}")
        return False

def get_presigned_url(client: Minio, bucket: str, key: str, expiry: int = 3600) -> Optional[str]:
    """Get presigned URL for object access"""
    try:
        url = client.presigned_get_object(bucket, key, expires=expiry)
        return url
        
    except S3Error as e:
        logger.error(f"Failed to generate presigned URL for {key}: {e}")
        return None
