def write_file(path: str, content: str) -> str:
    path = "./data/mnt/" + path
    with open(path, "w") as f:
        f.write(content)
    return "Done"