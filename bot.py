import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

games = {}

class MinesweeperGame:
    def __init__(self, size=8, mines=10):
        self.size = size
        self.mines_count = mines
        self.board = [[0]*size for _ in range(size)]
        self.revealed = [[False]*size for _ in range(size)]
        self.flagged = [[False]*size for _ in range(size)]
        self.game_over = False
        self.won = False
        self.place_mines()
        self.calc_numbers()
    
    def place_mines(self):
        placed = 0
        while placed < self.mines_count:
            r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
            if self.board[r][c] != -1:
                self.board[r][c] = -1
                placed += 1
    
    def calc_numbers(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == -1: continue
                cnt = 0
                for dr in [-1,0,1]:
                    for dc in [-1,0,1]:
                        if dr==0 and dc==0: continue
                        nr, nc = r+dr, c+dc
                        if 0<=nr<self.size and 0<=nc<self.size and self.board[nr][nc]==-1:
                            cnt += 1
                self.board[r][c] = cnt
    
    def reveal(self, r, c):
        if self.game_over or self.revealed[r][c] or self.flagged[r][c]: return
        self.revealed[r][c] = True
        if self.board[r][c] == -1:
            self.game_over = True
            return
        if self.board[r][c] == 0:
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    nr, nc = r+dr, c+dc
                    if 0<=nr<self.size and 0<=nc<self.size:
                        self.reveal(nr, nc)
        self.check_win()
    
    def check_win(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] != -1 and not self.revealed[r][c]: return
        self.won = True
        self.game_over = True
    
    def toggle_flag(self, r, c):
        if self.game_over or self.revealed[r][c]: return
        self.flagged[r][c] = not self.flagged[r][c]
    
    def get_keyboard(self):
        buttons = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    if self.board[r][c] == -1: text = "💣"
                    elif self.board[r][c] == 0: text = ""
                    else: text = str(self.board[r][c])
                elif self.flagged[r][c]: text = "🚩"
                else: text = "⬜"
                row.append(InlineKeyboardButton(text, callback_data=f"c_{r}_{c}"))
            buttons.append(row)
        buttons.append([
            InlineKeyboardButton("🔄 Новая", callback_data="new"),
            InlineKeyboardButton(" Флаг", callback_data="flag_mode")
        ])
        return InlineKeyboardMarkup(buttons)
    
    def get_status(self):
        if self.game_over:
            return "💥 Проигрыш! Мина!" if not self.won else "🎉 Победа!"
        return "🎮 Сапёр. Жми клетки!"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    games[uid] = MinesweeperGame()
    await update.message.reply_text(
        "🎮 Сапёр!\n⬜ - клетка, 💣 - мина, 🚩 - флаг\nЖми на клетки!",
        reply_markup=games[uid].get_keyboard()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    
    if uid not in games:
        games[uid] = MinesweeperGame()
    game = games[uid]
    
    if data == "new":
        games[uid] = MinesweeperGame()
        await query.edit_message_text("🔄 Новая игра!", reply_markup=games[uid].get_keyboard())
        return
    
    if data == "flag_mode":
        context.user_data[uid] = True
        await query.answer("Режим флага! Жми на клетку 🚩")
        return
    
    r, c = map(int, data.split("_")[1:])
    
    if context.user_data.get(uid):
        game.toggle_flag(r, c)
        context.user_data[uid] = False
    else:
        game.reveal(r, c)
    
    await query.edit_message_text(game.get_status(), reply_markup=game.get_keyboard())

def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()