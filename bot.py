import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

games = {}

class MinesGame:
    def __init__(self, size=5, mines=3):
        self.size = size
        self.mines_count = mines
        self.board = [[False]*size for _ in range(size)]
        self.revealed = [[False]*size for _ in range(size)]
        self.game_over = False
        self.won = False
        self.opened = 0
        self.total_safe = size*size - mines
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
    
    def get_multiplier(self):
        if self.opened == 0:
            return 1.0
        return round(1 + (self.opened * 0.5), 2)
    
    def get_keyboard(self):
        buttons = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    if self.board[r][c]:
                        text = ""
                    else:
                        text = ""
                else:
                    text = "⬜"
                row.append(InlineKeyboardButton(text, callback_data=f"{r}_{c}"))
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton(f"💰 Забрать x{self.get_multiplier()}", callback_data="cashout")])
        buttons.append([InlineKeyboardButton("🔄 Новая игра", callback_data="new")])
        
        return InlineKeyboardMarkup(buttons)
    
    def get_status(self):
        if self.game_over:
            if self.won:
                return f"🎉 ПОБЕДА! Открыл все {self.total_safe} клеток!\n💰 Выигрыш: x{self.get_multiplier()}"
            else:
                return f"💥 БОМБА! Проигрыш!\nОткрыл клеток: {self.opened}"
        return f"🎮 Открыто: {self.opened}/{self.total_safe}\n💰 Множитель: x{self.get_multiplier()}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    games[uid] = MinesGame(size=5, mines=3)
    await update.message.reply_text(
        " МИНЫ! Как в казино!\n\n"
        "⬜ - закрытая клетка\n"
        "💎 - безопасно (открыл)\n"
        "💣 - мина (проигрыш)\n\n"
        "Открывай клетки, избегай мин!\n"
        "Чем больше открыл - тем больше выигрыш!\n"
        "Забери выигрыш в любой момент!",
        reply_markup=games[uid].get_keyboard()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    
    if uid not in games:
        games[uid] = MinesGame()
    game = games[uid]
    
    if data == "new":
        games[uid] = MinesGame(size=5, mines=3)
        await query.edit_message_text("🔄 Новая игра! Удачи!", reply_markup=games[uid].get_keyboard())
        return
    
    if data == "cashout":
        if game.opened > 0 and not game.game_over:
            await query.edit_message_text(
                f"💰 Забрал выигрыш x{game.get_multiplier()}!\nОткрыл клеток: {game.opened}",
                reply_markup=game.get_keyboard()
            )
            game.game_over = True
            game.won = True
        return
    
    if game.game_over:
        await query.answer("Игра окончена! Начни новую 🔄")
        return
    
    r, c = map(int, data.split("_"))
    result = game.reveal(r, c)
    
    if result == "mine":
        await query.edit_message_text(game.get_status(), reply_markup=game.get_keyboard())
    elif result == "win":
        await query.edit_message_text(game.get_status(), reply_markup=game.get_keyboard())
    else:
        await query.edit_message_text(game.get_status(), reply_markup=game.get_keyboard())

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()