"""
GALILEO V2.0 - Multi-Sensor Fusion Module
==========================================

Joint inversion using gravity, magnetics, and seismic data.

Modules:
    joint_inversion: Combined inversion algorithms
    cross_regularization: Cross-gradient and joint sparsity
    hierarchical_priors: Bayesian hierarchical models
    gnn_fusion: Graph Neural Network based fusion
"""

__version__ = "0.1.0"

__all__ = [
    "JointInversion",
    "CrossGradientRegularization",
    "JointSparsity",
    "HierarchicalPrior",
    "GNNFusionModel",
]
