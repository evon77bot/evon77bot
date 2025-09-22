import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# === CONFIG ===
TOKEN = os.getenv("BOT_TOKEN")  # set this in Render env

# === In-memory storage ===
participants = {}  # user_id (int) -> {"username": str, "tickets": int, "wins": int}
draw_number = 0


# === Helpers ===
async def is_admin(update: Update, user_id: int) -> bool:
    """Check if a user is admin of the current group/supergroup."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return False
    try:
        member = await chat.get_member(user_id)
        return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False


def display_name_from_user(user):
    """Return @username if available, otherwise the full name."""
    if getattr(user, "username", None):
        return f"@{user.username}"
    return user.full_name


# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show rules + persistent entry button in group; private shows welcome."""
    chat_type = update.effective_chat.type
    keyboard = [[InlineKeyboardButton("🎟 Join the Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if chat_type == "private":
        await update.message.reply_text(
            "👋 Welcome! Thanks for starting the bot.\n\n"
            "You can receive a DM if you win a draw — don't forget to /start me in private chat!"
        )
    else:
        await update.message.reply_text(
            "🎉 Welcome to the Lucky Draw!\n\n"
            "Click the button below to enter. Each user gets 1 ticket by default.\n"
            "Admins can give extra tickets with /bonus.",
            reply_markup=reply_markup
        )


async def enter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    uid = user.id
    display = display_name_from_user(user)

    if uid in participants:
        await query.answer("✅ You already joined the draw.", show_alert=False)
        return

    participants[uid] = {"username": display, "tickets": 1, "wins": 0}
    await query.answer("🎟 You have entered the draw!", show_alert=False)

    try:
        await query.message.reply_text(f"🎉 {display} has joined the draw!")
    except Exception:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎉 {display} has joined the draw!")


async def enter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    display = display_name_from_user(user)

    if uid in participants:
        await update.message.reply_text("✅ You already joined the draw.")
        return

    participants[uid] = {"username": display, "tickets": 1, "wins": 0}
    await update.message.reply_text(f"🎟 {display} entered the draw!")
    if update.effective_chat.type in ("group", "supergroup"):
        await update.message.reply_text(f"🎉 {display} has joined the draw!")


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_admin(update, user_id):
        if not participants:
            await update.message.reply_text("📭 No participants yet.")
            return
        lines = ["📋 Participants & tickets:"]
        for uid, info in participants.items():
            lines.append(f"- {info['username']}: {info['tickets']} ticket(s)")
        await update.message.reply_text("\n".join(lines))
    else:
        if user_id not in participants:
            await update.message.reply_text("⚠️ You are not in the draw yet. Press the Enter button or use /enter.")
        else:
            await update.message.reply_text(f"🎟 You have {participants[user_id]['tickets']} ticket(s).")


async def bonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(update, user_id):
        await update.message.reply_text("⛔ Only admins can use /bonus.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /bonus @username number_of_tickets")
        return

    target = context.args[0]
    try:
        extra = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Ticket count must be a number.")
        return

    target_norm = target.lstrip("@").lower()
    for uid, info in participants.items():
        uname = info["username"].lstrip("@").lower()
        if uname == target_norm:
            info["tickets"] += extra
            await update.message.reply_text(
                f"✅ Added {extra} tickets to {info['username']}. Now {info['tickets']} tickets."
            )
            return

    await update.message.reply_text("⚠️ User not found in participants. Ask them to press Enter first.")


async def draw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global draw_number
    user_id = update.effective_user.id
    if not await is_admin(update, user_id):
        await update.message.reply_text("⛔ Only admins can run the draw.")
        return

    if not participants:
        await update.message.reply_text("📭 No participants to draw from.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /draw <count> <prize text...>")
        return

    if args[0].isdigit():
        count = max(1, int(args[0]))
        prize = " ".join(args[1:]).strip()
    else:
        count = 1
        prize = " ".join(args).strip()

    pool = []
    for uid, info in participants.items():
        pool.extend([uid] * max(1, int(info.get("tickets", 1))))

    if not pool:
        await update.message.reply_text("📭 No tickets in pool.")
        return

    draw_number += 1
    await update.message.reply_text(f"🎲 Starting Draw #{draw_number}...")
    await update.message.reply_text(f"👥 Participants: {len(participants)} | 🎟 Tickets: {len(pool)}")

    winners = []
    pool_copy = pool.copy()
    while len(winners) < count and pool_copy:
        winner_uid = random.choice(pool_copy)
        if winner_uid not in winners:
            for _ in range(3):
                await update.message.reply_text("Rolling... 🎲")
                await asyncio.sleep(1.0)

            winner_info = participants.get(winner_uid, {"username": "Unknown"})
            winner_name = winner_info["username"]
            prize_text = f" — Prize: {prize}" if prize else ""
            await update.message.reply_text(f"🏆 Winner: {winner_name}{prize_text} 🎉")

            try:
                await context.bot.send_message(
                    chat_id=winner_uid,
                    text=f"🎉 Congratulations {winner_name}! You won{(' ' + prize) if prize else ''} in Draw #{draw_number}!"
                )
            except Exception:
                await update.message.reply_text(
                    f"⚠️ Could not DM {winner_name}. They need to /start the bot in private to receive DMs."
                )
            winners.append(winner_uid)
            pool_copy = [x for x in pool_copy if x != winner_uid]
        else:
            pool_copy = [x for x in pool_copy if x != winner_uid]

    winners_names = [participants[w]["username"] for w in winners]
    await update.message.reply_text("🎉 Draw complete! Winners:\n" + "\n".join(f"- {n}" for n in winners_names))
    participants.clear()


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_admin(update, user_id):
        await update.message.reply_text("⛔ Only admins can clear participants.")
        return
    participants.clear()
    await update.message.reply_text("🧹 All participants cleared.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_admin(update, user_id):
        text = (
            "📋 Admin commands:\n"
            "/start - show join button\n"
            "/draw N Prize - run draw (e.g. /draw 2 iPhone)\n"
            "/bonus @username N - give extra tickets (user must have joined)\n"
            "/list - show participants & tickets\n"
            "/clear - clear participants\n"
            "/help - this message"
        )
    else:
        text = (
            "👥 User commands:\n"
            "/start - show join button\n"
            "/enter - enter the draw\n"
            "/list - show your tickets\n"
            "/help - this message"
        )
    await update.message.reply_text(text)


# === Main ===
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("enter", enter_command))
    app.add_handler(CallbackQueryHandler(enter_callback, pattern="enter"))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("bonus", bonus_cmd))
    app.add_handler(CommandHandler("draw", draw_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Evon77Bot running with dynamic admin detection...")
    app.run_polling()


if __name__ == "__main__":
    main()

