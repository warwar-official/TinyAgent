# CONTEXT MANAGER

Manage context, base promts, agent data etc.

## config structure

1. prompt_path - path to dir with "SYSTEM.md", "TOOLS.md", "CHARACTER.md", "ABILITIES.md", "utility/"
    1. SYSTEM.md - contain system prompt template
    2. TOOLS.md - contain tools prompt template
    3. CHARACTER.md - contain template for identity summary implemantation
    4. ABILITIES.md - prompt for ability, like thinking
    5. utility/ - dir with service prompts
        1. identity_summary.md - prompt for identity summarizing
        2. conversation_summary.md - prompt for conversation summarizing
        3. memory_summary.md - prompt for memory summarizing
        4. tool_summary.md - prompt for tool's result summarizing