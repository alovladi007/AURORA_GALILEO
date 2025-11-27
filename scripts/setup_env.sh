#!/bin/bash
# GeoSense Platform Environment Setup Script
#
# This script installs all required dependencies for the platform
#
# Usage:
#   chmod +x scripts/setup_env.sh
#   ./scripts/setup_env.sh

set -e

echo "=============================================="
echo "GeoSense Platform Environment Setup"
echo "=============================================="

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "[1/5] Creating virtual environment..."
    python3 -m venv venv
else
    echo ""
    echo "[1/5] Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo ""
echo "[2/5] Upgrading pip..."
pip install --upgrade pip

# Install core dependencies
echo ""
echo "[3/5] Installing core dependencies..."
pip install -q \
    fastapi>=0.100.0 \
    uvicorn[standard]>=0.23.0 \
    pydantic>=2.0.0 \
    numpy>=1.24.0 \
    scipy>=1.10.0 \
    sqlalchemy>=2.0.0 \
    alembic>=1.11.0 \
    psycopg2-binary>=2.9.0 \
    python-jose[cryptography]>=3.3.0 \
    passlib[bcrypt]>=1.7.4 \
    prometheus-client>=0.17.0 \
    slowapi>=0.1.8 \
    redis>=4.5.0 \
    celery>=5.3.0 \
    minio>=7.1.0 \
    httpx>=0.24.0 \
    websockets>=11.0 \
    python-multipart>=0.0.6

# Install JAX (for sensing and scientific computing)
echo ""
echo "[4/5] Installing JAX and ML dependencies..."

# Detect platform for JAX installation
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - use CPU-only JAX (MPS support coming)
    pip install -q jax jaxlib
else
    # Linux - try GPU first, fall back to CPU
    pip install -q --upgrade "jax[cpu]" || pip install -q jax jaxlib
fi

# Install PyTorch (for ML models)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS with MPS
    pip install -q torch torchvision
else
    # Linux - try CUDA first, fall back to CPU
    pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu 2>/dev/null || \
    pip install -q torch torchvision
fi

# Install Haiku (for neural network models)
pip install -q dm-haiku

# Install development dependencies
echo ""
echo "[5/5] Installing development dependencies..."
pip install -q \
    pytest>=7.3.0 \
    pytest-asyncio>=0.21.0 \
    pytest-cov>=4.1.0 \
    black>=23.3.0 \
    flake8>=6.0.0 \
    mypy>=1.3.0

echo ""
echo "=============================================="
echo "Environment setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Start PostgreSQL and create database:"
echo "     createdb gravity_ops"
echo ""
echo "  2. Run database migrations:"
echo "     alembic upgrade head"
echo ""
echo "  3. Create admin user:"
echo "     python scripts/init_db.py"
echo ""
echo "  4. Start the API server:"
echo "     uvicorn api.main:app --host 0.0.0.0 --port 5050 --reload"
echo ""
echo "  5. Start the UI (in another terminal):"
echo "     cd ui && npm install && npm run dev"
echo ""
