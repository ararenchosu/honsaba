import discord
from .othello_board import OthelloBoard

BLACK = "black"
WHITE = "white"


class OthelloView(discord.ui.View):
    def __init__(self, game, player_black, player_white, result_channel_id=None, ticket_channel=None):
        super().__init__(timeout=None)
        self.game = game
        self.player_black = player_black
        self.player_white = player_white
        self.board = game.board
        self.main_message = None
        self.result_channel_id = result_channel_id
        self.ticket_channel = ticket_channel
        self.force_ended = False
        self.game_completed = False
        self.selected_col = None
        # ✅ 終了時に呼び出す処理を外部から受け取る
        self.cleanup_callback = None

    async def build_embed(self):
        b, w = self.board.count()
        if self.selected_col is None:
            turn_text = (
                "⚫ 黒の番です — a～h から列を選んでください"
                if self.board.current == BLACK
                else "⚪ 白の番です — a～h から列を選んでください"
            )
        else:
            turn_text = f"👇 {chr(ord('ａ') + self.selected_col)}列を選択中 — 数字(1～8)で行を選んでください"

        embed = discord.Embed(title="🔳 オセロ", description=self.board.render(), color=0x222222)
        embed.add_field(
            name="状況",
            value=f"黒：{b}　白：{w}\n{turn_text}",
            inline=False,
        )
        embed.add_field(
            name="プレイヤー",
            value=f"{self.player_black.mention} 黒\n{self.player_white.mention} 白",
            inline=False,
        )
        return embed

    def check_turn(self, interaction):
        if self.force_ended or self.game_completed:
            return False
        if self.board.current == BLACK and interaction.user.id != self.player_black.id:
            return False
        if self.board.current == WHITE and interaction.user.id != self.player_white.id:
            return False
        return True

    # ===== 列選択ボタン =====
    @discord.ui.button(label="ａ", style=discord.ButtonStyle.secondary, row=0)
    async def col_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 0
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｂ", style=discord.ButtonStyle.secondary, row=0)
    async def col_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 1
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｃ", style=discord.ButtonStyle.secondary, row=0)
    async def col_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 2
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｄ", style=discord.ButtonStyle.secondary, row=0)
    async def col_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 3
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｅ", style=discord.ButtonStyle.secondary, row=0)
    async def col_e(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 4
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｆ", style=discord.ButtonStyle.secondary, row=1)
    async def col_f(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 5
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｇ", style=discord.ButtonStyle.secondary, row=1)
    async def col_g(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 6
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="ｈ", style=discord.ButtonStyle.secondary, row=1)
    async def col_h(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = 7
        await interaction.response.edit_message(embed=await self.build_embed())

    @discord.ui.button(label="⚠️ 強制終了", style=discord.ButtonStyle.danger, row=1)
    async def force_end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.force_ended or self.game_completed:
            await interaction.response.send_message(
                "❌ 既に終了しています。新しく対戦を開始してください。",
                ephemeral=True
            )
            return
        if interaction.user.id not in (self.player_black.id, self.player_white.id):
            await interaction.response.send_message("❌ 対戦者のみ実行できます", ephemeral=True)
            return

        self.force_ended = True
        self.game_completed = True
        self.disable_all_items()

        b, w = self.board.count()
        if b > w:
            result_text = f"⚫ {self.player_black.mention} の勝ち！"
        elif w > b:
            result_text = f"⚪ {self.player_white.mention} の勝ち！"
        else:
            result_text = "🤝 引き分け！"

        embed = discord.Embed(title="🔳 オセロ【強制終了】", description=self.board.render(), color=0xFF4444)
        embed.add_field(
            name="途中終了 状況",
            value=f"黒：{b}　白：{w}\n{result_text}",
            inline=False,
        )
        embed.add_field(
            name="プレイヤー",
            value=f"{self.player_black.mention} 黒\n{self.player_white.mention} 白",
            inline=False,
        )

        await interaction.response.edit_message(embed=embed, view=self)

        if self.result_channel_id and self.ticket_channel:
            guild = self.ticket_channel.guild
            result_ch = guild.get_channel(self.result_channel_id)
            if result_ch:
                res_embed = discord.Embed(title="⚠️ オセロ対戦【途中終了】", color=0xFF4444)
                res_embed.add_field(name="対戦者", value=f"⚫ {self.player_black.mention}\n⚪ {self.player_white.mention}", inline=False)
                res_embed.add_field(name="最終スコア", value=f"黒：{b}　白：{w}", inline=False)
                res_embed.add_field(name="結果", value=result_text, inline=False)
                res_embed.set_footer(text=f"終了者：{interaction.user}")
                await result_ch.send(embed=res_embed)

        # ✅ クリーンアップ実行（ID解除＋チャンネル削除）
        if self.cleanup_callback:
            await self.cleanup_callback()

    # ===== 行選択ボタン =====
    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, row=2)
    async def row1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, row=2)
    async def row2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, row=2)
    async def row3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, row=2)
    async def row4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 3)

    @discord.ui.button(label="5", style=discord.ButtonStyle.primary, row=2)
    async def row5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 4)

    @discord.ui.button(label="6", style=discord.ButtonStyle.primary, row=3)
    async def row6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 5)

    @discord.ui.button(label="7", style=discord.ButtonStyle.primary, row=3)
    async def row7(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 6)

    @discord.ui.button(label="8", style=discord.ButtonStyle.primary, row=3)
    async def row8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._place_stone(interaction, 7)

    @discord.ui.button(label="✖ キャンセル", style=discord.ButtonStyle.secondary, row=3)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        self.selected_col = None
        await interaction.response.edit_message(embed=await self.build_embed())

    async def _place_stone(self, interaction, row):
        if self.force_ended or self.game_completed:
            await interaction.response.send_message(
                "❌ この対戦は既に終了しています。新しく対戦を開始してください。",
                ephemeral=True,
            )
            return
        if not self.check_turn(interaction):
            await interaction.response.send_message("自分の番ではありません", ephemeral=True)
            return
        if self.selected_col is None:
            await interaction.response.send_message("先に列(a～h)を選んでください", ephemeral=True)
            return

        col = self.selected_col
        self.selected_col = None

        if not self.board.put(row, col):
            await interaction.response.send_message("❌ そこには置けません", ephemeral=True)
            await interaction.response.edit_message(embed=await self.build_embed())
            return

        next_color = WHITE if self.board.current == BLACK else BLACK
        if not self.board.can_put(next_color) and not self.board.is_game_over():
            self.board.current = next_color

        new_embed = await self.build_embed()

        if self.board.is_game_over():
            self.game_completed = True
            b, w = self.board.count()
            if b > w:
                result = f"⚫ {self.player_black.mention} の勝ち！"
            elif w > b:
                result = f"⚪ {self.player_white.mention} の勝ち！"
            else:
                result = "🤝 引き分け！"

            new_embed.set_field_at(
                0,
                name="🏆 対戦結果",
                value=f"黒：{b}　白：{w}\n{result}",
                inline=False,
            )
            self.disable_all_items()

            if self.result_channel_id and self.ticket_channel:
                guild = self.ticket_channel.guild
                result_ch = guild.get_channel(self.result_channel_id)
                if result_ch:
                    res_embed = discord.Embed(title="🎮 オセロ対戦結果", color=0x2ECC71)
                    res_embed.add_field(name="対戦者", value=f"⚫ {self.player_black.mention}\n⚪ {self.player_white.mention}", inline=False)
                    res_embed.add_field(name="最終スコア", value=f"黒：{b}　白：{w}", inline=False)
                    res_embed.add_field(name="結果", value=result, inline=False)
                    await result_ch.send(embed=res_embed)

            await interaction.response.edit_message(embed=new_embed, view=self)

            # ✅ クリーンアップ実行（ID解除＋チャンネル削除）
            if self.cleanup_callback:
                await self.cleanup_callback()
        else:
            await interaction.response.edit_message(embed=new_embed, view=self)

    def disable_all_items(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
