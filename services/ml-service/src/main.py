"""
ML Service - gRPC Server
"""

import grpc
from concurrent import futures
import logging
import signal
import sys
import os

from src.gen import ml_service_pb2_grpc
from src.service import MLServicer
from src.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def serve():
    """Start the gRPC server"""
    # Ensure model storage directory exists
    os.makedirs(settings.model_storage_path, exist_ok=True)

    # Create gRPC server
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )

    # Add servicer
    ml_service_pb2_grpc.add_MLServiceServicer_to_server(
        MLServicer(), server
    )

    # Bind to port
    server.add_insecure_port(f'[::]:{settings.service_port}')

    # Start server
    server.start()
    logger.info(f"{settings.service_name} started on port {settings.service_port}")

    # Graceful shutdown handler
    def handle_shutdown(signum, frame):
        logger.info("Shutting down gracefully...")
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
        server.stop(grace=5)


if __name__ == '__main__':
    serve()
