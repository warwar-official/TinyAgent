from dataclasses import dataclass
import telebot
import os
import json
import time
import uuid

from imports.messaging.queue_manager import MessageBus
from imports.messaging.message_models import AgentRequest, AgentResponse

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if TOKEN:
    bot = telebot.TeleBot(TOKEN)
    bot.set_my_commands([
        telebot.types.BotCommand("init", "Initialize agent."),
        telebot.types.BotCommand("own_task", "Start autonomous task loop. Unstable if agent have no global target."),
        telebot.types.BotCommand("identity_rethink", "Update identity. Based on previous conversation."),
    ])
else:
    bot = None

def telegram_response_handler(response: AgentResponse) -> None:
    if bot:
        # Check if the response type is an error, status update, or final response
        if response.type == "status_update":
            bot.send_message(response.chat_id, f"<i>{response.text}</i>", parse_mode="HTML")
        else:
            bot.send_message(response.chat_id, response.text)

def bot_process(bus: MessageBus, secret_path: str):
    if bot:
        # Register the Telegram frontend to receive responses
        bus.register_frontend("telegram", telegram_response_handler)
        
        secret_keeper = SecretKeeper(secret_path)
        bot_username = bot.get_me().username
        link = secret_keeper.create_link(bot_username)
        print(f"Telegram Bot Link: {link}")

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

        @bot.message_handler(commands=["init"])
        def init_agent(message):
            if secret_keeper.check_user(message.from_user.id):
                bus.send_to_backend(AgentRequest(
                    frontend_type="telegram",
                    chat_id=message.chat.id,
                    action="init",
                    text=""
                ))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                print(f"User is not allowed. User id: {message.from_user.id}")
        
        @bot.message_handler(commands=["own_task"])
        def own_task(message):
            if secret_keeper.check_user(message.from_user.id):
                bus.send_to_backend(AgentRequest(
                    frontend_type="telegram",
                    chat_id=message.chat.id,
                    action="own_task",
                    text=""
                ))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                print(f"User is not allowed. User id: {message.from_user.id}")
        
        @bot.message_handler(commands=["identity_rethink"])
        def identity_rethink(message):
            if secret_keeper.check_user(message.from_user.id):
                bus.send_to_backend(AgentRequest(
                    frontend_type="telegram",
                    chat_id=message.chat.id,
                    action="identity_rethink",
                    text=""
                ))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                print(f"User is not allowed. User id: {message.from_user.id}")

        @bot.message_handler(content_types=['photo'])
        def handle_photo(message):
            if secret_keeper.check_user(message.from_user.id):
                # Reject multi-image uploads (media groups)
                if message.media_group_id:
                    bot.send_message(message.chat.id, "⚠️ Multiple images are not supported. Please send one image at a time.")
                    return
                # Get the highest resolution photo
                file_id = message.photo[-1].file_id
                file_info = bot.get_file(file_id)
                image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                caption = message.caption or ""
                
                # The image logic previously in main needs to happen BEFORE model router,
                # but to avoid blocking telegram, backend worker handles it.
                # However, the previous logic used ImageManager.save_image_from_url inside main loop.
                # To support this cleanly, we'll pass the image_url temporarily through the text or image_hash slot,
                # but it's better to add image_url to AgentRequest explicitly since ImageManager downloads it.
                bus.send_to_backend(AgentRequest(
                    frontend_type="telegram",
                    chat_id=message.chat.id,
                    action="message",
                    text=f"[IMAGE_URL_ATTACHED]:{image_url}\n{caption}"
                ))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                print(f"User is not allowed. User id: {message.from_user.id}")

        @bot.message_handler(func=lambda message: True)
        def handle_message(message):
            if secret_keeper.check_user(message.from_user.id):
                bus.send_to_backend(AgentRequest(
                    frontend_type="telegram",
                    chat_id=message.chat.id,
                    action="message",
                    text=message.text
                ))
                bot.send_chat_action(message.chat.id, "typing")
            else:
                print(f"User is not allowed. User id: {message.from_user.id}")

        bot.infinity_polling(interval=0, timeout=20)
    else:
        print("Telegram bot is not initialized")

def stop_bot():
    if bot:
        bot.stop_polling()

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