# Telegram Frontend

## Overview
The Telegram frontend allows users to interact with TinyAgent through a dedicated Telegram bot. It is implemented using the `telebot` library.

## Features
- **Asynchronous Processing**: Messages are placed in a queue and handled by the backend worker.
- **Image Support**: Users can send images to the bot. The frontend downloads them and provides hashes to the pipeline.
- **Status Updates**: The bot displays intermediate status messages (e.g., "Routing...", "Executing tool...") if DEBUG mode is enabled.

## Configuration
Requires `TELEGRAM_BOT_TOKEN` in `.env`.

## Message Flow
1. User sends message/photo to Bot.
2. Bot downloads photo (if any) and sends `AgentRequest` to `MessageBus`.
3. Backend worker receives request, runs pipeline.
4. Pipeline returns `AgentResponse`.
5. Bot sends final text and any generated images back to the user.
