import os
import random
import csv
from datetime import datetime, time
import asyncio
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [123456789]  # 👈 Replace with your Telegram user ID(s)

participants = {}   # user_id → {"username": str, "tickets": int, "wins": int}
bonus_enabled = False
draw_number = 0

HISTORY_FILE = "history.csv"


# =========================
# HELPERS
# =========================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def save_history(prize: str, winners: list[str]):
    global draw_number
    draw_number += 1
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([draw_number, prize, ", ".join(winners), datetime.now().isoformat()])

def make_wheel_image():
    # Colorful wheel PNG (no names, just slices)
    num_slices = 12
    colors = plt.cm.tab20.colors
    wedges = np.ones(num_slices)

    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw={'aspect': 'equal'})
    ax.pie(wedges, colors=random.sample(colors, num_slices))
    ax.add_artist(plt.Circle((0, 0), 0.1, color="white"))

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        keyboard = [[InlineKeyboardButton("🎟 Enter the Draw", callback_data="enter_draw")]]
        await update.message.reply_text(
            "🎉 Welcome to Evon77 Lucky Draw! Click below to join:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("Use me inside the group to join draws!")

async def enter_draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    username = user.username or user.full_name

    # Give bonus randomly if enabled
    tickets = 1
    if bonus_enabled and random.random() < 0.3:  # 30% chance
        tickets += random.randint(1, 2)

    if user_id not in participants:
        participants[user_id] = {"username": username, "tickets": tickets, "wins": 0}
    else:
        participants[user_id]["tickets"] += tickets

    await query.answer("You're in the draw!")
    await query.message.reply_text(f"✅ {username} joined with {tickets} ticket(s)!")

async def draw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Admins only!")

    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /draw <count> <prize>")

    try:
        count = int(context.args[0])
        prize = " ".join(context.args[1:])
    except ValueError:
        return await update.message.reply_text("Invalid number of winners.")

    if not participants:
        return await update.message.reply_text("No participants yet!")

    winners = []
    for i in range(count):
        pool = []
        for user_id, info in participants.items():
            pool.extend([user_id] * info["tickets"])
        if not pool:
            break
        winner_id = random.choice(pool)
        winners.append(participants[winner_id]["username"])
        participants[winner_id]["wins"] += 1
        participants[winner_id]["tickets"] = 0  # remove tickets

        # Wheel PNG
        buf = make_wheel_image()
        await update.message.reply_photo(photo=InputFile(buf, "wheel.png"))
        await update.message.reply_text(f"🏆 Winner {i+1}: @{participants[winner_id]['username']} ({prize})")

    save_history(prize, winners)

    # Auto-clear after draw
    participants.clear()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Admins only!")

    if not participants:
        return await update.message.reply_text("No participants yet!")

    total_tickets = sum(p["tickets"] for p in participants.values())
    top_users = sorted(participants.values(), key=lambda x: x["wins"], reverse=True)[:3]
    stats_text = (
        f"📊 Stats\n"
        f"Total participants: {len(participants)}\n"
        f"Total tickets: {total_tickets}\n"
        f"Top winners: {', '.join(u['username'] for u in top_users)}"
    )
    await update.message.reply_text(stats_text)

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bonus_enabled
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Admins only!")

    if not context.args:
        return await update.message.reply_text(f"Bonus is {'ON' if bonus_enabled else 'OFF'}")

    if context.args[0].lower() == "on":
        bonus_enabled = True
        await update.message.reply_text("🎁 Bonus tickets ENABLED")
    else:
        bonus_enabled = False
        await update.message.reply_text("🎁 Bonus tickets DISABLED")


# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(enter_draw, pattern="enter_draw"))
    app.add_handler(CommandHandler("draw", draw))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("bonus", bonus))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
