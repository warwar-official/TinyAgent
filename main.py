from imports.models.generative.gemini import GeminiModel
from imports.models.embeddings.lm_studio import LMStudioEmbeddingModel
from imports.loop_manager import LoopManager
from imports.context_manager import ContextManager

from imports.plugins.memory_RAG import MemoryRAG

import os
import dotenv
import json
import importlib

dotenv.load_dotenv()

sys_prompt = """
Before you perform any actions, read the "identity.md" file. It contains important information about your role and tasks.

If question or task not simple, you can use think-mode. For this before the answer make block tagged <think></think>.
Inside this block follow next steps:
1. Describe what user ask you to do.
2. Describe what you know about this task.
3. Describe what you need to solve this task.
4. Make draft of plan to solve this task.
After this make answer to user.


You can use tools by writing json signature: {"toolcall": {"name":"tool_name", "arguments": []}}
If you call tool, you will initialize tool loop. So ask questions and make sure you have all information before calling tool.

Available tools:

"""

def load_config() -> dict:
    with open("config.json", "r") as f:
        return json.load(f)

def load_tools(config: dict) -> dict:
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
    return prompt

def main():
    model = GeminiModel("gemma-3-27b-it", os.getenv("GEMINI_API_KEY"))
    emb_model = LMStudioEmbeddingModel()
    memory = MemoryRAG("agent_data_system/memory/", emb_model.make_request)
    config = load_config()
    tool_table = load_tools(config)
    system_prompt = sys_prompt + make_tool_prompt(config)
    context_manager = ContextManager(system_prompt, memory)
    loop_manager = LoopManager(model, context_manager, tool_table)

    while True:
        user_input = input("Enter your message: ")
        if user_input == "/bye":
            break
        loop_manager.perform_loop(user_input)

if __name__ == "__main__":
    main()
