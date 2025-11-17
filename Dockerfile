# GALILEO V2.0 - Production Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Builder
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libopenblas0 \
    liblapack3 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd -r galileo && useradd -r -g galileo galileo

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=galileo:galileo . /app/

# Create necessary directories
RUN mkdir -p /app/data /app/checkpoints /app/logs && \
    chown -R galileo:galileo /app/data /app/checkpoints /app/logs

# Switch to non-root user
USER galileo

# Expose ports
EXPOSE 5050 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5050/health || exit 1

# Default command (can be overridden in docker-compose.yml)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5050", "--workers", "2"]
