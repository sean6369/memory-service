"""
EventBus interface + in-process implementation.

This is the MVP substitute for Apache Kafka. The publisher/subscriber seam is real
so Kafka can drop in later by implementing the EventBus protocol.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Callable


class EventBus(ABC):
    """Abstract event bus interface — Kafka-ready seam."""

    @abstractmethod
    def publish(self, topic: str, event: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        ...


class InProcessEventBus(EventBus):
    """In-process event bus for the MVP. Dispatches events synchronously."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        for handler in self._subscribers.get(topic, []):
            handler(event)

    def subscribe(self, topic: str, handler: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers[topic].append(handler)


# Singleton for the application
event_bus = InProcessEventBus()
