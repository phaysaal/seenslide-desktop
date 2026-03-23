"""WebSocket API for real-time updates."""

import logging
import json
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from core.interfaces.events import Event, EventType
from modules.web.dependencies import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients.

        Args:
            message: Message dictionary to broadcast
        """
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global connection manager
manager = ConnectionManager()


def event_to_dict(event: Event) -> dict:
    """Convert an Event to a dictionary for JSON serialization.

    Args:
        event: Event object

    Returns:
        Dictionary representation of event
    """
    return {
        "type": event.type.value if isinstance(event.type, EventType) else str(event.type),
        "data": event.data,
        "source": event.source,
        "timestamp": event.timestamp
    }


async def broadcast_event(event: Event):
    """Broadcast an event to all WebSocket clients.

    Args:
        event: Event to broadcast
    """
    message = event_to_dict(event)
    await manager.broadcast(message)


@router.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event updates.

    Args:
        websocket: WebSocket connection

    Subscribes to event bus and forwards events to connected clients.
    """
    await manager.connect(websocket)

    try:
        # Keep connection alive and listen for client messages
        while True:
            # Wait for messages from client (e.g., ping/pong)
            data = await websocket.receive_text()

            # Echo back or handle client messages
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


def setup_event_broadcasting(event_bus):
    """Set up event bus to broadcast events to WebSocket clients.

    Args:
        event_bus: Event bus instance to subscribe to
    """
    # Subscribe to all event types for broadcasting
    event_types = [
        EventType.SESSION_CREATED,
        EventType.SESSION_STARTED,
        EventType.SESSION_STOPPED,
        EventType.SLIDE_CAPTURED,
        EventType.SLIDE_UNIQUE,
        EventType.SLIDE_DUPLICATE,
        EventType.SLIDE_STORED,
        EventType.CAPTURE_ERROR,
        EventType.DEDUP_ERROR,
        EventType.STORAGE_ERROR,
    ]

    for event_type in event_types:
        event_bus.subscribe(event_type, broadcast_event)

    logger.info("Event broadcasting set up for WebSocket")
