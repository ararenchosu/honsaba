import discord
from discord import app_commands
from core.common import is_owner, CALL_CHANNEL_ID
from core.database import get_connection

# ========== パネル保存/読み込み ==========
def save_call_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO call_panel (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_call_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM call_panel
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

def get_call_message():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key='call_message'")
    r = cur.fetchone()
    conn.close()
    return r[0] if r else "$caller$さんが $target$さんを呼んでいます。"

def set_call_message(text):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("REPLACE INTO config VALUES ('call_message', ?)", (text,))
    conn.commit()
    conn.close()

# ===========================================
# ✅ 引数なしに変更 → 永続化対応
class CallPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📢 メンバーを呼ぶ",
        style=discord.ButtonStyle.primary,
        custom_id="call:do"
    )
    async def do_call(self, itx: discord.Interaction, btn: discord.ui.Button):
        class UserSelView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(
                    discord.ui.UserSelect(
                        placeholder="呼び出すユーザーを選択",
                        max_values=1,
                        custom_id="call:user_select"
                    )
                )

            async def interaction_check(self, inter: discord.Interaction) -> bool:
                target = self.children[0].values[0]
                msg = get_call_message().replace("$caller$", inter.user.mention).replace("$target$", target.mention)
                ch = inter.client.get_channel(CALL_CHANNEL_ID)
                if ch:
                    await ch.send(msg)
                    await inter.response.send_message(f"✅ {target.mention} を呼び出しました！", ephemeral=True)
                else:
                    await inter.response.send_message("❌ 通知チャンネルが見つかりません", ephemeral=True)
                return True

        await itx.response.send_message(
            "呼び出すユーザーを選択：",
            view=UserSelView(),
            ephemeral=True
        )

    @discord.ui.button(
        label="✏️ パネル編集",
        style=discord.ButtonStyle.secondary,
        custom_id="call:edit"
    )
    async def edit_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_call_panel()
        default_title = latest["title"] if latest else "📢 メンバー呼び出し"
        default_desc = latest["description"] if latest else "「メンバーを呼ぶ」からメンバーを選んで呼び出せます。"

        class EditModal(discord.ui.Modal, title="呼び出しパネル編集"):
            title_in = discord.ui.TextInput(
                label="タイトル",
                default=default_title,
                required=True
            )
            desc_in = discord.ui.TextInput(
                label="説明",
                style=discord.TextStyle.long,
                default=default_desc,
                required=True
            )

            def __init__(self):
                super().__init__()

            async def on_submit(self, inter: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0xe67e22
                )
                await inter.response.edit_message(embed=embed, view=CallPanelView())
                save_call_panel(
                    inter.channel_id,
                    inter.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0xe67e22
                )
                await inter.followup.send("✅ 更新・保存完了", ephemeral=True)

        await itx.response.send_modal(EditModal())

    @discord.ui.button(
        label="💬 メッセージ文変更",
        style=discord.ButtonStyle.secondary,
        custom_id="call:msg"
    )
    async def edit_msg(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        class MsgModal(discord.ui.Modal, title="呼び出しメッセージ編集"):
            msg_in = discord.ui.TextInput(
                label="文（$caller$/$target$ 置換）",
                default=get_call_message(),
                style=discord.TextStyle.long,
                required=True
            )
            async def on_submit(self, inter: discord.Interaction):
                set_call_message(str(self.msg_in))
                await inter.response.send_message(f"✅ 更新：\n{self.msg_in}", ephemeral=True)

        await itx.response.send_modal(MsgModal())

    @discord.ui.button(
        label="🔄 パネル更新",
        style=discord.ButtonStyle.secondary,
        custom_id="call:refresh"
    )
    async def refresh_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_call_panel()
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

# ✅ botがNoneの場合を回避
async def setup(tree, bot=None):
    # 起動時に永続View登録 — botが有効なときだけ実行
    if bot is not None and not hasattr(bot, "_call_panel_registered"):
        bot.add_view(CallPanelView())
        bot._call_panel_registered = True
        print("✅ call_panel 永続View登録完了")

    @tree.command(name="呼び出しパネル設置", description="呼び出しパネル設置（オーナー専用）")
    async def cmd_call_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        embed = discord.Embed(
            title="📢 メンバー呼び出し",
            description="ボタンからメンバーを選択して呼び出せます。\n通知は専用チャンネルに送信されます。",
            color=0xe67e22
        )
        await itx.response.send_message(embed=embed, view=CallPanelView())
        msg = await itx.original_response()
        save_call_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
