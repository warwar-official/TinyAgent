def write_file(path: str, content: str) -> None:
    path = "./agent_data/" + path
    with open(path, "w") as f:
        f.write(content)