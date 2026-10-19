import discord
from discord import app_commands
import random
import os
import re
import json
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
HISTORY_FILE = "mines_history.json"
MINES_CATEGORY_ID = 1558467161146663023
OWNER_ROLE_NAME = "鯖主"

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
    units = [
        ("無量大数", 10**68), ("那由多", 10**64), ("不可思議", 10**60),
        ("阿僧祇", 10**56), ("恒河沙", 10**52), ("極", 10**48),
        ("載", 10**44), ("正", 10**40), ("澗", 10**36), ("溝", 10**32),
        ("穣", 10**28), ("垓", 10**24), ("京", 10**20), ("兆", 10**16),
        ("億", 10**12), ("万", 10**8),
    ]
    for name, scale in units:
        if val >= scale:
            return f"{val / scale:.2f} {name}"
    return f"{int(val):,}"

def format_mul(val):
    val = float(val)
    for name, scale in UNIT_SCALE.items():
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

def load_history(user_id=None):
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            all_data = json.load(f)
            if user_id:
                return [h for h in all_data if h.get("user_id") == user_id]
            return all_data
    except Exception:
        return []

def save_history_entry(entry):
    all_data = load_history()
    all_data.insert(0, entry)
    all_data = all_data[:200]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

def clear_user_state(uid):
    game_states.pop(uid, None)
    last_settings.pop(uid, None)
    channel_map.pop(uid, None)
    message_map.pop(uid, None)
    control_message_map.pop(uid, None)

# ==================================================
# ✅ 全倍率 10,000倍UP（50万→50億）
# ==================================================
FINAL_MULTIPLIER = {
     1: 250_000.0,
     2: 400_000.0,
     3: 650_000.0,
     4: 1_000_000.0,
     5: 1_600_000.0,
     6: 2_600_000.0,
     7: 4_200_000.0,
     8: 6_800_000.0,
     9: 11_000_000.0,
    10: 18_000_000.0,
    11: 30_000_000.0,
    12: 50_000_000.0,
    13: 85_000_000.0,
    14: 150_000_000.0,
    15: 270_000_000.0,
    16: 500_000_000.0,
    17: 1_000_000_000.0,
    18: 2_500_000_000.0,
    19: 6_000_000_000.0,
    20: 20_000_000_000.0,
    21: 80_000_000_000.0,
    22: 350_000_000_000.0,
    23: 2_000_000_000_000.0,
    24: 50_000_000_000_000.0,
}

def calc_step_multiplier(bombs: int, opened: int):
    safe = 25 - bombs
    if opened >= safe:
        return FINAL_MULTIPLIER[bombs]
    ratio = opened / safe
    return round(1.0 + (FINAL_MULTIPLIER[bombs] - 1.0) * ratio ** 2.2, 2)

game_states = {}
last_settings = {}
channel_map = {}
message_map = {}
control_message_map = {}

# ==================================================
# ✅ ゲーム本体クラス
# ==================================================
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
        self.control_message = None
        for p in random.sample(range(25), bombs):
            self.grid[p] = True

    def has_owner_role(self, user: discord.User):
        if not self.channel or not hasattr(self.channel, 'guild'):
            return False
        member = self.channel.guild.get_member(user.id)
        if not member:
            return False
        return any(role.name == OWNER_ROLE_NAME for role in member.roles)

    def board_text(self, reveal_all=False):
        lines = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                if self.opened[idx]:
                    row.append("💣" if self.grid[idx] else "💎")
                elif reveal_all or self.has_owner_role(self.user):
                    row.append("💣" if self.grid[idx] else "💎")
                else:
                    row.append("□")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def playing_embed(self):
        e = discord.Embed(title="💎 マインス 💣", color=0xFFD700)
        e.add_field(name="🔹 プレイヤー", value=self.user.mention, inline=True)
        e.add_field(name="🔹 爆弾数", value=f"{self.bombs}個", inline=True)
        e.add_field(name="🔹 賭け額", value=format_value(self.bet), inline=True)
        e.add_field(name="🔥 現在倍率", value=f"**{format_mul(self.multiplier)}**", inline=True)
        e.add_field(name="🎯 盤面", value=self.board_text(), inline=False)
        return e

    def result_embed(self, title, desc, color):
        e = discord.Embed(title=title, description=desc, color=color)
        e.add_field(name="🎯 全盤面", value=self.board_text(reveal_all=True), inline=False)
        return e

