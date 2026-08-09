"""
Tests for Hardware Driver Interfaces
=====================================

Tests mock hardware drivers for HIL testing.
"""

import pytest
import numpy as np
import time
from hil.drivers import (
    TimingCardConfig,
    MockTimingCard,
    ADCConfig,
    MockADC,
    ScenarioRunner,
    timing_accuracy_scenario,
    adc_linearity_scenario,
    register_default_scenarios,
)


class TestTimingCardConfig:
    """Test TimingCardConfig dataclass."""

    def test_default_config(self):
        """Test default timing card configuration."""
        config = TimingCardConfig()

        assert config.clock_frequency == 10e6  # 10 MHz
        assert config.resolution == 1e-12  # 1 ps
        assert config.jitter > 0
        assert config.drift_rate > 0

    def test_custom_config(self):
        """Test custom timing card configuration."""
        config = TimingCardConfig(
            clock_frequency=100e6,
            resolution=1e-15,
            jitter=5e-13,
        )

        assert config.clock_frequency == 100e6
        assert config.resolution == 1e-15
        assert config.jitter == 5e-13


class TestMockTimingCard:
    """Test MockTimingCard driver."""

    def test_initialization(self):
        """Test timing card initialization."""
        card = MockTimingCard()

        assert card.config is not None
        assert card.sim_elapsed == 0.0
        assert len(card.trigger_queue) == 0

    def test_custom_config(self):
        """Test with custom configuration."""
        config = TimingCardConfig(jitter=1e-9, drift_rate=1e-9)
        card = MockTimingCard(config=config)

        assert card.config.jitter == 1e-9
        assert card.config.drift_rate == 1e-9

    def test_read_time(self):
        """Test reading time from card."""
        card = MockTimingCard()
        card.reset()

        time_value = card.read_time()

        assert isinstance(time_value, float)
        assert time_value >= 0

    def test_time_advances(self):
        """Test that time advances."""
        card = MockTimingCard()
        card.reset()

        t1 = card.read_time()
        time.sleep(0.01)  # Wait 10 ms
        t2 = card.read_time()

        assert t2 > t1

    def test_reset(self):
        """Test resetting timing card."""
        card = MockTimingCard()

        # Set some triggers
        card.set_trigger(1.0)
        card.set_trigger(2.0)

        # Reset
        card.reset()

        # Triggers should be cleared
        assert len(card.trigger_queue) == 0
        assert card.sim_elapsed == 0.0

    def test_set_trigger(self):
        """Test setting hardware triggers."""
        card = MockTimingCard()

        card.set_trigger(1.0)
        card.set_trigger(0.5)
        card.set_trigger(2.0)

        # Triggers should be sorted
        assert card.trigger_queue == [0.5, 1.0, 2.0]

    def test_check_triggers(self):
        """Test checking for triggered events."""
        card = MockTimingCard()

        card.set_trigger(1.0)
        card.set_trigger(2.0)
        card.set_trigger(3.0)

        # Check at t=1.5
        triggered = card.check_triggers(1.5)

        # Should trigger 1.0
        assert 1.0 in triggered
        assert 2.0 not in triggered

        # Remaining triggers
        assert card.trigger_queue == [2.0, 3.0]

    def test_check_triggers_multiple(self):
        """Test checking multiple triggers at once."""
        card = MockTimingCard()

        card.set_trigger(1.0)
        card.set_trigger(2.0)
        card.set_trigger(3.0)

        # Check at t=2.5
        triggered = card.check_triggers(2.5)

        # Should trigger 1.0 and 2.0
        assert len(triggered) == 2
        assert 1.0 in triggered
        assert 2.0 in triggered

        # Only 3.0 remains
        assert card.trigger_queue == [3.0]

    def test_quantization(self):
        """Test that time is quantized to resolution."""
        config = TimingCardConfig(resolution=1e-6, jitter=0.0)  # 1 µs resolution, no jitter
        card = MockTimingCard(config=config)
        card.reset()

        time_value = card.read_time()

        # Should be quantized to 1 µs
        # (May not be exact due to drift, but should be close)
        quantized = np.round(time_value / 1e-6) * 1e-6
        assert abs(time_value - quantized) < 1e-9  # Within 1 ns


