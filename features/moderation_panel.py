import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone
from core.common import is_owner
from core.database import get_connection

JST = timezone(timedelta(hours=9))
MOD_LOG_CHANNEL_ID = 1558836223920046200  # ログ送信先チャンネルID

# ========== データベース：履歴管理 ==========
def init_moderation_table():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS moderation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user_id TEXT NOT NULL,
            target_user_name TEXT NOT NULL,
            operator_user_id TEXT NOT NULL,
            operator_user_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            reason TEXT,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()

def add_moderation_log(target_user_id, target_user_name, operator_id, operator_name, action_type, reason):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO moderation_log 
        (target_user_id, target_user_name, operator_user_id, operator_user_name, action_type, reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        str(target_user_id), str(target_user_name),
        str(operator_id), str(operator_name),
        action_type, reason,
        datetime.now(JST).isoformat()
    ))
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id

def get_moderation_logs(target_user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT action_type, reason, timestamp, status, operator_user_name
        FROM moderation_log
        WHERE target_user_id = ?
        ORDER BY timestamp DESC
    """, (str(target_user_id),))
    result = cur.fetchall()
    conn.close()
    return result

def update_log_status(log_id, new_status):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE moderation_log SET status = ? WHERE id = ?
    """, (new_status, log_id))
    conn.commit()
    conn.close()