# ==================================================
# ✅ チャンネル作成用 最初のパネル
# ==================================================
class MinesStartPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_game_channel(self, guild: discord.Guild, user: discord.User):
        category = guild.get_channel(MINES_CATEGORY_ID)
        if not category:
            raise ValueError(f"カテゴリが見つかりません: {MINES_CATEGORY_ID}")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        for m in guild.members:
            if m.guild_permissions.administrator:
                overwrites[m] = discord.PermissionOverwrite(read_messages=True)
        channel = await guild.create_text_channel(
            name=f"マインズ-{user.name}", category=category,
            overwrites=overwrites, reason="マインズゲーム用"
        )
        channel_map[user.id] = channel
        return channel

    @discord.ui.button(label="✅ かんたんを始める [爆弾3個]", style=discord.ButtonStyle.grey, row=0, custom_id="mines_start_easy")
    async def easy_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        await self.start_game_flow(inter, bombs=3)

    @discord.ui.button(label="⚪ ふつうを始める [爆弾5個]", style=discord.ButtonStyle.blurple, row=0, custom_id="mines_start_normal")
    async def normal_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        await self.start_game_flow(inter, bombs=5)

    @discord.ui.button(label="🔴 むずかしいを始める [爆弾8個]", style=discord.ButtonStyle.red, row=0, custom_id="mines_start_hard")
    async def hard_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        await self.start_game_flow(inter, bombs=8)

    @discord.ui.button(label="⚙️ 自分で設定して始める", style=discord.ButtonStyle.green, row=1, custom_id="mines_start_custom")
    async def custom_btn(self, inter: discord.Interaction, btn: discord.ui.Button):
        uid = inter.user.id
        bal = get_point_value(uid)

        class CustomModal(discord.ui.Modal, title="💎 自分で設定"):
            bombs_in = discord.ui.TextInput(label="爆弾の数 (1～24)", placeholder="例：10", required=True)
            bet_in = discord.ui.TextInput(
                label=f"賭け額 保有:{format_value(bal)}｜｢オールベット｣で全額",
                placeholder="例：100万 / オールベット", required=True
            )
            async def on_submit(s, m):
                try:
                    bombs = int(s.bombs_in.value.strip())
                    bet = parse_value(s.bet_in.value.strip(), bal)
                    if not (1 <= bombs <= 24):
                        raise ValueError("爆弾は1～24")
                    if bet is None or bet <= 0 or bet > bal:
                        raise ValueError("賭け額が不正")
                except Exception as e:
                    await m.response.send_message(f"❌ {e}", ephemeral=True)
                    return
                await self.launch_game(m, bombs, bet)

        await inter.response.send_modal(CustomModal())

    async def start_game_flow(self, inter, bombs):
        uid = inter.user.id
        bal = get_point_value(uid)
        mul = format_mul(FINAL_MULTIPLIER[bombs])

        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個 ゲーム開始"):
            bet_in = discord.ui.TextInput(
                label=f"最大倍率:{mul} 保有:{format_value(bal)}｜｢オールベット｣で全額",
                placeholder="例：100万 / オールベット", required=True
            )
            async def on_submit(s, m):
                bet = parse_value(s.bet_in.value.strip(), bal)
                if bet is None or bet <= 0 or bet > bal:
                    await m.response.send_message("❌ 賭け額が不正です", ephemeral=True)
                    return
                await self.launch_game(m, bombs, bet)

        await inter.response.send_modal(BetModal())

    async def launch_game(self, inter, bombs, bet):
        uid = inter.user.id
        clear_user_state(uid)
        try:
            channel = await self.create_game_channel(inter.guild, inter.user)
        except Exception as e:
            await inter.response.send_message(f"❌ チャンネル作成失敗: {e}", ephemeral=True)
            return

        game = MinesGame(inter.user, bombs, bet)
        game.channel = channel
        game_states[uid] = game

        board_view = MinesBoardView(game)
        control_view = MinesControlView(game)

        try:
            board_msg = await channel.send(embed=game.playing_embed(), view=board_view)
            game.message = board_msg
            message_map[uid] = board_msg
            control_msg = await channel.send("👇 操作ボタン", view=control_view)
            game.control_message = control_msg
            control_message_map[uid] = control_msg
            await inter.response.send_message(f"✅ チャンネル作成 → ゲーム開始！\n{channel.mention}", ephemeral=True)
        except Exception as e:
            clear_user_state(uid)
            await inter.response.send_message(f"❌ 送信失敗: {e}", ephemeral=True)

