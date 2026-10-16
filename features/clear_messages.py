import discord
from discord import app_commands
from core.common import is_owner

async def setup(tree: app_commands.CommandTree):
    @tree.command(name="メッセージ全削除", description="チャンネルのメッセージを一括削除（オーナー専用）")
    async def cmd_clear(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return

        await itx.response.defer(ephemeral=True)  # 時間がかかるので応答を保持

        deleted_total = 0
        # 100件ずつ繰り返し削除
        while True:
            deleted = await itx.channel.purge(limit=100)
            if not deleted:
                break
            deleted_total += len(deleted)

        # 全ユーザーに見えるメッセージを送信
        await itx.channel.send(
            "⚠️ **オーナーによりメッセージが全削除されました**\n"
            f"削除されたメッセージ：{deleted_total}件"
        )

        await itx.followup.send(
            f"✅ 完了！{deleted_total}件のメッセージを削除しました",
            ephemeral=True
        )
