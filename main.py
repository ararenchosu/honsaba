import discord
from discord import app_commands
import asyncio
import os
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

JST = timezone(timedelta(hours=9))
STATUS_LOG_CHANNEL_ID = 1559119439981449256
REASON_FILE = ".last_stop_reason"

# ==================================================
# 🔴 Bot1：メインBot
# ==================================================
TOKEN_MAIN = os.getenv("DISCORD_TOKEN")
if not TOKEN_MAIN:
    print("❌ 環境変数 DISCORD_TOKEN が設定されていません")
    exit(1)
print(f"✅ メイントークン読み込み完了：{TOKEN_MAIN[:10]}...")

intents_main = discord.Intents.default()
intents_main.message_content = True
intents_main.members = True
bot_main = discord.Client(intents=intents_main)
tree_main = app_commands.CommandTree(bot_main)

# 重複実行防止用フラグ
bot_main._ready_executed = False

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

@bot_main.event
async def on_message(message):
    if message.guild and not message.author.bot:
        await security_panel.check_forbidden_words(message)
        await security_panel.check_link_restriction(message)

@bot_main.event
async def on_ready():
    # 重複実行を完全にブロック
    if bot_main._ready_executed:
        return
    bot_main._ready_executed = True

    print(f"\n========== メインBot 起動 ==========")
    print(f"✅ ログイン：{bot_main.user}")
    
    last_reason = get_and_clear_reason()
    
    def check_view_no_args(view_class, view_name: str):
        try:
            instance = view_class()
            if instance.timeout is not None:
                print(f"   ⚠️ 【{view_name}】: timeout が None になっていません")
            return instance
        except TypeError as e:
            print(f"   ❌ 【{view_name}】: 引数が必要 → {e}")
            return None

    print("\n🔍 メインBot View 永続化チェック & 登録中...")
    all_ok_main = True
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
        from features.mines_panel import MinesStartPanelView, BombsSelectView
        
        views_to_register_main = [
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
            (MinesStartPanelView, "MinesStartPanelView"),
            (BombsSelectView, "BombsSelectView"),
        ]
        
        for view_cls, name in views_to_register_main:
            instance = check_view_no_args(view_cls, name)
            if instance:
                bot_main.add_view(instance)
                print(f"   ✅ {name}")
            else:
                all_ok_main = False
        
        clv = CommandListView()
        clv.tree = tree_main
        bot_main.add_view(clv)
        print("   ✅ CommandListView")
        
        if all_ok_main:
            print("✅ メインBot 全View 永続登録完了 ✨")
        else:
            print("⚠️ メインBot：上記の❌ を修正して再起動してください")
            
    except Exception as e:
        print(f"❌ メインBot View登録エラー: {e}")
        import traceback
        traceback.print_exc()

    print("\n🔄 メインBot コマンド登録中...")
    await lottery_setup(tree_main, bot_main); print("  ✅ lottery_panel")
    await login_bonus_setup(tree_main, bot_main); print("  ✅ login_bonus")
    await slots_setup(tree_main, bot_main); print("  ✅ slots_panel")
    await blackjack_setup(tree_main, bot_main); print("  ✅ blackjack_panel")
    await highlow_setup(tree_main, bot_main); print("  ✅ highlow_panel")
    await point_admin_setup(tree_main, bot_main); print("  ✅ point_admin_panel")
    await embed_sender.setup(tree_main); print("  ✅ embed_sender")
    await clear_messages.setup(tree_main); print("  ✅ clear_messages")
    await moderation_panel.setup(tree_main, bot_main); print("  ✅ moderation_panel")
    await security_panel.setup(tree_main, bot_main); print("  ✅ security_panel")
    await invite_link.setup(tree_main, bot_main); print("  ✅ invite_link")
    await backup_panel.setup(tree_main, bot_main); print("  ✅ backup_panel")
    await command_list_panel.setup(tree_main); print("  ✅ command_list_panel")
    await othello.setup(tree_main); print("  ✅ othello")
    await othello_panel.setup(tree_main, bot_main); print("  ✅ othello_panel")
    await auth_panel.setup(tree_main, bot_main); print("  ✅ auth_panel")
    await role_panel.setup(tree_main, bot_main); print("  ✅ role_panel")
    await revoke_panel.setup(tree_main, bot_main); print("  ✅ revoke_panel")
    await call_panel.setup(tree_main, bot_main); print("  ✅ call_panel")
    await welcome_leave.setup(bot_main); print("  ✅ welcome_leave")
    await voice_panel.setup(tree_main, bot_main); print("  ✅ voice_panel")
    await ranking_panel.setup(tree_main, bot_main); print("  ✅ ranking_panel")
    await elevator_panel.setup(tree_main, bot_main); print("  ✅ elevator_panel")
    
    # mines_panel は実行しても止まらないように先に実行
    await mines_panel.setup(tree_main, bot_main)
    print("  ✅ mines_panel")

    # ✅ マインス コマンドを絶対に登録（ここが核心！）
    @tree_main.command(name="マインズパネル設置", description="💎 マインスパネルを設置（オーナー専用）")
    async def cmd_mine_panel(inter: discord.Interaction):
        if not is_owner(inter):
            await inter.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        from features.mines_panel import MinesStartPanelView
        embed = discord.Embed(
            title="💎 マインス 💣",
            description=(
                "下のボタンから難易度を選んでゲームを始められます！\n"
                "✅ かんたん [3個] ｜ ⚪ ふつう [5個] ｜ 🔴 むずかしい [8個] ｜ ⚙️ 自分で設定"
            ),
            color=0x1a1a1a
        )
        await inter.response.send_message(embed=embed, view=MinesStartPanelView())
        await inter.followup.send("✅ マインスパネル設置完了", ephemeral=True)

    print("  ✅ マインスコマンド 直接登録完了")
    print("✅ メインBot 全コマンド登録完了")
    
    print("\n🔄 メインBot グローバル同期中...")
    synced_main = await tree_main.sync()
    print(f"✅ メインBot 同期完了！合計 {len(synced_main)} 件")
    
    print("\n🔄 自動更新タスク起動中...")
    asyncio.create_task(ranking_panel.auto_update_task(bot_main))
    print("✅ ランキング自動更新タスク起動完了")
    
    # ✅ 起動ログ送信
    if last_reason == "restart_button":
        await send_status_embed(bot_main, "✅ 再起動完了",
            "ボタン操作により再起動されました。\n全パネル復旧済みです✨", 0xF39C12)
    else:
        await send_status_embed(bot_main, "🔄 起動完了",
            "機能追加・更新により起動しました。\n全パネル復旧済みです✨", 0x9B59B6)
    print("✅ 起動通知送信完了")
    print("✅ メインBot 準備完了\n")

