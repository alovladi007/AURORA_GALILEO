"""
Kafka Streaming
===============

Publishes telemetry and gravity records to Kafka topics for real-time
consumers (the API Gateway WebSocket bridge, downstream analytics). Designed to
degrade gracefully: if ``kafka-python`` is missing or the broker is
unreachable, publishing becomes a no-op and the in-process pub/sub fallback is
used for gRPC streaming.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from datetime import datetime
from typing import Dict, Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from kafka import KafkaProducer  # type: ignore

    _HAS_KAFKA = True
except Exception:  # noqa: BLE001
    _HAS_KAFKA = False

TOPIC_TELEMETRY = os.getenv("KAFKA_TOPIC_TELEMETRY", "galileo.telemetry")
TOPIC_GRAVITY = os.getenv("KAFKA_TOPIC_GRAVITY", "galileo.gravity")


class StreamBroker:
    """Hybrid Kafka producer + in-process fan-out for gRPC server streaming.

    Records ingested by the service are published here; gRPC ``Stream*`` RPCs
    subscribe to receive live records. Kafka publishing is best-effort.
    """

    def __init__(self):
        self._producer = self._init_kafka()
        self._subscribers: Dict[str, list] = {TOPIC_TELEMETRY: [], TOPIC_GRAVITY: []}
        self._lock = threading.Lock()

    def _init_kafka(self) -> Optional["KafkaProducer"]:
        if not _HAS_KAFKA:
            logger.info("kafka-python not installed; using in-process streaming only")
            return None
        brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        try:
            producer = KafkaProducer(
                bootstrap_servers=brokers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                retries=3,
                acks="all",
                linger_ms=10,
            )
            logger.info("Kafka producer connected to %s", brokers)
            return producer
        except Exception as exc:  # noqa: BLE001
            logger.warning("Kafka unavailable (%s); using in-process streaming", exc)
            return None

    # -- publish -----------------------------------------------------------
    def publish_telemetry(self, satellite_id: str, payload: Dict) -> None:
        self._publish(TOPIC_TELEMETRY, satellite_id, payload)

    def publish_gravity(self, satellite_id: str, payload: Dict) -> None:
        self._publish(TOPIC_GRAVITY, satellite_id, payload)

    def _publish(self, topic: str, key: str, payload: Dict) -> None:
        payload = {**payload, "_published_at": datetime.utcnow().isoformat()}
        if self._producer is not None:
            try:
                self._producer.send(topic, key=key, value=payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Kafka publish failed on %s: %s", topic, exc)
        # Always fan out to in-process subscribers.
        with self._lock:
            for q in list(self._subscribers.get(topic, [])):
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass

    # -- subscribe ---------------------------------------------------------
    def subscribe(self, topic: str, maxsize: int = 1000) -> "queue.Queue":
        q: "queue.Queue" = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.setdefault(topic, []).append(q)
        return q

    def unsubscribe(self, topic: str, q: "queue.Queue") -> None:
        with self._lock:
            subs = self._subscribers.get(topic, [])
            if q in subs:
                subs.remove(q)

    def stream(self, topic: str, stop_event: threading.Event,
               timeout: float = 1.0) -> Iterator[Dict]:
        """Yield live records from a topic until ``stop_event`` is set."""
        q = self.subscribe(topic)
        try:
            while not stop_event.is_set():
                try:
                    yield q.get(timeout=timeout)
                except queue.Empty:
                    continue
        finally:
            self.unsubscribe(topic, q)

    def close(self) -> None:
        if self._producer is not None:
            try:
                self._producer.flush()
                self._producer.close()
            except Exception:  # noqa: BLE001
                pass


# Global broker instance shared by the servicer.
broker = StreamBroker()
