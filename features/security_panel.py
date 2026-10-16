import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone
from core.common import is_owner
from core.database import get_connection
import asyncio
import re
JST = timezone(timedelta(hours=9))
MOD_LOG_CHANNEL_ID = 1559306800346562672
MUTE_ROLE_NAME = "ミュート"
TARGET_CHANNEL_ID = 1558099501305176095

# ========== データベース初期化 ==========
def init_security_tables():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forbidden_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            match_type TEXT DEFAULT 'partial',
            level TEXT DEFAULT 'warning'
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS security_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT 'off'
        )
    """)
    for key in ['spam_monitor', 'link_monitor', 'word_monitor']:
        cur.execute("INSERT OR IGNORE INTO security_settings VALUES (?, 'off')", (key,))
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_mutes (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            end_time TEXT NOT NULL,
            reason TEXT,
            mute_type TEXT DEFAULT 'timed'
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_tempbans (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            end_time TEXT NOT NULL,
            reason TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS security_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            timestamp TEXT NOT NULL,
            operator_id TEXT,
            operator_name TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notice_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    cur.execute("SELECT COUNT(*) FROM notice_templates")
    if cur.fetchone()[0] == 0:
        defaults = [
            ("注意", "迷惑行為を控えてください。ルールを守ってご利用ください。"),
            ("厳重注意", "繰り返し迷惑行為が見られます。今後同様の行為があった場合、ミュートまたはBANとなります。"),
            ("最終警告", "これ以上の違反は即時BANとなります。今一度行動を改めてください。")
        ]
        for t, c in defaults:
            cur.execute("INSERT INTO notice_templates (title, content) VALUES (?, ?)", (t, c))
    
    conn.commit()
    conn.close()

# ========== 共通：設定取得・更新 ==========
def get_setting(key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM security_settings WHERE key=?", (key,))
    r = cur.fetchone()
    conn.close()
    return r[0] if r else 'off'

def set_setting(key, value):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("REPLACE INTO security_settings VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# ========== 禁止ワード管理 ==========
def get_forbidden_words():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, word, match_type, level FROM forbidden_words")
    result = cur.fetchall()
    conn.close()
    return result

def add_forbidden_word(word, match_type='partial', level='warning'):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO forbidden_words (word, match_type, level) VALUES (?, ?, ?)",
        (word, match_type, level)
    )
    conn.commit()
    conn.close()

def remove_forbidden_word(word_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM forbidden_words WHERE id=?", (word_id,))
    conn.commit()
    conn.close()

# ========== ミュート管理 ==========
def add_mute(user_id, user_name, end_time_str, reason, mute_type='timed'):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO active_mutes VALUES (?, ?, ?, ?, ?)",
        (str(user_id), user_name, end_time_str, reason, mute_type)
    )
    conn.commit()
    conn.close()

def remove_mute(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM active_mutes WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()

def get_expired_mutes():
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(JST).isoformat()
    cur.execute("SELECT user_id, user_name FROM active_mutes WHERE end_time < ?", (now,))
    result = cur.fetchall()
    conn.close()
    return result

# ========== 期限付きBAN管理 ==========
def add_tempban(user_id, user_name, end_time_str, reason):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO active_tempbans VALUES (?, ?, ?, ?)",
        (str(user_id), user_name, end_time_str, reason)
    )
    conn.commit()
    conn.close()

def remove_tempban(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM active_tempbans WHERE user_id=?", (str(user_id),))
    conn.commit()
    conn.close()

def get_expired_tempbans():
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(JST).isoformat()
    cur.execute("SELECT user_id, user_name FROM active_tempbans WHERE end_time < ?", (now,))
    result = cur.fetchall()
    conn.close()
    return result

# ========== 履歴記録 ==========
def add_security_log(user_id, user_name, action, reason, op_id=None, op_name=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO security_log VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(user_id),
            user_name,
            action,
            reason,
            datetime.now(JST).isoformat(),
            str(op_id) if op_id else None,
            op_name
        )
    )
    conn.commit()
    conn.close()

def get_security_stats(days=7):
    conn = get_connection()
    cur = conn.cursor()
    since = (datetime.now(JST) - timedelta(days=days)).isoformat()
    cur.execute("""
        SELECT action, COUNT(*) FROM security_log
        WHERE timestamp >= ? GROUP BY action
    """, (since,))
    result = dict(cur.fetchall())
    conn.close()
    return result

# ========== 注意文テンプレート ==========
def get_templates():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, content FROM notice_templates")
    result = cur.fetchall()
    conn.close()
    return result

# ========== ログ送信 ==========
async def send_security_log(guild, title, desc, color=0x3498DB):
    if not MOD_LOG_CHANNEL_ID:
        return
    ch = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not ch:
        return
    embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.now(JST))
    await ch.send(embed=embed)

# ========== 共通モーダル ==========
class ConfirmModal(discord.ui.Modal):
    def __init__(self, title, callback):
        super().__init__(title=title)
        self.callback = callback
        self.reason_in = discord.ui.TextInput(label="理由", required=True, max_length=100)
        self.add_item(self.reason_in)
    async def on_submit(self, itx):
        await self.callback(itx, self.reason_in.value)

# ========== 共通：ユーザー選択View ==========
class SelectUserView(discord.ui.View):
    def __init__(self, callback):
        super().__init__(timeout=120)
        self.callback = callback
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        user = self.children[0].values[0]
        await self.callback(itx, user)
        return False

# ========== ① チャンネルロック ==========
class LockChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🔒 ロック実行", style=discord.ButtonStyle.danger, custom_id="sec:lock")
    async def lock_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        target_ch = itx.guild.get_channel(TARGET_CHANNEL_ID)
        if not target_ch:
            await itx.response.send_message("❌ 管理対象チャンネルが見つかりません", ephemeral=True)
            return
        async def _lock(itx, reason):
            perms = target_ch.overwrites_for(itx.guild.default_role)
            perms.send_messages = False
            await target_ch.set_permissions(itx.guild.default_role, overwrite=perms, reason=reason)
            add_security_log(itx.user.id, str(itx.user), "チャンネルロック", reason, itx.user.id, str(itx.user))
            await send_security_log(itx.guild, "🔒 チャンネルロック",
                f"チャンネル：{target_ch.mention}\n実行者：{itx.user.mention}\n理由：{reason}", 0xF1C40F)
            await itx.response.edit_message(
                content=f"✅ {target_ch.mention} をロックしました\n理由：{reason}",
                view=UnlockChannelView()
            )
        await itx.response.send_modal(ConfirmModal("チャンネルロック", _lock))

class UnlockChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🔓 解除", style=discord.ButtonStyle.success, custom_id="sec:unlock")
    async def unlock_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        target_ch = itx.guild.get_channel(TARGET_CHANNEL_ID)
        if not target_ch:
            await itx.response.send_message("❌ 管理対象チャンネルが見つかりません", ephemeral=True)
            return
        async def _unlock(itx, reason):
            perms = target_ch.overwrites_for(itx.guild.default_role)
            perms.send_messages = None
            await target_ch.set_permissions(itx.guild.default_role, overwrite=perms, reason=reason)
            add_security_log(itx.user.id, str(itx.user), "チャンネル解除", reason, itx.user.id, str(itx.user))
            await send_security_log(itx.guild, "🔓 チャンネル解除",
                f"チャンネル：{target_ch.mention}\n実行者：{itx.user.mention}\n理由：{reason}", 0x2ECC71)
            await itx.response.edit_message(content=f"✅ {target_ch.mention} を解除しました", view=None)
        await itx.response.send_modal(ConfirmModal("チャンネル解除", _unlock))

# ========== ② 時間指定ミュート ==========
class MuteUserSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        user = self.children[0].values[0]
        view = MuteDurationView(user)
        await itx.response.send_message(
            f"対象：{user.mention}\n時間を選択してください",
            view=view, ephemeral=True
        )
        return False

class MuteDurationView(discord.ui.View):
    def __init__(self, target):
        super().__init__(timeout=120)
        self.target = target
    @discord.ui.button(label="1時間", style=discord.ButtonStyle.primary)
    async def h1(self, itx, btn): await self._mute(itx, 1)
    @discord.ui.button(label="6時間", style=discord.ButtonStyle.primary)
    async def h6(self, itx, btn): await self._mute(itx, 6)
    @discord.ui.button(label="24時間", style=discord.ButtonStyle.primary)
    async def h24(self, itx, btn): await self._mute(itx, 24)
    @discord.ui.button(label="7日", style=discord.ButtonStyle.primary)
    async def d7(self, itx, btn): await self._mute(itx, 24*7)
    @discord.ui.button(label="無期限", style=discord.ButtonStyle.danger)
    async def perm(self, itx, btn): await self._mute(itx, None)
    async def _mute(self, itx, hours):
        end_time = (datetime.now(JST) + timedelta(hours=hours)).isoformat() if hours else None
        async def _confirm(itx, reason):
            role = discord.utils.get(itx.guild.roles, name=MUTE_ROLE_NAME)
            if not role:
                await itx.response.send_message(f"❌ 「{MUTE_ROLE_NAME}」ロールを先に作成してください", ephemeral=True)
                return
            await self.target.add_roles(role, reason=reason)
            if end_time:
                add_mute(self.target.id, str(self.target), end_time, reason)
            add_security_log(self.target.id, str(self.target), "ミュート", reason, itx.user.id, str(itx.user))
            try:
                await self.target.send(
                    f"🔇 サーバーにてミュートされました\n"
                    f"理由：{reason}\n"
                    f"期間：{f'{hours}時間' if hours else '無期限'}"
                )
            except: pass
            await send_security_log(itx.guild, "🔇 ミュート実行",
                f"対象：{self.target.mention}\n実行者：{itx.user.mention}\n理由：{reason}\n期間：{f'{hours}時間' if hours else '無期限'}", 0xF79E1B)
            await itx.response.edit_message(content=f"✅ {self.target.mention} をミュートしました", view=None)
        await itx.response.send_modal(ConfirmModal("ミュート実行", _confirm))

# ========== ③ 期限付きBAN ==========
class TempBanSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        user = self.children[0].values[0]
        view = TempBanDurationView(user)
        await itx.response.send_message(
            f"対象：{user.mention}\n期間を選択してください",
            view=view, ephemeral=True
        )
        return False

class TempBanDurationView(discord.ui.View):
    def __init__(self, target):
        super().__init__(timeout=120)
        self.target = target
    @discord.ui.button(label="3日", style=discord.ButtonStyle.primary)
    async def d3(self, itx, btn): await self._ban(itx, 3)
    @discord.ui.button(label="7日", style=discord.ButtonStyle.primary)
    async def d7(self, itx, btn): await self._ban(itx, 7)
    @discord.ui.button(label="30日", style=discord.ButtonStyle.primary)
    async def d30(self, itx, btn): await self._ban(itx, 30)
    @discord.ui.button(label="無期限", style=discord.ButtonStyle.danger)
    async def perm(self, itx, btn): await self._ban(itx, None)
    async def _ban(self, itx, days):
        end_time = (datetime.now(JST) + timedelta(days=days)).isoformat() if days else None
        async def _confirm(itx, reason):
            try:
                await itx.guild.ban(self.target, reason=reason, delete_message_days=0)
            except Exception as e:
                await itx.response.send_message(f"❌ BAN失敗：{e}", ephemeral=True)
                return
            if end_time:
                add_tempban(self.target.id, str(self.target), end_time, reason)
            add_security_log(self.target.id, str(self.target), "期限付きBAN", reason, itx.user.id, str(itx.user))
            try:
                await self.target.send(
                    f"🚫 サーバーからBANされました\n"
                    f"理由：{reason}\n"
                    f"期間：{f'{days}日' if days else '無期限'}"
                )
            except: pass
            await send_security_log(itx.guild, "🚫 BAN実行",
                f"対象：{self.target.mention}\n実行者：{itx.user.mention}\n理由：{reason}\n期間：{f'{days}日' if days else '無期限'}", 0xE74C3C)
            await itx.response.edit_message(content=f"✅ {self.target.mention} をBANしました", view=None)
        await itx.response.send_modal(ConfirmModal("期限付きBAN", _confirm))

# ========== ④ スパム一括削除 ==========
class SpamDeleteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        user = self.children[0].values[0]
        view = SpamDeleteCountView(user)
        await itx.response.send_message(
            f"対象：{user.mention}\n削除する件数を選択",
            view=view, ephemeral=True
        )
        return False

class SpamDeleteCountView(discord.ui.View):
    def __init__(self, target):
        super().__init__(timeout=120)
        self.target = target
    @discord.ui.button(label="直近10件", style=discord.ButtonStyle.primary)
    async def c10(self, itx, btn): await self._delete(itx, 10)
    @discord.ui.button(label="直近30件", style=discord.ButtonStyle.primary)
    async def c30(self, itx, btn): await self._delete(itx, 30)
    @discord.ui.button(label="直近50件", style=discord.ButtonStyle.primary)
    async def c50(self, itx, btn): await self._delete(itx, 50)
    async def _delete(self, itx, limit):
        deleted = 0
        async for msg in itx.channel.history(limit=200):
            if deleted >= limit: break
            if msg.author.id == self.target.id:
                try:
                    await msg.delete()
                    deleted += 1
                except: pass
        add_security_log(self.target.id, str(self.target), "スパム削除", f"{deleted}件", itx.user.id, str(itx.user))
        await send_security_log(itx.guild, "🧹 スパム一括削除",
            f"対象：{self.target.mention}\n実行者：{itx.user.mention}\n削除件数：{deleted}件", 0x9B59B6)
        await itx.response.edit_message(content=f"✅ {deleted}件削除しました", view=None)

# ========== ⑤ 緊急サーバー封鎖 ==========
class EmergencyLockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🚨 封鎖実行", style=discord.ButtonStyle.danger, custom_id="sec:emergency_lock")
    async def lock_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        async def _lock(itx, reason):
            perms = itx.guild.default_role.permissions
            perms.send_messages = False
            perms.create_instant_invite = False
            await itx.guild.edit(default_role_permissions=perms, reason=reason)
            add_security_log(itx.user.id, str(itx.user), "緊急封鎖", reason, itx.user.id, str(itx.user))
            await send_security_log(itx.guild, "🚨 緊急サーバー封鎖",
                f"実行者：{itx.user.mention}\n理由：{reason}", 0xE74C3C)
            await itx.response.edit_message(
                content=f"✅ サーバーを封鎖しました\n理由：{reason}",
                view=EmergencyUnlockView()
            )
        await itx.response.send_modal(ConfirmModal("緊急封鎖", _lock))

class EmergencyUnlockView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="✅ 封鎖解除", style=discord.ButtonStyle.success, custom_id="sec:emergency_unlock")
    async def unlock_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        async def _unlock(itx, reason):
            perms = itx.guild.default_role.permissions
            perms.send_messages = True
            perms.create_instant_invite = True
            await itx.guild.edit(default_role_permissions=perms, reason=reason)
            add_security_log(itx.user.id, str(itx.user), "緊急封鎖解除", reason, itx.user.id, str(itx.user))
            await send_security_log(itx.guild, "✅ 緊急封鎖解除",
                f"実行者：{itx.user.mention}\n理由：{reason}", 0x2ECC71)
            await itx.response.edit_message(content="✅ 通常運用に戻しました", view=None)
        await itx.response.send_modal(ConfirmModal("封鎖解除", _unlock))

# ========== ⑥ 禁止ワード管理画面 ==========
class ForbiddenWordView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    async def build_embed(self):
        words = get_forbidden_words()
        if words:
            word_list = "\n".join([f" [{wid}] `{word}`" for wid, word, _, _ in words])
        else:
            word_list = "⚠️ 登録された禁止ワードはありません"
        status = get_setting('word_monitor')
        embed = discord.Embed(
            title="🔍 禁止ワード管理",
            description=word_list,
            color=0x3498DB
        )
        embed.set_footer(text=f"現在の状態：{'✅ 検知有効' if status=='on' else '❌ 検知無効'}")
        return embed
    @discord.ui.button(label="➕ 新規登録", style=discord.ButtonStyle.success, row=0, custom_id="fw:add")
    async def add_btn(self, itx, btn):
        class AddModal(discord.ui.Modal, title="禁止ワード新規登録"):
            word = discord.ui.TextInput(label="禁止する言葉", required=True, max_length=100)
            async def on_submit(self, itx):
                add_forbidden_word(self.word.value)
                await itx.response.send_message(f"✅ 「{self.word.value}」を登録しました", ephemeral=True)
        await itx.response.send_modal(AddModal())
        await asyncio.sleep(0.4)
        embed = await self.build_embed()
        await itx.edit_original_response(embed=embed, view=self)
    @discord.ui.button(label="➖ 登録解除", style=discord.ButtonStyle.danger, row=0, custom_id="fw:remove")
    async def remove_btn(self, itx, btn):
        words = get_forbidden_words()
        if not words:
            await itx.response.send_message("❌ 登録されていません", ephemeral=True)
            return
        class RemoveView(discord.ui.View):
            def __init__(self, parent_view):
                super().__init__(timeout=None)
                self.parent = parent_view
                opts = [discord.SelectOption(label=f"{word[:25]}", value=str(wid)) for wid, word, _, _ in words]
                @discord.ui.select(placeholder="解除するワードを選択", options=opts)
                async def select_remove(self, inter: discord.Interaction, selected_values):
                    wid = int(selected_values[0])
                    remove_forbidden_word(wid)
                    await inter.response.send_message("✅ 登録を解除しました", ephemeral=True)
                    await asyncio.sleep(0.4)
                    embed = await self.parent.build_embed()
                    await inter.edit_original_response(embed=embed, view=self.parent)
        await itx.response.send_message("解除するワードを選択してください", view=RemoveView(self), ephemeral=True)
    @discord.ui.button(label="❌ 状態読込中...", style=discord.ButtonStyle.secondary, row=1, custom_id="fw:toggle")
    async def toggle_btn(self, itx, btn):
        new_val = 'on' if get_setting('word_monitor') == 'off' else 'off'
        set_setting('word_monitor', new_val)
        if new_val == 'on':
            btn.label = '✅ 検知中 → OFFにする'
            btn.style = discord.ButtonStyle.success
        else:
            btn.label = '❌ 停止中 → ONにする'
            btn.style = discord.ButtonStyle.secondary
        embed = await self.build_embed()
        await itx.response.edit_message(embed=embed, view=self)
    @discord.ui.button(label="🔙 メインに戻る", style=discord.ButtonStyle.secondary, row=1, custom_id="fw:back")
    async def back_btn(self, itx, btn):
        embed = await build_security_embed()
        await itx.response.edit_message(embed=embed, view=SecurityMainView())

# ========== ⑦ 注意文テンプレート送信 ==========
class SendNoticeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(
            discord.ui.UserSelect(
                placeholder="対象ユーザーを選択",
                min_values=1,
                max_values=1
            )
        )
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        target = self.children[0].values[0]
        templates = get_templates()
        class SelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)
                opts = [discord.SelectOption(label=title, value=str(tid)) for tid, title, _ in templates]
                @discord.ui.select(placeholder="送信する文面", options=opts)
                async def select_template(self, inter: discord.Interaction, selected_values):
                    tid = int(selected_values[0])
                    for t in templates:
                        if t[0] == tid:
                            _, title, content = t
                            break
                    try:
                        await target.send(f"⚠️ {title}\n\n{content}")
                    except:
                        pass
                    add_security_log(target.id, str(target), f"注意送信:{title}", content, inter.user.id, str(inter.user))
                    await send_security_log(inter.guild, f"✍️ {title}",
                        f"対象：{target.mention}\n実行者：{inter.user.mention}\n内容：{content}", 0x3498DB)
                    await inter.response.send_message(f"✅ {target.mention} に送信しました", ephemeral=True)
        await itx.response.send_message("送信する文面を選択", view=SelectView(), ephemeral=True)
        return False

# ========== ⑧ 状況サマリー ==========
async def build_stats_embed():
    stats = get_security_stats(7)
    embed = discord.Embed(title="📊 治安状況サマリー（過去7日間）", color=0x3498DB)
    embed.add_field(name="🔇 ミュート", value=str(stats.get("ミュート", 0)), inline=True)
    embed.add_field(name="🚫 BAN", value=str(stats.get("期限付きBAN", 0)), inline=True)
    embed.add_field(name="🧹 削除", value=str(stats.get("スパム削除", 0)), inline=True)
    notice_count = sum(v for k, v in stats.items() if k.startswith("注意送信"))
    embed.add_field(name="⚠️ 注意", value=str(notice_count), inline=True)
    return embed

# ========== 埋め込み作成 ==========
async def build_security_embed():
    ch_text = f"• <#{TARGET_CHANNEL_ID}>（管理対象）"
    embed = discord.Embed(title="🛡️ 治安管理パネル", color=0x992D22)
    embed.add_field(name="📺 管理対象チャンネル", value=ch_text, inline=False)
    
    spam_status = get_setting('spam_monitor')
    link_status = get_setting('link_monitor')
    word_status = get_setting('word_monitor')
    
    embed.add_field(name="⚡ 高速投稿監視", value=f"✅ {spam_status}" if spam_status=='on' else f"❌ {spam_status}", inline=True)
    embed.add_field(name="🔗 リンク制限", value=f"✅ {link_status}" if link_status=='on' else f"❌ {link_status}", inline=True)
    embed.add_field(name="🔍 禁止ワード", value=f"✅ {word_status}" if word_status=='on' else f"❌ {word_status}", inline=True)
    
    now_jst = datetime.now(JST)
    embed.set_footer(text=f"最終更新：{now_jst.strftime('%Y-%m-%d %H:%M:%S JST')}")
    return embed

# ========== メインパネル ==========
class SecurityMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        init_security_tables()
    
    # ========== 🔄 情報更新ボタン 追加 ==========
    @discord.ui.button(label="🔄 情報更新", style=discord.ButtonStyle.secondary, row=0, custom_id="sec:refresh")
    async def refresh_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        embed = await build_security_embed()
        await itx.response.edit_message(embed=embed, view=SecurityMainView())
        await itx.followup.send("✅ パネル情報を最新に更新しました", ephemeral=True)
    
    @discord.ui.button(label="🔒 チャンネルロック", style=discord.ButtonStyle.secondary, row=0, custom_id="sec:main_lock")
    async def lock_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        target_ch = itx.guild.get_channel(TARGET_CHANNEL_ID)
        ch_mention = target_ch.mention if target_ch else f"ID:{TARGET_CHANNEL_ID}"
        await itx.response.send_message(
            f"対象：{ch_mention}\n理由を入力してロック実行",
            view=LockChannelView(),
            ephemeral=True
        )
    
    @discord.ui.button(label="🔇 時間指定ミュート", style=discord.ButtonStyle.primary, row=1, custom_id="sec:main_mute")
    async def mute_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message("対象ユーザーを選択してください", view=MuteUserSelectView(), ephemeral=True)
    
    @discord.ui.button(label="⏰ 期限付きBAN", style=discord.ButtonStyle.danger, row=1, custom_id="sec:main_ban")
    async def ban_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message("対象ユーザーを選択してください", view=TempBanSelectView(), ephemeral=True)
    
    @discord.ui.button(label="🧹 スパム削除", style=discord.ButtonStyle.primary, row=1, custom_id="sec:main_spamdel")
    async def spamdel_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message("対象ユーザーを選択してください", view=SpamDeleteView(), ephemeral=True)
    
    @discord.ui.button(label="🚨 緊急封鎖", style=discord.ButtonStyle.danger, row=2, custom_id="sec:main_emergency")
    async def emergency_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message("⚠️ サーバー全体を一時停止します\n理由を入力して実行", view=EmergencyLockView(), ephemeral=True)
    
    @discord.ui.button(label="🔍 禁止ワード管理", style=discord.ButtonStyle.primary, row=2, custom_id="sec:main_word")
    async def wordmanage_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        view = ForbiddenWordView()
        embed = await view.build_embed()
        await itx.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚡ 高速投稿", style=discord.ButtonStyle.success, row=2, custom_id="sec:main_spam")
    async def spam_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        new_val = 'on' if get_setting('spam_monitor') == 'off' else 'off'
        set_setting('spam_monitor', new_val)
        embed = await build_security_embed()
        await itx.response.edit_message(embed=embed, view=SecurityMainView())
    
    @discord.ui.button(label="🔗 リンク制限", style=discord.ButtonStyle.success, row=3, custom_id="sec:main_link")
    async def link_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        new_val = 'on' if get_setting('link_monitor') == 'off' else 'off'
        set_setting('link_monitor', new_val)
        embed = await build_security_embed()
        await itx.response.edit_message(embed=embed, view=SecurityMainView())
    
    @discord.ui.button(label="📊 状況サマリー", style=discord.ButtonStyle.secondary, row=3, custom_id="sec:main_stats")
    async def stats_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        embed = await build_stats_embed()
        await itx.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="✍️ 注意文送信", style=discord.ButtonStyle.secondary, row=3, custom_id="sec:main_notice")
    async def notice_btn(self, itx, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_message("対象ユーザーを選択してください", view=SendNoticeView(), ephemeral=True)

# ========== ⑨ 禁止ワード自動検知 ==========
async def check_forbidden_words(message: discord.Message):
    if message.author.bot:
        return
    if get_setting('word_monitor') != 'on':
        return
    forbidden_list = get_forbidden_words()
    if not forbidden_list:
        return
    content = message.content.lower()
    detected_word = None
    for wid, word, match_type, level in forbidden_list:
        word_lower = word.lower()
        if match_type == 'partial':
            if word_lower in content:
                detected_word = word
                break
        elif match_type == 'exact':
            if word_lower == content.strip().lower():
                detected_word = word
                break
    if not detected_word:
        return
    try:
        await message.delete()
    except Exception as e:
        print(f"⚠️ メッセージ削除失敗：{e}")
        return
    add_security_log(
        message.author.id,
        str(message.author),
        "禁止ワード検知",
        f"ワード：{detected_word}\n内容：{message.content}",
        None, None
    )
    notice_embed = discord.Embed(
        title="⚠️ 禁止ワードを検知しました",
        description=f"{message.author.mention} のメッセージを削除しました。\n理由：禁止ワード「`{detected_word}`」を検知",
        color=0xF39C12,
        timestamp=datetime.now(JST)
    )
    try:
        await message.channel.send(embed=notice_embed, delete_after=5.0)
    except:
        pass
    dm_embed = discord.Embed(
        title="⚠️ 警告：サーバールール違反",
        description=f"""あなたの送信したメッセージに禁止ワードが含まれていたため削除しました。
