from imports.plugins.memory_RAG import MemoryRAG

from imports.plugins.memory_RAG import MemoryRAG

class ContextManager:
    def __init__(self, context_config: dict):
        self.memory: MemoryRAG | None = None
        try:
            prompts_path: str = context_config["prompts_path"]
            self._load_prompts(prompts_path)
            history_path: str = context_config["history_path"]
            memory_config: dict = context_config["memory"]
            if memory_config["active"]:
                self.memory = self._initialize_memory(memory_config)
        except KeyError as e:
            raise ValueError(f"Key Error while initializing context manager: {e}")
    
    def 

    def _initialize_memory(self, config: dict) -> MemoryRAG:
        pass