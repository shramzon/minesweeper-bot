import os
import random
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- ДАННЫЕ ПОЛЬЗОВАТЕЛЕЙ ---
users = {}
games = {}
locks = {}
farms = {}  # {uid: {"type": "small", "level": 1, "last_collect": 0}}

BONUS_AMOUNT = 500
BONUS_COOLDOWN = 20 * 60  # 20 минут
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
            "last_bonus": 0,
            "name": "Игрок"
        }
    return users[uid]

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
                    text = "⚫️" if self.board[r][c] else "💎"
                elif reveal_all and self.board[r][c]:
                    text = "⚫️"
                else:
                    text = "⬛"  # тёмная клетка
                row.append(InlineKeyboardButton(text, callback_data=f"cell_{r}_{c}"))
            buttons.append(row)
        
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        if self.opened > 0 and not self.game_over:
            buttons.append([InlineKeyboardButton(f"💰 Забрать x{mult} ({int(self.bet*mult)} мун)", callback_data="cashout")])
        buttons.append([InlineKeyboardButton("🔄 Новая игра", callback_data="new")])
        return InlineKeyboardMarkup(buttons)
    
    def get_status(self, user):
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        if self.game_over:
            if self.cashed_out:
                win = int(self.bet * mult)
                return f"💰 ЗАБРАЛ x{mult}!\n+{win} мун на баланс!\nОткрыл: {self.opened} клеток"
            elif self.won:
                win = int(self.bet * mult)
                return f"🎉 ВСЕ КЛЕТКИ! x{mult}\n+{win} мун на баланс!"
            else:
                return f"💥 БОМБА! -{self.bet} мун\nОткрыл: {self.opened} клеток"
        return f"💰 Множитель: x{mult}\n💎 Открыто: {self.opened}/{self.total_safe}\n⚫️ Мин: {self.mines_count}\n💵 Баланс: {user['balance']} мун"

# --- КОМАНДЫ ---

