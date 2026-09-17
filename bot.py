import json
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("BOT_TOKEN")
NEXA_AI_URL = os.getenv("NEXA_AI_URL", "").strip()
NEXA_AI_SECRET = os.getenv("NEXA_AI_SECRET", "").strip()
DB_NAME = os.getenv("NEXA_DB", "nexa_bot.db")
WIB = ZoneInfo("Asia/Jakarta")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN belum diatur sebagai environment variable")


def db():
    c = sqlite3.connect(DB_NAME)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
      title TEXT NOT NULL, description TEXT, deadline TEXT,
      priority TEXT DEFAULT 'medium', status TEXT DEFAULT 'pending', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expenses (
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
      amount INTEGER NOT NULL, category TEXT DEFAULT 'Lainnya', note TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS goals (
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
      title TEXT NOT NULL, target_amount INTEGER, saved_amount INTEGER DEFAULT 0,
      deadline TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL,
      content TEXT NOT NULL, created_at TEXT NOT NULL
    );
    """)
    c.commit(); c.close()


def menu():
    return InlineKeyboardMarkup([
      [InlineKeyboardButton("🧠 Tanya NEXA", callback_data="ask")],
      [InlineKeyboardButton("✅ Tasks", callback_data="tasks"), InlineKeyboardButton("💰 Finance", callback_data="finance")],
      [InlineKeyboardButton("🎯 Goals", callback_data="goals"), InlineKeyboardButton("📝 Notes", callback_data="notes")],
      [InlineKeyboardButton("📊 Hari Ini", callback_data="today"), InlineKeyboardButton("💎 Premium", callback_data="premium")],
    ])


def back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")]])


def money(n):
    try: return "Rp{:,.0f}".format(float(n)).replace(",", ".")
    except (ValueError, TypeError): return str(n)


async def ai(update, text):
    if not NEXA_AI_URL:
        return None
    u = update.effective_user
    payload = {
      "message": text, "text": text, "userId": str(u.id),
      "telegram_id": u.id, "channel": "telegram",
      "user": {"id": str(u.id), "name": u.full_name, "username": u.username}
    }
    headers = {"Content-Type": "application/json"}
    if NEXA_AI_SECRET: headers["x-nexa-bot-secret"] = NEXA_AI_SECRET
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(NEXA_AI_URL, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"NEXA AI error: {e}")
        return None


def unpack(result):
    if not isinstance(result, dict): return "chat", {}, str(result)
    if isinstance(result.get("result"), dict): result = result["result"]
    action = result.get("action") or result.get("intent") or "chat"
    data = result.get("data") or result.get("params") or result.get("arguments") or {}
    reply = result.get("reply") or result.get("message") or result.get("response") or ""
    return action, data if isinstance(data, dict) else {}, str(reply)


def add_task(uid, data, fallback):
    title = data.get("title") or data.get("task") or fallback
    c = db(); cur = c.execute(
      "INSERT INTO tasks (telegram_id,title,description,deadline,priority,created_at) VALUES (?,?,?,?,?,?)",
      (uid, title, data.get("description"), data.get("deadline"), data.get("priority", "medium"), datetime.now(WIB).isoformat()))
    c.commit(); i = cur.lastrowid; c.close(); return i


def add_expense(uid, data):
    raw = data.get("amount") or data.get("nominal")
    if raw is None: return None
    try: amount = int(float(str(raw).replace(".", "").replace(",", "")))
    except ValueError: return None
    c = db(); cur = c.execute(
      "INSERT INTO expenses (telegram_id,amount,category,note,created_at) VALUES (?,?,?,?,?)",
      (uid, amount, data.get("category", "Lainnya"), data.get("note") or data.get("description"), datetime.now(WIB).isoformat()))
    c.commit(); i = cur.lastrowid; c.close(); return i, amount


def add_goal(uid, data):
    title = data.get("title") or data.get("goal")
    if not title: return None
    target = data.get("target_amount") or data.get("target")
    c = db(); cur = c.execute(
      "INSERT INTO goals (telegram_id,title,target_amount,deadline,created_at) VALUES (?,?,?,?,?)",
      (uid, title, int(target) if str(target).isdigit() else None, data.get("deadline"), datetime.now(WIB).isoformat()))
    c.commit(); i = cur.lastrowid; c.close(); return i


def add_note(uid, data, fallback):
    content = data.get("content") or data.get("text") or fallback
    c = db(); cur = c.execute(
      "INSERT INTO notes (telegram_id,content,created_at) VALUES (?,?,?)",
      (uid, content, datetime.now(WIB).isoformat()))
    c.commit(); i = cur.lastrowid; c.close(); return i


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
      "👋 Halo! Saya *NEXA*.\n\nYour life, organized by AI.\n\nKirim perintah dengan bahasa biasa:\n• `Buat task menyelesaikan laporan besok`\n• `Catat pengeluaran 25000 makan`\n• `Buat goal beli iPhone target 15000000`\n• `Simpan catatan ide aplikasi AI`",
      parse_mode="Markdown", reply_markup=menu())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
      "🧠 *NEXA memahami bahasa natural.*\n\nContoh:\n`Buat task upload website Jumat`\n`Catat pengeluaran 35 ribu transport`\n`Aku mau nabung 10 juta untuk laptop`\n`Simpan ide: bikin landing page AI`",
      parse_mode="Markdown", reply_markup=back())


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text: return
    await update.message.chat.send_action("typing")
    result = await ai(update, text)
    if result is not None:
        action, data, reply = unpack(result)
        uid = update.effective_user.id
        if action in ("create_task", "task"):
            i = add_task(uid, data, text)
            await update.message.reply_text(reply or f"✅ Task dibuat. ID #{i}"); return
        if action in ("create_expense", "expense"):
            created = add_expense(uid, data)
            if created:
                _, amount = created
                await update.message.reply_text(reply or f"💰 Pengeluaran {money(amount)} dicatat."); return
        if action in ("create_goal", "goal"):
            i = add_goal(uid, data)
            if i: await update.message.reply_text(reply or f"🎯 Goal dibuat. ID #{i}"); return
        if action in ("create_note", "note"):
            i = add_note(uid, data, text)
            await update.message.reply_text(reply or f"📝 Catatan tersimpan. ID #{i}"); return
        if reply:
            await update.message.reply_text(reply); return

    low = text.lower()
    if low.startswith(("buat task ", "buat tugas ", "task ")):
        i = add_task(update.effective_user.id, {}, text.split(" ", 2)[-1])
        await update.message.reply_text(f"✅ Task lokal dibuat. ID #{i}\n\nAI gateway belum aktif. Atur NEXA_AI_URL untuk pemahaman AI penuh.")
    else:
        await update.message.reply_text("🧠 Pesan diterima. AI NEXA belum terhubung di environment bot ini. Atur NEXA_AI_URL.", reply_markup=menu())


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = q.from_user.id; a = q.data
    if a == "home": await q.edit_message_text("🏠 *NEXA*\n\nYour life, organized by AI.", parse_mode="Markdown", reply_markup=menu()); return
    if a == "ask": await q.edit_message_text("🧠 *Tanya NEXA*\n\nKirim pesan apa pun di chat ini.", parse_mode="Markdown", reply_markup=back()); return
    c = db()
    if a == "tasks":
        rows = c.execute("SELECT id,title,deadline,priority FROM tasks WHERE telegram_id=? AND status!='done' ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        text = "✅ *Tasks Aktif*\n\n" + ("\n".join(f"• #{r['id']} {r['title']} — {r['priority']}" + (f" ({r['deadline']})" if r['deadline'] else "") for r in rows) if rows else "Belum ada task.")
    elif a == "finance":
        total = c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE telegram_id=?", (uid,)).fetchone()[0]
        rows = c.execute("SELECT amount,category,note FROM expenses WHERE telegram_id=? ORDER BY id DESC LIMIT 5", (uid,)).fetchall()
        text = "💰 *Finance*\n\nTotal tercatat: " + money(total) + "\n\n" + ("\n".join(f"• {money(r['amount'])} — {r['category']}" for r in rows) if rows else "Belum ada pengeluaran.")
    elif a == "goals":
        rows = c.execute("SELECT id,title,target_amount,saved_amount FROM goals WHERE telegram_id=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
        text = "🎯 *Goals*\n\n" + ("\n".join(f"• #{r['id']} {r['title']} — {money(r['saved_amount'])}/{money(r['target_amount']) if r['target_amount'] else '-'}" for r in rows) if rows else "Belum ada goal.")
    elif a == "notes":
        rows = c.execute("SELECT content FROM notes WHERE telegram_id=? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
        text = "📝 *Notes*\n\n" + ("\n".join(f"• {r['content']}" for r in rows) if rows else "Belum ada catatan.")
    elif a == "today":
        tasks = c.execute("SELECT COUNT(*) FROM tasks WHERE telegram_id=? AND status!='done'", (uid,)).fetchone()[0]
        expense = c.execute("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE telegram_id=? AND date(created_at)=date('now','localtime')", (uid,)).fetchone()[0]
        text = f"📊 *Hari Ini*\n\n✅ Task aktif: {tasks}\n💰 Pengeluaran hari ini: {money(expense)}"
    elif a == "premium":
        text = "💎 *NEXA Premium*\n\nSegera hadir: smart planning, recurring reminder, receipt OCR, calendar, voice-to-action, dan laporan keuangan."
    else: text = "NEXA siap membantu."
    c.close(); await q.edit_message_text(text, parse_mode="Markdown", reply_markup=back())


if __name__ == "__main__":
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("NEXA Telegram Assistant berjalan dalam WIB...")
    app.run_polling()
