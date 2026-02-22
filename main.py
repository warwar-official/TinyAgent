import dotenv
dotenv.load_dotenv()

from imports.loop_manager import LoopManager
from prompt_toolkit import PromptSession
from imports.plugins.telegram import bot_responce, bot_process, stop_bot, TelegramBotMessage
from threading import Thread
import json
import queue


CONFIG_PATH = "config.json"
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

def concole_input_loop(request_queue: queue.Queue):
    input_session = PromptSession()
    while True:
        user_input = input_session.prompt("Enter your message: ")
        if user_input == "/bye":
            break
        request_queue.put(TelegramBotMessage("message", user_input, "console"))

def main():
    config = load_config(CONFIG_PATH)
    request_queue = queue.Queue()

    if config:
        loop_manager = LoopManager(config)
        if USE_TELEGRAM_FRONTEND:
            front_end_thread = Thread(target=bot_process, args=(request_queue, config["plugins"]["telegram"]["secret_path"]), daemon=True)
            front_end_thread.start()
        else:
            front_end_thread = Thread(target=concole_input_loop, args=(request_queue,), daemon=True)
            front_end_thread.start()
        while True:
            try:
                message = request_queue.get()
                if message.type == "message":
                    answer = loop_manager.perform_loop(message.message)
                    if message.chat_id == "console":
                        print(f"model: {answer}")
                    else:
                        bot_responce(answer, message.chat_id)
                elif message.type == "report":
                    print(message.message)
            except KeyboardInterrupt:
                if USE_TELEGRAM_FRONTEND:
                    print("\nStopping Telegram bot...")
                    stop_bot()
                else:
                    print("\nShutting down console loop...")
                
                # Daemon thread will gracefully die with the main thread
                break

if __name__ == "__main__":
    main()
