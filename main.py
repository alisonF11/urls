import telebot
import requests
import sqlite3
import re
from datetime import datetime
from telebot import types

# ===== Bot Configuration =====
TOKEN = '7800586340:AAGjVeACwjQF6vF4-6hHKJeMJC0xck9pIEk'
ADMIN_IDS = [7148392834]  # Replace with your Telegram administrator IDs
bot = telebot.TeleBot(TOKEN)

# ===== SQLite Database Connection =====
conn = sqlite3.connect('bot_admin.db', check_same_thread=False)
cursor = conn.cursor()

# Create the users table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    language_code TEXT
)
''')

# Create the links table
cursor.execute('''
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_url TEXT,
    shortened_url TEXT,
    created_at TEXT,
    click_count INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')
conn.commit()

# ===== Messages Dictionary =====
MESSAGES = {
    "start": {
        "en": "🎉 Welcome to the URL Shortener Bot!\nSend me a URL and I'll shorten it instantly 🔗."
    },
    "error_shortening": {
        "en": "⚠️ Oops! An error occurred while shortening the URL."
    },
    "shortened_response": {
        "en": "🔗 **Your shortened URL is:** {}"
    },
    "not_authorized": {
        "en": "🚫 You are not authorized to use this command."
    },
    "users_list": {
        "en": "👥 List of users:\n{}"
    },
    "notify_sent": {
        "en": "📢 Notification sent to {} users."
    },
    "delete_usage": {
        "en": "Usage: /admin_delete <user_id>."
    },
    "user_deleted": {
        "en": "✅ User {} removed from the bot."
    },
    "user_not_found": {
        "en": "⚠️ User not found."
    },
    "admin_commands": {
        "en": ("Admin Commands:\n"
               "/admin_users - List all users\n"
               "/admin_notify <message> - Send a notification to all users\n"
               "/admin_delete <user_id> - Delete a user by ID")
    },
    "invalid_link": {
        "en": "⚠️ Please provide a valid URL."
    }
}

def get_lang(message):
    """Always returns 'en' to enforce English messages."""
    return "en"

def get_msg(key, lang):
    return MESSAGES.get(key, {}).get(lang, MESSAGES.get(key, {}).get("en", ""))

def format_url(url):
    """Adds 'https://' if the URL does not start with 'http://' or 'https://'."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    return url

def shorten_url(url):
    """Uses the TinyURL API to shorten the URL."""
    api_url = f"http://tinyurl.com/api-create.php?url={url}"
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            return response.text.strip()
        return None
    except Exception as e:
        print("Error calling TinyURL API:", e)
        return None

def add_user(user):
    """Records the user in the database."""
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, language_code) VALUES (?, ?, ?)",
        (user.id, user.username, user.language_code)
    )
    conn.commit()

# ===== USER COMMANDS =====

@bot.message_handler(commands=['start'])
def start(message):
    # Always display the welcome message in English
    bot.send_message(message.chat.id, MESSAGES["start"]["en"])
    add_user(message.from_user)

# Handler for messages containing a URL
@bot.message_handler(func=lambda message: message.text and (message.text.startswith("http://") or 
    message.text.startswith("https://") or (not message.text.startswith("/") and '.' in message.text)))
def handle_url(message):
    lang = get_lang(message)
    add_user(message.from_user)
    original_url = format_url(message.text)
    shortened = shorten_url(original_url)
    if shortened is None:
        bot.send_message(message.chat.id, get_msg("error_shortening", lang))
        return
    now = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO links (user_id, original_url, shortened_url, created_at) VALUES (?, ?, ?, ?)",
        (message.from_user.id, original_url, shortened, now)
    )
    conn.commit()
    response_text = get_msg("shortened_response", lang).format(shortened)
    bot.send_message(message.chat.id, response_text, parse_mode="Markdown")

# Handler for other messages
@bot.message_handler(func=lambda message: not (message.text.startswith("http://") or 
    message.text.startswith("https://") or message.text.startswith("/") or '.' in message.text))
def handle_invalid_message(message):
    lang = get_lang(message)
    bot.send_message(message.chat.id, get_msg("invalid_link", lang))

# ===== ADMINISTRATOR COMMANDS =====

# /admin command: sends the list of admin commands directly to the administrator
@bot.message_handler(commands=['admin'])
def admin(message):
    lang = get_lang(message)
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, get_msg("not_authorized", lang))
        return
    bot.send_message(message.chat.id, get_msg("admin_commands", lang))

# /admin_users: Displays the list of all users
@bot.message_handler(commands=['admin_users'])
def admin_users(message):
    lang = get_lang(message)
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, get_msg("not_authorized", lang))
        return
    cursor.execute("SELECT user_id, username, language_code FROM users")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "No users found.")
        return
    user_list = "\n".join([f"ID: {row[0]}, Username: {row[1]}, Lang: {row[2]}" for row in rows])
    bot.send_message(message.chat.id, get_msg("users_list", lang).format(user_list))

# /admin_notify: Sends a notification to all users
@bot.message_handler(commands=['admin_notify'])
def admin_notify(message):
    lang = get_lang(message)
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, get_msg("not_authorized", lang))
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Usage: /admin_notify <message>")
        return
    notify_text = parts[1]
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, "📢 " + notify_text)
            count += 1
        except Exception as e:
            print(f"Error sending to {uid}: {e}")
    bot.send_message(message.chat.id, get_msg("notify_sent", lang).format(count))

# /admin_delete: Deletes a user by ID
@bot.message_handler(commands=['admin_delete'])
def admin_delete(message):
    lang = get_lang(message)
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, get_msg("not_authorized", lang))
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, get_msg("delete_usage", lang))
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, get_msg("delete_usage", lang))
        return
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        bot.send_message(message.chat.id, get_msg("user_not_found", lang))
        return
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM links WHERE user_id = ?", (user_id,))
    conn.commit()
    bot.send_message(message.chat.id, get_msg("user_deleted", lang).format(user_id))

# ===== Start the Bot =====
bot.polling()