@bot_main.event
async def on_close():
    if not os.path.exists(REASON_FILE):
        set_reason("update")

# ==================================================
# 🔵 Bot2：サブBot
# ==================================================
TOKEN_SUB = os.getenv("DISCORD_TOKEN_SUB")
bot_sub = None
tree_sub = None

if TOKEN_SUB:
    print(f"✅ サブトークン読み込み完了：{TOKEN_SUB[:10]}...")
    intents_sub = discord.Intents.default()
    intents_sub.message_content = True
    intents_sub.members = True
    bot_sub = discord.Client(intents=intents_sub)
    tree_sub = app_commands.CommandTree(bot_sub)
    
    bot_sub._ready_executed = False
    
    @bot_sub.event
    async def on_ready():
        if bot_sub._ready_executed:
            return
        bot_sub._ready_executed = True
        print(f"\n========== サブBot 起動 ==========")
        print(f"✅ ログイン：{bot_sub.user}")
        print("✅ サブBot 準備完了\n")
else:
    print("⚠️ 環境変数 DISCORD_TOKEN_SUB が未設定 → サブBotは起動しません")

# ==================================================
# 🚀 並行起動
# ==================================================
async def main():
    init_db()
    print("🔄 データベース初期化完了")
    tasks = [bot_main.start(TOKEN_MAIN)]
    if TOKEN_SUB and bot_sub:
        tasks.append(bot_sub.start(TOKEN_SUB))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
