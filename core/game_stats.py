import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "kn_server.db")

def init_stats():
    """テーブルがなければ作成する"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS game_stats (
        game_key TEXT PRIMARY KEY,
        play_count INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()
    print("✅ game_stats テーブル確認/作成完了")

def increment(game_key: str) -> int:
    """ユーザーに関係なく全体で+1"""
    # 初回は自動的にテーブル作成
    init_stats()
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO game_stats (game_key, play_count) VALUES (?, 0)", (game_key,))
    cur.execute("UPDATE game_stats SET play_count = play_count + 1 WHERE game_key = ?", (game_key,))
    cur.execute("SELECT play_count FROM game_stats WHERE game_key = ?", (game_key,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else 1

def get_count(game_key: str) -> int:
    init_stats()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT play_count FROM game_stats WHERE game_key = ?", (game_key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

# ✅ ファイル読み込み時に自動実行 → テーブルを確実に作成
init_stats()
