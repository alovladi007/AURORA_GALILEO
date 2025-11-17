"""
Hardware Driver Interfaces
==========================

Mock hardware drivers for HIL testing.
"""

import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import warnings


@dataclass
class TimingCardConfig:
    """Configuration for timing card."""
    clock_frequency: float = 10e6  # Hz (10 MHz reference)
    resolution: float = 1e-12  # s (1 ps)
    jitter: float = 1e-12  # s RMS
    drift_rate: float = 1e-12  # s/s


class TimingCardDriver(ABC):
    """Abstract base class for timing card driver."""

    @abstractmethod
    def read_time(self) -> float:
        """Read current time from card."""
        pass

    @abstractmethod
    def reset(self):
        """Reset timing card."""
        pass

    @abstractmethod
    def set_trigger(self, time: float):
        """Set hardware trigger at specified time."""
        pass


class MockTimingCard(TimingCardDriver):
    """
    Mock timing card for testing.

    Simulates:
    - Clock drift
    - Jitter
    - Trigger generation
    """

    def __init__(self, config: Optional[TimingCardConfig] = None):
        self.config = config or TimingCardConfig()
        self.start_time = 0.0
        self.drift_accumulated = 0.0
        self.trigger_queue: List[float] = []

    def read_time(self) -> float:
        """
        Read current time with realistic clock behavior.

        Returns:
            Time in seconds
        """
        import time as time_module

        # True elapsed time
        elapsed = time_module.time() - self.start_time

        # Add clock drift
        drift = self.config.drift_rate * elapsed
        self.drift_accumulated += drift

        # Add jitter
        jitter = np.random.randn() * self.config.jitter

        # Total time
        measured_time = elapsed + self.drift_accumulated + jitter

        # Quantize to resolution
        measured_time = np.round(measured_time / self.config.resolution) * self.config.resolution

        return measured_time

    def reset(self):
        """Reset timing card to zero."""
        import time as time_module
        self.start_time = time_module.time()
        self.drift_accumulated = 0.0
        self.trigger_queue = []

    def set_trigger(self, time: float):
        """
        Set hardware trigger at specified time.

        Args:
            time: Trigger time (s)
        """
        self.trigger_queue.append(time)
        self.trigger_queue.sort()

    def check_triggers(self, current_time: float) -> List[float]:
        """
        Check for triggered events.

        Args:
            current_time: Current time (s)

        Returns:
            List of triggered times
        """
        triggered = []

        while self.trigger_queue and self.trigger_queue[0] <= current_time:
            triggered.append(self.trigger_queue.pop(0))

        return triggered


@dataclass
class ADCConfig:
    """Configuration for Analog-to-Digital Converter."""
    sampling_rate: float = 100e6  # Hz (100 MHz)
    resolution_bits: int = 16
    input_range: float = 2.0  # V peak-to-peak
    noise_floor: float = 1e-6  # V RMS


class ADCDriver(ABC):
    """Abstract base class for ADC driver."""

    @abstractmethod
    def acquire(self, duration: float) -> np.ndarray:
        """Acquire data for specified duration."""
        pass

    @abstractmethod
    def configure(self, config: ADCConfig):
        """Configure ADC parameters."""
        pass


class MockADC(ADCDriver):
    """
    Mock ADC for testing.

    Simulates:
    - Quantization noise
    - Thermal noise
    - Sample rate
    """

    def __init__(self, config: Optional[ADCConfig] = None):
        self.config = config or ADCConfig()
        self.buffer: List[float] = []

    def acquire(self, duration: float) -> np.ndarray:
        """
        Acquire data for specified duration.

        Args:
            duration: Acquisition duration (s)

        Returns:
            Acquired samples, shape (n_samples,)
        """
        n_samples = int(duration * self.config.sampling_rate)

        # Simulate input signal (placeholder - would come from real hardware)
        signal = np.zeros(n_samples)

        # Add thermal noise
        noise = np.random.randn(n_samples) * self.config.noise_floor

        # Total signal
        total_signal = signal + noise

        # Quantize
        lsb = self.config.input_range / (2**self.config.resolution_bits)
        quantized = np.round(total_signal / lsb) * lsb

        # Clip to range
        max_value = self.config.input_range / 2
        quantized = np.clip(quantized, -max_value, max_value)

        return quantized

    def configure(self, config: ADCConfig):
        """Update ADC configuration."""
        self.config = config


