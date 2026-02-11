from imports.models.gemini import GeminiModel
from imports.tools.get_current_temperature import get_current_temperature
import json

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
        'type':'object',
        'properties': {
            'location':{
                'type':'string',
                'description':'The city name, e.g. Lviv'
            }
        },
        'required': ['location']
    }
"""

def get_toolcall(message: str) -> str:
    toolcall = message[message.find("{"):message.rfind("}")]
    return toolcall

def main():
    """model = GeminiModel("gemma-3-27b-it", "")
    payload = {
        'contents': [
            {
                'role':'user',
                'parts': [
                    {
                        'text': sys_prompt
                    }
                ]
            },
            {
                'role':'user',
                'parts': [
                    {
                        'text':'What the wether in Kyiv?'
                    }
                ]
            }
        ]
    }
    answer = model.make_request(payload)
    tool = get_toolcall(answer)"""
    tool = '{"toolcall": {"name":"get_current_temperature", "arguments": {"location": "Kyiv"}}}'
    tool_json = json.loads(tool)["toolcall"]
    func = globals()[tool_json["name"]]
    res = func(**tool_json["arguments"])
    print(res)
    """print(answer)
    print(tool)"""

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