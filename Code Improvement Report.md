# Code Improvement Report

## Architecture Review

This report presents a high-level review of `# Inefficient Code`, `# Poor Readability`, and `# Architectural Issues` in `main.py` and `loop_manager.py`.

### 1. Inefficient Code
* **Frequent JSON Reading for Logs:** The system reads from and writes to historical JSON data repeatedly. Operations like `HistoryManager.get_records` might trigger heavy IO depending on implementation details. State reading in `_task_loop` constantly invokes IO saving (`_save_state`).
* **Unnecessary Object Creations:** Within `_task_loop` inside `LoopManager`, the `AgentMessage` and `HistoryRecord` instances are sometimes created or rebuilt repeatedly in loop limits (see `STEP_PER_TASK_LIMIT`), contributing to object churn.

### 2. Poor Readability
* **Complex Logic in `LoopManager._task_loop`:** The `_task_loop` handles a complex mix of interactive vs. non-interactive tasks, stop words formatting, summary limits, and callback functions, making it difficult to follow execution paths. This should ideally be split into multiple smaller helper functions.
* **Variable Naming and Magic Strings:** Methods like `_make_payload` rely heavily on implicit boolean flags (`tool`, `history`, `task`) instead of descriptive state enumerations. Usage of raw string checks (like `"none"`, `"task"`, `"ready"`) makes typing weak and bug-prone.

### 3. Architectural Issues
* **Loose State Management Data Flow:** While `LoopState` tries to centralize state, updates happen haphazardly across the class (e.g., inside `_task_loop` versus `_summarise` versus `router`).
* **Tight Coupling with Dependencies:** `LoopManager` has a large amount of responsibilities (acting as the Router, Agent executor, Summary processor, task history writer, and Memory/RAG orchestrator). It violates the Single Responsibility Principle. 
* **Hardcoded RAG Paths:** Although we moved MCP configurations gracefully, things like `model.vision_enabled` check directly in LoopManager, or handling RAG logic via queues inside the main loop orchestrator, demonstrate fuzzy boundaries between components.
