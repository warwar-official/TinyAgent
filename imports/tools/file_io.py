import os
from pathlib import Path
from typing import Dict

def file_io(path: str, mode: str, content: str = "") -> Dict:
    tool_answer = {
        "tool_name": "file_io",
        "tool_arguments": {
            "path": path,
            "mode": mode,
            "content": content
        },
        "tool_result": None,
        "truncate": False,
        "error": None
    }

    path = path.lstrip("/")
    base_path = Path("./data/mnt/").resolve()
    
    # Join safely and resolve to remove any "../" traversals
    full_path = (base_path / path).resolve()
    
    # Strictly ensure that the normalized final path lives inside base_path
    if not full_path.is_relative_to(base_path):
        tool_answer["error"] = "Path traversal is not allowed. Access denied."
        return tool_answer
        
    try:
        if mode in ("w", "a"):
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
        with open(full_path, mode) as f:
            if mode == "w":
                f.write(content)
                tool_answer["tool_result"] = "Done"
            elif mode == "a":
                f.write(content)
                tool_answer["tool_result"] = "Done"
            elif mode == "r":
                content = f.read()
                if len(content) > 10000:
                    tool_answer["truncate"] = True
                    tool_answer["tool_result"] = content[:10000] + "... (truncated)"
                else:
                    tool_answer["tool_result"] = content
            else:
                tool_answer["error"] = "Invalid mode"
        return tool_answer
    except Exception as e:
        tool_answer["error"] = f"Error: {type(e).__name__}"
        return tool_answer