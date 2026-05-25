"""
Configuration for Data Service
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Service settings"""

    # Service
    service_name: str = "data-service"
    service_port: int = 50051

    # Database
    database_url: str = "postgresql://galileo:galileo_dev_password@localhost:27432/galileo"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
