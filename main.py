import dotenv
dotenv.load_dotenv()

from imports.image_manager import ImageManager
from imports.history_manager import HistoryManager
from prompt_toolkit import PromptSession
from imports.plugins.telegram import bot_process, stop_bot
from threading import Thread
import json
import time

from imports.messaging.queue_manager import MessageBus
from imports.messaging.message_models import AgentRequest, AgentResponse
from imports.messaging.frontend_listener import frontend_listener_loop
from imports.messaging.backend_worker import backend_worker_loop

# Pipeline engine imports
from imports.agent.pipeline.pipeline_engine import PipelineEngine
from imports.providers_manager import ProvidersManager, Model
from imports.mcp.connector import MCPConnector

CONFIG_PATH = "config/config.json"
USE_TELEGRAM_FRONTEND = True

def load_config(path: str) -> dict | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except IOError as e:
        print(f"Unable to read config! Error: {e}")
    except json.JSONDecodeError as e:
        print(f"Unable to decode config! Error: {e}")
    return None

def console_input_loop(bus: MessageBus) -> None:
    input_session = PromptSession()
    while True:
        user_input = input_session.prompt("Enter your message: ")
        if user_input == "/bye":
            break
        bus.send_to_backend(AgentRequest(
            frontend_type="console",
            chat_id="console",
            action="message",
            text=user_input
        ))

def main():
    config = load_config(CONFIG_PATH)
    if not config:
        return

    bus = MessageBus()
    image_manager = ImageManager()

    # Initialize components for PipelineEngine
    providers_manager = ProvidersManager(config.get("providers", {}))
    model = Model(**config.get("agent", {}).get("model", {}))
    
    # Init MCP connector
    mcp_config_path = config.get("context", {}).get("mcp_config_path", "./tools/mcp_config.json")
    try:
        with open(mcp_config_path, "r", encoding="utf-8") as f:
            mcp_config_data = json.load(f)
    except Exception as e:
        print(f"Failed to load MCP config {mcp_config_path}: {e}")
        mcp_config_data = {}
    mcp_connector = MCPConnector(config_data=mcp_config_data, app_config=config, image_manager=image_manager)
    
    pipeline_engine = PipelineEngine(
        providers_manager=providers_manager,
        model=model,
        config=config,
        image_manager=image_manager,
        mcp_connector=mcp_connector
    )

    # Handlers for dispatched messages
    def console_response_handler(response: AgentResponse) -> None:
        if response.type == "final_response":
            print(f"model: {response.text}")
            for img_hash in response.image_hashes:
                print(f"[Image: {img_hash}]")
        elif response.type == "status_update":
            print(f"[STATUS]: {response.text}")
        elif response.type == "error":
            print(f"[ERROR]: {response.text}")
        else:
            print(f"[{response.type.upper()}]: {response.text}")

    bus.register_frontend("console", console_response_handler)
    # Telegram registers itself in bot_process

    # Initialize HistoryManager
    # Here we can pass a specific path if configured, or default
    history_path = config.get("context", {}).get("history_path", "./data/history.json")
    history_manager = HistoryManager(history_path)

    # 1. Start generic queues processor
    frontend_listener_thread = Thread(target=frontend_listener_loop, args=(bus,), daemon=True)
    frontend_listener_thread.start()
    
    # 2. Start the Backend Processing loop
    backend_thread = Thread(target=backend_worker_loop, args=(bus, pipeline_engine, history_manager), daemon=True)
    backend_thread.start()

    # 3. Start Frontends
    if USE_TELEGRAM_FRONTEND:
        front_end_thread = Thread(target=bot_process, args=(bus, config["plugins"]["telegram"]["secret_path"]), daemon=True)
        front_end_thread.start()
    else:
        front_end_thread = Thread(target=console_input_loop, args=(bus,), daemon=True)
        front_end_thread.start()

    # Wait indefinitely until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if USE_TELEGRAM_FRONTEND:
            print("\nStopping Telegram bot...")
            stop_bot()
        else:
            print("\nShutting down console loop...")

if __name__ == "__main__":
    main()