# ==================================================
# ✅ ゲーム盤面ボタン
# ==================================================
class MinesBoardView(discord.ui.View):
    def __init__(self, game: MinesGame):
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
                disabled = False
            btn = discord.ui.Button(label=lbl, style=style, disabled=disabled, row=idx // 5)
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
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            clear_user_state(g.user_id)
            save_history_entry({
                "user_id": g.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet, "result": "lose", "amount": -g.bet,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("💣 爆弾！", f"🔹 賭け：{format_value(g.bet)}\n🔹 結果：-{format_value(g.bet)}", 0xE74C3C)
            try:
                await inter.response.edit_message(embed=embed, view=MinesResultView(g))
                if g.control_message:
                    await g.control_message.delete()
            except Exception:
                pass
            return

        g.opened_count += 1
        g.multiplier = calc_step_multiplier(g.bombs, g.opened_count)

        if g.opened_count >= (25 - g.bombs):
            g.game_over = True
            win = int(g.bet * g.multiplier)
            add_point_value(g.user_id, win)
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            clear_user_state(g.user_id)
            save_history_entry({
                "user_id": g.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet, "result": "win", "amount": win,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("🎉 全開け！",
                f"🔹 賭け：{format_value(g.bet)}\n🔹 確定倍率：{format_mul(g.multiplier)}\n🔹 獲得：+{format_value(win)}", 0xFFD700)
            try:
                await inter.response.edit_message(embed=embed, view=MinesResultView(g))
                if g.control_message:
                    await g.control_message.delete()
            except Exception:
                pass
            return

        await inter.response.edit_message(embed=g.playing_embed(), view=self)

# ==================================================
# ✅ 途中終了ボタン
# ==================================================
class MinesControlView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        self._build()

    def _build(self):
        self.clear_items()
        can_end = self.game.opened_count > 0
        end_btn = discord.ui.Button(
            label="💰 この倍率で終了", style=discord.ButtonStyle.primary,
            disabled=not can_end, custom_id=f"mines_end_{self.game.user_id}"
        )
        end_btn.callback = self.end_btn
        self.add_item(end_btn)

    async def interaction_check(self, inter):
        if inter.user.id != self.game.user_id:
            await inter.response.send_message("❌ 自分のゲームだけ操作できます", ephemeral=True)
            return False
        if self.game.game_over:
            await inter.response.send_message("❌ ゲームは終了しています", ephemeral=True)
            return False
        return True

    async def end_btn(self, inter, btn):
        if self.game.opened_count == 0:
            await inter.response.send_message("❌ 1マス以上開けてから終了してください", ephemeral=True)
            return
        self.game.game_over = True
        win = int(self.game.bet * self.game.multiplier)
        add_point_value(self.game.user_id, win)
        last_settings[self.game.user_id] = {"bombs": self.game.bombs, "bet": self.game.bet}
        clear_user_state(self.game.user_id)
        save_history_entry({
            "user_id": self.game.user_id, "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            "bombs": self.game.bombs, "bet": self.game.bet, "result": "cashout", "amount": win,
            "multiplier": format_mul(self.game.multiplier)
        })
        embed = self.game.result_embed("💰 回収完了！",
            f"🔹 賭け：{format_value(self.game.bet)}\n🔹 確定倍率：{format_mul(self.game.multiplier)}\n🔹 獲得：+{format_value(win)}", 0x2ECC71)
        try:
            await inter.response.edit_message(embed=embed, view=MinesResultView(self.game))
            if self.game.control_message:
                await self.game.control_message.delete()
            await inter.response.send_message("✅ 終了しました", ephemeral=True)
        except Exception:
            pass

# ==================================================
# ✅ 結果画面ボタン（3つに増やす）
# ==================================================
class MinesResultView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        
        # 1行目：同じ設定 / 賭け金変更
        if game.user_id in last_settings:
            self.add_item(discord.ui.Button(
                label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary, row=0,
                custom_id=f"mines_retry_same_{game.user_id}"
            ))
        self.add_item(discord.ui.Button(
            label="💸 賭け金を変えてもう1回", style=discord.ButtonStyle.success, row=0,
            custom_id=f"mines_retry_new_{game.user_id}"
        ))
        
        # 2行目：チャンネルを閉じる
        self.add_item(discord.ui.Button(
            label="🗑️ チャンネルを閉じる", style=discord.ButtonStyle.danger, row=1,
            custom_id=f"mines_close_{game.user_id}"
        ))

    @discord.ui.button(label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary)
    async def retry_same_btn(self, inter, btn):
        uid = inter.user.id
        setting = last_settings.get(uid)
        if not setting:
            await inter.response.send_message("❌ 設定が見つかりません", ephemeral=True)
            return
        bal = get_point_value(uid)
        if setting["bet"] > bal:
            await inter.response.send_message(
                f"❌ ポイントが足りません\n賭け額：{format_value(setting['bet'])}\n保有：{format_value(bal)}", ephemeral=True)
            return
        clear_user_state(uid)
        start_panel = MinesStartPanel()
        await start_panel.launch_game(inter, setting["bombs"], setting["bet"])

    @discord.ui.button(label="💸 賭け金を変えてもう1回", style=discord.ButtonStyle.success)
    async def retry_new_btn(self, inter, btn):
        uid = inter.user.id
        setting = last_settings.get(uid)
        if not setting:
            await inter.response.send_message("❌ 設定が見つかりません", ephemeral=True)
            return
        bal = get_point_value(uid)
        bombs = setting["bombs"]
        mul = format_mul(FINAL_MULTIPLIER[bombs])

        class NewBetModal(discord.ui.Modal, title=f"💸 賭け金変更 (爆弾{bombs}個)"):
            new_bet_in = discord.ui.TextInput(
                label=f"新しい賭け額 保有:{format_value(bal)}｜｢オールベット｣で全額",
                placeholder="例：500万 / オールベット", required=True
            )
            async def on_submit(s, m):
                new_bet = parse_value(s.new_bet_in.value.strip(), bal)
                if new_bet is None or new_bet <= 0 or new_bet > bal:
                    await m.response.send_message("❌ 賭け額が不正です", ephemeral=True)
                    return
                clear_user_state(uid)
                start_panel = MinesStartPanel()
                await start_panel.launch_game(m, bombs, new_bet)

        await inter.response.send_modal(NewBetModal())

    @discord.ui.button(label="🗑️ チャンネルを閉じる", style=discord.ButtonStyle.danger)
    async def close_btn(self, inter, btn):
        uid = inter.user.id
        ch = channel_map.get(uid)
        clear_user_state(uid)
        try:
            if ch:
                await ch.delete(reason="ゲーム終了")
            await inter.response.send_message("✅ チャンネルを閉じました", ephemeral=True)
        except Exception:
            await inter.response.send_message("✅ 状態をリセットしました", ephemeral=True)

# ==================================================
# ✅ セットアップ
# ==================================================
async def send_start_panel(channel):
    """チャンネルに開始パネルを送信（管理用）"""
    view = MinesStartPanel()
    embed = discord.Embed(title="💎 マインス ゲーム", description="下のボタンから難易度を選んでゲームを始めてください", color=0x2ECC71)
    await channel.send(embed=embed, view=view)

def setup(bot):
    bot.add_view(MinesStartPanel())
    print("[MINES] ✅ マインス開始パネル登録完了")
