"""
Data Service - gRPC Server
"""

import grpc
from concurrent import futures
import logging
import signal
import sys
import time

from src.gen import data_service_pb2_grpc
from src.service import DataServicer
from src.database import db
from src.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def serve():
    """Start the gRPC server"""
    # Connect to database
    logger.info("Connecting to database...")
    db.connect()

    # Create gRPC server
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )

    # Add servicer
    data_service_pb2_grpc.add_DataServiceServicer_to_server(
        DataServicer(), server
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
        db.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Wait for termination
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
        server.stop(grace=5)
        db.close()


if __name__ == '__main__':
    serve()
