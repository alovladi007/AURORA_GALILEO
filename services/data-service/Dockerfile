FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY proto/ ./proto/

# Generate protobuf code
RUN python -m grpc_tools.protoc \
    --proto_path=proto \
    --python_out=src/gen \
    --grpc_python_out=src/gen \
    proto/*.proto

# Create __init__.py files
RUN touch src/gen/__init__.py

EXPOSE 50051

CMD ["python", "-m", "src.main"]
