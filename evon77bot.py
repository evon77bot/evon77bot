# evon77bot.py
# Evon77Bot v2 - in-memory mode, spinning wheel PNG per winner, scheduled draws, bonus tickets (admin toggles)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import os, random, csv, asyncio, json
from datetime import datetime, date, time as dtime, timedelta
from PIL import Image, ImageDraw, ImageFont

# ----------------- Config (environment toggles) -----------------
TOKEN = os.getenv("BOT_TOKEN")  # required
# If REQUIRE_MEMBERSHIP env var set to "True" (case-ins) then membership is enforced:
REQUIRE_MEMBERSHIP = os.getenv("REQUIRE_MEMBERSHIP", "False").lower() == "true"
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "")  # without '@'

# Wheel image settings
WHEEL_SIZE = (600, 600)
WHEEL_SEGMENTS = 12  # visual segments (doesn't map to names)
WHEEL_COLORS = [
    (239, 71, 111), (255, 209, 102), (6, 214, 160), (17, 138, 178),
    (7, 59, 76), (255, 99, 72), (255, 159, 67), (66, 135, 245),
    (123, 104, 238), (255, 127, 80), (46, 204, 113), (255, 204, 153)
]

# ----------------- In-memory state -----------------
participants = {}  # user_id (str) -> {"username": str, "tickets": int, "wins": int}
history_rows = []  # list of (draw_number, timestamp, prize, winners_list)
draw_counter = 0
bonus_enabled = False
bonus_chance = 0.15
bonus_min = 2
bonus_max = 3

scheduled_tasks = []  # keeps info about scheduled draws for display (not persistent)

# Runtime CSV filename (runtime-only; wiped on redeploy)
HISTORY_CSV = "draw_history_runtime.csv"

