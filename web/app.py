from flask import Flask, render_template, jsonify, request
import random
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "CHANGE_TO_RANDOM_LONG_STRING_HERE"
JST = timezone(timedelta(hours=9))

# ✅ 絶対パスで指定：プロジェクトルートから確実に読み込む
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "kn_points_data.json")
HISTORY_FILE = os.path.join(BASE_DIR, "mines_history.json")

FINAL_MULTIPLIER = {
    1: 250_000.0, 2: 400_000.0, 3: 650_000.0, 4: 1_000_000.0, 5: 1_600_000.0,
    6: 2_600_000.0, 7: 4_200_000.0, 8: 6_800_000.0, 9: 11_000_000.0, 10: 18_000_000.0,
    11: 30_000_000.0, 12: 50_000_000.0, 13: 85_000_000.0, 14: 150_000_000.0, 15: 270_000_000.0,
    16: 500_000_000.0, 17: 1_000_000_000.0, 18: 2_500_000_000.0, 19: 6_000_000_000.0, 20: 20_000_000_000.0,
    21: 80_000_000_000.0, 22: 350_000_000_000.0, 23: 2_000_000_000_000.0, 24: 50_000_000_000_000.0,
}

UNIT_SCALE = {
    "無量大数": 10**68, "那由多": 10**64, "不可思議": 10**60,
    "阿僧祇": 10**56, "恒河沙": 10**52, "極": 10**48,
    "載": 10**44, "正": 10**40, "澗": 10**36, "溝": 10**32,
    "穣": 10**28, "垓": 10**24, "京": 10**20, "兆": 10**16,
    "億": 10**12, "万": 10**8,
}

def load_points():
    # 絶対パスで確実に読み込み
    if not os.path.exists(DATA_FILE):
        print(f"⚠️ ファイルが見つかりません: {DATA_FILE}")
        return {"points": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 読み込みエラー: {e}")
        return {"points": {}}

def save_points(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 保存エラー: {e}")

def parse_bet(bet_input, balance):
    s = str(bet_input).strip()
    if s in ["オールベット", "全額", "allbet", "AllBet"]:
        return balance
    for unit, scale in UNIT_SCALE.items():
        if unit in s:
            try:
                num_part = s.replace(unit, "").strip()
                return int(float(num_part) * scale)
            except:
                return None
    try:
        return int(float(s))
    except:
        return None

active_games = {}
user_tokens = {}

@app.route("/")
def index():
    return "✅ マインスサーバー稼働中 / Discordからボタンを押して開始"

@app.route("/create-session", methods=["POST"])
def create_session():
    data = request.json
    user_id = str(data.get("user_id"))
    token = str(uuid.uuid4())
    user_tokens[token] = user_id
    if user_id in active_games:
        del active_games[user_id]
    return jsonify({"success": True, "session_url": f"/game/{token}"})

@app.route("/game/<token>")
def game_page(token):
    if token not in user_tokens:
        return "❌ 無効なリンクです / Discordから再度ボタンを押してください", 404
    return render_template("mines.html", token=token)

@app.route("/start", methods=["POST"])
def start_game():
    data = request.json
    token = data.get("token")
    if token not in user_tokens:
        return jsonify({"error": "セッションが無効です"}), 400
    user_id = user_tokens[token]
    bombs = int(data.get("bombs", 5))
    bet_input = data.get("bet", "100")

    points_data = load_points()
    balance = points_data.get("points", {}).get(user_id, 0)
    bet_value = parse_bet(bet_input, balance)

    if bet_value is None or bet_value <= 0 or bet_value > balance:
        return jsonify({"error": "ポイントが足りないか金額が不正です"}), 400
    if not (1 <= bombs <= 24):
        return jsonify({"error": "爆弾数は1～24にしてください"}), 400

    grid = [False] * 25
    for p in random.sample(range(25), bombs):
        grid[p] = True

    active_games[user_id] = {
        "bombs": bombs, "bet": bet_value, "grid": grid,
        "opened": [False]*25, "opened_count": 0,
        "multiplier": 1.0, "game_over": False
    }

    points_data["points"][user_id] = balance - bet_value
    save_points(points_data)
    return jsonify({"success": True, "balance": points_data["points"][user_id]})

@app.route("/open", methods=["POST"])
def open_cell():
    data = request.json
    token = data.get("token")
    idx = int(data.get("index"))
    if token not in user_tokens:
        return jsonify({"error": "セッション無効"}), 400
    user_id = user_tokens[token]
    if user_id not in active_games:
        return jsonify({"error": "ゲームなし"}), 404
    g = active_games[user_id]

    if g["game_over"] or g["opened"][idx]:
        return jsonify({"error": "無効な操作"}), 400
    g["opened"][idx] = True

    if g["grid"][idx]:
        g["game_over"] = True
        all_bombs = [i for i, b in enumerate(g["grid"]) if b]
        points_data = load_points()
        bal = points_data["points"].get(user_id, 0)
        del active_games[user_id]
        return jsonify({"result": "lose", "balance": bal, "all_bombs": all_bombs})

    g["opened_count"] += 1
    safe = 25 - g["bombs"]
    if g["opened_count"] >= safe:
        g["multiplier"] = FINAL_MULTIPLIER[g["bombs"]]
        g["game_over"] = True
        win = int(g["bet"] * g["multiplier"])
        points_data = load_points()
        points_data["points"][user_id] = points_data["points"].get(user_id, 0) + win
        save_points(points_data)
        bal = points_data["points"][user_id]
        del active_games[user_id]
        return jsonify({"result": "win", "multiplier": g["multiplier"], "amount": win, "balance": bal})
    else:
        ratio = g["opened_count"] / safe
        g["multiplier"] = round(1.0 + (FINAL_MULTIPLIER[g["bombs"]] - 1.0) * ratio ** 2.2, 2)
        return jsonify({"result": "continue", "multiplier": g["multiplier"]})

@app.route("/cashout", methods=["POST"])
def cashout():
    data = request.json
    token = data.get("token")
    if token not in user_tokens:
        return jsonify({"error": "セッション無効"}), 400
    user_id = user_tokens[token]
    if user_id not in active_games:
        return jsonify({"error": "ゲームなし"}), 404
    g = active_games[user_id]
    if g["opened_count"] == 0:
        return jsonify({"error": "1マス以上開けてください"}), 400

    g["game_over"] = True
    win = int(g["bet"] * g["multiplier"])
    points_data = load_points()
    points_data["points"][user_id] = points_data["points"].get(user_id, 0) + win
    save_points(points_data)
    bal = points_data["points"][user_id]
    del active_games[user_id]
    return jsonify({"result": "cashout", "multiplier": g["multiplier"], "amount": win, "balance": bal})

@app.route("/balance", methods=["POST"])
def get_balance():
    data = request.json
    token = data.get("token")
    if token not in user_tokens:
        return jsonify({"error": "無効"}), 400
    user_id = user_tokens[token]
    points_data = load_points()
    return jsonify({"balance": points_data["points"].get(user_id, 0)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
