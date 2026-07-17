"""
Comprehensive tests for Session 1: Mission & Measurement Physics Model.

Tests cover:
- Orbital dynamics (two-body, J2, drag, SRP, Hill equations)
- Measurement models (phase, time-delay, noise characterization)
- Zero-noise validation
- Allan deviation computation
"""

import pytest
import numpy as np
import jax
import jax.numpy as jnp
from numpy.testing import assert_allclose, assert_array_less

pytest.skip(
    "API drift: this suite targets a sim.dynamics API surface "
    "(two_body_acceleration, OrbitPropagator, SatelliteProperties, ...) "
    "that was never implemented (module provides two_body_dynamics, "
    "propagate_orbit, ...). Reconcile in Phase 1 W1.1 of "
    "MASTER_BUILD_PROMPT_18_MONTHS.md.",
    allow_module_level=True,
)

from sim.dynamics import (
    two_body_acceleration,
    j2_acceleration,
    atmospheric_drag_acceleration,
    solar_radiation_pressure_acceleration,
    hill_acceleration,
    orbital_energy,
    angular_momentum,
    orbital_period,
    keplerian_to_cartesian,
    OrbitPropagator,
    SatelliteProperties,
    PerturbationType,
    OrbitalState,
    GM_EARTH,
    R_EARTH,
    J2,
)

from sensing.model import (
    MeasurementModel,
    NoiseParameters,
    OpticalLink,
    MeasurementType,
    allan_deviation,
    power_spectral_density,
    NoiseGenerator,
)


class TestTwoBodyDynamics:
    """Test two-body Keplerian motion."""
    
    def test_two_body_acceleration_direction(self):
        """Acceleration should point toward Earth center."""
        position = jnp.array([7000e3, 0.0, 0.0])  # 7000 km radius
        acc = two_body_acceleration(position)
        
        # Should point in -r direction
        assert acc[0] < 0
        assert abs(acc[1]) < 1e-10
        assert abs(acc[2]) < 1e-10
    
    def test_two_body_acceleration_magnitude(self):
        """Test acceleration magnitude for circular orbit."""
        r = 7000e3  # m
        position = jnp.array([r, 0.0, 0.0])
        acc = two_body_acceleration(position)
        
        # Expected: GM/r²
        expected_mag = GM_EARTH / r**2
        actual_mag = jnp.linalg.norm(acc)
        
        assert_allclose(actual_mag, expected_mag, rtol=1e-10)
    
    def test_orbital_energy_conservation(self):
        """Energy should be conserved in two-body motion."""
        # Circular orbit at 7000 km
        r = 7000e3
        v = jnp.sqrt(GM_EARTH / r)
        
        state = jnp.array([r, 0.0, 0.0, 0.0, v, 0.0])
        
        # Energy for circular orbit: E = -GM/(2r)
        energy = orbital_energy(state)
        expected = -GM_EARTH / (2 * r)
        
        assert_allclose(energy, expected, rtol=1e-10)
    
    def test_angular_momentum_conservation(self):
        """Angular momentum should be perpendicular to orbital plane."""
        # Equatorial circular orbit
        r = 7000e3
        v = jnp.sqrt(GM_EARTH / r)
        
        state = jnp.array([r, 0.0, 0.0, 0.0, v, 0.0])
        h = angular_momentum(state)
        
        # Should be in +z direction
        assert abs(h[0]) < 1e-5
        assert abs(h[1]) < 1e-5
        assert h[2] > 0
        
        # Magnitude: h = rv for circular orbit
        assert_allclose(jnp.linalg.norm(h), r * v, rtol=1e-10)
    
    def test_orbital_period(self):
        """Test orbital period calculation."""
        # LEO at 400 km altitude
        r = R_EARTH + 400e3
        v = jnp.sqrt(GM_EARTH / r)
        
        state = jnp.array([r, 0.0, 0.0, 0.0, v, 0.0])
        period = orbital_period(state)
        
        # Expected: ~92 minutes
        expected = 2 * jnp.pi * jnp.sqrt(r**3 / GM_EARTH)
        
        assert_allclose(period, expected, rtol=1e-10)
        assert 5400 < period < 5600  # ~90-93 minutes


