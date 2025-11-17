"""Tests for CCSDS telemetry."""

import pytest
from telemetry.ccsds import CCSDSPrimaryHeader, CCSDSPacket, TelemetryFramer, TelemetryDeframer


def test_primary_header_pack_unpack():
    """Test CCSDS primary header serialization."""
    header = CCSDSPrimaryHeader(
        apid=100,
        packet_sequence_count=42,
        packet_data_length=255,
    )

    packed = header.pack()
    assert len(packed) == 6

    unpacked = CCSDSPrimaryHeader.unpack(packed)
    assert unpacked.apid == 100
    assert unpacked.packet_sequence_count == 42
    assert unpacked.packet_data_length == 255


def test_framer_deframer_roundtrip():
    """Test framing and deframing."""
    framer = TelemetryFramer(apid=50)
    deframer = TelemetryDeframer()

    user_data = b"Hello, CCSDS!"
    timestamp = 1234567890.5

    # Frame
    packet = framer.frame(user_data, timestamp)

    # Deframe
    result = deframer.deframe(packet)

    assert result['apid'] == 50
    assert result['user_data'] == user_data
    assert abs(result['timestamp'] - timestamp) < 1e-6


def test_sequence_count_increment():
    """Test sequence count increments."""
    framer = TelemetryFramer()

    packet1 = framer.frame(b"First")
    packet2 = framer.frame(b"Second")

    header1 = CCSDSPrimaryHeader.unpack(packet1)
    header2 = CCSDSPrimaryHeader.unpack(packet2)

    assert header2.packet_sequence_count == header1.packet_sequence_count + 1
