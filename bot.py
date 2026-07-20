import os
import random
import time
import asyncio
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, ContextTypes, CommandHandler

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
DB_PATH = "mines.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            uid INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 1000,
            games_played INTEGER DEFAULT 0,
            games_won INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            last_bonus INTEGER DEFAULT 0,
            name TEXT DEFAULT 'Игрок',
            total_spent INTEGER DEFAULT 0,
            total_collected INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS games (
            gid INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER,
            mines INTEGER,
            bet INTEGER,
            opened INTEGER DEFAULT 0,
            game_over BOOLEAN DEFAULT 0,
            won BOOLEAN DEFAULT 0,
            cashed_out BOOLEAN DEFAULT 0,
            board TEXT,
            revealed TEXT,
            created_at REAL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS farms (
            uid INTEGER PRIMARY KEY,
            type TEXT,
            level INTEGER DEFAULT 1,
            last_collect REAL
        )
    ''')
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE uid=?", (uid,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (uid) VALUES (?)", (uid,))
        conn.commit()
        row = (uid, 1000, 0, 0, 0, 0, "Игрок", 0, 0)
    conn.close()
    return {
        "uid": row[0],
        "balance": row[1],
        "games_played": row[2],
        "games_won": row[3],
        "total_won": row[4],
        "last_bonus": row[5],
        "name": row[6],
        "total_spent": row[7],
        "total_collected": row[8]
    }

def update_user(uid, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    values = list(kwargs.values()) + [uid]
    c.execute(f"UPDATE users SET {set_clause} WHERE uid=?", values)
    conn.commit()
    conn.close()

def get_game(gid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM games WHERE gid=?", (gid,))
    row = c.fetchone()
    conn.close()
    return row

def create_game(uid, mines, bet):
    board = [[False]*5 for _ in range(5)]
    revealed = [[False]*5 for _ in range(5)]
    # Расставляем мины
    placed = 0
    while placed < mines:
        r, c = random.randint(0, 4), random.randint(0, 4)
        if not board[r][c]:
            board[r][c] = True
            placed += 1
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO games (uid, mines, bet, board, revealed, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (uid, mines, bet, str(board), str(revealed), time.time()))
    gid = c.lastrowid
    conn.commit()
    conn.close()
    return gid

def update_game(gid, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    values = list(kwargs.values()) + [gid]
    c.execute(f"UPDATE games SET {set_clause} WHERE gid=?", values)
    conn.commit()
    conn.close()

# --- ГЛОБАЛЬНЫЕ ДАННЫЕ ---
locks = {}
BONUS_AMOUNT = 500
BONUS_COOLDOWN = 20 * 60
DEFAULT_MINES = 3
FIELD_SIZE = 5

def get_lock(uid):
    if uid not in locks:
        locks[uid] = asyncio.Lock()
    return locks[uid]

def calc_multiplier(opened, total_cells, mines_count):
    if opened == 0:
        return 1.00
    safe_cells = total_cells - mines_count
    probability = 1.0
    for i in range(opened):
        probability *= (safe_cells - i) / (total_cells - i)
    multiplier = 0.97 / probability
    return round(multiplier, 2)

# --- КОМАНДЫ ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type not in ['private', 'group', 'supergroup']:
        return

    uid = update.effective_user.id
    user = get_user(uid)
    lock = get_lock(uid)

    async with lock:
        text = update.message.text.strip().lower()

        # --- ПОМОЩЬ ---
        if text in ["помощь", "help", "команды", "чё делать"]:
            await update.message.reply_text(
                "🎮 Команды:\n\n"
                "профиль — ваш профиль\n"
                "рейтинг — топ игроков\n"
                "мины — начать игру (3 мины)\n"
                "мины 5 1000 — игра с 5 минами и ставкой 1000 мун\n"
                "магазин — магазин ферм\n"
                "собрать — собрать доход\n"
                "бонус — получить бонус\n\n"
                "В группе: упоминайте бота (@Sexment_bot)"
            )
            return

        # --- ПРОФИЛЬ ---
        elif text in ["профиль", "мой профиль", "аккаунт"]:
            farm = None
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT type FROM farms WHERE uid=?", (uid,))
            row = c.fetchone()
            if row:
                farm = row[0]
            conn.close()

            farm_name = {
                "small": "Малая ферма",
                "medium": "Средняя ферма",
                "large": "Большая ферма"
            }.get(farm, "Нет фермы")

            income_per_hour = {
                "small": 50,
                "medium": 150,
                "large": 350
            }.get(farm, 0)

            await update.message.reply_text(
                f"👤 Профиль\n\n"
                f"💰 Баланс: {user['balance']} мун\n"
                f"🎮 Игр: {user['games_played']}\n"
                f"🏆 Выиграно: {user['games_won']}\n"
                f"📊 Винрейт: {round(user['games_won']/user['games_played']*100, 1) if user['games_played']>0 else 0}%\n"
                f"💵 Всего выиграно: {user['total_won']} мун\n"
                f"🌱 Ферма: {farm_name}\n"
                f"📈 Доход: {income_per_hour}/час"
            )
            return

        # --- РЕЙТИНГ ---
        elif text in ["рейтинг", "топ", "лидеры"]:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT uid, balance FROM users ORDER BY balance DESC LIMIT 10")
            rows = c.fetchall()
            conn.close()

            if not rows:
                await update.message.reply_text("📊 Пока нет игроков.")
                return

            lines = ["🏆 ТОП 10:\n"]
            for i, (uid, bal) in enumerate(rows, 1):
                lines.append(f"{i}. Игрок{uid}: {bal} мун")
            await update.message.reply_text("\n".join(lines))
            return

        # --- МИНЫ ---
        elif text.startswith("мины"):
            parts = text.split()
            if len(parts) == 3:
                try:
                    mines = int(parts[1])
                    bet = int(parts[2])
                except:
                    await update.message.reply_text("❌ Пример: мины 5 1000")
                    return
                if mines < 1 or mines > 24 or bet < 10 or user["balance"] < bet:
                    await update.message.reply_text("❌ Ошибочный ввод или недостаточно мун")
                    return

                update_user(uid, balance=user["balance"] - bet, total_spent=user["total_spent"] + bet, games_played=user["games_played"] + 1)
                gid = create_game(uid, mines, bet)
                await update.message.reply_text(
                    f"🎮 Ставка: {bet} мун | ⚫️ Мин: {mines}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⬛", callback_data=f"cell_{gid}_0_0")],
                        [InlineKeyboardButton("🔄", callback_data=f"new_{gid}")]
                    ])
                )
                return

            elif len(parts) == 1:
                buttons = [
                    [InlineKeyboardButton("100", callback_data="bet_100"),
                     InlineKeyboardButton("500", callback_data="bet_500")],
                    [InlineKeyboardButton("1000", callback_data="bet_1000"),
                     InlineKeyboardButton("2000", callback_data="bet_2000")]
                ]
                await update.message.reply_text(
                    "🎮 МИНЫ (3 мин)\nВыберите ставку:",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return

        # --- МАГАЗИН ---
        elif text in ["магазин", "фермы", "шоп"]:
            buttons = [
                [InlineKeyboardButton("Малая — 2000 мун", callback_data="buy_small")],
                [InlineKeyboardButton("Средняя — 5000 мун", callback_data="buy_medium")],
                [InlineKeyboardButton("Большая — 10000 мун", callback_data="buy_large")]
            ]
            await update.message.reply_text(
                "🏪 Магазин ферм\n\n"
                "Фермы дают пассивный доход.\n"
                f"Баланс: {user['balance']} мун",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # --- СОБРАТЬ ---
        elif text in ["собрать", "доход", "ферма"]:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT type, last_collect FROM farms WHERE uid=?", (uid,))
            row = c.fetchone()
            if not row:
                await update.message.reply_text("❌ Нет фермы!")
                conn.close()
                return

            farm_type, last_collect = row
            now = time.time()
            hours = int((now - last_collect) // 3600)
            if hours <= 0:
                await update.message.reply_text("⏰ Собирайте не чаще раза в час!")
                conn.close()
                return

            income = {"small": 50, "medium": 150, "large": 350}[farm_type] * hours
            update_user(uid, balance=user["balance"] + income, total_collected=user["total_collected"] + income)
            c.execute("UPDATE farms SET last_collect=? WHERE uid=?", (now, uid))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"💰 +{income} мун")
            return

        # --- БОНУС ---
        elif text in ["бонус", "подарок"]:
            now = time.time()
            if now - user["last_bonus"] < BONUS_COOLDOWN:
                await update.message.reply_text("⏳ Бонус ещё не готов")
                return
            update_user(uid, balance=user["balance"] + BONUS_AMOUNT, last_bonus=now)
            await update.message.reply_text(f"🎁 +{BONUS_AMOUNT} мун")
            return

        else:
            await update.message.reply_text("❓ Напишите: помощь")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    lock = get_lock(uid)

    async with lock:
        await query.answer()

        if data.startswith("bet_"):
            bet = int(data.split("_")[1])
            user = get_user(uid)
            if user["balance"] < bet:
                await query.edit_message_text("❌ Недостаточно мун!")
                return
            update_user(uid, balance=user["balance"] - bet, total_spent=user["total_spent"] + bet, games_played=user["games_played"] + 1)
            gid = create_game(uid, DEFAULT_MINES, bet)
            await query.edit_message_text(
                f"🎮 Ставка: {bet} мун | ⚫️ Мин: {DEFAULT_MINES}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬛", callback_data=f"cell_{gid}_0_0")]
                ])
            )
            return