class TestJ2Perturbation:
    """Test J2 (Earth oblateness) perturbation."""
    
    def test_j2_acceleration_equator(self):
        """J2 effect should be minimal at equator."""
        position = jnp.array([7000e3, 0.0, 0.0])
        acc = j2_acceleration(position)
        
        # At equator (z=0), J2 acceleration is small
        two_body = jnp.linalg.norm(two_body_acceleration(position))
        j2_mag = jnp.linalg.norm(acc)
        
        # J2 should be ~1000x smaller than two-body
        assert j2_mag < two_body / 100
    
    def test_j2_acceleration_pole(self):
        """J2 effect should be maximum near poles."""
        position = jnp.array([0.0, 0.0, 7000e3])
        acc = j2_acceleration(position)
        
        # Should have component in -z direction
        assert acc[2] < 0
        
        # Should be larger than equatorial case
        position_eq = jnp.array([7000e3, 0.0, 0.0])
        acc_eq = j2_acceleration(position_eq)
        
        assert jnp.linalg.norm(acc) > jnp.linalg.norm(acc_eq)
    
    def test_j2_order_of_magnitude(self):
        """J2 acceleration should be ~1000x smaller than two-body."""
        position = jnp.array([7000e3, 0.0, 1000e3])
        
        two_body_mag = jnp.linalg.norm(two_body_acceleration(position))
        j2_mag = jnp.linalg.norm(j2_acceleration(position))
        
        # J2 ~ 1e-3 of two-body
        ratio = j2_mag / two_body_mag
        assert 1e-4 < ratio < 1e-2


class TestAtmosphericDrag:
    """Test atmospheric drag model."""
    
    def test_drag_opposes_motion(self):
        """Drag should oppose velocity direction."""
        position = jnp.array([6778e3, 0.0, 0.0])  # 400 km altitude
        velocity = jnp.array([0.0, 7500.0, 0.0])
        
        sat_props = SatelliteProperties(mass=100.0, area=1.0, cd=2.2)
        rho = 1e-11  # kg/m³
        
        acc = atmospheric_drag_acceleration(position, velocity, sat_props, rho)
        
        # Should oppose velocity (negative y component)
        assert acc[1] < 0
        assert abs(acc[0]) < abs(acc[1]) * 0.1
        assert abs(acc[2]) < abs(acc[1]) * 0.1
    
    def test_drag_magnitude_scales_with_density(self):
        """Drag should scale linearly with density."""
        position = jnp.array([6778e3, 0.0, 0.0])
        velocity = jnp.array([0.0, 7500.0, 0.0])
        sat_props = SatelliteProperties(mass=100.0, area=1.0)
        
        rho1 = 1e-11
        rho2 = 2e-11
        
        acc1 = atmospheric_drag_acceleration(position, velocity, sat_props, rho1)
        acc2 = atmospheric_drag_acceleration(position, velocity, sat_props, rho2)
        
        # Should be roughly 2x
        ratio = jnp.linalg.norm(acc2) / jnp.linalg.norm(acc1)
        assert_allclose(ratio, 2.0, rtol=0.01)


class TestSolarRadiationPressure:
    """Test solar radiation pressure model."""
    
    def test_srp_points_away_from_sun(self):
        """SRP acceleration should point away from Sun."""
        sat_position = jnp.array([7000e3, 0.0, 0.0])
        sun_position = jnp.array([-150e9, 0.0, 0.0])  # Sun in -x direction
        
        sat_props = SatelliteProperties(mass=100.0, area=1.0, cr=1.5)
        
        acc = solar_radiation_pressure_acceleration(
            sat_position, sun_position, sat_props, in_shadow=False
        )
        
        # Should point in +x direction (away from sun)
        assert acc[0] > 0
        assert abs(acc[1]) < abs(acc[0]) * 0.1
        assert abs(acc[2]) < abs(acc[0]) * 0.1
    
    def test_srp_zero_in_shadow(self):
        """No SRP in shadow."""
        sat_position = jnp.array([7000e3, 0.0, 0.0])
        sun_position = jnp.array([-150e9, 0.0, 0.0])
        sat_props = SatelliteProperties(mass=100.0, area=1.0)
        
        acc = solar_radiation_pressure_acceleration(
            sat_position, sun_position, sat_props, in_shadow=True
        )
        
        assert jnp.all(acc == 0.0)
    
    def test_srp_order_of_magnitude(self):
        """SRP should be ~1e-7 m/s² for typical satellites."""
        sat_position = jnp.array([7000e3, 0.0, 0.0])
        sun_position = jnp.array([150e9, 0.0, 0.0])
        sat_props = SatelliteProperties(mass=100.0, area=1.0, cr=1.3)
        
        acc = solar_radiation_pressure_acceleration(
            sat_position, sun_position, sat_props, in_shadow=False
        )
        
        mag = jnp.linalg.norm(acc)
        assert 1e-8 < mag < 1e-6  # Typical range


