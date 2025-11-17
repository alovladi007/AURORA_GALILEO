"""
GALILEO V2.0 - Multi-Sensor Fusion Module
==========================================

Joint inversion using gravity, magnetics, and seismic data.

Modules:
    joint_inversion: Combined inversion algorithms
    regularization: Cross-gradient, joint sparsity, TV, minimum support
    gnn_fusion: Graph Neural Network based fusion
"""

from fusion.joint_inversion import (
    JointInversion,
    InversionResult,
    create_synthetic_joint_problem,
    compare_joint_vs_individual,
)

from fusion.regularization import (
    cross_gradient_2d,
    cross_gradient_3d,
    joint_sparsity,
    total_variation,
    minimum_support,
    StructuralCouplingRegularization,
)

try:
    from fusion.gnn_fusion import (
        GraphData,
        MultiModalGNNFusion,
    )
    HAS_GNN = True
except ImportError:
    HAS_GNN = False

__version__ = "0.1.0"

__all__ = [
    # Joint inversion
    "JointInversion",
    "InversionResult",
    "create_synthetic_joint_problem",
    "compare_joint_vs_individual",
    # Regularization
    "cross_gradient_2d",
    "cross_gradient_3d",
    "joint_sparsity",
    "total_variation",
    "minimum_support",
    "StructuralCouplingRegularization",
]

if HAS_GNN:
    __all__.extend([
        "GraphData",
        "MultiModalGNNFusion",
    ])
