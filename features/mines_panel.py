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
    # ✅ オールベット対応
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
    units = [
        ("無量大数", 10**68), ("那由多", 10**64), ("不可思議", 10**60),
        ("阿僧祇", 10**56), ("恒河沙", 10**52), ("極", 10**48),
        ("載", 10**44), ("正", 10**40), ("澗", 10**36), ("溝", 10**32),
        ("穣", 10**28), ("垓", 10**24), ("京", 10**20), ("兆", 10**16),
        ("億", 10**12), ("万", 10**8),
    ]
    for name, scale in units:
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

def force_reset_user(user_id):
    uid = user_id
    try:
        all_data = load_history()
        all_data = [h for h in all_data if h.get("user_id") != uid]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    clear_user_state(uid)

# ==================================================
# ✅ 全倍率を 10,000倍 に引き上げ（50万 → 50億 に合わせ）
# ==================================================
FINAL_MULTIPLIER = {
     1: 250_000.0,       # 25倍 → 25万倍
     2: 400_000.0,       # 40倍 → 40万倍
     3: 650_000.0,       # 65倍 → 65万倍
     4: 1_000_000.0,     # 100倍 → 100万倍
     5: 1_600_000.0,     # 160倍 → 160万倍
     6: 2_600_000.0,     # 260倍 → 260万倍
     7: 4_200_000.0,     # 420倍 → 420万倍
     8: 6_800_000.0,     # 680倍 → 680万倍
     9: 11_000_000.0,    # 1100倍 → 1100万倍
    10: 18_000_000.0,    # 1800倍 → 1800万倍
    11: 30_000_000.0,    # 3000倍 → 3000万倍
    12: 50_000_000.0,    # 5000倍 → 5000万倍
    13: 85_000_000.0,    # 8500倍 → 8500万倍
    14: 150_000_000.0,   # 1.5万倍 → 1.5億倍
    15: 270_000_000.0,   # 2.7万倍 → 2.7億倍
    16: 500_000_000.0,   # 5万倍 → 5億倍
    17: 1_000_000_000.0, # 10万倍 → 10億倍
    18: 2_500_000_000.0, # 25万倍 → 25億倍
    19: 6_000_000_000.0, # 60万倍 → 60億倍
    20: 20_000_000_000.0, # 200万倍 → 200億倍
    21: 80_000_000_000.0, # 800万倍 → 800億倍
    22: 350_000_000_000.0, # 3500万倍 → 3500億倍
    23: 2_000_000_000_000.0, # 2億倍 → 2兆倍
    24: 50_000_000_000_000.0, # 50億倍 → 50兆倍
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
        if not self.channel or not hasattr(self.channel, 'guild') or not self.channel.guild:
            return False
        member = self.channel.guild.get_member(user.id)
        if not member:
            return False
        return any(role.name == OWNER_ROLE_NAME for role in member.roles)

    def board_text_for(self, user: discord.User, reveal_all=False):
        show_all = reveal_all or self.has_owner_role(user)
        lines = []
        for r in range(5):
            row = []
            for c in range(5):
                idx = r * 5 + c
                if self.opened[idx]:
                    row.append("💣" if self.grid[idx] else "💎")
                elif show_all:
                    row.append("💣" if self.grid[idx] else "💎")
                else:
                    row.append("□")
            lines.append(" ".join(row))
        return "\n".join(lines)

    def playing_embed_for(self, user: discord.User):
        e = discord.Embed(title="💎 マインス 💣", color=0xFFD700)
        e.add_field(name="🔹 プレイヤー", value=self.user.mention, inline=True)
        e.add_field(name="🔹 爆弾数", value=f"{self.bombs}個", inline=True)
        e.add_field(name="🔹 賭け額", value=format_value(self.bet), inline=True)
        e.add_field(name="🔥 現在倍率", value=f"**{format_mul(self.multiplier)}**", inline=True)
        if self.has_owner_role(user) and not self.game_over:
            e.add_field(name="👑 鯖主モード", value="全位置を表示中", inline=False)
        e.add_field(name="🎯 盤面", value=self.board_text_for(user), inline=False)
        return e

    def result_embed(self, title, desc, color):
        e = discord.Embed(title=title, description=desc, color=color)
        e.add_field(name="🎯 全盤面", value=self.board_text_for(self.user, reveal_all=True), inline=False)
        return e

async def create_game_channel(guild: discord.Guild, user: discord.User):
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
    return await guild.create_text_channel(
        name=f"マインズ-{user.name}", category=category,
        overwrites=overwrites, reason="マインズゲーム用"
    )

class MinesBoardView(discord.ui.View):
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
            btn = discord.ui.Button(label=lbl, style=style, disabled=disabled, row=idx // 5)
            btn.callback = lambda i, idx=idx: self.on_click(i, idx)
            self.add_item(btn)

    async def interaction_check(self, inter):
        uid = inter.user.id
        if uid not in game_states:
            await inter.response.send_message("❌ ゲームが存在しません。新しく開始してください。", ephemeral=True)
            return False
        if self.game.game_over:
            await inter.response.send_message("❌ ゲームは終了しています。", ephemeral=True)
            return False
        return inter.user.id == self.game.user_id

    async def on_click(self, inter, idx):
        g = self.game
        if g.game_over or g.opened[idx]:
            return await inter.response.defer(ephemeral=True)
        
        try:
            if not g.channel or not hasattr(g.channel, 'guild'):
                clear_user_state(inter.user.id)
                return await inter.response.send_message("❌ チャンネルが削除されています。新しく開始してください。", ephemeral=True)
        except Exception:
            clear_user_state(inter.user.id)
            return await inter.response.send_message("❌ 状態が不正です。再度ゲームを開始してください。", ephemeral=True)
        
        g.opened[idx] = True

        if g.grid[idx]:
            g.game_over = True
            add_point_value(g.user_id, -g.bet)
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            clear_user_state(g.user_id)
            save_history_entry({
                "user_id": g.user_id,
                "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet,
                "result": "lose", "amount": -g.bet,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("💣 爆弾！", 
                f"🔹 賭け：{format_value(g.bet)}\n🔹 結果：-{format_value(g.bet)}", 0xE74C3C)
            try:
                await inter.response.edit_message(embed=embed, view=None)
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
                "user_id": g.user_id,
                "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs, "bet": g.bet,
                "result": "win", "amount": win,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("🎉 全開け！",
                f"🔹 賭け：{format_value(g.bet)}\n🔹 確定倍率：{format_mul(g.multiplier)}\n🔹 獲得：+{format_value(win)}", 0xFFD700)
            try:
                await inter.response.edit_message(embed=embed, view=None)
                if g.control_message:
                    await g.control_message.delete()
            except Exception:
                pass
            return

        try:
            await inter.response.edit_message(embed=g.playing_embed_for(inter.user), view=MinesBoardView(g))
            if g.control_message:
                await g.control_message.edit(view=MinesControlView(g))
        except Exception:
            clear_user_state(inter.user.id)
            await inter.followup.send("❌ チャンネルが利用できません。新しく開始してください。", ephemeral=True)

class MinesControlView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        g = self.game
        can_end = g.opened_count > 0
        end_btn = discord.ui.Button(
            label="💰 この倍率で終了",
            style=discord.ButtonStyle.primary if can_end else discord.ButtonStyle.secondary,
            disabled=not can_end
        )
        end_btn.callback = self.on_end
        self.add_item(end_btn)

    async def interaction_check(self, inter):
        uid = inter.user.id
        if uid not in game_states:
            await inter.response.send_message("❌ ゲームが存在しません。新しく開始してください。", ephemeral=True)
            return False
        if self.game.game_over:
            await inter.response.send_message("❌ ゲームは終了しています。", ephemeral=True)
            return False
        return inter.user.id == self.game.user_id

    async def on_end(self, inter):
        g = self.game
        if g.game_over or g.opened_count == 0:
            return await inter.response.defer(ephemeral=True)
        
        try:
            if not g.channel or not hasattr(g.channel, 'guild'):
                clear_user_state(inter.user.id)
                return await inter.response.send_message("❌ チャンネルが削除されています。", ephemeral=True)
        except Exception:
            clear_user_state(inter.user.id)
            return await inter.response.send_message("❌ 状態が不正です。", ephemeral=True)
        
        g.game_over = True
        win = int(g.bet * g.multiplier)
        add_point_value(g.user_id, win)
        last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
        clear_user_state(g.user_id)
        save_history_entry({
            "user_id": g.user_id,
            "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            "bombs": g.bombs, "bet": g.bet,
            "result": "cashout", "amount": win,
            "multiplier": format_mul(g.multiplier)
        })
        embed = g.result_embed("💰 回収完了！",
            f"🔹 賭け：{format_value(g.bet)}\n🔹 確定倍率：{format_mul(g.multiplier)}\n🔹 獲得：+{format_value(win)}", 0x2ECC71)
        try:
            if g.message:
                await g.message.edit(embed=embed, view=None)
            await inter.response.send_message("✅ 終了しました", ephemeral=True)
        except Exception:
            await inter.response.send_message("✅ ポイントを加算しました", ephemeral=True)

class MinesResultView(discord.ui.View):
    def __init__(self, game: MinesGame):
        super().__init__(timeout=None)
        self.game = game
        uid = game.user_id
        if uid in last_settings:
            retry_btn = discord.ui.Button(label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary, row=0)
            retry_btn.callback = self.on_retry
            self.add_item(retry_btn)
        close_btn = discord.ui.Button(label="🗑️ チャンネルを閉じる", style=discord.ButtonStyle.danger, row=0)
        close_btn.callback = self.on_close
        self.add_item(close_btn)

    async def on_retry(self, inter):
        uid = self.game.user_id
        if uid in game_states:
            clear_user_state(uid)
        
        setting = last_settings.get(uid)
        if not setting:
            return await inter.response.send_message("❌ 設定が見つかりません", ephemeral=True)
        bal = get_point_value(uid)
        if setting["bet"] > bal:
            return await inter.response.send_message(
                f"❌ ポイントが足りません\n賭け額：{format_value(setting['bet'])}\n保有：{format_value(bal)}", ephemeral=True)
        channel = channel_map.get(uid)
        try:
            if not channel or not hasattr(channel, 'guild'):
                channel = None
        except Exception:
            channel = None
            
        if not channel:
            try:
                channel = await create_game_channel(inter.guild, inter.user)
                channel_map[uid] = channel
            except Exception as e:
                return await inter.response.send_message(f"❌ チャンネル作成失敗：{e}", ephemeral=True)
        new_game = MinesGame(inter.user, setting["bombs"], setting["bet"])
        new_game.channel = channel
        game_states[uid] = new_game
        board_view = MinesBoardView(new_game)
        control_view = MinesControlView(new_game)
        try:
            board_msg = await channel.send(embed=new_game.playing_embed_for(inter.user), view=board_view)
            new_game.message = board_msg
            message_map[uid] = board_msg
            control_msg = await channel.send("👇 操作ボタン", view=control_view)
            new_game.control_message = control_msg
            control_message_map[uid] = control_msg
            await inter.response.send_message("✅ 新しいゲームを開始しました！", ephemeral=True)
        except Exception as e:
            clear_user_state(uid)
            await inter.response.send_message(f"❌ 失敗：{e}", ephemeral=True)

    async def on_close(self, inter):
        uid = self.game.user_id
        c = channel_map.get(uid)
        clear_user_state(uid)
        try:
            if c:
                await c.delete(reason="ゲーム終了")
            await inter.response.send_message("✅ チャンネルを閉じました", ephemeral=True)
        except Exception:
            await inter.response.send_message("✅ 状態をリセットしました", ephemeral=True)

class MinesStartPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ かんたん [3個]", style=discord.ButtonStyle.grey, row=0, custom_id="mine_v25_easy")
    async def easy(self, inter, btn):
        uid = inter.user.id
        clear_user_state(uid)
        await self._start_fixed(inter, 3)

    @discord.ui.button(label="⚪ ふつう [5個]", style=discord.ButtonStyle.blurple, row=0, custom_id="mine_v25_normal")
    async def normal(self, inter, btn):
        uid = inter.user.id
        clear_user_state(uid)
        await self._start_fixed(inter, 5)

    @discord.ui.button(label="🔴 むずかしい [8個]", style=discord.ButtonStyle.red, row=0, custom_id="mine_v25_hard")
    async def hard(self, inter, btn):
        uid = inter.user.id
        clear_user_state(uid)
        await self._start_fixed(inter, 8)

    @discord.ui.button(label="⚙️ 自分で設定", style=discord.ButtonStyle.green, row=1, custom_id="mine_v25_custom")
    async def custom(self, inter, btn):
        uid = inter.user.id
        clear_user_state(uid)
        bal = get_point_value(uid)

        class BetInputModal(discord.ui.Modal, title="💎 自分で設定"):
            bet_in = discord.ui.TextInput(
                label=f"賭けるポイント 保有:{format_value(bal)} | ｢オールベット｣で全額",
                placeholder="例：1京 / オールベット", required=True
            )
            bomb_in = discord.ui.TextInput(
                label="爆弾の数（1～24）", placeholder="例：5", required=True
            )
            async def on_submit(s, m):
                try:
                    # ✅ オールベット対応：balanceを渡す
                    bet_val = parse_value(s.bet_in.value, bal)
                    bomb_val = parse_value(s.bomb_in.value)
                    if bet_val is None or bomb_val is None:
                        return await m.response.send_message("❌ 入力が正しくありません", ephemeral=True)
                    bet_val = int(bet_val)
                    bomb_val = int(bomb_val)
                    if bet_val <= 0 or bet_val > bal:
                        return await m.response.send_message("❌ ポイントが足りません", ephemeral=True)
                    if not (1 <= bomb_val <= 24):
                        return await m.response.send_message("❌ 爆弾は1～24で指定", ephemeral=True)
                    
                    channel = channel_map.get(uid)
                    try:
                        if not channel or not hasattr(channel, 'guild'):
                            channel = None
                    except Exception:
                        channel = None
                    
                    if not channel:
                        channel = await create_game_channel(m.guild, m.user)
                        channel_map[uid] = channel
                    
                    game = MinesGame(m.user, bomb_val, bet_val)
                    game.channel = channel
                    game_states[uid] = game
                    
                    board_view = MinesBoardView(game)
                    control_view = MinesControlView(game)
                    
                    board_msg = await channel.send(embed=game.playing_embed_for(m.user), view=board_view)
                    game.message = board_msg
                    message_map[uid] = board_msg
                    control_msg = await channel.send("👇 操作ボタン", view=control_view)
                    game.control_message = control_msg
                    control_message_map[uid] = control_msg
                    
                    await m.response.send_message(f"✅ 賭け額：{format_value(bet_val)} で開始！", ephemeral=True)
                except Exception as e:
                    print(f"[ERROR] {e}")
                    clear_user_state(uid)
                    await m.response.send_message(f"❌ エラー：{e}", ephemeral=True)
        
        await inter.response.send_modal(BetInputModal())

    @discord.ui.button(label="🔄 パネル更新", style=discord.ButtonStyle.secondary, row=2, custom_id="mine_v25_refresh")
    async def refresh_panel(self, inter, btn):
        new_view = MinesStartPanelView()
        try:
            await inter.response.edit_message(view=new_view)
            await inter.followup.send("✅ 更新完了！", ephemeral=True)
        except Exception as e:
            await inter.response.send_message(f"❌ 更新失敗：{e}", ephemeral=True)

    @discord.ui.button(label="🗑️ 強制リセット", style=discord.ButtonStyle.danger, row=2, custom_id="mine_v25_reset")
    async def force_reset_btn(self, inter, btn):
        clear_user_state(inter.user.id)
        await inter.response.send_message("✅ リセット完了！", ephemeral=True)

    async def _start_fixed(self, inter, bombs):
        uid = inter.user.id
        mul = format_mul(FINAL_MULTIPLIER[bombs])
        bal = get_point_value(uid)
        
        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個"):
            bet_in = discord.ui.TextInput(
                label=f"最大倍率：{mul} 保有:{format_value(bal)} | ｢オールベット｣で全額",
                placeholder="例：1000 / オールベット", required=True
            )
            async def on_submit(s, m):
                try:
                    val = parse_value(s.bet_in.value, bal)
                    if val is None or val <= 0 or val > bal:
                        return await m.response.send_message("❌ 入力が正しくありません", ephemeral=True)
                    
                    channel = channel_map.get(uid)
                    try:
                        if not channel or not hasattr(channel, 'guild'):
                            channel = None
                    except Exception:
                        channel = None
                    
                    if not channel:
                        channel = await create_game_channel(m.guild, m.user)
                        channel_map[uid] = channel
                    
                    game = MinesGame(m.user, bombs, int(val))
                    game.channel = channel
                    game_states[uid] = game
                    
                    board_view = MinesBoardView(game)
                    control_view = MinesControlView(game)
                    
                    board_msg = await channel.send(embed=game.playing_embed_for(m.user), view=board_view)
                    game.message = board_msg
                    message_map[uid] = board_msg
                    control_msg = await channel.send("👇 操作ボタン", view=control_view)
                    game.control_message = control_msg
                    control_message_map[uid] = control_msg
                    
                    await m.response.send_message(f"✅ 賭け額：{format_value(val)} で開始！", ephemeral=True)
                except Exception as e:
                    print(f"[ERROR] {e}")
                    clear_user_state(uid)
                    await m.response.send_message(f"❌ エラー：{e}", ephemeral=True)
        
        await inter.response.send_modal(BetModal())

async def setup(tree, bot):
    print("[MINES] setup() 実行中...")
    view = MinesStartPanelView()
    bot.add_view(view)
    print("[MINES] ✅ View登録完了！カスタムID: mine_v25_*")
