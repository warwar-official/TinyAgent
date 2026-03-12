import logging
from imports.messaging.queue_manager import MessageBus

def frontend_listener_loop(bus: MessageBus) -> None:
    """
    Background thread that continually reads from backend_to_frontend queue
    and dispatches to the registered frontend listeners.
    """
    while True:
        try:
            response = bus.backend_to_frontend.get()
            bus.dispatch_to_frontend(response)
        except Exception as e:
            logging.error(f"Error in frontend listener loop: {e}")
