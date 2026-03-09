from imports.mcp.base import MCPServer
from datetime import datetime


class PromptBuilderMCP(MCPServer):
    """MCP server that assembles system prompts.

    Moves the prompt-building logic out of ``LoopManager._make_payload``
    into a dedicated MCP endpoint.
    """

    def __init__(self, prompts: dict) -> None:
        self._prompts = prompts

    # ------------------------------------------------------------------
    # RPC handlers
    # ------------------------------------------------------------------

    def _rpc_prompt_list(self, params: dict) -> list[dict]:
        return [
            {
                "name": "system_prompt",
                "description": "Builds the full system prompt for the agent.",
            }
        ]

    def _rpc_prompt_generate(self, params: dict) -> str:
        """Build a system prompt from the supplied arguments.

        Expected ``params["arguments"]``::

            {
                "identity":          str,
                "tool_description":  str,   # pre-formatted tool list
                "retrieved_memory":  str,
                "autonomous_notes":  str,
                "task_info":         str | None,  # optional [TASK] block
            }

        The ``ability_prompt``, ``tools_prompt``, ``securety_prompt`` are
        read from the prompts dict that was passed at construction time.
        """
        args: dict = params.get("arguments", {})

        identity = args.get("identity", "")
        tool_description = args.get("tool_description", "")
        retrieved_memory = args.get("retrieved_memory", "None")
        autonomous_notes = args.get("autonomous_notes", "")
        task_info = args.get("task_info", "")

        ability_prompt = self._prompts.get("ability_prompt", "")
        tools_prompt = self._prompts.get("tools_prompt", "")
        security_prompt = self._prompts.get("securety_prompt", "")

        system_prompt = (
            "[SYSTEM]\n\n"
            "# IDENTITY SECTION\n\n"
            f"{identity}\n\n"
            "# TECHNICAL SECTION\n\n"
            f"{ability_prompt}\n\n"
            f"{tools_prompt}\n"
            f"{tool_description}\n\n"
            "# RUNTIME STATE\n\n"
            f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Retrived memories:\n{retrieved_memory}\n"
            f"Notes from the autonomus loop:\n{autonomous_notes}\n"
            f"{security_prompt}\n"
            "[END_SYSTEM]\n"
        )

        if task_info:
            system_prompt += task_info

        return system_prompt
