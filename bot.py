import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

games = {}

class MinesweeperGame:
    def __init__(self, size=8, mines=10):
        self.size = size
        self.mines_count = mines
        self.board = [[0] * size for _ in range(size)]
        self.revealed = [[False] * size for _ in range(size)]
        self.flagged = [[False] * size for _ in range(size)]
        self.game_over = False
        self.won = False
        self.place_mines()
        self.calculate_numbers()
    
    def place_mines(self):
        mines_placed = 0
        while mines_placed < self.mines_count:
            r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
            if self.board[r][c] != -1:
                self.board[r][c] = -1
                mines_placed += 1
    
    def calculate_numbers(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == -1: continue
                count = 0
                for dr in [-1,0,1]:
                    for dc in [-1,0,1]:
                        if dr==0 and dc==0: continue
                        nr, nc = r+dr, c+dc
                        if 0<=nr<self.size and 0<=nc<self.size and self.board[nr][nc]==-1:
                            count += 1
                self.board[r][c] = count
    
    def reveal(self, r, c):
        if self.game_over or self.revealed[r][c] or self.flagged[r][c]: return
        self.revealed[r][c] = True
        if self.board[r][c] == -1:
            self.game_over = True
            return
        if self.board[r][c] == 0:
            for dr in [-1,0,1]:
                for dc in [-1,0,1]:
                    self.reveal(r+dr, c+dc)
        self.check_win()
    
    def check_win(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] != -1 and not self.revealed[r][c]: return
        self.won = self.game_over = True
    
    def get_keyboard(self):
        buttons = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    text = "💣" if self.board[r][c]==-1 else ("·" if self.board[r][c]==0 else str(self.board[r][c]))
                elif self.flagged[r][c]: text = ""
                else: text = "⬜"
                row.append(InlineKeyboardButton(text, callback_data=f"{r}_{c}"))
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🔄 Новая игра", callback_data="new")])
        return InlineKeyboardMarkup(buttons)

async def start(update: Update, context):
    games[update.effective_user.id] = MinesweeperGame()
    await update.message.reply_text("🎮 Сапёр! Жми на клетки", reply_markup=games[update.effective_user.id].get_keyboard())

async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if query.data == "new":
        games[uid] = MinesweeperGame()
        await query.edit_message_text(" Новая игра!", reply_markup=games[uid].get_keyboard())
        return
    if uid not in games: games[uid] = MinesweeperGame()
    game = games[uid]
    r, c = map(int, query.data.split("_"))
    game.reveal(r, c)
    status = "🎉 Победа!" if game.won else ("💥 Проигрыш!" if game.game_over else "🎮 Играй!")
    await query.edit_message_text(status, reply_markup=game.get_keyboard())

async def main():
    app = Application.builder().token(os.environ.get('TELEGRAM_BOT_TOKEN')).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button))
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())