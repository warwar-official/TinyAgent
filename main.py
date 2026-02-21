from imports.loop_manager import LoopManager
from prompt_toolkit import PromptSession
import dotenv
import json

dotenv.load_dotenv()

CONFIG_PATH = "config.json"

def load_config(path: str) -> dict | None:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except IOError as e:
        print(f"Unable to read config! Error: {e}")
    except json.JSONDecodeError as e:
        print(f"Unable to decode config! Error: {e}")
    return None

def main():
    config = load_config(CONFIG_PATH)
    input_session = PromptSession()

    if config:
        loop_manager = LoopManager(config)
        while True:
            user_input = input_session.prompt("Enter your message: ")
            if user_input == "/bye":
                break
            loop_manager.perform_loop(user_input)

if __name__ == "__main__":
    main()
