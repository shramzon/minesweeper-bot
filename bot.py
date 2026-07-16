import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

games = {}

class MinesweeperGame:
    def __init__(self, user_id, size=8, mines=10):
        self.user_id = user_id
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
            r = random.randint(0, self.size - 1)
            c = random.randint(0, self.size - 1)
            if self.board[r][c] != -1:
                self.board[r][c] = -1
                mines_placed += 1
    
    def calculate_numbers(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == -1:
                    continue
                count = 0
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.size and 0 <= nc < self.size:
                            if self.board[nr][nc] == -1:
                                count += 1
                self.board[r][c] = count
    
    def reveal(self, r, c):
        if self.game_over or self.revealed[r][c] or self.flagged[r][c]:
            return
        
        self.revealed[r][c] = True
        
        if self.board[r][c] == -1:
            self.game_over = True
            for i in range(self.size):
                for j in range(self.size):
                    if self.board[i][j] == -1:
                        self.revealed[i][j] = True
            return
        
        if self.board[r][c] == 0:
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.size and 0 <= nc < self.size:
                        if not self.revealed[nr][nc] and not self.flagged[nr][nc]:
                            self.reveal(nr, nc)
        
        self.check_win()
    
    def toggle_flag(self, r, c):
        if self.game_over or self.revealed[r][c]:
            return
        self.flagged[r][c] = not self.flagged[r][c]
    
    def check_win(self):
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] != -1 and not self.revealed[r][c]:
                    return
        self.won = True
        self.game_over = True
    
    def get_keyboard(self):
        buttons = []
        for r in range(self.size):
            row = []
            for c in range(self.size):
                if self.revealed[r][c]:
                    if self.board[r][c] == -1:
                        text = ""
                    elif self.board[r][c] == 0:
                        text = "·"
                    else:
                        text = str(self.board[r][c])
                    row.append(InlineKeyboardButton(text, callback_data=f"r_{r}_{c}"))
                elif self.flagged[r][c]:
                    row.append(InlineKeyboardButton("🚩", callback_data=f"f_{r}_{c}"))
                else:
                    row.append(InlineKeyboardButton("⬜", callback_data=f"c_{r}_{c}"))
            buttons.append(row)
        
        if not self.game_over:
            buttons.append([
                InlineKeyboardButton("🔄 Новая игра", callback_data="new"),
                InlineKeyboardButton("🏴 Флаг", callback_data="mode_flag")
            ])
        
        return InlineKeyboardMarkup(buttons)
    
    def get_message(self):
        if self.game_over:
            if self.won:
                return " Поздравляю! Вы победили!"
            else:
                return "💥 Бум! Вы наступили на мину!"
        return "🎮 Играем! Нажимайте на клетки"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    games[user_id] = MinesweeperGame(user_id)
    
    await update.message.reply_text(
        "🎮 Добро пожаловать в Сапёр!\n\n"
        "Нажимайте на клетки, чтобы открыть их.\n"
        "Цифры показывают количество мин рядом.\n"
        "Избегайте мин 💣!\n\n"
        "Используйте кнопку 'Флаг' чтобы отмечать мины.",
        reply_markup=games[user_id].get_keyboard()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "new":
        games[user_id] = MinesweeperGame(user_id)
        await query.edit_message_text(
            games[user_id].get_message(),
            reply_markup=games[user_id].get_keyboard()
        )
        return
    
    if data == "mode_flag":
        context.user_data['flag_mode'] = True
        await query.answer("Режим флага активирован! Нажмите на клетку.")
        return
    
    if user_id not in games:
        games[user_id] = MinesweeperGame(user_id)
    
    game = games[user_id]
    
    if game.game_over:
        await query.edit_message_text(
            game.get_message(),
            reply_markup=game.get_keyboard()
        )
        return
    
    action, r, c = data.split('_')
    r, c = int(r), int(c)
    
    flag_mode = context.user_data.get('flag_mode', False)
    
    if action == 'c':
        if flag_mode:
            game.toggle_flag(r, c)
            context.user_data['flag_mode'] = False
        else:
            game.reveal(r, c)
    elif action == 'f':
        game.toggle_flag(r, c)
    
    await query.edit_message_text(
        game.get_message(),
        reply_markup=game.get_keyboard()
    )

async def main():
    TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())