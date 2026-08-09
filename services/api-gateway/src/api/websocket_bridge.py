"""
WebSocket Bridge for Real-Time Data Streaming
==============================================

Bridges Kafka topics to WebSocket clients for live telemetry and gravity data
streams. Supports subscription filtering, backpressure control, and graceful
degradation when Kafka is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict

logger = logging.getLogger(__name__)

# Try to import Kafka, fall back to in-process streaming if unavailable
try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    _HAS_KAFKA = True
except ImportError:
    _HAS_KAFKA = False
    logger.info("kafka-python not available; WebSocket bridge limited to in-process streams")


class WebSocketClient:
    """Represents a connected WebSocket client with subscription state."""

    def __init__(self, websocket: WebSocket, client_id: str):
        self.websocket = websocket
        self.client_id = client_id
        self.subscriptions: Set[str] = set()
        self.satellite_filters: Set[str] = set()
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.active = True

    async def send(self, message: Dict[str, Any]):
        """Send message to client with backpressure handling."""
        if not self.active:
            return

        try:
            # Non-blocking put; drop if queue full (backpressure)
            self.message_queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(f"Client {self.client_id} queue full, dropping message")

    async def send_loop(self):
        """Consume queue and send messages to WebSocket."""
        while self.active:
            try:
                message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=30.0
                )
                await self.websocket.send_json(message)
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await self.websocket.send_json({"type": "ping"})
                except Exception:
                    self.active = False
                    break
            except Exception as e:
                logger.error(f"Error sending to client {self.client_id}: {e}")
                self.active = False
                break

    def matches_filter(self, satellite_id: str) -> bool:
        """Check if message matches client's satellite filters."""
        if not self.satellite_filters:
            return True  # No filter = all satellites
        return satellite_id in self.satellite_filters


class WebSocketBridge:
    """Bridges Kafka topics to WebSocket clients."""

    def __init__(self, kafka_bootstrap_servers: str = "localhost:9092"):
        self.kafka_servers = kafka_bootstrap_servers
        self.clients: Dict[str, WebSocketClient] = {}
        self.topic_consumers: Dict[str, Any] = {}
        self.running = False
        self._in_process_queues: Dict[str, asyncio.Queue] = {
            "galileo.telemetry": asyncio.Queue(),
            "galileo.gravity": asyncio.Queue(),
        }

    async def start(self):
        """Start Kafka consumers and broadcast tasks."""
        if self.running:
            return

        self.running = True
        logger.info("Starting WebSocket bridge")

        if _HAS_KAFKA:
            # Start Kafka consumer tasks
            asyncio.create_task(self._consume_kafka("galileo.telemetry"))
            asyncio.create_task(self._consume_kafka("galileo.gravity"))
        else:
            # Start in-process consumer tasks
            asyncio.create_task(self._consume_in_process("galileo.telemetry"))
            asyncio.create_task(self._consume_in_process("galileo.gravity"))

    async def stop(self):
        """Stop all consumers."""
        self.running = False
        for consumer in self.topic_consumers.values():
            consumer.close()
        logger.info("WebSocket bridge stopped")

    async def connect_client(self, websocket: WebSocket, client_id: str) -> WebSocketClient:
        """Accept and register a new WebSocket client."""
        await websocket.accept()
        client = WebSocketClient(websocket, client_id)
        self.clients[client_id] = client

        # Start send loop for this client
        asyncio.create_task(client.send_loop())

        logger.info(f"WebSocket client connected: {client_id}")
        return client

    async def disconnect_client(self, client_id: str):
        """Remove a disconnected client."""
        if client_id in self.clients:
            self.clients[client_id].active = False
            del self.clients[client_id]
            logger.info(f"WebSocket client disconnected: {client_id}")

    async def handle_subscription(self, client: WebSocketClient, message: Dict[str, Any]):
        """Handle subscription/unsubscription requests."""
        action = message.get("action")
        topics = message.get("topics", [])
        satellite_ids = message.get("satellite_ids", [])

        if action == "subscribe":
            client.subscriptions.update(topics)
            client.satellite_filters.update(satellite_ids)
            await client.send({
                "type": "subscription_confirmed",
                "topics": list(client.subscriptions),
                "satellite_ids": list(client.satellite_filters),
            })
            logger.info(f"Client {client.client_id} subscribed to {topics}")

        elif action == "unsubscribe":
            client.subscriptions.difference_update(topics)
            client.satellite_filters.difference_update(satellite_ids)
            await client.send({
                "type": "subscription_confirmed",
                "topics": list(client.subscriptions),
                "satellite_ids": list(client.satellite_filters),
            })

    async def _consume_kafka(self, topic: str):
        """Consume from Kafka topic and broadcast to subscribed clients."""
        try:
            # kafka-python is a SYNCHRONOUS client: both the constructor
            # (which blocks while bootstrapping) and poll() must run in a
            # worker thread, or they block the entire event loop and the
            # application never finishes startup.
            def _make_consumer():
                return KafkaConsumer(
                    topic,
                    bootstrap_servers=self.kafka_servers,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    enable_auto_commit=True,
                    group_id=f'websocket_bridge_{topic}',
                )

            consumer = await asyncio.to_thread(_make_consumer)
            self.topic_consumers[topic] = consumer
            logger.info(f"Kafka consumer started for topic: {topic}")

            while self.running:
                # Blocking poll in a worker thread
                msg_pack = await asyncio.to_thread(
                    consumer.poll, timeout_ms=1000
                )
                for tp, messages in msg_pack.items():
                    for message in messages:
                        await self._broadcast(topic, message.value)

        except KafkaError as e:
            logger.error(f"Kafka error on topic {topic}: {e}")
        except Exception as e:
            logger.error(f"Error consuming topic {topic}: {e}")

    async def _consume_in_process(self, topic: str):
        """Consume from in-process queue (fallback when Kafka unavailable)."""
        queue = self._in_process_queues[topic]
        logger.info(f"In-process consumer started for topic: {topic}")

        while self.running:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                await self._broadcast(topic, message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error consuming in-process topic {topic}: {e}")

    async def _broadcast(self, topic: str, data: Dict[str, Any]):
        """Broadcast message to all subscribed clients."""
        satellite_id = data.get("satellite_id", "")

        for client in list(self.clients.values()):
            if topic in client.subscriptions:
                if client.matches_filter(satellite_id):
                    await client.send({
                        "type": "data",
                        "topic": topic,
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": data,
                    })

    async def publish_in_process(self, topic: str, data: Dict[str, Any]):
        """Publish to in-process queue (used when Kafka unavailable)."""
        if topic in self._in_process_queues:
            try:
                self._in_process_queues[topic].put_nowait(data)
            except asyncio.QueueFull:
                logger.warning(f"In-process queue full for topic {topic}")


# Global bridge instance
_bridge: Optional[WebSocketBridge] = None


def get_bridge() -> WebSocketBridge:
    """Get or create the global WebSocket bridge instance."""
    global _bridge
    if _bridge is None:
        import os
        kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        _bridge = WebSocketBridge(kafka_servers)
    return _bridge
