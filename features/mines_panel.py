import discord
from discord import app_commands
import random
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
MINES_CATEGORY_ID = 1558467161146663023  # 特定のカテゴリにまとめたい場合はIDを入れる

def load_points_all():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        import json
        return json.load(f)

def save_points_all(data):
    import json
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_point_value(user_id):
    return load_points_all()["points"].get(str(user_id), 0)

def add_point_value(user_id, amount):
    data = load_points_all()
    uid = str(user_id)
    data["points"][uid] = data["points"].get(uid, 0) + amount
    save_points_all(data)
    return data["points"][uid]

FINAL_MULTIPLIER = {
    1: 11.2, 2: 13.0, 3: 15.7, 4: 21.45, 5: 32.9, 6: 45.85, 7: 64.15, 8: 96.3,
    9: 145.5, 10: 201.75, 11: 341.25, 12: 492.3, 13: 852.5, 14: 1520.0,
    15: 2805.0, 16: 5545.0, 17: 11730.0, 18: 26540.0, 19: 66350.0, 20: 182400.0,
    21: 570000.0, 22: 2090000.0, 23: 10150000.0, 24: 126500000.0,
}

def format_mul(val):
    return f"{val:,}倍" if val >= 1000 else f"{val}倍"

def calc_step_multiplier(bombs: int, opened: int):
    safe = 25 - bombs
    if opened >= safe:
        return FINAL_MULTIPLIER[bombs]
    ratio = opened / safe
    return round(1.0 + (FINAL_MULTIPLIER[bombs] - 1.0) * ratio ** 1.5, 2)

game_states = {}
user_state = {}
last_settings = {}
temp_channels = {}

class MinesGame:
    def __init__(self, user: discord.User, bombs: int, bet: int):
        self.user = user
        self.user_id = user.id
        self.bombs = bombs
        self.bet = bet
        self.grid = [False] * 25
        self.opened = [False] * 25
        self.opened_count = 0
        self.multiplier = 1.0
        self.game_over = False
        self.channel = None
        self.message = None
        for p in random.sample(range(25), bombs):
            self.grid[p] = True

    def board_text(self, reveal_all=False):
        lines = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                if reveal_all or self.opened[idx]:
                    row.append("💣" if self.grid[idx] else "💎")
                else:
                    row.append("□")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def playing_embed(self):
        e = discord.Embed(title="💎 マインス 💣", color=0x1a1a1a)
        e.add_field(name="🔹 プレイヤー", value=self.user.mention, inline=True)
        e.add_field(name="🔹 爆弾数", value=f"{self.bombs}個", inline=True)
        e.add_field(name="🔹 賭け額", value=f"{self.bet:,}pt", inline=True)
        e.add_field(name="🔹 現在倍率", value=f"**{self.multiplier}倍**", inline=True)
        e.add_field(name="🎯 盤面", value=self.board_text(), inline=False)
        return e

    def result_embed(self, title, desc, color):
        e = discord.Embed(title=title, description=desc, color=color)
        e.add_field(name="🎯 全盤面", value=self.board_text(reveal_all=True), inline=False)
        return e

async def create_game_channel(guild: discord.Guild, user: discord.User):
    category = guild.get_channel(MINES_CATEGORY_ID) if MINES_CATEGORY_ID else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    for m in guild.members:
        if m.guild_permissions.administrator:
            overwrites[m] = discord.PermissionOverwrite(read_messages=True)
    channel = await guild.create_text_channel(
        name=f"マインズ-{user.name}",
        category=category,
        overwrites=overwrites,
        reason="マインズゲーム用"
    )
    return channel

