from dataclasses import dataclass
import telebot
import os
import json
import queue
import time
import uuid

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if TOKEN:
    bot = telebot.TeleBot(TOKEN)
else:
    bot = None

def bot_responce(message: str, chat_id: str) -> bool:
    if bot:
        bot.send_message(chat_id, message)
        return True
    return False

def bot_process(request_queue: queue.Queue, secret_path: str):
    if bot:
        secret_keeper = SecretKeeper(secret_path)
        bot_username = bot.get_me().username
        link = secret_keeper.create_link(bot_username)
        request_queue.put(TelegramBotMessage("report", f"Link: {link}"))

        @bot.message_handler(commands=["start"])
        def start(message):
            args = message.text.split()
            if len(args) < 2:
                bot.send_message(message.chat.id, "Token required")
                bot.delete_state(message.chat.id)
            else:
                token = args[1]
                if not secret_keeper.add_user(message.from_user.id, token):
                    bot.send_message(message.chat.id, "Invalid token")
                    bot.delete_state(message.chat.id)
                bot.send_message(message.chat.id, "Token added")

        @bot.message_handler(func=lambda message: True)
        def hendle_message(message):
            if secret_keeper.check_user(message.from_user.id):
                request_queue.put(TelegramBotMessage("message", message.text, message.chat.id))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                request_queue.put(TelegramBotMessage("report", f"User is not allowed. User id: {message.from_user.id} "))
        bot.infinity_polling(interval=0, timeout=20)
    else:
        request_queue.put(TelegramBotMessage("report", "Bot is not initialized"))

@dataclass
class TelegramBotMessage:
    type: str
    message: str
    chat_id: str
    def __init__(self, type: str, message: str, chat_id: str = ""):
        self.type = type
        self.message = message
        self.chat_id = chat_id

class SecretKeeper:
    def __init__(self, path: str):
        self.allowed_users: list[str] = []
        self.active_token: str | None = None
        self.token_expires_at: float = 0

        self.path = path
        self._load_users()
    
    def add_user(self, user_id: str, token: str) -> bool:
        if user_id in self.allowed_users:
            return True
        if self._check_token(token):
            self.allowed_users.append(user_id)
            self._save_users()
            return True
        return False

    def remove_user(self, user_id: str) -> bool:
        if user_id not in self.allowed_users:
            return False
        self.allowed_users.remove(user_id)
        self._save_users()
        return True
    
    def check_user(self, user_id: str) -> bool:
        return user_id in self.allowed_users
    
    def create_link(self, bot_username: str) -> str:
        self.active_token = str(uuid.uuid4())
        self.token_expires_at = time.time() + 300
        self._save_users()
        return f"https://t.me/{bot_username}?start={self.active_token}"
    
    def _check_token(self, token: str) -> bool:
        if self.active_token == token and time.time() < self.token_expires_at:
            return True
        return False

    def _load_users(self):
        try:
            with open(self.path, "r") as f:
                self.allowed_users = json.load(f)
        except IOError as e:
            print(f"Unable to read users! Error: {e}")
        except json.JSONDecodeError as e:
            print(f"Unable to decode users! Error: {e}")
    
    def _save_users(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self.allowed_users, f)
        except IOError as e:
            print(f"Unable to write users! Error: {e}")