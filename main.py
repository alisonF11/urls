import telebot
import requests
import sqlite3
import re
from datetime import datetime, timedelta
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
    expiration TEXT,
    click_count INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')
conn.commit()

# ===== Messages Dictionary =====
MESSAGES = {
    "start": {
        "en": "🎉 Welcome to the URL Shortener Bot!\nSend me a URL and I'll shorten it instantly 🔗.\n\n(Note: This bot supports setting link expiration in days, hours, or minutes.)",
        "fr": "🎉 Bienvenue sur le Bot Raccourcisseur d'URL !\nEnvoyez-moi une URL et je vous la raccourcirai instantanément 🔗.\n\n(Attention : Ce bot permet de définir l'expiration du lien en jours, heures ou minutes.)"
    },
    "error_shortening": {
        "en": "⚠️ Oops! An error occurred while shortening the URL.",
        "fr": "⚠️ Oups ! Une erreur est survenue lors du raccourcissement de l'URL."
    },
    "shortened_response": {
        "en": "🔗 **Your shortened URL is:** {}",
        "fr": "🔗 **Votre lien raccourci est :** {}"
    },
    "ask_expiration": {
        "en": "Would you like to set an expiration date for this link?",
        "fr": "Souhaitez-vous définir une date d'expiration pour ce lien ?"
    },
    "button_expire": {
        "en": "⏳ Set expiration date",
        "fr": "⏳ Définir une date d'expiration"
    },
    "enter_expiration": {
        "en": "📅 Enter the expiration time (e.g., '7', '7 days', '3 hours', '15 minutes'):",
        "fr": "📅 Entrez le temps d'expiration (exemple : '7', '7 days', '3 hours', '15 minutes') :"
    },
    "expiration_set": {
        "en": "✅ The link's expiration has been set for {} ⏰.",
        "fr": "✅ L'expiration du lien a été définie pour {} ⏰."
    },
    "invalid_expiration": {
        "en": "⚠️ Please enter a valid expiration (number and unit: days, hours, or minutes).",
        "fr": "⚠️ Veuillez entrer une durée d'expiration valide (nombre et unité : days, hours ou minutes)."
    },
    "not_authorized": {
        "en": "🚫 You are not authorized to use this command.",
        "fr": "🚫 Vous n'êtes pas autorisé à utiliser cette commande."
    },
    "users_list": {
        "en": "👥 List of users:\n{}",
        "fr": "👥 Liste des utilisateurs :\n{}"
    },
    "notify_sent": {
        "en": "📢 Notification sent to {} users.",
        "fr": "📢 Notification envoyée à {} utilisateurs."
    },
    "delete_usage": {
        "en": "Usage: /admin_delete <user_id>.",
        "fr": "Usage : /admin_delete <user_id>."
    },
    "user_deleted": {
        "en": "✅ User {} removed from the bot.",
        "fr": "✅ Utilisateur {} supprimé du bot."
    },
    "user_not_found": {
        "en": "⚠️ User not found.",
        "fr": "⚠️ Utilisateur non trouvé."
    },
    "admin_commands": {
        "en": ("Admin Commands:\n"
               "/admin_users - List all users\n"
               "/admin_notify <message> - Send a notification to all users\n"
               "/admin_delete <user_id> - Delete a user by ID"),
        "fr": ("Commandes Admin :\n"
               "/admin_users - Afficher la liste des utilisateurs\n"
               "/admin_notify <message> - Envoyer une notification à tous les utilisateurs\n"
               "/admin_delete <user_id> - Supprimer un utilisateur par ID")
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

def parse_expiration(text):
    """
    Parses the text to return a timedelta.
    Accepted examples: "7", "7 days", "3 hours", "15 minutes", "7d", "3h", "15m".
    If no unit is provided, days are assumed.
    """
    text = text.strip().lower()
    # If it is only a number, assume days
    if text.isdigit():
        return timedelta(days=int(text))
    match = re.match(r"(\d+)\s*(\w+)", text)
    if not match:
        return None
    number = int(match.group(1))
    unit = match.group(2)
    if unit in ["day", "days", "d"]:
        return timedelta(days=number)
    elif unit in ["hour", "hours", "h"]:
        return timedelta(hours=number)
    elif unit in ["minute", "minutes", "min", "m"]:
        return timedelta(minutes=number)
    return None

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

# Dictionary to track pending expiration states (chat_id -> link_id)
pending_expiration = {}

# ===== USER COMMANDS =====

@bot.message_handler(commands=['start'])
def start(message):
    # Always display the welcome message in English
    bot.send_message(message.chat.id, MESSAGES["start"]["en"])
    add_user(message.from_user)

# Handler for messages containing a URL (also checks that the chat is not waiting for expiration input)
@bot.message_handler(func=lambda message: message.text and (message.text.startswith("http://") or 
    message.text.startswith("https://") or (not message.text.startswith("/") and '.' in message.text))
    and message.chat.id not in pending_expiration)
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
    link_id = cursor.lastrowid

    response_text = get_msg("shortened_response", lang).format(shortened) + "\n\n" + get_msg("ask_expiration", lang)
    markup = types.InlineKeyboardMarkup()
    btn_expire = types.InlineKeyboardButton(get_msg("button_expire", lang), callback_data=f"set_expiration:{link_id}")
    markup.add(btn_expire)
    bot.send_message(message.chat.id, response_text, reply_markup=markup, parse_mode="Markdown")

# Callback for the button to set expiration
@bot.callback_query_handler(func=lambda call: call.data.startswith("set_expiration"))
def callback_set_expiration(call):
    lang = get_lang(call.message)
    try:
        _, link_id = call.data.split(":")
        pending_expiration[call.message.chat.id] = int(link_id)
        bot.answer_callback_query(call.id, get_msg("enter_expiration", lang))
        bot.send_message(call.message.chat.id, get_msg("enter_expiration", lang))
    except Exception as e:
        bot.answer_callback_query(call.id, get_msg("callback_error", lang))

# Handler to receive the expiration time provided by the user
@bot.message_handler(func=lambda message: message.chat.id in pending_expiration)
def set_expiration(message):
    lang = get_lang(message)
    delta = parse_expiration(message.text)
    if delta is None:
        bot.send_message(message.chat.id, get_msg("invalid_expiration", lang))
        return
    link_id = pending_expiration[message.chat.id]
    expiration_date = datetime.now() + delta
    cursor.execute(
        "UPDATE links SET expiration = ? WHERE id = ?",
        (expiration_date.isoformat(), link_id)
    )
    conn.commit()
    bot.send_message(message.chat.id, get_msg("expiration_set", lang).format(message.text.strip()))
    del pending_expiration[message.chat.id]

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
        bot.send_message(message.chat.id, "No users found." if lang=="en" else "Aucun utilisateur trouvé.")
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
        bot.send_message(message.chat.id, "Usage: /admin_notify <message>" if lang=="en" else "Usage : /admin_notify <message>")
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
