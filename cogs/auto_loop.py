import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# ✅ Clientだけインポート、sessionsはこのファイル内で管理
from cogs.ywp_auto import Client

# ✅ このファイル専用のセッション管理
sessions = {}

# ============================================================
# 自動周回マネージャー
# ============================================================
class AutoLoopManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.running = {}

    async def send_dm(self, user_id: int, content: str, embed=None):
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if not user:
                return False
            await user.send(content=content, embed=embed)
            return True
        except Exception as e:
            print(f"⚠️ DM送信失敗 (user:{user_id}): {e}")
            return False

    async def start_loop(
        self,
        user_id: int,
        client,
        stage_id: int,
        count: int = 999999,
        interval: float = 2.0
    ):
        if user_id in self.running:
            return False, "既に実行中です。先に停止してください。"

        start_embed = discord.Embed(
            title="🔄 自動周回 開始",
            description=f"📌 ステージID: `{stage_id}`\n"
                        f"🎯 目標回数: {'無制限' if count == 999999 else f'{count}回'}\n"
                        f"⏱ 実行間隔: {interval}秒\n"
                        f"📩 通知: 5回ごとにお届け",
            color=0x00D16F,
            timestamp=datetime.now(JST)
        )
        await self.send_dm(user_id, "✅ 自動周回を開始します！", embed=start_embed)

        self.running[user_id] = {
            "stage_id": stage_id,
            "total": count,
            "done": 0,
            "success": 0,
            "failed": 0,
        }

        asyncio.create_task(
            self._loop_task(user_id, client, stage_id, count, interval)
        )
        return True, "周回開始！DMで状況を確認してください📩"

    async def _loop_task(self, user_id: int, client, stage_id: int, count: int, interval: float):
        info = self.running[user_id]
        start_time = asyncio.get_event_loop().time()

        while info["done"] < count:
            if user_id not in self.running:
                await self.send_dm(user_id, "🛑 自動周回が停止されました。")
                return

            try:
                rc, res = client.battle(stage_id)
                if rc == 0 or res.get("resultCode") == 0:
                    info["success"] += 1
                else:
                    info["failed"] += 1
                    if info["failed"] % 5 == 1:
                        await self.send_dm(
                            user_id,
                            f"⚠️ ステージ`{stage_id}` でエラー: rc={rc}\n"
                            f"続行中… 成功:{info['success']} 失敗:{info['failed']}"
                        )
            except Exception as e:
                info["failed"] += 1
                await self.send_dm(
                    user_id,
                    f"❌ 例外エラー: {str(e)[:100]}\n続行中…"
                )

            info["done"] += 1

            # ✅ 5回ごとに通知
            if info["done"] % 5 == 0 or info["done"] == count:
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                progress = f"{info['done']}/{count}" if count != 999999 else f"{info['done']}回"

                embed = discord.Embed(
                    title="📊 自動周回 状況",
                    description=(
                        f"📍 ステージ: `{stage_id}`\n"
                        f"🔄 実行済: {progress}\n"
                        f"✅ 成功: {info['success']}回\n"
                        f"❌ 失敗: {info['failed']}回\n"
                        f"⏱ 経過時間: {elapsed//60}分{elapsed%60}秒"
                    ),
                    color=0x2584FF,
                    timestamp=datetime.now(JST)
                )
                await self.send_dm(user_id, content="", embed=embed)

            await asyncio.sleep(interval)

        # 完了通知
        elapsed = int(asyncio.get_event_loop().time() - start_time)
        finish_embed = discord.Embed(
            title="🎉 自動周回 完了！",
            description=(
                f"📍 ステージ: `{stage_id}`\n"
                f"✅ 成功: {info['success']}回\n"
                f"❌ 失敗: {info['failed']}回\n"
                f"⏱ 合計時間: {elapsed//60}分{elapsed%60}秒"
            ),
            color=0x00D16F,
            timestamp=datetime.now(JST)
        )
        await self.send_dm(user_id, "✅ 設定された回数に到達しました！", embed=finish_embed)
        del self.running[user_id]

    def stop_loop(self, user_id: int) -> bool:
        if user_id in self.running:
            del self.running[user_id]
            return True
        return False

    def get_status(self, user_id: int):
        return self.running.get(user_id)

