# GALILEO V2.0 — Phase 5 Implementation

Phase 5 implements **Advanced Features**: hyperparameter tuning, multi-scale
inversion, formation flying controllers, EKF navigation filters, and enhanced
3D visualization for production-grade scientific capabilities.

## Summary

| Component | Before | After |
|-----------|--------|-------|
| **ML Hyperparameter Tuning** | Fixed hyperparameters | Optuna-based automatic tuning with pruning |
| **Inversion Multi-Scale** | Single-resolution grid | Wavelet-based hierarchical inversion (10x faster) |
| **Formation Control** | Single-satellite orbit propagation | LQR/MPC formation flying controllers |
| **Navigation** | No state estimation | Extended Kalman Filter with multi-sensor fusion |
| **3D Visualization** | Basic satellite tracking | Volume rendering, particle effects, heatmaps |

## Week 19: Hyperparameter Tuning

### ML Service Enhancements

**New Module**: `services/ml-service/src/hyperparameter_tuner.py`

Integrates Optuna for automatic hyperparameter optimization:

- **Trial-based search**: Learning rate, hidden units, regularization, batch size
- **Multi-objective**: Optimize for validation loss + training time
- **Pruning**: MedianPruner stops unpromising trials early
- **MLflow integration**: Log trials, best parameters, optimization history
- **Async execution**: Non-blocking tuning jobs with progress tracking

```python
class HyperparameterTuner:
    def __init__(self, mlflow_tracking_uri: Optional[str] = None):
        self.studies: Dict[str, optuna.Study] = {}
        
    def start_tuning(
        self,
        model_type: str,
        n_trials: int = 50,
        timeout: int = 3600
    ) -> str:
        """Start hyperparameter search job."""
        
    def objective(self, trial: optuna.Trial) -> float:
        """Optuna objective: train model with trial params, return val loss."""
        lr = trial.suggest_float("lr", 1e-4, 1e-1, log=True)
        n_hidden = trial.suggest_int("n_hidden", 16, 256)
        # ... train model, return validation loss
```

**Updated Module**: `services/ml-service/src/service.py`

- New RPC: `TuneHyperparameters(request)` → tuning job_id
- New RPC: `GetTuningStatus(job_id)` → progress, best params, trials
- Auto-apply best params to subsequent training jobs

**Proto additions** (`proto/ml_service.proto`):

```protobuf
message TuneHyperparametersRequest {
  string model_type = 1;
  int32 n_trials = 2;
  int32 timeout_seconds = 3;
  map<string, string> fixed_params = 4;
}

message TuningStatus {
  string job_id = 1;
  string status = 2;  // running, completed, failed
  int32 trials_completed = 3;
  int32 trials_total = 4;
  map<string, float> best_params = 5;
  float best_value = 6;
  repeated TrialResult trials = 7;
}
```

## Week 20: Multi-Scale Inversion

### Inversion Service Enhancements

**New Module**: `services/inversion-service/src/multiscale_solver.py`

Implements wavelet-based hierarchical inversion:

- **Wavelet decomposition**: Decompose model into coarse + detail coefficients
- **Coarse-to-fine solving**: Solve on coarse grid first, refine with details
- **Adaptive refinement**: Only refine regions with significant misfit
- **Speed improvement**: 5-10x faster for large grids (100x100+)

```python
class MultiscaleInversionEngine:
    def __init__(
        self,
        levels: int = 3,
        wavelet: str = "db4",
        refinement_threshold: float = 0.1
    ):
        self.levels = levels  # decomposition depth
        
    def solve_hierarchical(
        self,
        observations: np.ndarray,
        grid_shape: Tuple[int, int],
        method: str = "tikhonov"
    ) -> InversionResult:
        """Solve on coarse grid → refine → solve details → combine."""
        
        # Level 0: coarsest grid (e.g. 25x25 for 100x100 input)
        m_coarse = self._solve_coarse(observations, grid_shape)
        
        # Progressively refine regions with high misfit
        for level in range(1, self.levels + 1):
            active_cells = self._identify_refinement_cells(m_coarse, level)
            m_detail = self._solve_refinement(observations, active_cells, level)
            m_coarse = self._combine_scales(m_coarse, m_detail)
        
        return InversionResult(model=m_coarse, ...)
```

**Integration**:
- Add `use_multiscale=True` option to existing `SolveInversion` RPC
- Proto field: `bool use_multiscale = 13;`
- Automatic selection for grids > 50x50

## Week 21: Formation Flying Controllers

### Control Service Integration

**Integrate `control/controllers`** into Control Service:

**New Module**: `services/control-service/src/formation_controller.py`

Wraps repository-root controllers for gRPC exposure:

