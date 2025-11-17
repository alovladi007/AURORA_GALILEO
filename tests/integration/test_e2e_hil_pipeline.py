"""
E2E Integration Test: HIL Pipeline
===================================

Tests complete HIL workflow from emulation through data collection and analysis.
"""

import pytest
import numpy as np
from hil.optical_bench import OpticalBenchEmulator, LaserParameters, OpticalPath
from hil.drivers import MockTimingCard, MockADC, ScenarioRunner, TimingCardConfig, ADCConfig
from data.stac import STACCatalog, STACItem, STACAsset


class TestHILPipeline:
    """Test complete HIL testing pipeline."""

    def test_synchronized_measurement_campaign(self):
        """
        E2E test: Synchronized multi-instrument measurement campaign.

        Simulates:
        1. Timing card provides precise time base
        2. Optical bench measures inter-satellite range
        3. ADC captures telemetry signals
        4. Data is collected and cataloged
        """
        # Step 1: Initialize hardware
        timing_card = MockTimingCard(
            config=TimingCardConfig(
                clock_frequency=10e6,
                jitter=1e-12,
                drift_rate=1e-13,
            )
        )
        timing_card.reset()

        adc = MockADC(
            config=ADCConfig(
                sampling_rate=1e6,
                resolution_bits=16,
                input_range=2.0,
            )
        )

        optical_bench = OpticalBenchEmulator(
            laser_params=LaserParameters(
                wavelength=1064e-9,
                power=1.0,
                frequency_noise=1e3,
            ),
            optical_path=OpticalPath(
                baseline=200e3,
                pointing_jitter=1e-6,
            ),
            sampling_rate=10.0,
            seed=42,
        )

        # Step 2: Define measurement scenario
        duration = 10.0  # seconds
        n_measurements = int(duration * optical_bench.sampling_rate)

        # Orbital range variation
        baseline = 200e3
        eccentricity = 0.01
        period = 3600.0
        omega = 2 * np.pi / period

        def range_function(t):
            return baseline * (1 + eccentricity * np.cos(omega * t))

        # Step 3: Execute synchronized measurements
        measurements = []

        for i in range(n_measurements):
            # Read precise time from timing card
            t = timing_card.read_time()

            # Compute true range
            true_range = range_function(t)

            # Measure phase with optical bench
            measured_phase, diagnostics = optical_bench.measure_phase(true_range)

            # Record measurement
            measurements.append({
                'time': t,
                'true_range': true_range,
                'measured_phase': measured_phase,
                'phase_noise': diagnostics['total_noise_rms'],
            })

            # Simulate some delay
            import time
            time.sleep(0.001)

        # Step 4: Acquire ADC data (simulating telemetry)
        telemetry_data = adc.acquire(duration=0.1)

        # Step 5: Analyze measurements
        times = np.array([m['time'] for m in measurements])
        phases = np.array([m['measured_phase'] for m in measurements])
        true_ranges = np.array([m['true_range'] for m in measurements])
        noise_levels = np.array([m['phase_noise'] for m in measurements])

        # Convert phase to range
        wavelength = optical_bench.laser.wavelength
        measured_ranges = phases * wavelength

        # Compute ranging error
        range_errors = measured_ranges - true_ranges
        rms_error = np.sqrt(np.mean(range_errors**2))

        # Step 6: Create STAC catalog for measurement data
        catalog = STACCatalog(catalog_id="hil-measurements")

        # Create item for ranging data
        item = STACItem(
            id=f"ranging-{int(times[0])}",
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[-1.0, -1.0, 1.0, 1.0],
            properties={
                'datetime': '2024-01-01T00:00:00Z',
                'duration': duration,
                'n_measurements': n_measurements,
                'rms_error_m': float(rms_error),
                'mean_noise_cycles': float(np.mean(noise_levels)),
                'instrument': 'optical_bench',
            },
            assets={
                'phase_data': STACAsset(
                    href='data/phase_measurements.csv',
                    title='Phase Measurements',
                    type='text/csv',
                    roles=['data'],
                ),
                'telemetry': STACAsset(
                    href='data/telemetry.bin',
                    title='ADC Telemetry',
                    type='application/octet-stream',
                    roles=['metadata'],
                ),
            },
        )
        catalog.add_item(item)

        # Step 7: Validate results
        assert len(measurements) == n_measurements
        assert rms_error < 1.0, f"RMS ranging error {rms_error:.6f} m too large"
        assert len(telemetry_data) > 0
        assert len(catalog.items) == 1

        # Step 8: Return comprehensive results
        return {
            'measurements': measurements,
            'rms_error': rms_error,
            'mean_noise': np.mean(noise_levels),
            'telemetry_samples': len(telemetry_data),
            'catalog': catalog,
        }

    def test_timing_synchronization_validation(self):
        """
        E2E test: Validate timing synchronization across instruments.
        """
        # Create multiple timing cards
        card1 = MockTimingCard(config=TimingCardConfig(drift_rate=1e-12))
        card2 = MockTimingCard(config=TimingCardConfig(drift_rate=2e-12))

        card1.reset()
        card2.reset()

        # Synchronize
        import time
        start_time = time.time()

        # Measure time drift over 1 second
        n_samples = 100
        drifts = []

        for _ in range(n_samples):
            t1 = card1.read_time()
            t2 = card2.read_time()
            drift = abs(t1 - t2)
            drifts.append(drift)
            time.sleep(0.01)

        # Validate synchronization
        mean_drift = np.mean(drifts)
        max_drift = np.max(drifts)

        # Drift should be small (picosecond level)
        assert mean_drift < 1e-9, f"Mean drift {mean_drift:.3e} s too large"
        assert max_drift < 1e-8, f"Max drift {max_drift:.3e} s too large"

        return {
            'mean_drift': mean_drift,
            'max_drift': max_drift,
            'std_drift': np.std(drifts),
        }

    def test_scenario_runner_integration(self):
        """
        E2E test: Run multiple HIL scenarios and validate results.
        """
        # Create scenario runner
        runner = ScenarioRunner()

        # Register custom scenario: Full measurement cycle
        def full_measurement_scenario(timing_card, adc, duration=1.0):
            # Reset timing
            timing_card.reset()

            # Set triggers
            trigger_times = [0.1, 0.5, 0.9]
            for t in trigger_times:
                timing_card.set_trigger(t)

            # Simulate measurements
            measurements = []
            import time
            start = time.time()

            while time.time() - start < duration:
                current_time = timing_card.read_time()

                # Check for triggers
                triggered = timing_card.check_triggers(current_time)

                if triggered:
                    # Acquire ADC data on trigger
                    samples = adc.acquire(0.001)  # 1 ms burst
                    measurements.append({
                        'trigger_time': triggered[0],
                        'samples': len(samples),
                        'mean_value': np.mean(samples),
                    })

                time.sleep(0.01)

            return {
                'n_triggers': len(measurements),
                'measurements': measurements,
            }

        runner.register_scenario('full_measurement', full_measurement_scenario)

        # Run scenario
        result = runner.run_scenario('full_measurement', duration=1.0)

        # Validate
        assert result['n_triggers'] == 3, "Should capture 3 triggers"
        assert len(result['measurements']) == 3

        # Run all scenarios (including defaults)
        from hil.drivers import register_default_scenarios
        register_default_scenarios(runner)

        all_results = runner.run_all_scenarios()

        # All scenarios should pass
        for name, result in all_results.items():
            assert 'error' not in result, f"Scenario {name} failed: {result.get('error')}"

        return all_results

    def test_heterodyne_detection_pipeline(self):
        """
        E2E test: Complete heterodyne detection and PLL tracking pipeline.
        """
        # Create optical bench
        emulator = OpticalBenchEmulator(
            sampling_rate=10000.0,  # 10 kHz for beat signal
            seed=42,
        )

        # Generate heterodyne beat signal
        signal_freq = 100e6  # 100 MHz
        lo_freq = 100.01e6   # 100.01 MHz (10 kHz beat)
        duration = 0.5       # 500 ms

        beat_signal = emulator.heterodyne_beat(signal_freq, lo_freq, duration)

        # Track with PLL
        center_freq = 10e3  # Expected beat at 10 kHz
        bandwidth = 100.0   # 100 Hz bandwidth

        phase, freq = emulator.pll_tracking(beat_signal, center_freq, bandwidth)

        # Analyze tracking performance
        # After lock-in, frequency should be close to 10 kHz
        steady_state = freq[-1000:]  # Last 1000 samples
        mean_freq = np.mean(steady_state)
        std_freq = np.std(steady_state)

        # Validate
        expected_beat = abs(signal_freq - lo_freq)
        assert abs(mean_freq - expected_beat) < 100.0, \
            f"PLL should track beat frequency: got {mean_freq:.1f} Hz, expected {expected_beat:.1f} Hz"

        assert std_freq < 50.0, \
            f"PLL frequency jitter {std_freq:.1f} Hz too large"

        return {
            'mean_frequency': mean_freq,
            'std_frequency': std_freq,
            'expected_frequency': expected_beat,
            'tracking_error': abs(mean_freq - expected_beat),
            'n_samples': len(beat_signal),
        }

    def test_complete_hil_session(self):
        """
        E2E test: Complete HIL session with all instruments.

        Simulates a realistic HIL test session:
        1. Hardware initialization and self-test
        2. Calibration measurements
        3. Science measurements
        4. Data cataloging and export
        """
        # Phase 1: Initialization
        timing_card = MockTimingCard()
        adc = MockADC()
        optical_bench = OpticalBenchEmulator(sampling_rate=10.0, seed=42)

        timing_card.reset()

        # Phase 2: Self-test
        self_test_passed = True

        # Test timing card
        t1 = timing_card.read_time()
        import time
        time.sleep(0.01)
        t2 = timing_card.read_time()
        if t2 <= t1:
            self_test_passed = False

        # Test ADC
        test_data = adc.acquire(0.001)
        if len(test_data) == 0:
            self_test_passed = False

        # Test optical bench
        _, diag = optical_bench.measure_phase(200e3)
        if diag['total_noise_rms'] <= 0:
            self_test_passed = False

        assert self_test_passed, "Self-test should pass"

        # Phase 3: Calibration (measure known baseline)
        calibration_range = 200e3  # 200 km
        calibration_measurements = []

        for _ in range(10):
            phase, _ = optical_bench.measure_phase(calibration_range)
            calibration_measurements.append(phase)

        calibration_mean = np.mean(calibration_measurements)
        calibration_std = np.std(calibration_measurements)

        # Phase 4: Science measurements (varying range)
        science_measurements = []
        for i in range(50):
            # Sinusoidal variation
            t = i * 0.1
            range_var = calibration_range * (1 + 0.01 * np.sin(2 * np.pi * t / 10.0))
            phase, diag = optical_bench.measure_phase(range_var)

            science_measurements.append({
                'time': t,
                'range': range_var,
                'phase': phase,
                'noise': diag['total_noise_rms'],
            })

        # Phase 5: Data cataloging
        catalog = STACCatalog(catalog_id="hil-session")

        session_item = STACItem(
            id="hil-session-001",
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[-1.0, -1.0, 1.0, 1.0],
            properties={
                'datetime': '2024-01-01T00:00:00Z',
                'session_type': 'complete_hil',
                'self_test_passed': self_test_passed,
                'calibration_mean_phase': float(calibration_mean),
                'calibration_std_phase': float(calibration_std),
                'n_science_measurements': len(science_measurements),
            },
            assets={
                'calibration': STACAsset(
                    href='data/calibration.csv',
                    title='Calibration Data',
                    roles=['calibration'],
                ),
                'science': STACAsset(
                    href='data/science.csv',
                    title='Science Measurements',
                    roles=['data'],
                ),
            },
        )
        catalog.add_item(session_item)

        # Validate session
        assert len(calibration_measurements) == 10
        assert len(science_measurements) == 50
        assert calibration_std > 0, "Should have measurement noise"
        assert len(catalog.items) == 1

        return {
            'self_test_passed': self_test_passed,
            'calibration_mean': calibration_mean,
            'calibration_std': calibration_std,
            'n_science_measurements': len(science_measurements),
            'catalog': catalog,
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
