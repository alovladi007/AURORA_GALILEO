"""
WebSocket Server for Real-Time Optical Bench Data Streaming
"""

import asyncio
import json
import logging
from typing import Set
from datetime import datetime
import websockets
from websockets.server import WebSocketServerProtocol

from optical_bench import OpticalBenchEmulator, BenchParameters, NoiseProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmulatorServer:
    """WebSocket server for streaming emulator data"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.emulator = OpticalBenchEmulator()
        self.clients: Set[WebSocketServerProtocol] = set()
        self.running = False
        self.update_rate = 50  # Hz (20ms updates)
        
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new client connection"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
        
        # Send initial state
        await websocket.send(json.dumps({
            "type": "connection",
            "status": "connected",
            "message": "Connected to Optical Bench Emulator",
            "server_time": datetime.now().isoformat()
        }))
    
    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """Unregister a client connection"""
        self.clients.discard(websocket)
        logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
    
    async def broadcast_state(self):
        """Broadcast current emulator state to all connected clients"""
        if not self.clients:
            return
        
        state = self.emulator.get_full_state()
        message = json.dumps({
            "type": "state_update",
            "data": state
        })
        
        # Send to all clients, remove dead connections
        dead_clients = set()
        for client in self.clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                dead_clients.add(client)
        
        # Clean up dead connections
        self.clients -= dead_clients
    
    async def broadcast_diagnostics(self):
        """Broadcast system diagnostics"""
        if not self.clients:
            return
        
        diagnostics = self.emulator.get_diagnostics()
        message = json.dumps({
            "type": "diagnostics",
            "data": diagnostics
        })
        
        for client in self.clients.copy():
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                self.clients.discard(client)
    
    async def broadcast_event(self, event_type: str, data: dict):
        """Broadcast a special event to all clients"""
        message = json.dumps({
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        for client in self.clients.copy():
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                self.clients.discard(client)
    
    async def handle_client_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming messages from clients"""
        try:
            data = json.loads(message)
            command = data.get("command")
            
            if command == "inject_event":
                event_type = data.get("event_type", "vibration_spike")
                magnitude = data.get("magnitude", 1.0)
                self.emulator.inject_event(event_type, magnitude)
                await self.broadcast_event("event_injected", {
                    "event_type": event_type,
                    "magnitude": magnitude
                })
                logger.info(f"Injected event: {event_type} (magnitude: {magnitude})")
            
            elif command == "reset":
                self.emulator.reset()
                await self.broadcast_event("system_reset", {})
                logger.info("Emulator reset")
            
            elif command == "set_update_rate":
                rate = data.get("rate", 50)
                self.update_rate = max(1, min(1000, rate))  # Clamp 1-1000 Hz
                logger.info(f"Update rate set to {self.update_rate} Hz")
            
            elif command == "set_parameters":
                params = data.get("parameters", {})
                if "baseline_length" in params:
                    self.emulator.params.baseline_length = params["baseline_length"]
                if "temperature" in params:
                    self.emulator.params.temperature = params["temperature"]
                if "vibration_amplitude" in params:
                    self.emulator.noise.vibration_amplitude = params["vibration_amplitude"]
                logger.info(f"Parameters updated: {params}")
            
            elif command == "get_diagnostics":
                await self.broadcast_diagnostics()
            
            else:
                logger.warning(f"Unknown command: {command}")
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON received from client")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
    
    async def client_handler(self, websocket: WebSocketServerProtocol,
                             path: str = "/"):
        # websockets >= 11 invokes handlers with (websocket) only; the
        # legacy two-argument form is kept via a default for older
        # versions.
        """Handle individual client connections"""
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                await self.handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)
    
    async def data_stream_loop(self):
        """Main loop for streaming data to clients"""
        logger.info("Data streaming loop started")
        diagnostics_counter = 0
        
        while self.running:
            # Broadcast state update
            await self.broadcast_state()
            
            # Send diagnostics every 2 seconds
            diagnostics_counter += 1
            if diagnostics_counter >= (self.update_rate * 2):
                await self.broadcast_diagnostics()
                diagnostics_counter = 0
            
            # Wait for next update
            await asyncio.sleep(1.0 / self.update_rate)
    
    async def start(self):
        """Start the WebSocket server"""
        self.running = True
        
        # Start the WebSocket server
        async with websockets.serve(self.client_handler, self.host, self.port):
            logger.info(f"Emulator server started on ws://{self.host}:{self.port}")
            logger.info(f"Update rate: {self.update_rate} Hz")
            
            # Start data streaming
            await self.data_stream_loop()
    
    def stop(self):
        """Stop the server"""
        self.running = False
        logger.info("Server stopped")


async def main():
    """Main entry point"""
    server = EmulatorServer(host="localhost", port=8765)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.stop()


if __name__ == "__main__":
    print("=" * 60)
    print("Optical Bench Emulator - WebSocket Server")
    print("=" * 60)
    print(f"Starting server on ws://localhost:8765")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    asyncio.run(main())
