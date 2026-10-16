import discord
from discord import app_commands
from core.common import is_owner

async def setup(tree):
    @tree.command(name="emb", description="埋め込みメッセージを送信（オーナー専用）")
    @app_commands.describe(title="タイトル", desc="説明文", color="色コード（例：ff0000=赤）")
    async def emb_cmd(itx: discord.Interaction, title: str, desc: str, color: str = "2ecc71"):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        try:
            col = int(color, 16)
        except:
            col = 0x2ecc71
        embed = discord.Embed(title=title, description=desc, color=col)
        await itx.response.send_message(embed=embed)
