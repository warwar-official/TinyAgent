import json
import os
from imports.memory_rag import MemoryRAG

def export_memories():
    # Load config to get db paths and settings
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    print("Initializing MemoryRAG...")
    memory_manager = MemoryRAG(config)

    print("Retrieving all memories from database...")
    memories_json = memory_manager.get_all_memories_json()
    memories_list = json.loads(memories_json)

    output_file = "data/all_memories.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(memories_list, f, ensure_ascii=False, indent=4)

    print(f"Successfully exported {len(memories_list)} memories to {output_file}")

if __name__ == "__main__":
    export_memories()
