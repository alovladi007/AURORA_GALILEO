"""
WebSocket API Routes
====================

WebSocket endpoints for real-time data streaming. Clients can subscribe to
telemetry and gravity data topics with optional satellite filtering.

Protocol:
  Client → Server:
    {
      "action": "subscribe" | "unsubscribe",
      "topics": ["galileo.telemetry", "galileo.gravity"],
      "satellite_ids": ["SAT001", "SAT002"]  // optional filter
    }

  Server → Client:
    {
      "type": "data" | "subscription_confirmed" | "ping" | "error",
      "topic": "galileo.telemetry",
      "timestamp": "2024-01-15T12:00:00Z",
      "data": { ... }
    }
"""

import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional

from api.websocket_bridge import get_bridge, WebSocketClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/stream")
async def stream_endpoint(
    websocket: WebSocket,
    client_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time data streaming.

    Query Parameters:
      - client_id: Optional client identifier (auto-generated if not provided)

    The client should send subscription messages to specify which topics and
    satellites to receive updates for.
    """
    if not client_id:
        client_id = f"ws_{uuid.uuid4().hex[:8]}"

    bridge = get_bridge()
    client: Optional[WebSocketClient] = None

    try:
        # Connect the client
        client = await bridge.connect_client(websocket, client_id)

        # Send welcome message
        await client.send({
            "type": "connected",
            "client_id": client_id,
            "available_topics": ["galileo.telemetry", "galileo.gravity"],
            "message": "Send subscription message to start receiving data",
        })

        # Handle incoming messages
        while client.active:
            try:
                message = await websocket.receive_json()

                # Handle subscription management
                if message.get("action") in ["subscribe", "unsubscribe"]:
                    await bridge.handle_subscription(client, message)

                # Handle ping/pong
                elif message.get("type") == "ping":
                    await client.send({"type": "pong"})

                else:
                    await client.send({
                        "type": "error",
                        "message": f"Unknown message type: {message.get('type')}",
                    })

            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                await client.send({
                    "type": "error",
                    "message": str(e),
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        if client:
            await bridge.disconnect_client(client_id)


@router.websocket("/telemetry")
async def telemetry_stream(
    websocket: WebSocket,
    satellite_id: Optional[str] = Query(None),
):
    """
    Dedicated WebSocket endpoint for telemetry streaming.

    Automatically subscribes to galileo.telemetry topic with optional
    satellite filtering.
    """
    client_id = f"telem_{uuid.uuid4().hex[:8]}"
    bridge = get_bridge()
    client: Optional[WebSocketClient] = None

    try:
        client = await bridge.connect_client(websocket, client_id)

        # Auto-subscribe to telemetry
        subscription = {
            "action": "subscribe",
            "topics": ["galileo.telemetry"],
        }
        if satellite_id:
            subscription["satellite_ids"] = [satellite_id]

        await bridge.handle_subscription(client, subscription)

        # Keep connection alive
        while client.active:
            try:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await client.send({"type": "pong"})
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info(f"Telemetry stream disconnected: {client_id}")
    finally:
        if client:
            await bridge.disconnect_client(client_id)


@router.websocket("/gravity")
async def gravity_stream(
    websocket: WebSocket,
    satellite_id: Optional[str] = Query(None),
):
    """
    Dedicated WebSocket endpoint for gravity data streaming.

    Automatically subscribes to galileo.gravity topic with optional
    satellite filtering.
    """
    client_id = f"grav_{uuid.uuid4().hex[:8]}"
    bridge = get_bridge()
    client: Optional[WebSocketClient] = None

    try:
        client = await bridge.connect_client(websocket, client_id)

        # Auto-subscribe to gravity
        subscription = {
            "action": "subscribe",
            "topics": ["galileo.gravity"],
        }
        if satellite_id:
            subscription["satellite_ids"] = [satellite_id]

        await bridge.handle_subscription(client, subscription)

        # Keep connection alive
        while client.active:
            try:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await client.send({"type": "pong"})
            except Exception:
                break

    except WebSocketDisconnect:
        logger.info(f"Gravity stream disconnected: {client_id}")
    finally:
        if client:
            await bridge.disconnect_client(client_id)
