# evon77bot.py
import os
import random
import csv
from datetime import datetime
from telegram import (
    Update,
    ChatMember,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)

# Get token from environment (Render: set BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN")

# Data structures
participants = {}   # key -> {'display': str, 'tickets': int}
winner_count = 1
draw_number = 0
HISTORY_FILE = "draw_history.csv"

# Ensure history file exists
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Draw Number", "Timestamp", "Username", "Tickets", "Winner?"])

# -----------------------
# Helpers
# -----------------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False

def normalize_arg_name(arg: str) -> str:
    return arg.lstrip("@").strip()

def find_participant_key_by_name(name: str):
    """Find participant key by display name (case-insensitive)."""
    lower = name.lower()
    for k, v in participants.items():
        if v['display'].lstrip("@").lower() == lower or k.lstrip("@").lower() == lower:
            return k
    return None

# -----------------------
# Commands & Handlers
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉 Welcome to Evon77bot Lucky Draw!\n\n"
        "Admins: /newdraw <winners>\n"
        "Users: press the button or use /enter to join (default 1 ticket).\n"
        "Admins: /participants, /addticket, /removeticket, /setticket, /draw, /history"
    )

# /enter - user joins with default 1 ticket (cannot self-increase)
async def enter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    key = f"@{user.username}" if user.username else f"{user.first_name}_{user.id}"
    display = f"@{user.username}" if user.username else user.first_name

    if key in participants:
        await update.message.reply_text(f"⚠️ {display}, you are already in the draw with {participants[key]['tickets']} ticket(s).")
        return

    participants[key] = {"display": display, "tickets": 1}
    await update.message.reply_text(f"✅ {display} entered the draw with 1 ticket!")

# CallbackQuery (button press) - same semantics as /enter
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    key = f"@{user.username}" if user.username else f"{user.first_name}_{user.id}"
    display = f"@{user.username}" if user.username else user.first_name

    if key in participants:
        # Reply as a short message to the chat
        await query.message.reply_text(f"⚠️ {display}, you already entered with {participants[key]['tickets']} ticket(s).")
        return

    participants[key] = {"display": display, "tickets": 1}
    await query.message.reply_text(f"✅ {display} entered the draw with 1 ticket!")

# /newdraw <winners> - admin only, post the enter button
async def newdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global winner_count, participants
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can start a draw.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /newdraw <winners>")
        return

    try:
        winner_count = int(context.args[0])
        if winner_count < 1:
            raise ValueError()
    except:
        await update.message.reply_text("⚠️ Winners must be a positive integer. Example: /newdraw 2")
        return
        
        participants = {}  # reset participants for the new round
    keyboard = [[InlineKeyboardButton("🎟️ Enter Lucky Draw", callback_data="enter")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎁 New lucky draw started!\n🏆 {winner_count} winner(s) will be picked.\n➡️ Press the button to join!",
        reply_markup=reply_markup
    )

# /participants - admin only
async def participants_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can view participants.")
        return

    if not participants:
        await update.message.reply_text("ℹ️ No participants yet.")
        return

    lines = ["👥 Participant List:"]
    for k, v in participants.items():
        lines.append(f"- {v['display']}: {v['tickets']} ticket(s)")
    await update.message.reply_text("\n".join(lines))

# /addticket @name N  (admin)
async def addticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can add tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /addticket @username <number>")
        return

    name = normalize_arg_name(context.args[0])
    try:
        extra = int(context.args[1])
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    key = find_participant_key_by_name(name)
    if key is None:
        # user not in list — create with default 1 plus extra
        key = f"@{name}"
        participants[key] = {"display": f"@{name}", "tickets": 1 + extra}
    else:
        participants[key]['tickets'] += extra

    await update.message.reply_text(f"✅ {participants[key]['display']} total tickets: {participants[key]['tickets']}")

# /removeticket @name N  (admin)
async def removeticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can remove tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /removeticket @username <number>")
        return

    name = normalize_arg_name(context.args[0])
    try:
        remove = int(context.args[1])
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    key = find_participant_key_by_name(name)
    if key is None:
        await update.message.reply_text("ℹ️ That user is not in the draw.")
        return

    participants[key]['tickets'] = max(1, participants[key]['tickets'] - remove)
    await update.message.reply_text(f"✅ {participants[key]['display']} total tickets: {participants[key]['tickets']}")

# /setticket @name N  (admin)
async def setticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can set tickets.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Usage: /setticket @username <number>")
        return

    name = normalize_arg_name(context.args[0])
    try:
        count = int(context.args[1])
        if count < 1:
            count = 1
    except:
        await update.message.reply_text("⚠️ Ticket number must be an integer.")
        return

    key = find_participant_key_by_name(name)
    if key is None:
        key = f"@{name}"
        participants[key] = {"display": f"@{name}", "tickets": count}
    else:
        participants[key]['tickets'] = count

    await update.message.reply_text(f"✅ {participants[key]['display']}'s tickets set to {participants[key]['tickets']}")

# /draw (admin only) -> picks winners and exports CSV + appends to history
async def draw_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global participants, draw_number

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can end the draw.")
        return

    pool = []
    for k, v in participants.items():
        pool.extend([k] * v['tickets'])

    if not pool:
        await update.message.reply_text("⚠️ No participants to draw from.")
        return

    draw_number += 1
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    random.shuffle(pool)

    winners = []
    for entry in pool:
        if len(winners) >= winner_count:
            break
        if entry not in winners:
            winners.append(entry)

    winner_displays = [participants[w]['display'] for w in winners]
    await update.message.reply_text(
        f"🏆 Lucky Draw #{draw_number} Results\n📅 {now}\n👑 Winners: {', '.join(winner_displays)}"
    )

    # write per-draw CSV
    filename = f"draw_{draw_number}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Draw Number", "Timestamp", "Username", "Tickets", "Winner?"])
        for k, v in participants.items():
            writer.writerow([draw_number, now, v['display'], v['tickets'], "YES" if k in winners else "NO"])

    # send CSV file
    await update.message.reply_document(document=InputFile(filename))
    os.remove(filename)

    # append to history
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        for k, v in participants.items():
            writer.writerow([draw_number, now, v['display'], v['tickets'], "YES" if k in winners else "NO"])

    participants = {}  # reset for next round

# /history (admin only) -> download master history file
async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Only admins can request history.")
        return
    if os.path.exists(HISTORY_FILE):
        await update.message.reply_document(document=InputFile(HISTORY_FILE))
    else:
        await update.message.reply_text("⚠️ No history file found.")

# -----------------------
# App & Handlers registration
# -----------------------
def main():
    app = Application.builder().token(TOKEN).build()

    # basic commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("enter", enter_cmd))
    app.add_handler(CommandHandler("newdraw", newdraw))
    app.add_handler(CommandHandler("participants", participants_list))
    app.add_handler(CommandHandler("addticket", addticket))
    app.add_handler(CommandHandler("removeticket", removeticket))
    app.add_handler(CommandHandler("setticket", setticket))
    app.add_handler(CommandHandler("draw", draw_cmd))
    app.add_handler(CommandHandler("history", history_cmd))

    # button callback (pattern ^enter$)
    app.add_handler(CallbackQueryHandler(button_click, pattern="^enter$"))

    # debug message so Render logs show the bot is ready
    print("✅ Evon77bot connected to Telegram and is now running!")

    app.run_polling()

if __name__ == "_main_":
    main()


