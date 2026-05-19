"""In-memory SSE broadcaster for real-time dispute progress streaming."""

import asyncio
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class SSEManager:
    """
    Manages per-dispute asyncio queues for Server-Sent Events.

    Multiple subscribers per dispute are supported — each gets its own queue.
    publish() is safe to call with zero subscribers.
    """

    def __init__(self) -> None:
        # dispute_id → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def subscribe(self, dispute_id: str) -> asyncio.Queue:
        """Register a new subscriber queue for a dispute and return it."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[dispute_id].append(queue)
        logger.debug("SSE subscribe: dispute=%s total=%d", dispute_id, len(self._subscribers[dispute_id]))
        return queue

    async def unsubscribe(self, dispute_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue. Safe to call even if already removed."""
        queues = self._subscribers.get(dispute_id, [])
        try:
            queues.remove(queue)
        except ValueError:
            pass
        if not queues:
            self._subscribers.pop(dispute_id, None)
        logger.debug("SSE unsubscribe: dispute=%s remaining=%d", dispute_id, len(queues))

    async def publish(self, dispute_id: str, event_type: str, data: dict) -> None:
        """
        Push an event to all subscribers for a dispute.
        No-op if there are no subscribers.
        """
        queues = self._subscribers.get(dispute_id, [])
        if not queues:
            return
        message = {"event": event_type, "data": data}
        for queue in list(queues):  # snapshot to avoid mutation during iteration
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for dispute=%s, dropping event=%s", dispute_id, event_type)

    def format_event(self, event_type: str, data: dict) -> str:
        """Format a dict as a strict SSE frame: event + data + double newline."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# Singleton used across the application
sse_manager = SSEManager()
