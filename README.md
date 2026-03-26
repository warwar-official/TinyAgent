# TinyAgent

TinyAgent is a lightweight AI agent designed to interact with users via terminal or Telegram and perform tasks autonomously utilizing a modular MCP-based tool system.

## Features

- **Dynamic MCP Architecture**: Modular design where tools, prompts, and retrieval are handled by independent servers.
- **Image Processing (Vision)**: Accepts photos via Telegram and processes them with vision-capable LLMs.
- **RAG & Vector Memory**: Context-awareness across multiple sessions using a vector database.
- **Automated Summarization**: Extracts history states and memories to reduce token overhead.
- **RPS Control**: Built-in 1.5s delay to prevent rate-limiting from API providers.
- **Debug Mode**: Toggleable intermediate status updates via `DEBUG` environment variable.

## MCP System

TinyAgent uses a Model Context Protocol (MCP) inspired architecture to manage external tools, prompts, and system state.

→ See detailed documentation: [docs/mcp/index.md](docs/mcp/index.md)

## Frontends

TinyAgent supports multiple frontends for interaction, including Telegram and a local Console CLI.

→ See detailed documentation: [docs/frontend/index.md](docs/frontend/index.md)

## Prerequisites

- Python 3.9+
- Create a `.env` file in the project's root with:
  - `GEMINI_API_KEY`
  - `TELEGRAM_BOT_TOKEN`
  - `DEBUG=True` (optional, for technical status updates)

## Installation

1. **Clone the repository:**
   ```bash
   git clone [repository-url]
   cd TinyAgent
   ```
2. **Setup virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Settings are managed within:
- `config/config.json`: Main agent properties.
- `config/mcp_config.json`: MCP routes and tool definitions.

## Running TinyAgent

Execute the main script to start chatting:

```bash
python main.py
```

- Type your message and hit Enter.
- Type `/bye` to smoothly exit the application.
