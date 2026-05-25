"""
ML Service Configuration
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "ML Service"
    service_port: int = int(os.getenv("ML_SERVICE_PORT", "50052"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # MLflow configuration
    mlflow_tracking_uri: str = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")

    # Model storage
    model_storage_path: str = os.getenv("MODEL_STORAGE_PATH", "/app/models")

    class Config:
        env_file = ".env"


settings = Settings()
