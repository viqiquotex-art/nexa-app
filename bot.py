import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "nexa_bot.db"
WIB = ZoneInfo("Asia/Jakarta")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN belum diatur sebagai environment variable")


def now_wib():
    return datetime.now(WIB)


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
        npk TEXT,
        date TEXT NOT NULL,
        check_in TEXT,
        check_out TEXT,
        UNIQUE(telegram_id, date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        username TEXT,
        npk TEXT,
        registered_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        price TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )""")

    # Upgrade database lama tanpa menghapus data absensi.
    columns = [r[1] for r in conn.execute("PRAGMA table_info(attendance)").fetchall()]
    if "npk" not in columns:
        conn.execute("ALTER TABLE attendance ADD COLUMN npk TEXT")

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
        [
            InlineKeyboardButton("🟢 Check In", callback_data="check_in"),
            InlineKeyboardButton("🔴 Check Out", callback_data="check_out"),
        ],
        [InlineKeyboardButton("📋 Riwayat Hari Ini", callback_data="history")],
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")],
    ])


def back_home_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Menu Utama", callback_data="home")]
    ])


def get_user(telegram_id):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return row


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    registered = get_user(user.id)
    extra = ""
    if not registered:
        extra = "\n\n⚠️ Kamu belum mendaftarkan NPK.\nGunakan:\n`/daftar NPK_KAMU`"
    await update.message.reply_text(
        f"👋 Halo, {user.first_name}!\n\nSelamat datang di *NexaAssistantBot*.\n\nPilih layanan yang kamu butuhkan:{extra}",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text(
            "📝 *Pendaftaran NPK*\n\nFormat:\n`/daftar NPK_KAMU`\n\nContoh:\n`/daftar 12345678`",
            parse_mode="Markdown",
        )
        return

    npk = context.args[0].strip()
    if len(npk) > 50:
        await update.message.reply_text("⚠️ NPK terlalu panjang. Silakan periksa kembali.")
        return

    now = now_wib().strftime("%Y-%m-%d %H:%M:%S")
    conn = db()
    conn.execute(
        """INSERT INTO users (telegram_id, full_name, username, npk, registered_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET
           full_name=excluded.full_name,
           username=excluded.username,
           npk=excluded.npk""",
        (user.id, user.full_name, user.username, npk, now),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ *Pendaftaran berhasil!*\n\nNama: {user.full_name}\nNPK: `{npk}`\n\nSekarang kamu sudah bisa melakukan absensi.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = query.data

    if action == "home":
        await query.edit_message_text(
            "🏠 *Menu Utama*\n\nSilakan pilih layanan:",
            parse_mode="Markdown",
            reply_markup=main_menu(),
        )
        return

    if action == "attendance":
        registered = get_user(user.id)
        if not registered:
            await query.edit_message_text(
                "⚠️ *NPK belum terdaftar*\n\nSilakan kirim:\n`/daftar NPK_KAMU`\n\nSetelah itu kamu bisa melakukan Check In/Out.",
                parse_mode="Markdown",
                reply_markup=back_home_menu(),
            )
            return
        await query.edit_message_text(
            f"🕐 *Menu Absensi*\n\nNPK: `{registered['npk']}`\nNama: {registered['full_name']}\n\nPilih tindakan:",
            parse_mode="Markdown",
            reply_markup=attendance_menu(),
        )
        return

    if action in ("check_in", "check_out"):
        registered = get_user(user.id)
        if not registered:
            await query.edit_message_text(
                "⚠️ NPK belum terdaftar.\n\nGunakan `/daftar NPK_KAMU` terlebih dahulu.",
                parse_mode="Markdown",
                reply_markup=back_home_menu(),
            )
            return

        now = now_wib()
        today = now.strftime("%Y-%m-%d")
        clock = now.strftime("%H:%M:%S")
        full_name = registered["full_name"]
        npk = registered["npk"]

        conn = db()
        row = conn.execute(
            "SELECT * FROM attendance WHERE telegram_id=? AND date=?",
            (user.id, today),
        ).fetchone()

        if action == "check_in":
            if row and row["check_in"]:
                msg = f"⚠️ Kamu sudah *Check In* hari ini pada {row['check_in']}."
            elif row:
                conn.execute(
                    "UPDATE attendance SET check_in=?, full_name=?, npk=? WHERE telegram_id=? AND date=?",
                    (clock, full_name, npk, user.id, today),
                )
                conn.commit()
                msg = f"✅ *Check In berhasil!*\n\nNama: {full_name}\nNPK: `{npk}`\nTanggal: {today}\nJam: {clock}"
            else:
                conn.execute(
                    "INSERT INTO attendance (telegram_id, full_name, npk, date, check_in) VALUES (?, ?, ?, ?, ?)",
                    (user.id, full_name, npk, today, clock),
                )
                conn.commit()
                msg = f"✅ *Check In berhasil!*\n\nNama: {full_name}\nNPK: `{npk}`\nTanggal: {today}\nJam: {clock}"
        else:
            if not row or not row["check_in"]:
                msg = "⚠️ Kamu belum melakukan *Check In* hari ini."
            elif row["check_out"]:
                msg = f"⚠️ Kamu sudah *Check Out* hari ini pada {row['check_out']}."
            else:
                conn.execute(
                    "UPDATE attendance SET check_out=? WHERE telegram_id=? AND date=?",
                    (clock, user.id, today),
                )
                conn.commit()
                msg = f"🔴 *Check Out berhasil!*\n\nNama: {full_name}\nNPK: `{npk}`\nTanggal: {today}\nJam: {clock}"
        conn.close()
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=attendance_menu())
        return

    if action == "history":
        today = now_wib().strftime("%Y-%m-%d")
        conn = db()
        row = conn.execute(
            "SELECT * FROM attendance WHERE telegram_id=? AND date=?",
            (user.id, today),
        ).fetchone()
        conn.close()
        if not row:
            text = "📋 *Riwayat Hari Ini*\n\nBelum ada data absensi."
        else:
            text = (
                f"📋 *Riwayat Hari Ini*\n\n"
                f"Tanggal: {today}\n"
                f"NPK: `{row['npk'] or '-'}'`\n"
                f"🟢 Check In: {row['check_in'] or '-'}\n"
                f"🔴 Check Out: {row['check_out'] or '-'}"
            ).replace("`'`", "`")
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
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_home_menu())
        return

    if action == "profile":
        registered = get_user(user.id)
        username = f"@{user.username}" if user.username else "-"
        npk = registered["npk"] if registered else "Belum terdaftar"
        text = f"👤 *Profil*\n\nNama: {user.full_name}\nUsername: {username}\nNPK: `{npk}`\nTelegram ID: `{user.id}`"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_home_menu())
        return

    if action == "help":
        text = (
            "ℹ️ *Bantuan*\n\n"
            "📝 `/daftar NPK` — Mendaftarkan NPK.\n"
            "🕐 Absensi — Check In, Check Out, dan riwayat.\n"
            "🛒 Toko Nexa — Melihat produk Nexa.\n"
            "👤 Profil — Melihat data akun Telegram.\n\n"
            "Versi *NexaAssistantBot Attendance v2*."
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_home_menu())


if __name__ == "__main__":
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daftar", daftar))
    app.add_handler(CallbackQueryHandler(button))
    print("NexaAssistantBot berjalan dalam WIB...")
    app.run_polling()
