import os
import asyncio
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN") # токен будет браться из переменной окружения


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


# --- База данных ---
def init_db():
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, cost REAL, price REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY, product_name TEXT, qty INTEGER,
                  revenue REAL, cost REAL, tax REAL, profit REAL, date TEXT)''')
    conn.commit()
    conn.close()


def add_product(name, cost, price):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO products (name, cost, price) VALUES (?, ?, ?)",
              (name.lower(), cost, price))
    conn.commit()
    conn.close()


def get_product(name):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute("SELECT name, cost, price FROM products WHERE name = ?", (name.lower(),))
    row = c.fetchone()
    conn.close()
    return row


def add_sale(product_name, qty, revenue, cost, tax, profit):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute("INSERT INTO sales (product_name, qty, revenue, cost, tax, profit, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (product_name.lower(), qty, revenue, cost, tax, profit, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


def undo_last_sale():
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute("SELECT id, product_name, qty, revenue, profit, date FROM sales ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    sale_id, product_name, qty, revenue, profit, date = row
    c.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
    conn.commit()
    conn.close()
    return (product_name, qty, revenue, profit, date)


def get_stats(days=None):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    if days:
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("SELECT SUM(qty), SUM(revenue), SUM(tax), SUM(profit) FROM sales WHERE date >= ?", (date_from,))
        summary = c.fetchone()
        c.execute("""
            SELECT product_name, SUM(qty), SUM(revenue), SUM(profit)
            FROM sales
            WHERE date >= ?
            GROUP BY product_name
            ORDER BY SUM(profit) DESC
        """, (date_from,))
    else:
        c.execute("SELECT SUM(qty), SUM(revenue), SUM(tax), SUM(profit) FROM sales")
        summary = c.fetchone()
        c.execute("""
            SELECT product_name, SUM(qty), SUM(revenue), SUM(profit)
            FROM sales
            GROUP BY product_name
            ORDER BY SUM(profit) DESC
        """)
    by_product = c.fetchall()
    conn.close()
    return summary, by_product


def format_stats_text(title, empty_text, days=None):
    summary, by_product = get_stats(days)
    if not summary or summary[0] is None:
        return empty_text

    qty, revenue, tax, profit = summary
    text = (
        f"{title}:\n\n"
        f"Продано штук: {int(qty)}\n"
        f"Выручка: {revenue:.0f} ₽\n"
        f"Налог 6%: {tax:.0f} ₽\n"
        f"Чистая прибыль: {profit:.0f} ₽"
    )

    if by_product:
        text += "\n\nПо товарам:\n"
        for prod_name, prod_qty, prod_rev, prod_profit in by_product:
            text += (
                f"• {prod_name.capitalize()} — {int(prod_qty)} шт "
                f"({prod_rev:.0f} ₽, прибыль {prod_profit:.0f} ₽)\n"
            )

    return text.rstrip()


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Это бот учёта продаж FFL.\n\n"
        "Команды:\n"
        "/add Название себестоимость цена — добавить товар\n"
        "Пример: /add Томаситко 180 950\n\n"
        "+ Название — зафиксировать продажу 1 шт\n"
        "+ Название 2 — продать 2 штуки\n"
        "/undo — отменить последнюю продажу\n\n"
        "/stats — статистика за всё время\n"
        "/week — за 7 дней\n"
        "/month — за 30 дней\n"
        "/products — список товаров"
    )
    await update.message.reply_text(text)


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text("Формат: /add Название себестоимость цена\nПример: /add Томаситко 180 950")
            return
        name = args[0]
        cost = float(args[1])
        price = float(args[2])
        add_product(name, cost, price)
        await update.message.reply_text(f"Товар «{name}» добавлен.\nСебестоимость: {cost} ₽\nЦена: {price} ₽")
    except Exception:
        await update.message.reply_text("Ошибка. Проверь формат: /add Название себестоимость цена")


async def products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    c.execute("SELECT name, cost, price FROM products")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("Товаров пока нет. Добавь через /add")
        return
    text = "Твои товары:\n\n"
    for name, cost, price in rows:
        text += f"• {name.capitalize()} — {cost} ₽ → {price} ₽\n"
    await update.message.reply_text(text)


async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    removed = undo_last_sale()
    if not removed:
        await update.message.reply_text("Отменять нечего — записей о продажах нет.")
        return
    product_name, qty, revenue, profit, date = removed
    await update.message.reply_text(
        f"Последняя продажа отменена:\n\n"
        f"• {product_name.capitalize()} × {int(qty)}\n"
        f"• Выручка: {revenue:.0f} ₽\n"
        f"• Прибыль: {profit:.0f} ₽\n"
        f"• Время: {date}"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = format_stats_text("Статистика за всё время", "Продаж пока нет")
    await update.message.reply_text(text)


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = format_stats_text("За последние 7 дней", "За последние 7 дней продаж нет", days=7)
    await update.message.reply_text(text)


async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = format_stats_text("За последние 30 дней", "За последние 30 дней продаж нет", days=30)
    await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith("+"):
        return

    parts = text[1:].strip().split()
    if not parts:
        await update.message.reply_text("Напиши: + Название или + Название 2")
        return

    name = parts[0]
    qty = 1
    if len(parts) > 1 and parts[1].isdigit():
        qty = int(parts[1])

    product = get_product(name)
    if not product:
        await update.message.reply_text(f"Товар «{name}» не найден. Сначала добавь его через /add")
        return

    _, cost, price = product
    revenue = price * qty
    total_cost = cost * qty
    tax = revenue * 0.06
    profit = revenue - tax - total_cost

    add_sale(name, qty, revenue, total_cost, tax, profit)

    await update.message.reply_text(
        f"Продажа записана!\n\n"
        f"{name.capitalize()} × {qty}\n"
        f"Выручка: {revenue:.0f} ₽\n"
        f"Налог: {tax:.0f} ₽\n"
        f"Прибыль: {profit:.0f} ₽"
    )


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("products", products_command))
    app.add_handler(CommandHandler("undo", undo_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("month", month_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    port = int(os.environ.get("PORT", 10000))
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever(),
        daemon=True
    ).start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
