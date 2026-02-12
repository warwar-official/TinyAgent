from imports.models.gemini import GeminiModel
from imports.tools.get_current_temperature import get_current_temperature
import json
import os
import dotenv

dotenv.load_dotenv()

tool_table = {
    "get_current_temperature":get_current_temperature
}

sys_prompt = """
Instructions:

You are helpful assistant.
Give answer in Ukrainian.
You can tools by writing json signature: {"toolcall": {"name":"tool_name", "arguments": []}}

Avaible tools:

'name':'get_current_temperature',
'description':'Gets the current temperature for a given location.',
'parameters':
    {
        'properties': {
            'location':{
                'type':'string',
                'description':'The city name, e.g. Lviv'
            }
        },
        'required': ['location']
    }
"""

def history_to_payload(history: list[tuple[str, str]]) -> dict:
    payload = {
        'contents': [
        ]
    }
    for role, text in history:    
        payload['contents'].append({
            'role': role,
            'parts': [
                {
                    'text': text
                }
            ]
        })
    return payload

def perform_loop(model: GeminiModel, prompt: str):
    history: list[tuple[str, str]] = []
    history.append(("user", sys_prompt))
    history.append(("user", prompt))
    payload = history_to_payload(history)
    answer = model.make_request(payload)
    print(answer)
    history.append(("model", answer))
    tool = parse_toolcall(answer)
    res = tool_table[tool["name"]](**tool["arguments"])
    history.append(("user", f"Tool {tool['name']}, arguments: {tool['arguments']}, returned result: {res}"))
    payload = history_to_payload(history)
    answer = model.make_request(payload)
    history.append(("model", answer))
    return answer

def parse_toolcall(message: str) -> dict:
    toolcall = message[message.find("{"):message.rfind("}")+1]
    return json.loads(toolcall)

def main():
    model = GeminiModel("gemma-3-27b-it", os.getenv("GEMINI_API_KEY"))
    answer = perform_loop(model, "What the wether in Kyiv?")
    print(answer)

if __name__ == "__main__":
    main()

"""
,
        'tools': [
            {
                'functionDeclarations': [
                    {
                        'name':'get_current_temperature',
                        'description':'Gets the current temperature for a given location.',
                        'parameters':
                            {
                                'type':'object',
                                'properties': {
                                    'location':{
                                        'type':'string',
                                        'description':'The city name, e.g. Lviv'
                                    }
                                },
                                'required': ['location']
                            }
                    }
                ]
            }
        ]
"""