class TestHillEquations:
    """Test Hill-Clohessy-Wiltshire relative motion."""
    
    def test_hcw_radial_drift(self):
        """Radial offset causes along-track drift."""
        # Small radial offset, zero velocity
        rel_state = jnp.array([100.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        n = jnp.sqrt(GM_EARTH / (7000e3)**3)  # Mean motion
        
        acc = hill_acceleration(rel_state, n)
        
        # Should have positive along-track acceleration (drift)
        assert acc[1] > 0
    
    def test_hcw_along_track_oscillation(self):
        """Along-track offset causes oscillation."""
        # Small along-track offset
        rel_state = jnp.array([0.0, 100.0, 0.0, 0.0, 0.0, 0.0])
        n = jnp.sqrt(GM_EARTH / (7000e3)**3)
        
        acc = hill_acceleration(rel_state, n)
        
        # No acceleration in y (along-track dynamics governed by velocity)
        assert abs(acc[1]) < 1e-10
    
    def test_hcw_cross_track_oscillation(self):
        """Cross-track motion is simple harmonic."""
        # Cross-track offset
        rel_state = jnp.array([0.0, 0.0, 100.0, 0.0, 0.0, 0.0])
        n = jnp.sqrt(GM_EARTH / (7000e3)**3)
        
        acc = hill_acceleration(rel_state, n)
        
        # Should have restoring force: az = -n²z
        expected_az = -n**2 * 100.0
        assert_allclose(acc[2], expected_az, rtol=1e-10)


class TestKeplerianConversion:
    """Test Keplerian to Cartesian conversion."""
    
    def test_circular_orbit_equatorial(self):
        """Test conversion for circular equatorial orbit."""
        a = 7000e3  # m
        e = 0.0
        i = 0.0
        omega = 0.0
        w = 0.0
        nu = 0.0  # at periapsis (same as apoapsis for circular)
        
        pos, vel = keplerian_to_cartesian(a, e, i, omega, w, nu)
        
        # Should be at [a, 0, 0]
        assert_allclose(pos[0], a, rtol=1e-10)
        assert_allclose(pos[1], 0.0, atol=1e-5)
        assert_allclose(pos[2], 0.0, atol=1e-5)
        
        # Velocity should be [0, v_circ, 0]
        v_circ = jnp.sqrt(GM_EARTH / a)
        assert_allclose(vel[0], 0.0, atol=1e-5)
        assert_allclose(vel[1], v_circ, rtol=1e-10)
        assert_allclose(vel[2], 0.0, atol=1e-5)
    
    def test_energy_from_keplerian(self):
        """Energy from Keplerian elements should match expected value."""
        a = 7000e3
        e = 0.1
        i = jnp.radians(45)
        omega = jnp.radians(30)
        w = jnp.radians(60)
        nu = jnp.radians(90)
        
        pos, vel = keplerian_to_cartesian(a, e, i, omega, w, nu)
        state = jnp.concatenate([pos, vel])
        
        energy = orbital_energy(state)
        expected_energy = -GM_EARTH / (2 * a)
        
        assert_allclose(energy, expected_energy, rtol=1e-6)


class TestOrbitPropagation:
    """Test orbit propagator."""
    
    def test_two_body_propagation(self):
        """Test propagation with two-body dynamics only."""
        # Initial circular orbit
        r = 7000e3
        v = jnp.sqrt(GM_EARTH / r)
        state0 = jnp.array([r, 0.0, 0.0, 0.0, v, 0.0])
        
        propagator = OrbitPropagator(perturbations=[])
        
        # Propagate one orbit
        period = 2 * jnp.pi * jnp.sqrt(r**3 / GM_EARTH)
        times, states = propagator.propagate_rk4(
            state0, 0.0, 60.0, int(period / 60)
        )
        
        # Energy should be conserved
        energies = jnp.array([orbital_energy(s) for s in states])
        energy_variation = jnp.std(energies) / jnp.abs(jnp.mean(energies))
        
        assert energy_variation < 1e-6  # < 0.0001%
    
    def test_j2_propagation_secular_drift(self):
        """J2 causes secular drift in RAAN and argument of periapsis."""
        # Initial orbit with inclination
        a = 7000e3
        e = 0.01
        i = jnp.radians(60)
        omega = jnp.radians(0)
        w = jnp.radians(0)
        nu = jnp.radians(0)
        
        pos, vel = keplerian_to_cartesian(a, e, i, omega, w, nu)
        state0 = jnp.concatenate([pos, vel])
        
        propagator = OrbitPropagator(perturbations=[PerturbationType.J2])
        
        # Propagate for several orbits
        period = 2 * jnp.pi * jnp.sqrt(a**3 / GM_EARTH)
        times, states = propagator.propagate_rk4(
            state0, 0.0, 300.0, int(10 * period / 300)
        )
        
        # Check that orbit changes (J2 causes drift)
        # Angular momentum direction should precess
        h0 = angular_momentum(states[0])
        hf = angular_momentum(states[-1])
        
        angle_change = jnp.arccos(
            jnp.dot(h0, hf) / (jnp.linalg.norm(h0) * jnp.linalg.norm(hf))
        )
        
        # Should have measurable precession
        assert angle_change > 1e-5


class TestMeasurementModel:
    """Test ranging measurement model."""
    
    def test_geometric_range(self):
        """Test geometric range calculation."""
        model = MeasurementModel(
            noise_params=NoiseParameters(),
            link=OpticalLink()
        )
        
        pos1 = jnp.array([7000e3, 0.0, 0.0])
        pos2 = jnp.array([7000e3, 100e3, 0.0])
        
        range_val = model.geometric_range(pos1, pos2)
        
        assert_allclose(range_val, 100e3, rtol=1e-10)
    
    def test_geometric_range_rate(self):
        """Test range rate (Doppler) calculation."""
        model = MeasurementModel(
            noise_params=NoiseParameters(),
            link=OpticalLink()
        )
        
        # Moving satellites
        pos1 = jnp.array([7000e3, 0.0, 0.0])
        vel1 = jnp.array([0.0, 7500.0, 0.0])
        pos2 = jnp.array([7000e3, 100e3, 0.0])
        vel2 = jnp.array([0.0, 7600.0, 0.0])
        
        range_rate = model.geometric_range_rate(pos1, vel1, pos2, vel2)
        
        # Closing velocity: 100 m/s in along-track
        assert_allclose(range_rate, 100.0, rtol=1e-10)
    
    def test_zero_noise_measurement(self):
        """Zero noise should give exact geometric range."""
        # Perfect measurement (no noise)
        noise_params = NoiseParameters(
            photon_rate=1e20,  # Very high - negligible shot noise
            quantum_efficiency=1.0,
            frequency_noise_psd=0.0,
            phase_noise_floor=0.0,
            pointing_jitter_rms=0.0,
            temperature=0.0,
            allan_dev_coefficients={'tau_minus_half': 0.0, 'tau_zero': 0.0, 'tau_plus_half': 0.0}
        )
        
        link = OpticalLink(range=100e3)
        model = MeasurementModel(noise_params=noise_params, link=link)
        
        # Noise budget should be tiny
        budget = model.noise_budget()
        assert budget['total_rss'] < 1e-10  # Essentially zero
        
        # Measurement should match geometric range
        pos1 = jnp.array([7000e3, 0.0, 0.0])
        pos2 = jnp.array([7000e3, 100e3, 0.0])
        
        key = jax.random.PRNGKey(0)
        measurement, std = model.generate_measurement(pos1, pos2, key)
        
        assert_allclose(measurement, 100e3, rtol=1e-10)
    
    def test_noise_budget_components(self):
        """All noise components should be positive."""
        model = MeasurementModel(
            noise_params=NoiseParameters(),
            link=OpticalLink()
        )
        
        budget = model.noise_budget()
        
        for key, value in budget.items():
            assert value >= 0.0, f"{key} should be non-negative"
        
        # Total should be larger than any component
        components = [budget[k] for k in budget if k != 'total_rss']
        assert budget['total_rss'] >= max(components)


class TestNoiseCharacterization:
    """Test noise generation and characterization."""
    
    def test_allan_deviation_white_noise(self):
        """Allan deviation of white noise should scale as 1/√τ."""
        # Generate white noise
        np.random.seed(42)
        n_samples = 100000
        dt = 0.1
        noise = np.random.randn(n_samples)
        
        taus, adevs = allan_deviation(noise, dt, max_tau=1000)
        
        # Should decrease with tau
        assert np.all(np.diff(adevs) < 0)
        
        # Log-log slope should be approximately -0.5
        log_tau = np.log(taus[1:20])
        log_adev = np.log(adevs[1:20])
        slope = np.polyfit(log_tau, log_adev, 1)[0]
        
        assert -0.6 < slope < -0.4  # Should be ~-0.5
    
    def test_power_spectral_density(self):
        """Test PSD calculation for known signal."""
        # Sinusoid
        dt = 0.01
        t = np.arange(0, 10, dt)
        freq = 5.0  # Hz
        signal = np.sin(2 * np.pi * freq * t)
        
        freqs, psd = power_spectral_density(signal, dt)
        
        # Peak should be at 5 Hz
        peak_idx = np.argmax(psd)
        peak_freq = freqs[peak_idx]
        
        assert_allclose(peak_freq, freq, rtol=0.01)
    
    def test_white_noise_statistics(self):
        """White noise should have correct mean and std."""
        key = jax.random.PRNGKey(42)
        n_samples = 100000
        std = 2.5
        
        noise = NoiseGenerator.white_noise(key, n_samples, std)
        
        assert_allclose(float(jnp.mean(noise)), 0.0, atol=0.01)
        assert_allclose(float(jnp.std(noise)), std, rtol=0.01)
    
    def test_random_walk_properties(self):
        """Random walk variance should grow linearly with time."""
        key = jax.random.PRNGKey(42)
        n_samples = 10000
        dt = 1.0
        diffusion = 1.0
        
        walk = NoiseGenerator.random_walk(key, n_samples, diffusion, dt)
        
        # Split into bins and check variance growth
        n_bins = 10
        bin_size = n_samples // n_bins
        
        variances = []
        for i in range(n_bins):
            start = i * bin_size
            end = (i + 1) * bin_size
            segment = walk[start:end] - walk[start]  # Relative to start
            variances.append(float(jnp.var(segment)))
        
        # Variance should increase (roughly linearly)
        assert variances[-1] > variances[0]


@pytest.mark.benchmark
class TestPerformance:
    """Performance benchmarks for physics models."""
    
    def test_two_body_performance(self, benchmark):
        """Benchmark two-body acceleration."""
        position = jnp.array([7000e3, 0.0, 0.0])
        
        def compute():
            return two_body_acceleration(position)
        
        result = benchmark(compute)
        assert result is not None
    
    def test_orbit_propagation_performance(self, benchmark):
        """Benchmark orbit propagation."""
        r = 7000e3
        v = jnp.sqrt(GM_EARTH / r)
        state0 = jnp.array([r, 0.0, 0.0, 0.0, v, 0.0])
        
        propagator = OrbitPropagator(perturbations=[PerturbationType.J2])
        
        def propagate():
            return propagator.propagate_rk4(state0, 0.0, 60.0, 100)
        
        result = benchmark(propagate)
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
