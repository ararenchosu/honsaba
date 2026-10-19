import discord
from discord import app_commands
import random
import re
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
HISTORY_FILE = "mines_history.json"
MINES_CATEGORY_ID = 1558467161146663023

UNIT_SCALE = {
    "無量大数": 10**68, "那由多": 10**64, "不可思議": 10**60,
    "阿僧祇": 10**56, "恒河沙": 10**52, "極": 10**48,
    "載": 10**44, "正": 10**40, "澗": 10**36, "溝": 10**32,
    "穣": 10**28, "垓": 10**24, "京": 10**20, "兆": 10**16,
    "億": 10**12, "万": 10**8,
}

def parse_value(input_str: str, balance=0):
    s = input_str.strip()
    if s in ["オールベット", "全額", "allbet", "AllBet"]:
        return balance
    match = re.match(r"([0-9]*\.?[0-9]+)\s*([^\d\s]*)", s)
    if not match:
        try:
            return float(s)
        except ValueError:
            return None
    num_str = match.group(1)
    unit = match.group(2)
    try:
        num = float(num_str)
    except ValueError:
        return None
    if unit in UNIT_SCALE:
        return num * UNIT_SCALE[unit]
    return num

def format_value(val):
    val = float(val)
    for name, scale in reversed(list(UNIT_SCALE.items())):
        if val >= scale:
            return f"{val / scale:.2f} {name}"
    return f"{int(val):,}"

def format_mul(val):
    val = float(val)
    for name, scale in reversed(list(UNIT_SCALE.items())):
        if val >= scale:
            return f"{val / scale:.2f} {name}倍"
    return f"{val:.1f}倍"

def load_points_all():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "points" not in data:
                data["points"] = {}
            return data
    except Exception:
        return {"points": {}}

def get_point_value(user_id):
    return load_points_all()["points"].get(str(user_id), 0)

def add_point_value(user_id, amount):
    data = load_points_all()
    uid = str(user_id)
    data["points"][uid] = data["points"].get(uid, 0) + amount
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data["points"][uid]

def save_history_entry(entry):
    all_data = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            pass
    all_data.insert(0, entry)
    all_data = all_data[:200]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

FINAL_MULTIPLIER = {
     1: 250_000.0, 2: 400_000.0, 3: 650_000.0, 4: 1_000_000.0, 5: 1_600_000.0,
     6: 2_600_000.0, 7: 4_200_000.0, 8: 6_800_000.0, 9: 11_000_000.0, 10: 18_000_000.0,
    11: 30_000_000.0, 12: 50_000_000.0, 13: 85_000_000.0, 14: 150_000_000.0, 15: 270_000_000.0,
    16: 500_000_000.0, 17: 1_000_000_000.0, 18: 2_500_000_000.0, 19: 6_000_000_000.0, 20: 20_000_000_000.0,
    21: 80_000_000_000.0, 22: 350_000_000_000.0, 23: 2_000_000_000_000.0, 24: 50_000_000_000_000.0,
}

def calc_step_multiplier(bombs: int, opened: int):
    safe = 25 - bombs
    if opened >= safe:
        return FINAL_MULTIPLIER[bombs]
    ratio = opened / safe
    return round(1.0 + (FINAL_MULTIPLIER[bombs] - 1.0) * ratio ** 2.2, 2)

active_games = {}

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
        self.board_msg = None
        self.control_msg = None
        for p in random.sample(range(25), bombs):
            self.grid[p] = True

    def board_text(self):
        lines = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                if self.opened[idx]:
                    row.append("💣" if self.grid[idx] else "💎")
                else:
                    row.append("□")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def reveal_all_text(self):
        lines = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                row.append("💣" if self.grid[idx] else "💎")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def playing_embed(self):
        return discord.Embed(title="💎 マインス 💣", color=0xFFD700
        ).add_field(name="🔹 プレイヤー", value=self.user.mention, inline=True
        ).add_field(name="🔹 爆弾数", value=f"{self.bombs}個", inline=True
        ).add_field(name="🔹 賭け額", value=format_value(self.bet), inline=True
        ).add_field(name="🔥 現在倍率", value=f"**{format_mul(self.multiplier)}**", inline=True
        ).add_field(name="🎯 盤面", value=self.board_text(), inline=False)

    def result_embed(self, title, desc, color):
        return discord.Embed(title=title, description=desc, color=color
        ).add_field(name="🎯 全盤面", value=self.reveal_all_text(), inline=False)