```python
from control.controllers.lqr import FormationLQRController
from control.controllers.mpc import FormationMPCController
from control.controllers.station_keeping import StationKeepingController

class FormationControlManager:
    """Manages formation flying controllers for multiple satellites."""
    
    def __init__(self):
        self.controllers: Dict[str, Any] = {}
        
    def create_controller(
        self,
        formation_id: str,
        controller_type: str,  # "lqr", "mpc", "station_keeping"
        config: Dict[str, Any]
    ):
        """Create a formation controller instance."""
        n = config.get("mean_motion", 0.001)  # rad/s for LEO
        
        if controller_type == "lqr":
            self.controllers[formation_id] = FormationLQRController(n=n)
        elif controller_type == "mpc":
            horizon = config.get("horizon", 10)
            self.controllers[formation_id] = FormationMPCController(
                n=n, horizon=horizon
            )
        # ... other types
    
    def compute_control(
        self,
        formation_id: str,
        relative_state: np.ndarray,
        reference_state: np.ndarray
    ) -> np.ndarray:
        """Compute control thrust for formation."""
        controller = self.controllers[formation_id]
        return controller.compute_control(relative_state, reference_state)
```

**New RPCs** (`proto/control_service.proto`):

```protobuf
message CreateFormationRequest {
  string formation_id = 1;
  string controller_type = 2;  // lqr, mpc, station_keeping
  int32 num_satellites = 3;
  map<string, double> config = 4;
}

message ComputeFormationControlRequest {
  string formation_id = 1;
  repeated RelativeState satellite_states = 2;
  RelativeState reference_state = 3;
}

message FormationControlResponse {
  string formation_id = 1;
  repeated ThrustCommand commands = 2;  // one per satellite
}
```

**Dependencies**:
- Add `jax`, `jaxlib` to `services/control-service/requirements.txt`
- Mount `control/` package into container (or vendor into service)

## Week 22: EKF Navigation Filters

### Control Service Navigation

**Integrate `control/navigation/ekf.py`** into Control Service:

**New Module**: `services/control-service/src/navigation_ekf.py`

Wraps EKF for state estimation:

```python
from control.navigation.ekf import ExtendedKalmanFilter
import jax.numpy as jnp

class NavigationManager:
    """Manages EKF state estimators for satellites."""
    
    def __init__(self):
        self.filters: Dict[str, ExtendedKalmanFilter] = {}
    
    def create_filter(
        self,
        satellite_id: str,
        dynamics_type: str = "two_body_j2",
        measurement_type: str = "gps"
    ):
        """Create EKF for a satellite."""
        # Define dynamics function (two-body + J2)
        def dynamics(x, u, t):
            # x = [rx, ry, rz, vx, vy, vz]
            # ... two-body + J2 dynamics from propagator.py
            return dx_dt
        
        # Define measurement function (GPS)
        def measurement(x, t):
            # GPS measures position only
            return x[:3]
        
        Q = jnp.eye(6) * 1e-6  # process noise
        R = jnp.eye(3) * 1.0   # GPS measurement noise (meters)
        
        self.filters[satellite_id] = ExtendedKalmanFilter(
            dynamics_func=dynamics,
            measurement_func=measurement,
            Q=Q, R=R, dt=1.0,
            state_dim=6, meas_dim=3
        )
    
    def update_filter(
        self,
        satellite_id: str,
        measurement: np.ndarray
    ) -> np.ndarray:
        """Process measurement, return state estimate."""
        ekf = self.filters[satellite_id]
        ekf.update(measurement)
        return np.array(ekf.x)
```

**New RPCs**:

```protobuf
message CreateNavigationFilterRequest {
  string satellite_id = 1;
  string dynamics_type = 2;  // two_body, two_body_j2
  string measurement_type = 3;  // gps, laser, imu
}

message NavigationMeasurement {
  string satellite_id = 1;
  google.protobuf.Timestamp timestamp = 2;
  repeated double position = 3;  // GPS position [x, y, z]
  repeated double velocity = 4;  // optional
}

message StateEstimate {
  string satellite_id = 1;
  repeated double state = 2;      // [rx, ry, rz, vx, vy, vz]
  repeated double covariance = 3; // flattened 6x6 matrix
}
```

## Week 23: Advanced 3D Visualization

### Frontend Enhancements

**New Component**: `ui/src/components/VolumeRenderer.tsx`

Volume rendering for 3D gravity fields:

```typescript
interface VolumeRendererProps {
  gravityField: number[][][];  // 3D grid
  bounds: {
    minLat: number; maxLat: number;
    minLon: number; maxLon: number;
    minAlt: number; maxAlt: number;
  };
  colormap: string;  // "viridis", "plasma", "coolwarm"
  opacity: number;
}

export function VolumeRenderer({ gravityField, bounds, ... }: Props) {
  // Use Cesium custom shaders for GPU-accelerated volume rendering
  const volumeEntity = useMemo(() => {
    return new Cesium.CustomDataSource("gravity-volume");
  }, []);
  
  // Raymarching shader for volume rendering
  const fragmentShader = `...`;
  
  return <CesiumViewer ... />;
}
```

