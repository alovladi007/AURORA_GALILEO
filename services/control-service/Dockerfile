FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/control-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files from root
COPY proto/ ./proto/

# Copy application
COPY services/control-service/src/ ./src/

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

EXPOSE 50054

CMD ["python", "-m", "src.main"]
