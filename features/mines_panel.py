import discord
from discord import app_commands
import aiohttp
import re
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
HISTORY_FILE = "mines_history.json"

# ✅ ウェブサーバーのアドレス（自分の環境に合わせて変更）
WEB_BASE_URL = "https://app-6cfc7eb9.fadehost.app"

UNIT_SCALE = {
    "無量大数": 10**68, "那由多": 10**64, "不可思議": 10**60,
    "阿僧祇": 10**56, "恒河沙": 10**52, "極": 10**48,
    "載": 10**44, "正": 10**40, "澗": 10**36, "溝": 10**32,
    "穣": 10**28, "垓": 10**24, "京": 10**20, "兆": 10**16,
    "億": 10**12, "万": 10**8,
}

def parse_value(input_str: str, balance=0):
    s = input_str.strip()
    if s in ["オールベット", "全額", "allbet", "AllBet"]:
        return balance
    match = re.match(r"([0-9]*\.?[0-9]+)\s*([^\d\s]*)", s)
    if not match:
        try:
            return float(s)
        except ValueError:
            return None
    num_str = match.group(1)
    unit = match.group(2)
    try:
        num = float(num_str)
    except ValueError:
        return None
    if unit in UNIT_SCALE:
        return num * UNIT_SCALE[unit]
    return num

def format_value(val):
    val = float(val)
    for name, scale in reversed(list(UNIT_SCALE.items())):
        if val >= scale:
            return f"{val / scale:.2f} {name}"
    return f"{int(val):,}"

def load_points_all():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "points" not in data:
                data["points"] = {}
            return data
    except Exception:
        return {"points": {}}

def get_point_value(user_id):
    return load_points_all()["points"].get(str(user_id), 0)

def save_history_entry(entry):
    all_data = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            pass
    all_data.insert(0, entry)
    all_data = all_data[:200]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

# ==============================================
# ✅ メインパネル（永続：ウェブ版）
# ==============================================
class MinesWebStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💎 マインスを始める",
        style=discord.ButtonStyle.green,
        custom_id="mines_web_start_v3"
    )
    async def start_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.defer(ephemeral=True)

        try:
            # ウェブサーバーにセッション作成を要求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{WEB_BASE_URL}/create-session",
                    json={"user_id": str(inter.user.id)}
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"Status {resp.status}")
                    data = await resp.json()

            if not data.get("success"):
                raise Exception("Session creation failed")

            game_url = f"{WEB_BASE_URL}{data['session_url']}"

            # 本人だけにURLを表示
            await inter.followup.send(
                embed=discord.Embed(
                    title="💎 あなた専用ゲームページ",
                    description=(
                        f"👇 下のリンクからゲームを始めてください！\n"
                        f"{game_url}\n\n"
                        f"⚠️ このリンクは**あなた専用**です。他の人に教えないでください。\n"
                        f"💡 スマホからでも遊べます！"
                    ),
                    color=0x2ECC71
                ),
                ephemeral=True
            )

        except Exception as e:
            await inter.followup.send(
                embed=discord.Embed(
                    title="❌ エラー",
                    description=f"ゲームページの作成に失敗しました。\n{str(e)}\n"
                                f"ウェブサーバーが起動しているか確認してください。",
                    color=0xE74C3C
                ),
                ephemeral=True
            )

# ==============================================
# ✅ 管理用：パネル送信コマンド
# ==============================================
async def send_panel(inter: discord.Interaction):
    embed = discord.Embed(
        title="💎 マインスゲーム",
        description=(
            "下のボタンを押すと、あなた専用のゲームページが開きます！\n"
            "✅ Discordのチャンネル作成は不要です\n"
            "✅ スマホ・PCどちらからでもプレイ可能\n"
            "✅ 単位入力対応：100万 / 50兆 / オールベット"
        ),
        color=0xFFD700
    )
    embed.add_field(
        name="📊 ルール",
        value="💎 ダイヤを開けて倍率UP！\n💣 爆弾を踏むと負け\n💰 好きなタイミングで回収可能",
        inline=False
    )
    await inter.response.send_message(embed=embed, view=MinesWebStartView())

# ==============================================
# ✅ セットアップ
# ==============================================
async def setup(tree, bot):
    # 永続Viewを登録
    bot.add_view(MinesWebStartView())

    # コマンド登録
    @tree.command(
        name="マインスパネル",
        description="マインスの開始パネルを表示"
    )
    async def mines_panel_cmd(inter: discord.Interaction):
        await send_panel(inter)

    print("[MINES] ✅ ウェブ版セットアップ完了")
