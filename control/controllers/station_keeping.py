"""
Station-keeping controller for fuel-efficient orbit maintenance.

Implements dead-band control, impulsive maneuvers, and long-term 
orbit maintenance strategies for satellite formations.
"""

import jax
import jax.numpy as jnp
from typing import Tuple, Optional, Dict, List, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class StationKeepingBox:
    """
    Defines the station-keeping box constraints.
    """
    along_track_min: float      # km
    along_track_max: float      # km
    cross_track_min: float      # km
    cross_track_max: float      # km
    radial_min: float          # km
    radial_max: float          # km
    
    def contains(self, position: jnp.ndarray) -> bool:
        """Check if position is within box."""
        return (
            self.along_track_min <= position[0] <= self.along_track_max and
            self.cross_track_min <= position[1] <= self.cross_track_max and
            self.radial_min <= position[2] <= self.radial_max
        )
    
    def distance_to_boundary(self, position: jnp.ndarray) -> float:
        """Minimum distance to any box boundary."""
        distances = jnp.array([
            position[0] - self.along_track_min,
            self.along_track_max - position[0],
            position[1] - self.cross_track_min,
            self.cross_track_max - position[1],
            position[2] - self.radial_min,
            self.radial_max - position[2]
        ])
        return jnp.min(distances)


class DeadBandController:
    """
    Dead-band controller for station-keeping with minimal fuel usage.
    
    Only applies control when satellite approaches box boundaries.
    """
    
    def __init__(
        self,
        n: float,
        box: StationKeepingBox,
        control_threshold: float = 0.8,
        max_thrust: float = 0.001,  # km/s² 
        min_impulse_duration: float = 10.0  # seconds
    ):
        """
        Initialize dead-band controller.
        
        Args:
            n: Mean motion (rad/s)
            box: Station-keeping box definition
            control_threshold: Fraction of box at which to activate (0.8 = 80%)
            max_thrust: Maximum thrust magnitude
            min_impulse_duration: Minimum burn duration
        """
        self.n = n
        self.box = box
        self.control_threshold = control_threshold
        self.max_thrust = max_thrust
        self.min_impulse_duration = min_impulse_duration
        
        # Compute control box (inner boundary where control activates)
        box_size = jnp.array([
            box.along_track_max - box.along_track_min,
            box.cross_track_max - box.cross_track_min,
            box.radial_max - box.radial_min
        ])
        
        margin = box_size * (1 - control_threshold) / 2
        
        self.control_box = StationKeepingBox(
            along_track_min=box.along_track_min + margin[0],
            along_track_max=box.along_track_max - margin[0],
            cross_track_min=box.cross_track_min + margin[1],
            cross_track_max=box.cross_track_max - margin[1],
            radial_min=box.radial_min + margin[2],
            radial_max=box.radial_max - margin[2]
        )
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_control(
        self,
        state: jnp.ndarray,
        time_since_last_burn: float = 0.0
    ) -> Tuple[jnp.ndarray, bool]:
        """
        Compute dead-band control.
        
        Args:
            state: Relative state [x, y, z, vx, vy, vz]
            time_since_last_burn: Time since last maneuver (s)
            
        Returns:
            control: Control acceleration
            fire: Whether to fire thrusters
        """
        position = state[:3]
        velocity = state[3:]
        
        # Check if within control box
        in_control_box = self.control_box.contains(position)
        
        # No control if well within bounds
        if in_control_box:
            return jnp.zeros(3), False
        
        # Compute control to reverse velocity components leading out of box
        control = jnp.zeros(3)
        fire = False
        
        # Along-track (x) control
        if position[0] < self.control_box.along_track_min and velocity[0] < 0:
            control = control.at[0].set(self.max_thrust)
            fire = True
        elif position[0] > self.control_box.along_track_max and velocity[0] > 0:
            control = control.at[0].set(-self.max_thrust)
            fire = True
        
        # Cross-track (y) control
        if position[1] < self.control_box.cross_track_min and velocity[1] < 0:
            control = control.at[1].set(self.max_thrust)
            fire = True
        elif position[1] > self.control_box.cross_track_max and velocity[1] > 0:
            control = control.at[1].set(-self.max_thrust)
            fire = True
        
        # Radial (z) control
        if position[2] < self.control_box.radial_min and velocity[2] < 0:
            control = control.at[2].set(self.max_thrust)
            fire = True
        elif position[2] > self.control_box.radial_max and velocity[2] > 0:
            control = control.at[2].set(-self.max_thrust)
            fire = True
        
        return control, fire
    
    def simulate(
        self,
        initial_state: jnp.ndarray,
        duration: float,
        dt: float = 1.0,
        disturbances: Optional[jnp.ndarray] = None
    ) -> Dict[str, jnp.ndarray]:
        """
        Simulate dead-band control over time.
        
        Args:
            initial_state: Initial relative state
            duration: Simulation duration (s)
            dt: Time step
            disturbances: Disturbance accelerations (N x 3)
            
        Returns:
            Simulation results dictionary
        """
        from ..lqr import hill_clohessy_wiltshire_matrices
        
        # Get dynamics matrices
        A, B = hill_clohessy_wiltshire_matrices(self.n, dt)
        
        steps = int(duration / dt)
        times = jnp.arange(steps) * dt
        
        states = jnp.zeros((steps, 6))
        controls = jnp.zeros((steps, 3))
        burns = jnp.zeros(steps, dtype=bool)
        
        state = initial_state
        time_since_burn = float('inf')
        
        for i in range(steps):
            # Store state
            states = states.at[i].set(state)
            
            # Compute control
            control, fire = self.compute_control(state, time_since_burn)
            
            # Apply minimum impulse duration
            if fire and time_since_burn < self.min_impulse_duration:
                control = jnp.zeros(3)
                fire = False
            
            controls = controls.at[i].set(control)
            burns = burns.at[i].set(fire)
            
            # Update time since burn
            if fire:
                time_since_burn = 0.0
            else:
                time_since_burn += dt
            
            # Propagate state
            disturbance = disturbances[i] if disturbances is not None else jnp.zeros(3)
            state = A @ state + B @ (control + disturbance)
        
        # Compute statistics
        total_burns = jnp.sum(burns)
        total_dv = jnp.sum(jnp.linalg.norm(controls[burns], axis=1)) * dt
        
        return {
            'times': times,
            'states': states,
            'controls': controls,
            'burns': burns,
            'total_burns': total_burns,
            'total_dv': total_dv,
            'fuel_efficiency': total_dv / (duration / 86400)  # m/s per day
        }


