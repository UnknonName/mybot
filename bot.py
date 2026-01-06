
from dotenv import load_dotenv
import os
from config import MAX_HISTORY

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

import time, sqlite3, json, logging, io
import matplotlib.pyplot as plt
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

DB = "memory.db"
ADMIN_ID = 123456789  # замени на свой Telegram ID

tariffs = {
    "lite":   {"price": 150,  "tokens_limit": 2000,  "photos_limit": 0},
    "pro":    {"price": 450,  "tokens_limit": 8000,  "photos_limit": 20},
    "vision": {"price": 1200, "tokens_limit": 20000, "photos_limit": 200},
}

# ----------------------- БАЗА ДАННЫХ -----------------------

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS memory (
        user_id TEXT PRIMARY KEY,
        plan TEXT DEFAULT 'lite',
        balance INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 20,
        tokens_used INTEGER DEFAULT 0,
        photos_used INTEGER DEFAULT 0,
        expenses INTEGER DEFAULT 0,
        subscription_until INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def ensure_user(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO memory (user_id) VALUES (?)", (str(user_id),))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT plan, balance, free_quota, tokens_used, photos_used, expenses, subscription_until FROM memory WHERE user_id=?", (str(user_id),))
    r = c.fetchone()
    conn.close()
    return r

def update_field(user_id, field, value):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(f"UPDATE memory SET {field}=? WHERE user_id=?", (value, str(user_id)))
    conn.commit()
    conn.close()

def add_to_field(user_id, field, delta):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute(f"UPDATE memory SET {field}={field}+? WHERE user_id=?", (delta, str(user_id)))
    conn.commit()
    conn.close()

# ----------------------- ЛОГИКА ПОДПИСКИ -----------------------

def check_subscription(user_id):
    plan, balance, quota, tokens, photos, expenses, until = get_user(user_id)
    now = int(time.time())

    if until > now:
        return

    update_field(user_id, "plan", "lite")

def activate_subscription(user_id):
    next_month = int(time.time()) + 30*24*3600
    update_field(user_id, "plan", "pro")
    update_field(user_id, "subscription_until", next_month)

# ----------------------- РАСХОДЫ -----------------------

def pay_for_action(user_id, token_cost, photo_cost=0):
    plan, balance, quota, tokens_used, photos_used, ex
penses, _ = get_user(user_id)
    limit_t = tariffs[plan]["tokens_limit"]
    limit_p = tariffs[plan]["photos_limit"]

    if tokens_used + token_cost > limit_t:
        return False

    if photos_used + photo_cost > limit_p:
        return False

    add_to_field(user_id, "tokens_used", token_cost)
    add_to_field(user_id, "photos_used", photo_cost)

    if tariffs[plan]["price"] == 0:
        return True

    if quota > 0:
        add_to_field(user_id, "free_quota", -1)
        return True

    if balance >= tariffs[plan]["price"]:
        add_to_field(user_id, "balance", -tariffs[plan]["price"])
        add_to_field(user_id, "expenses", tariffs[plan]["price"])
        return True

    return False

# ----------------------- ГРАФИКИ СТАТИСТИКИ -----------------------

def generate_stats_plot(user_id):
    user = get_user(user_id)
    tokens = user[3]
    photos = user[4]
    expenses = user[5]
labels = ["Токены", "Фото", "⭐️ Расходы"]
    values = [tokens, photos, expenses]

    fig, ax = plt.subplots()
    ax.bar(labels, values, color=["#4c8bf5", "#34a853", "#fbbc05"])
    ax.set_title("Статистика использования")

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    return buf

# ----------------------- ВЕБ‑ПАНЕЛЬ ДЛЯ АДМИНА -----------------------

class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "admin" not in self.path:
            self.send_response(403)
            self.end_headers()
            return

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT user_id, plan, balance, expenses FROM memory")
        users = c.fetchall()
        conn.close()

        html = "<h1>Админ‑панель</h1><table border='1'><tr><th>User</th><th>Plan</th><th>Balance</th><th>Expenses</th></tr>"
        for u in users:
            html += f"<tr><td>{u[0]}</td><td>{u[1]}</td><td>{u[2]}</td><td>{u[3]}</td></tr>"
        html += "</table>"

        self.send_response(200)
        self.end_headers()
        self.wfile.write(html.encode())

def start_admin_panel():
    server = HTTPServer(("0.0.0.0", 8080), AdminHandler)
    server.serve_forever()

# ----------------------- КОМАНДЫ -----------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    ensure_user(user_id)
    await update.message.reply_text("Привет. Готов работать.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    buf = generat
e_stats_plot(user_id)
    await update.message.reply_photo(photo=buf)

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = [LabeledPrice("Подписка на месяц", 350)]
    await update.message.reply_invoice(
        title="Подписка",
        description="30 дней тарифа Pro",
        payload="sub_350",
        provider_token="",
        currency="XTR",
        prices=prices
    )

async def success(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if update.message.successful_payment.invoice_payload == "sub_350":
        activate_subscription(user_id)
        await update.message.reply_text("Подписка активирована.")
    else:
        add_to_field(user_id, "balance", 100)
        await update.message.reply_text("Баланс пополнен на 100 ⭐️")

async def text_handler(update: Update, context):
    user_id = update.effective_chat.id
    ensure_user(user_id)
    check_subscription(user_id)

    tokens = len(update.message.text) // 4

    if not pay_for_action(user_id, tokens):
        await update.message.reply_text("Лимит превышен или нет средств.")
        return

    await update.message.reply_text("Ответ обработан.")

async def photo_handler(update: Update, context):
    user_id = update.effective_chat.id
    ensure_user(user_id)
    check_subscription(user_id)

    if not pay_for_action(user_id, token_cost=100, photo_cost=1):
        await update.message.reply_text("Фотолимит превышен.")
        return

    await update.message.reply_text("Фото обработано.")

# ----------------------- MAIN -----------------------

def main():
    init_db()

    app = ApplicationBuilder().token("YOUR_TOKEN").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success))

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT, text_handler))

    # авто‑продление подписок каждые 10 минут
    app.job_queue.run_repeating(lambda c: auto_renew_subscriptions(), 600)

    # запуск админ‑панели в отдельном процессе
    import threading
    threading.Thread(target=start_admin_panel, daemon=True).start()

    app.run_polling()

if name == "main":
    main()

