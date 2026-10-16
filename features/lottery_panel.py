import discord
from discord import app_commands
from core.common import is_owner
from core.database import get_connection
import json
import os
import random
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
LOTTERY_RESULT_CHANNEL_ID = 1558705232781906071
DATA_FILE = "kn_points_data.json"

# ========== パネル保存/読み込み ==========
def save_lottery_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lottery_panel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            color INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO lottery_panel 
        (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_lottery_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM lottery_panel
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    r = cur.fetchone()
    conn.close()
    if r:
        return {
            "channel_id": int(r[0]),
            "message_id": int(r[1]),
            "title": r[2],
            "description": r[3],
            "color": int(r[4])
        }
    return None

def save_point_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS point_panel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            color INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO point_panel 
        (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_point_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM point_panel
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    r = cur.fetchone()
    conn.close()
    if r:
        return {
            "channel_id": int(r[0]),
            "message_id": int(r[1]),
            "title": r[2],
            "description": r[3],
            "color": int(r[4])
        }
    return None

# ===========================================
class PointData:
    def __init__(self):
        self.points = {}
        self.last_lottery_draw = {}
        self.last_bonus_receive = {}
        self._load()

    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.points = data.get("points", {})
                    old_last = data.get("last_draw", {})
                    if not data.get("last_lottery_draw"):
                        self.last_lottery_draw = old_last
                    else:
                        self.last_lottery_draw = data.get("last_lottery_draw", {})
                    self.last_bonus_receive = data.get("last_bonus_receive", {})
            except Exception as e:
                print(f"⚠️ データ読み込みエラー: {e}")
                self.points = {}
                self.last_lottery_draw = {}
                self.last_bonus_receive = {}

    def _save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "points": self.points,
                "last_lottery_draw": self.last_lottery_draw,
                "last_bonus_receive": self.last_bonus_receive
            }, f, ensure_ascii=False, indent=2)

    def get_points(self, user_id):
        return self.points.get(str(user_id), 0)

    def add_points(self, user_id, amount):
        uid = str(user_id)
        self.points[uid] = self.get_points(user_id) + amount
        self._save()
        return self.points[uid]

    def can_lottery_today(self, user_id):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        return self.last_lottery_draw.get(str(user_id)) != today

    def mark_lottery_drew(self, user_id):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        self.last_lottery_draw[str(user_id)] = today
        self._save()

    def can_receive_bonus_today(self, user_id):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        return self.last_bonus_receive.get(str(user_id)) != today

    def mark_bonus_received(self, user_id):
        today = datetime.now(JST).strftime("%Y-%m-%d")
        self.last_bonus_receive[str(user_id)] = today
        self._save()

point_data = PointData()

LOTTERY_PRIZES = [
    {"name": "🎖️ 1等", "points": 100, "rate": 0.05},
    {"name": "🥈 2等", "points": 75,  "rate": 0.10},
    {"name": "🥉 3等", "points": 50,  "rate": 0.20},
    {"name": "🏅 4等", "points": 25,  "rate": 0.30},
    {"name": "🎀 5等", "points": 10,  "rate": 0.35},
]

class LotteryPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🗳 くじを引く！",
        style=discord.ButtonStyle.primary,
        custom_id="lottery:draw"
    )
    async def draw_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not point_data.can_lottery_today(itx.user.id):
            await itx.response.send_message(
                "❌ 今日は既にくじを引いています。また明日お試しください！",
                ephemeral=True
            )
            return
        r = random.random()
        cumulative = 0
        prize = None
        for p in LOTTERY_PRIZES:
            cumulative += p["rate"]
            if r < cumulative:
                prize = p
                break
        if prize is None:
            prize = LOTTERY_PRIZES[-1]
        point_data.mark_lottery_drew(itx.user.id)
        new_points = point_data.add_points(itx.user.id, prize["points"])
        await itx.response.send_message(
            f"🎉 {prize['name']} 当選！\n"
            f"➕ {prize['points']}ポイント 獲得✨\n"
            f"💳 現在のポイント：{new_points}ポイント",
            ephemeral=True
        )
        await send_lottery_result_embed(itx, prize, new_points)

    @discord.ui.button(
        label="🧪 通知テスト(オーナーのみ)",
        style=discord.ButtonStyle.secondary,
        custom_id="lottery:test",
        row=1
    )
    async def test_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ このボタンはオーナー専用です", ephemeral=True)
            return
        r = random.random()
        cumulative = 0
        prize = None
        for p in LOTTERY_PRIZES:
            cumulative += p["rate"]
            if r < cumulative:
                prize = p
                break
        if prize is None:
            prize = LOTTERY_PRIZES[-1]
        dummy_points = point_data.get_points(itx.user.id)
        await itx.response.send_message(
            f"🧪 テスト実行！\n"
            f"表示結果：{prize['name']}\n"
            f"⚠️ ポイント・抽選権には影響しません",
            ephemeral=True
        )
        await send_lottery_result_embed(itx, prize, dummy_points, is_test=True)

    @discord.ui.button(
        label="✏️ パネル編集",
        style=discord.ButtonStyle.secondary,
        custom_id="lottery:edit",
        row=2
    )
    async def edit_lottery_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_lottery_panel()
        default_title = latest["title"] if latest else "🗳 1日1回！くじ引き"
        default_desc = latest["description"] if latest else (
            "⬇️のボタンを押して1日1回くじが引けます✨\n"
            "🎖️1等:100pt / 🥈2等:75pt / 🥉3等:50pt / 🏅4等:25pt / 🎀5等:10pt"
        )
        class LotteryEditModal(discord.ui.Modal, title="くじパネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title, required=True)
            desc_in = discord.ui.TextInput(
                label="説明文", style=discord.TextStyle.long,
                default=default_desc, required=True
            )
            async def on_submit(self, m_itx: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0xFFD700
                )
                await m_itx.response.edit_message(embed=embed, view=LotteryPanelView())
                save_lottery_panel(
                    m_itx.channel_id,
                    m_itx.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0xFFD700
                )
                await m_itx.followup.send("✅ 更新・保存完了", ephemeral=True)
        await itx.response.send_modal(LotteryEditModal())

    @discord.ui.button(
        label="🔄 パネル更新",
        style=discord.ButtonStyle.secondary,
        custom_id="lottery:refresh",
        row=3
    )
    async def refresh_lottery(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_lottery_panel()
        if not latest:
            await itx.response.send_message("⚠️ 保存されたパネルが見つかりません", ephemeral=True)
            return
        embed = discord.Embed(
            title=latest["title"],
            description=latest["description"],
            color=latest["color"]
        )
        await itx.response.edit_message(embed=embed)
        await itx.followup.send("✅ パネルを最新に更新しました", ephemeral=True)

async def send_lottery_result_embed(itx, prize, total_points, is_test=False):
    result_channel = itx.client.get_channel(LOTTERY_RESULT_CHANNEL_ID)
    if not result_channel:
        print(f"⚠️ 結果通知チャンネルが見つかりません: {LOTTERY_RESULT_CHANNEL_ID}")
        return
    title = "🧪 【テスト】くじ引き結果" if is_test else "🗳 くじ引き結果"
    description = f"{itx.user.mention} がくじを引きました！"
    if is_test:
        description = f"{itx.user.mention} がテスト抽選を実行しました！\n⚠️ これはテストです（ポイント加算なし）"
    result_embed = discord.Embed(
        title=title,
        description=description,
        color=0x888888 if is_test else 0xFFD700,
        timestamp=datetime.now(JST)
    )
    result_embed.add_field(name="🎯 結果", value=prize["name"], inline=True)
    result_embed.add_field(name="✨ 獲得ポイント", value=f"{prize['points']}ポイント", inline=True)
    result_embed.add_field(name="💳 合計ポイント", value=f"{total_points}ポイント", inline=True)
    result_embed.set_thumbnail(url=itx.user.display_avatar.url)
    await result_channel.send(embed=result_embed)

class PointCheckPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="💳 ポイントを確認",
        style=discord.ButtonStyle.success,
        custom_id="points:check"
    )
    async def check_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        pts = point_data.get_points(itx.user.id)
        await itx.response.send_message(
            f"💳 {itx.user.mention} が現在持っているポイントは **{pts}ポイント** です✨",
            ephemeral=True
        )

    @discord.ui.button(
        label="✏️ パネル編集",
        style=discord.ButtonStyle.secondary,
        custom_id="points:edit"
    )
    async def edit_point_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_point_panel()
        default_title = latest["title"] if latest else "💰 ポイント確認"
        default_desc = latest["description"] if latest else (
            "⬇️のボタンを押すと現在のポイントが確認できます✨"
        )
        class PointEditModal(discord.ui.Modal, title="ポイントパネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title, required=True)
            desc_in = discord.ui.TextInput(
                label="説明文", style=discord.TextStyle.long,
                default=default_desc, required=True
            )
            async def on_submit(self, m_itx: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0x2ECC71
                )
                await m_itx.response.edit_message(embed=embed, view=PointCheckPanelView())
                save_point_panel(
                    m_itx.channel_id,
                    m_itx.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0x2ECC71
                )
                await m_itx.followup.send("✅ 更新・保存完了", ephemeral=True)
        await itx.response.send_modal(PointEditModal())

    @discord.ui.button(
        label="🔄 パネル更新",
        style=discord.ButtonStyle.secondary,
        custom_id="points:refresh"
    )
    async def refresh_point(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_point_panel()
        if not latest:
            await itx.response.send_message("⚠️ 保存されたパネルが見つかりません", ephemeral=True)
            return
        embed = discord.Embed(
            title=latest["title"],
            description=latest["description"],
            color=latest["color"]
        )
        await itx.response.edit_message(embed=embed)
        await itx.followup.send("✅ パネルを最新に更新しました", ephemeral=True)

# ✅ botを受け取って永続View登録
async def setup(tree, bot=None):
    if bot is not None and not hasattr(bot, "_lottery_panel_registered"):
        bot.add_view(LotteryPanelView())
        bot.add_view(PointCheckPanelView())
        bot._lottery_panel_registered = True
        print("✅ lottery_panel 永続View登録完了")

    @tree.command(name="くじ引きパネル設置", description="くじ引きパネルを設置（オーナー専用）")
    async def cmd_lottery_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="🗳 1日1回！くじ引き",
            description="⬇️のボタンを押して1日1回くじが引けます✨\n"
                        "🎖️1等:100pt / 🥈2等:75pt / 🥉3等:50pt / 🏅4等:25pt / 🎀5等:10pt",
            color=0xFFD700
        )
        await itx.response.send_message(embed=embed, view=LotteryPanelView())
        msg = await itx.original_response()
        save_lottery_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )

    @tree.command(name="ポイント確認パネル設置", description="ポイント確認パネルを設置（オーナー専用）")
    async def cmd_point_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="💰 ポイント確認",
            description="⬇️のボタンを押すと現在のポイントが確認できます✨",
            color=0x2ECC71
        )
        await itx.response.send_message(embed=embed, view=PointCheckPanelView())
        msg = await itx.original_response()
        save_point_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
