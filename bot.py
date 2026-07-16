import os
import random
import time
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

users = {}
games = {}
pending_games = {}

BONUS_AMOUNT = 500
BONUS_COOLDOWN = 60
START_BALANCE = 1000
BET_AMOUNT = 100
FIELD_SIZE = 5

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "balance": START_BALANCE,
            "games_played": 0,
            "games_won": 0,
            "total_won": 0,
            "last_bonus": 0
        }
    return users[uid]

def calc_multiplier(opened, total_cells, mines_count):
    if opened == 0:
        return 1.00
    
    safe_cells = total_cells - mines_count
    probability = 1.0
    
    for i in range(opened):
        probability *= (safe_cells - i) / (total_cells - i)
    
    multiplier = 0.97 / probability
    return round(multiplier, 2)

class MinesGame:
    def __init__(self, uid, mines_count):
        self.uid = uid
        self.size = FIELD_SIZE
        self.mines_count = mines_count
        self.total_cells = self.size * self.size
        self.board = [[False]*self.size for _ in range(self.size)]
        self.revealed = [[False]*self.size for _ in range(self.size)]
        self.game_over = False
        self.won = False
        self.opened = 0
        self.total_safe = self.total_cells - self.mines_count
        self.bet = BET_AMOUNT
        self.cashed_out = False
        self.place_mines()
    
    def place_mines(self):
        placed = 0
        while placed < self.mines_count:
            r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
            if not self.board[r][c]:
                self.board[r][c] = True
                placed += 1
    
    def reveal(self, r, c):
        if self.game_over or self.revealed[r][c]:
            return "already"
        self.revealed[r][c] = True
        self.opened += 1
        if self.board[r][c]:
            self.game_over = True
            self.won = False
            return "mine"
        if self.opened == self.total_safe:
            self.game_over = True
            self.won = True
            return "win"
        return "safe"
    
    def cashout(self):
        if self.opened == 0 or self.game_over:
            return 0
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        win = int(self.bet * mult)
        self.game_over = True
        self.cashed_out = True
        self.won = True
        return win
    
    def get_keyboard(self, reveal_all=False):
        buttons = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    if self.board[r][c]:
                        text = "💣"
                    else:
                        text = "💎"
                elif reveal_all and self.board[r][c]:
                    text = "💣"
                else:
                    text = "⬜"
                row.append(InlineKeyboardButton(text, callback_data=f"{r}_{c}"))
            buttons.append(row)
        
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        cashout_btn = InlineKeyboardButton(
            f"💰 Забрать x{mult} ({int(self.bet*mult)}₽)",
            callback_data="cashout"
        ) if self.opened > 0 and not self.game_over else InlineKeyboardButton(
            f"💰 Забрать x{mult}",
            callback_data="cashout"
        )
        buttons.append([cashout_btn])
        buttons.append([InlineKeyboardButton("🔄 Новая игра (-100₽)", callback_data="new")])
        return InlineKeyboardMarkup(buttons)
    
    def get_status(self, user):
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        if self.game_over:
            if self.cashed_out:
                win = int(self.bet * mult)
                return f"💰 ЗАБРАЛ x{mult}!\n+{win}₽ на баланс!\nОткрыл: {self.opened} клеток"
            elif self.won:
                win = int(self.bet * mult)
                return f"🎉 ВСЕ КЛЕТКИ! x{mult}\n+{win}₽ на баланс!"
            else:
                return f"💥 БОМБА! -{self.bet}₽\nОткрыл: {self.opened} клеток"
        return f" Ставка: {self.bet}₽\n💰 Множитель: x{mult}\n💎 Открыто: {self.opened}/{self.total_safe}\n💣 Мин: {self.mines_count}\n\n💵 Баланс: {user['balance']}₽"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    
    if user["balance"] < BET_AMOUNT:
        await update.message.reply_text(f"❌ Недостаточно средств!\nБаланс: {user['balance']}₽\nНужно: {BET_AMOUNT}₽\n\nВозьми бонус: /bonus")
        return
    
    pending_games[uid] = True
    
    buttons = []
    for i in range(1, 25):
        buttons.append(InlineKeyboardButton(f" {i} мин", callback_data=f"mines_{i}"))
    
    keyboard = InlineKeyboardMarkup([buttons[i:i+5] for i in range(0, len(buttons), 5)])
    
    await update.message.reply_text(
        f"🎮 МИНЫ! Ставка: {BET_AMOUNT}₽\n\n"
        f"Выбери количество мин (1-24):\n"
        f"Чем больше мин — тем выше риск и выигрыш!\n\n"
        f"💵 Баланс: {user['balance']}₽",
        reply_markup=keyboard
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    user = get_user(uid)
    
    if data.startswith("mines_"):
        if uid not in pending_games:
            await query.answer("Сначала напиши /start")
            return
        
        mines_count = int(data.split("_")[1])
        del pending_games[uid]
        
        user["balance"] -= BET_AMOUNT
        user["games_played"] += 1
        games[uid] = MinesGame(uid, mines_count)
        
        await query.edit_message_text(
            f"🎮 МИНЫ! Ставка: {BET_AMOUNT}₽\n💣 Мин: {mines_count}\n\n"
            f"Открывай клетки — множитель растёт!\n"
            f" Не попади на мину!\n"
            f"💰 Забирай выигрыш в любой момент!\n\n"
            f"💵 Баланс: {user['balance']}₽",
            reply_markup=games[uid].get_keyboard()
        )
        return
    
    if data == "new":
        if user["balance"] < BET_AMOUNT:
            await query.edit_message_text(f"❌ Недостаточно средств!\nБаланс: {user['balance']}₽\nВозьми бонус: /bonus")
            return
        
        pending_games[uid] = True
        
        buttons = []
        for i in range(1, 25):
            buttons.append(InlineKeyboardButton(f"💣 {i} мин", callback_data=f"mines_{i}"))
        
        keyboard = InlineKeyboardMarkup([buttons[i:i+5] for i in range(0, len(buttons), 5)])
        
        await query.edit_message_text(
            f"🎮 МИНЫ! Ставка: {BET_AMOUNT}₽\n\n"
            f"Выбери количество мин (1-24):\n\n"
            f"💵 Баланс: {user['balance']}₽",
            reply_markup=keyboard
        )
        return
    
    if data == "cashout":
        if uid not in games or games[uid].game_over:
            await query.answer("Нет активной игры!")
            return
        game = games[uid]
        if game.opened == 0:
            await query.answer("Открой хотя бы 1 клетку!")
            return
        win = game.cashout()
        user["balance"] += win
        user["games_won"] += 1
        user["total_won"] += win
        await query.edit_message_text(game.get_status(user), reply_markup=game.get_keyboard(reveal_all=True))
        return
    
    if uid not in games:
        await query.answer("Начни игру: /start")
        return
    
    game = games[uid]
    if game.game_over:
        await query.answer("Игра окончена! Начни новую 🔄")
        return
    
    r, c = map(int, data.split("_"))
    result = game.reveal(r, c)
    
    if result == "mine":
        await query.edit_message_text(game.get_status(user), reply_markup=game.get_keyboard(reveal_all=True))
    elif result == "win":
        win = int(game.bet * calc_multiplier(game.opened, game.total_cells, game.mines_count))
        user["balance"] += win
        user["games_won"] += 1
        user["total_won"] += win
        await query.edit_message_text(game.get_status(user), reply_markup=game.get_keyboard(reveal_all=True))
    else:
        await query.edit_message_text(game.get_status(user), reply_markup=game.get_keyboard())

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    
    win_rate = round(user["games_won"] / user["games_played"] * 100, 1) if user["games_played"] > 0 else 0
    
    text = (
        f"👤 Твой профиль:\n\n"
        f"💵 Баланс: {user['balance']}₽\n"
        f" Игр сыграно: {user['games_played']}\n"
        f"🏆 Игр выиграно: {user['games_won']}\n"
        f" Винрейт: {win_rate}%\n"
        f"💰 Всего выиграно: {user['total_won']}₽\n\n"
        f"Команды:\n"
        f"/start — начать игру\n"
        f"/bonus — получить бонус\n"
        f"/profile — этот профиль"
    )
    await update.message.reply_text(text)

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    now = int(time.time())
    
    time_left = BONUS_COOLDOWN - (now - user["last_bonus"])
    if time_left > 0:
        await update.message.reply_text(f" Бонус уже получен!\nПовторно через: {time_left} сек.")
        return
    
    user["balance"] += BONUS_AMOUNT
    user["last_bonus"] = now
    await update.message.reply_text(f"🎁 Бонус +{BONUS_AMOUNT}₽!\n💵 Баланс: {user['balance']}₽")

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('bonus', bonus))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()