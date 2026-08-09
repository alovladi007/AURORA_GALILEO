FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install gateway dependencies
COPY services/api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto definitions and generate stubs at the path src/main.py
# imports them from (gen.python.proto.*)
COPY proto/ ./proto/
RUN mkdir -p src/gen/python/proto && \
    python -m grpc_tools.protoc \
        -I proto \
        --python_out=src/gen/python/proto \
        --grpc_python_out=src/gen/python/proto \
        proto/common.proto proto/data_service.proto proto/ml_service.proto \
        proto/inversion_service.proto proto/control_service.proto && \
    touch src/gen/__init__.py src/gen/python/__init__.py src/gen/python/proto/__init__.py

# Copy the gateway application
COPY services/api-gateway/src/main.py ./src/main.py
COPY services/api-gateway/src/api/ ./src/api/

# src on the path so `gen.*` and `api.*` resolve inside src/main.py
ENV PYTHONPATH="/app/src:/app/src/gen/python/proto:/app"

# Create non-root user
RUN useradd -m -u 1000 galileo && chown -R galileo:galileo /app
USER galileo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
