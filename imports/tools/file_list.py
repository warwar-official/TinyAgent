import os

def file_list(dir: str) -> dict:

    tool_answer = {
        "tool_name": "file_list",
        "tool_arguments": {
            "dir": dir
        },
        "tool_result": None,
        "truncate": False,
        "error": None
    }

    # Remove leading slash so os.path.join doesn't treat it as absolute root
    safe_dir = dir.lstrip("/")
    
    # Establish the base allowed directory as an absolute path
    base_mnt_dir = os.path.abspath("./data/mnt")
    
    # Construct the target path and resolve it absolutely
    target_dir = os.path.abspath(os.path.join(".", "data", "mnt", safe_dir))
    
    # Check for directory traversal (must be inside base_mnt_dir)
    if not target_dir.startswith(base_mnt_dir):
         tool_answer["error"] = "Permission denied. Cannot access paths outside of data/mnt/"
         return tool_answer

    if not os.path.exists(target_dir):
        tool_answer["error"] = f"Error: Directory '{dir}' does not exist."
        return tool_answer
    if not os.path.isdir(target_dir):
        tool_answer["error"] = f"Error: Path '{dir}' is not a directory."
        return tool_answer
    
    try:
        items = os.listdir(target_dir)
        if not items:
            tool_answer["tool_result"] = "Directory is empty."
            return tool_answer
        
        result = []
        for item in items:
            item_path = os.path.join(target_dir, item)
            if os.path.isdir(item_path):
                result.append(f"[DIR]  {item}")
            else:
                result.append(f"[FILE] {item}")
        
        tool_answer["tool_result"] = "\n".join(sorted(result))
        return tool_answer
    except Exception as e:
        tool_answer["error"] = f"Error reading directory: {str(e)}"
        return tool_answer