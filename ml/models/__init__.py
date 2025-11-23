"""ML models for geophysical inversion."""

from .pinn import (
    PhysicsInformedNN,
    GravityPINN,
    MagneticPINN,
    JointGravityMagneticPINN,
)

from .fno import (
    SpectralConv2d,
    SpectralConv3d,
    FNO2D,
    FNO3D,
    GravityForwardFNO,
    MagneticForwardFNO,
    JointForwardFNO,
)

from .inversion import (
    InversionNN,
    ConditionalInversionNN,
    ResidualInversionNN,
    EnsembleInversionNN,
    GravityInversionNN,
    MagneticInversionNN,
    JointInversionNN,
)

from .models_3d import (
    Gravity3DPINN,
    UNet3D,
    Volumetric3DInversion,
    MultiScale3DInversion,
)

__all__ = [
    # PINNs
    'PhysicsInformedNN',
    'GravityPINN',
    'MagneticPINN',
    'JointGravityMagneticPINN',
    # FNOs
    'SpectralConv2d',
    'SpectralConv3d',
    'FNO2D',
    'FNO3D',
    'GravityForwardFNO',
    'MagneticForwardFNO',
    'JointForwardFNO',
    # Inversion NNs
    'InversionNN',
    'ConditionalInversionNN',
    'ResidualInversionNN',
    'EnsembleInversionNN',
    'GravityInversionNN',
    'MagneticInversionNN',
    'JointInversionNN',
    # 3D Models
    'Gravity3DPINN',
    'UNet3D',
    'Volumetric3DInversion',
    'MultiScale3DInversion',
]
