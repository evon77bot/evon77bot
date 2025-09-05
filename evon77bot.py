from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import csv
import os
import asyncio
from datetime import datetime

# Get token from Render environment
TOKEN = os.getenv("BOT_TOKEN")

# Store participants (user_id → {"username": str, "tickets": int})
participants = {}
winner_count = 1
draw_number = 0  # counter for each draw

# History file
HISTORY_FILE = "draw_history.csv"
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Draw Number", "Date", "Winners"])

# --- Commands ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎟 Enter Draw", callback_data="enter_draw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
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
        await query.edit_message_text(f"✅ {username}, you have entered the draw with 1 ticket!")
    else:
        await query.edit_message_text(f"⚠️ {username}, you are already in the draw.")

async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if not participants:
        await update.message.reply_text("⚠️ No participants yet.")
        return

    msg = "📋 Current Participants:\n\n"
    for p in participants.values():
        msg += f"- {p['username']} ({p['tickets']} 🎟)\n"

    await update.message.reply_text(msg)

async def add_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addtickets <username> <number>")
        return

    username = context.args[0].lstrip("@")
    try:
        tickets = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number of tickets.")
        return

    for uid, data in participants.items():
        if data["username"] == username:
            data["tickets"] += tickets
            await update.message.reply_text(f"✅ Added {tickets} tickets to {username}.")
            return

    await update.message.reply_text(f"⚠️ User @{username} not found in participants.")

async def draw_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global draw_number
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
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

    # Build ticket pool
    pool = []
    for p in participants.values():
        pool.extend([p["username"]] * p["tickets"])

    total_participants = len(participants)
    total_tickets = len(pool)

    winners = random.sample(pool, min(num_winners, len(pool)))
    draw_number += 1

    # Save to history
    with open(HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([draw_number, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ", ".join(winners)])

    # 🎰 Shuffle animation
    shuffle_msg = await update.message.reply_text("🎰 Rolling the wheel...")
    for _ in range(5):
        fake_name = random.choice(pool)
        await shuffle_msg.edit_text(f"🎰 Spinning... maybe {fake_name}?")
        await asyncio.sleep(1)

    # Final result
    await shuffle_msg.edit_text(
        f"🎉 Lucky Draw #{draw_number}\n\n"
        f"👥 Participants: {total_participants}\n"
        f"🎟 Total Tickets: {total_tickets}\n\n"
        f"🏆 Winner(s):\n" + "\n".join(f"- {w}" for w in winners)
    )

    # Reset participants after draw
    participants.clear()

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(HISTORY_FILE):
        await update.message.reply_text("⚠️ No history yet.")
        return

    with open(HISTORY_FILE, "r") as f:
        lines = f.readlines()[1:]

    if not lines:
        await update.message.reply_text("⚠️ No history yet.")
        return

    msg = "📜 Lucky Draw History:\n\n"
    for line in lines[-5:]:  # last 5 draws
        draw_num, date, winners = line.strip().split(",")
        msg += f"#{draw_num} ({date}): {winners}\n"

    await update.message.reply_text(msg)

async def clear_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    participants.clear()
    await update.message.reply_text("🧹 All participants cleared!")

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

    app.run_polling()

if __name__ == "__main__":
    main()
