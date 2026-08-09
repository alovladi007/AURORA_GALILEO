"""
CCSDS Telemetry Framing
========================

CCSDS (Consultative Committee for Space Data Systems) packet structure.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional
import struct


@dataclass
class CCSDSPrimaryHeader:
    """
    CCSDS Primary Header (6 bytes).

    Bits:
        0-2: Version (always 000)
        3: Type (0=TM, 1=TC)
        4: Secondary header flag
        5-15: APID (Application Process ID)
        16-17: Sequence flags
        18-31: Packet sequence count
        32-47: Packet data length - 1
    """
    version: int = 0
    packet_type: int = 0  # 0=telemetry
    secondary_header_flag: int = 1
    apid: int = 0
    sequence_flags: int = 3  # 11=unsegmented
    packet_sequence_count: int = 0
    packet_data_length: int = 0

    def pack(self) -> bytes:
        """Pack header into 6 bytes."""
        # Packet ID (2 bytes)
        packet_id = (
            (self.version & 0x07) << 13 |
            (self.packet_type & 0x01) << 12 |
            (self.secondary_header_flag & 0x01) << 11 |
            (self.apid & 0x7FF)
        )

        # Packet Sequence Control (2 bytes)
        psc = (
            (self.sequence_flags & 0x03) << 14 |
            (self.packet_sequence_count & 0x3FFF)
        )

        # Packet Data Length (2 bytes)
        pdl = self.packet_data_length & 0xFFFF

        return struct.pack('>HHH', packet_id, psc, pdl)

    @classmethod
    def unpack(cls, data: bytes) -> 'CCSDSPrimaryHeader':
        """Unpack header from 6 bytes."""
        if len(data) < 6:
            raise ValueError("Need at least 6 bytes for primary header")

        packet_id, psc, pdl = struct.unpack('>HHH', data[:6])

        return cls(
            version=(packet_id >> 13) & 0x07,
            packet_type=(packet_id >> 12) & 0x01,
            secondary_header_flag=(packet_id >> 11) & 0x01,
            apid=packet_id & 0x7FF,
            sequence_flags=(psc >> 14) & 0x03,
            packet_sequence_count=psc & 0x3FFF,
            packet_data_length=pdl,
        )


@dataclass
class CCSDSSecondaryHeader:
    """
    CCSDS Secondary Header (mission-specific).

    Common fields:
        - Time code (various formats)
        - Ancillary data
    """
    time_seconds: int = 0
    time_subseconds: int = 0

    def pack(self) -> bytes:
        """Pack secondary header (8 bytes example)."""
        return struct.pack('>II', self.time_seconds, self.time_subseconds)

    @classmethod
    def unpack(cls, data: bytes) -> 'CCSDSSecondaryHeader':
        """Unpack secondary header."""
        if len(data) < 8:
            raise ValueError("Need at least 8 bytes for secondary header")

        time_sec, time_subsec = struct.unpack('>II', data[:8])

        return cls(
            time_seconds=time_sec,
            time_subseconds=time_subsec,
        )


@dataclass
class CCSDSPacket:
    """
    Complete CCSDS packet.

    Structure:
        - Primary header (6 bytes)
        - Secondary header (optional, N bytes)
        - User data
    """
    primary_header: CCSDSPrimaryHeader
    secondary_header: Optional[CCSDSSecondaryHeader] = None
    user_data: bytes = b''

    def pack(self) -> bytes:
        """Pack packet into bytes."""
        # Pack primary header
        packet = self.primary_header.pack()

        # Pack secondary header if present
        if self.secondary_header is not None:
            packet += self.secondary_header.pack()

        # Append user data
        packet += self.user_data

        return packet

    @classmethod
    def unpack(cls, data: bytes) -> 'CCSDSPacket':
        """Unpack packet from bytes."""
        # Unpack primary header
        primary = CCSDSPrimaryHeader.unpack(data)

        offset = 6

        # Unpack secondary header if present
        secondary = None
        if primary.secondary_header_flag:
            secondary = CCSDSSecondaryHeader.unpack(data[offset:])
            offset += 8  # Assuming 8-byte secondary header

        # Extract user data. packet_data_length is (data-field length
        # - 1) per CCSDS 133.0-B, where the data field INCLUDES the
        # secondary header; subtract the 8 bytes already consumed or
        # the slice reads into the next packet of a stream.
        data_field_len = primary.packet_data_length + 1
        user_len = data_field_len - (8 if primary.secondary_header_flag else 0)
        user_data = data[offset:offset + user_len]

        return cls(
            primary_header=primary,
            secondary_header=secondary,
            user_data=user_data,
        )


class TelemetryFramer:
    """CCSDS telemetry framer."""

    def __init__(self, apid: int = 1):
        self.apid = apid
        self.sequence_count = 0

    def frame(self, data: bytes, timestamp: Optional[float] = None) -> bytes:
        """
        Frame user data into CCSDS packet.

        Args:
            data: User data
            timestamp: Optional timestamp (seconds)

        Returns:
            Complete CCSDS packet
        """
        # Create primary header
        primary = CCSDSPrimaryHeader(
            apid=self.apid,
            packet_sequence_count=self.sequence_count,
            packet_data_length=len(data) + 8 - 1,  # +8 for secondary header, -1 per spec
        )

        # Create secondary header with timestamp
        if timestamp is not None:
            time_sec = int(timestamp)
            time_subsec = int((timestamp - time_sec) * 1e9)  # nanoseconds
            secondary = CCSDSSecondaryHeader(
                time_seconds=time_sec,
                time_subseconds=time_subsec,
            )
        else:
            secondary = CCSDSSecondaryHeader()

        # Create packet
        packet = CCSDSPacket(
            primary_header=primary,
            secondary_header=secondary,
            user_data=data,
        )

        # Increment sequence count
        self.sequence_count = (self.sequence_count + 1) & 0x3FFF

        return packet.pack()


class TelemetryDeframer:
    """CCSDS telemetry deframer."""

    def deframe(self, packet_bytes: bytes) -> dict:
        """
        Deframe CCSDS packet.

        Args:
            packet_bytes: Raw packet bytes

        Returns:
            Dictionary with parsed fields
        """
        packet = CCSDSPacket.unpack(packet_bytes)

        result = {
            'apid': packet.primary_header.apid,
            'sequence_count': packet.primary_header.packet_sequence_count,
            'user_data': packet.user_data,
        }

        if packet.secondary_header is not None:
            timestamp = (
                packet.secondary_header.time_seconds +
                packet.secondary_header.time_subseconds / 1e9
            )
            result['timestamp'] = timestamp

        return result
