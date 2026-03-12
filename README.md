# TinyAgent

TinyAgent is a lightweight AI agent designed to interact with users via terminal or Telegram and perform tasks autonomously utilizing a modular MCP-based tool system. Driven by external Large Language Models (LLMs) via configurable providers, the agent maintains dialogue history, builds a long-term vector database of memories, processes images via vision-capable models, and coordinates modular tools like web searching and file interaction.

## Features

- **Dynamic MCP Architecture**: Modular server-based design where tools, prompts, and retrieval are handled by independent, configurable MCP servers. The standard set (`base_tools`, `prompt_builder`, `retrieval`) is loaded dynamically via a unified `tools/mcp_config.json`, which also natively supports future integration with remote JSON-RPC APIs.
- **Image Processing (Vision)**: Accepts photos via Telegram, stores them locally, and sends base64-encoded images to vision-capable LLMs (Google Gemini, OpenAI). Models can be configured with `vision_enabled` flag.
- **Document Retrieval (RAG)**: `RetrievalMCP` server allows the agent to index local files and web pages into a vector knowledge base and retrieve relevant chunks on demand.
- **CLI & Telegram Interface**: Interactive prompt-based terminal session (powered by `prompt_toolkit`) or Telegram bot frontend with photo support.
- **Dynamic Providers & Models**: Configurable model API endpoints (Google-compatible and OpenAI-compatible structures) with separate main and summary models.
- **Tool Calling System**: Extendable tool framework supporting web searches, URL fetching, weather fetching, file reading, and file writing. Tools and their configurations are defined entirely in `mcp_config.json` without modifying base Python logic.
- **RAG & Vector Memory**: Context-awareness across multiple sessions using Qdrant vector database with FastEmbed (`intfloat/multilingual-e5-large`) to recall, embed, and merge long-term memories.
- **Automated Summarization**: Extracts history states and memories when context windows approach boundaries to reduce token overhead. Summarization runs without images (`encode_images=False`) for efficiency.

*Note: For safe usage, the agent reads/writes files primarily inside a controlled path space (`./data/mnt/`).*

## Prerequisites
- Python 3.9+
- Create a `.env` file in the project's root storing credentials like API keys (e.g. `GEMINI_API_KEY`, `BRAVE_API_KEY`, `TELEGRAM_BOT_TOKEN`).

## Installation

1. **Clone the repository:**
   ```bash
   git clone [repository-url]
   cd TinyAgent
   ```
2. **Setup virtual environment (recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Settings are managed within two main configuration files: `config.json` for agent properties, and `tools/mcp_config.json` for MCP routes.

- **`config.json`**:
  - **`agent.model`** — Main LLM model config. Set `vision_enabled: true` for models that support image inputs.
  - **`agent.summary_model`** — Model used for summarization and memory extraction.
  - **`context`** — Memory models, storage locations, and flags. Database uses `./data/memory/db/` (Qdrant). The `mcp_config_path` points to the primary JSON defining your active tools.
- **`tools/mcp_config.json`**:
  - Defines the array of active servers (either `local_class` Python models or `remote` endpoints).
  - Explicitly documents all tools, prompts, and specialized abilities for dynamic injection.

### Telegram Frontend Integration
TinyAgent supports interacting via Telegram with **text and photo** messages:
1. Ensure `pyTelegramBotAPI` is installed (`pip install -r requirements.txt`).
2. Add your Telegram Bot Token to `.env` as `TELEGRAM_BOT_TOKEN="your_token_here"`.
3. In `main.py`, set `USE_TELEGRAM_FRONTEND = True`.
4. Run the script. A one-time link will be printed to your console. Click it to initialize your chat session.

### Image Processing
When a photo is sent via Telegram:
1. The image is downloaded and stored in `data/images/` as `<md5_hash>.jpg`.
2. An `image_index.json` tracks all stored images.
3. The image is base64-encoded and included in the LLM payload.
4. If the active model has `vision_enabled: false`, the agent returns an error instead of running inference.

*Note: Only single images are supported per message. Multi-image uploads are rejected with a warning.*

## Running TinyAgent

Execute the main script to start chatting:

```bash
python main.py
```

- Type your message and hit Enter.
- Type `/bye` to smoothly exit the application.

## Project Structure

```
imports/
├── mcp/
│   ├── base.py                   # MCPServer base class
│   ├── connector.py              # MCPConnector — config parser and command router
│   └── remote.py                 # RemoteMCPServer — JSON-RPC HTTP wrapper
├── image_manager.py              # Image download, storage, base64 encoding
├── loop_manager.py               # Agent inference loop and orchestration
├── history_manager.py            # Dialogue history with image support
├── memory_rag.py                 # Long-term vector memory (Qdrant)
├── providers_manager.py          # LLM API request handling (Google, OpenAI)
├── task_manager.py               # Multi-step task orchestration
├── tools/                        # Base Python tools (web_search, etc.)
└── plugins/
    └── telegram.py               # Telegram bot frontend
    
tools/
├── mcp_config.json               # Main orchestration template for servers, tools, and abilities
├── basetools_mcp.py              # Tool loading and execution interface
├── prompt_builder_mcp.py         # System prompt assembly
└── retrieval_mcp.py              # Document retrieval (add_file, add_url, retrieve)
```

