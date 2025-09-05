from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import csv
import os
from datetime import datetime

# Get token from environment variable
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
        writer.writerow(["Draw #", "Timestamp", "Winners"])


# ================= Commands =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎟 Join Lucky Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome! Click below to join the lucky draw ⬇️", reply_markup=reply_markup)


async def enter_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    if user_id not in participants:
        participants[user_id] = {"username": username, "tickets": 1}
        await update.message.reply_text(f"🎟 {username} entered the lucky draw! (1 ticket)")
    else:
        await update.message.reply_text(
            f"⚠️ {username}, you already joined! You have {participants[user_id]['tickets']} ticket(s)."
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    username = user.username or user.first_name

    if user_id not in participants:
        participants[user_id] = {"username": username, "tickets": 1}
        await query.edit_message_text(f"🎟 {username} entered the lucky draw! (1 ticket)")
    else:
        await query.edit_message_text(
            f"⚠️ {username}, you already joined! You have {participants[user_id]['tickets']} ticket(s)."
        )


async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if not participants:
        await update.message.reply_text("No participants yet.")
        return

    text = "📋 Participants:\n"
    for p in participants.values():
        text += f"- {p['username']}: {p['tickets']} ticket(s)\n"

    await update.message.reply_text(text)


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

    # Build the ticket pool
    pool = []
    for p in participants.values():
        pool.extend([p["username"]] * p["tickets"])

    winners = random.sample(pool, min(winner_count, len(pool)))
    draw_number += 1

    # Save to history
    with open(HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([draw_number, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ", ".join(winners)])

    await update.message.reply_text(
        f"🎉 Lucky Draw #{draw_number} Winners:\n" + "\n".join(f"- {w}" for w in winners)
    )


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            lines = f.readlines()[1:]  # skip header
            if not lines:
                await update.message.reply_text("No draw history yet.")
                return

            text = "📜 Draw History:\n"
            for line in lines[-5:]:  # show last 5 draws
                draw, ts, winners = line.strip().split(",", 2)
                text += f"Draw #{draw} ({ts}): {winners}\n"

            await update.message.reply_text(text)
    else:
        await update.message.reply_text("No history file found.")


async def add_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addtickets @username X")
        return

    username = context.args[0].lstrip("@")
    try:
        tickets_to_add = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Ticket count must be a number.")
        return

    for uid, p in participants.items():
        if p["username"] == username:
            p["tickets"] += tickets_to_add
            await update.message.reply_text(f"✅ Added {tickets_to_add} tickets to {username}.")
            return

    await update.message.reply_text(f"⚠️ User @{username} not found in participants.")


async def reset_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status not in ["administrator", "creator"]:
        await update.message.reply_text("⚠️ This command is for admins only.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /resettickets @username")
        return

    username = context.args[0].lstrip("@")
    for uid, p in participants.items():
        if p["username"] == username:
            p["tickets"] = 1
            await update.message.reply_text(f"✅ Reset {username}'s tickets to 1.")
            return

    await update.message.reply_text(f"⚠️ User @{username} not found in participants.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)

    if chat_member.status in ["administrator", "creator"]:
        # Admin help
        help_text = (
            "🤖 *Evon77Bot Commands (Admin)*\n\n"
            "/start – Show join button\n"
            "/enter – Join the lucky draw (1 ticket by default)\n"
            "/list – View participants & ticket counts (admin only)\n"
            "/draw – Pick a winner(s)\n"
            "/history – Show past winners\n"
            "/addtickets @username X – Add X tickets to user\n"
            "/resettickets @username – Reset user tickets to 1\n"
            "/help – Show this help message"
        )
    else:
        # Normal user help
        help_text = (
            "🤖 *Evon77Bot Commands*\n\n"
            "/start – Show join button\n"
            "/enter – Join the lucky draw (1 ticket by default)\n"
            "/help – Show this help message\n\n"
            "👉 Extra tickets can only be given by admins."
        )

    await update.message.reply_text(help_text, parse_mode="Markdown")


# ================= Main =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("enter", enter_draw))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("list", list_participants))
    app.add_handler(CommandHandler("draw", draw_winner))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("addtickets", add_tickets))
    app.add_handler(CommandHandler("resettickets", reset_tickets))
    app.add_handler(CommandHandler("help", help_command))

    print("✅ Evon77Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
