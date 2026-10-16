import discord
from discord import app_commands
import os
import shutil
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
STATUS_LOG_CHANNEL_ID = 1559119439981449256
REASON_FILE = ".last_stop_reason"
BACKUP_DIR = "data_backup"
DATA_DIR = "data"
DB_FILE = "kn_server.db"
POINT_FILE = "kn_points_data.json"

os.makedirs(BACKUP_DIR, exist_ok=True)

BACKUP_HOURS = list(range(1, 25))  # 1時～24時まで毎時
auto_backup_task = None

def set_reason(reason: str):
    with open(REASON_FILE, "w", encoding="utf-8") as f:
        f.write(reason)

def clear_reason_file():
    if os.path.exists(REASON_FILE):
        try: os.remove(REASON_FILE)
        except: pass

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

def get_latest_backup():
    if not os.path.exists(BACKUP_DIR):
        return None
    backups = sorted(os.listdir(BACKUP_DIR), reverse=True)
    return backups[0] if backups else None

def cleanup_old_backups():
    if not os.path.exists(BACKUP_DIR):
        return
    backups = sorted(os.listdir(BACKUP_DIR), reverse=True)
    if len(backups) <= 1:
        return
    for old_name in backups[1:]:
        old_path = os.path.join(BACKUP_DIR, old_name)
        try:
            if os.path.isdir(old_path):
                shutil.rmtree(old_path)
            else:
                os.remove(old_path)
            print(f"🗑️ 古いバックアップ削除: {old_name}")
        except Exception as e:
            print(f"⚠️ 削除失敗 {old_name}: {e}")

def create_backup(note: str = ""):
    cleanup_old_backups()
    suffix = f"_{note}" if note else ""
    now = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{now}{suffix}")
    os.makedirs(backup_path, exist_ok=True)
    
    if os.path.exists(os.path.join(DATA_DIR, DB_FILE)):
        shutil.copy2(os.path.join(DATA_DIR, DB_FILE), backup_path)
    if os.path.exists(os.path.join(DATA_DIR, POINT_FILE)):
        shutil.copy2(os.path.join(DATA_DIR, POINT_FILE), backup_path)
    
    return backup_path

def restore_backup(backup_name: str):
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    if not os.path.exists(backup_path):
        return False, "バックアップが見つかりません"
    try:
        if os.path.exists(os.path.join(backup_path, DB_FILE)):
            shutil.copy2(os.path.join(backup_path, DB_FILE), os.path.join(DATA_DIR, DB_FILE))
        if os.path.exists(os.path.join(backup_path, POINT_FILE)):
            shutil.copy2(os.path.join(backup_path, POINT_FILE), os.path.join(DATA_DIR, POINT_FILE))
        return True, "復元完了"
    except Exception as e:
        return False, str(e)

async def auto_backup_scheduler(client):
    await client.wait_until_ready()
    last_executed_hour = None
    while not client.is_closed():
        now = get_jst_now()
        current_hour = now.hour
        effective_hour = 24 if current_hour == 0 else current_hour
        if effective_hour in BACKUP_HOURS and last_executed_hour != effective_hour:
            try:
                path = create_backup("定刻")
                print(f"✅ 定刻バックアップ実行: {now.strftime('%H時')} → {path}")
                await send_status_embed(
                    client,
                    title=f"⏰ 定刻バックアップ（{now.strftime('%H時')}）",
                    description=f"スケジュールされた時間にバックアップを実行しました。\n📁 `{path}`\n✅ 最新1件のみ保持中",
                    color=0x3498DB
                )
                last_executed_hour = effective_hour
            except Exception as e:
                print(f"⚠️ 定刻バックアップエラー: {e}")
        await asyncio.sleep(30)

def start_auto_backup(client):
    global auto_backup_task
    if auto_backup_task is None or auto_backup_task.done():
        auto_backup_task = asyncio.create_task(auto_backup_scheduler(client))
        schedule_str = " / ".join(f"{h}時" for h in BACKUP_HOURS)
        print(f"✅ 定刻バックアップ開始（毎日 {schedule_str}）")

def get_panel_embed():
    latest = get_latest_backup()
    schedule_str = " / ".join(f"{h}時" for h in BACKUP_HOURS)
    status = "⏸️ 停止中（手動で開始）"
    if auto_backup_task and not auto_backup_task.done():
        status = "✅ 稼働中"
    embed = discord.Embed(
        title="📦 データバックアップ・管理",
        description=(
            f"{status}\n"
            f"⏰ 定刻: 毎日 {schedule_str}\n"
            "💾 最新を永久保存 → 手動保存\n"
            "▶️ 定刻監視開始 → 毎日の自動実行をON\n"
            "⏹️ 定刻監視停止 → 毎日の自動実行をOFF\n"
            "📥 保存分を復元 → 最新の状態に戻す\n"
            "🔄 Botを再起動 → 自動的に復帰✨"
        ),
        color=0x2ECC71
    )
    embed.add_field(
        name="📋 最新（1件保持）",
        value=f"`{latest}`" if latest else "なし",
        inline=False
    )
    return embed

class BackupPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def check_owner(self, itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナーのみ実行可能です", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(
        label="💾 最新を永久保存",
        style=discord.ButtonStyle.primary,
        custom_id="backup:create"
    )
    async def backup_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        path = create_backup("手動")
        await itx.response.edit_message(embed=get_panel_embed())
        await itx.followup.send(f"✅ バックアップを保存\n📁 `{path}`", ephemeral=True)
    
    @discord.ui.button(
        label="▶️ 定刻監視開始",
        style=discord.ButtonStyle.success,
        custom_id="backup:start_schedule"
    )
    async def start_schedule_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        if auto_backup_task and not auto_backup_task.done():
            await itx.response.send_message("✅ 既に定刻監視は稼働中です", ephemeral=True)
            return
        start_auto_backup(itx.client)
        await itx.response.edit_message(embed=get_panel_embed())
        await itx.followup.send("✅ 定刻バックアップ監視を開始しました", ephemeral=True)
    
    @discord.ui.button(
        label="⏹️ 定刻監視停止",
        style=discord.ButtonStyle.secondary,
        custom_id="backup:stop_schedule"
    )
    async def stop_schedule_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        global auto_backup_task
        if auto_backup_task and not auto_backup_task.done():
            auto_backup_task.cancel()
            auto_backup_task = None
            await itx.response.edit_message(embed=get_panel_embed())
            await itx.followup.send("✅ 定刻監視を停止しました", ephemeral=True)
        else:
            await itx.response.send_message("⚠️ 定刻監視は既に停止しています", ephemeral=True)
    
    @discord.ui.button(
        label="🔄 パネル情報更新",
        style=discord.ButtonStyle.secondary,
        custom_id="backup:refresh"
    )
    async def refresh_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        await itx.response.edit_message(embed=get_panel_embed())
        await itx.followup.send("✅ パネル情報を最新に更新しました", ephemeral=True)
    
    @discord.ui.button(
        label="📥 保存分を復元",
        style=discord.ButtonStyle.danger,
        custom_id="backup:restore"
    )
    async def restore_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        latest = get_latest_backup()
        if not latest:
            await itx.response.send_message("❌ 復元可能なバックアップがありません", ephemeral=True)
            return
        await itx.response.send_message(
            f"⚠️ 復元しますか？\n`{latest}`\n※ 現在のデータは上書きされます",
            view=RestoreConfirmView(),
            ephemeral=True
        )
        itx.client._pending_restore = latest
    
    @discord.ui.button(
        label="🔄 Botを再起動",
        style=discord.ButtonStyle.secondary,
        custom_id="backup:restart"
    )
    async def restart_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not await self.check_owner(itx):
            return
        await itx.response.send_message(
            "🔄 Botを再起動します…\n✅ 数秒後に自動的に復帰します✨",
            ephemeral=True
        )
        set_reason("restart_button")
        await send_status_embed(
            itx.client, "🔄 再起動実行", "オーナーにより再起動されました", 0xF39C12
        )
        await asyncio.sleep(1)
        
        # ✅ 正常終了コードで終了 → FadeHostが自動で再起動
        sys.exit(0)

class RestoreConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="✅ 復元を実行",
        style=discord.ButtonStyle.danger,
        custom_id="backup:restore_confirm"
    )
    async def do_restore(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        backup_name = getattr(itx.client, "_pending_restore", None)
        if not backup_name:
            await itx.response.send_message("❌ 最初から操作してください", ephemeral=True)
            return
        ok, msg = restore_backup(backup_name)
        if ok:
            await itx.response.edit_message(
                content=f"✅ {msg}\n🔄 再起動ボタンを押して復帰させてください",
                view=None
            )
            await send_status_embed(
                itx.client, "📥 復元実行", f"`{backup_name}` から復元しました", 0x9B59B6
            )
            if hasattr(itx.client, "_pending_restore"):
                delattr(itx.client, "_pending_restore")
        else:
            await itx.response.edit_message(content=f"❌ 失敗：{msg}", view=None)
    
    @discord.ui.button(
        label="❌ キャンセル",
        style=discord.ButtonStyle.secondary,
        custom_id="backup:restore_cancel"
    )
    async def cancel(self, itx: discord.Interaction, btn: discord.ui.Button):
        if hasattr(itx.client, "_pending_restore"):
            delattr(itx.client, "_pending_restore")
        await itx.response.edit_message(content="✅ キャンセルしました", view=None)

async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None and not hasattr(bot, "_backup_views_registered"):
        bot.add_view(BackupPanelView())
        bot.add_view(RestoreConfirmView())
        bot._backup_views_registered = True
        print("✅ backup_panel 永続View登録完了")
    
    @tree.command(name="バックアップパネル", description="バックアップ管理パネルを表示")
    async def backup_panel_cmd(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナーのみ", ephemeral=True)
            return
        await itx.response.send_message(
            embed=get_panel_embed(),
            view=BackupPanelView()
        )
