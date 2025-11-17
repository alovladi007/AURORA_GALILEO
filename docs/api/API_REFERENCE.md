# GALILEO V2.0 API Reference

Comprehensive API documentation for all modules.

---

## Table of Contents

1. [Fusion Module](#fusion-module)
2. [HIL Module](#hil-module)
3. [Data Module](#data-module)
4. [Time Module](#time-module)
5. [POD Module](#pod-module)
6. [Telemetry Module](#telemetry-module)
7. [Control (Rust) Module](#control-rust-module)

---

## Fusion Module

### `fusion.joint_inversion`

#### `JointInversionProblem`

**Description**: Joint inversion problem for multi-sensor geophysical data.

```python
class JointInversionProblem:
    def __init__(self, n_params: int, n_data1: int, n_data2: int)
```

**Parameters**:
- `n_params` (int): Number of model parameters
- `n_data1` (int): Number of observations from sensor 1 (e.g., gravity)
- `n_data2` (int): Number of observations from sensor 2 (e.g., magnetics)

**Methods**:

##### `set_initial_model(m0: np.ndarray)`
Set initial model guess.

**Parameters**:
- `m0` (np.ndarray): Initial model, shape (n_params,)

##### `set_forward_operator1(G1: np.ndarray, operator_type: str = 'gravity')`
Set forward operator for sensor 1.

**Parameters**:
- `G1` (np.ndarray): Forward operator matrix, shape (n_data1, n_params)
- `operator_type` (str): Type of operator ('gravity', 'magnetic', etc.)

##### `set_forward_operator2(G2: np.ndarray, operator_type: str = 'magnetic')`
Set forward operator for sensor 2.

**Parameters**:
- `G2` (np.ndarray): Forward operator matrix, shape (n_data2, n_params)
- `operator_type` (str): Type of operator

**Example**:
```python
from fusion.joint_inversion import JointInversionProblem

problem = JointInversionProblem(
    n_params=1000,
    n_data1=300,
    n_data2=300,
)

problem.set_initial_model(np.zeros(1000))
problem.set_forward_operator1(G_gravity)
problem.set_forward_operator2(G_magnetic)
```

---

#### `solve_joint_inversion()`

**Description**: Solve joint inversion problem with regularization.

```python
def solve_joint_inversion(
    problem: JointInversionProblem,
    data1: np.ndarray,
    data2: np.ndarray,
    regularization: Optional[Callable] = None,
    max_iterations: int = 50,
    tolerance: float = 1e-4,
) -> Dict[str, Any]
```

**Parameters**:
- `problem` (JointInversionProblem): Configured inversion problem
- `data1` (np.ndarray): Observations from sensor 1, shape (n_data1,)
- `data2` (np.ndarray): Observations from sensor 2, shape (n_data2,)
- `regularization` (Optional[Callable]): Regularization function
- `max_iterations` (int): Maximum iterations
- `tolerance` (float): Convergence tolerance

**Returns**:
- Dictionary with keys:
  - `'model'` (np.ndarray): Inverted model
  - `'converged'` (bool): Convergence status
  - `'n_iterations'` (int): Number of iterations
  - `'initial_misfit'` (float): Initial data misfit
  - `'final_misfit'` (float): Final data misfit

**Example**:
```python
result = solve_joint_inversion(
    problem=problem,
    data1=gravity_data,
    data2=magnetic_data,
    max_iterations=30,
)

print(f"Converged: {result['converged']}")
print(f"Iterations: {result['n_iterations']}")
```

---

### `fusion.regularization`

#### `cross_gradient_2d()`

**Description**: Compute cross-gradient for 2D models.

```python
def cross_gradient_2d(
    model1: np.ndarray,
    model2: np.ndarray,
    grid_spacing: float = 1.0,
) -> Tuple[float, np.ndarray, np.ndarray]
```

**Parameters**:
- `model1` (np.ndarray): First model, shape (ny, nx)
- `model2` (np.ndarray): Second model, shape (ny, nx)
- `grid_spacing` (float): Grid spacing in meters

**Returns**:
- Tuple of (cross_gradient_norm, grad_m1, grad_m2)
  - `cross_gradient_norm` (float): Scalar regularization value
  - `grad_m1` (np.ndarray): Gradient w.r.t. model1
  - `grad_m2` (np.ndarray): Gradient w.r.t. model2

**Example**:
```python
from fusion.regularization import cross_gradient_2d

cg_norm, grad1, grad2 = cross_gradient_2d(
    density_model,
    susceptibility_model,
    grid_spacing=1000.0,  # 1 km
)
```

---

#### `StructuralCouplingRegularization`

**Description**: Combined structural coupling regularization.

```python
class StructuralCouplingRegularization:
    def __init__(
        self,
        lambda_cross_grad: float = 1.0,
        lambda_sparsity: float = 0.1,
        lambda_tv: float = 0.1,
        lambda_support: float = 0.0,
    )
```

**Parameters**:
- `lambda_cross_grad` (float): Weight for cross-gradient term
- `lambda_sparsity` (float): Weight for joint sparsity
- `lambda_tv` (float): Weight for total variation
- `lambda_support` (float): Weight for minimum support

**Methods**:

##### `__call__(models: List[np.ndarray], reference_models: Optional[List[np.ndarray]] = None)`

**Parameters**:
- `models` (List[np.ndarray]): List of model arrays
- `reference_models` (Optional[List[np.ndarray]]): Reference models for support term

**Returns**:
- Tuple of (total_regularization, gradients)

**Example**:
```python
reg = StructuralCouplingRegularization(
    lambda_cross_grad=1.0,
    lambda_sparsity=0.1,
    lambda_tv=0.05,
)

total_reg, grads = reg([model1, model2])
```

---

## HIL Module

### `hil.optical_bench`

#### `OpticalBenchEmulator`

**Description**: Software emulator for optical bench.

```python
class OpticalBenchEmulator:
    def __init__(
        self,
        laser_params: Optional[LaserParameters] = None,
        optical_path: Optional[OpticalPath] = None,
        sampling_rate: float = 10.0,
        seed: Optional[int] = None,
    )
```

**Parameters**:
- `laser_params` (LaserParameters): Laser configuration
- `optical_path` (OpticalPath): Optical path configuration
- `sampling_rate` (float): Sampling rate in Hz
- `seed` (Optional[int]): Random seed for reproducibility

**Methods**:

##### `measure_phase(true_range: float, velocity: float = 0.0)`

**Description**: Measure optical phase with realistic noise.

**Parameters**:
- `true_range` (float): True inter-satellite range in meters
- `velocity` (float): Range rate in m/s

**Returns**:
- Tuple of (measured_phase, diagnostics)
  - `measured_phase` (float): Phase measurement in cycles
  - `diagnostics` (dict): Noise contributions

**Example**:
```python
from hil.optical_bench import OpticalBenchEmulator

emulator = OpticalBenchEmulator(sampling_rate=10.0, seed=42)

phase, diagnostics = emulator.measure_phase(true_range=200e3)

print(f"Phase: {phase:.3f} cycles")
print(f"Noise RMS: {diagnostics['total_noise_rms']:.3e} cycles")
```

##### `simulate_measurement_sequence(range_function: Callable, duration: float)`

**Description**: Simulate measurement sequence over time.

**Parameters**:
- `range_function` (Callable): Function r(t) returning range vs time
- `duration` (float): Simulation duration in seconds

**Returns**:
- Dictionary with keys: 'times', 'phases', 'true_ranges', 'noise_levels'

---

### `hil.drivers`

#### `MockTimingCard`

**Description**: Mock timing card for HIL testing.

```python
class MockTimingCard:
    def __init__(self, config: Optional[TimingCardConfig] = None)
```

**Methods**:

##### `read_time()`
Read current time from card.

**Returns**:
- float: Time in seconds

##### `reset()`
Reset timing card to zero.

##### `set_trigger(time: float)`
Set hardware trigger at specified time.

**Example**:
```python
from hil.drivers import MockTimingCard

card = MockTimingCard()
card.reset()

t = card.read_time()
card.set_trigger(1.0)  # Trigger at 1 second
```

---

## Data Module

### `data.stac`

#### `STACCatalog`

**Description**: STAC catalog management.

```python
class STACCatalog:
    def __init__(
        self,
        catalog_id: str = "galileo-catalog",
        description: str = "GALILEO V2.0 Data Catalog",
    )
```

**Methods**:

##### `add_collection(collection: STACCollection)`
Add collection to catalog.

##### `add_item(item: STACItem)`
Add item to catalog.

##### `search(bbox: Optional[List[float]] = None, datetime_range: Optional[Tuple] = None, collections: Optional[List[str]] = None)`

**Description**: Search catalog for items.

**Parameters**:
- `bbox` (Optional[List[float]]): Bounding box [min_lon, min_lat, max_lon, max_lat]
- `datetime_range` (Optional[Tuple]): (start, end) datetime tuple
- `collections` (Optional[List[str]]): Collection IDs to search

**Returns**:
- List[STACItem]: Matching items

**Example**:
```python
from data.stac import STACCatalog, create_gravity_collection

catalog = STACCatalog(catalog_id="my-data")

collection = create_gravity_collection()
catalog.add_collection(collection)

results = catalog.search(
    bbox=[-10, 30, 10, 50],
    collections=["gravity-maps"],
)
```

---

## Time Module

### `time.timescales`

#### `tai_to_gps(tai_seconds: float)`

**Description**: Convert TAI to GPS time.

**Parameters**:
- `tai_seconds` (float): TAI time in seconds since J2000

**Returns**:
- float: GPS time in seconds

**Example**:
```python
from time.timescales import tai_to_gps

gps_time = tai_to_gps(1234567890.0)
```

---

## POD Module

### `pod.measurements`

#### `GNSSMeasurement`

**Description**: GNSS measurement dataclass.

```python
@dataclass
class GNSSMeasurement:
    time: float
    pseudorange: float
    satellite_position: np.ndarray
    satellite_velocity: np.ndarray
```

**Example**:
```python
from pod.measurements import GNSSMeasurement

measurement = GNSSMeasurement(
    time=1000.0,
    pseudorange=20e6,  # 20,000 km
    satellite_position=np.array([1e7, 2e7, 3e7]),
    satellite_velocity=np.array([1e3, 2e3, 3e3]),
)
```

---

## Control (Rust) Module

### `control_rs`

#### `LQR`

**Description**: Linear Quadratic Regulator (Rust implementation).

```python
import control_rs

lqr = control_rs.LQR(A, B, Q, R)
K = lqr.compute_gain()
```

**Parameters**:
- `A` (np.ndarray): State matrix, shape (n, n)
- `B` (np.ndarray): Input matrix, shape (n, m)
- `Q` (np.ndarray): State cost matrix, shape (n, n)
- `R` (np.ndarray): Input cost matrix, shape (m, m)

**Returns**:
- `K` (np.ndarray): Optimal gain matrix, shape (m, n)

**Performance**: ~100x faster than Python implementation

---

## Error Handling

All modules use custom exceptions:

```python
from fusion.joint_inversion import InversionError
from hil.optical_bench import OpticalBenchError
from data.stac import STACError
```

Example:
```python
try:
    result = solve_joint_inversion(...)
except InversionError as e:
    print(f"Inversion failed: {e}")
```

---

## Type Hints

All modules include comprehensive type hints:

```python
from typing import Optional, List, Dict, Tuple, Callable
import numpy as np
```

Use type checkers for static analysis:
```bash
mypy fusion/ hil/ data/
```

---

## Testing

Run tests for specific modules:

```bash
# Unit tests
pytest tests/fusion/ -v
pytest tests/hil/ -v
pytest tests/data/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

---

## Performance Tips

1. **Use Rust modules** for performance-critical operations (LQR, MPC, filters)
2. **Vectorize operations** with NumPy instead of loops
3. **Profile code** with cProfile or line_profiler
4. **Cache results** for expensive computations
5. **Use sparse matrices** for large forward operators

---

## Version Compatibility

- **Python**: 3.9, 3.10, 3.11
- **NumPy**: >= 1.20
- **SciPy**: >= 1.7 (optional)
- **PyTorch**: >= 1.10 (optional, for GNN fusion)
- **Rust**: 1.70+ (for control module)

---

**GALILEO V2.0** - API Reference
**Version**: 2.0.0
**Last Updated**: 2024-11-17
