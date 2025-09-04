from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import os
import random
import csv
from datetime import datetime

# ======================
# Bot Token (from Render env)
# ======================
TOKEN = os.getenv("BOT_TOKEN")

# Store participants {user_id: {"username": str, "tickets": int}}
participants = {}
HISTORY_FILE = "winners.csv"

# ======================
# Check if user is admin
# ======================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]

# ======================
# /start command
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎟 Join Lucky Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to Evon77 Lucky Draw Bot!\nClick below to join 🎉",
        reply_markup=reply_markup
    )

# ======================
# /enter command
# ======================
async def enter_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    if user_id not in participants:
        participants[user_id] = {"username": username, "tickets": 1}
    else:
        participants[user_id]["tickets"] += 1

    await update.message.reply_text(
        f"🎟 {username} entered the lucky draw! (Total tickets: {participants[user_id]['tickets']})"
    )

# ======================
# Button handler (Join Draw)
# ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "enter":
        user = query.from_user
        user_id = user.id
        username = user.username or user.first_name

        if user_id not in participants:
            participants[user_id] = {"username": username, "tickets": 1}
        else:
            participants[user_id]["tickets"] += 1

        await query.edit_message_text(
            f"🎟 {username} entered the lucky draw! (Total tickets: {participants[user_id]['tickets']})"
        )

# ======================
# /list command (admin only)
# ======================
async def list_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can see the list.")
        return

    if not participants:
        await update.message.reply_text("📭 No participants yet.")
        return

    msg = "📋 *Current Participants:*\n"
    for user_id, data in participants.items():
        msg += f"- {data['username']}: {data['tickets']} tickets\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# ======================
# Save winner to history CSV
# ======================
def save_winner(username: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(HISTORY_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([now, username])

# ======================
# /draw command (admin only)
# ======================
async def draw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can draw winners.")
        return

    pool = []
    for user_id, data in participants.items():
        pool.extend([user_id] * data["tickets"])

    if not pool:
        await update.message.reply_text("📭 No participants to draw from.")
        return

    winner_id = random.choice(pool)
    winner = participants[winner_id]["username"]

    # Save to history
    save_winner(winner)

    await update.message.reply_text(
        f"🏆 Congratulations {winner}! You won the lucky draw! 🎉"
    )

# ======================
# /history command (admin only)
# ======================
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can see history.")
        return

    if not os.path.exists(HISTORY_FILE):
        await update.message.reply_text("📭 No winners yet.")
        return

    msg = "🏆 *Past Winners:*\n"
    with open(HISTORY_FILE, "r") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                msg += f"- {row[0]} → {row[1]}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# ======================
# /addtickets command (admin only)
# ======================
async def add_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can give tickets.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /addtickets @username 3")
        return

    username = context.args[0].replace("@", "")
    try:
        extra = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Ticket count must be a number.")
        return

    for user_id, data in participants.items():
        if data["username"] == username:
            participants[user_id]["tickets"] += extra
            await update.message.reply_text(
                f"✅ Gave {extra} tickets to {username}. (Total: {participants[user_id]['tickets']})"
            )
            return

    await update.message.reply_text("⚠️ User not found in participants.")

# ======================
# /resettickets command (admin only)
# ======================
async def reset_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can reset tickets.")
        return

    participants.clear()
    await update.message.reply_text("🔄 All tickets have been reset.")

# ======================
# Main
# ======================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("enter", enter_draw))
    app.add_handler(CommandHandler("list", list_participants))
    app.add_handler(CommandHandler("draw", draw_cmd))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("addtickets", add_tickets))
    app.add_handler(CommandHandler("resettickets", reset_tickets))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Evon77bot connected and running...")
    app.run_polling()

if __name__ == "__main__":
    main()
