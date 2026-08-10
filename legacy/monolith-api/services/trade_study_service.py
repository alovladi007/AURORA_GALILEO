"""
Trade Study Service for GeoSense Platform API

Provides business logic for design trade studies and optimization:
- Baseline length vs noise vs sensitivity analysis
- Orbit altitude and inclination vs coverage studies
- Optical power and aperture tradeoffs
- Multi-objective Pareto front analysis

This service bridges API endpoints with trade study modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Import trade study modules
try:
    from trades.baseline_study import BaselineTradeStudy
    from trades.orbit_study import OrbitTradeStudy
    from trades.optical_study import OpticalTradeStudy
    from trades.pareto_analysis import ParetoAnalysis
    TRADE_IMPORTS_AVAILABLE = True
except ImportError as e:
    TRADE_IMPORTS_AVAILABLE = False
    print(f"Trade study imports not available: {e}")


@dataclass
class TradeStudyResult:
    """Container for trade study results."""
    study_type: str
    parameters: Dict[str, Any]
    results: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'study_type': self.study_type,
            'parameters': self.parameters,
            'results': self._convert_arrays(self.results)
        }

    def _convert_arrays(self, obj):
        """Convert numpy arrays to lists recursively."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._convert_arrays(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_arrays(item) for item in obj]
        else:
            return obj


