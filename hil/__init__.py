"""
GALILEO V2.0 - Hardware-in-the-Loop (HIL) Module
=================================================

Hardware-in-the-loop testing infrastructure.

Modules:
    optical_bench: Software optical bench emulator
    drivers: Mock hardware drivers (timing cards, ADCs)
"""

from hil.optical_bench import (
    OpticalBenchEmulator,
    LaserParameters,
    OpticalPath,
    simulate_orbital_ranging,
)

from hil.drivers import (
    TimingCardDriver,
    MockTimingCard,
    TimingCardConfig,
    ADCDriver,
    MockADC,
    ADCConfig,
    ScenarioRunner,
    register_default_scenarios,
)

__version__ = "0.1.0"

__all__ = [
    # Optical bench
    "OpticalBenchEmulator",
    "LaserParameters",
    "OpticalPath",
    "simulate_orbital_ranging",
    # Hardware drivers
    "TimingCardDriver",
    "MockTimingCard",
    "TimingCardConfig",
    "ADCDriver",
    "MockADC",
    "ADCConfig",
    # Scenarios
    "ScenarioRunner",
    "register_default_scenarios",
]
