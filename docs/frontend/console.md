# Console Frontend

## Overview
A simple command-line interface for local interaction with the agent. Useful for debugging and rapid testing without external dependencies.

## Usage
When the agent starts in console mode, it will prompt:
`Enter your message:`

- Type your message and press Enter.
- Type `/bye` to exit.

## Features
- Displays status updates with `[STATUS]` prefix.
- Displays final responses and indicates generated image hashes.
- Built using `prompt_toolkit` for a better CLI experience.

## Limitations
- Does not support uploading images directly (unlike Telegram).
- Text-only output.
