import os

def read_file(path: str) -> str:
    if os.path.exists("./data/mnt/" + path):
        path = "./data/mnt/" + path
    else:
        return "File not found"
    with open(path, "r") as f:
        return f.read()