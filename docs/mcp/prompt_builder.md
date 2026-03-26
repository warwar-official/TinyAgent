# Prompt Builder MCP

## Purpose
The `PromptBuilderMCP` is responsible for centralizing all prompts used by the agent's various roles (Router, Executor, Verifier, etc.). It ensures consistency and allows for easy updates to the agent's reasoning logic.

## Functions
- **System Prompt Construction**: Combines identity, memories, and task history into a coherent system instruction.
- **Role-Specific Prompts**: Provides specialized templates for different pipeline stages.

## Prompts Managed
- `system_prompt`
- `router_role_prompt`
- `executor_role_prompt`
- `verifier_role_prompt`
- `aggregator_role_prompt`
- `formatter_role_prompt`
- `summary_role_prompt`
- `memory_creation_role_prompt`
- `memory_retrieval_role_prompt`
- `skill_builder_role_prompt`

## Usage Example
```python
prompt = mcp.get_prompt("executor_role_prompt", arguments={"task": "Find a recipe"})
```
