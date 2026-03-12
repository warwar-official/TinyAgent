from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentRequest:
    """Message sent from a frontend to the backend processing loop."""
    frontend_type: str   # e.g., "console", "telegram"
    chat_id: str         # The unique dialog ID
    action: str          # e.g., "message", "init", "own_task", "identity_rethink"
    text: str = ""       # The text payload
    image_hash: Optional[str] = None # The hashed image filename if present

@dataclass
class AgentResponse:
    """Message sent from the backend to a specific frontend chat."""
    frontend_type: str   # e.g., "console", "telegram"
    chat_id: str         # The unique dialog ID
    type: str            # e.g., "final_response", "status_update", "error"
    text: str            # The text content to display
