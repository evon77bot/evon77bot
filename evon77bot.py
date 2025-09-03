from telegram import Update, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import random
import csv
import os
from datetime import datetime

# import os
TOKEN = os.getenv("BOT_TOKEN")

# Store participants (username → ticket count)
participants = {}
winner_count = 1
draw_number = 0  # counter for each draw

# History file
HISTORY_FILE = "draw_history.csv"

# Ensure history file exists with headers
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Draw Number", "Timestamp", "Username", "Tickets", "Winner?"])

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉 Welcome to Evon77bot Lucky Draw!\n"
        "➡️ Wait for admin to start a new draw.\n"
        "Admins use /newdraw <winners> to begin."
    )

# Check admin
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    return member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]

# Button handler (user entry)
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user.username or query.from_user.first_name
    await query.answer()

    if user in participants:
        await query.message.reply_text(
            f"⚠️ {user}, you are already in the draw with {participants[user]} ticket(s)."
        )
    else:
        participants[user] = 1  # default = 1 ticket
        await query.message.reply_text(f"✅ {user} entered the lucky draw with 1 ticket!")

# /newdraw (admin only)
async def newdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global winner_count, participants

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can start a draw.")
        return

    try:
        winner_count = int(context.args[0])
    except:
        await update.message.reply_text("⚠️ Usage: /newdraw <winners>")
        return

    participants = {}  # reset participants

    keyboard = [[InlineKeyboardButton("🎟️ Enter Lucky Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎁 New lucky draw started!\n"
        f"🏆 {winner_count} winner(s) will be selected!\n"
        f"➡️ Press the button below to join!",
        reply_markup=reply_markup
    )

# /participants (admin only)
async def participants_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can see the participant list.")
        return

    if not participants:
        await update.message.reply_text("ℹ️ No participants yet.")
        return

    message = "👥 Participant List:\n"
    for user, tickets in participants.items():
        message += f"- {user}: {tickets} ticket(s)\n"

    await update.message.reply_text(message)

# /addticket (admin only)
async def addticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can add tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addticket @username <number>")
        return

    username = context.args[0].lstrip("@")
    try:
        extra = int(context.args[1])
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    if username not in participants:
        participants[username] = 1  # ensure user exists
    participants[username] += extra

    await update.message.reply_text(
        f"✅ Gave {extra} extra ticket(s) to {username}. Total: {participants[username]}"
    )
# /removeticket (admin only)
async def removeticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can remove tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /removeticket @username <number>")
        return

    username = context.args[0].lstrip("@")
    try:
        remove = int(context.args[1])
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    if username not in participants:
        await update.message.reply_text(f"ℹ️ {username} is not in the draw.")
        return

    participants[username] = max(1, participants[username] - remove)  # never below 1

    await update.message.reply_text(
        f"✅ Removed {remove} ticket(s) from {username}. Total: {participants[username]}"
    )

# /setticket (admin only)
async def setticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can set tickets directly.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /setticket @username <number>")
        return

    username = context.args[0].lstrip("@")
    try:
        count = int(context.args[1])
        if count < 1:
            count = 1
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    participants[username] = count
    await update.message.reply_text(
        f"✅ Set {username}'s tickets to {count}."
    )

# /draw (admin only) + CSV export with history
async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global participants, winner_count, draw_number

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can end the draw.")
        return

    pool = []
    for user, tickets in participants.items():
        pool.extend([user] * tickets)

    if pool:
        draw_number += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        random.shuffle(pool)
        winners = list(set(pool[:winner_count]))
        mentions = ", ".join(winners)
        await update.message.reply_text(
            f"🏆 Lucky Draw #{draw_number} Results 🎉\n"
            f"📅 {now}\n"
            f"👑 Winners: {mentions}"
        )

        # Save participants to per-draw CSV
        filename = f"draw_{draw_number}.csv"
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Draw Number", "Timestamp", "Username", "Tickets", "Winner?"])
            for user, tickets in participants.items():
                winner_flag = "YES" if user in winners else "NO"
                writer.writerow([draw_number, now, user, tickets, winner_flag])

        # Send the per-draw CSV
        await update.message.reply_document(document=InputFile(filename))
        os.remove(filename)

        # Append to permanent history file
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            for user, tickets in participants.items():
                winner_flag = "YES" if user in winners else "NO"
                writer.writerow([draw_number, now, user, tickets, winner_flag])

    else:
        await update.message.reply_text("⚠️ No participants joined this draw.")

    participants = {}  # reset for next round

# /history (admin only) → download master history log
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can request the history log.")
        return

    if os.path.exists(HISTORY_FILE):
        await update.message.reply_document(document=InputFile(HISTORY_FILE))
    else:
        await update.message.reply_text("⚠️ No history file found yet.")
# Run the bot
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("newdraw", newdraw))
app.add_handler(CommandHandler("participants", participants_list))
app.add_handler(CommandHandler("addticket", addticket))
app.add_handler(CommandHandler("removeticket", removeticket))
app.add_handler(CommandHandler("setticket", setticket))
app.add_handler(CommandHandler("draw", draw))
app.add_handler(CommandHandler("history", history))
app.add_handler(CallbackQueryHandler(button_click, pattern="enter"))

print("Evon77bot is running...")

app.run_polling()