class ImpulsiveManeuverPlanner:
    """
    Plans optimal impulsive maneuvers for station-keeping.
    """
    
    def __init__(
        self,
        n: float,
        min_time_between_burns: float = 3600.0  # 1 hour
    ):
        """
        Initialize maneuver planner.
        
        Args:
            n: Mean motion (rad/s)
            min_time_between_burns: Minimum time between maneuvers (s)
        """
        self.n = n
        self.min_time_between_burns = min_time_between_burns
        self.T_orbit = 2 * jnp.pi / n
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_tangential_burn(
        self,
        current_drift_rate: float,
        target_drift_rate: float
    ) -> float:
        """
        Compute tangential burn to achieve desired drift rate.
        
        Args:
            current_drift_rate: Current along-track drift (km/orbit)
            target_drift_rate: Desired drift rate (km/orbit)
            
        Returns:
            dv: Required tangential velocity change (km/s)
        """
        # For circular orbits: Δa/a ≈ 2Δv/v
        # Drift rate ≈ -3π * (Δa/a) * a per orbit
        
        # Simplified: drift_rate ≈ -3 * n * a * Δv
        # So: Δv = -(drift_rate_change) / (3 * n * a)
        
        drift_change = target_drift_rate - current_drift_rate
        
        # Approximate semi-major axis from mean motion
        mu = 398600.4418  # km³/s²
        a = (mu / self.n**2)**(1/3)
        
        dv = -drift_change / (3 * self.n * a * self.T_orbit)
        
        return dv
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_radial_burn_pair(
        self,
        current_position: float,
        target_position: float,
        transfer_time: float
    ) -> Tuple[float, float]:
        """
        Compute radial burn pair for position adjustment.
        
        Uses two burns separated by transfer_time to adjust radial position
        without changing orbit energy.
        
        Args:
            current_position: Current radial offset (km)
            target_position: Target radial offset (km)
            transfer_time: Time between burns (s)
            
        Returns:
            dv1: First radial burn (km/s)
            dv2: Second radial burn (km/s)
        """
        position_change = target_position - current_position
        
        # For small changes: Δz ≈ (Δv_r * T) / π
        # where T is half orbital period for maximum effect
        
        # Optimal transfer time is half orbit
        optimal_time = self.T_orbit / 2
        efficiency = jnp.sin(self.n * transfer_time)
        
        dv1 = position_change * self.n / (2 * efficiency)
        dv2 = -dv1  # Cancel velocity change
        
        return dv1, dv2
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_cross_track_burn(
        self,
        current_position: float,
        current_velocity: float,
        target_position: float
    ) -> float:
        """
        Compute cross-track burn for inclination adjustment.
        
        Args:
            current_position: Current cross-track position (km)
            current_velocity: Current cross-track velocity (km/s)
            target_position: Target cross-track position (km)
            
        Returns:
            dv: Required cross-track velocity change (km/s)
        """
        # Cross-track motion is decoupled (simple harmonic)
        # y(t) = y0*cos(nt) + (vy0/n)*sin(nt)
        
        # To reach target_position with zero velocity:
        # Need vy such that amplitude = target_position
        
        amplitude_current = jnp.sqrt(
            current_position**2 + (current_velocity/self.n)**2
        )
        
        dv_required = -current_velocity + self.n * target_position
        
        return dv_required
    
    def plan_maintenance_cycle(
        self,
        current_state: jnp.ndarray,
        box: StationKeepingBox,
        planning_horizon: float
    ) -> List[Dict]:
        """
        Plan station-keeping maneuvers for planning horizon.
        
        Args:
            current_state: Current relative state
            box: Station-keeping box
            planning_horizon: Planning period (s)
            
        Returns:
            List of planned maneuvers
        """
        maneuvers = []
        
        # Analyze current trajectory
        position = current_state[:3]
        velocity = current_state[3:]
        
        # Estimate drift rates
        drift_rate_x = velocity[0] * self.T_orbit  # km/orbit
        
        # Plan along-track maintenance
        box_center_x = (box.along_track_min + box.along_track_max) / 2
        
        if abs(position[0] - box_center_x) > (box.along_track_max - box.along_track_min) * 0.3:
            # Plan tangential burn to adjust drift
            target_drift = -jnp.sign(position[0] - box_center_x) * 0.001  # Small drift toward center
            dv_tangential = self.compute_tangential_burn(drift_rate_x, target_drift)
            
            maneuvers.append({
                'time': 0.0,
                'type': 'tangential',
                'dv': jnp.array([dv_tangential, 0, 0]),
                'purpose': 'along-track maintenance'
            })
        
        # Plan radial maintenance if needed
        box_center_z = (box.radial_min + box.radial_max) / 2
        
        if abs(position[2] - box_center_z) > (box.radial_max - box.radial_min) * 0.3:
            dv1, dv2 = self.compute_radial_burn_pair(
                position[2], box_center_z, self.T_orbit / 2
            )
            
            maneuvers.append({
                'time': self.min_time_between_burns,
                'type': 'radial',
                'dv': jnp.array([0, 0, dv1]),
                'purpose': 'radial adjustment (burn 1/2)'
            })
            
            maneuvers.append({
                'time': self.min_time_between_burns + self.T_orbit / 2,
                'type': 'radial',
                'dv': jnp.array([0, 0, dv2]),
                'purpose': 'radial adjustment (burn 2/2)'
            })
        
        # Plan cross-track maintenance
        box_center_y = (box.cross_track_min + box.cross_track_max) / 2
        
        if abs(position[1] - box_center_y) > (box.cross_track_max - box.cross_track_min) * 0.3:
            dv_cross = self.compute_cross_track_burn(
                position[1], velocity[1], box_center_y
            )
            
            maneuvers.append({
                'time': len(maneuvers) * self.min_time_between_burns,
                'type': 'cross-track',
                'dv': jnp.array([0, dv_cross, 0]),
                'purpose': 'cross-track maintenance'
            })
        
        return maneuvers


