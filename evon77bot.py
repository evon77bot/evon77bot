import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# === CONFIG ===
TOKEN = os.getenv("BOT_TOKEN")  # Add this as environment variable in Render
ADMIN_IDS = [7379218059]  # Replace with your Telegram user ID(s)

# === STORAGE ===
participants = {}  # {user_id: {"username": str, "tickets": int}}
draw_number = 0


# === HELPERS ===
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_username(user) -> str:
    return f"@{user.username}" if user.username else user.full_name


# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show rules + entry button. Works in group & private chat."""
    chat_type = update.effective_chat.type
    keyboard = [[InlineKeyboardButton("🎟 Join Lucky Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if chat_type == "private":
        await update.message.reply_text(
            "👋 Welcome! Thanks for starting the bot.\n\n"
            "✅ You can now receive direct messages if you win a lucky draw! 🎉"
        )
    else:
        await update.message.reply_text(
            "🎉 Welcome to the Lucky Draw!\n\n"
            "Click the button below to enter. Each user gets 1 ticket by default.\n"
            "Admins may assign bonus tickets.",
            reply_markup=reply_markup,
        )


async def enter_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button press to enter the draw."""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    username = get_username(user)

    if user_id in participants:
        participants[user_id] = {"username": username, "tickets": 1}
        await query.answer("🎟 You have entered the lucky draw!")
    else:
        await query.answer("✅ You are already in the lucky draw.")


async def list_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tickets (own if user, all if admin)."""
    user_id = update.effective_user.id

    if is_admin(user_id):
        if not participants:
            await update.message.reply_text("📭 No participants yet.")
            return

        text = "📋 *Participants & Tickets:*\n"
        for p in participants.values():
            text += f"{p['username']}: {p['tickets']} 🎟\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        if user_id not in participants:
            await update.message.reply_text("⚠️ You are not in the draw yet. Use /start to join.")
        else:
            tickets = participants[user_id]["tickets"]
            await update.message.reply_text(f"🎟 You have {tickets} ticket(s).")


async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: give extra tickets to a participant."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Only admins can give bonus tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /bonus @username number_of_tickets")
        return

    target = context.args[0]
    try:
        extra = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Ticket count must be a number.")
        return

    found = False
    for pid, pdata in participants.items():
        if pdata["username"] == target:
            pdata["tickets"] += extra
            await update.message.reply_text(f"✅ Gave {extra} bonus tickets to {pdata['username']}.")
            found = True
            break

    if not found:
        await update.message.reply_text("⚠️ User not found in the participants list.")


async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: pick a winner."""
    global draw_number
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("❌ Only admins can run the draw.")
        return

    if not participants:
        await update.message.reply_text("📭 No participants to draw from.")
        return

    # Build ticket pool
    pool = []
    for pid, pdata in participants.items():
        pool.extend([(pid, pdata["username"])] * pdata["tickets"])

    draw_number += 1
    await update.message.reply_text(f"🎲 Starting Draw #{draw_number}...")

    # Rolling effect
    for i in range(3):
        await update.message.reply_text("Rolling... 🎲")

    # Pick winner
    winner_id, winner_name = random.choice(pool)

    # Announce in group
    await update.message.reply_text(f"🏆 The winner is: {winner_name} 🎉")

    # Try sending DM
    try:
        await context.bot.send_message(
            chat_id=winner_id,
            text=f"🎉 Congratulations {winner_name}!\n"
                 f"You have won Draw #{draw_number}! 🏆"
        )
    except Exception:
        await update.message.reply_text(
            f"⚠️ Could not DM {winner_name}. They need to /start the bot in private chat."
        )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only: clear participants."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Only admins can clear participants.")
        return

    participants.clear()
    await update.message.reply_text("🧹 All participants have been cleared.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help menu (different for users/admins)."""
    user_id = update.effective_user.id
    if is_admin(user_id):
        text = (
            "📋 *Admin Commands:*\n"
            "/start - Show rules and entry button\n"
            "/draw - Pick a winner\n"
            "/bonus - Give extra tickets\n"
            "/list - Show all participants & tickets\n"
            "/clear - Clear all participants\n\n"
            "👥 *User Commands:*\n"
            "/start - Show rules and entry button\n"
            "/enter - Enter the lucky draw\n"
            "/list - Show your tickets\n"
            "/help - Show this help message"
        )
    else:
        text = (
            "👥 *User Commands:*\n"
            "/start - Show rules and entry button\n"
            "/enter - Enter the lucky draw\n"
            "/list - Show your tickets\n"
            "/help - Show this help message"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# === MAIN ===
def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_tickets))
    application.add_handler(CommandHandler("bonus", bonus))
    application.add_handler(CommandHandler("draw", draw))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(enter_draw, pattern="enter"))

    application.run_polling()


if __name__ == "__main__":
    main()




