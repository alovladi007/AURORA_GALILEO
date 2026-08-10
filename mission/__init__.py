"""GALILEO mission scenario generation (Phase 3 W3.1).

Generates honest synthetic mission data — orbits from the validated
dynamics, gravity observables from the real spherical-harmonic field —
and feeds it through the platform's REAL ingestion path (gateway REST
-> gRPC -> TimescaleDB). Every record is provenance-tagged synthetic.
"""

from mission.scenario import (
    MissionConfig,
    MissionScenario,
    ecef_to_geodetic_spherical,
    eci_to_ecef,
)

__all__ = [
    "MissionConfig",
    "MissionScenario",
    "eci_to_ecef",
    "ecef_to_geodetic_spherical",
]
