from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import csv
import os
import asyncio
from datetime import datetime
import logging
import pickle
import atexit

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get token from Render environment
TOKEN = os.getenv("BOT_TOKEN")

# Store participants (user_id → {"username": str, "tickets": int})
participants = {}
winner_count = 1
draw_number = 0  # counter for each draw

# History file
HISTORY_FILE = "draw_history.csv"

# Initialize history file if it doesn't exist
if not os.path.exists(HISTORY_FILE):
    try:
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Draw Number", "Date", "Winners"])
    except IOError as e:
        logger.error(f"Error creating history file: {e}")

# Load previous draw number from history
try:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            rows = list(reader)
            if rows:
                draw_number = int(rows[-1][0])
except (IOError, ValueError, IndexError) as e:
    logger.error(f"Error loading history: {e}")

# --- Helper Functions ---
def is_admin(chat_member):
    return chat_member.status in ["administrator", "creator"]

def save_history(draw_num, date, winners):
    try:
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([draw_num, date, ", ".join(winners)])
    except IOError as e:
        logger.error(f"Error saving to history: {e}")

def save_participants():
    try:
        with open("participants.pkl", "wb") as f:
            pickle.dump(participants, f)
    except Exception as e:
        logger.error(f"Error saving participants: {e}")

def load_participants():
    global participants
    try:
        with open("participants.pkl", "rb") as f:
            participants = pickle.load(f)
    except FileNotFoundError:
        participants = {}
    except Exception as e:
        logger.error(f"Error loading participants: {e}")
        participants = {}

# Load participants at startup and register save function on exit
load_participants()
atexit.register(save_participants)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎟 Enter Draw", callback_data="enter_draw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send a new message each time to ensure the button is always visible
    await update.message.reply_text(
        "🎉 Welcome to Evon77Bot Lucky Draw!\n\nClick below to join:",
        reply_markup=reply_markup,
    )

async def enter_draw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    username = user.username or user.full_name

    if user_id not in participants:
        participants[user_id] = {"username": username, "tickets": 1}
        try:
            await query.edit_message_text(f"✅ {username}, you have entered the draw with 1 ticket!")
        except Exception as e:
            if "Message is not modified" in str(e):
                # Message is already correct, no need to edit
                pass
            else:
                logger.error(f"Error in enter_draw_callback: {e}")
    else:
        try:
            await query.edit_message_text(f"⚠️ {username}, you are already in the draw.")
        except Exception as e:
            if "Message is not modified" in str(e):
                pass
            else:
                logger.error(f"Error in enter_draw_callback: {e}")
    
    # Save participants after modification
    save_participants()

async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        
        if not is_admin(chat_member):
            await update.message.reply_text("⚠️ This command is for admins only.")
            return
    except Exception as e:
        await update.message.reply_text("⚠️ Error verifying admin status.")
        logger.error(f"Error in list_participants: {e}")
        return

    if not participants:
        await update.message.reply_text("⚠️ No participants yet.")
        return

    msg = "📋 Current Participants:\n\n"
    for p in participants.values():
        msg += f"- {p['username']} ({p['tickets']} 🎟)\n"
    
    msg += f"\nTotal: {len(participants)} participants, {sum(p['tickets'] for p in participants.values())} tickets"

    await update.message.reply_text(msg)

async def add_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        
        if not is_admin(chat_member):
            await update.message.reply_text("⚠️ This command is for admins only.")
            return
    except Exception as e:
        await update.message.reply_text("⚠️ Error verifying admin status.")
        logger.error(f"Error in add_tickets: {e}")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addtickets <username> <number>")
        return

    username = context.args[0].lstrip("@").lower()
    try:
        tickets = int(context.args[1])
        if tickets <= 0:
            await update.message.reply_text("⚠️ Please provide a positive number of tickets.")
            return
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number of tickets.")
        return

    for uid, data in participants.items():
        if data["username"].lower() == username:
            data["tickets"] += tickets
            await update.message.reply_text(f"✅ Added {tickets} tickets to {data['username']}. They now have {data['tickets']} tickets.")
            save_participants()
            return

    await update.message.reply_text(f"⚠️ User @{username} not found in participants.")