class LongTermStationKeeper:
    """
    Long-term station-keeping strategy with fuel optimization.
    """
    
    def __init__(
        self,
        n: float,
        box: StationKeepingBox,
        fuel_budget_per_year: float = 10.0,  # m/s per year
        planning_horizon_days: int = 7
    ):
        """
        Initialize long-term station keeper.
        
        Args:
            n: Mean motion (rad/s)
            box: Station-keeping box
            fuel_budget_per_year: Annual fuel budget (m/s)
            planning_horizon_days: Planning horizon (days)
        """
        self.n = n
        self.box = box
        self.fuel_budget_per_year = fuel_budget_per_year
        self.planning_horizon = planning_horizon_days * 86400  # seconds
        
        # Daily fuel budget
        self.daily_fuel_budget = fuel_budget_per_year / 365.25 / 1000  # km/s
        
        # Initialize controllers
        self.deadband = DeadBandController(n, box)
        self.maneuver_planner = ImpulsiveManeuverPlanner(n)
        
        # Fuel usage history
        self.fuel_history = []
        self.maneuver_history = []
    
    def update_strategy(
        self,
        current_state: jnp.ndarray,
        elapsed_time: float,
        fuel_used_to_date: float
    ) -> Dict[str, Any]:
        """
        Update station-keeping strategy based on current status.
        
        Args:
            current_state: Current relative state
            elapsed_time: Time since mission start (s)
            fuel_used_to_date: Cumulative fuel used (km/s)
            
        Returns:
            Strategy update dictionary
        """
        # Check fuel usage rate
        days_elapsed = elapsed_time / 86400
        expected_fuel = self.daily_fuel_budget * days_elapsed
        fuel_margin = expected_fuel - fuel_used_to_date
        
        strategy = {
            'mode': 'nominal',
            'fuel_margin': fuel_margin,
            'adjustments': []
        }
        
        # Adjust strategy based on fuel margin
        if fuel_margin < -0.001:  # Over budget
            strategy['mode'] = 'fuel_critical'
            strategy['adjustments'].append('increase_deadband')
            
            # Expand control box to reduce fuel usage
            self.deadband.control_threshold = min(0.95, self.deadband.control_threshold + 0.05)
            
        elif fuel_margin > 0.002:  # Under budget
            strategy['mode'] = 'fuel_surplus'
            strategy['adjustments'].append('tighten_control')
            
            # Tighten control for better accuracy
            self.deadband.control_threshold = max(0.7, self.deadband.control_threshold - 0.02)
        
        # Plan upcoming maneuvers
        planned_maneuvers = self.maneuver_planner.plan_maintenance_cycle(
            current_state, self.box, self.planning_horizon
        )
        
        strategy['planned_maneuvers'] = planned_maneuvers
        strategy['estimated_fuel'] = sum(
            jnp.linalg.norm(m['dv']) for m in planned_maneuvers
        )
        
        return strategy
    
    def simulate_year(
        self,
        initial_state: jnp.ndarray,
        disturbance_level: float = 1e-9  # km/s²
    ) -> Dict[str, Any]:
        """
        Simulate one year of station-keeping.
        
        Args:
            initial_state: Initial relative state
            disturbance_level: RMS disturbance acceleration
            
        Returns:
            Year-long simulation results
        """
        year_seconds = 365.25 * 86400
        dt = 60.0  # 1-minute time step
        steps = int(year_seconds / dt)
        
        # Generate disturbances
        key = jax.random.PRNGKey(42)
        disturbances = jax.random.normal(key, (steps, 3)) * disturbance_level
        
        # Run dead-band control
        results = self.deadband.simulate(
            initial_state,
            year_seconds,
            dt,
            disturbances
        )
        
        # Compute annual statistics
        annual_stats = {
            'total_dv': results['total_dv'] * 1000,  # m/s
            'total_burns': results['total_burns'],
            'fuel_efficiency': results['fuel_efficiency'] * 1000,  # m/s per day
            'max_position_error': jnp.max(jnp.abs(results['states'][:, :3])) * 1000,  # m
            'within_budget': results['total_dv'] * 1000 < self.fuel_budget_per_year
        }
        
        return annual_stats