🔍 検知されたワード：`{detected_word}`
📝 送信された内容：{message.content}
今後このような行為が続く場合、ミュートまたはBANとなる場合があります。
サーバールールを守ってご利用ください。""",
        color=0xE74C3C,
        timestamp=datetime.now(JST)
    )
    try:
        await message.author.send(embed=dm_embed)
    except Exception as e:
        print(f"ℹ️ DM送信不可：{message.author} / {e}")
    await send_security_log(message.guild, "🔍 禁止ワード検知", 
        f"ユーザー：{message.author.mention}\nチャンネル：{message.channel.mention}\n検知ワード：`{detected_word}`\n送信内容：{message.content}", 0xE74C3C)

# ========== ⑩ リンク自動検知・制限 ==========
URL_PATTERN = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", re.IGNORECASE)
ALLOWED_DOMAINS = [
    r"discord\.com/channels/",
    r"discord\.gg/",
    r"discord\.new/",
    r"cdn\.discordapp\.com/",
    r"media\.discordapp\.net/",
]
def is_allowed_link(url):
    for domain in ALLOWED_DOMAINS:
        if re.search(domain, url, re.IGNORECASE):
            return True
    return False

async def check_link_restriction(message: discord.Message):
    if message.author.bot:
        return
    if is_owner(message):
        return
    if get_setting('link_monitor') != 'on':
        return
    urls_found = URL_PATTERN.findall(message.content)
    if not urls_found:
        return
    external_links = [url for url in urls_found if not is_allowed_link(url)]
    if not external_links:
        return
    try:
        await message.delete()
    except Exception as e:
        print(f"⚠️ リンク制限：削除失敗 {e}")
        return
    add_security_log(
        message.author.id,
        str(message.author),
        "リンク制限",
        f"検知：{', '.join(external_links[:5])}\n内容：{message.content}",
        None, None
    )
    notice_embed = discord.Embed(
        title="⚠️ 外部リンクを制限しました",
        description=f"{message.author.mention} のメッセージを削除しました。\n理由：許可されていない外部リンクが含まれています。",
        color=0xF39C12,
        timestamp=datetime.now(JST)
    )
    try:
        await message.channel.send(embed=notice_embed, delete_after=5.0)
    except:
        pass
    dm_embed = discord.Embed(
        title="⚠️ 警告：リンク制限",
        description=f"""サーバーでは外部リンクの送信を制限しています。
