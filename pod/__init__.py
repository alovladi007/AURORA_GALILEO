"""
GALILEO V2.0 - Precise Orbit Determination (POD) Module
========================================================

Precise orbit determination using GNSS, SLR, and DORIS measurements.

Modules:
    measurements: GNSS pseudorange/carrier, SLR, DORIS models
    estimators: Batch least-squares, square-root information filter
    smoothers: RTS smoother for post-processing
    dynamics: Empirical accelerations and force modeling
    validation: Orbit overlap and residual analysis
"""

from pod.measurements import (
    GNSSMeasurement,
    SLRMeasurement,
    DORISMeasurement,
    dual_frequency_ionosphere_correction,
    troposphere_correction,
)

from pod.estimators import (
    BatchLeastSquares,
    SquareRootInformationFilter,
    estimate_orbit_batch,
    estimate_orbit_sequential,
)

from pod.smoothers import (
    RTSSmoother,
    smooth_orbit,
)

from pod.orbit_determination import (
    DynamicODResult,
    dynamics_two_body_j2,
    estimate_orbit_dynamic,
)

from pod.dynamics import (
    EmpiricalAccelerations,
    PiecewiseConstantAccel,
    estimate_empirical_forces,
)

from pod.validation import (
    compute_orbit_overlap,
    analyze_residuals,
    outlier_rejection,
)

__all__ = [
    # Measurements
    "GNSSMeasurement",
    "SLRMeasurement",
    "DORISMeasurement",
    "dual_frequency_ionosphere_correction",
    "troposphere_correction",
    # Estimators
    "BatchLeastSquares",
    "SquareRootInformationFilter",
    "estimate_orbit_batch",
    "estimate_orbit_sequential",
    # Smoothers
    "RTSSmoother",
    "smooth_orbit",
    # Dynamics
    "EmpiricalAccelerations",
    "PiecewiseConstantAccel",
    "estimate_empirical_forces",
    # Validation
    "compute_orbit_overlap",
    "analyze_residuals",
    "outlier_rejection",
]

__version__ = "0.1.0"