# Utility functions
@jax.jit
def estimate_annual_fuel(
    n: float,
    box_size: float,
    disturbance_level: float = 1e-9
) -> float:
    """
    Estimate annual fuel requirement for station-keeping.
    
    Uses analytical approximation for quick estimates.
    
    Args:
        n: Mean motion (rad/s)
        box_size: Characteristic box dimension (km)
        disturbance_level: RMS disturbance (km/s²)
        
    Returns:
        Estimated annual fuel (m/s)
    """
    # Number of maneuvers per year (approximately)
    T_drift = box_size / (disturbance_level * 86400)  # Time to drift across box
    maneuvers_per_year = 365.25 * 86400 / T_drift
    
    # Fuel per maneuver (order of magnitude)
    dv_per_maneuver = 2 * disturbance_level * T_drift
    
    # Annual fuel
    annual_fuel = maneuvers_per_year * dv_per_maneuver * 1000  # m/s
    
    return annual_fuel


def optimize_box_size(
    n: float,
    fuel_budget: float,
    disturbance_level: float = 1e-9,
    safety_factor: float = 2.0
) -> float:
    """
    Optimize station-keeping box size for given fuel budget.
    
    Args:
        n: Mean motion (rad/s)
        fuel_budget: Annual fuel budget (m/s)
        disturbance_level: RMS disturbance (km/s²)
        safety_factor: Safety margin factor
        
    Returns:
        Optimal box size (km)
    """
    # Fuel scales inversely with box size
    # fuel ∝ disturbance * (year/drift_time) * drift_time
    # fuel ∝ disturbance * year
    # drift_time ∝ box_size / disturbance
    # maneuvers ∝ 1/drift_time ∝ disturbance/box_size
    # fuel ∝ disturbance²/box_size
    
    optimal_box = (
        safety_factor * disturbance_level**2 * 365.25 * 86400 * 1000 / fuel_budget
    )
    
    return optimal_box


