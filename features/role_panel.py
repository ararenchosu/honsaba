import discord
from discord import app_commands
from core.common import is_owner
from core.database import get_connection

# ========== パネル保存/読み込み ==========
def init_role_give_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_give_panel (
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

def save_role_give_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO role_give_panel 
        (channel_id, message_id, title, description, color, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_role_give_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM role_give_panel
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

# ========== 重複データ一括整理 ==========
def cleanup_duplicate_roles():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT guild_id, role_id, COUNT(*) as cnt
        FROM select_roles
        GROUP BY guild_id, role_id
        HAVING cnt > 1
    """)
    duplicates = cur.fetchall()
    
    removed_count = 0
    for guild_id, role_id, cnt in duplicates:
        cur.execute("""
            DELETE FROM select_roles
            WHERE guild_id = ? AND role_id = ? AND id NOT IN (
                SELECT MIN(id) FROM select_roles WHERE guild_id = ? AND role_id = ?
            )
        """, (guild_id, role_id, guild_id, role_id))
        removed_count += cur.rowcount
    
    conn.commit()
    conn.close()
    return removed_count

def get_selectable_roles(guild_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role_id, role_name FROM select_roles WHERE guild_id=?", (str(guild_id),))
    result = cur.fetchall()
    conn.close()
    seen = {}
    for rid, name in result:
        if rid not in seen:
            seen[rid] = name
    return list(seen.items())

def add_selectable_role(guild_id, role_id, role_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM select_roles WHERE guild_id=? AND role_id=?",
        (str(guild_id), str(role_id))
    )
    existing = cur.fetchone()
    if existing:
        conn.close()
        return "duplicate"
    cur.execute(
        "INSERT INTO select_roles VALUES (NULL, ?, ?, ?)",
        (str(guild_id), str(role_id), role_name)
    )
    conn.commit()
    conn.close()
    return "ok"

def remove_selectable_role(guild_id, role_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM select_roles WHERE guild_id=? AND role_id=?",
        (str(guild_id), str(role_id))
    )
    conn.commit()
    conn.close()

# ===========================================
class RoleSelectPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(label="🎖️ ロールを選択して取得", style=discord.ButtonStyle.primary, custom_id="rpanel:select", row=0)
    async def select_role(self, itx: discord.Interaction, btn: discord.ui.Button):
        roles = get_selectable_roles(itx.guild_id)
        if not roles:
            await itx.response.send_message(
                "❌ 付与するロールが設定されていません。オーナーが追加してください。",
                ephemeral=True
            )
            return

        class RoleSelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.role_list = roles

            @discord.ui.select(
                placeholder="取得するロールを選択",
                max_values=len(roles),
                options=[discord.SelectOption(label=name, value=rid) for rid, name in roles]
            )
            async def select_callback(self, inter: discord.Interaction, selected_values):
                added = []
                for rid in selected_values:
                    r = inter.guild.get_role(int(rid))
                    if r and r not in inter.user.roles:
                        await inter.user.add_roles(r)
                        added.append(r.name)
                if added:
                    await inter.response.send_message(
                        f"✅ ロールを付与：{', '.join(added)}", ephemeral=True
                    )
                else:
                    await inter.response.send_message(
                        "✅ 選択されたロールは既に付与されています", ephemeral=True
                    )

        await itx.response.send_message(
            "取得するロールを選択してください：", view=RoleSelectView(), ephemeral=True
        )

    @discord.ui.button(label="🗑️ 選択候補から削除", style=discord.ButtonStyle.danger, custom_id="rpanel:remove", row=0)
    async def remove_role_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        roles = get_selectable_roles(itx.guild_id)
        if not roles:
            await itx.response.send_message(
                "❌ 登録されているロールがありません", ephemeral=True
            )
            return

        class RemoveSelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.select(
                placeholder="削除するロールを選択",
                max_values=1,
                options=[discord.SelectOption(label=name, value=rid) for rid, name in roles]
            )
            async def remove_callback(self, inter: discord.Interaction, selected_values):
                rid = selected_values[0]
                r = inter.guild.get_role(int(rid))
                remove_selectable_role(inter.guild_id, rid)
                await inter.response.send_message(
                    f"🗑️ 「{r.name if r else '不明なロール'}」を選択候補から削除しました",
                    ephemeral=True
                )

        await itx.response.send_message(
            "削除するロールを選択してください：", view=RemoveSelectView(), ephemeral=True
        )

    @discord.ui.button(label="✏️ パネル編集", style=discord.ButtonStyle.secondary, custom_id="rpanel:edit", row=1)
    async def edit_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_role_give_panel()
        default_title = latest["title"] if latest else "🎖️ ロール選択"
        default_desc = latest["description"] if latest else (
            "ボタンから必要なロールを選択して取得してください。"
        )

        class EditModal(discord.ui.Modal, title="ロールパネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title)
            desc_in = discord.ui.TextInput(
                label="説明", style=discord.TextStyle.long,
                default=default_desc
            )

            async def on_submit(self, inter: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0x3498db
                )
                await inter.response.edit_message(embed=embed, view=RoleSelectPanelView())
                save_role_give_panel(
                    inter.channel_id,
                    inter.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0x3498db
                )
                await inter.followup.send("✅ 更新・保存完了", ephemeral=True)

        await itx.response.send_modal(EditModal())

    @discord.ui.button(label="➕ 付与ロール追加", style=discord.ButtonStyle.success, custom_id="rpanel:add", row=1)
    async def add_role_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        class RolePickerView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                self.add_item(
                    discord.ui.RoleSelect(  # ✅ 修正：RoleSelect に変更
                        placeholder="追加するロールを選択"
                    )
                )

            async def role_selected(self, inter: discord.Interaction, role: discord.Role):
                result = add_selectable_role(inter.guild_id, role.id, role.name)
                if result == "duplicate":
                    await inter.response.send_message(
                        f"⚠️ 「{role.name}」は既に登録されています。重複したものを削除しました。",
                        ephemeral=True
                    )
                else:
                    await inter.response.send_message(
                        f"✅ 「{role.name}」を選択候補に追加しました！",
                        ephemeral=True
                    )

        await itx.response.send_message(
            "追加するロールを選択してください：", view=RolePickerView(), ephemeral=True
        )

    @discord.ui.button(label="🔧 重複データ整理", style=discord.ButtonStyle.secondary, custom_id="rpanel:cleanup", row=2)
    async def cleanup_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        removed = cleanup_duplicate_roles()
        if removed > 0:
            await itx.response.send_message(
                f"✅ 重複データを整理しました。計 {removed} 件を削除しました。",
                ephemeral=True
            )
        else:
            await itx.response.send_message(
                "✅ 重複データは見つかりませんでした。",
                ephemeral=True
            )

    @discord.ui.button(label="🔄 パネル更新", style=discord.ButtonStyle.secondary, custom_id="rpanel:refresh", row=2)
    async def refresh_panel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_role_give_panel()
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
    init_role_give_table()
    if bot is not None and not hasattr(bot, "_role_panel_registered"):
        bot.add_view(RoleSelectPanelView())
        bot._role_panel_registered = True
        print("✅ role_panel 永続View登録完了")

    @tree.command(name="ロール付与パネル設置", description="選択式ロールパネル設置（オーナー専用）")
    async def cmd_role_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        cleanup_duplicate_roles()
        
        embed = discord.Embed(
            title="🎖️ ロール選択",
            description="""⬇️のボタンを押して、必要なロールを選択して取得してください。
誤ったロールを付けた際はロール剥奪でロールを外すことができます。
🎖️ ロールを選択して取得 → ユーザーがロール取得
🗑️ 選択候補から削除 → オーナー専用：パネルからロール自体を削除
➕ 付与ロール追加 → オーナー専用：新しいロールを候補に追加
🔧 重複データ整理 → オーナー専用：重複した登録を一括削除""",
            color=0x3498db
        )
        await itx.response.send_message(embed=embed, view=RoleSelectPanelView())
        msg = await itx.original_response()
        save_role_give_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
