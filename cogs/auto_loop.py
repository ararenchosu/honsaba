import discord
from discord import app_commands
from discord.ext import commands
import asyncio

# 他のCogから共通関数をインポート（既存のものをそのまま使う）
from cogs.stage_analyze import load_sessions, normalize_account_list

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
            color=0x00D16F
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
        return True, "自動周回を開始しました。状況はDMでお届けします📩"

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
                    color=0x2584FF
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
            color=0x00D16F
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
# Cog本体
# ============================================================
class AutoLoopCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = AutoLoopManager(bot)

    @app_commands.command(name="自動周回", description="指定したステージを自動で周回（5回ごとにDM通知）")
    @app_commands.describe(
        stage_id="周回するステージID",
        count="回数（空欄=無制限）",
        interval="実行間隔（秒）"
    )
    async def start_auto(
        self,
        interaction: discord.Interaction,
        stage_id: int,
        count: int = 999999,
        interval: float = 2.0
    ):
        # ログイン確認
        sessions = load_sessions()
        user_data = sessions.get(str(interaction.user.id))
        if not user_data:
            await interaction.response.send_message(
                "❌ 先に `/ywp_login` でログインしてください。",
                ephemeral=True
            )
            return

        accounts = normalize_account_list(user_data)
        if not accounts:
            await interaction.response.send_message("❌ アカウントが見つかりません", ephemeral=True)
            return

        acc = accounts[0]
        udkey = acc.get("udkey") or acc.get("udkey_encoded")
        if not udkey:
            await interaction.response.send_message(
                "❌ udkeyが見つかりません。再ログインしてください。",
                ephemeral=True
            )
            return

        from cogs.ywp_auto import Client
        client = Client(udkey)
        client.login(acc.get("userId"))

        ok, msg = await self.manager.start_loop(
            interaction.user.id, client, stage_id, count, interval
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="自動周回停止", description="実行中の自動周回を中断")
    async def stop_auto(self, interaction: discord.Interaction):
        if self.manager.stop_loop(interaction.user.id):
            await interaction.response.send_message(
                "🛑 自動周回を停止しました。DMに最終結果が届きます。",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ 自動周回は実行されていません。",
                ephemeral=True
            )

    @app_commands.command(name="自動周回状況", description="現在の実行状況を確認")
    async def status_auto(self, interaction: discord.Interaction):
        info = self.manager.get_status(interaction.user.id)
        if not info:
            await interaction.response.send_message(
                "❌ 自動周回は実行されていません。",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📊 自動周回 実行中",
            description=(
                f"📍 ステージ: `{info['stage_id']}`\n"
                f"🔄 実行済: {info['done']}/{info['total'] if info['total'] != 999999 else '∞'}\n"
                f"✅ 成功: {info['success']}\n"
                f"❌ 失敗: {info['failed']}"
            ),
            color=0x2584FF
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoLoopCog(bot))