# ==============================================
# ✅ メインパネル（永続）
# ==============================================
class MinesCreatePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎮 マインズを始める", style=discord.ButtonStyle.primary, custom_id="mines_create_btn_v2")
    async def create_btn(self, inter: discord.Interaction, btn):
        await inter.response.defer(ephemeral=True)
        try:
            guild = inter.guild
            category = guild.get_channel(MINES_CATEGORY_ID)
            if not category:
                raise ValueError(f"カテゴリが見つかりません: {MINES_CATEGORY_ID}")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                inter.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True),
            }
            for m in guild.members:
                if m.guild_permissions.administrator:
                    overwrites[m] = discord.PermissionOverwrite(read_messages=True)
            channel = await guild.create_text_channel(
                name=f"マインズ-{inter.user.name}", category=category,
                overwrites=overwrites, reason="マインズゲーム用"
            )
        except Exception as e:
            await inter.followup.send(f"❌ チャンネル作成失敗: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title="💎 難易度を選択",
            description=(
                "下のボタンから選んでください！\n"
                "✅ かんたん [3個] ｜ ⚪ ふつう [5個] ｜ 🔴 むずかしい [8個] ｜ ⚙️ 自分で設定"
            ),
            color=0x2ECC71
        )
        await channel.send(embed=embed, view=MinesSelectView())
        await inter.followup.send(
            f"✅ 作成完了！→ {channel.mention}\nそちらで難易度を選んでください",
            ephemeral=True
        )

# ==============================================
# ✅ 難易度選択パネル（永続：custom_id全部新しい！）
# ==============================================
class MinesSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def start_bet_modal(self, inter, bombs):
        bal = get_point_value(inter.user.id)
        max_mul = format_mul(FINAL_MULTIPLIER[bombs])
        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個"):
            bet_in = discord.ui.TextInput(
                label=f"最大倍率:{max_mul} 保有:{format_value(bal)}",
                placeholder="例：100万 / オールベット", required=True
            )
            async def on_submit(s, m):
                bet = parse_value(s.bet_in.value.strip(), bal)
                if not bet or bet <= 0 or bet > bal:
                    await m.response.send_message("❌ 賭け額が不正です", ephemeral=True)
                    return
                await start_game(m, bombs, bet)
        await inter.response.send_modal(BetModal())

    @discord.ui.button(label="✅ かんたん [3個]", style=discord.ButtonStyle.secondary, custom_id="mines_diff_easy_v2")
    async def easy(self, inter, btn):
        await self.start_bet_modal(inter, 3)

    @discord.ui.button(label="⚪ ふつう [5個]", style=discord.ButtonStyle.blurple, custom_id="mines_diff_normal_v2")
    async def normal(self, inter, btn):
        await self.start_bet_modal(inter, 5)

    @discord.ui.button(label="🔴 むずかしい [8個]", style=discord.ButtonStyle.danger, custom_id="mines_diff_hard_v2")
    async def hard(self, inter, btn):
        await self.start_bet_modal(inter, 8)

    @discord.ui.button(label="⚙️ 自分で設定", style=discord.ButtonStyle.green, custom_id="mines_diff_custom_v2")
    async def custom(self, inter, btn):
        bal = get_point_value(inter.user.id)
        class CustomModal(discord.ui.Modal, title="💎 自分で設定"):
            bombs_in = discord.ui.TextInput(label="爆弾の数 (1～24)", placeholder="例：10", required=True)
            bet_in = discord.ui.TextInput(
                label=f"賭け額 保有:{format_value(bal)}",
                placeholder="例：500万 / オールベット", required=True
            )
            async def on_submit(s, m):
                try:
                    bombs = int(s.bombs_in.value.strip())
                    bet = parse_value(s.bet_in.value.strip(), bal)
                    if not (1 <= bombs <= 24):
                        raise ValueError()
                    if not bet or bet <= 0 or bet > bal:
                        raise ValueError()
                except:
                    await m.response.send_message("❌ 入力が正しくありません", ephemeral=True)
                    return
                await start_game(m, bombs, bet)
        await inter.response.send_modal(CustomModal())

# ==============================================
# ✅ ゲーム開始
# ==============================================
async def start_game(inter, bombs, bet):
    try:
        await inter.message.delete()
    except:
        pass

    game = MinesGame(inter.user, bombs, bet)
    active_games[inter.user.id] = game

    board_view = MinesBoardView(game)
    board_msg = await inter.channel.send(embed=game.playing_embed(), view=board_view)
    game.board_msg = board_msg

    control_view = MinesControlView(game)
    control_msg = await inter.channel.send("👇 操作ボタン", view=control_view)
    game.control_msg = control_msg

    await inter.response.send_message("✅ ゲーム開始！", ephemeral=True)

