import os
import random
import time
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- ДАННЫЕ ПОЛЬЗОВАТЕЛЕЙ ---
users = {}
games = {}
locks = {}
farms = {}
pending_actions = {}

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
        self.start_time = time.time()
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
    
    def get_field(self):
        field = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    text = "⚫️" if self.board[r][c] else "💎"
                else:
                    text = "⬛"
                row.append(text)
            field.append(" ".join(row))
        return "\n".join(field)

# --- КОМАНДЫ БЕЗ "/" ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    lock = get_lock(uid)
    
    async with lock:
        text = update.message.text.strip().lower()
        
        # --- КОМАНДЫ БЕЗ "/" ---
        if text in ["старт", "начать", "привет"]:
            await update.message.reply_text(
                "🎮 Добро пожаловать!\n\n"
                "Доступные команды:\n"
                "профиль — ваш профиль\n"
                "рейтинг — топ игроков\n"
                "мины — начать игру в мины\n"
                "магазин — магазин ферм\n"
                "собрать — собрать доход\n"
                "бонус — получить бонус\n"
                "помощь — помощь\n\n"
                "Удачи в игре! 💰"
            )
            return
        
        elif text in ["помощь", "help"]:
            await update.message.reply_text(
                "🎮 Помощь по боту:\n\n"
                "профиль — информация о вас\n"
                "рейтинг — топ игроков\n"
                "мины — начать игру (ставка 100 мун)\n"
                "  • Введите количество мин (1-10)\n"
                "  • Введите координаты (1 1, 2 3...)\n"
                "  • забрать — забрать выигрыш\n"
                "  • поле — показать поле\n"
                "магазин — купить ферму (пассивный доход)\n"
                "собрать — собрать доход с фермы\n"
                "бонус — получить бонус раз в 20 минут\n\n"
                "🎯 Цель: открывать клетки, избегая мин!\n"
                "💰 Чем больше открыл — тем выше множитель!"
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
                f"👤 Ваш профиль:\n\n"
                f"💰 Баланс: {user['balance']} мун\n"
                f"🎮 Игр сыграно: {user['games_played']}\n"
                f"🏆 Выиграно: {user['games_won']}\n"
                f"📊 Винрейт: {win_rate}%\n"
                f"💵 Всего выиграно: {user['total_won']} мун\n"
                f"💸 Всего потрачено: {user['total_spent']} мун\n"
                f"🌱 Ферма: {farm_name}\n"
                f"📈 Доход: {income_per_hour}/час\n"
                f"📥 Всего собрано: {user['total_collected']} мун\n\n"
                f"Доступные команды:\n"
                f"мины — начать игру\n"
                f"рейтинг — топ игроков\n"
                f"магазин — магазин\n"
                f"собрать — собрать доход\n"
                f"бонус — бонус"
            )
            return
        
        elif text in ["рейтинг", "топ", "лидеры"]:
            sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)
            top = sorted_users[:10]
            
            if not top:
                await update.message.reply_text("📊 Пока нет игроков в рейтинге.")
                return
            
            lines = ["🏆 ТОП 10 ИГРОКОВ:\n"]
            for i, (uid, data) in enumerate(top, 1):
                name = data.get("name", f"Игрок{uid}")
                lines.append(f"{i}. {name}: {data['balance']} мун")
            
            await update.message.reply_text("\n".join(lines))
            return
        
        elif text in ["мины", "игра", "сыграть"]:
            if user["balance"] < BET_AMOUNT:
                await update.message.reply_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nНужно: {BET_AMOUNT} мун\n\nВозьми: бонус")
                return
            
            await update.message.reply_text(
                f"🎮 МИНЫ! Ставка: {BET_AMOUNT} мун\n\nВведите количество мин (1-10):"
            )
            
            pending_actions[uid] = "choosing_mines"
            return
        
        elif text in ["магазин", "фермы", "шоп"]:
            farm_info = {
                "small": {"name": "Малая ферма", "price": 2000, "income": 50},
                "medium": {"name": "Средняя ферма", "price": 5000, "income": 150},
                "large": {"name": "Большая ферма", "price": 10000, "income": 350}
            }
            
            current_farm = farms.get(uid, {}).get("type", "none")
            
            text_reply = "🏪 Магазин ферм\n\n"
            for key, info in farm_info.items():
                status = "✅ Куплена" if current_farm == key else f"🛒 Купить ({info['price']} мун)"
                text_reply += f"{info['name']} — {info['income']}/час | {status}\n"
            
            text_reply += f"\nВведите номер фермы для покупки:\n"
            text_reply += f"1 — Малая (2000 мун)\n"
            text_reply += f"2 — Средняя (5000 мун)\n"
            text_reply += f"3 — Большая (10000 мун)\n\n"
            text_reply += f"Баланс: {user['balance']} мун"
            
            await update.message.reply_text(text_reply)
            pending_actions[uid] = "choosing_farm"
            return
        
        elif text in ["собрать", "доход", "ферма"]:
            if uid not in farms:
                await update.message.reply_text("❌ У вас нет фермы!\nКупите: магазин")
                return
            
            farm = farms[uid]
            farm_info = {
                "small": {"income": 50},
                "medium": {"income": 150},
                "large": {"income": 350}
            }
            
            income = farm_info[farm["type"]]["income"]
            now = int(time.time())
            
            hours_passed = (now - farm["last_collect"]) // 3600
            
            if hours_passed <= 0:
                await update.message.reply_text(f"⏰ Собирайте доход не чаще раза в час!\nСледующий сбор через: {3600 - (now - farm['last_collect'])} секунд")
                return
            
            earnings = income * hours_passed
            user["balance"] += earnings
            user["total_collected"] += earnings
            farm["last_collect"] = now
            
            await update.message.reply_text(f"💰 Собрали {earnings} мун с фермы!\nБаланс: {user['balance']} мун")
            return
        
        elif text in ["бонус", "подарок", "награда"]:
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
            return
        
        # --- ОБРАБОТКА ИГРЫ ---
        elif pending_actions.get(uid) == "choosing_mines":
            try:
                mines_count = int(text)
                if mines_count < 1 or mines_count > 10:
                    await update.message.reply_text("❌ Введите число от 1 до 10!")
                    return
                
                if user["balance"] < BET_AMOUNT:
                    await update.message.reply_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун")
                    return
                
                user["balance"] -= BET_AMOUNT
                user["total_spent"] += BET_AMOUNT
                user["games_played"] += 1
                games[uid] = MinesGame(uid, mines_count)
                
                del pending_actions[uid]
                
                game = games[uid]
                await update.message.reply_text(
                    f"🎮 МИНЫ! Ставка: {BET_AMOUNT} мун | ⚫️ Мин: {mines_count}\n\n"
                    f"`{game.get_field()}`\n\n"
                    f"💰 Множитель: x{calc_multiplier(game.opened, game.total_cells, game.mines_count)}\n"
                    f"💎 Открыто: {game.opened}/{game.total_safe}\n"
                    f"Баланс: {user['balance']} мун\n\n"
                    f"Введите координаты (например, '1 2') или:\n"
                    f"забрать — забрать выигрыш\n"
                    f"поле — показать поле\n"
                    f"новая — новая игра"
                )
                return
            except ValueError:
                await update.message.reply_text("❌ Введите число от 1 до 10!")
                return
        
        elif pending_actions.get(uid) == "choosing_farm":
            try:
                choice = int(text)
                if choice < 1 or choice > 3:
                    await update.message.reply_text("❌ Введите 1, 2 или 3!")
                    return
                
                farm_types = ["small", "medium", "large"]
                farm_prices = [2000, 5000, 10000]
                farm_names = ["Малая ферма", "Средняя ферма", "Большая ферма"]
                
                farm_type = farm_types[choice - 1]
                price = farm_prices[choice - 1]
                name = farm_names[choice - 1]
                
                if user["balance"] < price:
                    await update.message.reply_text(f"❌ Недостаточно мун!\nНужно: {price}, у вас: {user['balance']}")
                    return
                
                user["balance"] -= price
                farms[uid] = {"type": farm_type, "level": 1, "last_collect": int(time.time())}
                
                del pending_actions[uid]
                
                await update.message.reply_text(f"✅ Куплена {name}!\nБаланс: {user['balance']} мун")
            except ValueError:
                await update.message.reply_text("❌ Введите число: 1, 2 или 3!")
            return
        
        # --- КОМАНДЫ В ИГРЕ ---
        elif text in ["забрать", "выйти", "забрать выигрыш"]:
            if uid not in games:
                await update.message.reply_text("❌ Нет активной игры!\nНачните: мины")
                return
            
            game = games[uid]
            if game.opened == 0:
                await update.message.reply_text("❌ Откройте хотя бы 1 клетку!")
                return
            
            if game.game_over:
                await update.message.reply_text("❌ Игра уже окончена!")
                return
            
            win = game.cashout()
            user["balance"] += win
            user["games_won"] += 1
            user["total_won"] += win
            
            await update.message.reply_text(
                f"💰 ЗАБРАЛ x{calc_multiplier(game.opened, game.total_cells, game.mines_count)}!\n"
                f"+{win} мун на баланс!\n\n"
                f"`{game.get_field()}`\n\n"
                f"Баланс: {user['balance']} мун"
            )
            
            del games[uid]
            return
        
        elif text in ["поле", "показать", "карта"]:
            if uid not in games:
                await update.message.reply_text("❌ Нет активной игры!\nНачните: мины")
                return
            
            game = games[uid]
            await update.message.reply_text(
                f"`{game.get_field()}`\n\n"
                f"💰 Множитель: x{calc_multiplier(game.opened, game.total_cells, game.mines_count)}\n"
                f"💎 Открыто: {game.opened}/{game.total_safe}\n"
                f"⚫️ Мин: {game.mines_count}\n"
                f"Баланс: {user['balance']} мун"
            )
            return
        
        elif text in ["новая", "новая игра", "перезапуск"]:
            if uid in games:
                del games[uid]
            
            if user["balance"] < BET_AMOUNT:
                await update.message.reply_text(f"❌ Недостаточно мун!\nБаланс: {user['balance']} мун\nВозьми: бонус")
                return
            
            await update.message.reply_text(
                f"🎮 НОВАЯ ИГРА! Ставка: {BET_AMOUNT} мун\n\nВведите количество мин (1-10):"
            )
            
            pending_actions[uid] = "choosing_mines"
            return
        
        # --- КООРДИНАТЫ В ИГРЕ ---
        elif uid in games:
            game = games[uid]
            if game.game_over:
                await update.message.reply_text("❌ Игра окончена!\nНачните новую: новая")
                return
            
            try:
                coords = text.split()
                if len(coords) != 2:
                    await update.message.reply_text("❌ Введите 2 числа через пробел (например, '1 2')")
                    return
                
                r, c = int(coords[0]) - 1, int(coords[1]) - 1  # 1-indexed -> 0-indexed
                
                if r < 0 or r >= game.size or c < 0 or c >= game.size:
                    await update.message.reply_text(f"❌ Введите числа от 1 до {game.size}!")
                    return
                
                result = game.reveal(r, c)
                
                if result == "mine":
                    await update.message.reply_text(
                        f"💥 БОМБА! -{BET_AMOUNT} мун\n\n"
                        f"`{game.get_field()}`\n\n"
                        f"Открыл: {game.opened} клеток\n"
                        f"Баланс: {user['balance']} мун"
                    )
                    del games[uid]
                elif result == "win":
                    win = int(game.bet * calc_multiplier(game.opened, game.total_cells, game.mines_count))
                    user["balance"] += win
                    user["games_won"] += 1
                    user["total_won"] += win
                    await update.message.reply_text(
                        f"🎉 ВСЕ КЛЕТКИ! x{calc_multiplier(game.opened, game.total_cells, game.mines_count)}\n"
                        f"+{win} мун на баланс!\n\n"
                        f"`{game.get_field()}`\n\n"
                        f"Баланс: {user['balance']} мун"
                    )
                    del games[uid]
                else:
                    await update.message.reply_text(
                        f"`{game.get_field()}`\n\n"
                        f"💰 Множитель: x{calc_multiplier(game.opened, game.total_cells, game.mines_count)}\n"
                        f"💎 Открыто: {game.opened}/{game.total_safe}\n"
                        f"Баланс: {user['balance']} мун"
                    )
            except ValueError:
                await update.message.reply_text("❌ Введите 2 числа через пробел (например, '1 2')")
            return
        
        # --- НЕИЗВЕСТНАЯ КОМАНДА ---
        else:
            await update.message.reply_text(
                "🎮 Неизвестная команда!\n"
                "Попробуйте: помощь"
            )

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()