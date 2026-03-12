import queue
from typing import Callable
from imports.messaging.message_models import AgentRequest, AgentResponse

class MessageBus:
    """Manages the asynchronous queues between frontends and the backend."""
    def __init__(self):
        self.frontend_to_backend: queue.Queue[AgentRequest] = queue.Queue()
        self.backend_to_frontend: queue.Queue[AgentResponse] = queue.Queue()
        
        # Registry of callback functions to handle frontend routing
        # mapping frontend_type -> callback(AgentResponse)
        self._frontend_listeners: dict[str, Callable[[AgentResponse], None]] = {}

    def send_to_backend(self, request: AgentRequest) -> None:
        """Called by a frontend when user sends input."""
        self.frontend_to_backend.put(request)
        
    def send_to_frontend(self, response: AgentResponse) -> None:
        """Called by the backend to send data to the user."""
        self.backend_to_frontend.put(response)

    def register_frontend(self, frontend_type: str, callback: Callable[[AgentResponse], None]) -> None:
        """Register a callback for a specific frontend."""
        self._frontend_listeners[frontend_type] = callback
        
    def dispatch_to_frontend(self, response: AgentResponse) -> None:
        """Route the response to the correct frontend listener."""
        listener = self._frontend_listeners.get(response.frontend_type)
        if listener:
            listener(response)
        else:
            print(f"Warning: No listener registered for frontend type '{response.frontend_type}'. Dropping message.")