class TestADCConfig:
    """Test ADCConfig dataclass."""

    def test_default_config(self):
        """Test default ADC configuration."""
        config = ADCConfig()

        assert config.sampling_rate == 100e6  # 100 MHz
        assert config.resolution_bits == 16
        assert config.input_range == 2.0
        assert config.noise_floor > 0

    def test_custom_config(self):
        """Test custom ADC configuration."""
        config = ADCConfig(
            sampling_rate=1e9,
            resolution_bits=14,
            input_range=1.0,
        )

        assert config.sampling_rate == 1e9
        assert config.resolution_bits == 14
        assert config.input_range == 1.0


class TestMockADC:
    """Test MockADC driver."""

    def test_initialization(self):
        """Test ADC initialization."""
        adc = MockADC()

        assert adc.config is not None
        assert len(adc.buffer) == 0

    def test_custom_config(self):
        """Test with custom configuration."""
        config = ADCConfig(sampling_rate=1e6, resolution_bits=12)
        adc = MockADC(config=config)

        assert adc.config.sampling_rate == 1e6
        assert adc.config.resolution_bits == 12

    def test_acquire_basic(self):
        """Test basic data acquisition."""
        adc = MockADC()

        duration = 0.001  # 1 ms
        samples = adc.acquire(duration)

        # Check sample count
        expected_samples = int(duration * adc.config.sampling_rate)
        assert len(samples) == expected_samples

    def test_acquire_returns_array(self):
        """Test that acquire returns numpy array."""
        adc = MockADC()

        samples = adc.acquire(0.001)

        assert isinstance(samples, np.ndarray)

    def test_quantization(self):
        """Test ADC quantization."""
        config = ADCConfig(
            sampling_rate=1e6,
            resolution_bits=8,  # Coarse resolution
            input_range=2.0,
            noise_floor=0.0,  # No noise for this test
        )
        adc = MockADC(config=config)

        samples = adc.acquire(0.001)

        # LSB
        lsb = config.input_range / (2**config.resolution_bits)

        # All samples should be multiples of LSB
        quantized_samples = np.round(samples / lsb) * lsb
        np.testing.assert_array_almost_equal(samples, quantized_samples, decimal=10)

    def test_clipping(self):
        """Test that ADC clips to input range."""
        config = ADCConfig(
            sampling_rate=1e6,
            input_range=1.0,
            noise_floor=0.0,
        )
        adc = MockADC(config=config)

        samples = adc.acquire(0.001)

        # All samples should be within [-0.5, 0.5]
        max_value = config.input_range / 2
        assert np.all(samples >= -max_value)
        assert np.all(samples <= max_value)

    def test_configure(self):
        """Test reconfiguring ADC."""
        adc = MockADC()

        original_rate = adc.config.sampling_rate

        new_config = ADCConfig(sampling_rate=1e9)
        adc.configure(new_config)

        assert adc.config.sampling_rate == 1e9
        assert adc.config.sampling_rate != original_rate

    def test_noise_floor(self):
        """Test that ADC has noise floor."""
        config = ADCConfig(
            sampling_rate=1e6,
            noise_floor=1e-3,  # 1 mV RMS
        )
        adc = MockADC(config=config)

        samples = adc.acquire(0.01)  # Longer duration for better statistics

        # Standard deviation should be close to noise floor
        std = np.std(samples)
        assert 0.5 * config.noise_floor < std < 2.0 * config.noise_floor


