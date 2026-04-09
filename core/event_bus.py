import queue
import threading

class EventBus:
    def __init__(self):
        self._queue = queue.Queue()
        self._lock = threading.Lock()

    def publish(self, event_type: str, data: dict = {}):
        self._queue.put({"type": event_type, "data": data})

    def subscribe(self, timeout: float = None):
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

bus = EventBus()