async def draw_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global draw_number
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        
        if not is_admin(chat_member):
            await update.message.reply_text("⚠️ This command is for admins only.")
            return
    except Exception as e:
        await update.message.reply_text("⚠️ Error verifying admin status.")
        logger.error(f"Error in draw_winner: {e}")
        return

    if not participants:
        await update.message.reply_text("⚠️ No participants in the draw.")
        return

    # Default 1 winner
    num_winners = 1
    if context.args:
        try:
            num_winners = max(1, int(context.args[0]))
        except ValueError:
            await update.message.reply_text("⚠️ Please provide a valid number. Example: /draw 3")
            return

    # Build weighted list for drawing
    weighted_list = []
    for p in participants.values():
        weighted_list.extend([p["username"]] * p["tickets"])

    if num_winners > len(weighted_list):
        await update.message.reply_text(f"⚠️ Not enough tickets for {num_winners} winners. There are only {len(weighted_list)} tickets.")
        return

    total_participants = len(participants)
    total_tickets = len(weighted_list)

    # 🎰 Shuffle animation
    try:
        shuffle_msg = await update.message.reply_text("🎰 Rolling the wheel...")
        for i in range(5):
            fake_name = random.choice(weighted_list) if weighted_list else "No participants"
            try:
                await shuffle_msg.edit_text(f"🎰 Spinning... maybe {fake_name}?")
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.error(f"Error in draw animation: {e}")
            await asyncio.sleep(1)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error during animation: {e}")
        logger.error(f"Error in draw_winner animation: {e}")
        return

    # Draw winners
    winners = []
    for _ in range(num_winners):
        if not weighted_list:
            break
        winner = random.choice(weighted_list)
        winners.append(winner)
        # Remove all instances of this winner to prevent duplicate wins
        weighted_list = [name for name in weighted_list if name != winner]

    draw_number += 1
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Save to history
    save_history(draw_number, current_time, winners)

    # Final result
    result_text = (
        f"🎉 Lucky Draw #{draw_number}\n\n"
        f"👥 Participants: {total_participants}\n"
        f"🎟 Total Tickets: {total_tickets}\n\n"
        f"🏆 Winner(s):\n" + "\n".join(f"- {w}" for w in winners)
    )
    
    try:
        await shuffle_msg.edit_text(result_text)
    except Exception as e:
        # If we can't edit the message, send a new one
        await update.message.reply_text(result_text)
        logger.error(f"Error editing shuffle message: {e}")

    # Reset participants after draw
    participants.clear()
    save_participants()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(HISTORY_FILE):
        await update.message.reply_text("⚠️ No history yet.")
        return

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[1:]  # Skip header
    except IOError as e:
        await update.message.reply_text("⚠️ Error reading history file.")
        logger.error(f"Error in history: {e}")
        return

    if not lines:
        await update.message.reply_text("⚠️ No history yet.")
        return

    msg = "📜 Lucky Draw History:\n\n"
    for line in lines[-5:]:  # last 5 draws
        parts = line.strip().split(",")
        if len(parts) >= 3:
            draw_num, date, winners = parts[0], parts[1], ",".join(parts[2:])
            msg += f"#{draw_num} ({date}): {winners}\n"

    await update.message.reply_text(msg)

async def clear_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        
        if not is_admin(chat_member):
            await update.message.reply_text("⚠️ This command is for admins only.")
            return
    except Exception as e:
        await update.message.reply_text("⚠️ Error verifying admin status.")
        logger.error(f"Error in clear_participants: {e}")
        return

    count = len(participants)
    participants.clear()
    save_participants()
    await update.message.reply_text(f"🧹 Cleared {count} participants!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ An error occurred. Please try again later.")
        except Exception as e:
            logger.error(f"Error in error_handler: {e}")

# --- Main ---
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(enter_draw_callback, pattern="enter_draw"))
    app.add_handler(CommandHandler("participants", list_participants))
    app.add_handler(CommandHandler("addtickets", add_tickets))
    app.add_handler(CommandHandler("draw", draw_winner))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("clear", clear_participants))
    
    # Add error handler
    app.add_error_handler(error_handler)

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
