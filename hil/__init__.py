"""
GALILEO V2.0 - Hardware-in-the-Loop (HIL) Module
=================================================

Hardware-in-the-loop testing infrastructure.

Modules:
    emulator: Software optical bench emulator
    drivers: Mock hardware drivers (timing cards, ADCs)
    scenarios: Test scenario scripts
    realtime: Real-time stream processing
"""

__version__ = "0.1.0"

__all__ = [
    "OpticalBenchEmulator",
    "TimingCardDriver",
    "ADCDriver",
    "ScenarioRunner",
    "RealtimeStreamer",
]