class ScenarioRunner:
    """
    HIL test scenario runner.

    Coordinates multiple hardware interfaces for integrated testing.
    """

    def __init__(
        self,
        timing_card: Optional[TimingCardDriver] = None,
        adc: Optional[ADCDriver] = None,
    ):
        self.timing_card = timing_card or MockTimingCard()
        self.adc = adc or MockADC()

        self.scenarios: dict = {}

    def register_scenario(self, name: str, scenario_func: callable):
        """
        Register a test scenario.

        Args:
            name: Scenario name
            scenario_func: Function implementing the scenario
        """
        self.scenarios[name] = scenario_func

    def run_scenario(self, name: str, **kwargs) -> dict:
        """
        Run a registered scenario.

        Args:
            name: Scenario name
            **kwargs: Scenario parameters

        Returns:
            Scenario results
        """
        if name not in self.scenarios:
            raise ValueError(f"Unknown scenario: {name}")

        # Reset hardware
        self.timing_card.reset()

        # Run scenario
        results = self.scenarios[name](
            timing_card=self.timing_card,
            adc=self.adc,
            **kwargs,
        )

        return results

    def run_all_scenarios(self) -> dict:
        """
        Run all registered scenarios.

        Returns:
            Dictionary mapping scenario names to results
        """
        all_results = {}

        for name in self.scenarios:
            print(f"Running scenario: {name}")
            try:
                results = self.run_scenario(name)
                all_results[name] = results
                print(f"  ✓ {name} passed")
            except Exception as e:
                all_results[name] = {'error': str(e)}
                print(f"  ✗ {name} failed: {e}")

        return all_results


# ============================================================================
# Example scenarios
# ============================================================================

def timing_accuracy_scenario(
    timing_card: TimingCardDriver,
    adc: ADCDriver,
    duration: float = 10.0,
) -> dict:
    """
    Test scenario: Timing accuracy over duration.

    Args:
        timing_card: Timing card driver
        adc: ADC driver
        duration: Test duration (s)

    Returns:
        Results dictionary
    """
    import time

    # Measure time repeatedly
    measurements = []
    expected_times = []

    start = time.time()

    for i in range(100):
        expected = i * duration / 100
        measured = timing_card.read_time()

        measurements.append(measured)
        expected_times.append(expected)

        time.sleep(duration / 100)

    measurements = np.array(measurements)
    expected_times = np.array(expected_times)

    # Compute error
    errors = measurements - expected_times

    return {
        'mean_error': np.mean(errors),
        'std_error': np.std(errors),
        'max_error': np.max(np.abs(errors)),
        'measurements': measurements,
        'expected': expected_times,
    }


def adc_linearity_scenario(
    timing_card: TimingCardDriver,
    adc: ADCDriver,
    test_voltages: Optional[np.ndarray] = None,
) -> dict:
    """
    Test scenario: ADC linearity.

    Args:
        timing_card: Timing card (unused in this scenario)
        adc: ADC driver
        test_voltages: Voltages to test (V)

    Returns:
        Results dictionary
    """
    if test_voltages is None:
        # Sweep from -1V to +1V
        test_voltages = np.linspace(-1.0, 1.0, 21)

    # Measure each voltage
    # (In real scenario, would set DAC output and measure)
    # For mock, just verify acquisition works

    duration = 0.01  # 10 ms per measurement
    results = []

    for v in test_voltages:
        samples = adc.acquire(duration)
        mean_value = np.mean(samples)
        std_value = np.std(samples)

        results.append({
            'input': v,
            'measured_mean': mean_value,
            'measured_std': std_value,
        })

    return {'measurements': results}


def register_default_scenarios(runner: ScenarioRunner):
    """Register default HIL test scenarios."""
    runner.register_scenario('timing_accuracy', timing_accuracy_scenario)
    runner.register_scenario('adc_linearity', adc_linearity_scenario)
