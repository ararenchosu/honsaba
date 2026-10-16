class OthelloBoard:
    def __init__(self):
        self.board = [[None for _ in range(8)] for _ in range(8)]
        self.current = "black"
        self.board[3][3] = "white"
        self.board[3][4] = "black"
        self.board[4][3] = "black"
        self.board[4][4] = "white"

    def put(self, row, col):
        if self.board[row][col] is not None:
            return False
        enemy = "white" if self.current == "black" else "black"
        flipped = []
        dirs = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]
        for dr, dc in dirs:
            r, c = row + dr, col + dc
            temp = []
            while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == enemy:
                temp.append((r, c))
                r += dr
                c += dc
            if temp and 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == self.current:
                flipped.extend(temp)
        if not flipped:
            return False
        self.board[row][col] = self.current
        for r, c in flipped:
            self.board[r][c] = self.current
        self.current = enemy
        return True

    def can_put(self, color):
        enemy = "white" if color == "black" else "black"
        for row in range(8):
            for col in range(8):
                if self.board[row][col] is not None:
                    continue
                dirs = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]
                for dr, dc in dirs:
                    r, c = row + dr, col + dc
                    count = 0
                    while 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == enemy:
                        count += 1
                        r += dr
                        c += dc
                    if count > 0 and 0 <= r < 8 and 0 <= c < 8 and self.board[r][c] == color:
                        return True
        return False

    def is_game_over(self):
        return not self.can_put("black") and not self.can_put("white")

    def count(self):
        b = sum(row.count("black") for row in self.board)
        w = sum(row.count("white") for row in self.board)
        return b, w

    def render(self):
        lines = []
        lines.append("    ａ ｂ ｃ ｄ ｅ ｆ ｇ ｈ")
        for i, row in enumerate(self.board):
            cells = []
            for cell in row:
                if cell == "black":
                    cells.append("⚫")
                elif cell == "white":
                    cells.append("⚪")
                else:
                    cells.append("⬜")
            lines.append(f"{i+1:2d}  " + "".join(cells))
        return "\n".join(lines)