async def mines_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    
    if user["balance"] < BET_AMOUNT:
        await update.message.reply_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nНужно: {BET_AMOUNT} мун\n\nВозьми бонус: /bonus")
        return
    
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(f"⚫️{i}", callback_data=f"mines_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    await update.message.reply_text(
        f"🎮 МИНЫ! Ставка: {BET_AMOUNT} мун\n\nВыбери количество мин (1-10):\n💰 Баланс: {user['balance']} мун",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    win_rate = round(user["games_won"] / user["games_played"] * 100, 1) if user["games_played"] > 0 else 0
    
    text = (
        f"👤 Профиль:\n\n"
        f"💰 Баланс: {user['balance']} мун\n"
        f"🎮 Игр сыграно: {user['games_played']}\n"
        f"🏆 Выиграно: {user['games_won']}\n"
        f"📊 Винрейт: {win_rate}%\n"
        f"💵 Всего выиграно: {user['total_won']} мун\n\n"
        f"Команды:\n"
        f"/mines — начать игру\n"
        f"/rating — топ игроков\n"
        f"/shop — магазин\n"
        f"/collect — собрать доход\n"
        f"/bonus — бонус"
    )
    await update.message.reply_text(text)

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)
    top = sorted_users[:10]
    
    lines = ["🏆 ТОП ИГРОКОВ:\n"]
    for i, (uid, data) in enumerate(top, 1):
        name = data.get("name", f"Игрок{i}")
        lines.append(f"{i}. {name} — {data['balance']} мун")
    
    if not top:
        lines.append("Пока нет игроков.")
    
    await update.message.reply_text("\n".join(lines))

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    
    farm_info = {
        "small": {"name": "Малая ферма", "price": 2000, "income": 50, "desc": "50 мун/час"},
        "medium": {"name": "Средняя ферма", "price": 5000, "income": 150, "desc": "150 мун/час"},
        "large": {"name": "Большая ферма", "price": 10000, "income": 350, "desc": "350 мун/час"}
    }
    
    current_farm = farms.get(uid, {}).get("type", "none")
    
    buttons = []
    for key, info in farm_info.items():
        status = "✅ Куплена" if current_farm == key else "🛒 Купить"
        buttons.append([InlineKeyboardButton(f"{info['name']} — {info['price']} мун | {status}", callback_data=f"buy_{key}")])
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    
    await update.message.reply_text(
        "🏪 Магазин ферм\n\n"
        "Фермы дают пассивный доход каждые 60 минут.\n"
        "Собирай вручную через /collect.\n\n"
        f"Баланс: {user['balance']} мун",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    
    if uid not in farms:
        await update.message.reply_text("❌ У тебя нет фермы!\nКупи в магазине: /shop")
        return
    
    farm = farms[uid]
    farm_info = {
        "small": {"income": 50},
        "medium": {"income": 150},
        "large": {"income": 350}
    }
    
    income = farm_info[farm["type"]]["income"]
    now = int(time.time())
    
    # Считаем сколько часов прошло с последнего сбора
    hours_passed = (now - farm["last_collect"]) // 3600
    
    if hours_passed <= 0:
        await update.message.reply_text(f"⏰ Собирай доход не чаще раза в час!\nСледующий сбор через: {3600 - (now - farm['last_collect'])} секунд")
        return
    
    earnings = income * hours_passed
    user["balance"] += earnings
    farm["last_collect"] = now
    
    await update.message.reply_text(f"💰 Собрал {earnings} мун с фермы!\nБаланс: {user['balance']} мун")

async def bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    now = int(time.time())
    
    time_left = BONUS_COOLDOWN - (now - user["last_bonus"])
    if time_left > 0:
        mins = time_left // 60
        secs = time_left % 60
        await update.message.reply_text(f"⏳ Бонус уже получен!\nПовторно через: {mins}м {secs}с")
        return
    
    user["balance"] += BONUS_AMOUNT
    user["last_bonus"] = now
    await update.message.reply_text(f"🎁 Бонус +{BONUS_AMOUNT} мун!\n💰 Баланс: {user['balance']} мун")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    user = get_user(uid)
    lock = get_lock(uid)
    
    async with lock:
        await query.answer()
        
        if data.startswith("mines_"):
            mines_count = int(data.split("_")[1])
            
            if user["balance"] < BET_AMOUNT:
                await query.edit_message_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nВозьми бонус: /bonus")
                return
            
            user["balance"] -= BET_AMOUNT
            user["games_played"] += 1
            games[uid] = MinesGame(uid, mines_count)
            
            await query.edit_message_text(
                f"🎮 МИНЫ! Ставка: {BET_AMOUNT} мун | ⚫️ Мин: {mines_count}\n💰 Баланс: {user['balance']} мун",
                reply_markup=games[uid].get_keyboard()
            )
            return
        
        if data == "new":
            if user["balance"] < BET_AMOUNT:
                await query.edit_message_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nВозьми бонус: /bonus")
                return
            
            buttons = []
            row = []
            for i in range(1, 11):
                row.append(InlineKeyboardButton(f"⚫️{i}", callback_data=f"mines_{i}"))
                if len(row) == 5:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            
            await query.edit_message_text(
                f"🎮 МИНЫ! Ставка: {BET_AMOUNT} мун\n\nВыбери количество мин (1-10):\n💰 Баланс: {user['balance']} мун",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        
        if data == "cashout":
            if uid not in games or games[uid].game_over:
                return
            game = games[uid]
            if game.opened == 0:
                return
            win = game.cashout()
            user["balance"] += win
            user["games_won"] += 1
            user["total_won"] += win
            await query.edit_message_text(game.get_status(user), reply_markup=game.get_keyboard(reveal_all=True))
            return
        
        if data.startswith("cell_"):
            if uid not in games:
                return
            
            game = games[uid]
            if game.game_over:
                return
            
            r, c = map(int, data.split("_")[1:])
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
            return
        
        if data.startswith("buy_"):
            farm_type = data.split("_")[1]
            farm_info = {
                "small": {"price": 2000, "name": "Малая ферма"},
                "medium": {"price": 5000, "name": "Средняя ферма"},
                "large": {"price": 10000, "name": "Большая ферма"}
            }
            
            price = farm_info[farm_type]["price"]
            if user["balance"] < price:
                await query.answer(f"Недостаточно мун! Нужно {price}")
                return
            
            user["balance"] -= price
            farms[uid] = {"type": farm_type, "level": 1, "last_collect": int(time.time())}
            await query.answer(f"✅ Куплена {farm_info[farm_type]['name']}!")
            return
        
        if data == "back":
            await query.edit_message_text("Возврат в меню...")
            return

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('mines', mines_cmd))
    app.add_handler(CommandHandler('profile', profile))
    app.add_handler(CommandHandler('rating', rating))
    app.add_handler(CommandHandler('shop', shop))
    app.add_handler(CommandHandler('collect', collect))
    app.add_handler(CommandHandler('bonus', bonus))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()