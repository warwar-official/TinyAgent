from imports.models.gemini import GeminiModel
from imports.tools.get_current_weather import get_current_weather
from imports.loop_manager import LoopManager
import os
import dotenv
import json
import importlib

dotenv.load_dotenv()

sys_prompt = """
Instructions:

You are helpful assistant.
Give answer in Ukrainian.
You can tools by writing json signature: {"toolcall": {"name":"tool_name", "arguments": []}}

Avaible tools:

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
    config = load_config()
    tool_table = load_tools(config)
    system_prompt = sys_prompt + make_tool_prompt(config)
    loop_manager = LoopManager()
    loop_manager.set_model(model)
    loop_manager.set_system_prompt(system_prompt)
    loop_manager.set_tool_table(tool_table)
    loop_manager.perform_loop("Hi, help me. Find the information about Ukrainian athlete that was disqualified. And send me this information as a message.")

if __name__ == "__main__":
    main()
