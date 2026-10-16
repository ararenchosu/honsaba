import discord
from discord import app_commands
from core.common import is_owner
from core.database import get_connection
from features.lottery_panel import point_data

# ========== パネル保存/読み込み ==========
def save_login_bonus_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS login_bonus_panel (
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
        INSERT OR REPLACE INTO login_bonus_panel 
        (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_login_bonus_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM login_bonus_panel
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

class LoginBonusPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(
        label="🎁 ログインボーナス受取",
        style=discord.ButtonStyle.primary,
        custom_id="loginbonus:receive"
    )
    async def receive_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not point_data.can_receive_bonus_today(itx.user.id):
            await itx.response.send_message(
                "✅ 今日は既に受け取り済みです。また明日お待ちください✨",
                ephemeral=True
            )
            return
        point_data.mark_bonus_received(itx.user.id)
        new_points = point_data.add_points(itx.user.id, 100)
        await itx.response.send_message(
            f"🎉 ログインボーナス受け取り完了！\n"
            f"➕ 100ポイント 獲得✨\n"
            f"💳 現在のポイント：{new_points}ポイント",
            ephemeral=True
        )

    @discord.ui.button(
        label="✏️ パネル編集",
        style=discord.ButtonStyle.secondary,
        custom_id="loginbonus:edit"
    )
    async def edit_bonus_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        
        latest = get_latest_login_bonus_panel()
        default_title = latest["title"] if latest else "🎁 毎日ログインボーナス"
        default_desc = latest["description"] if latest else (
            "⬇️のボタンを押すと1日1回100ポイントがもらえます✨\n"
            "🗳 くじ引きとは別に受け取れます！"
        )
        
        class BonusEditModal(discord.ui.Modal, title="ログインボーナス編集"):
            title_in = discord.ui.TextInput(
                label="タイトル",
                default=default_title,
                required=True
            )
            desc_in = discord.ui.TextInput(
                label="説明文",
                style=discord.TextStyle.long,
                default=default_desc,
                required=True
            )
            
            async def on_submit(self, m_itx: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0x00FF7F
                )
                await m_itx.response.edit_message(embed=embed, view=LoginBonusPanelView())
                save_login_bonus_panel(
                    m_itx.channel_id,
                    m_itx.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0x00FF7F
                )
                await m_itx.followup.send("✅ 更新・保存完了", ephemeral=True)
        
        await itx.response.send_modal(BonusEditModal())

    @discord.ui.button(
        label="🔄 パネル更新",
        style=discord.ButtonStyle.secondary,
        custom_id="loginbonus:refresh"
    )
    async def refresh_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        
        latest = get_latest_login_bonus_panel()
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

# ✅ 引数をbot=Noneにしてmain.pyから呼び出せるように
async def setup(tree, bot=None):
    if bot is not None and not hasattr(bot, "_login_bonus_registered"):
        bot.add_view(LoginBonusPanelView())
        bot._login_bonus_registered = True
        print("✅ login_bonus 永続View登録完了")
    
    @tree.command(
        name="ログインボーナスパネル設置",
        description="ログインボーナスパネルを設置（オーナー専用）"
    )
    async def cmd_login_bonus_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎁 毎日ログインボーナス",
            description="⬇️のボタンを押すと1日1回 **100ポイント** がもらえます✨\n"
                        "🗳 くじ引きとは別に受け取れます！",
            color=0x00FF7F
        )
        await itx.response.send_message(embed=embed, view=LoginBonusPanelView())
        msg = await itx.original_response()
        save_login_bonus_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
