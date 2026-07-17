"""
GALILEO V2.0 - Telemetry Module
================================

CCSDS telemetry framing (packet headers, framing/deframing engines).

Modules:
    ccsds: CCSDS packet primary/secondary headers, framer/deframer

Planned (not yet implemented — see MASTER_BUILD_PROMPT_18_MONTHS.md
Phase 1 W1.4): Protobuf/Avro schema encoders and ingest adapters with
backpressure.
"""

__version__ = "0.1.0"

from telemetry.ccsds import (
    CCSDSPacket,
    CCSDSPrimaryHeader,
    CCSDSSecondaryHeader,
    TelemetryFramer,
    TelemetryDeframer,
)

__all__ = [
    "CCSDSPacket",
    "CCSDSPrimaryHeader",
    "CCSDSSecondaryHeader",
    "TelemetryFramer",
    "TelemetryDeframer",
]
