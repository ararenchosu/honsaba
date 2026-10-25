import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone
from core.database import init_db
# ===== 各機能インポート =====
from features.lottery_panel import setup as lottery_setup
from features.login_bonus import setup as login_bonus_setup
from features.slots_panel import setup as slots_setup
from features.blackjack_panel import setup as blackjack_setup
from features.highlow_panel import setup as highlow_setup
from features.point_admin_panel import setup as point_admin_setup
import features.embed_sender as embed_sender
import features.clear_messages as clear_messages
import features.moderation_panel as moderation_panel
import features.security_panel as security_panel
import features.invite_link as invite_link
import features.backup_panel as backup_panel
import features.command_list_panel as command_list_panel
import features.othello as othello
import features.othello_panel as othello_panel
import features.auth_panel as auth_panel
import features.role_panel as role_panel
import features.revoke_panel as revoke_panel
import features.call_panel as call_panel
import features.welcome_leave as welcome_leave
import features.voice_channel_panel as voice_panel
import features.ranking_panel as ranking_panel
import features.elevator_panel as elevator_panel
import features.mines_panel as mines_panel
from core.common import is_owner
# ===== ウェブサーバーインポート =====
try:
    from web.app import app as flask_app
    WEB_AVAILABLE = True
except Exception as e:
    print(f"⚠️ ウェブサーバー読み込みエラー: {e}")
    WEB_AVAILABLE = False
# ===== 共通設定 =====
JST = timezone(timedelta(hours=9))
STATUS_LOG_CHANNEL_ID = 1559119439981449256
REASON_FILE = ".last_stop_reason"
def get_jst_now():
    return datetime.now(JST)
async def send_status_embed(client, title: str, description: str, color: int):
    if not STATUS_LOG_CHANNEL_ID:
        return
    try:
        channel = client.get_channel(STATUS_LOG_CHANNEL_ID)
        if not channel:
            print(f"⚠️ チャンネルが見つかりません: {STATUS_LOG_CHANNEL_ID}")
            return
        now_jst = get_jst_now()
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"時刻：{now_jst.strftime('%Y-%m-%d %H:%M:%S JST')}")
        await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ 通知送信エラー: {e}")
def clear_reason_file():
    if os.path.exists(REASON_FILE):
        try: os.remove(REASON_FILE)
        except: pass
def set_reason(reason: str):
    with open(REASON_FILE, "w", encoding="utf-8") as f:
        f.write(reason)
def get_and_clear_reason():
    if os.path.exists(REASON_FILE):
        with open(REASON_FILE, "r", encoding="utf-8") as f:
            reason = f.read().strip()
        clear_reason_file()
        return reason
    return None
def check_view_no_args(view_class, view_name: str):
    try:
        instance = view_class()
        if instance.timeout is not None:
            print(f"   ⚠️ 【{view_name}】: timeout が None になっていません")
        return instance
    except TypeError as e:
        print(f"   ❌ 【{view_name}】: 引数が必要 → {e}")
        return None
# ===== ウェブサーバー起動 =====
def run_web_server():
    if not WEB_AVAILABLE:
        return
    try:
        flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ ウェブサーバー起動エラー: {e}")
