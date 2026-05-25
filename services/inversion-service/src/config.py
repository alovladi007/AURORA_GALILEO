"""
Inversion Service Configuration
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "Inversion Service"
    service_port: int = int(os.getenv("INVERSION_SERVICE_PORT", "50053"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Data Service connection
    data_service_addr: str = os.getenv("DATA_SERVICE_ADDR", "data-service:50051")

    # ML Service connection
    ml_service_addr: str = os.getenv("ML_SERVICE_ADDR", "ml-service:50052")

    # Computation settings
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "1000"))
    convergence_threshold: float = float(os.getenv("CONVERGENCE_THRESHOLD", "1e-6"))

    class Config:
        env_file = ".env"


settings = Settings()