# ==============================================
# ✅ 盤面ボタン
# ==============================================
class MinesBoardView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game
        self._build()

    def _build(self):
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
                disabled = g.game_over
            btn = discord.ui.Button(label=lbl, style=style, disabled=disabled, row=idx // 5, custom_id=f"mines_cell_{g.user_id}_{idx}_v2")
            btn.callback = lambda i, idx=idx: self.on_click(i, idx)
            self.add_item(btn)

    async def interaction_check(self, inter):
        if inter.user.id != self.game.user_id:
            await inter.response.send_message("❌ 自分のゲームだけ操作できます", ephemeral=True)
            return False
        if self.game.game_over:
            await inter.response.send_message("❌ ゲームは終了しています", ephemeral=True)
            return False
        return True

    async def on_click(self, inter, idx):
        g = self.game
        if g.opened[idx]:
            return await inter.response.defer()
        g.opened[idx] = True

        if g.grid[idx]:
            g.game_over = True
            add_point_value(g.user_id, -g.bet)
            active_games.pop(g.user_id, None)
            save_history_entry({
                "user_id": g.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet, "result": "lose", "amount": -g.bet,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("💣 爆弾！",
                f"🔹 賭け：{format_value(g.bet)}\n🔹 結果：-{format_value(g.bet)}", 0xE74C3C)
            await inter.response.edit_message(embed=embed, view=MinesResultView(g))
            try:
                await g.control_msg.delete()
            except:
                pass
            return

        g.opened_count += 1
        g.multiplier = calc_step_multiplier(g.bombs, g.opened_count)

        if g.opened_count >= (25 - g.bombs):
            g.game_over = True
            win = int(g.bet * g.multiplier)
            add_point_value(g.user_id, win)
            active_games.pop(g.user_id, None)
            save_history_entry({
                "user_id": g.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet, "result": "win", "amount": win,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("🎉 全開け！",
                f"🔹 賭け：{format_value(g.bet)}\n🔹 倍率：{format_mul(g.multiplier)}\n🔹 獲得：+{format_value(win)}", 0xFFD700)
            await inter.response.edit_message(embed=embed, view=MinesResultView(g))
            try:
                await g.control_msg.delete()
            except:
                pass
            return

        await inter.response.edit_message(embed=g.playing_embed(), view=self)

# ==============================================
# ✅ 制御ボタン
# ==============================================
class MinesControlView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game
        self._build()

    def _build(self):
        self.clear_items()
        can_end = self.game.opened_count > 0
        self.add_item(discord.ui.Button(
            label="💰 この倍率で終了", style=discord.ButtonStyle.primary,
            disabled=not can_end, custom_id=f"mines_end_btn_{self.game.user_id}_v2"
        ))

    async def interaction_check(self, inter):
        if inter.user.id != self.game.user_id:
            await inter.response.send_message("❌ 自分のゲームだけ操作できます", ephemeral=True)
            return False
        if self.game.game_over:
            await inter.response.send_message("❌ ゲームは終了しています", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="💰 この倍率で終了", style=discord.ButtonStyle.primary, custom_id="mines_end_btn_v2")
    async def end_btn(self, inter, btn):
        if self.game.opened_count == 0:
            await inter.response.send_message("❌ 1マス以上開けてから終了してください", ephemeral=True)
            return
        self.game.game_over = True
        win = int(self.game.bet * self.game.multiplier)
        add_point_value(self.game.user_id, win)
        active_games.pop(self.game.user_id, None)
        save_history_entry({
            "user_id": self.game.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            "bombs": self.game.bombs, "bet": self.game.bet, "result": "cashout", "amount": win,
            "multiplier": format_mul(self.game.multiplier)
        })
        embed = self.game.result_embed("💰 回収完了！",
            f"🔹 賭け：{format_value(self.game.bet)}\n🔹 倍率：{format_mul(self.game.multiplier)}\n🔹 獲得：+{format_value(win)}", 0x2ECC71)
        await inter.response.edit_message(embed=embed, view=MinesResultView(self.game))
        try:
            await self.game.control_msg.delete()
        except:
            pass
        await inter.response.send_message("✅ 終了しました", ephemeral=True)

# ==============================================
# ✅ 結果画面
# ==============================================
class MinesResultView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.bombs = game.bombs
        self.last_bet = game.bet
        self.user_id = game.user_id

    @discord.ui.button(label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary, custom_id="mines_retry_same_v2")
    async def retry_same(self, inter, btn):
        bal = get_point_value(inter.user.id)
        if self.last_bet > bal:
            await inter.response.send_message(
                f"❌ ポイントが足りません\n賭け：{format_value(self.last_bet)}\n保有：{format_value(bal)}", ephemeral=True)
            return
        try:
            await inter.message.delete()
        except:
            pass
        await start_game(inter, self.bombs, self.last_bet)

    @discord.ui.button(label="💸 賭け金を変えてもう1回", style=discord.ButtonStyle.success, custom_id="mines_retry_new_v2")
    async def retry_new(self, inter, btn):
        bal = get_point_value(inter.user.id)
        class NewBetModal(discord.ui.Modal, title=f"💎 爆弾{self.bombs}個"):
            new_bet = discord.ui.TextInput(
                label=f"保有:{format_value(bal)}",
                placeholder="例：500万 / オールベット", required=True
            )
            async def on_submit(s, m):
                bet = parse_value(s.new_bet.value.strip(), bal)
                if not bet or bet <= 0 or bet > bal:
                    await m.response.send_message("❌ 賭け額が不正です", ephemeral=True)
                    return
                try:
                    await m.message.delete()
                except:
                    pass
                await start_game(m, self.bombs, bet)
        await inter.response.send_modal(NewBetModal())

# ==============================================
# ✅ セットアップ
# ==============================================
async def setup(tree, bot):
    # ✅ 両方を登録
    bot.add_view(MinesCreatePanelView())
    bot.add_view(MinesSelectView())
    print("[MINES] ✅ セットアップ完了")
