import dotenv
dotenv.load_dotenv()

from imports.loop_manager import LoopManager, AgentMessage
from imports.image_manager import ImageManager
from prompt_toolkit import PromptSession
from imports.plugins.telegram import bot_responce, bot_process, stop_bot, TelegramBotMessage
from threading import Thread
import json
import queue
import time

CONFIG_PATH = "config.json"
USE_TELEGRAM_FRONTEND = True
AUTONOMOUS_LOOP_INTERVAL = 0

def load_config(path: str) -> dict | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except IOError as e:
        print(f"Unable to read config! Error: {e}")
    except json.JSONDecodeError as e:
        print(f"Unable to decode config! Error: {e}")
    return None

def concole_input_loop(request_queue: queue.Queue):
    input_session = PromptSession()
    while True:
        user_input = input_session.prompt("Enter your message: ")
        if user_input == "/bye":
            break
        request_queue.put(TelegramBotMessage("message", user_input, "console"))

def autonomous_loop(request_queue: queue.Queue):
    if AUTONOMOUS_LOOP_INTERVAL > 0:
        while True:
            request_queue.put(TelegramBotMessage("action", "autonomous_loop", "console"))
            time.sleep(AUTONOMOUS_LOOP_INTERVAL)

def main():
    config = load_config(CONFIG_PATH)
    request_queue = queue.Queue()
    image_manager = ImageManager()

    if config:
        if USE_TELEGRAM_FRONTEND:
            front_end_thread = Thread(target=bot_process, args=(request_queue, config["plugins"]["telegram"]["secret_path"]), daemon=True)
            front_end_thread.start()
        else:
            front_end_thread = Thread(target=concole_input_loop, args=(request_queue,), daemon=True)
            front_end_thread.start()

        autonomous_thread = Thread(target=autonomous_loop, args=(request_queue,), daemon=True)
        autonomous_thread.start()

        loop_manager = LoopManager(config, image_manager)
        
        while True:
            try:
                message = request_queue.get()
                if message.type == "message":
                    # Process image if present
                    image_hash = None
                    if hasattr(message, 'image_url') and message.image_url:
                        try:
                            image_hash = image_manager.save_image_from_url(message.image_url)
                        except Exception as e:
                            print(f"Failed to download image: {e}")
                    
                    agent_message = AgentMessage(
                        text=message.message or "",
                        image_hash=image_hash,
                    )
                    answer = loop_manager.router(agent_message)
                    if message.chat_id == "console":
                        print(f"model: {answer}")
                    else:
                        bot_responce(answer, message.chat_id)
                elif message.type == "report":
                    print(message.message)
                elif message.type == "action":
                    if message.message == "init":
                        answer = loop_manager.init_agent()
                        bot_responce(answer, message.chat_id)
                    elif message.message == "own_task":
                        answer = loop_manager.own_task()
                        bot_responce(answer, message.chat_id)
                    elif message.message == "identity_rethink":
                        answer = loop_manager.identity_rethink()
                        bot_responce(answer, message.chat_id)
                else:
                    print(f"Unknown message type: {message.type}")
            except KeyboardInterrupt:
                if USE_TELEGRAM_FRONTEND:
                    print("\nStopping Telegram bot...")
                    stop_bot()
                else:
                    print("\nShutting down console loop...")
                break

if __name__ == "__main__":
    main()
