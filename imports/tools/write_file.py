def write_file(path: str, content: str) -> str:
    path = "./agent_data/" + path
    with open(path, "w") as f:
        f.write(content)
    return "Done"