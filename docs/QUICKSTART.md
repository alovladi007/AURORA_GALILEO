# GALILEO V2.0 Quick Start Guide

## Overview

GALILEO V2.0 is a comprehensive platform for space-based geophysical sensing, combining satellite gravimetry, magnetics, and multi-sensor data fusion. This guide will help you get started quickly.

## Table of Contents

1. [Installation](#installation)
2. [Basic Usage](#basic-usage)
3. [Module Overview](#module-overview)
4. [Example Workflows](#example-workflows)
5. [Testing](#testing)
6. [Benchmarking](#benchmarking)

---

## Installation

### Prerequisites

- **Python**: 3.9, 3.10, or 3.11
- **Rust**: 1.70+ (for control module)
- **System Dependencies**:
  - BLAS/LAPACK libraries (for Rust tests)
  - PostgreSQL (optional, for data backend)
  - Redis (optional, for caching)

### Quick Install

```bash
# Clone repository
git clone https://github.com/alovladi007/GALILEO-V2.0.git
cd GALILEO-V2.0

# Install Python dependencies
pip install -r requirements.txt

# Build Rust control module
cd control-rs
cargo build --release
cd ..

# Run tests (optional)
pytest tests/
```

### Docker Installation

```bash
# Build and run with Docker Compose
docker-compose up -d

# Access services
# - Backend API: http://localhost:8000
# - PostgreSQL: localhost:5432
# - Redis: localhost:6379
```

---

## Basic Usage

### 1. Time and Relativity

Convert between time scales and apply relativistic corrections:

```python
from time.timescales import tai_to_gps, gps_to_utc
from time.relativity import gravitational_redshift

# Time conversion
gps_time = tai_to_gps(tai_seconds=1234567890.0)
utc_time = gps_to_utc(gps_time)

# Gravitational redshift (satellite at altitude)
dt = gravitational_redshift(
    altitude=400e3,  # 400 km
    dt_proper=1.0,   # 1 second proper time
)
print(f"Time dilation: {dt - 1.0:.3e} seconds")
```

### 2. Precise Orbit Determination (POD)

Estimate satellite orbit from GNSS measurements:

```python
from pod.measurements import GNSSMeasurement
from pod.estimator import BatchLeastSquares

# Create GNSS measurements
measurements = [
    GNSSMeasurement(
        time=t,
        pseudorange=pr,
        satellite_position=sv_pos,
        satellite_velocity=sv_vel,
    )
    for t, pr, sv_pos, sv_vel in gnss_data
]

# Run batch least squares
estimator = BatchLeastSquares()
state_estimate = estimator.estimate(measurements)

print(f"Position: {state_estimate.position} m")
print(f"Velocity: {state_estimate.velocity} m/s")
```

### 3. Data Fusion

Perform joint inversion of gravity and magnetic data:

```python
from fusion.joint_inversion import JointInversionProblem, solve_joint_inversion
from fusion.regularization import StructuralCouplingRegularization

# Set up problem
problem = JointInversionProblem(
    n_params=1000,  # Model parameters
    n_data1=300,    # Gravity observations
    n_data2=300,    # Magnetic observations
)

problem.set_initial_model(initial_guess)
problem.set_forward_operator1(gravity_operator)
problem.set_forward_operator2(magnetic_operator)

# Create regularization
reg = StructuralCouplingRegularization(
    lambda_cross_grad=1.0,
    lambda_sparsity=0.1,
    lambda_tv=0.05,
)

# Solve
result = solve_joint_inversion(
    problem=problem,
    data1=gravity_data,
    data2=magnetic_data,
    regularization=reg,
    max_iterations=50,
)

print(f"Converged: {result['converged']}")
print(f"Iterations: {result['n_iterations']}")
print(f"Final misfit: {result['final_misfit']:.3e}")
```

### 4. Hardware-in-the-Loop (HIL)

Emulate optical bench for inter-satellite ranging:

```python
from hil.optical_bench import OpticalBenchEmulator
from hil.drivers import MockTimingCard

# Create emulator
emulator = OpticalBenchEmulator(
    sampling_rate=10.0,  # Hz
    seed=42,
)

# Measure inter-satellite range
true_range = 200e3  # 200 km
measured_phase, diagnostics = emulator.measure_phase(true_range)

# Convert to range
wavelength = emulator.laser.wavelength
measured_range = measured_phase * wavelength

print(f"True range: {true_range:.1f} m")
print(f"Measured range: {measured_range:.1f} m")
print(f"Error: {measured_range - true_range:.3f} m")
print(f"Noise RMS: {diagnostics['total_noise_rms']:.3e} cycles")
```

### 5. Data Cataloging (STAC)

Create and manage spatiotemporal asset catalogs:

```python
from data.stac import STACCatalog, create_gravity_map_item, create_gravity_collection

# Create catalog
catalog = STACCatalog(catalog_id="my-data")

# Add collection
collection = create_gravity_collection(
    collection_id="gravity-maps",
    title="Gravity Field Maps",
)
catalog.add_collection(collection)

# Add data item
item = create_gravity_map_item(
    gravity_file="/data/gravity_map_2024.tif",
    bbox=[-180, -90, 180, 90],  # Global
    datetime_str="2024-01-01T00:00:00Z",
    collection_id="gravity-maps",
)
catalog.add_item(item)

# Search catalog
results = catalog.search(
    bbox=[-10, 30, 10, 50],  # Europe
    collections=["gravity-maps"],
)
print(f"Found {len(results)} items")

# Export to filesystem
catalog.export("./stac-catalog")
```

---

## Module Overview

### Core Modules

| Module | Description | Key Features |
|--------|-------------|--------------|
| **time** | Time scales & relativity | TAI/GPS/UTC, leap seconds, gravitational/SR corrections |
| **pod** | Precise orbit determination | GNSS measurements, batch LS, SRIF, RTS smoother |
| **telemetry** | CCSDS telemetry | Primary/secondary headers, pack/unpack |
| **fusion** | Multi-sensor fusion | Joint inversion, regularization, GNN |
| **hil** | Hardware-in-the-loop | Optical bench, timing cards, ADC drivers |
| **data** | Data cataloging | STAC implementation, search, export |

### Rust Modules (High Performance)

| Module | Description | Performance |
|--------|-------------|-------------|
| **control-rs/lqr** | Linear Quadratic Regulator | 10-100x faster than Python |
| **control-rs/mpc** | Model Predictive Control | Sparse QP with OSQP |
| **control-rs/navigation** | EKF/UKF filters | Real-time capable |
| **control-rs/lqg** | LQG controller | Combined control + estimation |

---

## Example Workflows

### Workflow 1: Complete Fusion Pipeline

```python
"""
Complete workflow: Generate synthetic data → Invert → Catalog results
"""

import numpy as np
from fusion.joint_inversion import JointInversionProblem, solve_joint_inversion
from fusion.regularization import StructuralCouplingRegularization
from data.stac import STACCatalog, create_gravity_map_item

# 1. Generate synthetic data
nx, ny = 50, 50
n_params = nx * ny

# True model (compact anomaly)
true_model = np.zeros((ny, nx))
true_model[20:30, 20:30] = 500.0  # kg/m^3

# Forward operator
np.random.seed(42)
n_obs = 200
G = np.random.randn(n_obs, n_params) * 0.05

# Observations
d_true = G @ true_model.flatten()
d_obs = d_true + np.random.randn(n_obs) * 1.0

# 2. Solve inversion
problem = JointInversionProblem(n_params=n_params, n_data1=n_obs, n_data2=0)
problem.set_initial_model(np.zeros(n_params))
problem.set_forward_operator1(G)

reg = StructuralCouplingRegularization(lambda_tv=0.1)

result = solve_joint_inversion(
    problem=problem,
    data1=d_obs,
    data2=np.array([]),
    regularization=reg,
    max_iterations=30,
)

# 3. Catalog results
catalog = STACCatalog(catalog_id="fusion-results")

item = create_gravity_map_item(
    gravity_file="results/inverted_model.tif",
    bbox=[-10, 30, 10, 50],
    datetime_str="2024-01-01T00:00:00Z",
    metadata={
        'iterations': result['n_iterations'],
        'misfit': float(result['final_misfit']),
    },
)
catalog.add_item(item)

catalog.export("./fusion_results")

print(f"✓ Inversion converged in {result['n_iterations']} iterations")
print(f"✓ Results exported to ./fusion_results")
```

### Workflow 2: HIL Measurement Campaign

```python
"""
HIL workflow: Set up hardware → Run measurements → Analyze results
"""

from hil.optical_bench import OpticalBenchEmulator
from hil.drivers import MockTimingCard, ScenarioRunner
import numpy as np

# 1. Initialize hardware
timing_card = MockTimingCard()
timing_card.reset()

emulator = OpticalBenchEmulator(sampling_rate=10.0, seed=42)

# 2. Define measurement scenario
def orbital_ranging_scenario(timing_card, adc, duration=10.0):
    """Measure inter-satellite range during orbit."""
    measurements = []

    baseline = 200e3
    for i in range(100):
        t = timing_card.read_time()

        # Orbital variation
        range_var = baseline * (1 + 0.01 * np.sin(2 * np.pi * t / 3600.0))

        # Measure
        phase, diag = emulator.measure_phase(range_var)

        measurements.append({
            'time': t,
            'phase': phase,
            'noise': diag['total_noise_rms'],
        })

    return {'measurements': measurements}

# 3. Run scenario
runner = ScenarioRunner(timing_card=timing_card)
runner.register_scenario('orbital_ranging', orbital_ranging_scenario)

results = runner.run_scenario('orbital_ranging')

# 4. Analyze
measurements = results['measurements']
noise_levels = [m['noise'] for m in measurements]

print(f"✓ Collected {len(measurements)} measurements")
print(f"✓ Mean noise: {np.mean(noise_levels):.3e} cycles")
print(f"✓ Max noise: {np.max(noise_levels):.3e} cycles")
```

---

## Testing

### Run Unit Tests

```bash
# Run all tests
pytest tests/

# Run specific module tests
pytest tests/fusion/
pytest tests/hil/
pytest tests/data/

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

### Run Integration Tests

```bash
# Run E2E integration tests
pytest tests/integration/

# Run specific pipeline test
pytest tests/integration/test_e2e_fusion_pipeline.py -v
```

### Run Rust Tests

```bash
cd control-rs
cargo test

# With output
cargo test -- --nocapture

# Specific test
cargo test test_lqr_basic
```

---

## Benchmarking

### Run Performance Benchmarks

```bash
# Python benchmarks
python benchmarks/benchmark_fusion.py

# Rust benchmarks (using Criterion)
cd control-rs
cargo bench
```

### Expected Performance

| Benchmark | Target | Typical |
|-----------|--------|---------|
| Joint inversion (100 params) | < 1.0s | ~0.3s |
| Joint inversion (1000 params) | < 10.0s | ~3.5s |
| Cross-gradient (100x100) | < 0.1s | ~0.03s |
| Total Variation (100x100) | < 0.05s | ~0.02s |
| LQR solver (Rust) | < 0.001s | ~0.0002s |
| MPC solve (Rust) | < 0.01s | ~0.003s |

---

## Next Steps

1. **Explore Examples**: Check `examples/` directory for more workflows
2. **Read API Docs**: See `docs/API.md` for detailed module documentation
3. **Join Community**: Visit GitHub for issues, discussions, and contributions
4. **Read Papers**: See `docs/REFERENCES.md` for scientific background

---

## Getting Help

- **Documentation**: `docs/`
- **GitHub Issues**: https://github.com/alovladi007/GALILEO-V2.0/issues
- **API Reference**: `docs/API.md`
- **Examples**: `examples/`

---

**Version**: 2.0.0 (90% complete)
**Last Updated**: 2024-11-17
