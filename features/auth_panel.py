import discord
from discord import app_commands
from core.common import is_owner
from core.database import get_connection

# ========== パネル保存/読み込み ==========
def save_auth_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO auth_panel (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_auth_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM auth_panel
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
class AuthPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ 鯖メン認証",
        style=discord.ButtonStyle.primary,
        custom_id="auth:get"
    )
    async def get_role(self, itx: discord.Interaction, btn: discord.ui.Button):
        role = discord.utils.get(itx.guild.roles, name="鯖メン")
        if not role:
            await itx.response.send_message("❌ 「鯖メン」ロールが存在しません。先にロールを作成してください。", ephemeral=True)
            return
        if role in itx.user.roles:
            await itx.response.send_message("✅ 既に認証済みです！", ephemeral=True)
            return
        await itx.user.add_roles(role)
        await itx.response.send_message(f"✅ 「鯖メン」ロールを付与しました！", ephemeral=True)

    @discord.ui.button(
        label="✏️ パネル編集",
        style=discord.ButtonStyle.secondary,
        custom_id="auth:edit"
    )
    async def edit_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_auth_panel()
        default_title = latest["title"] if latest else "🔐 サーバー認証"
        default_desc = latest["description"] if latest else "⬇️のボタンを押して「鯖メン」ロールを取得してください。\n取得後鯖全体を閲覧できます。"

        class AuthEditModal(discord.ui.Modal, title="認証パネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title)
            desc_in = discord.ui.TextInput(
                label="説明", style=discord.TextStyle.long,
                default=default_desc
            )
            async def on_submit(self, inter: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0x2ecc71
                )
                await inter.response.edit_message(embed=embed, view=AuthPanelView())
                save_auth_panel(
                    inter.channel_id,
                    inter.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0x2ecc71
                )
                await inter.followup.send("✅ 更新・保存完了", ephemeral=True)

        await itx.response.send_modal(AuthEditModal())

    @discord.ui.button(
        label="🔄 パネル更新",
        style=discord.ButtonStyle.secondary,
        custom_id="auth:refresh"
    )
    async def refresh_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_auth_panel()
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
    if bot is not None and not hasattr(bot, "_auth_panel_registered"):
        bot.add_view(AuthPanelView())
        bot._auth_panel_registered = True
        print("✅ auth_panel 永続View登録完了")

    @tree.command(name="認証パネル設置", description="鯖認証パネル設置（オーナー専用）")
    async def cmd_auth_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="🔐 サーバー認証",
            description="下のボタンを押して「鯖メン」ロールを取得してください。",
            color=0x2ecc71
        )
        await itx.response.send_message(embed=embed, view=AuthPanelView())
        msg = await itx.original_response()
        save_auth_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
