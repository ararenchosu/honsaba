import discord
from discord import app_commands
from core.common import is_owner
from core.database import get_connection

# ========== パネル保存/読み込み ==========
def init_role_revoke_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_revoke_panel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            color INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_role_revoke_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO role_revoke_panel 
        (channel_id, message_id, title, description, color, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_role_revoke_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM role_revoke_panel
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
def get_selectable_roles(guild_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role_id, role_name FROM select_roles WHERE guild_id=?", (str(guild_id),))
    result = cur.fetchall()
    conn.close()
    return result

class RoleRevokePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(label="🗑️ ロールを選択して外す", style=discord.ButtonStyle.danger, custom_id="revoke:remove")
    async def remove_role(self, itx: discord.Interaction, btn: discord.ui.Button):
        selectable_roles = get_selectable_roles(itx.guild_id)
        if not selectable_roles:
            await itx.response.send_message(
                "❌ 剥奪可能なロールが設定されていません。", ephemeral=True
            )
            return

        user_role_ids = {str(r.id) for r in itx.user.roles}
        removable = [(rid, name) for rid, name in selectable_roles if rid in user_role_ids]
        if not removable:
            await itx.response.send_message(
                "✅ 現在剥奪できるロールは付与されていません。", ephemeral=True
            )
            return

        class RevokeSelView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(discord.ui.Select(
                    placeholder="外すロールを選択",
                    max_values=len(removable),
                    options=[discord.SelectOption(label=name, value=rid) for rid, name in removable]
                ))

            async def interaction_check(self, inter: discord.Interaction) -> bool:
                selected = self.children[0].values
                removed = []
                for rid in selected:
                    r = inter.guild.get_role(int(rid))
                    if r and r in inter.user.roles:
                        await inter.user.remove_roles(r)
                        removed.append(r.name)
                if removed:
                    await inter.response.send_message(
                        f"✅ ロールを剥奪：{', '.join(removed)}", ephemeral=True
                    )
                else:
                    await inter.response.send_message(
                        "❌ 選択されたロールが見つかりませんでした。", ephemeral=True
                    )
                return True

        await itx.response.send_message(
            "外すロールを選択してください：", view=RevokeSelView(), ephemeral=True
        )

    @discord.ui.button(label="✏️ パネル編集", style=discord.ButtonStyle.secondary, custom_id="revoke:edit")
    async def edit_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_role_revoke_panel()
        default_title = latest["title"] if latest else "🗑️ ロール剥奪"
        default_desc = latest["description"] if latest else (
            "ボタンから不要なロールを選択して外すことができます。"
        )

        class EditModal(discord.ui.Modal, title="ロール剥奪パネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title)
            desc_in = discord.ui.TextInput(
                label="説明", style=discord.TextStyle.long,
                default=default_desc
            )

            async def on_submit(self, inter: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0xe74c3c
                )
                await inter.response.edit_message(embed=embed, view=RoleRevokePanelView())
                save_role_revoke_panel(
                    inter.channel_id,
                    inter.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0xe74c3c
                )
                await inter.followup.send("✅ 更新・保存完了", ephemeral=True)

        await itx.response.send_modal(EditModal())

    @discord.ui.button(label="🔄 パネル更新", style=discord.ButtonStyle.secondary, custom_id="revoke:refresh")
    async def refresh_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_role_revoke_panel()
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


async def setup(tree, bot=None):
    init_role_revoke_table()
    if bot is not None and not hasattr(bot, "_revoke_panel_registered"):
        bot.add_view(RoleRevokePanelView())
        bot._revoke_panel_registered = True
        print("✅ revoke_panel 永続View登録完了")

    @tree.command(name="ロール剥奪パネル設置", description="ロール剥奪パネル設置（オーナー専用）")
    async def cmd_revoke_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="🗑️ ロール剥奪",
            description="⬇️のボタンを押して、不要になったロールを選択して外すことができます。\n誤ったロールを外した際はロール付与で付け直すことができます。",
            color=0xe74c3c
        )
        await itx.response.send_message(embed=embed, view=RoleRevokePanelView())
        msg = await itx.original_response()
        save_role_revoke_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
