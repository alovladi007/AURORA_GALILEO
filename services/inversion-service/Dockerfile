FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    gfortran \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/inversion-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files from root
COPY proto/ ./proto/

# Copy application
COPY services/inversion-service/src/ ./src/

# Shipped ML artifacts + the completion module (Phase 4): the engine's
# ml_completion method loads ml/models/gravity_completion_v1.json
COPY ml/__init__.py ./ml/__init__.py
COPY ml/gravity_completion.py ./ml/gravity_completion.py
COPY ml/models/ ./ml/models/

# Create gen directory for protobuf output
RUN mkdir -p src/gen

# Generate protobuf code
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src/gen \
    --grpc_python_out=src/gen \
    proto/*.proto

# Create __init__.py files
RUN touch src/gen/__init__.py

# Add gen directory to PYTHONPATH so imports work
ENV PYTHONPATH="/app/src/gen:${PYTHONPATH}"

EXPOSE 50053

CMD ["python", "-m", "src.main"]
