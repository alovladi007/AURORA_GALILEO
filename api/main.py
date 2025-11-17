"""
FastAPI application for GeoSense Platform.

Provides REST API endpoints for:
- Orbit propagation
- Formation control simulation
- Laser interferometry analysis
- ML model predictions
- Platform status and documentation
"""

from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import time
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import authentication
from api.auth import get_current_user, get_current_active_user

# Import GeoSense modules (optional - gracefully degrade if not available)
try:
    import jax.numpy as jnp
    import numpy as np
    from sim.dynamics import (
        two_body_dynamics,
        propagate_orbit_jax,
        orbital_elements_to_cartesian,
        propagate_relative_orbit,
    )
    from sensing.phase_model import compute_phase, range_to_phase
    from sensing.noise import total_phase_noise_std
    from sensing.allan import allan_deviation
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    import_error_message = str(e)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="GeoSense Platform API",
    description="AI-enhanced space-based geophysical sensing platform",
    version="0.4.0"
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration - secure by default
CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # Specific origins only, no wildcards
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)

# Prometheus Metrics
REQUEST_COUNT = Counter(
    'galileo_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'galileo_api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# Middleware for Prometheus metrics
@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    """Track request metrics"""
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)

    return response

# ============================================================================
# Request/Response Models
# ============================================================================

class OrbitalElements(BaseModel):
    """Orbital elements (a, e, i, Ω, ω, ν) in km and degrees."""
    semi_major_axis: float = Field(..., gt=6371.0, lt=1000000.0, description="Semi-major axis in km (must be > Earth radius)")
    eccentricity: float = Field(..., ge=0.0, lt=1.0, description="Eccentricity (0 ≤ e < 1 for elliptical orbits)")
    inclination: float = Field(..., ge=0.0, le=180.0, description="Inclination in degrees (0-180)")
    raan: float = Field(..., ge=0.0, lt=360.0, description="Right ascension of ascending node in degrees (0-360)")
    argument_of_perigee: float = Field(..., ge=0.0, lt=360.0, description="Argument of perigee in degrees (0-360)")
    true_anomaly: float = Field(..., ge=0.0, lt=360.0, description="True anomaly in degrees (0-360)")

class PropagationRequest(BaseModel):
    """Request for orbit propagation."""
    orbital_elements: OrbitalElements
    duration: float = Field(..., gt=0.0, le=31536000.0, description="Propagation duration in seconds (max 1 year)")
    time_step: float = Field(10.0, gt=0.0, le=3600.0, description="Time step in seconds (max 1 hour)")

class FormationRequest(BaseModel):
    """Request for formation flying simulation."""
    delta_state: List[float] = Field(..., min_items=6, max_items=6, description="Relative state [x,y,z,vx,vy,vz] in km and km/s")
    mean_motion: float = Field(..., gt=0.0, description="Mean motion in rad/s")
    duration: float = Field(..., gt=0.0, le=86400.0, description="Duration in seconds (max 1 day)")
    time_step: float = Field(10.0, gt=0.0, le=600.0, description="Time step in seconds (max 10 min)")

class PhaseRequest(BaseModel):
    """Request for phase measurement calculation."""
    range_km: float = Field(..., gt=0.0, le=10000.0, description="Range in km (max 10,000 km)")
    wavelength: float = Field(1064e-9, gt=0.0, le=10e-6, description="Wavelength in meters (default 1064nm Nd:YAG)")

class NoiseRequest(BaseModel):
    """Request for noise budget calculation."""
    power: float = Field(..., gt=0.0, le=1000.0, description="Laser power in Watts (max 1kW)")
    range_km: float = Field(..., gt=0.0, le=10000.0, description="Range in km")
    range_rate_km_s: float = Field(..., ge=-10.0, le=10.0, description="Range rate in km/s")
    frequency_stability: float = Field(1e-13, gt=0.0, le=1e-6, description="Frequency stability")

# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Redirect to API documentation."""
    return {
        "message": "GeoSense Platform API",
        "version": "0.4.0",
        "documentation": "/docs",
        "ui": "http://localhost:3000 (Next.js UI - run 'cd ui && npm install && npm run dev')",
        "health": "/health",
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.4.0",
        "modules": {
            "imports_available": IMPORTS_AVAILABLE,
            "jax": True,
            "numpy": True,
        },
        "capabilities": [
            "orbital_dynamics",
            "formation_flying",
            "laser_interferometry",
            "gnc_systems",
            "machine_learning",
            "gravity_inversion"
        ]
    }

