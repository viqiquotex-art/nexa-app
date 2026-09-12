import os
import sqlite3
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "nexa_bot.db"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN belum diatur sebagai environment variable")


def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        full_name TEXT NOT NULL,
        date TEXT NOT NULL,
        check_in TEXT,
        check_out TEXT,
        UNIQUE(telegram_id, date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        price TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )""")
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            [
                ("Nexa Digital", "Produk digital Nexa", "Hubungi admin"),
                ("Nexa Template", "Template siap pakai", "Hubungi admin"),
                ("Nexa Service", "Jasa dan layanan Nexa", "Hubungi admin"),
            ],
        )
    conn.commit()
    conn.close()


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕐 Absensi", callback_data="attendance")],
        [InlineKeyboardButton("🛒 Toko Nexa", callback_data="shop")],
        [InlineKeyboardButton("👤 Profil", callback_data="profile")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")],
    ])


def attendance_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Check In", callback_data="check_in"), InlineKeyboardButton("🔴 Check Out", callback_data="check_out")],
        [InlineKeyboardButton("📋 Riwayat Hari Ini", callback_data="history")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Halo, {user.first_name}!\n\nSelamat datang di *NexaAssistantBot*.\n\nPilih layanan yang kamu butuhkan:",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = query.data

    if action == "home":
        await query.edit_message_text("🏠 *Menu Utama*\n\nSilakan pilih layanan:", parse_mode="Markdown", reply_markup=main_menu())
        return

    if action == "attendance":
        await query.edit_message_text("🕐 *Menu Absensi*\n\nPilih tindakan:", parse_mode="Markdown", reply_markup=attendance_menu())
        return

    if action in ("check_in", "check_out"):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        clock = now.strftime("%H:%M:%S")
        full_name = user.full_name
        conn = db()
        row = conn.execute("SELECT * FROM attendance WHERE telegram_id=? AND date=?", (user.id, today)).fetchone()

        if action == "check_in":
            if row and row["check_in"]:
                msg = f"⚠️ Kamu sudah *Check In* hari ini pada {row['check_in']}."
            elif row:
                conn.execute("UPDATE attendance SET check_in=?, full_name=? WHERE telegram_id=? AND date=?", (clock, full_name, user.id, today))
                conn.commit()
                msg = f"✅ *Check In berhasil!*\n\nNama: {full_name}\nTanggal: {today}\nJam: {clock}"
            else:
                conn.execute("INSERT INTO attendance (telegram_id, full_name, date, check_in) VALUES (?, ?, ?, ?)", (user.id, full_name, today, clock))
                conn.commit()
                msg = f"✅ *Check In berhasil!*\n\nNama: {full_name}\nTanggal: {today}\nJam: {clock}"
        else:
            if not row or not row["check_in"]:
                msg = "⚠️ Kamu belum melakukan *Check In* hari ini."
            elif row["check_out"]:
                msg = f"⚠️ Kamu sudah *Check Out* hari ini pada {row['check_out']}."
            else:
                conn.execute("UPDATE attendance SET check_out=? WHERE telegram_id=? AND date=?", (clock, user.id, today))
                conn.commit()
                msg = f"🔴 *Check Out berhasil!*\n\nNama: {full_name}\nTanggal: {today}\nJam: {clock}"
        conn.close()
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=attendance_menu())
        return

    if action == "history":
        today = datetime.now().strftime("%Y-%m-%d")
        conn = db()
        row = conn.execute("SELECT * FROM attendance WHERE telegram_id=? AND date=?", (user.id, today)).fetchone()
        conn.close()
        if not row:
            text = "📋 *Riwayat Hari Ini*\n\nBelum ada data absensi."
        else:
            text = f"📋 *Riwayat Hari Ini*\n\nTanggal: {today}\n🟢 Check In: {row['check_in'] or '-'}\n🔴 Check Out: {row['check_out'] or '-'}"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=attendance_menu())
        return

    if action == "shop":
        conn = db()
        products = conn.execute("SELECT * FROM products WHERE active=1 ORDER BY id").fetchall()
        conn.close()
        text = "🛒 *Toko Nexa*\n\n"
        for p in products:
            text += f"*{p['name']}*\n{p['description']}\n💰 {p['price']}\n\n"
        text += "Untuk pemesanan, lanjutkan melalui admin Nexa."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")]]))
        return

    if action == "profile":
        username = f"@{user.username}" if user.username else "-"
        text = f"👤 *Profil*\n\nNama: {user.full_name}\nUsername: {username}\nTelegram ID: `{user.id}`"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")]]))
        return

    if action == "help":
        text = "ℹ️ *Bantuan*\n\n🕐 Absensi — Check In, Check Out, dan riwayat.\n🛒 Toko Nexa — Melihat produk Nexa.\n👤 Profil — Melihat data akun Telegram.\n\nVersi awal NexaAssistantBot."
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")]]))


if __name__ == "__main__":
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    print("NexaAssistantBot berjalan...")
    app.run_polling()