# ensure CSV header
if not os.path.exists(HISTORY_CSV):
    with open(HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Draw#", "Timestamp", "Prize", "Winners"])

# ----------------- Utilities -----------------
def save_history_row(draw_no, prize, winners):
    ts = datetime.now().isoformat()
    history_rows.append((draw_no, ts, prize, winners.copy()))
    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([draw_no, ts, prize or "-", ", ".join(winners)])

def save_participants_snapshot():  # not persistent intentionally; helper if you want to inspect
    try:
        with open("participants_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(participants, f, indent=2)
    except:
        pass

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in ("administrator", "creator")
    except:
        return False

# simple wheel PNG generator (colorful segments, pointer at top). Returns filepath.
def generate_wheel_png(out_path, highlight_index=None, segments=WHEEL_SEGMENTS, size=WHEEL_SIZE):
    w, h = size
    cx, cy = w//2, h//2
    r = int(min(cx, cy)*0.9)
    im = Image.new("RGB", (w, h), (24,24,24))
    draw = ImageDraw.Draw(im)
    # font (default)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except:
        font = ImageFont.load_default()

    # draw segments
    angle_per = 360.0 / segments
    start_angle = -90  # pointer at top
    for i in range(segments):
        color = WHEEL_COLORS[i % len(WHEEL_COLORS)]
        a0 = start_angle + i*angle_per
        a1 = a0 + angle_per
        draw.pieslice([cx-r, cy-r, cx+r, cy+r], a0, a1, fill=color)
        # optional small segment border
        draw.arc([cx-r, cy-r, cx+r, cy+r], a0, a1, fill=(20,20,20))

    # draw center circle
    draw.ellipse([cx-80, cy-80, cx+80, cy+80], fill=(20,20,20))
    # pointer triangle at top
    tri = [(cx-12, cy-r-10), (cx+12, cy-r-10), (cx, cy-r+20)]
    draw.polygon(tri, fill=(255,255,255))

    # highlight segment if provided (draw outer border)
    if highlight_index is not None:
        a0 = start_angle + highlight_index*angle_per
        a1 = a0 + angle_per
        draw.pieslice([cx-r-6, cy-r-6, cx+r+6, cy+r+6], a0, a1, outline=(255,255,255), width=6)

    # footer text
    draw.text((10, h-30), "Evon77 Lucky Draw", fill=(200,200,200), font=font)

    im.save(out_path, format="PNG")
    return out_path

# ----------------- Handlers -----------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎟 Enter Draw", callback_data="enter_draw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎉 Welcome! Click to join the current lucky draw (button stays visible until admin runs the draw).", reply_markup=reply_markup)

# Allow both callback button and /enter command
async def enter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # supports both CallbackQuery and Command
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
        await query.answer()  # close loading state
        chat = query.message.chat
        origin = "callback"
    else:
        user = update.effective_user
        chat = update.effective_chat
        origin = "command"

    uid = str(user.id)
    username = user.username or (user.full_name if hasattr(user, "full_name") else user.first_name)

    # membership check if enabled (uses env var)
    if REQUIRE_MEMBERSHIP and REQUIRED_CHANNEL:
        try:
            member = await context.bot.get_chat_member(f"@{REQUIRED_CHANNEL}", user.id)
            if member.status not in ("member","administrator","creator"):
                if origin == "callback":
                    await query.message.reply_text("⚠️ You must join the required channel/group before entering.")
                else:
                    await update.message.reply_text("⚠️ You must join the required channel/group before entering.")
                return
        except Exception:
            # could not verify
            if origin == "callback":
                await query.message.reply_text("⚠️ Could not verify membership. Please ensure the bot can access the channel.")
            else:
                await update.message.reply_text("⚠️ Could not verify membership. Please ensure the bot can access the channel.")
            return

    if uid in participants:
        msg = f"⚠️ {username}, you already joined (tickets: {participants[uid]['tickets']}). Ask admin for more tickets."
        if origin == "callback":
            await query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    # base ticket
    tickets = 1
    note = ""
    if bonus_enabled:
        if random.random() < bonus_chance:
            bonus = random.randint(bonus_min, bonus_max)
            tickets += bonus
            note = f" (bonus +{bonus})"

    participants[uid] = {"username": username, "tickets": tickets, "wins": 0}
    save_participants_snapshot()
    msg = f"✅ {username} entered with {tickets} ticket(s){note}."
    if origin == "callback":
        await query.message.reply_text(msg)
    else:
        await update.message.reply_text(msg)

# admin: list participants
async def participants_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ This command is for admins only.")
        return
    if not participants:
        await update.message.reply_text("📭 No participants yet.")
        return
    lines = ["📋 Participants:"]
    for info in participants.values():
        lines.append(f"- {info['username']}: {info['tickets']} ticket(s)")
    await update.message.reply_text("\n".join(lines))

# admin: add tickets
async def addtickets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addtickets @username N")
        return
    name = context.args[0].lstrip("@")
    try:
        n = int(context.args[1])
    except:
        await update.message.reply_text("Ticket count must be a number.")
        return
    for uid, info in participants.items():
        if info["username"].lstrip("@").lower() == name.lower():
            info["tickets"] += n
            save_participants_snapshot()
            await update.message.reply_text(f"✅ Added {n} tickets to {info['username']}. Now {info['tickets']}.")
            return
    await update.message.reply_text("User not found. They must enter first.")

# admin: reset user's tickets to 1
async def resettickets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /resettickets @username")
        return
    name = context.args[0].lstrip("@")
    for uid, info in participants.items():
        if info["username"].lstrip("@").lower() == name.lower():
            info["tickets"] = 1
            save_participants_snapshot()
            await update.message.reply_text(f"✅ Reset {info['username']}'s tickets to 1.")
            return
    await update.message.reply_text("User not found.")

# draw command: /draw [N] [Prize words...]
async def draw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global draw_counter
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if not participants:
        await update.message.reply_text("No participants.")
        return

    # parse args
    num = 1
    prize = ""
    if context.args:
        if context.args[0].isdigit():
            num = max(1, int(context.args[0]))
            prize = " ".join(context.args[1:]).strip()
        else:
            prize = " ".join(context.args).strip()

    # build ticket pool
    pool = []
    for uid, info in participants.items():
        pool.extend([info["username"]] * int(info["tickets"]))

    total_participants = len(participants)
    total_tickets = len(pool)
    winners = []
    if pool:
        shuffled = pool.copy()
        random.shuffle(shuffled)
        for name in shuffled:
            if name not in winners:
                winners.append(name)
            if len(winners) >= min(num, len(set(pool))):
                break

    draw_counter += 1
    save_history_row(draw_counter, prize, winners)

    # For each winner: generate PNG wheel, send it, then announce the winner
    # Visual wheel has segments but not mapped to names; it's just for show.
    for idx, winner in enumerate(winners, start=1):
        # pick a random segment to highlight (visual)
        seg_index = random.randrange(0, WHEEL_SEGMENTS)
        png_path = f"wheel_{draw_counter}_{idx}.png"
        try:
            generate_wheel_png(png_path, highlight_index=seg_index, segments=WHEEL_SEGMENTS, size=WHEEL_SIZE)
            await update.message.reply_photo(InputFile(png_path), caption=f"🎡 Spinning for winner #{idx}...")
        except Exception:
            await update.message.reply_text("🎰 Spinning...")

        # small pause for drama
        await asyncio.sleep(1.2)
        # announce winner (with prize if provided)
        if prize:
            await update.message.reply_text(f"🏆 Winner #{idx} — {winner} — Prize: *{prize}*", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"🏆 Winner #{idx} — {winner}")

        # increment winner count in memory
        for uid, info in participants.items():
            if info["username"] == winner:
                info["wins"] = info.get("wins", 0) + 1

        # cleanup generated png
        try:
            if os.path.exists(png_path):
                os.remove(png_path)
        except:
            pass

    # final summary
    summary = [f"🎉 Lucky Draw #{draw_counter}"]
    if prize:
        summary.append(f"🎁 Prize: {prize}")
    summary.append(f"👥 Participants: {total_participants}")
    summary.append(f"🎟 Total Tickets: {total_tickets}")
    summary.append("🏁 Winners:")
    summary.extend([f"- {w}" for w in winners])
    await update.message.reply_text("\n".join(summary))

    # after draw: clear participants for next round
    participants.clear()

# schedule: /schedule HH:MM N Prize min=X
async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /schedule HH:MM N Prize words... [min=X]")
        return
    time_str = context.args[0]
    try:
        hh, mm = time_str.split(":")
        hh = int(hh); mm = int(mm)
        target_time = dtime(hh, mm)
    except:
        await update.message.reply_text("Invalid time. Use HH:MM (24h).")
        return
    try:
        num = int(context.args[1])
    except:
        await update.message.reply_text("Provide number of winners N.")
        return

    # parse min= token in rest
    minp = 1
    prize_parts = []
    for tok in context.args[2:]:
        if tok.startswith("min="):
            try:
                minp = int(tok.split("=",1)[1])
            except:
                pass
        else:
            prize_parts.append(tok)
    prize = " ".join(prize_parts).strip()

    # compute next occurrence of target_time (server time)
    now = datetime.now()
    dt_target = datetime.combine(now.date(), target_time)
    if dt_target <= now:
        dt_target += timedelta(days=1)
    delay = (dt_target - now).total_seconds()

    async def job():
        await asyncio.sleep(delay)
        if len(participants) < minp:
            await update.message.reply_text(f"Scheduled draw canceled: need at least {minp} participants (now {len(participants)}).")
            return
        # simulate admin calling /draw with args
        class Ctx: pass
        ctx = Ctx()
        ctx.args = [str(num)] + ([prize] if prize else [])
        # call draw_handler directly (reuse)
        await draw_handler(update, type("obj", (), {"args": ctx.args}))

    task = asyncio.create_task(job())
    scheduled_tasks.append({"time": time_str, "num": num, "prize": prize or "-", "min": minp})
    await update.message.reply_text(f"✅ Scheduled draw at {time_str} for prize '{prize or '-'}' (min {minp}).")

# bonus toggle: /bonus on|off
async def bonus_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bonus_enabled
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /bonus on OR /bonus off")
        return
    a = context.args[0].lower()
    if a in ("on","true","1"):
        bonus_enabled = True
        await update.message.reply_text("✅ Bonus tickets enabled.")
    else:
        bonus_enabled = False
        await update.message.reply_text("✅ Bonus tickets disabled.")

# stats
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_draws = len(history_rows)
    cur_participants = len(participants)
    total_tickets = sum(info["tickets"] for info in participants.values()) if participants else 0
    top_winners = sorted(((info.get("wins",0), info["username"]) for info in participants.values()), reverse=True)[:5]
    top_participants = sorted(((info["tickets"], info["username"]) for info in participants.values()), reverse=True)[:5]
    lines = [f"📊 Stats:",
             f"- Draws this session: {total_draws}",
             f"- Current participants: {cur_participants}",
             f"- Current total tickets: {total_tickets}",
             "",
             "🏆 Top winners (current session):"]
    for wins, name in top_winners:
        if wins>0:
            lines.append(f"- {name}: {wins} win(s)")
    lines.append("")
    lines.append("🎟 Top ticket holders:")
    for t, name in top_participants:
        lines.append(f"- {name}: {t} tickets")
    await update.message.reply_text("\n".join(lines))

# history (last N) and export
async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = 10
    if context.args and context.args[0].isdigit():
        n = int(context.args[0])
    if not history_rows:
        await update.message.reply_text("No history this session.")
        return
    lines = [f"📜 Draw history (last {n}):"]
    for row in history_rows[-n:]:
        lines.append(f"- #{row[0]} {row[1]} Prize: {row[2]} Winners: {', '.join(row[3])}")
    await update.message.reply_text("\n".join(lines))

async def export_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if os.path.exists(HISTORY_CSV):
        await update.message.reply_document(InputFile(HISTORY_CSV), caption="Full draw history (this session)")
    else:
        await update.message.reply_text("No history file available.")

# config display and quick changes: /config, /require on/off, /setchannel name
async def config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    txt = f"⚙️ Current config:\n- Require membership: {'✅' if REQUIRE_MEMBERSHIP else '❌'}\n- Required channel: @{REQUIRED_CHANNEL if REQUIRED_CHANNEL else '(none)'}\n- Bonus enabled: {'✅' if bonus_enabled else '❌'}"
    await update.message.reply_text(txt)

async def require_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global REQUIRE_MEMBERSHIP
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /require on OR /require off")
        return
    a = context.args[0].lower()
    REQUIRE_MEMBERSHIP = a in ("on","true","1")
    await update.message.reply_text(f"✅ Require membership set to {REQUIRE_MEMBERSHIP}")

async def setchannel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global REQUIRED_CHANNEL
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setchannel ChannelName (without @)")
        return
    REQUIRED_CHANNEL = context.args[0].lstrip("@")
    await update.message.reply_text(f"✅ Required channel set to @{REQUIRED_CHANNEL}")

# clear participants
async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Admins only.")
        return
    participants.clear()
    await update.message.reply_text("✅ Participants cleared.")

# help
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        text = (
            "Admin commands:\n"
            "/start - show join button\n"
            "/draw [N] [Prize] - draw N winners\n"
            "/schedule HH:MM N Prize min=X - schedule next draw\n"
            "/participants - list participants\n"
            "/addtickets @name N\n"
            "/resettickets @name\n"
            "/bonus on|off\n"
            "/stats\n"
            "/history [N]\n"
            "/export\n"
            "/require on|off\n"
            "/setchannel name\n"
            "/clear\n"
        )
    else:
        text = "User commands:\n/start - show join button\n/help - this message\n(enter via button or /enter)"
    await update.message.reply_text(text)

# ----------------- Main -----------------
def main():
    if not TOKEN:
        print("ERROR: BOT_TOKEN env var not set.")
        return

    app = Appli
