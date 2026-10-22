from flask import Flask, render_template, jsonify, request
import random
import json
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
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

active_games = {}

@app.route("/")
def index():
    return render_template("mines.html")

@app.route("/start", methods=["POST"])
def start_game():
    data = request.json
    user_id = str(data.get("user_id"))
    bombs = int(data.get("bombs", 5))
    bet = int(data.get("bet", 100))

    points_data = load_points()
    balance = points_data.get("points", {}).get(user_id, 0)
    if bet <= 0 or bet > balance:
        return jsonify({"error": "ポイントが足りません"}), 400

    grid = [False] * 25
    for p in random.sample(range(25), bombs):
        grid[p] = True

    active_games[user_id] = {
        "bombs": bombs,
        "bet": bet,
        "grid": grid,
        "opened": [False] * 25,
        "opened_count": 0,
        "multiplier": 1.0,
        "game_over": False,
    }

    return jsonify({
        "success": True,
        "balance": balance - bet,
        "game_id": user_id
    })

@app.route("/open", methods=["POST"])
def open_cell():
    data = request.json
    user_id = str(data.get("user_id"))
    idx = int(data.get("index"))

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
        points_data["points"][user_id] = points_data["points"].get(user_id, 0) - game["bet"]
        save_points(points_data)
        del active_games[user_id]
        return jsonify({
            "result": "lose",
            "cell": idx,
            "balance": points_data["points"][user_id]
        })

    # 成功
    game["opened_count"] += 1
    safe = 25 - game["bombs"]
    if game["opened_count"] >= safe:
        game["multiplier"] = FINAL_MULTIPLIER[game["bombs"]]
        game["game_over"] = True
        win = int(game["bet"] * game["multiplier"])
        points_data = load_points()
        points_data["points"][user_id] = points_data["points"].get(user_id, 0) - game["bet"] + win
        save_points(points_data)
        del active_games[user_id]
        return jsonify({
            "result": "win",
            "multiplier": game["multiplier"],
            "amount": win,
            "balance": points_data["points"][user_id]
        })
    else:
        ratio = game["opened_count"] / safe
        game["multiplier"] = round(1.0 + (FINAL_MULTIPLIER[game["bombs"]] - 1.0) * ratio ** 2.2, 2)

    return jsonify({
        "result": "continue",
        "multiplier": game["multiplier"],
        "opened_count": game["opened_count"]
    })

@app.route("/cashout", methods=["POST"])
def cashout():
    data = request.json
    user_id = str(data.get("user_id"))
    if user_id not in active_games:
        return jsonify({"error": "ゲームが見つかりません"}), 404

    game = active_games[user_id]
    if game["opened_count"] == 0:
        return jsonify({"error": "1マス以上開けてください"}), 400

    game["game_over"] = True
    win = int(game["bet"] * game["multiplier"])
    points_data = load_points()
    points_data["points"][user_id] = points_data["points"].get(user_id, 0) - game["bet"] + win
    save_points(points_data)
    del active_games[user_id]

    return jsonify({
        "result": "cashout",
        "multiplier": game["multiplier"],
        "amount": win,
        "balance": points_data["points"][user_id]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