class TestScenarioRunner:
    """Test ScenarioRunner for HIL testing."""

    def test_initialization(self):
        """Test scenario runner initialization."""
        runner = ScenarioRunner()

        assert runner.timing_card is not None
        assert runner.adc is not None
        assert len(runner.scenarios) == 0

    def test_custom_hardware(self):
        """Test with custom hardware."""
        timing_card = MockTimingCard()
        adc = MockADC()

        runner = ScenarioRunner(timing_card=timing_card, adc=adc)

        assert runner.timing_card is timing_card
        assert runner.adc is adc

    def test_register_scenario(self):
        """Test registering a scenario."""
        runner = ScenarioRunner()

        def test_scenario(timing_card, adc):
            return {'result': 'success'}

        runner.register_scenario('test', test_scenario)

        assert 'test' in runner.scenarios
        assert runner.scenarios['test'] is test_scenario

    def test_run_scenario(self):
        """Test running a registered scenario."""
        runner = ScenarioRunner()

        def test_scenario(timing_card, adc, param1=10):
            return {'param1': param1, 'timing': timing_card.read_time()}

        runner.register_scenario('test', test_scenario)

        results = runner.run_scenario('test', param1=20)

        assert results['param1'] == 20
        assert 'timing' in results

    def test_run_scenario_unknown(self):
        """Test that running unknown scenario raises error."""
        runner = ScenarioRunner()

        with pytest.raises(ValueError, match="Unknown scenario"):
            runner.run_scenario('nonexistent')

    def test_run_scenario_resets_hardware(self):
        """Test that running scenario resets hardware."""
        timing_card = MockTimingCard()
        timing_card.set_trigger(1.0)
        timing_card.sim_elapsed = 10.0

        runner = ScenarioRunner(timing_card=timing_card)

        def dummy_scenario(timing_card, adc):
            return {}

        runner.register_scenario('dummy', dummy_scenario)
        runner.run_scenario('dummy')

        # Should have reset
        assert timing_card.sim_elapsed == 0.0
        assert len(timing_card.trigger_queue) == 0

    def test_run_all_scenarios(self):
        """Test running all registered scenarios."""
        runner = ScenarioRunner()

        def scenario1(timing_card, adc):
            return {'value': 1}

        def scenario2(timing_card, adc):
            return {'value': 2}

        runner.register_scenario('s1', scenario1)
        runner.register_scenario('s2', scenario2)

        all_results = runner.run_all_scenarios()

        assert 's1' in all_results
        assert 's2' in all_results
        assert all_results['s1']['value'] == 1
        assert all_results['s2']['value'] == 2

    def test_run_all_scenarios_with_failure(self):
        """Test that failures are captured."""
        runner = ScenarioRunner()

        def good_scenario(timing_card, adc):
            return {'status': 'ok'}

        def bad_scenario(timing_card, adc):
            raise RuntimeError("Test error")

        runner.register_scenario('good', good_scenario)
        runner.register_scenario('bad', bad_scenario)

        all_results = runner.run_all_scenarios()

        assert all_results['good']['status'] == 'ok'
        assert 'error' in all_results['bad']
        assert 'Test error' in all_results['bad']['error']


class TestExampleScenarios:
    """Test example HIL scenarios."""

    def test_timing_accuracy_scenario(self):
        """Test timing accuracy scenario."""
        timing_card = MockTimingCard()
        adc = MockADC()

        # Run with short duration for speed
        results = timing_accuracy_scenario(
            timing_card=timing_card,
            adc=adc,
            duration=1.0,
        )

        # Check output structure
        assert 'mean_error' in results
        assert 'std_error' in results
        assert 'max_error' in results
        assert 'measurements' in results
        assert 'expected' in results

        # Basic sanity checks
        assert isinstance(results['mean_error'], (int, float, np.number))
        assert isinstance(results['std_error'], (int, float, np.number))
        assert isinstance(results['max_error'], (int, float, np.number))

    def test_adc_linearity_scenario(self):
        """Test ADC linearity scenario."""
        timing_card = MockTimingCard()
        adc = MockADC()

        results = adc_linearity_scenario(
            timing_card=timing_card,
            adc=adc,
        )

        # Check output structure
        assert 'measurements' in results
        assert len(results['measurements']) > 0

        # Check measurement structure
        for measurement in results['measurements']:
            assert 'input' in measurement
            assert 'measured_mean' in measurement
            assert 'measured_std' in measurement

    def test_adc_linearity_custom_voltages(self):
        """Test ADC linearity with custom test voltages."""
        timing_card = MockTimingCard()
        adc = MockADC()

        test_voltages = np.array([-0.5, 0.0, 0.5])

        results = adc_linearity_scenario(
            timing_card=timing_card,
            adc=adc,
            test_voltages=test_voltages,
        )

        # Should have 3 measurements
        assert len(results['measurements']) == 3

    def test_register_default_scenarios(self):
        """Test registering default scenarios."""
        runner = ScenarioRunner()

        register_default_scenarios(runner)

        # Should have registered scenarios
        assert 'timing_accuracy' in runner.scenarios
        assert 'adc_linearity' in runner.scenarios

    def test_run_default_scenarios(self):
        """Test running default scenarios."""
        runner = ScenarioRunner()
        register_default_scenarios(runner)

        # Run timing accuracy scenario
        results = runner.run_scenario('timing_accuracy', duration=0.5)
        assert 'mean_error' in results

        # Run ADC linearity scenario
        results = runner.run_scenario('adc_linearity')
        assert 'measurements' in results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
