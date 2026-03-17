from imports.mcp.base import MCPServer
from datetime import datetime
import json

class PromptBuilderMCP(MCPServer):
    """MCP server that generates all system prompts."""

    def __init__(self, prompts_path: str) -> None:
        self._prompts = self._load_prompts(prompts_path)

    @staticmethod
    def _load_prompts(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"PromptBuilderMCP: Failed to read prompts from {path}: {e}")
            return {}

    def _rpc_prompt_generate(self, params: dict) -> str:
        name: str = params.get("name", "")
        args: dict = params.get("arguments", {})

        generators = {
            "system_prompt": self._build_system_prompt,
            "conversation_summary_prompt": self._build_simple,
            "task_summary_prompt": self._build_simple,
            "memory_summary_prompt": self._build_simple,
            "tool_summary_prompt": self._build_formatted,
            "tool_result_template": self._build_formatted,
            "task_stopword_prompt": self._build_formatted,
            "default_identity_prompt": self._build_simple,
        }

        builder = generators.get(name)
        if builder is None:
            if name in self._prompts:
                return self._prompts[name]
            raise ValueError(f"Unknown prompt: {name}")

        if builder == self._build_simple:
            return self._prompts.get(name, "")
        elif builder == self._build_formatted:
            template = self._prompts.get(name, "")
            return template.format(**args)
        else:
            return builder(args)

    def _build_system_prompt(self, args: dict) -> str:
        identity = args.get("identity", "")
        tool_description = args.get("tool_description", "")
        ability_prompt = args.get("ability_prompt", "")
        retrieved_memory = args.get("retrieved_memory", "None")
        autonomous_notes = args.get("autonomous_notes", "")
        task_info = args.get("task_info", "")

        tools_prompt = self._prompts.get("tools_prompt", "")
        security_prompt = self._prompts.get("securety_prompt", "")

        system_prompt = (
            "[SYSTEM]\n"
            "# IDENTITY SECTION\n"
            f"{identity}\n"
            "# TECHNICAL SECTION\n"
            f"{ability_prompt}\n"
            f"{tools_prompt}\n"
            f"{tool_description}\n"
            "# RUNTIME STATE\n"
            f"Current date and time: {datetime.now().strftime('%H:%M, %A, %-d %B %Y')}\n"
            f"Retrived memories:\n{retrieved_memory}\n"
            f"Notes from the autonomus loop:\n{autonomous_notes}\n"
            f"{security_prompt}\n"
            "[END_SYSTEM]\n"
        )

        if task_info:
            system_prompt += task_info

        return system_prompt

    def _build_simple(self, args: dict) -> str:
        return ""

    def _build_formatted(self, args: dict) -> str:
        return ""