# ========== ゲーム中View — ここに処理を全部書く ==========
class MinesPlayingView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        g = self.game
        for idx in range(25):
            if g.opened[idx]:
                lbl = "💣" if g.grid[idx] else "💎"
                style = discord.ButtonStyle.danger if g.grid[idx] else discord.ButtonStyle.success
                disabled = True
            else:
                lbl = "□"
                style = discord.ButtonStyle.secondary
                disabled = False
            btn = discord.ui.Button(label=lbl, style=style, disabled=disabled, row=idx//5)
            btn.callback = lambda i, idx=idx: self.on_click(i, idx)
            self.add_item(btn)
        if g.opened_count > 0:
            cash_btn = discord.ui.Button(label="💰 回収", style=discord.ButtonStyle.primary, row=4)
            cash_btn.callback = self.on_cash
            self.add_item(cash_btn)

    async def interaction_check(self, inter):
        return inter.user.id == self.game.user_id

    async def on_click(self, inter, idx):
        g = self.game
        if g.game_over or g.opened[idx]:
            return await inter.response.defer()

        g.opened[idx] = True

        if g.grid[idx]:
            # 爆弾
            g.game_over = True
            add_point_value(g.user_id, -g.bet)
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            embed = g.result_embed(
                "💣 爆弾！",
                f"🔹 賭け：{g.bet:,}pt\n🔹 結果：-{g.bet:,}pt",
                0xE74C3C
            )
            await inter.response.edit_message(embed=embed, view=MinesResultView(g))
        else:
            # 当たり
            g.opened_count += 1
            g.multiplier = calc_step_multiplier(g.bombs, g.opened_count)
            await inter.response.edit_message(embed=g.playing_embed(), view=self)

    async def on_cash(self, inter):
        g = self.game
        if g.game_over:
            return await inter.response.defer()
        g.game_over = True
        win = int(g.bet * g.multiplier)
        add_point_value(g.user_id, win)
        last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
        embed = g.result_embed(
            "💰 回収完了！",
            f"🔹 賭け：{g.bet:,}pt\n🔹 倍率：{g.multiplier}倍\n🔹 獲得：+{win:,}pt",
            0x2ECC71
        )
        await inter.response.edit_message(embed=embed, view=MinesResultView(g))

# ========== 結果View ==========
class MinesResultView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        uid = game.user_id
        if uid in last_settings:
            retry_btn = discord.ui.Button(label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary)
            retry_btn.callback = self.on_retry
            self.add_item(retry_btn)
        close_btn = discord.ui.Button(label="🗑️ チャンネルを閉じる", style=discord.ButtonStyle.danger)
        close_btn.callback = self.on_close
        self.add_item(close_btn)

    async def on_retry(self, inter):
        if inter.user.id != self.game.user_id:
            return await inter.response.defer()
        if self.game.user_id in game_states:
            return await inter.response.send_message("❌ 進行中です", ephemeral=True)
        setting = last_settings.get(self.game.user_id)
        if not setting:
            return await inter.response.send_message("❌ 設定なし", ephemeral=True)
        bal = get_point_value(self.game.user_id)
        if setting["bet"] > bal:
            return await inter.response.send_message(f"❌ ポイント不足", ephemeral=True)
        
        channel = await create_game_channel(inter.guild, inter.user)
        new_game = MinesGame(inter.user, setting["bombs"], setting["bet"])
        new_game.channel = channel
        game_states[self.game.user_id] = new_game
        temp_channels[self.game.user_id] = channel
        
        view = MinesPlayingView(new_game)
        msg = await channel.send(embed=new_game.playing_embed(), view=view)
        new_game.message = msg
        await inter.response.send_message(f"✅ 新規チャンネル → {channel.mention}", ephemeral=True)

    async def on_close(self, inter):
        if inter.user.id != self.game.user_id and not inter.user.guild_permissions.administrator:
            return await inter.response.defer()
        c = temp_channels.pop(self.game.user_id, None)
        if c:
            await c.delete(reason="終了")
        await inter.response.send_message("✅ 閉じました", ephemeral=True)

# ========== スタート用パネル ==========
class MinesStartPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ かんたん [3個]", style=discord.ButtonStyle.success, row=0, custom_id="mine:panel_easy")
    async def easy(self, inter, btn):
        await self._start_fixed(inter, 3)

    @discord.ui.button(label="⚪ ふつう [5個]", style=discord.ButtonStyle.secondary, row=0, custom_id="mine:panel_normal")
    async def normal(self, inter, btn):
        await self._start_fixed(inter, 5)

    @discord.ui.button(label="🔴 むずかしい [8個]", style=discord.ButtonStyle.danger, row=1, custom_id="mine:panel_hard")
    async def hard(self, inter, btn):
        await self._start_fixed(inter, 8)

    async def _start_fixed(self, inter, bombs):
        if inter.user.id in game_states:
            return await inter.response.send_message("❌ 進行中です！", ephemeral=True)
        mul = format_mul(FINAL_MULTIPLIER[bombs])
        bal = get_point_value(inter.user.id)
        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個"):
            bet_in = discord.ui.TextInput(label=f"倍率：{mul}\n賭けるポイント", required=True)
            async def on_submit(s, m):
                try:
                    val = int(s.bet_in.value.strip())
                except:
                    return await m.response.send_message("❌ 数字を入力", ephemeral=True)
                if val <= 0 or val > bal:
                    return await m.response.send_message(f"❌ ポイント不足\n保有：{bal:,}pt", ephemeral=True)
                await start_game(m.user, m.guild, bombs, val)
                await m.response.send_message("✅ ゲームチャンネルを作成しました！", ephemeral=True)
        await inter.response.send_modal(BetModal())

async def start_game(user, guild, bombs, bet):
    channel = await create_game_channel(guild, user)
    game = MinesGame(user, bombs, bet)
    game.channel = channel
    game_states[user.id] = game
    temp_channels[user.id] = channel
    view = MinesPlayingView(game)
    msg = await channel.send(embed=game.playing_embed(), view=view)
    game.message = msg

async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is None:
        return
    if not hasattr(bot, "_mines_views_done"):
        bot.add_view(MinesStartPanelView())
        bot._mines_views_done = True
        print("✅ mines_panel 登録完了")
