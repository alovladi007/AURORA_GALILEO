"""
Machine Learning Module for GALILEO V2.0
=========================================

Physics-informed machine learning for geophysical inversion and sensing.

Components:
- PINNs: Physics-Informed Neural Networks with PDE constraints
- FNOs: Fourier Neural Operators for fast forward modeling
- Inversion NNs: Direct data-to-model inversion networks
- Uncertainty: Bayesian and ensemble methods for uncertainty quantification
- Training: Flexible training framework with checkpointing and early stopping
"""

from .models import (
    # PINNs
    PhysicsInformedNN,
    GravityPINN,
    MagneticPINN,
    JointGravityMagneticPINN,
    # FNOs
    FNO2D,
    FNO3D,
    GravityForwardFNO,
    MagneticForwardFNO,
    JointForwardFNO,
    # Inversion
    InversionNN,
    GravityInversionNN,
    MagneticInversionNN,
    JointInversionNN,
    EnsembleInversionNN,
)

from .utils import (
    UncertaintyEstimate,
    mc_dropout_predict,
    ensemble_predict,
    BayesianNN,
    DeepEnsemble,
)

__version__ = '2.0.0'

__all__ = [
    # Models
    'PhysicsInformedNN',
    'GravityPINN',
    'MagneticPINN',
    'JointGravityMagneticPINN',
    'FNO2D',
    'FNO3D',
    'GravityForwardFNO',
    'MagneticForwardFNO',
    'JointForwardFNO',
    'InversionNN',
    'GravityInversionNN',
    'MagneticInversionNN',
    'JointInversionNN',
    'EnsembleInversionNN',
    # Uncertainty
    'UncertaintyEstimate',
    'mc_dropout_predict',
    'ensemble_predict',
    'BayesianNN',
    'DeepEnsemble',
]
