import discord
from discord import app_commands
from core.common import is_owner, RESULT_CHANNEL_ID, OTHELLO_CATEGORY_ID
from core.database import get_connection
import asyncio
from .othello_view import OthelloView
from .othello_board import OthelloBoard

active_games = set()

# ========== パネル保存/読み込み ==========
def save_othello_panel(channel_id: int, message_id: int, title: str, description: str, color: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS othello_panel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            color INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT OR REPLACE INTO othello_panel 
        (channel_id, message_id, title, description, color)
        VALUES (?, ?, ?, ?, ?)
    """, (str(channel_id), str(message_id), title, description, color))
    conn.commit()
    conn.close()

def get_latest_othello_panel():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT channel_id, message_id, title, description, color
        FROM othello_panel
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    r = cur.fetchone()
    conn.close()
    if r:
        return {
            "channel_id": int(r[0]),
            "message_id": int(r[1]),
            "title": r[2],
            "description": r[3],
            "color": int(r[4])
        }
    return None
# ===========================================

class OthelloPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(label="🎮 対戦開始", style=discord.ButtonStyle.primary, custom_id="othello_panel:challenge")
    async def challenge_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if itx.user.id in active_games:
            await itx.response.send_message("❌ あなたは既に対戦中です", ephemeral=True)
            return

        selected_opponent = None
        selection_done = asyncio.Event()
        is_invalid = False  # ✅ 不適切な場合のフラグ追加

        class OpponentSelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(
                    discord.ui.UserSelect(
                        placeholder="対戦相手を選んでください",
                        min_values=1,
                        max_values=1
                    )
                )

            async def interaction_check(self, inter: discord.Interaction) -> bool:
                nonlocal selected_opponent, is_invalid
                selected_opponent = self.children[0].values[0]

                # ✅ 自分自身を選択
                if selected_opponent == inter.user:
                    await inter.response.send_message(
                        "❌ 自分自身とは対戦できません", ephemeral=True
                    )
                    is_invalid = True
                    selection_done.set()
                    return False

                # ✅ Botを選択
                if selected_opponent.bot:
                    await inter.response.send_message(
                        "❌ Botとは対戦できません", ephemeral=True
                    )
                    is_invalid = True
                    selection_done.set()
                    return False

                # ✅ 既に対戦中
                if selected_opponent.id in active_games:
                    await inter.response.send_message(
                        f"❌ {selected_opponent.mention} は既に対戦中です", ephemeral=True
                    )
                    is_invalid = True
                    selection_done.set()
                    return False

                # ✅ 正常な場合
                await inter.response.send_message(
                    f"✅ {selected_opponent.mention} に対戦を申し込みました。チャンネルを作成します…",
                    ephemeral=True
                )
                selection_done.set()
                return False

        select_view = OpponentSelectView()
        await itx.response.send_message(
            "👇 対戦相手を下から選んでください",
            view=select_view,
            ephemeral=True
        )

        try:
            await asyncio.wait_for(selection_done.wait(), timeout=60)
        except asyncio.TimeoutError:
            await itx.followup.send(
                "⏰ 60秒以内に相手が選択されませんでした。もう一度お試しください。",
                ephemeral=True
            )
            return

        # ✅ 無効な相手が選ばれた → ここで処理を完全に停止
        if is_invalid:
            return

        # ========== 以降は正常な場合のみ実行 ==========
        opponent = selected_opponent
        challenger = itx.user
        guild = itx.guild
        category = None
        if OTHELLO_CATEGORY_ID and OTHELLO_CATEGORY_ID != 0:
            category = guild.get_channel(OTHELLO_CATEGORY_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            challenger: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            opponent: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for oid in [1256574550901133377, 1546348374922625065]:
            owner = guild.get_member(oid)
            if owner:
                overwrites[owner] = discord.PermissionOverwrite(view_channel=True)

        channel_name = f"オセロ-{challenger.name}-vs-{opponent.name}"
        try:
            ticket_ch = await guild.create_text_channel(
                name=channel_name,
                topic=f"対戦申込：{challenger.mention} → {opponent.mention}",
                category=category,
                overwrites=overwrites
            )
        except Exception as e:
            await itx.followup.send(f"❌ チャンネル作成エラー：{e}", ephemeral=True)
            return

        await itx.followup.send(
            f"✅ チャンネル作成完了！ → {ticket_ch.mention}",
            ephemeral=True
        )

        class ApproveRejectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.final_decision = None

            @discord.ui.button(label="✅ 承認", style=discord.ButtonStyle.success)
            async def approve_btn(self, btn_itx: discord.Interaction, btn):
                if btn_itx.user.id != opponent.id:
                    await btn_itx.response.send_message("❌ 招待された人だけが押せます", ephemeral=True)
                    return
                self.final_decision = "approve"
                self.stop()

                class StartBoardView(discord.ui.View):
                    def __init__(self):
                        super().__init__(timeout=None)
                    @discord.ui.button(label="🎮 盤面表示", style=discord.ButtonStyle.primary)
                    async def show_board_btn(self, board_itx: discord.Interaction, btn):
                        await board_itx.response.defer()
                        active_games.add(challenger.id)
                        active_games.add(opponent.id)
                        game = type('Game', (), {'board': OthelloBoard()})()
                        game_view = OthelloView(
                            game=game,
                            player_black=challenger,
                            player_white=opponent,
                            result_channel_id=RESULT_CHANNEL_ID,
                            ticket_channel=ticket_ch
                        )
                        async def cleanup_and_close():
                            active_games.discard(challenger.id)
                            active_games.discard(opponent.id)
                            await ticket_ch.send("✅ 対戦終了！5秒後にこのチャンネルを削除します")
                            await asyncio.sleep(5)
                            try:
                                await ticket_ch.delete()
                            except:
                                pass
                        game_view.cleanup_callback = cleanup_and_close
                        embed = await game_view.build_embed()
                        game_view.main_message = await ticket_ch.send(
                            embed=embed,
                            view=game_view
                        )

                await btn_itx.response.send_message(
                    "✅ 承認されました。⬇️の盤面表示ボタンを押して開始しましょう",
                    view=StartBoardView(),
                    ephemeral=False
                )

            @discord.ui.button(label="❌ 拒否", style=discord.ButtonStyle.danger)
            async def reject_btn(self, btn_itx: discord.Interaction, btn):
                if btn_itx.user.id != opponent.id:
                    await btn_itx.response.send_message("❌ 招待された人だけが押せます", ephemeral=True)
                    return
                self.final_decision = "reject"
                self.stop()
                await btn_itx.response.send_message("❌ 拒否されたのでチケット削除します", ephemeral=False)
                await ticket_ch.send("5秒後にこのチャンネルを削除します")
                await asyncio.sleep(5)
                await ticket_ch.delete()

        ar_view = ApproveRejectView()
        await ticket_ch.send(
            f"{opponent.mention}\n{challenger.mention} がオセロの対戦を申し込んでいます！\n⏰ 2分以内に「✅ 承認」または「❌ 拒否」を押してください。",
            view=ar_view
        )
        await ar_view.wait()

        if ar_view.final_decision is None:
            await ticket_ch.send("⏰ 応答がないため、このチャンネルを削除します")
            await asyncio.sleep(3)
            await ticket_ch.delete()
            return

    @discord.ui.button(label="✏️ パネル編集", style=discord.ButtonStyle.secondary, custom_id="othello_panel:edit")
    async def edit_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_othello_panel()
        default_title = latest["title"] if latest else "🎮 オセロで対戦しよう！"
        default_desc = latest["description"] if latest else (
            "下のボタンを押して対戦相手を選んでください。\n"
            "承諾されると専用チャンネルが自動作成されます。"
        )
        class EditModal(discord.ui.Modal, title="パネル編集"):
            title_in = discord.ui.TextInput(label="タイトル", default=default_title)
            desc_in = discord.ui.TextInput(
                label="説明文", style=discord.TextStyle.long,
                default=default_desc
            )
            async def on_submit(self, modal_itx: discord.Interaction):
                embed = discord.Embed(
                    title=str(self.title_in),
                    description=str(self.desc_in),
                    color=0x222222
                )
                await modal_itx.response.edit_message(embed=embed, view=OthelloPanelView())
                save_othello_panel(
                    modal_itx.channel_id,
                    modal_itx.message.id,
                    str(self.title_in),
                    str(self.desc_in),
                    0x222222
                )
                await modal_itx.followup.send("✅ 更新・保存完了", ephemeral=True)
        await itx.response.send_modal(EditModal())

    @discord.ui.button(label="🔄 パネル更新", style=discord.ButtonStyle.secondary, custom_id="othello_panel:refresh")
    async def refresh_panel(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        latest = get_latest_othello_panel()
        if not latest:
            await itx.response.send_message("⚠️ 保存されたパネルが見つかりません", ephemeral=True)
            return
        embed = discord.Embed(
            title=latest["title"],
            description=latest["description"],
            color=latest["color"]
        )
        await itx.response.edit_message(embed=embed)
        await itx.followup.send("✅ パネルを最新に更新しました", ephemeral=True)

async def setup(tree, bot=None):
    if bot is not None and not hasattr(bot, "_othello_panel_registered"):
        bot.add_view(OthelloPanelView())
        bot._othello_panel_registered = True
        print("✅ othello_panel 永続View登録完了")

    @tree.command(name="オセロパネル設置", description="オセロ対戦パネルを設置（オーナー専用）")
    async def cmd_othello_panel(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="🔳 オセロで対戦しよう！",
            description="⬇️のボタンを押して対戦相手を選んでください。\n承諾されると専用チャンネルが自動作成されます。",
            color=0x222222
        )
        await itx.response.send_message(embed=embed, view=OthelloPanelView())
        msg = await itx.original_response()
        save_othello_panel(
            itx.channel_id,
            msg.id,
            embed.title,
            embed.description,
            embed.color.value
        )