**New Component**: `ui/src/components/ParticleEffects.tsx`

Particle system for thrust plumes and maneuvers:

```typescript
interface ParticleSystemProps {
  satellites: SatelliteState[];
  thrustCommands: ThrustCommand[];
}

export function ParticleEffects({ satellites, thrustCommands }: Props) {
  useEffect(() => {
    // Create particle system for each satellite with active thrust
    thrustCommands.forEach(cmd => {
      if (cmd.magnitude > 0) {
        createThrustPlume(cmd.satellite_id, cmd.direction, cmd.magnitude);
      }
    });
  }, [thrustCommands]);
  
  // Cesium ParticleEmitter
  function createThrustPlume(satId, direction, magnitude) {
    return new Cesium.ParticleSystem({
      image: '/textures/particle.png',
      emissionRate: magnitude * 100,
      particleLife: 1.0,
      // ... color, size, velocity based on thrust
    });
  }
}
```

**Enhanced Component**: `ui/src/components/HeatmapOverlay.tsx`

High-resolution gravity heatmap on globe:

```typescript
export function HeatmapOverlay({ gravityData }: Props) {
  const heatmapImagery = useMemo(() => {
    // Convert gravity grid to WebGL texture
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d')!;
    
    // Apply colormap to gravity values
    const imageData = applyColormap(gravityData, 'viridis');
    ctx.putImageData(imageData, 0, 0);
    
    return new Cesium.SingleTileImageryProvider({
      url: canvas.toDataURL(),
      rectangle: Cesium.Rectangle.fromDegrees(
        bounds.minLon, bounds.minLat,
        bounds.maxLon, bounds.maxLat
      ),
    });
  }, [gravityData]);
  
  return <ImageryLayer imageryProvider={heatmapImagery} alpha={0.7} />;
}
```

## Week 24: Integration & Polish

### End-to-End Workflows

**Automated Formation Mission**:

1. API Gateway workflow: `formation_mission_workflow`
   - Trigger: `control.mission_started` event
   - Steps:
     1. Create navigation filters for all satellites (EKF)
     2. Create formation controller (LQR/MPC)
     3. Start telemetry streaming
     4. Periodically compute formation control (every 10s)
     5. Update particle effects visualization

**Tuning + Inversion Pipeline**:

1. User triggers ML hyperparameter tuning (Optuna)
2. Best model auto-selected for gravity prediction
3. Multi-scale inversion uses ML model as prior
4. Results visualized with volume renderer + heatmap

### Testing

**New Test Suites**:

- `services/ml-service/tests/test_hyperparameter_tuner.py` (Optuna mocking, best params)
- `services/inversion-service/tests/test_multiscale_solver.py` (wavelet decomposition, speedup)
- `services/control-service/tests/test_formation_controller.py` (LQR gains, MPC constraints)
- `services/control-service/tests/test_navigation_ekf.py` (EKF convergence, GPS noise)
- `ui/tests/VolumeRenderer.test.tsx` (Cesium volume entity creation)

### Documentation

- Update `docs/ARCHITECTURE.md` with formation control architecture
- Add `docs/ADVANCED_FEATURES.md` (hyperparameter tuning guide, multi-scale tips)
- Update API documentation with new RPCs

## Technology Additions

**Backend**:
- `optuna==3.5.0` (ML Service)
- `pywavelets==1.5.0` (Inversion Service)
- `jax==0.4.23`, `jaxlib==0.4.23` (Control Service - for LQR/EKF)

**Frontend**:
- Cesium custom shaders (volume rendering)
- WebGL texture manipulation (heatmaps)

## Success Metrics

- **Hyperparameter Tuning**: 10-20% validation loss improvement vs. default params
- **Multi-Scale Inversion**: 5-10x speedup for 100x100 grids, <5% accuracy loss
- **Formation Control**: Maintain <100m formation error over 1-orbit simulation
- **EKF Navigation**: Position error <10m RMS with GPS noise
- **Visualization**: 60fps 3D rendering with 50x50x50 volume grid

## Migration Path

All new features are **opt-in** via request flags:

- `TuneHyperparametersRequest` is a new RPC (doesn't affect existing training)
- `use_multiscale=true` flag in `SolveInversionRequest` (defaults to false)
- Formation controllers are independent services (don't affect single-satellite)
- Advanced visualization components are additive (existing GlobeViewer unchanged)

---

**Phase 5 Status**: Starting implementation (Week 19: Hyperparameter Tuning)
