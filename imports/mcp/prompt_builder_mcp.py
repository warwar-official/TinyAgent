from imports.mcp.base import MCPServer
from datetime import datetime


class PromptBuilderMCP(MCPServer):
    """MCP server that generates all system prompts.

    Handles system prompt assembly, summarization prompts, memory prompts,
    tool result formatting, and task stopword prompts.
    """

    def __init__(self, prompts: dict) -> None:
        self._prompts = prompts

    # ------------------------------------------------------------------
    # RPC handlers
    # ------------------------------------------------------------------

    def _rpc_prompt_list(self, params: dict) -> list[dict]:
        return [
            {"name": "system_prompt", "description": "Builds the full system prompt for the agent."},
            {"name": "conversation_summary_prompt", "description": "Prompt for summarizing conversation history."},
            {"name": "task_summary_prompt", "description": "Prompt for summarizing task progress."},
            {"name": "memory_summary_prompt", "description": "Prompt for extracting long-term memory facts."},
            {"name": "tool_summary_prompt", "description": "Prompt for summarizing long tool results."},
            {"name": "tool_result_template", "description": "Template for formatting tool results in history."},
            {"name": "task_stopword_prompt", "description": "Prompt instructing the agent about task completion."},
            {"name": "default_identity_prompt", "description": "Default identity prompt for uninitialized agents."},
        ]

    def _rpc_prompt_generate(self, params: dict) -> str:
        """Generate a prompt by name with the given arguments."""
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
            raise ValueError(f"Unknown prompt: {name}")

        if builder == self._build_simple:
            return self._prompts.get(name, "")
        elif builder == self._build_formatted:
            template = self._prompts.get(name, "")
            return template.format(**args)
        else:
            return builder(args)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

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
        """Return a static prompt template (no formatting needed)."""
        # This is dispatched specially in _rpc_prompt_generate
        return ""

    def _build_formatted(self, args: dict) -> str:
        """Return a formatted prompt template."""
        # This is dispatched specially in _rpc_prompt_generate
        return ""