class TradeStudyService:
    """
    Service for mission design trade studies.

    Provides high-level functions for executing trade studies,
    Pareto analysis, and multi-objective optimization.
    """

    def __init__(self):
        """Initialize trade study service."""
        if not TRADE_IMPORTS_AVAILABLE:
            print("Warning: Trade study modules not available.")

        # Cache study instances
        self._baseline_studies = {}
        self._orbit_studies = {}
        self._optical_studies = {}
        self._pareto_analyses = {}

    # =================================================================
    # Baseline Trade Studies
    # =================================================================

    def run_baseline_study(
        self,
        baseline_min: float = 10.0,
        baseline_max: float = 1000.0,
        n_points: int = 50,
        wavelength: float = 10e-6,
        integration_time: float = 3600.0
    ) -> TradeStudyResult:
        """
        Run baseline length vs noise vs sensitivity trade study.

        Args:
            baseline_min: Minimum baseline length (m)
            baseline_max: Maximum baseline length (m)
            n_points: Number of sample points
            wavelength: Laser wavelength (m)
            integration_time: Integration time (s)

        Returns:
            TradeStudyResult with resolution, noise, and sensitivity data
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        study = BaselineTradeStudy()
        study.baseline_range = np.linspace(baseline_min, baseline_max, n_points)
        study.wavelength = wavelength
        study.integration_time = integration_time

        results = study.run_trade_study()

        return TradeStudyResult(
            study_type='baseline',
            parameters={
                'baseline_min': baseline_min,
                'baseline_max': baseline_max,
                'n_points': n_points,
                'wavelength': wavelength,
                'integration_time': integration_time
            },
            results=results
        )

    # =================================================================
    # Orbit Trade Studies
    # =================================================================

    def run_orbit_study(
        self,
        altitude_min: float = 400.0,
        altitude_max: float = 1500.0,
        inclination_min: float = 0.0,
        inclination_max: float = 98.0,
        n_points: int = 50
    ) -> TradeStudyResult:
        """
        Run orbit altitude and inclination vs coverage trade study.

        Args:
            altitude_min: Minimum altitude (km)
            altitude_max: Maximum altitude (km)
            inclination_min: Minimum inclination (deg)
            inclination_max: Maximum inclination (deg)
            n_points: Number of sample points

        Returns:
            TradeStudyResult with swath, coverage, revisit, and power data
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        study = OrbitTradeStudy()
        study.altitude_range = np.linspace(altitude_min, altitude_max, n_points)
        study.inclination_range = np.linspace(inclination_min, inclination_max, n_points)

        results = study.run_trade_study()

        return TradeStudyResult(
            study_type='orbit',
            parameters={
                'altitude_min': altitude_min,
                'altitude_max': altitude_max,
                'inclination_min': inclination_min,
                'inclination_max': inclination_max,
                'n_points': n_points
            },
            results=results
        )

    # =================================================================
    # Optical Trade Studies
    # =================================================================

    def run_optical_study(
        self,
        power_min: float = 1.0,
        power_max: float = 100.0,
        aperture_min: float = 0.1,
        aperture_max: float = 2.0,
        n_points: int = 50,
        wavelength: float = 1550e-9,
        distance: float = 40000e3
    ) -> TradeStudyResult:
        """
        Run optical power and aperture trade study.

        Args:
            power_min: Minimum transmit power (W)
            power_max: Maximum transmit power (W)
            aperture_min: Minimum aperture (m)
            aperture_max: Maximum aperture (m)
            n_points: Number of sample points
            wavelength: Optical wavelength (m)
            distance: Link distance (m)

        Returns:
            TradeStudyResult with link budget, data rate, and mass data
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        study = OpticalTradeStudy()
        study.power_range = np.linspace(power_min, power_max, n_points)
        study.aperture_range = np.linspace(aperture_min, aperture_max, n_points)
        study.wavelength = wavelength
        study.distance = distance

        results = study.run_trade_study()

        return TradeStudyResult(
            study_type='optical',
            parameters={
                'power_min': power_min,
                'power_max': power_max,
                'aperture_min': aperture_min,
                'aperture_max': aperture_max,
                'n_points': n_points,
                'wavelength': wavelength,
                'distance': distance
            },
            results=results
        )

    # =================================================================
    # Pareto Analysis
    # =================================================================

    def find_pareto_front(
        self,
        objectives: np.ndarray,
        objectives_to_maximize: List[bool]
    ) -> Dict[str, Any]:
        """
        Find Pareto front from multi-objective data.

        Args:
            objectives: Array of shape (n_points, n_objectives)
            objectives_to_maximize: List indicating which objectives to maximize

        Returns:
            Dictionary with Pareto indices and normalized objectives
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        analysis = ParetoAnalysis()

        pareto_indices = analysis.find_pareto_front(
            objectives,
            np.array(objectives_to_maximize)
        )

        normalized = analysis.normalize_objectives(objectives)

        return {
            'pareto_indices': pareto_indices.tolist(),
            'n_pareto_points': len(pareto_indices),
            'normalized_objectives': normalized.tolist(),
            'pareto_points': objectives[pareto_indices].tolist()
        }

    def multi_objective_analysis(
        self,
        design_points: List[Dict[str, float]],
        objective_names: List[str],
        maximize_objectives: List[bool]
    ) -> Dict[str, Any]:
        """
        Perform multi-objective Pareto analysis on design points.

        Args:
            design_points: List of design point dictionaries
            objective_names: Names of objectives to analyze
            maximize_objectives: Which objectives to maximize

        Returns:
            Complete Pareto analysis results
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        # Extract objectives into array
        objectives = np.array([
            [point[name] for name in objective_names]
            for point in design_points
        ])

        # Find Pareto front
        pareto_result = self.find_pareto_front(objectives, maximize_objectives)

        # Get Pareto design points
        pareto_designs = [design_points[i] for i in pareto_result['pareto_indices']]

        return {
            'design_points': design_points,
            'objective_names': objective_names,
            'pareto_indices': pareto_result['pareto_indices'],
            'pareto_designs': pareto_designs,
            'pareto_points': pareto_result['pareto_points'],
            'n_pareto': pareto_result['n_pareto_points'],
            'pareto_fraction': pareto_result['n_pareto_points'] / len(design_points)
        }

    # =================================================================
    # Sensitivity Analysis
    # =================================================================

    def sensitivity_analysis(
        self,
        study_type: str,
        parameter_name: str,
        parameter_values: List[float],
        baseline_params: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Perform sensitivity analysis by varying one parameter.

        Args:
            study_type: Type of study ('baseline', 'orbit', 'optical')
            parameter_name: Parameter to vary
            parameter_values: Values to test
            baseline_params: Baseline parameters for study

        Returns:
            Sensitivity analysis results
        """
        if not TRADE_IMPORTS_AVAILABLE:
            raise RuntimeError("Trade study modules not available")

        results_list = []

        for value in parameter_values:
            # Update parameter
            params = baseline_params.copy()
            params[parameter_name] = value

            # Run study with updated parameters
            if study_type == 'baseline':
                result = self.run_baseline_study(**params)
            elif study_type == 'orbit':
                result = self.run_orbit_study(**params)
            elif study_type == 'optical':
                result = self.run_optical_study(**params)
            else:
                raise ValueError(f"Unknown study type: {study_type}")

            results_list.append(result.to_dict())

        return {
            'study_type': study_type,
            'parameter_name': parameter_name,
            'parameter_values': parameter_values,
            'baseline_params': baseline_params,
            'results': results_list
        }

    # =================================================================
    # Comparison and Ranking
    # =================================================================

    def compare_designs(
        self,
        designs: List[Dict[str, Any]],
        weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Compare and rank design alternatives.

        Args:
            designs: List of design configurations with metrics
            weights: Optional weights for weighted scoring

        Returns:
            Ranked designs with scores
        """
        if weights is None:
            # Equal weights
            weights = {key: 1.0 for key in designs[0].keys() if isinstance(designs[0][key], (int, float))}

        # Normalize metrics
        metrics = list(weights.keys())
        for metric in metrics:
            values = [d[metric] for d in designs]
            min_val, max_val = min(values), max(values)

            for design in designs:
                if max_val > min_val:
                    design[f'{metric}_normalized'] = (design[metric] - min_val) / (max_val - min_val)
                else:
                    design[f'{metric}_normalized'] = 0.5

        # Compute weighted scores
        for design in designs:
            score = sum(
                design[f'{metric}_normalized'] * weights[metric]
                for metric in metrics
            )
            design['total_score'] = score

        # Rank designs
        ranked = sorted(designs, key=lambda d: d['total_score'], reverse=True)
        for i, design in enumerate(ranked):
            design['rank'] = i + 1

        return {
            'designs': ranked,
            'weights': weights,
            'best_design': ranked[0]
        }


# Singleton
_trade_study_service = None

def get_trade_study_service() -> TradeStudyService:
    """Get or create trade study service singleton."""
    global _trade_study_service
    if _trade_study_service is None:
        _trade_study_service = TradeStudyService()
    return _trade_study_service