@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/propagate")
@limiter.limit("100/minute")  # Rate limiting
async def propagate_orbit(request: PropagationRequest):
    """
    Propagate an orbit from orbital elements.

    Returns trajectory as list of [x, y, z, vx, vy, vz] states in km and km/s.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Simulation modules not available")

    try:
        # Use simulation service
        from api.services import get_simulation_service
        service = get_simulation_service()

        # Prepare elements dict
        elements = {
            'semi_major_axis': request.orbital_elements.semi_major_axis,
            'eccentricity': request.orbital_elements.eccentricity,
            'inclination': request.orbital_elements.inclination,
            'raan': request.orbital_elements.raan,
            'argument_of_perigee': request.orbital_elements.argument_of_perigee,
            'true_anomaly': request.orbital_elements.true_anomaly,
        }

        # Propagate orbit
        result = service.propagate_from_elements(
            elements,
            duration=request.duration,
            time_step=request.time_step,
            include_perturbations=False
        )

        # Add orbital parameters
        params = service.compute_orbital_parameters(elements)

        return {
            **result,
            "orbital_parameters": params,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Propagation failed: {str(e)}")

@app.post("/api/formation")
async def propagate_formation(request: FormationRequest):
    """
    Simulate formation flying using Hill-Clohessy-Wiltshire equations.

    Returns relative trajectory as list of [x, y, z, vx, vy, vz] states.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Simulation modules not available")

    try:
        # Use simulation service
        from api.services import get_simulation_service
        service = get_simulation_service()

        # For now, use simple formation propagation
        # TODO: Support full chief/deputy simulation from request
        delta_state = request.delta_state

        # Create a basic LEO orbit for chief if not provided
        chief_elements = {
            'semi_major_axis': 6900.0,  # 500 km altitude LEO
            'eccentricity': 0.001,
            'inclination': 98.0,  # Sun-synchronous
            'raan': 0.0,
            'argument_of_perigee': 0.0,
            'true_anomaly': 0.0,
        }

        # Simulate formation
        result = service.simulate_formation(
            chief_elements,
            delta_state,
            duration=request.duration,
            time_step=request.time_step
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Formation simulation failed: {str(e)}")

@app.post("/api/phase")
async def calculate_phase(request: PhaseRequest):
    """Calculate phase measurement from range."""
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Sensing modules not available")

    try:
        phase_rad = compute_phase(request.range_km, request.wavelength)
        phase_cycles = range_to_phase(request.range_km, request.wavelength)

        return {
            "range_km": request.range_km,
            "wavelength_m": request.wavelength,
            "phase_rad": float(phase_rad),
            "phase_cycles": float(phase_cycles),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Phase calculation failed: {str(e)}")

@app.post("/api/noise")
async def calculate_noise_budget(request: NoiseRequest):
    """Calculate comprehensive noise budget for laser interferometry."""
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Sensing modules not available")

    try:
        total_noise, breakdown = total_phase_noise_std(
            power=request.power,
            range_km=request.range_km,
            range_rate_km_s=request.range_rate_km_s,
            frequency_stability=request.frequency_stability,
        )

        # Convert JAX arrays to Python floats
        breakdown_dict = {k: float(v) for k, v in breakdown.items()}

        return {
            "total_noise_rad": float(total_noise),
            "breakdown": breakdown_dict,
            "range_km": request.range_km,
            "power_W": request.power,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Noise calculation failed: {str(e)}")

# ============================================================================
# Inversion Endpoints
# ============================================================================

class TikhonovInversionRequest(BaseModel):
    """Request for Tikhonov regularized inversion."""
    forward_matrix: List[List[float]]  # n_data x n_model
    data: List[float]  # n_data
    lambda_reg: float
    regularization_type: str = 'smoothness'  # 'smoothness' or 'identity'
    regularization_order: int = 2

class LCurveRequest(BaseModel):
    """Request for L-curve analysis."""
    forward_matrix: List[List[float]]
    data: List[float]
    lambda_range: Optional[List[float]] = None

class GravityAnomalyRequest(BaseModel):
    """Request for gravity anomaly computation."""
    latitude: List[float]
    longitude: List[float]
    observed_gravity: List[float]  # mGal
    model_name: str = 'EGM96'
    correction_type: str = 'free_air'  # 'free_air', 'bouguer', 'isostatic'
    elevation: Optional[List[float]] = None  # meters

class JointInversionSetupRequest(BaseModel):
    """Request for joint inversion setup."""
    gravity_data: List[float]
    latitude: List[float]
    longitude: List[float]
    depth: Optional[List[float]] = None
    model_name: str = 'joint_model'

@app.post("/api/inversion/tikhonov")
async def solve_tikhonov_inversion(request: TikhonovInversionRequest):
    """
    Solve linear inverse problem using Tikhonov regularization.

    Returns model estimate with resolution diagnostics.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service
        import numpy as np

        service = get_inversion_service()

        # Convert to numpy arrays
        forward_matrix = np.array(request.forward_matrix)
        data = np.array(request.data)

        # Solve inversion
        result = service.solve_tikhonov(
            forward_matrix,
            data,
            request.lambda_reg,
            regularization_type=request.regularization_type,
            regularization_order=request.regularization_order
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tikhonov inversion failed: {str(e)}")

@app.post("/api/inversion/l-curve")
async def compute_l_curve(request: LCurveRequest):
    """
    Compute L-curve for regularization parameter selection.

    Returns optimal lambda and curve data for visualization.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service
        import numpy as np

        service = get_inversion_service()

        # Convert to numpy arrays
        forward_matrix = np.array(request.forward_matrix)
        data = np.array(request.data)
        lambda_range = np.array(request.lambda_range) if request.lambda_range else None

        # Compute L-curve
        result = service.compute_l_curve(forward_matrix, data, lambda_range)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"L-curve computation failed: {str(e)}")

@app.get("/api/inversion/gravity-model/{model_name}")
async def load_gravity_model(model_name: str):
    """
    Load reference gravity field model (EGM96 or EGM2008).

    Returns model metadata and specifications.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service

        service = get_inversion_service()

        # Load model
        result = service.load_gravity_model(model_name)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gravity model loading failed: {str(e)}")

@app.post("/api/inversion/gravity-anomaly")
async def compute_gravity_anomaly(request: GravityAnomalyRequest):
    """
    Compute gravity anomaly relative to reference model.

    Supports free-air, Bouguer, and isostatic corrections.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service
        import numpy as np

        service = get_inversion_service()

        # Convert to numpy arrays
        lat = np.array(request.latitude)
        lon = np.array(request.longitude)
        observed_gravity = np.array(request.observed_gravity)
        elevation = np.array(request.elevation) if request.elevation else None

        # Compute anomaly
        result = service.compute_gravity_anomaly(
            lat, lon, observed_gravity,
            model_name=request.model_name,
            correction_type=request.correction_type,
            elevation=elevation
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gravity anomaly computation failed: {str(e)}")

@app.post("/api/inversion/joint/setup")
async def setup_joint_inversion(request: JointInversionSetupRequest):
    """
    Set up joint inversion model with gravity data.

    Returns model ID for subsequent operations.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service
        import numpy as np

        service = get_inversion_service()

        # Convert to numpy arrays
        gravity_data = np.array(request.gravity_data)
        lat = np.array(request.latitude)
        lon = np.array(request.longitude)
        depth = np.array(request.depth) if request.depth else None

        # Setup joint inversion
        model_id = service.setup_joint_inversion_model(
            gravity_data, lat, lon, depth, request.model_name
        )

        return {
            "model_id": model_id,
            "status": "configured",
            "data_types": ["gravity"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Joint inversion setup failed: {str(e)}")

@app.post("/api/inversion/joint/{model_id}/run")
async def run_joint_inversion(
    model_id: str,
    max_iterations: int = 100,
    convergence_tol: float = 1e-6
):
    """
    Execute joint inversion for configured model.

    Returns inversion results including model, residuals, and convergence info.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Inversion modules not available")

    try:
        from api.services import get_inversion_service

        service = get_inversion_service()

        # Run inversion
        results = service.run_joint_inversion(
            model_id,
            max_iterations=max_iterations,
            convergence_tol=convergence_tol
        )

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Joint inversion failed: {str(e)}")

# ============================================================================
# Control/GNC Endpoints
# ============================================================================

class LQRControllerRequest(BaseModel):
    """Request for creating LQR controller."""
    mean_motion: float
    position_weight: float = 10.0
    velocity_weight: float = 1.0
    control_weight: float = 0.01
    discrete: bool = False
    dt: Optional[float] = None
    controller_id: str = 'default'

class ControlComputeRequest(BaseModel):
    """Request for computing control action."""
    controller_id: str
    current_state: List[float]  # [x, y, z, vx, vy, vz]
    reference_state: Optional[List[float]] = None

class EKFCreateRequest(BaseModel):
    """Request for creating Extended Kalman Filter."""
    mu: float = 398600.4418
    process_noise_std: float = 1e-6
    gps_noise_std: float = 0.01
    dt: float = 1.0
    ekf_id: str = 'default_ekf'

class EKFStepRequest(BaseModel):
    """Request for EKF update step."""
    ekf_id: str
    state: List[float]  # [x, y, z, vx, vy, vz]
    covariance: List[List[float]]  # 6x6 matrix
    measurement: List[float]  # GPS measurement [x, y, z]
    control: Optional[List[float]] = None
    time: float = 0.0

@app.post("/api/control/lqr/create")
async def create_lqr_controller(request: LQRControllerRequest):
    """
    Create LQR controller for formation flying.

    Returns controller ID and gain matrix.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service

        service = get_control_service()

        # Create controller
        result = service.create_lqr_controller(
            mean_motion=request.mean_motion,
            position_weight=request.position_weight,
            velocity_weight=request.velocity_weight,
            control_weight=request.control_weight,
            discrete=request.discrete,
            dt=request.dt,
            controller_id=request.controller_id
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LQR controller creation failed: {str(e)}")

@app.post("/api/control/lqr/compute")
async def compute_lqr_control(request: ControlComputeRequest):
    """
    Compute LQR control action for current state.

    Returns control acceleration vector.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service
        import numpy as np

        service = get_control_service()

        # Compute control
        result = service.compute_lqr_control(
            controller_id=request.controller_id,
            current_state=np.array(request.current_state),
            reference_state=np.array(request.reference_state) if request.reference_state else None
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LQR control computation failed: {str(e)}")

@app.post("/api/control/lqr/simulate")
async def simulate_lqr_trajectory(
    controller_id: str,
    initial_state: List[float],
    duration: float,
    dt: float = 10.0
):
    """
    Simulate closed-loop trajectory with LQR controller.

    Returns complete trajectory with states and controls.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service
        import numpy as np

        service = get_control_service()

        # Simulate
        result = service.simulate_lqr_trajectory(
            controller_id=controller_id,
            initial_state=np.array(initial_state),
            duration=duration,
            dt=dt
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LQR simulation failed: {str(e)}")

@app.post("/api/control/ekf/create")
async def create_ekf_filter(request: EKFCreateRequest):
    """
    Create Extended Kalman Filter for state estimation.

    Returns filter ID and configuration.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service

        service = get_control_service()

        # Create EKF
        result = service.create_orbital_ekf(
            mu=request.mu,
            process_noise_std=request.process_noise_std,
            gps_noise_std=request.gps_noise_std,
            dt=request.dt,
            ekf_id=request.ekf_id
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EKF creation failed: {str(e)}")

@app.post("/api/control/ekf/step")
async def ekf_update_step(request: EKFStepRequest):
    """
    Perform EKF prediction and update step.

    Returns updated state estimate with uncertainties.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service
        import numpy as np

        service = get_control_service()

        # EKF step
        result = service.ekf_full_step(
            ekf_id=request.ekf_id,
            state=np.array(request.state),
            covariance=np.array(request.covariance),
            measurement=np.array(request.measurement),
            control=np.array(request.control) if request.control else None,
            time=request.time
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EKF step failed: {str(e)}")

@app.get("/api/control/hcw-matrices")
async def get_hcw_matrices(mean_motion: float, dt: Optional[float] = None):
    """
    Get Hill-Clohessy-Wiltshire system matrices.

    Returns A and B matrices for relative orbital motion.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service

        service = get_control_service()

        # Get matrices
        result = service.compute_hcw_matrices(mean_motion, dt)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HCW matrix computation failed: {str(e)}")

@app.get("/api/control/controllers")
async def list_controllers():
    """
    List all cached controllers and filters.

    Returns IDs of LQR controllers, MPC controllers, and EKF filters.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Control modules not available")

    try:
        from api.services import get_control_service

        service = get_control_service()

        return service.list_controllers()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Controller listing failed: {str(e)}")

# ============================================================================
# Emulator Endpoints
# ============================================================================

class EmulatorCreateRequest(BaseModel):
    """Request for creating optical bench emulator."""
    emulator_id: str = 'default'
    baseline_length: float = 1.0
    wavelength: float = 632.8e-9
    sampling_rate: float = 1000.0
    temperature: float = 293.15
    shot_noise_level: float = 0.01
    vibration_amplitude: float = 1e-9
    phase_stability: float = 0.1

class EmulatorEventRequest(BaseModel):
    """Request for injecting emulator event."""
    emulator_id: str = 'default'
    event_type: str  # 'vibration_spike', 'thermal_jump'
    magnitude: Optional[float] = None
    delta_temp: Optional[float] = None

@app.post("/api/emulator/create")
async def create_emulator_instance(request: EmulatorCreateRequest):
    """
    Create optical bench emulator instance.

    Returns emulator configuration and ID.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.create_emulator(
            emulator_id=request.emulator_id,
            baseline_length=request.baseline_length,
            wavelength=request.wavelength,
            sampling_rate=request.sampling_rate,
            temperature=request.temperature,
            shot_noise_level=request.shot_noise_level,
            vibration_amplitude=request.vibration_amplitude,
            phase_stability=request.phase_stability
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emulator creation failed: {str(e)}")

@app.get("/api/emulator/{emulator_id}/status")
async def get_emulator_status(emulator_id: str = 'default'):
    """
    Get emulator operational status.

    Returns current state and configuration.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.get_emulator_status(emulator_id)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")

@app.post("/api/emulator/{emulator_id}/start")
async def start_emulator(emulator_id: str = 'default'):
    """
    Start emulator data generation.

    Returns start confirmation.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.start_emulator(emulator_id)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emulator start failed: {str(e)}")

@app.post("/api/emulator/{emulator_id}/stop")
async def stop_emulator(emulator_id: str = 'default'):
    """
    Stop emulator data generation.

    Returns stop confirmation.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.stop_emulator(emulator_id)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emulator stop failed: {str(e)}")

@app.get("/api/emulator/{emulator_id}/state")
async def get_current_state(emulator_id: str = 'default'):
    """
    Get current emulator state snapshot.

    Returns all current signal values.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        state = service.get_current_state(emulator_id)

        return state.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"State retrieval failed: {str(e)}")

@app.get("/api/emulator/{emulator_id}/history")
async def get_signal_history(
    emulator_id: str = 'default',
    duration: float = 1.0,
    signal_type: str = 'interference'
):
    """
    Get time series of emulator signals.

    Returns historical signal data for specified duration.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.get_signal_history(emulator_id, duration, signal_type)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History retrieval failed: {str(e)}")

@app.post("/api/emulator/{emulator_id}/inject-event")
async def inject_emulator_event(emulator_id: str, request: EmulatorEventRequest):
    """
    Inject anomaly or event into emulator.

    Simulates environmental disturbances or equipment anomalies.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        if request.event_type == 'vibration_spike':
            magnitude = request.magnitude or 10.0
            result = service.inject_vibration_spike(emulator_id, magnitude)
        elif request.event_type == 'thermal_jump':
            delta_temp = request.delta_temp or 1.0
            result = service.inject_thermal_jump(emulator_id, delta_temp)
        else:
            raise ValueError(f"Unknown event type: {request.event_type}")

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Event injection failed: {str(e)}")

@app.post("/api/emulator/{emulator_id}/reset")
async def reset_emulator(emulator_id: str = 'default'):
    """
    Reset emulator to initial state.

    Clears all accumulated drift and resets counters.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        result = service.reset_emulator(emulator_id)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emulator reset failed: {str(e)}")

@app.get("/api/emulator/list")
async def list_emulators():
    """
    List all active emulator instances.

    Returns IDs of all created emulators.
    """
    if not IMPORTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Emulator modules not available")

    try:
        from api.services import get_emulator_service

        service = get_emulator_service()

        return service.list_emulators()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emulator listing failed: {str(e)}")


# =============================================================================
# CALIBRATION ENDPOINTS - Sensor Calibration and Characterization
# =============================================================================

@app.post("/api/calibration/allan-deviation")
async def compute_allan_deviation(request: dict):
    """
    Compute Allan deviation for frequency stability analysis.

    Body:
    {
        "data": [array of phase measurements],
        "sample_rate": 1000.0,  # Hz
        "tau_min": 0.1,  # seconds
        "tau_max": 100.0,  # seconds
        "n_taus": 20,
        "method": "overlapping"  # or "standard", "modified"
    }

    Returns Allan deviation results with tau values and stability metrics.
    """
    try:
        from api.services import get_calibration_service
        import numpy as np

        service = get_calibration_service()

        data = np.array(request['data'])
        sample_rate = request['sample_rate']
        tau_min = request.get('tau_min', 0.1)
        tau_max = request.get('tau_max', 100.0)
        n_taus = request.get('n_taus', 20)
        method = request.get('method', 'overlapping')

        result = service.compute_allan_deviation(
            data=data,
            sample_rate=sample_rate,
            tau_min=tau_min,
            tau_max=tau_max,
            n_taus=n_taus,
            method=method
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allan deviation computation failed: {str(e)}")


@app.post("/api/calibration/phase-from-range")
async def calibrate_phase_from_range(request: dict):
    """
    Convert range measurements to phase for laser interferometry.

    Body:
    {
        "range_data": [array of range in km],
        "wavelength": 1064e-9,  # meters
        "phase_offset": 0.0  # radians
    }

    Returns phase measurements, phase rates, and calibration info.
    """
    try:
        from api.services import get_calibration_service
        import numpy as np

        service = get_calibration_service()

        range_data = np.array(request['range_data'])
        wavelength = request.get('wavelength', 1064e-9)
        phase_offset = request.get('phase_offset', 0.0)

        result = service.calibrate_phase_from_range(
            range_data=range_data,
            wavelength=wavelength,
            phase_offset=phase_offset
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Phase calibration failed: {str(e)}")


@app.post("/api/calibration/noise-budget")
async def compute_noise_budget(request: dict):
    """
    Compute comprehensive phase noise budget.

    Body:
    {
        "power": 1.0,  # Watts
        "range_km": 100.0,  # km
        "range_rate_km_s": 0.1,  # km/s
        "frequency_stability": 1e-13,
        "wavelength": 1064e-9  # meters
    }

    Returns noise budget breakdown with shot noise, frequency noise, etc.
    """
    try:
        from api.services import get_calibration_service

        service = get_calibration_service()

        power = request['power']
        range_km = request['range_km']
        range_rate_km_s = request['range_rate_km_s']
        frequency_stability = request.get('frequency_stability', 1e-13)
        wavelength = request.get('wavelength', 1064e-9)

        result = service.compute_phase_noise_budget(
            power=power,
            range_km=range_km,
            range_rate_km_s=range_rate_km_s,
            frequency_stability=frequency_stability,
            wavelength=wavelength
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Noise budget computation failed: {str(e)}")


@app.post("/api/calibration/measurement-quality")
async def analyze_measurement_quality(request: dict):
    """
    Analyze measurement quality metrics.

    Body:
    {
        "measurements": [array of measured values],
        "timestamps": [array of timestamps],
        "reference": [array of reference values]  # optional
    }

    Returns quality metrics: mean, std, rms, errors, correlation, etc.
    """
    try:
        from api.services import get_calibration_service
        import numpy as np

        service = get_calibration_service()

        measurements = np.array(request['measurements'])
        timestamps = np.array(request['timestamps'])
        reference = np.array(request['reference']) if 'reference' in request else None

        result = service.analyze_measurement_quality(
            measurements=measurements,
            timestamps=timestamps,
            reference=reference
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quality analysis failed: {str(e)}")


@app.post("/api/calibration/identify-noise")
async def identify_noise_types(request: dict):
    """
    Identify dominant noise types from Allan deviation slope.

    Body:
    {
        "tau_values": [array of averaging times],
        "adev_values": [array of Allan deviation values]
    }

    Returns noise type identification with slope analysis and interpretation.
    """
    try:
        from api.services import get_calibration_service
        import numpy as np

        service = get_calibration_service()

        tau_values = np.array(request['tau_values'])
        adev_values = np.array(request['adev_values'])

        result = service.identify_noise_types(
            tau_values=tau_values,
            adev_values=adev_values
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Noise identification failed: {str(e)}")


# =============================================================================
# MACHINE LEARNING ENDPOINTS - PINN and U-Net Training/Inference
# =============================================================================

@app.post("/api/ml/pinn/create")
async def create_pinn_model(request: dict):
    """
    Create Physics-Informed Neural Network model.

    Body:
    {
        "model_id": "my_pinn",
        "hidden_layers": [64, 128, 128, 64],
        "activation": "tanh"  # or "relu", "silu"
    }

    Returns model configuration and parameter count.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request.get('model_id', 'default')
        hidden_layers = request.get('hidden_layers', [64, 128, 128, 64])
        activation = request.get('activation', 'tanh')

        result = service.create_pinn_model(
            model_id=model_id,
            hidden_layers=hidden_layers,
            activation=activation
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PINN creation failed: {str(e)}")


@app.post("/api/ml/pinn/train")
async def train_pinn_model(request: dict):
    """
    Train PINN model with synthetic gravity data.

    Body:
    {
        "model_id": "my_pinn",
        "n_samples": 5000,
        "epochs": 100,
        "batch_size": 64,
        "lr": 0.001,
        "lambda_physics": 1.0,
        "val_split": 0.2
    }

    Returns training history and final metrics.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request.get('model_id', 'default')
        n_samples = request.get('n_samples', 5000)
        epochs = request.get('epochs', 100)
        batch_size = request.get('batch_size', 64)
        lr = request.get('lr', 1e-3)
        lambda_physics = request.get('lambda_physics', 1.0)
        val_split = request.get('val_split', 0.2)

        result = service.train_pinn(
            model_id=model_id,
            n_samples=n_samples,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            lambda_physics=lambda_physics,
            val_split=val_split
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PINN training failed: {str(e)}")


@app.post("/api/ml/pinn/inference")
async def pinn_inference(request: dict):
    """
    Run inference with trained PINN model.

    Body:
    {
        "model_id": "my_pinn",
        "coordinates": [[x1, y1, z1], [x2, y2, z2], ...],  # shape (N, 3)
        "densities": [rho1, rho2, ...]  # shape (N,)
    }

    Returns predicted gravity field vectors.
    """
    try:
        from api.services import get_ml_service
        import numpy as np

        service = get_ml_service()

        # Use default model_id if not provided
        model_id = request.get('model_id', 'default_pinn')
        coordinates = np.array(request.get('coordinates', [[0.0, 0.0, 0.0]]))
        densities = np.array(request.get('densities', [0.0]))

        result = service.pinn_inference(
            model_id=model_id,
            coordinates=coordinates,
            densities=densities
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PINN inference failed: {str(e)}")


@app.post("/api/ml/unet/create")
async def create_unet_model(request: dict):
    """
    Create U-Net model for gravity field denoising.

    Body:
    {
        "model_id": "my_unet",
        "in_channels": 1,
        "out_channels": 1,
        "base_channels": 64,
        "depth": 4,
        "dropout": 0.1
    }

    Returns model configuration.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request.get('model_id', 'default')
        in_channels = request.get('in_channels', 1)
        out_channels = request.get('out_channels', 1)
        base_channels = request.get('base_channels', 64)
        depth = request.get('depth', 4)
        dropout = request.get('dropout', 0.1)

        result = service.create_unet_model(
            model_id=model_id,
            in_channels=in_channels,
            out_channels=out_channels,
            base_channels=base_channels,
            depth=depth,
            dropout=dropout
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UNet creation failed: {str(e)}")


@app.post("/api/ml/unet/train")
async def train_unet_model(request: dict):
    """
    Train U-Net model with synthetic phase-gravity pairs.

    Body:
    {
        "model_id": "my_unet",
        "n_samples": 500,
        "image_size": 128,
        "noise_level": 0.1,
        "epochs": 100,
        "batch_size": 8,
        "lr": 0.001,
        "loss_fn": "mse",  # or "mae", "huber"
        "val_split": 0.2
    }

    Returns training history with PSNR, SSIM metrics.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request.get('model_id', 'default')
        n_samples = request.get('n_samples', 500)
        image_size = request.get('image_size', 128)
        noise_level = request.get('noise_level', 0.1)
        epochs = request.get('epochs', 100)
        batch_size = request.get('batch_size', 8)
        lr = request.get('lr', 1e-3)
        loss_fn = request.get('loss_fn', 'mse')
        val_split = request.get('val_split', 0.2)

        result = service.train_unet(
            model_id=model_id,
            n_samples=n_samples,
            image_size=image_size,
            noise_level=noise_level,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            loss_fn=loss_fn,
            val_split=val_split
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UNet training failed: {str(e)}")


@app.post("/api/ml/unet/inference")
async def unet_inference(request: dict):
    """
    Run inference with trained U-Net model.

    Body:
    {
        "model_id": "my_unet",
        "phase_data": [[...], [...], ...]  # 2D array (H, W) or 3D (N, H, W)
    }

    Returns denoised gravity field prediction.
    """
    try:
        from api.services import get_ml_service
        import numpy as np

        service = get_ml_service()

        # Use default model_id if not provided
        model_id = request.get('model_id', 'default_unet')
        phase_data = np.array(request.get('phase_data', [[0.0]]))

        result = service.unet_inference(
            model_id=model_id,
            phase_data=phase_data
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UNet inference failed: {str(e)}")


@app.post("/api/ml/unet/uncertainty")
async def unet_uncertainty_estimation(request: dict):
    """
    Estimate prediction uncertainty using MC Dropout.

    Body:
    {
        "model_id": "my_unet",
        "phase_data": [[...], [...], ...],
        "n_samples": 50  # Number of MC dropout samples
    }

    Returns predictions with uncertainty estimates.
    """
    try:
        from api.services import get_ml_service
        import numpy as np

        service = get_ml_service()

        model_id = request['model_id']
        phase_data = np.array(request['phase_data'])
        n_samples = request.get('n_samples', 50)

        result = service.unet_uncertainty_estimation(
            model_id=model_id,
            phase_data=phase_data,
            n_samples=n_samples
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Uncertainty estimation failed: {str(e)}")


@app.post("/api/ml/pinn/save")
async def save_pinn_model(request: dict):
    """
    Save PINN model to disk.

    Body:
    {
        "model_id": "my_pinn",
        "filename": "my_pinn.pth"  # optional
    }

    Returns save confirmation.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request['model_id']
        filename = request.get('filename')

        result = service.save_pinn_model(
            model_id=model_id,
            filename=filename
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PINN save failed: {str(e)}")


@app.post("/api/ml/pinn/load")
async def load_pinn_model(request: dict):
    """
    Load PINN model from disk.

    Body:
    {
        "model_id": "my_pinn",
        "filepath": "./models/my_pinn.pth",
        "hidden_layers": [64, 128, 128, 64],
        "activation": "tanh"
    }

    Returns load confirmation.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request['model_id']
        filepath = request['filepath']
        hidden_layers = request.get('hidden_layers', [64, 128, 128, 64])
        activation = request.get('activation', 'tanh')

        result = service.load_pinn_model(
            model_id=model_id,
            filepath=filepath,
            hidden_layers=hidden_layers,
            activation=activation
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PINN load failed: {str(e)}")


@app.post("/api/ml/unet/save")
async def save_unet_model(request: dict):
    """
    Save U-Net model to disk.

    Body:
    {
        "model_id": "my_unet",
        "filename": "my_unet.pth"  # optional
    }

    Returns save confirmation.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request['model_id']
        filename = request.get('filename')

        result = service.save_unet_model(
            model_id=model_id,
            filename=filename
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UNet save failed: {str(e)}")


@app.post("/api/ml/unet/load")
async def load_unet_model(request: dict):
    """
    Load U-Net model from disk.

    Body:
    {
        "model_id": "my_unet",
        "filepath": "./models/my_unet.pth",
        "in_channels": 1,
        "out_channels": 1,
        "base_channels": 64,
        "depth": 4
    }

    Returns load confirmation.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        model_id = request['model_id']
        filepath = request['filepath']
        in_channels = request.get('in_channels', 1)
        out_channels = request.get('out_channels', 1)
        base_channels = request.get('base_channels', 64)
        depth = request.get('depth', 4)

        result = service.load_unet_model(
            model_id=model_id,
            filepath=filepath,
            in_channels=in_channels,
            out_channels=out_channels,
            base_channels=base_channels,
            depth=depth
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"UNet load failed: {str(e)}")


@app.get("/api/ml/models")
async def list_ml_models():
    """
    List all loaded ML models.

    Returns lists of PINN and U-Net models currently in memory.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        return service.list_models()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model listing failed: {str(e)}")


@app.get("/api/ml/model/{model_type}/{model_id}")
async def get_model_info(model_type: str, model_id: str):
    """
    Get information about a specific model.

    Path params:
        model_type: 'pinn' or 'unet'
        model_id: Model identifier

    Returns model info including parameter count and device.
    """
    try:
        from api.services import get_ml_service

        service = get_ml_service()

        result = service.get_model_info(model_id=model_id, model_type=model_type)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model info: {str(e)}")


# =============================================================================
# TRADE STUDY ENDPOINTS - Mission Design Trade Studies
# =============================================================================

@app.post("/api/trades/baseline")
async def run_baseline_trade_study(request: dict):
    """
    Run baseline length vs noise vs sensitivity trade study.

    Body:
    {
        "baseline_min": 10.0,  # meters
        "baseline_max": 1000.0,
        "n_points": 50,
        "wavelength": 1e-5,  # 10 microns
        "integration_time": 3600.0  # seconds
    }

    Returns resolution, noise, and sensitivity trade data.
    """
    try:
        from api.services import get_trade_study_service

        service = get_trade_study_service()

        result = service.run_baseline_study(
            baseline_min=request.get('baseline_min', 10.0),
            baseline_max=request.get('baseline_max', 1000.0),
            n_points=request.get('n_points', 50),
            wavelength=request.get('wavelength', 10e-6),
            integration_time=request.get('integration_time', 3600.0)
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Baseline study failed: {str(e)}")


@app.post("/api/trades/orbit")
async def run_orbit_trade_study(request: dict):
    """
    Run orbit altitude and inclination vs coverage trade study.

    Body:
    {
        "altitude_min": 400.0,  # km
        "altitude_max": 1500.0,
        "inclination_min": 0.0,  # degrees
        "inclination_max": 98.0,
        "n_points": 50
    }

    Returns swath width, revisit time, coverage area, power, and lifetime data.
    """
    try:
        from api.services import get_trade_study_service

        service = get_trade_study_service()

        result = service.run_orbit_study(
            altitude_min=request.get('altitude_min', 400.0),
            altitude_max=request.get('altitude_max', 1500.0),
            inclination_min=request.get('inclination_min', 0.0),
            inclination_max=request.get('inclination_max', 98.0),
            n_points=request.get('n_points', 50)
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orbit study failed: {str(e)}")


@app.post("/api/trades/optical")
async def run_optical_trade_study(request: dict):
    """
    Run optical power and aperture trade study.

    Body:
    {
        "power_min": 1.0,  # Watts
        "power_max": 100.0,
        "aperture_min": 0.1,  # meters
        "aperture_max": 2.0,
        "n_points": 50,
        "wavelength": 1550e-9,  # meters
        "distance": 40000e3  # meters (GEO)
    }

    Returns link budget, data rate, pointing accuracy, and mass data.
    """
    try:
        from api.services import get_trade_study_service

        service = get_trade_study_service()

        result = service.run_optical_study(
            power_min=request.get('power_min', 1.0),
            power_max=request.get('power_max', 100.0),
            aperture_min=request.get('aperture_min', 0.1),
            aperture_max=request.get('aperture_max', 2.0),
            n_points=request.get('n_points', 50),
            wavelength=request.get('wavelength', 1550e-9),
            distance=request.get('distance', 40000e3)
        )

        return result.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optical study failed: {str(e)}")


@app.post("/api/trades/pareto")
async def find_pareto_front(request: dict):
    """
    Find Pareto front from multi-objective data.

    Body:
    {
        "objectives": [[obj1_val1, obj2_val1], [obj1_val2, obj2_val2], ...],
        "objectives_to_maximize": [true, false]  # true = maximize, false = minimize
    }

    Returns Pareto-optimal design indices and normalized objectives.
    """
    try:
        from api.services import get_trade_study_service
        import numpy as np

        service = get_trade_study_service()

        objectives = np.array(request['objectives'])
        objectives_to_maximize = request['objectives_to_maximize']

        result = service.find_pareto_front(objectives, objectives_to_maximize)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pareto analysis failed: {str(e)}")


@app.post("/api/trades/sensitivity")
async def run_sensitivity_analysis(request: dict):
    """
    Perform sensitivity analysis by varying one parameter.

    Body:
    {
        "study_type": "baseline",  # or "orbit", "optical"
        "parameter_name": "wavelength",
        "parameter_values": [1e-5, 2e-5, 3e-5],
        "baseline_params": {"baseline_min": 10, "baseline_max": 1000, ...}
    }

    Returns results for each parameter value.
    """
    try:
        from api.services import get_trade_study_service

        service = get_trade_study_service()

        result = service.sensitivity_analysis(
            study_type=request['study_type'],
            parameter_name=request['parameter_name'],
            parameter_values=request['parameter_values'],
            baseline_params=request['baseline_params']
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sensitivity analysis failed: {str(e)}")


@app.post("/api/trades/compare")
async def compare_designs(request: dict):
    """
    Compare and rank design alternatives.

    Body:
    {
        "designs": [
            {"name": "Design A", "cost": 100, "performance": 0.8, ...},
            {"name": "Design B", "cost": 150, "performance": 0.9, ...}
        ],
        "weights": {"cost": -1.0, "performance": 2.0}  # negative = minimize
    }

    Returns ranked designs with weighted scores.
    """
    try:
        from api.services import get_trade_study_service

        service = get_trade_study_service()

        designs = request['designs']
        weights = request.get('weights')

        result = service.compare_designs(designs, weights)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Design comparison failed: {str(e)}")


# =============================================================================
# COMPLIANCE ENDPOINTS - Security, Audit, RBAC, Secrets, Retention
# =============================================================================

@app.post("/api/compliance/audit/log")
async def log_audit_event(request: dict):
    """
    Log audit event with cryptographic chaining.

    Body: {
        "event_type": "LOGIN", "action": "user_login", "result": "success",
        "user_id": "user123", "resource": "/api/data", "severity": "info",
        "metadata": {}, "ip_address": "192.168.1.1"
    }
    """
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.log_audit_event(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit logging failed: {str(e)}")


@app.get("/api/compliance/audit/verify")
async def verify_audit_chain():
    """Verify integrity of audit log chain."""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.verify_audit_chain()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chain verification failed: {str(e)}")


@app.post("/api/compliance/auth/check")
async def check_permission(request: dict):
    """Check user permission for resource. Body: {"user_id": "...", "permission": "DATA_READ", "resource": "..."}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.check_permission(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Permission check failed: {str(e)}")


@app.post("/api/compliance/auth/policy")
async def create_policy(request: dict):
    """Create authorization policy. Body: {"name": "...", "description": "...", "permissions": [...]}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.create_policy(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy creation failed: {str(e)}")


@app.post("/api/compliance/auth/assign-role")
async def assign_role(request: dict):
    """Assign role to user. Body: {"user_id": "...", "role": "..."}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.assign_role(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Role assignment failed: {str(e)}")


@app.get("/api/compliance/auth/policies")
async def list_policies():
    """List all authorization policies."""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.list_policies()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy listing failed: {str(e)}")


@app.post("/api/compliance/secrets/store")
async def store_secret(request: dict):
    """Store encrypted secret. Body: {"name": "...", "value": "...", "secret_type": "API_KEY", "rotation_days": 90}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.store_secret(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Secret storage failed: {str(e)}")


@app.post("/api/compliance/secrets/retrieve")
async def retrieve_secret(request: dict):
    """Retrieve secret. Body: {"secret_id": "...", "user_id": "..."}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.retrieve_secret(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Secret retrieval failed: {str(e)}")


@app.post("/api/compliance/secrets/rotate")
async def rotate_secret(request: dict):
    """Rotate secret. Body: {"secret_id": "...", "new_value": "...", "user_id": "..."}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.rotate_secret(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Secret rotation failed: {str(e)}")


@app.get("/api/compliance/secrets/list")
async def list_secrets(include_expired: bool = False):
    """List all secrets (metadata only)."""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.list_secrets(include_expired=include_expired)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Secret listing failed: {str(e)}")


@app.post("/api/compliance/retention/policy")
async def create_retention_policy(request: dict):
    """Create retention policy. Body: {"name": "...", "retention_days": 365, "action": "DELETE", "classification": "CONFIDENTIAL"}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.create_retention_policy(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retention policy creation failed: {str(e)}")


@app.post("/api/compliance/retention/legal-hold")
async def apply_legal_hold(request: dict):
    """Apply legal hold. Body: {"name": "...", "case_number": "...", "custodian": "...", "resources": [...]}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.apply_legal_hold(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Legal hold application failed: {str(e)}")


@app.post("/api/compliance/retention/release-hold")
async def release_legal_hold(request: dict):
    """Release legal hold. Body: {"hold_id": "...", "user_id": "..."}"""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.release_legal_hold(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hold release failed: {str(e)}")


@app.get("/api/compliance/retention/policies")
async def list_retention_policies():
    """List all retention policies."""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.list_retention_policies()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy listing failed: {str(e)}")


@app.get("/api/compliance/retention/legal-holds")
async def list_legal_holds(active_only: bool = True):
    """List legal holds."""
    try:
        from api.services import get_compliance_service
        service = get_compliance_service()
        return service.list_legal_holds(active_only=active_only)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hold listing failed: {str(e)}")


# =================================================================
# Workflow Orchestration Endpoints
# =================================================================

@app.get("/api/workflow/templates")
async def list_workflow_templates():
    """List all available workflow templates."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.list_workflow_templates()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template listing failed: {str(e)}")


@app.get("/api/workflow/templates/{workflow_type}")
async def get_workflow_template(workflow_type: str):
    """Get specific workflow template."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        template = service.get_workflow_template(workflow_type)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template not found: {workflow_type}")
        return template
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template retrieval failed: {str(e)}")


@app.post("/api/workflow/submit")
async def submit_workflow(request: dict):
    """
    Submit workflow for execution.

    Body: {
        "workflow_type": "full_mission",
        "parameters": {...},
        "user_id": "user123",
        "priority": 5
    }
    """
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()

        # Ensure required parameters key exists
        if 'parameters' not in request:
            request['parameters'] = {}

        return service.submit_workflow(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow submission failed: {str(e)}")


@app.post("/api/workflow/{workflow_id}/execute")
async def execute_workflow(workflow_id: str):
    """
    Execute workflow synchronously.

    Note: For long-running workflows, use submit + status polling instead.
    """
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.execute_workflow(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {str(e)}")


@app.get("/api/workflow/{workflow_id}/status")
async def get_workflow_status(workflow_id: str):
    """Get current workflow status."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.get_workflow_status(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@app.get("/api/workflow/list")
async def list_workflows(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """List workflows with optional filters."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.list_workflows(user_id=user_id, status=status, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow listing failed: {str(e)}")


@app.post("/api/workflow/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str):
    """Cancel running workflow."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.cancel_workflow(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow cancellation failed: {str(e)}")


@app.get("/api/workflow/{workflow_id}/outputs")
async def get_workflow_outputs(workflow_id: str):
    """Get workflow output data and files."""
    try:
        from api.services import get_workflow_service
        service = get_workflow_service()
        return service.get_workflow_outputs(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Output retrieval failed: {str(e)}")


# =================================================================
# Database Persistence Endpoints
# =================================================================

@app.post("/api/db/users")
async def create_user(request: dict):
    """Create user. Body: {"username": "...", "email": "...", "hashed_password": "..."}"""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.create_user(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"User creation failed: {str(e)}")


@app.get("/api/db/users/{username}")
async def get_user(username: str):
    """Get user by username."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        user = service.get_user_by_username(username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"User retrieval failed: {str(e)}")


@app.get("/api/db/users")
async def list_users(active_only: bool = True, limit: int = 100):
    """List all users."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.list_users(active_only=active_only, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"User listing failed: {str(e)}")


@app.post("/api/db/jobs")
async def create_job(request: dict):
    """Create processing job. Body: {"job_type": "...", "user_id": "...", "config": {...}}"""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.create_job(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job creation failed: {str(e)}")


@app.put("/api/db/jobs/{job_id}/status")
async def update_job_status(job_id: str, request: dict):
    """Update job status. Body: {"status": "...", "result": {...}, "error_message": "..."}"""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.update_job_status(job_id=job_id, **request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job update failed: {str(e)}")


@app.get("/api/db/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job by ID."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        job = service.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job retrieval failed: {str(e)}")


@app.get("/api/db/jobs")
async def list_jobs(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 100
):
    """List processing jobs."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.list_jobs(user_id=user_id, status=status, job_type=job_type, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Job listing failed: {str(e)}")


@app.post("/api/db/observations")
async def create_observation(request: dict):
    """Create satellite observation."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        # Parse datetime if string
        if 'time' in request and isinstance(request['time'], str):
            from datetime import datetime
            request['time'] = datetime.fromisoformat(request['time'].replace('Z', '+00:00'))
        return service.create_observation(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Observation creation failed: {str(e)}")


@app.post("/api/db/observations/bulk")
async def bulk_create_observations(request: dict):
    """Bulk create observations. Body: {"observations": [{...}, ...]}"""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.bulk_create_observations(request.get('observations', []))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk observation creation failed: {str(e)}")


@app.get("/api/db/observations")
async def query_observations(
    satellite_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 1000
):
    """Query satellite observations."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime strings
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else None
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

        return service.query_observations(
            satellite_id=satellite_id,
            start_time=start_dt,
            end_time=end_dt,
            job_id=job_id,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Observation query failed: {str(e)}")


@app.post("/api/db/products")
async def create_product(request: dict):
    """Create gravity product."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime strings
        if 'time_start' in request and isinstance(request['time_start'], str):
            request['time_start'] = datetime.fromisoformat(request['time_start'].replace('Z', '+00:00'))
        if 'time_end' in request and isinstance(request['time_end'], str):
            request['time_end'] = datetime.fromisoformat(request['time_end'].replace('Z', '+00:00'))

        return service.create_product(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Product creation failed: {str(e)}")


@app.get("/api/db/products")
async def query_products(
    product_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 100
):
    """Query gravity products."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime strings
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else None
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

        return service.query_products(
            product_type=product_type,
            start_time=start_dt,
            end_time=end_dt,
            job_id=job_id,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Product query failed: {str(e)}")


@app.post("/api/db/baselines")
async def create_baseline_vector(request: dict):
    """Create baseline vector."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime if string
        if 'time' in request and isinstance(request['time'], str):
            request['time'] = datetime.fromisoformat(request['time'].replace('Z', '+00:00'))

        return service.create_baseline_vector(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Baseline vector creation failed: {str(e)}")


@app.post("/api/db/baselines/bulk")
async def bulk_create_baseline_vectors(request: dict):
    """Bulk create baseline vectors. Body: {"baseline_vectors": [{...}, ...]}"""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.bulk_create_baseline_vectors(request.get('baseline_vectors', []))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk baseline vector creation failed: {str(e)}")


@app.get("/api/db/baselines")
async def query_baseline_vectors(
    satellite_1: Optional[str] = None,
    satellite_2: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 1000
):
    """Query baseline vectors."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime strings
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else None
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

        return service.query_baseline_vectors(
            satellite_1=satellite_1,
            satellite_2=satellite_2,
            start_time=start_dt,
            end_time=end_dt,
            job_id=job_id,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Baseline vector query failed: {str(e)}")


@app.post("/api/db/audit-logs")
async def create_audit_log(request: dict):
    """Create audit log entry."""
    try:
        from api.services import get_database_service
        service = get_database_service()
        return service.create_audit_log(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit log creation failed: {str(e)}")


@app.get("/api/db/audit-logs")
async def query_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100
):
    """Query audit logs."""
    try:
        from api.services import get_database_service
        from datetime import datetime
        service = get_database_service()

        # Parse datetime strings
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else None
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

        return service.query_audit_logs(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            start_time=start_dt,
            end_time=end_dt,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit log query failed: {str(e)}")


# =================================================================
# Background Task Processing Endpoints
# =================================================================

@app.post("/api/tasks/submit")
async def submit_task(request: dict):
    """
    Submit task for async execution.

    Body: {
        "task_name": "simulation.propagate_formation",
        "parameters": {...},
        "priority": 5,
        "countdown": 0
    }
    """
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.submit_task(**request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task submission failed: {str(e)}")


@app.post("/api/tasks/submit-chain")
async def submit_task_chain(request: dict):
    """
    Submit task chain for sequential execution.

    Body: {
        "tasks": [
            {"task_name": "...", "parameters": {...}},
            {"task_name": "...", "parameters": {...}}
        ]
    }
    """
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.submit_chain(request.get('tasks', []))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task chain submission failed: {str(e)}")


@app.post("/api/tasks/submit-group")
async def submit_task_group(request: dict):
    """
    Submit task group for parallel execution.

    Body: {
        "tasks": [
            {"task_name": "...", "parameters": {...}},
            {"task_name": "...", "parameters": {...}}
        ]
    }
    """
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.submit_group(request.get('tasks', []))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task group submission failed: {str(e)}")


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get task execution status."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.get_task_status(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task status retrieval failed: {str(e)}")


@app.get("/api/tasks/{task_id}/result")
async def get_task_result(task_id: str, timeout: Optional[float] = None):
    """Get task result (blocks until complete)."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.get_task_result(task_id, timeout=timeout)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task result retrieval failed: {str(e)}")


@app.get("/api/tasks/active")
async def list_active_tasks():
    """List all active tasks."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.list_active_tasks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Active task listing failed: {str(e)}")


@app.get("/api/tasks/scheduled")
async def list_scheduled_tasks():
    """List scheduled tasks."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.list_scheduled_tasks()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheduled task listing failed: {str(e)}")


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, terminate: bool = False):
    """Cancel running task."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.cancel_task(task_id, terminate=terminate)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task cancellation failed: {str(e)}")


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry failed task."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.retry_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task retry failed: {str(e)}")


@app.get("/api/tasks/workers/stats")
async def get_worker_stats():
    """Get Celery worker statistics."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.get_worker_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker stats retrieval failed: {str(e)}")


@app.get("/api/tasks/workers/ping")
async def ping_workers():
    """Ping Celery workers."""
    try:
        from api.services import get_task_service
        service = get_task_service()
        return service.ping_workers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker ping failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
