# Memory MCP

## Purpose
Handles all long-term data persistence using a RAG (Retrieval-Augmented Generation) system. It manages personal facts, archived conversations, and learned "skills".

## Features
- **Semantic Search**: Uses embeddings to find relevant memories based on meaning, not just keywords.
- **Skill Database**: Stores successful execution paths for complex tasks to improve future performance.
- **Archived Messages**: Allows the agent to reference past conversations beyond the current session history.

## Tools
### 1. `save_memory`
- **Input**: `content`, `source`, `type`.
- **Action**: Persists a fact to the memory bank.

### 2. `search_memory`
- **Input**: `query`, `limit`.
- **Returns**: Top relevant memories (truncated to 300 chars).

### 3. `save_skill`
- **Input**: `skill_data`.
- **Action**: Saves a successful task execution trace.

### 4. `search_skills`
- **Input**: `query`.
- **Returns**: Previously learned strategies for similar tasks.

### 5. `search_archived_messages`
- **Input**: `query`.
- **Returns**: Snippets from previous chat history.
