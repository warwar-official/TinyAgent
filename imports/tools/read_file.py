import os

def read_file(path: str) -> str:
    if os.path.exists("./agent_data/" + path):
        path = "./agent_data/" + path
    elif os.path.exists("./agent_data_system/configs/" + path):
        path = "./agent_data_system/configs/" + path
    else:
        return "File not found"
    with open(path, "r") as f:
        return f.read()