from flask import Flask, render_template, jsonify, request, session
import random
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = "CHANGE_TO_YOUR_SECRET_KEY_HERE"  # 任意の文字列に変更
JST = timezone(timedelta(hours=9))
DATA_FILE = "../kn_points_data.json"

FINAL_MULTIPLIER = {
    1: 250_000.0, 2: 400_000.0, 3: 650_000.0, 4: 1_000_000.0, 5: 1_600_000.0,
    6: 2_600_000.0, 7: 4_200_000.0, 8: 6_800_000.0, 9: 11_000_000.0, 10: 18_000_000.0,
    11: 30_000_000.0, 12: 50_000_000.0, 13: 85_000_000.0, 14: 150_000_000.0, 15: 270_000_000.0,
    16: 500_000_000.0, 17: 1_000_000_000.0, 18: 2_500_000_000.0, 19: 6_000_000_000.0, 20: 20_000_000_000.0,
    21: 80_000_000_000.0, 22: 350_000_000_000.0, 23: 2_000_000_000_000.0, 24: 50_000_000_000_000.0,
}

def load_points():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_points(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# アクティブなゲームとトークン管理
active_games = {}
user_tokens = {}  # token -> user_id

@app.route("/")
def index():
    return "✅ サーバー稼働中 / Discordからボタンを押して開始してください"

# Discordから呼ばれる：ユーザー専用トークン発行
@app.route("/create-session", methods=["POST"])
def create_session():
    data = request.json
    user_id = str(data.get("user_id"))
    
    # ユーザー専用トークン発行
    token = str(uuid.uuid4())
    user_tokens[token] = user_id
    
    # 古いゲームは削除
    if user_id in active_games:
        del active_games[user_id]
    
    return jsonify({
        "success": True,
        "session_url": f"/game/{token}"
    })

# 個人用ゲームページ
@app.route("/game/<token>")
def game_page(token):
    if token not in user_tokens:
        return "❌ 無効なリンクです / Discordから再度ボタンを押してください", 404
    return render_template("mines.html", token=token)

# ゲーム開始
@app.route("/start", methods=["POST"])
def start_game():
    data = request.json
    token = data.get("token")
    
    if token not in user_tokens:
        return jsonify({"error": "セッションが無効です"}), 400
    user_id = user_tokens[token]
    
    bombs = int(data.get("bombs", 5))
    bet_input = str(data.get("bet", "100"))

    # 単位変換
    UNIT_SCALE = {
        "無量大数": 10**68, "那由多": 10**64, "不可思議": 10**60,
        "阿僧祇": 10**56, "恒河沙": 10**52, "極": 10**48,
        "載": 10**44, "正": 10**40, "澗": 10**36, "溝": 10**32,
        "穣": 10**28, "𥝱": 10**24, "垓": 10**20, "京": 10**16,
        "兆": 10**12, "億": 10**8, "万": 10**4, "千": 10**3,
        "百": 10**2, "十": 10**1,
    }
    bet_value = bet_input
    for unit, scale in UNIT_SCALE.items():
        if unit in bet_input:
            num_part = bet_input.replace(unit, "").strip()
            try:
                bet_value = int(float(num_part) * scale)
                break
            except:
                bet_value = 0
    if not isinstance(bet_value, int):
        try:
            bet_value = int(float(bet_input))
        except:
            bet_value = 0

    points_data = load_points()
    balance = points_data.get("points", {}).get(user_id, 0)
    
    if bet_input.strip() == "オールベット":
        bet_value = balance
    
    if bet_value <= 0 or bet_value > balance:
        return jsonify({"error": "ポイントが足りないか、無効な金額です"}), 400

    grid = [False] * 25
    for p in random.sample(range(25), bombs):
        grid[p] = True

    active_games[user_id] = {
        "bombs": bombs,
        "bet": bet_value,
        "grid": grid,
        "opened": [False] * 25,
        "opened_count": 0,
        "multiplier": 1.0,
        "game_over": False,
    }

    points_data["points"][user_id] = balance - bet_value
    save_points(points_data)

    return jsonify({
        "success": True,
        "balance": points_data["points"][user_id],
        "user_id": user_id
    })

# マスを開く
@app.route("/open", methods=["POST"])
def open_cell():
    data = request.json
    token = data.get("token")
    idx = int(data.get("index"))
    
    if token not in user_tokens:
        return jsonify({"error": "セッションが無効です"}), 400
    user_id = user_tokens[token]

    if user_id not in active_games:
        return jsonify({"error": "ゲームが見つかりません"}), 404
    game = active_games[user_id]

    if game["game_over"] or game["opened"][idx]:
        return jsonify({"error": "無効な操作です"}), 400

    game["opened"][idx] = True

    if game["grid"][idx]:
        # 爆弾
        game["game_over"] = True
        points_data = load_points()
        balance = points_data["points"].get(user_id, 0)
        del active_games[user_id]
        return jsonify({
            "result": "lose",
            "cell": idx,
            "balance": balance,
            "all_bombs": [i for i, b in enumerate(game["grid"]) if b]
        })

    # 成功
    game["opened_count"] += 1
    safe = 25 - game["bombs"]
    
    if game["opened_count"] >= safe:
        game["multiplier"] = FINAL_MULTIPLIER[game["bombs"]]
        game["game_over"] = True
        win = int(game["bet"] * game["multiplier"])
        points_data = load_points()
        points_data["points"][user_id] = points_data["points"].get(user_id, 0) + win
        save_points(points_data)
        balance = points_data["points"][user_id]
        del active_games[user_id]
        return jsonify({
            "result": "win",
            "multiplier": game["multiplier"],
            "amount": win,
            "balance": balance
        })
    else:
        ratio = game["opened_count"] / safe
        game["multiplier"] = round(1.0 + (FINAL_MULTIPLIER[game["bombs"]] - 1.0) * ratio ** 2.2, 2)

    return jsonify({
        "result": "continue",
        "multiplier": game["multiplier"],
        "opened_count": game["opened_count"]
    })

# 換金
@app.route("/cashout", methods=["POST"])
def cashout():
    data = request.json
    token = data.get("token")
    
    if token not in user_tokens:
        return jsonify({"error": "セッションが無効です"}), 400
    user_id = user_tokens[token]
    
    if user_id not in active_games:
        return jsonify({"error": "ゲームが見つかりません"}), 404
    game = active_games[user_id]
    
    if game["opened_count"] == 0:
        return jsonify({"error": "1マス以上開けてください"}), 400

    game["game_over"] = True
    win = int(game["bet"] * game["multiplier"])
    points_data = load_points()
    points_data["points"][user_id] = points_data["points"].get(user_id, 0) + win
    save_points(points_data)
    balance = points_data["points"][user_id]
    del active_games[user_id]

    return jsonify({
        "result": "cashout",
        "multiplier": game["multiplier"],
        "amount": win,
        "balance": balance
    })

# 残高確認
@app.route("/balance", methods=["POST"])
def get_balance():
    data = request.json
    token = data.get("token")
    if token not in user_tokens:
        return jsonify({"error": "無効"}), 400
    user_id = user_tokens[token]
    points_data = load_points()
    return jsonify({
        "balance": points_data["points"].get(user_id, 0)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
