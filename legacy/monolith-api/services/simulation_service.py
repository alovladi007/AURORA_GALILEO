"""
Simulation Service - Business Logic Layer

This service implements the actual simulation functionality,
bridging the API layer with the core simulation modules.
"""

import numpy as np
from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Try to import simulation modules with graceful fallback
try:
    from sim.dynamics import (
        two_body_dynamics,
        perturbed_dynamics,
        orbital_elements_to_cartesian,
        cartesian_to_orbital_elements,
        propagate_orbit,
        propagate_relative_orbit,
        hill_clohessy_wiltshire_dynamics,
        GM_EARTH,
        R_EARTH,
    )
    SIMULATION_AVAILABLE = True
except ImportError as e:
    SIMULATION_AVAILABLE = False
    print(f"Warning: Simulation modules not available: {e}")
    # Define fallback constants
    GM_EARTH = 398600.4418  # km^3/s^2
    R_EARTH = 6378.137  # km


@dataclass
class OrbitalState:
    """Represents an orbital state in Cartesian coordinates."""
    position: np.ndarray  # [x, y, z] in km
    velocity: np.ndarray  # [vx, vy, vz] in km/s
    time: float  # seconds


@dataclass
class OrbitalElements:
    """Represents classical orbital elements."""
    semi_major_axis: float  # km
    eccentricity: float
    inclination: float  # radians
    raan: float  # radians (Ω)
    argument_of_perigee: float  # radians (ω)
    true_anomaly: float  # radians (ν)