# ========== 確認用モーダル ==========
class ActionConfirmModal(discord.ui.Modal):
    def __init__(self, target_user, action_type):
        super().__init__(title=f"{action_type} 実行確認")
        self.target_user = target_user
        self.action_type = action_type
        self.reason_input = discord.ui.TextInput(
            label="理由（必須）",
            style=discord.TextStyle.long,
            placeholder="理由を記入してください",
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, itx: discord.Interaction):
        reason = self.reason_input.value.strip()
        if not reason:
            await itx.response.send_message("❌ 理由を入力してください", ephemeral=True)
            return
        success = True
        desc = ""
        color = 0x808080
        if self.action_type == "⚠️ 警告":
            try:
                await self.target_user.send(
                    f"⚠️ **サーバーより警告**\n"
                    f"理由：{reason}\n"
                    f"日時：{datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}"
                )
                desc = f"{self.target_user.mention} に警告を送信しました"
                color = 0xF1C40F
            except Exception as e:
                desc = f"⚠️ 警告を送信しました（DM配信失敗：{e}）"
                color = 0xF1C40F
        elif self.action_type == "🚪 キック":
            try:
                await itx.guild.kick(self.target_user, reason=reason)
                desc = f"{self.target_user.mention} をキックしました"
                color = 0xF79E1B
            except Exception as e:
                success = False
                desc = f"❌ キック失敗：{e}"
        elif self.action_type == "🚫 BAN":
            try:
                await itx.guild.ban(self.target_user, reason=reason, delete_message_days=0)
                desc = f"{self.target_user.mention} をBANしました"
                color = 0xE74C3C
            except Exception as e:
                success = False
                desc = f"❌ BAN失敗：{e}"
        if success:
            add_moderation_log(
                self.target_user.id, str(self.target_user),
                itx.user.id, str(itx.user),
                self.action_type, reason
            )
        embed = discord.Embed(
            title=self.action_type,
            description=desc,
            color=color,
            timestamp=datetime.now(JST)
        )
        embed.add_field(name="対象", value=self.target_user.mention, inline=True)
        embed.add_field(name="実行者", value=itx.user.mention, inline=True)
        embed.add_field(name="理由", value=reason, inline=False)
        await itx.response.send_message(embed=embed, ephemeral=True)
        # ログチャンネル送信
        if MOD_LOG_CHANNEL_ID and success:
            log_ch = itx.client.get_channel(MOD_LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(embed=embed)

# ========== ユーザー選択ビュー ==========
class SelectTargetView(discord.ui.View):
    def __init__(self, action):
        super().__init__(timeout=120)
        self.action = action
        self.selected_user = None
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        self.selected_user = self.children[0].values[0]
        await self.process_selection(itx)
        return False  # 二重実行防止

    async def process_selection(self, itx: discord.Interaction):
        target = self.selected_user
        if self.action == "history":
            logs = get_moderation_logs(target.id)
            if not logs:
                await itx.response.send_message(
                    f"✅ {target.mention} には管理履歴がありません", ephemeral=True
                )
                return
            desc_lines = []
            for act, reason, ts, status, op in logs:
                status_mark = "✅" if status == "released" else "🔴"
                desc_lines.append(f"{status_mark} **{act}** [{ts[:16]}] by {op}\n　理由：{reason}")
            embed = discord.Embed(
                title=f"📝 管理履歴：{target}",
                description="\n\n".join(desc_lines[:15]),
                color=0x3498DB
            )
            await itx.response.send_message(embed=embed, ephemeral=True)
        elif self.action == "unban":
            try:
                ban_entry = await itx.guild.fetch_ban(target)
                if ban_entry:
                    await itx.guild.unban(target)
                    add_moderation_log(
                        target.id, str(target),
                        itx.user.id, str(itx.user),
                        "✅ BAN解除", "管理者による解除"
                    )
                    await itx.response.send_message(
                        f"✅ {target.mention} のBANを解除しました", ephemeral=True
                    )
            except discord.NotFound:
                await itx.response.send_message(
                    f"⚠️ {target.mention} はBANされていません", ephemeral=True
                )
        else:
            await itx.response.send_modal(ActionConfirmModal(target, self.action))

# ========== メインパネル ==========
class ModerationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効
        init_moderation_table()

    @discord.ui.button(label="⚠️ 警告", style=discord.ButtonStyle.secondary, custom_id="mod:warn", row=0)
    async def warn_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message(
            "⚠️ 警告するユーザーを選択してください",
            view=SelectTargetView("⚠️ 警告"),
            ephemeral=True
        )

    @discord.ui.button(label="🚪 キック", style=discord.ButtonStyle.primary, custom_id="mod:kick", row=0)
    async def kick_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message(
            "🚪 キックするユーザーを選択してください",
            view=SelectTargetView("🚪 キック"),
            ephemeral=True
        )

    @discord.ui.button(label="🚫 BAN", style=discord.ButtonStyle.danger, custom_id="mod:ban", row=0)
    async def ban_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message(
            "🚫 BANするユーザーを選択してください",
            view=SelectTargetView("🚫 BAN"),
            ephemeral=True
        )

    @discord.ui.button(label="📝 履歴表示", style=discord.ButtonStyle.secondary, custom_id="mod:history", row=1)
    async def history_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message(
            "📝 履歴を確認するユーザーを選択してください",
            view=SelectTargetView("history"),
            ephemeral=True
        )

    @discord.ui.button(label="✅ BAN解除", style=discord.ButtonStyle.success, custom_id="mod:unban", row=1)
    async def unban_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message(
            "✅ BANを解除するユーザーを選択してください",
            view=SelectTargetView("unban"),
            ephemeral=True
        )

# ✅ 引数統一
async def setup(tree: app_commands.CommandTree, bot=None):
    init_moderation_table()
    if bot is not None and not hasattr(bot, "_moderation_views_registered"):
        bot.add_view(ModerationPanelView())
        bot._moderation_views_registered = True
        print("✅ moderation_panel 永続View登録完了")

    @tree.command(name="管理パネル設置", description="メンバー管理パネル設置（オーナー専用）")
    @app_commands.check(is_owner)
    async def cmd(itx: discord.Interaction):
        embed = discord.Embed(
            title="🔨 メンバー管理パネル",
            description="""⚠️ 警告 → DMに警告送信・履歴記録
🚪 キック → 理由を入力してキック
🚫 BAN → 理由を入力してBAN
📝 履歴表示 → 対象ユーザーの過去の記録を表示
✅ BAN解除 → BANされたユーザーを解除
🔒 オーナー以外は使用できません
📋 全操作は自動的に履歴として保存されます""",
            color=0x992D22,
            timestamp=datetime.now(JST)
        )
        await itx.response.send_message(embed=embed, view=ModerationPanelView())
        await itx.followup.send("✅ 管理パネル設置完了", ephemeral=True)
