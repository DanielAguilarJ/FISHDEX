import asyncio
import json
import logging
from typing import Set

logger = logging.getLogger(__name__)

class EventBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance.listeners = set()
        return cls._instance

    def register(self, queue: asyncio.Queue):
        self.listeners.add(queue)
        logger.debug(f"Registered event listener. Total: {len(self.listeners)}")

    def unregister(self, queue: asyncio.Queue):
        if queue in self.listeners:
            self.listeners.remove(queue)
            logger.debug(f"Unregistered event listener. Total: {len(self.listeners)}")

    async def emit(self, event_type: str, payload: dict):
        event = {
            "type": event_type,
            **payload
        }
        event_str = json.dumps(event)
        
        # Broadcast to all listeners
        inactive = []
        for queue in self.listeners:
            try:
                queue.put_nowait(event_str)
            except asyncio.QueueFull:
                logger.warning("Listener queue full, dropping event")
            except Exception as e:
                logger.error(f"Error sending event to listener: {e}")
                inactive.append(queue)
                
        for q in inactive:
            self.unregister(q)

event_bus = EventBus()

class EventBusLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            payload = {
                "level": record.levelname,
                "message": log_entry,
                "logger": record.name
            }
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(event_bus.emit("log", payload))
                )
            except RuntimeError:
                pass
        except Exception:
            self.handleError(record)
