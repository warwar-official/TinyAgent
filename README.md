# TinyAgent

TinyAgent is a lightweight, CLI-based AI agent designed to interact with users via terminal and perform tasks autonomously utilizing a multi-tool setup. Driven by external Large Language Models (LLMs) via providers, the agent maintains dialogue history, builds a long-term vector database of memories, and seamlessly coordinates different modular tools like web searching and file interaction.

## Features

- **CLI Interface**: An interactive, prompt-based session (powered by `prompt_toolkit`) allowing natural conversation.
- **Dynamic Provders & Models**: Configurable model API endpoints (e.g. Google-compatible and OpenAI-compatible structures).
- **Tool Calling System**: Extendable tool framework supporting web searches, url fetching, weather fetching, file reading, and file writing.
- **RAG & Vector Memory**: Automates context-awareness across multiple sessions using a FAISS-powered database to seamlessly recall, embed, and merge similar long-term memories or facts.
- **Automated Summarization**: Extracts history states and memories when context windows approach boundaries to reduce token overhead.

## Prerequisites
- Python 3.9+ 
- Create a `.env` file in the project's root space storing credentials like your actual API Keys to connect to LLM providers (e.g. `GEMINI_API_KEY`).

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

Settings are managed within `config.json`.
- Configure the agent's LLM model info and active modules under `"agent"`.
- Configure tool descriptions and parameters under `"tools"`.
- Configure memory models, storage locations, and flags under `"context"`. By default, the memory database uses `./data/memory/` and session dialogue history resides in `./data/history.json`.

*Note: For safe usage, the agent attempts to read/write files primarily inside a controlled path space (`./data/mnt/`).*

## Running TinyAgent

Execute the main script to start chatting:

```bash
python main.py
```

- Type your message and hit Enter. 
- Type `/bye` to smoothly exit the application.
