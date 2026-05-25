"""
Control Service Configuration
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "Control Service"
    service_port: int = int(os.getenv("CONTROL_SERVICE_PORT", "50054"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Data Service connection
    data_service_addr: str = os.getenv("DATA_SERVICE_ADDR", "data-service:50051")

    # Simulation settings
    propagation_timestep: float = float(os.getenv("PROPAGATION_TIMESTEP", "60.0"))  # seconds
    max_propagation_duration: float = float(os.getenv("MAX_PROPAGATION_DURATION", "86400.0"))  # 24 hours

    class Config:
        env_file = ".env"


settings = Settings()
