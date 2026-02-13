def read_file(path: str) -> str:
    path = "./agent_data/" + path
    with open(path, "r") as f:
        return f.read()