🔗 検知されたリンク：
{chr(10).join(f'・{url}' for url in external_links[:5])}
※ Discord内のメッセージリンク・招待リンク等は許可されています。
外部サイトへのリンクは送信しないでください。""",
        color=0xE67E22,
        timestamp=datetime.now(JST)
    )
    try:
        await message.author.send(embed=dm_embed)
    except Exception as e:
        print(f"ℹ️ DM送信不可：{message.author} / {e}")
    await send_security_log(message.guild, "🔗 リンク制限",
        f"ユーザー：{message.author.mention}\nチャンネル：{message.channel.mention}\n検知リンク：\n{chr(10).join(f'・{url}' for url in external_links[:5])}", 0xE67E22)

# ========== セットアップ ==========
async def setup(tree: app_commands.CommandTree, bot=None):
    init_security_tables()
    
    if bot is not None and not hasattr(bot, "_security_views_registered"):
        bot.add_view(SecurityMainView())
        bot.add_view(ForbiddenWordView())
        bot.add_view(LockChannelView())
        bot.add_view(UnlockChannelView())
        bot.add_view(EmergencyLockView())
        bot.add_view(EmergencyUnlockView())
        bot._security_views_registered = True
        print("✅ security_panel 永続View登録完了")
    
    @tree.command(name="治安パネル設置", description="治安管理パネル（オーナー専用）")
    @app_commands.check(is_owner)
    async def cmd(itx: discord.Interaction):
        embed = await build_security_embed()
        await itx.response.send_message(embed=embed, view=SecurityMainView())
        await itx.followup.send("✅ 治安パネル設置完了", ephemeral=True)