class SimulationService:
    """
    Service for orbital dynamics simulation.

    Provides high-level interface for:
    - Orbit propagation (Keplerian and perturbed)
    - Formation flying simulation
    - State conversions
    """

    def __init__(self):
        self.available = SIMULATION_AVAILABLE
        self.mu = GM_EARTH
        self.re = R_EARTH

    def check_available(self):
        """Check if simulation modules are available."""
        if not self.available:
            raise RuntimeError(
                "Simulation modules not available. "
                "Install dependencies: pip install jax jaxlib numpy scipy"
            )

    def propagate_orbit_simple(
        self,
        initial_state: np.ndarray,
        duration: float,
        time_step: float = 10.0,
        include_perturbations: bool = False
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Propagate an orbit using RK4 integration.

        Args:
            initial_state: [x, y, z, vx, vy, vz] in km and km/s
            duration: Total propagation time in seconds
            time_step: Integration time step in seconds
            include_perturbations: Include J2, drag, SRP if True

        Returns:
            times: Array of time points
            states: Array of state vectors at each time
        """
        self.check_available()

        # Choose dynamics function
        if include_perturbations:
            dynamics_func = perturbed_dynamics
        else:
            dynamics_func = two_body_dynamics

        # Use the propagator
        times, states = propagate_orbit(
            dynamics_func,
            initial_state,
            t_span=(0.0, duration),
            dt=time_step
        )

        return np.array(times), np.array(states)

    def orbital_elements_to_state(
        self,
        elements: OrbitalElements
    ) -> OrbitalState:
        """
        Convert orbital elements to Cartesian state.

        Args:
            elements: Classical orbital elements

        Returns:
            OrbitalState with position and velocity
        """
        self.check_available()

        # Pack elements into array [a, e, i, Ω, ω, ν]
        oe = np.array([
            elements.semi_major_axis,
            elements.eccentricity,
            elements.inclination,
            elements.raan,
            elements.argument_of_perigee,
            elements.true_anomaly,
        ])

        # Convert to Cartesian
        state = orbital_elements_to_cartesian(oe)

        return OrbitalState(
            position=np.array(state[:3]),
            velocity=np.array(state[3:]),
            time=0.0
        )

    def state_to_orbital_elements(
        self,
        state: OrbitalState
    ) -> OrbitalElements:
        """
        Convert Cartesian state to orbital elements.

        Args:
            state: Orbital state in Cartesian coordinates

        Returns:
            OrbitalElements
        """
        self.check_available()

        # Pack state
        state_vec = np.concatenate([state.position, state.velocity])

        # Convert to elements
        elements = cartesian_to_orbital_elements(state_vec)

        return OrbitalElements(
            semi_major_axis=float(elements[0]),
            eccentricity=float(elements[1]),
            inclination=float(elements[2]),
            raan=float(elements[3]),
            argument_of_perigee=float(elements[4]),
            true_anomaly=float(elements[5]),
        )

    def propagate_from_elements(
        self,
        elements: Dict[str, float],
        duration: float,
        time_step: float = 10.0,
        include_perturbations: bool = False
    ) -> Dict[str, Any]:
        """
        High-level function to propagate from orbital elements.

        Args:
            elements: Dict with keys: semi_major_axis, eccentricity, inclination,
                     raan, argument_of_perigee, true_anomaly (angles in degrees)
            duration: Propagation duration in seconds
            time_step: Integration step in seconds
            include_perturbations: Include perturbations

        Returns:
            Dict with times and states
        """
        # Convert angles to radians
        oe = OrbitalElements(
            semi_major_axis=elements['semi_major_axis'],
            eccentricity=elements['eccentricity'],
            inclination=np.deg2rad(elements['inclination']),
            raan=np.deg2rad(elements['raan']),
            argument_of_perigee=np.deg2rad(elements['argument_of_perigee']),
            true_anomaly=np.deg2rad(elements['true_anomaly']),
        )

        # Convert to Cartesian
        initial_state = self.orbital_elements_to_state(oe)
        state_vec = np.concatenate([initial_state.position, initial_state.velocity])

        # Propagate
        times, states = self.propagate_orbit_simple(
            state_vec,
            duration,
            time_step,
            include_perturbations
        )

        # Return as serializable dict
        return {
            'times': times.tolist(),
            'states': states.tolist(),
            'num_points': len(times),
            'duration': duration,
            'time_step': time_step,
            'perturbations_included': include_perturbations,
        }

    def simulate_formation(
        self,
        chief_elements: Dict[str, float],
        deputy_offset: List[float],
        duration: float,
        time_step: float = 10.0,
        control_enabled: bool = False
    ) -> Dict[str, Any]:
        """
        Simulate formation flying.

        Args:
            chief_elements: Chief spacecraft orbital elements
            deputy_offset: [dx, dy, dz, dvx, dvy, dvz] in km and km/s
            duration: Simulation duration in seconds
            time_step: Integration step
            control_enabled: Enable formation control (not yet implemented)

        Returns:
            Dict with chief and deputy trajectories
        """
        self.check_available()

        # Propagate chief
        chief_result = self.propagate_from_elements(
            chief_elements,
            duration,
            time_step
        )

        # Calculate mean motion from semi-major axis
        a = chief_elements['semi_major_axis']
        n = np.sqrt(self.mu / a**3)  # rad/s

        # Propagate relative motion
        delta_state = np.array(deputy_offset)
        times, rel_states = propagate_relative_orbit(
            delta_state,
            n,
            t_span=(0.0, duration),
            dt=time_step
        )

        return {
            'chief': chief_result,
            'relative_motion': {
                'times': times.tolist(),
                'states': rel_states.tolist(),
                'mean_motion': float(n),
            },
            'control_enabled': control_enabled,
        }

    def compute_orbital_parameters(
        self,
        elements: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Compute derived orbital parameters.

        Args:
            elements: Orbital elements

        Returns:
            Dict with orbital period, altitude, etc.
        """
        a = elements['semi_major_axis']
        e = elements['eccentricity']

        # Orbital period
        T = 2 * np.pi * np.sqrt(a**3 / self.mu)

        # Perigee and apogee
        r_p = a * (1 - e) - self.re  # altitude
        r_a = a * (1 + e) - self.re  # altitude

        # Mean motion
        n = np.sqrt(self.mu / a**3)

        # Energy
        energy = -self.mu / (2 * a)

        return {
            'orbital_period_s': float(T),
            'orbital_period_min': float(T / 60),
            'perigee_altitude_km': float(r_p),
            'apogee_altitude_km': float(r_a),
            'mean_motion_rad_s': float(n),
            'mean_motion_deg_s': float(np.rad2deg(n)),
            'specific_energy_km2_s2': float(energy),
        }


# Global service instance
_simulation_service = None

def get_simulation_service() -> SimulationService:
    """Get or create simulation service singleton."""
    global _simulation_service
    if _simulation_service is None:
        _simulation_service = SimulationService()
    return _simulation_service
