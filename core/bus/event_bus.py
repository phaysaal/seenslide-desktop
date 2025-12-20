"""Event bus for publish-subscribe communication between modules."""

import logging
from typing import Callable, Dict, List
from core.interfaces.events import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """Singleton event bus for pub/sub communication.

    The event bus allows modules to communicate without direct dependencies.
    Modules subscribe to event types they're interested in, and publish
    events when something happens.

    Example:
        bus = EventBus()
        bus.subscribe(EventType.SLIDE_CAPTURED, my_handler)
        bus.publish(Event(EventType.SLIDE_CAPTURED, data={"slide_id": "123"}))
    """

    _instance = None

    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the event bus."""
        if self._initialized:
            return

        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000  # Keep last 1000 events
        self._initialized = True

        logger.info("EventBus initialized")

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to an event type.

        Args:
            event_type: Type of event to subscribe to
            handler: Function to call when event is published.
                     Should accept Event as parameter.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"Subscribed handler to {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Unsubscribe a handler from an event type.

        Args:
            event_type: Type of event to unsubscribe from
            handler: Handler function to remove
        """
        if event_type in self._subscribers:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
                logger.debug(f"Unsubscribed handler from {event_type.value}")

    def publish(self, event: Event) -> None:
        """Publish an event to all subscribers.

        Args:
            event: Event to publish
        """
        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        logger.debug(f"Publishing event: {event.type.value} from {event.source}")

        # Call all subscribers
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(
                        f"Error in event handler for {event.type.value}: {e}",
                        exc_info=True
                    )

    def get_history(self, event_type: EventType = None, limit: int = 100) -> List[Event]:
        """Get recent event history.

        Args:
            event_type: Filter by event type (None = all events)
            limit: Maximum number of events to return

        Returns:
            List of events, most recent first
        """
        events = self._event_history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return list(reversed(events[-limit:]))

    def clear_history(self) -> None:
        """Clear event history."""
        self._event_history.clear()
        logger.debug("Event history cleared")

    def subscriber_count(self, event_type: EventType) -> int:
        """Get number of subscribers for an event type.

        Args:
            event_type: Event type to check

        Returns:
            Number of subscribers
        """
        return len(self._subscribers.get(event_type, []))
