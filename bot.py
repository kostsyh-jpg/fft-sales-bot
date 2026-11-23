import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")  # токен будет браться из переменной окружения

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
              (product_name, qty, revenue, cost, tax, profit, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_stats(days=None):
    conn = sqlite3.connect("sales.db")
    c = conn.cursor()
    if days:
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("SELECT SUM(qty), SUM(revenue), SUM(tax), SUM(profit) FROM sales WHERE date >= ?", (date_from,))
    else:
        c.execute("SELECT SUM(qty), SUM(revenue), SUM(tax), SUM(profit) FROM sales")
    row = c.fetchone()
    conn.close()
    return row

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Это бот учёта продаж FFL.\n\n"
        "Команды:\n"
        "/add Название себестоимость цена — добавить товар\n"
        "Пример: /add Томаситко 180 950\n\n"
        "+ Название — зафиксировать продажу 1 шт\n"
        "+ Название 2 — продать 2 штуки\n\n"
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
    except:
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_stats()
    if not row or row[0] is None:
        await update.message.reply_text("Продаж пока нет")
        return
    qty, revenue, tax, profit = row
    text = (
        f"Статистика за всё время:\n\n"
        f"Продано штук: {int(qty)}\n"
        f"Выручка: {revenue:.0f} ₽\n"
        f"Налог 6%: {tax:.0f} ₽\n"
        f"Чистая прибыль: {profit:.0f} ₽"
    )
    await update.message.reply_text(text)

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_stats(7)
    if not row or row[0] is None:
        await update.message.reply_text("За последние 7 дней продаж нет")
        return
    qty, revenue, tax, profit = row
    text = (
        f"За последние 7 дней:\n\n"
        f"Продано штук: {int(qty)}\n"
        f"Выручка: {revenue:.0f} ₽\n"
        f"Налог 6%: {tax:.0f} ₽\n"
        f"Чистая прибыль: {profit:.0f} ₽"
    )
    await update.message.reply_text(text)

async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_stats(30)
    if not row or row[0] is None:
        await update.message.reply_text("За последние 30 дней продаж нет")
        return
    qty, revenue, tax, profit = row
    text = (
        f"За последние 30 дней:\n\n"
        f"Продано штук: {int(qty)}\n"
        f"Выручка: {revenue:.0f} ₽\n"
        f"Налог 6%: {tax:.0f} ₽\n"
        f"Чистая прибыль: {profit:.0f} ₽"
    )
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
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("month", month_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("Бот запущен...")
    app.run_polling()
    


if __name__ == "__main__":
    main()
