import discord
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner
JST = timezone(timedelta(hours=9))
PANEL_TABLE = "ranking_panels"
DATA_FILE = "kn_points_data.json"

# ========== ポイントを日本語表記に変換 — 最大・無量大数まで ==========
def format_points_jp(points: int) -> str:
    """
    日本の大数の単位で最大・無量大数まで表示
    万 → 億 → 兆 → 京 → 垓 → 𥝱 → 穣 → 溝 → 澗 → 正 → 載 → 極 →
    恒河沙 → 阿僧祇 → 那由他 → 不可思議 → 無量大数
    """
    if points < 10000:
        return f"{points:,}P"
    
    # 上から順に判定：10^4 ～ 10^68（無量大数）まで
    units = [
        (10**68, "無量大数"),
        (10**64, "不可思議"),
        (10**60, "那由他"),
        (10**56, "阿僧祇"),
        (10**52, "恒河沙"),
        (10**48, "極"),
        (10**44, "載"),
        (10**40, "正"),
        (10**36, "澗"),
        (10**32, "溝"),
        (10**28, "穣"),
        (10**24, "𥝱"),
        (10**20, "垓"),
        (10**16, "京"),
        (10**12, "兆"),
        (10**8,  "億"),
        (10**4,  "万"),
    ]
    
    result = ""
    remaining = points
    
    for scale, name in units:
        if remaining >= scale:
            val = remaining // scale
            result += f"{val:,}{name}"
            remaining = remaining % scale
    
    if remaining > 0:
        result += f"{remaining:,}"
    
    return f"{result}P"

# ========== データ読み込み ==========
def load_points_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("points", {})
    except Exception as e:
        print(f"⚠️ ポイントデータ読み込みエラー: {e}")
        return {}

# ========== DB処理 ==========
def init_db():
    from core.database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {PANEL_TABLE} (
            channel_id TEXT PRIMARY KEY,
            message_id TEXT,
            title TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_panel(channel_id):
    from core.database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT message_id, title, description FROM {PANEL_TABLE} WHERE channel_id = ?",
        (str(channel_id),)
    )
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    return {"message_id": r[0], "title": r[1], "description": r[2]}

def save_panel(channel_id, message_id, title, description):
    from core.database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        REPLACE INTO {PANEL_TABLE} (channel_id, message_id, title, description, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (str(channel_id), str(message_id), title, description))
    conn.commit()
    conn.close()

# ========== ランキング取得 ==========
def get_ranking(limit=10):
    points_dict = load_points_data()
    if not points_dict:
        return []
    return sorted(points_dict.items(), key=lambda x: x[1], reverse=True)[:limit]

def get_user_rank_and_points(user_id):
    uid = str(user_id)
    points_dict = load_points_data()
    if not points_dict or uid not in points_dict:
        return 0, 0
    sorted_list = sorted(points_dict.items(), key=lambda x: x[1], reverse=True)
    for idx, (user_id_str, pts) in enumerate(sorted_list, 1):
        if user_id_str == uid:
            return idx, pts
    return 0, 0

# ========== 埋め込み作成 ==========
def build_ranking_embed(title, description, guild: discord.Guild):
    ranking = get_ranking(10)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for idx, (uid, pts) in enumerate(ranking, 1):
        user = guild.get_member(int(uid))
        name = user.mention if user else f"ユーザーID:{uid}"
        prefix = medals[idx-1] if idx <= 3 else f" {idx}."
        pts_text = format_points_jp(pts)
        lines.append(f"{prefix} {name} ・・・ **{pts_text}**")
    if not lines:
        lines.append("まだポイントが記録されていません")
    embed = discord.Embed(
        title=title,
        description=description + "\n\n" + "\n".join(lines),
        color=0xFFD700,
        timestamp=datetime.now(JST)
    )
    embed.set_footer(text=f"最終更新: {datetime.now(JST).strftime('%H:%M:%S')}")
    return embed