# Example usage
if __name__ == "__main__":
    print("Station-Keeping Controller Test")
    print("=" * 50)
    
    # Define station-keeping box (±50m in each direction)
    box = StationKeepingBox(
        along_track_min=-0.050, along_track_max=0.050,
        cross_track_min=-0.050, cross_track_max=0.050,
        radial_min=-0.050, radial_max=0.050
    )
    
    # LEO parameters
    n = 0.001  # rad/s
    
    # Test dead-band controller
    deadband = DeadBandController(n, box, control_threshold=0.8)
    
    # Initial state near boundary
    x0 = jnp.array([0.040, 0.0, 0.0, 0.00001, 0.0, 0.0])  # Near +x boundary
    
    # Simulate for one day
    results = deadband.simulate(x0, 86400, dt=60.0)
    
    print(f"Dead-band Control (1 day):")
    print(f"  Total burns: {results['total_burns']}")
    print(f"  Total ΔV: {results['total_dv']*1000:.3f} m/s")
    print(f"  Fuel efficiency: {results['fuel_efficiency']*1000:.3f} m/s/day")
    print(f"  Max position: {jnp.max(jnp.abs(results['states'][:,:3]))*1000:.1f} m")
    
    # Test maneuver planner
    print(f"\nManeuver Planning:")
    planner = ImpulsiveManeuverPlanner(n)
    maneuvers = planner.plan_maintenance_cycle(x0, box, 7*86400)
    
    for i, m in enumerate(maneuvers):
        print(f"  Maneuver {i+1}: {m['type']}, "
              f"ΔV={jnp.linalg.norm(m['dv'])*1000:.3f} m/s, "
              f"t={m['time']/3600:.1f} hrs")
    
    # Test long-term strategy
    print(f"\nLong-term Station-keeping (1 year):")
    keeper = LongTermStationKeeper(n, box, fuel_budget_per_year=5.0)
    annual = keeper.simulate_year(x0)
    
    print(f"  Annual ΔV: {annual['total_dv']:.2f} m/s")
    print(f"  Total burns: {annual['total_burns']}")
    print(f"  Within budget: {annual['within_budget']}")
    print(f"  Max error: {annual['max_position_error']:.1f} m")
    
    # Estimate optimal box size
    optimal = optimize_box_size(n, fuel_budget=5.0)
    print(f"\nOptimal box size for 5 m/s/year: ±{optimal*1000:.1f} m")