# ============================================================
# パネル用View
# ============================================================
class AutoLoopPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔑 ログイン", style=discord.ButtonStyle.primary, custom_id="autoloop:login")
    async def login_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📋 ログイン情報をDMで送信してください\n"
            "下記の形式で送信してください：\n"
            "`udkey:ここにudkeyを入力`",
            ephemeral=True
        )

    @discord.ui.button(label="🔄 周回設定", style=discord.ButtonStyle.green, custom_id="autoloop:settings")
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AutoLoopModal())

    @discord.ui.button(label="🛑 停止", style=discord.ButtonStyle.danger, custom_id="autoloop:stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("AutoLoopCog")
        if cog and cog.manager.stop_loop(interaction.user.id):
            await interaction.response.send_message(
                "🛑 停止しました。DMに最終結果が届きます。",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ 実行中の周回はありません。",
                ephemeral=True
            )

    @discord.ui.button(label="📊 状況", style=discord.ButtonStyle.secondary, custom_id="autoloop:status")
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("AutoLoopCog")
        if not cog:
            await interaction.response.send_message("❌ 機能が見つかりません", ephemeral=True)
            return

        info = cog.manager.get_status(interaction.user.id)
        if not info:
            await interaction.response.send_message("❌ 実行中の周回はありません。", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 自動周回 実行中",
            description=(
                f"📍 ステージ: `{info['stage_id']}`\n"
                f"🔄 実行済: {info['done']}/{info['total'] if info['total'] != 999999 else '∞'}\n"
                f"✅ 成功: {info['success']}\n"
                f"❌ 失敗: {info['failed']}"
            ),
            color=0x2584FF,
            timestamp=datetime.now(JST)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# 周回設定モーダル
# ============================================================
class AutoLoopModal(discord.ui.Modal, title="自動周回設定"):
    stage_id = discord.ui.TextInput(
        label="周回するステージID",
        placeholder="例: 29901011",
        required=True
    )
    count = discord.ui.TextInput(
        label="回数（空欄=無制限）",
        placeholder="例: 50",
        required=False
    )
    interval = discord.ui.TextInput(
        label="実行間隔（秒）",
        default="2.0",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # ✅ このファイル内のsessionsから取得
        user_id_str = str(interaction.user.id)
        user_data = sessions.get(user_id_str)

        if not user_data:
            await interaction.response.send_message(
                "❌ まず最初に「🔑 ログイン」ボタンからudkeyをDMで送信してログインしてください。",
                ephemeral=True
            )
            return

        udkey = user_data.get("udkey")
        if not udkey:
            await interaction.response.send_message(
                "❌ udkeyが見つかりません。再度「🔑 ログイン」から登録してください。",
                ephemeral=True
            )
            return

        # 入力値処理
        try:
            stage_id_val = int(self.stage_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ステージIDは数字で入力してください", ephemeral=True)
            return

        try:
            count_val = int(self.count.value.strip()) if self.count.value.strip() else 999999
        except ValueError:
            count_val = 999999

        try:
            interval_val = float(self.interval.value.strip())
        except ValueError:
            interval_val = 2.0

        # Client作成・ログイン
        client = Client(udkey)
        client.login(str(interaction.user.id))

        # 周回開始
        cog = interaction.client.get_cog("AutoLoopCog")
        ok, msg = await cog.manager.start_loop(
            interaction.user.id, client, stage_id_val, count_val, interval_val
        )
        await interaction.response.send_message(msg, ephemeral=True)

# ============================================================
# Cog本体
# ============================================================
class AutoLoopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = AutoLoopManager(bot)

    @app_commands.command(name="自動周回パネル", description="💎 自動周回パネルを表示")
    async def panel_cmd(self, interaction: discord.Interaction):
        em = discord.Embed(
            title="🔄 自動周回 管理パネル",
            description=(
                "🔑 ログイン → DMに `udkey:xxxx` と送信\n"
                "🔄 周回設定 → 条件を入力して開始\n"
                "🛑 停止 → 実行中の周回を中断\n"
                "📊 状況 → 現在の進捗を確認\n\n"
                "📩 状況はDMに5回ごとにお届けします"
            ),
            color=0x2584FF,
            timestamp=datetime.now(JST)
        )
        em.set_footer(text=f"ユーザー: {interaction.user}")
        await interaction.response.send_message(embed=em, view=AutoLoopPanelView(), ephemeral=False)

    # ログイン受信用メッセージ監視
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        # DM以外は無視
        if message.guild:
            return

        content = message.content.strip()
        if content.lower().startswith("udkey:"):
            udkey_val = content[len("udkey:"):].strip()
            if not udkey_val:
                await message.channel.send("❌ udkeyが空です", delete_after=5)
                return

            # ✅ このファイル内のsessionsに保存
            user_id_str = str(message.author.id)
            sessions[user_id_str] = {
                "udkey": udkey_val,
                "userId": user_id_str,
                "discord_id": user_id_str,
                "logged_at": datetime.now(JST).isoformat()
            }

            await message.channel.send(
                "✅ ログイン完了！次にパネルの「🔄 周回設定」ボタンから設定してください。",
                delete_after=10
            )
            # メッセージ削除（セキュリティ）
            try:
                await message.delete()
            except:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoLoopCog(bot))
    # View永続化登録
    bot.add_view(AutoLoopPanelView())
