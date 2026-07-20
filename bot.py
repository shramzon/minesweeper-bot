import os
import random
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- ДАННЫЕ ПОЛЬЗОВАТЕЛЕЙ ---
users = {}
games = {}
locks = {}
farms = {}

BONUS_AMOUNT = 500
BONUS_COOLDOWN = 20 * 60  # 20 минут
START_BALANCE = 1000
DEFAULT_MINES = 3
FIELD_SIZE = 5

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "balance": START_BALANCE,
            "games_played": 0,
            "games_won": 0,
            "total_won": 0,
            "last_bonus": 0,
            "name": "Игрок",
            "total_spent": 0,
            "total_collected": 0
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
    def __init__(self, uid, mines_count, bet_amount):
        self.uid = uid
        self.size = FIELD_SIZE
        self.mines_count = mines_count
        self.bet = bet_amount
        self.total_cells = self.size * self.size
        self.board = [[False]*self.size for _ in range(self.size)]
        self.revealed = [[False]*self.size for _ in range(self.size)]
        self.game_over = False
        self.won = False
        self.opened = 0
        self.total_safe = self.total_cells - self.mines_count
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
                    text = "⬛"
                row.append(InlineKeyboardButton(text, callback_data=f"cell_{r}_{c}"))
            buttons.append(row)
        
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        if self.opened > 0 and not self.game_over:
            buttons.append([InlineKeyboardButton(f"💰 x{mult}", callback_data="cashout")])
        buttons.append([InlineKeyboardButton("🔄", callback_data="new")])
        return InlineKeyboardMarkup(buttons)
    
    def get_status(self, user):
        mult = calc_multiplier(self.opened, self.total_cells, self.mines_count)
        if self.game_over:
            if self.cashed_out:
                win = int(self.bet * mult)
                return f"💰 ЗАБРАЛ x{mult}!\n+{win} мун"
            elif self.won:
                win = int(self.bet * mult)
                return f"🎉 ВСЕ КЛЕТКИ! x{mult}\n+{win} мун"
            else:
                return f"💥 БОМБА! -{self.bet} мун"
        return f"💰 x{mult}\n💎 {self.opened}/{self.total_safe}"

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
        
        # --- ОСНОВНЫЕ КОМАНДЫ ---
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
                "В группе: упоминайте бота (@Sexment_bot) или отвечайте на его сообщение"
            )
            return
        
        elif text in ["профиль", "мой профиль", "аккаунт"]:
            win_rate = round(user["games_won"] / user["games_played"] * 100, 1) if user["games_played"] > 0 else 0
            
            farm_name = {
                "small": "Малая ферма",
                "medium": "Средняя ферма", 
                "large": "Большая ферма"
            }.get(farms.get(uid, {}).get("type"), "Нет фермы")
            
            income_per_hour = {
                "small": 50,
                "medium": 150,
                "large": 350
            }.get(farms.get(uid, {}).get("type"), 0)
            
            await update.message.reply_text(
                f"👤 Профиль\n\n"
                f"💰 Баланс: {user['balance']} мун\n"
                f"🎮 Игр: {user['games_played']}\n"
                f"🏆 Выиграно: {user['games_won']}\n"
                f"📊 Винрейт: {win_rate}%\n"
                f"💵 Всего выиграно: {user['total_won']} мун\n"
                f"🌱 Ферма: {farm_name}\n"
                f"📈 Доход: {income_per_hour}/час"
            )
            return
        
        elif text in ["рейтинг", "топ", "лидеры"]:
            sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)
            top = sorted_users[:10]
            
            if not top:
                await update.message.reply_text("📊 Пока нет игроков в рейтинге.")
                return
            
            lines = ["🏆 ТОП 10:\n"]
            for i, (uid, data) in enumerate(top, 1):
                name = data.get("name", f"Игрок{i}")
                lines.append(f"{i}. {name}: {data['balance']} мун")
            
            await update.message.reply_text("\n".join(lines))
            return
        
        elif text.startswith("мины"):
            parts = text.split()
            
            # Быстрая игра: мины 5 1000
            if len(parts) == 3:
                try:
                    mines_count = int(parts[1])
                    bet_amount = int(parts[2])
                except ValueError:
                    await update.message.reply_text("❌ Неверный формат! Пример: мины 5 1000")
                    return
                
                if mines_count < 1 or mines_count > 24:
                    await update.message.reply_text("❌ Мин от 1 до 24!")
                    return
                
                if bet_amount < 10:
                    await update.message.reply_text("❌ Мин ставка: 10 мун!")
                    return
                
                if user["balance"] < bet_amount:
                    await update.message.reply_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nНужно: {bet_amount} мун")
                    return
                
                user["balance"] -= bet_amount
                user["total_spent"] += bet_amount
                user["games_played"] += 1
                games[uid] = MinesGame(uid, mines_count, bet_amount)
                
                await update.message.reply_text(
                    f"🎮 Ставка: {bet_amount} мун | ⚫️ Мин: {mines_count}",
                    reply_markup=games[uid].get_keyboard()
                )
                return
            
            # Обычная игра: мины → выбор ставки
            elif len(parts) == 1:
                buttons = [
                    [InlineKeyboardButton("100", callback_data="bet_100"),
                     InlineKeyboardButton("500", callback_data="bet_500")],
                    [InlineKeyboardButton("1000", callback_data="bet_1000"),
                     InlineKeyboardButton("2000", callback_data="bet_2000")]
                ]
                
                await update.message.reply_text(
                    f"🎮 МИНЫ (3 мин по умолчанию)\nВыберите ставку:",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return
            
            else:
                await update.message.reply_text("❌ Неверный формат! Пример: мины 5 1000")
                return
        
        elif text in ["магазин", "фермы", "шоп"]:
            farm_info = {
                "small": {"name": "Малая", "price": 2000},
                "medium": {"name": "Средняя", "price": 5000},
                "large": {"name": "Большая", "price": 10000}
            }
            
            current_farm = farms.get(uid, {}).get("type", "none")
            
            buttons = []
            for key, info in farm_info.items():
                status = "✅" if current_farm == key else "🛒"
                buttons.append([InlineKeyboardButton(f"{info['name']} — {info['price']} мун | {status}", callback_data=f"buy_{key}")])
            
            buttons.append([InlineKeyboardButton("🔙", callback_data="back")])
            
            await update.message.reply_text(
                "🏪 Магазин ферм\n\n"
                "Фермы дают пассивный доход.\n"
                f"Баланс: {user['balance']} мун",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        
        elif text in ["собрать", "доход", "ферма"]:
            if uid not in farms:
                await update.message.reply_text("❌ Нет фермы!")
                return
            
            farm = farms[uid]
            farm_income = {
                "small": 50,
                "medium": 150,
                "large": 350
            }[farm["type"]]
            
            now = int(time.time())
            hours_passed = (now - farm["last_collect"]) // 3600
            
            if hours_passed <= 0:
                await update.message.reply_text("⏰ Собирайте не чаще раза в час!")
                return
            
            earnings = farm_income * hours_passed
            user["balance"] += earnings
            user["total_collected"] += earnings
            farm["last_collect"] = now
            
            await update.message.reply_text(f"💰 +{earnings} мун")
            return
        
        elif text in ["бонус", "подарок", "награда"]:
            now = int(time.time())
            time_left = BONUS_COOLDOWN - (now - user["last_bonus"])
            
            if time_left > 0:
                mins = time_left // 60
                secs = time_left % 60
                await update.message.reply_text(f"⏳ Через: {mins}м {secs}с")
                return
            
            user["balance"] += BONUS_AMOUNT
            user["last_bonus"] = now
            await update.message.reply_text(f"🎁 +{BONUS_AMOUNT} мун")
            return
        
        # --- НЕИЗВЕСТНАЯ КОМАНДА ---
        else:
            await update.message.reply_text("❓ Неизвестная команда\nНапишите: помощь")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data
    user = get_user(uid)
    lock = get_lock(uid)
    
    async with lock:
        await query.answer()
        
        if data.startswith("bet_"):
            bet_amount = int(data.split("_")[1])
            
            if user["balance"] < bet_amount:
                await query.edit_message_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун")
                return
            
            user["balance"] -= bet_amount
            user["total_spent"] += bet_amount
            user["games_played"] += 1
            games[uid] = MinesGame(uid, DEFAULT_MINES, bet_amount)
            
            await query.edit_message_text(
                f"🎮 Ставка: {bet_amount} мун | ⚫️ Мин: {DEFAULT_MINES}",
                reply_markup=games[uid].get_keyboard()
            )
            return
        
        elif data.startswith("cell_"):
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
        
        elif data == "cashout":
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
        
        elif data == "new":
            buttons = [
                [InlineKeyboardButton("100", callback_data="bet_100"),
                 InlineKeyboardButton("500", callback_data="bet_500")],
                [InlineKeyboardButton("1000", callback_data="bet_1000"),
                 InlineKeyboardButton("2000", callback_data="bet_2000")]
            ]
            
            await query.edit_message_text(
                "🎮 МИНЫ (3 мин)\nВыберите ставку:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        
        elif data.startswith("buy_"):
            farm_type = data.split("_")[1]
            price = {
                "small": 2000,
                "medium": 5000,
                "large": 10000
            }[farm_type]
            
            if user["balance"] < price:
                await query.answer("Недостаточно мун!")
                return
            
            user["balance"] -= price
            farms[uid] = {"type": farm_type, "level": 1, "last_collect": int(time.time())}
            await query.answer("✅ Куплена!")
            return
        
        elif data == "back":
            await query.edit_message_text("Возврат...")
            return

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()