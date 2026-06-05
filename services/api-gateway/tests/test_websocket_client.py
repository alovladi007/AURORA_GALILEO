"""
WebSocket Client Test
=====================

Test client for verifying real-time WebSocket streaming functionality.
"""

import asyncio
import json
import websockets
from datetime import datetime


async def test_stream_endpoint():
    """Test the main /ws/stream endpoint with subscriptions."""
    uri = "ws://localhost:8000/ws/stream"

    async with websockets.connect(uri) as websocket:
        # Receive welcome message
        welcome = await websocket.recv()
        print(f"Connected: {json.loads(welcome)}")

        # Subscribe to telemetry and gravity topics
        subscription = {
            "action": "subscribe",
            "topics": ["galileo.telemetry", "galileo.gravity"],
            "satellite_ids": ["SAT001", "SAT002"],
        }
        await websocket.send(json.dumps(subscription))

        # Wait for subscription confirmation
        confirmation = await websocket.recv()
        print(f"Subscription: {json.loads(confirmation)}")

        # Receive messages for 30 seconds
        print("\nListening for messages (30 seconds)...")
        try:
            async with asyncio.timeout(30):
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if data["type"] == "data":
                        print(f"\n[{data['timestamp']}] {data['topic']}")
                        print(f"  Satellite: {data['data'].get('satellite_id')}")
                        if data['topic'] == "galileo.telemetry":
                            print(f"  Location: {data['data'].get('location')}")
                            print(f"  Battery: {data['data'].get('battery_level')}%")
                        elif data['topic'] == "galileo.gravity":
                            print(f"  Gravity: {data['data'].get('gravity_value')} mGal")
                            print(f"  Quality: {data['data'].get('quality_flag')}")

                    elif data["type"] == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))

        except asyncio.TimeoutError:
            print("\nTest complete")


async def test_telemetry_endpoint():
    """Test the dedicated /ws/telemetry endpoint."""
    uri = "ws://localhost:8000/ws/telemetry?satellite_id=SAT001"

    async with websockets.connect(uri) as websocket:
        print("Connected to telemetry stream (SAT001 only)")

        try:
            async with asyncio.timeout(15):
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if data["type"] == "data":
                        telem = data["data"]
                        print(f"[{telem['timestamp']}] SAT001 - "
                              f"Lat: {telem['location']['latitude']:.2f}, "
                              f"Lon: {telem['location']['longitude']:.2f}, "
                              f"Alt: {telem['location']['altitude']:.0f} m, "
                              f"Battery: {telem['battery_level']:.1f}%")

        except asyncio.TimeoutError:
            print("\nTest complete")


async def test_gravity_endpoint():
    """Test the dedicated /ws/gravity endpoint."""
    uri = "ws://localhost:8000/ws/gravity"

    async with websockets.connect(uri) as websocket:
        print("Connected to gravity stream (all satellites)")

        try:
            async with asyncio.timeout(15):
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if data["type"] == "data":
                        grav = data["data"]
                        print(f"[{grav['timestamp']}] {grav['satellite_id']} - "
                              f"Gravity: {grav['gravity_value']:.2f} mGal, "
                              f"Uncertainty: {grav['uncertainty']:.3f}, "
                              f"Quality: {grav['quality_flag']}")

        except asyncio.TimeoutError:
            print("\nTest complete")


async def main():
    """Run all WebSocket tests."""
    print("=" * 70)
    print("WebSocket Stream Tests")
    print("=" * 70)

    print("\n\nTest 1: Main stream endpoint with subscription")
    print("-" * 70)
    try:
        await test_stream_endpoint()
    except Exception as e:
        print(f"Error: {e}")

    print("\n\nTest 2: Dedicated telemetry endpoint")
    print("-" * 70)
    try:
        await test_telemetry_endpoint()
    except Exception as e:
        print(f"Error: {e}")

    print("\n\nTest 3: Dedicated gravity endpoint")
    print("-" * 70)
    try:
        await test_gravity_endpoint()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