# ========== View ==========
class RankingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(
        label="✏️ 内容編集",
        style=discord.ButtonStyle.secondary,
        custom_id="ranking:edit"
    )
    async def edit_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        panel_data = get_panel(itx.channel_id)
        if not panel_data:
            await itx.response.send_message("❌ 先にパネルを設置してください", ephemeral=True)
            return
        
        class RankingEditModal(discord.ui.Modal, title="ランキングパネル編集"):
            title_in = discord.ui.TextInput(
                label="パネルタイトル",
                default=panel_data["title"],
                required=True
            )
            desc_in = discord.ui.TextInput(
                label="説明文",
                default=panel_data["description"],
                style=discord.TextStyle.long,
                required=True
            )
            async def on_submit(self, m_itx: discord.Interaction):
                embed = build_ranking_embed(str(self.title_in), str(self.desc_in), m_itx.guild)
                try:
                    msg = await m_itx.channel.fetch_message(panel_data["message_id"])
                    await msg.edit(embed=embed)
                    save_panel(m_itx.channel_id, panel_data["message_id"], str(self.title_in), str(self.desc_in))
                    await m_itx.response.send_message("✅ 更新・保存完了", ephemeral=True)
                except Exception as e:
                    await m_itx.response.send_message(f"❌ 更新に失敗: {e}", ephemeral=True)
        
        await itx.response.send_modal(RankingEditModal())

    @discord.ui.button(
        label="🔄 今すぐ更新",
        style=discord.ButtonStyle.primary,
        custom_id="ranking:refresh"
    )
    async def refresh_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        panel_data = get_panel(itx.channel_id)
        if not panel_data:
            await itx.response.send_message("❌ パネル情報が見つかりません", ephemeral=True)
            return
        embed = build_ranking_embed(panel_data["title"], panel_data["description"], itx.guild)
        try:
            msg = await itx.channel.fetch_message(panel_data["message_id"])
            await msg.edit(embed=embed)
            await itx.response.send_message("✅ 最新に更新しました", ephemeral=True)
        except Exception as e:
            await itx.response.send_message(f"❌ 更新に失敗: {e}", ephemeral=True)

# ========== 自動更新タスク ==========
async def auto_update_task(client: discord.Client):
    await client.wait_until_ready()
    while not client.is_closed():
        now = datetime.now(JST)
        target = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait = (target - datetime.now(JST)).total_seconds()
        await asyncio.sleep(wait)
        
        from core.database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT channel_id, message_id, title, description FROM {PANEL_TABLE}")
        panels = cur.fetchall()
        conn.close()
        
        for ch_id, msg_id, title, desc in panels:
            try:
                channel = client.get_channel(int(ch_id))
                if not channel:
                    continue
                embed = build_ranking_embed(title, desc, channel.guild)
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed)
            except Exception as e:
                print(f"⚠️ ランキング自動更新エラー: {e}")
        
        await asyncio.sleep(60)

# ========== セットアップ ==========
async def setup_panel(channel):
    title = "🏆 ポイントランキング"
    desc = "現在のポイント上位10名を表示します✨"
    embed = build_ranking_embed(title, desc, channel.guild)
    view = RankingPanelView()
    msg = await channel.send(embed=embed, view=view)
    save_panel(channel.id, msg.id, title, desc)

async def setup(tree: app_commands.CommandTree, bot=None):
    init_db()
    
    if bot is not None and not hasattr(bot, "_ranking_views_registered"):
        bot.add_view(RankingPanelView())
        bot._ranking_views_registered = True
        print("✅ ranking_panel 永続View登録完了")
    
    if bot is not None and not hasattr(bot, "_ranking_task_started"):
        bot._ranking_task_started = True
        asyncio.create_task(auto_update_task(bot))
        print("✅ ranking_panel 自動更新タスク起動完了")
    
    @tree.command(
        name="ポイントランキングパネル設置",
        description="ポイントランキングパネルを設置（オーナー専用）"
    )
    async def cmd(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        await setup_panel(itx.channel)
        await itx.response.send_message("✅ ランキングパネルを設置しました", ephemeral=True)
