import discord
from discord import app_commands
from core.common import is_owner

class CommandListView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永続化
        self.page = 0
        self.items_per_page = 5
        self.all_commands = []
        self.tree = None

    def make_embed(self, all_commands=None):
        if all_commands is not None:
            self.all_commands = all_commands

        cmd_list = []
        for cmd in self.all_commands:
            cmd_list.append({
                "name": f"/{cmd.name}",
                "desc": cmd.description or "説明なし"
            })

        if not cmd_list:
            total_pages = 1
            page_items = []
        else:
            total_pages = (len(cmd_list) + self.items_per_page - 1) // self.items_per_page
            start = self.page * self.items_per_page
            end = start + self.items_per_page
            page_items = cmd_list[start:end]

        embed = discord.Embed(
            title=f"📋 コマンド一覧  ({self.page+1}/{total_pages}ページ)",
            description=f"登録済み：**{len(cmd_list)}件** ｜ 🔄 更新ボタンで最新になります",
            color=0x3498DB
        )
        for info in page_items:
            embed.add_field(
                name=f"🔹 {info['name']}",
                value=(
                    "┌──────────────────────────\n"
                    f"│ 📝 {info['desc']}\n"
                    "└──────────────────────────"
                ),
                inline=False
            )
        embed.set_footer(text=f"最終更新：{discord.utils.utcnow().strftime('%H:%M:%S')} UTC")
        return embed

    @discord.ui.button(label="🔄 更新", style=discord.ButtonStyle.success, custom_id="cmdlist:refresh")
    async def refresh_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        if not self.tree:
            await itx.response.send_message("⚠️ 読み込み中です。しばらくしてからお試しください。", ephemeral=True)
            return

        self.page = 0
        # ✅ 最新のコマンド一覧を再取得
        self.all_commands = self.tree.get_commands()
        # ✅ メッセージを確実に更新
        await itx.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="◀️ 前へ", style=discord.ButtonStyle.secondary, custom_id="cmdlist:prev")
    async def prev_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        if self.page > 0:
            self.page -= 1
            await itx.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await itx.response.defer()

    @discord.ui.button(label="次へ ▶️", style=discord.ButtonStyle.primary, custom_id="cmdlist:next")
    async def next_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        if not self.all_commands:
            await itx.response.send_message("⚠️ 先に「更新」を押して一覧を読み込んでください", ephemeral=True)
            return

        total_pages = (len(self.all_commands) + self.items_per_page - 1) // self.items_per_page
        if self.page < total_pages - 1:
            self.page += 1
            await itx.response.edit_message(embed=self.make_embed(), view=self)
        else:
            await itx.response.defer()

async def setup(tree: app_commands.CommandTree):
    bot = tree.client

    # ✅ 起動時に永続Viewを1回だけ登録
    if not hasattr(bot, "_cmdlist_view_registered"):
        persistent_view = CommandListView()
        persistent_view.tree = tree
        bot.add_view(persistent_view)
        bot._cmdlist_view_registered = True

    @tree.command(
        name="コマンド確認パネル",
        description="コマンド一覧を表示（オーナー専用）"
    )
    async def cmd_list_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return

        all_cmds = tree.get_commands()
        view = CommandListView()
        view.tree = tree
        view.all_commands = all_cmds

        await itx.response.send_message(
            embed=view.make_embed(),
            view=view,
            ephemeral=False
        )
        await itx.followup.send(
            "✅ 一覧パネルを設置しました！\n"
            "🔄 コマンド追加後は「更新」を押すだけで最新になります✨",
            ephemeral=True
        )