# ============================================================
# Intents
# ============================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
# ============================================================
# 🔴 メインBot：YWPBot（Cog形式 + 全機能統合）
# ============================================================
class YWPBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self._ready_done = False
    async def setup_hook(self):
        init_db()
        print("🔄 データベース初期化完了")
        # --- ウェブサーバー起動（バックグラウンド） ---
        if WEB_AVAILABLE:
            web_thread = threading.Thread(target=run_web_server, daemon=True)
            web_thread.start()
            print("✅ ウェブサーバー起動完了 :8080")
        # --- Cog読み込み ---
        cogs = [
            "cogs.ywp_auto",
            "cogs.ywp_commands",
            "cogs.ywp_stages",
            "cogs.ywp_panel",
            "cogs.auto_loop",  # ✅ 自動周回 追加
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Cogロード: {cog}")
            except Exception as e:
                print(f"❌ Cogロード失敗 {cog}: {e}")
        # --- View永続化登録 ---
        print("\n🔍 View 永続化登録中...")
        all_ok = True
        try:
            from features.lottery_panel import LotteryPanelView, PointCheckPanelView
            from features.login_bonus import LoginBonusPanelView
            from features.slots_panel import SlotPanelView
            from features.blackjack_panel import BlackjackPanelView
            from features.highlow_panel import HighLowPanelView
            from features.point_admin_panel import PointAdminView
            from features.moderation_panel import ModerationPanelView
            from features.security_panel import (
                SecurityMainView, ForbiddenWordView,
                LockChannelView, UnlockChannelView,
                EmergencyLockView, EmergencyUnlockView
            )
            from features.invite_link import InvitePanelView
            from features.backup_panel import BackupPanelView, RestoreConfirmView
            from features.command_list_panel import CommandListView
            from features.elevator_panel import ElevatorView
            from features.mines_panel import MinesWebStartView
            views_to_register = [
                (LotteryPanelView, "LotteryPanelView"),
                (PointCheckPanelView, "PointCheckPanelView"),
                (LoginBonusPanelView, "LoginBonusPanelView"),
                (SlotPanelView, "SlotPanelView"),
                (BlackjackPanelView, "BlackjackPanelView"),
                (HighLowPanelView, "HighLowPanelView"),
                (PointAdminView, "PointAdminView"),
                (ModerationPanelView, "ModerationPanelView"),
                (SecurityMainView, "SecurityMainView"),
                (ForbiddenWordView, "ForbiddenWordView"),
                (LockChannelView, "LockChannelView"),
                (UnlockChannelView, "UnlockChannelView"),
                (EmergencyLockView, "EmergencyLockView"),
                (EmergencyUnlockView, "EmergencyUnlockView"),
                (InvitePanelView, "InvitePanelView"),
                (BackupPanelView, "BackupPanelView"),
                (RestoreConfirmView, "RestoreConfirmView"),
                (othello_panel.OthelloPanelView, "OthelloPanelView"),
                (call_panel.CallPanelView, "CallPanelView"),
                (auth_panel.AuthPanelView, "AuthPanelView"),
                (role_panel.RoleSelectPanelView, "RoleSelectPanelView"),
                (revoke_panel.RoleRevokePanelView, "RoleRevokePanelView"),
                (voice_panel.VoiceCreatePanelView, "VoiceCreatePanelView"),
                (ranking_panel.RankingPanelView, "RankingPanelView"),
                (ElevatorView, "ElevatorView"),
                (MinesWebStartView, "MinesWebStartView"),
            ]
            for view_cls, name in views_to_register:
                instance = check_view_no_args(view_cls, name)
                if instance:
                    self.add_view(instance)
                    print(f"   ✅ {name}")
                else:
                    all_ok = False
            clv = CommandListView()
            clv.tree = self.tree
            self.add_view(clv)
            print("   ✅ CommandListView")
            if all_ok:
                print("✅ 全View 永続登録完了 ✨")
            else:
                print("⚠️ 上記の❌ を修正して再起動してください")
        except Exception as e:
            print(f"❌ View登録エラー: {e}")
            import traceback
            traceback.print_exc()
        # --- 各機能セットアップ ---
        print("\n🔄 コマンド登録中...")
        tree = self.tree
        await lottery_setup(tree, self); print("  ✅ lottery_panel")
        await login_bonus_setup(tree, self); print("  ✅ login_bonus")
        await slots_setup(tree, self); print("  ✅ slots_panel")
        await blackjack_setup(tree, self); print("  ✅ blackjack_panel")
        await highlow_setup(tree, self); print("  ✅ highlow_panel")
        await point_admin_setup(tree, self); print("  ✅ point_admin_panel")
        await embed_sender.setup(tree); print("  ✅ embed_sender")
        await clear_messages.setup(tree); print("  ✅ clear_messages")
        await moderation_panel.setup(tree, self); print("  ✅ moderation_panel")
        await security_panel.setup(tree, self); print("  ✅ security_panel")
        await invite_link.setup(tree); print("  ✅ invite_link")
        await backup_panel.setup(tree, self); print("  ✅ backup_panel")
        await command_list_panel.setup(tree); print("  ✅ command_list_panel")
        await othello.setup(tree); print("  ✅ othello")
        await othello_panel.setup(tree, self); print("  ✅ othello_panel")
        await auth_panel.setup(tree, self); print("  ✅ auth_panel")
        await role_panel.setup(tree, self); print("  ✅ role_panel")
        await revoke_panel.setup(tree, self); print("  ✅ revoke_panel")
        await call_panel.setup(tree, self); print("  ✅ call_panel")
        await welcome_leave.setup(self); print("  ✅ welcome_leave")
        await voice_panel.setup(tree, self); print("  ✅ voice_panel")
        await ranking_panel.setup(tree, self); print("  ✅ ranking_panel")
        await elevator_panel.setup(tree, self); print("  ✅ elevator_panel")
        try:
            await mines_panel.setup(tree, self)
            print("  ✅ mines_panel")
        except Exception as e:
            print(f"  ⚠️ mines_panel エラー（スキップ）: {e}")
        # --- マインスパネル設置コマンド ---
        @tree.command(name="マインズパネル設置", description="💎 マインスパネルを設置（オーナー専用）")
        async def mine_panel_cmd(inter: discord.Interaction):
            if not is_owner(inter):
                await inter.response.send_message("❌ オーナー専用です", ephemeral=True)
                return
            from features.mines_panel import MinesWebStartView
            em = discord.Embed(
                title="💎 マインス ゲーム",
                description=(
                    "下のボタンを押してゲームを始めてください✨\n"
                    "✅ チャンネル作成不要・すぐ遊べます"
                ),
                color=0x2ECC71
            )
            await inter.response.send_message(embed=em, view=MinesWebStartView())
            await inter.followup.send("✅ パネル設置完了", ephemeral=True)
        print("  ✅ マインスコマンド登録完了")
        # --- スラッシュコマンド同期 ---
        print("\n🔁 スラッシュコマンド同期中...")
        synced = await tree.sync()
        print(f"✅ 同期完了！合計 {len(synced)} 件")
        # --- 自動更新タスク ---
        print("\n🔄 自動更新タスク起動中...")
        asyncio.create_task(ranking_panel.auto_update_task(self))
        print("✅ ランキング自動更新タスク起動完了")
        self._ready_done = True
bot_main = YWPBot()
# ==================================================
# 🔵 サブBot（任意）
# ==================================================
TOKEN_SUB = os.getenv("DISCORD_TOKEN_SUB")
bot_sub = None
if TOKEN_SUB:
    print(f"✅ サブトークン読み込み完了：{TOKEN_SUB[:10]}...")
    intents_sub = discord.Intents.default()
    intents_sub.message_content = True
    intents_sub.members = True
    class SubBot(discord.Client):
        def __init__(self):
            super().__init__(intents=intents_sub)
            self.tree = app_commands.CommandTree(self)
            self._ready_done = False
        async def on_ready(self):
            if self._ready_done:
                return
            self._ready_done = True
            print(f"\n========== サブBot 起動 ==========")
            print(f"✅ ログイン：{self.user}")
            print("✅ サブBot 準備完了\n")
    bot_sub = SubBot()
else:
    print("⚠️ 環境変数 DISCORD_TOKEN_SUB が未設定 → サブBotは起動しません")
# ==================================================
# 起動イベント
# ==================================================
@bot_main.event
async def on_message(message):
    if message.guild and not message.author.bot:
        await security_panel.check_forbidden_words(message)
        await security_panel.check_link_restriction(message)
@bot_main.event
async def on_ready():
    if bot_main._ready_done:
        return
    print(f"\n========== メインBot 起動 ==========")
    print(f"✅ Logged in as {bot_main.user} ({bot_main.user.id})")
    print(f"📡 接続サーバー: {len(bot_main.guilds)}件")
    last_reason = get_and_clear_reason()
    if last_reason == "restart_button":
        await send_status_embed(bot_main, "✅ 再起動完了",
            "ボタン操作により再起動されました。\n全パネル復旧済みです✨", 0xF39C12)
    else:
        await send_status_embed(bot_main, "🔄 起動完了",
            "機能追加・更新により起動しました。\n全パネル復旧済みです✨", 0x9B59B6)
    print("✅ メインBot 準備完了\n")
@bot_main.event
async def on_close():
    if not os.path.exists(REASON_FILE):
        set_reason("update")
# ==================================================
# 🚀 並行起動
# ==================================================
async def main():
    tasks = [bot_main.start(os.getenv("DISCORD_TOKEN"))]
    if TOKEN_SUB and bot_sub:
        tasks.append(bot_sub.start(TOKEN_SUB))
    await asyncio.gather(*tasks)
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 停止")
