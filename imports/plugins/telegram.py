import telebot
import dotenv
import os
import queue

dotenv.load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)
chat_id: int = 0

def bot_response(message: str):
    bot.send_message(chat_id, message)

def bot_process(request_queue: queue.Queue):
    @bot.message_handler(func=lambda message: True)
    def hendle_message(message):
        global chat_id
        chat_id = message.chat.id
        request_queue.put(message.text)
        bot.send_chat_action(message.chat.id, "typing")

    bot.infinity_polling(interval=0, timeout=20)