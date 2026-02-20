"""from imports.models.generative.gemini import GeminiModel
from imports.models.embeddings.lm_studio import LMStudioEmbeddingModel
from imports.loop_manager import LoopManager
from imports.context_manager import ContextManager
from imports.task_manager import TaskManager

from imports.plugins.memory_RAG import MemoryRAG"""

from imports import context_manager
from imports.context_manager_new import ContextManager

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

"""def load_tools(config: dict) -> dict:
    tool_table = {}
    for tool in config["tools"]:
        tool_name = tool["name"]
        module = importlib.import_module(f"imports.tools.{tool_name}")
        tool_table[tool_name] = getattr(module, tool_name)
    return tool_table

def make_tool_prompt(config: dict) -> str:
    prompt = ""
    for tool in config["tools"]:
        prompt += f"\n{tool['name']}: {tool['description']}\nParameters: {tool['parameters']}\n"
    return prompt"""

def main():
    config = load_config(CONFIG_PATH)
    if config:
        try:
            context_manager = ContextManager(config["context"])
        except KeyError as e:
            print(f"Config uncorrect. Error: {e}")
        except ValueError as e:
            print(e)

"""def main():
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY:
        model = GeminiModel("gemma-3-27b-it", GEMINI_API_KEY)
    else:
        raise ValueError("EMINI_API_KEY not in .env")

    emb_model = LMStudioEmbeddingModel()
    memory = None #MemoryRAG("agent_data_system/memory/", emb_model.make_request)
    
    config = load_config()
    tool_table = load_tools(config)
    task_manager = TaskManager()
    tool_table["add_task"] = task_manager.add_task
    tool_table["finish_task"] = task_manager.finish_task

    system_prompt = sys_prompt + make_tool_prompt(config)
    context_manager = ContextManager(system_prompt, memory)
    loop_manager = LoopManager(model, context_manager, task_manager, tool_table)

    while True:
        user_input = input("Enter your message: ")
        if user_input == "/bye":
            break
        loop_manager.perform_loop(user_input)"""

if __name__ == "__main__":
    main()
    """emb_model = LMStudioEmbeddingModel()
    memory = MemoryRAG("agent_data_system/memory/", emb_model.make_request)
    print(memory.get_all_memories_json())"""
