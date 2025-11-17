"""
GALILEO V2.0 - Telemetry Module
================================

CCSDS telemetry framing, Protobuf/Avro schemas, and ICD management.

Modules:
    ccsds: CCSDS packet primary/secondary headers
    protobuf_schemas: Protobuf message definitions
    avro_schemas: Avro schemas for archival
    framing: Packet framing/deframing engines
    ingest: Telemetry ingest adapters with backpressure
"""

__version__ = "0.1.0"

# Export main components (to be implemented)
__all__ = [
    "CCSDSPacket",
    "CCSDSPrimaryHeader",
    "CCSDSSecondaryHeader",
    "ProtobufEncoder",
    "AvroEncoder",
    "TelemetryFramer",
    "TelemetryDeframer",
    "IngestAdapter",
]
