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

# ✅ 単位 → 数値 変換テーブル
UNIT_SCALE = {
    "無量大数": 10**68,
    "那由多": 10**64,
    "不可思議": 10**60,
    "阿僧祇": 10**56,
    "恒河沙": 10**52,
    "極": 10**48,
    "載": 10**44,
    "正": 10**40,
    "澗": 10**36,
    "溝": 10**32,
    "穣": 10**28,
    "垓": 10**24,
    "京": 10**20,
    "兆": 10**16,
    "億": 10**12,
    "万": 10**8,
}

def parse_value(input_str: str):
    s = input_str.strip()
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
        ("載", 10**44), ("正", 10**40), ("澗", 10**36),
        ("溝", 10**32), ("穣", 10**28), ("垓", 10**24),
        ("京", 10**20), ("兆", 10**16), ("億", 10**12), ("万", 10**8),
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
        ("載", 10**44), ("正", 10**40), ("澗", 10**36),
        ("溝", 10**32), ("穣", 10**28), ("垓", 10**24),
        ("京", 10**20), ("兆", 10**16), ("億", 10**12), ("万", 10**8),
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

def save_points_all(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_point_value(user_id):
    return load_points_all()["points"].get(str(user_id), 0)

def add_point_value(user_id, amount):
    data = load_points_all()
    uid = str(user_id)
    data["points"][uid] = data["points"].get(uid, 0) + amount
    save_points_all(data)
    return data["points"][uid]

# ===== ✅ 履歴管理 =====
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

def clear_all_user_data(user_id):
    """✅ ユーザーの履歴＋状態を完全消去"""
    uid = str(user_id)
    # 1. プレイ履歴削除
    all_data = load_history()
    all_data = [h for h in all_data if h.get("user_id") != user_id]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    # 2. ゲーム状態・設定履歴・チャンネル情報を全削除
    if user_id in game_states:
        del game_states[user_id]
    if user_id in last_settings:
        del last_settings[user_id]
    if user_id in channel_map:
        del channel_map[user_id]
    if user_id in message_map:
        del message_map[user_id]
    if user_id in control_message_map:
        del control_message_map[user_id]
    return True

FINAL_MULTIPLIER = {
     1: 25.0, 2: 40.0, 3: 65.0, 4: 100.0, 5: 160.0, 6: 260.0, 7: 420.0, 8: 680.0,
     9: 1100.0, 10: 1800.0, 11: 3000.0, 12: 5000.0, 13: 8500.0, 14: 15000.0,
    15: 27000.0, 16: 50000.0, 17: 100000.0, 18: 250000.0, 19: 600000.0,
    20: 2000000.0, 21: 8000000.0, 22: 35000000.0, 23: 200000000.0, 24: 5000000000.0,
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

main_panel_view = None

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

    def check_all_opened(self):
        safe = 25 - self.bombs
        return self.opened_count >= safe

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
        if self.game.game_over or self.game.user_id not in game_states:
            return False
        return inter.user.id == self.game.user_id

    async def on_click(self, inter, idx):
        g = self.game
        if g.game_over or g.opened[idx]:
            return await inter.response.defer(ephemeral=True)
        g.opened[idx] = True

        if g.grid[idx]:
            g.game_over = True
            add_point_value(g.user_id, -g.bet)
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            game_states.pop(g.user_id, None)
            save_history_entry({
                "user_id": g.user_id,
                "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs,
                "bet": g.bet,
                "result": "lose",
                "amount": -g.bet,
                "multiplier": format_mul(g.multiplier)
            })
            embed = g.result_embed("💣 爆弾！", 
                f"🔹 賭け：{format_value(g.bet)}\n🔹 結果：-{format_value(g.bet)}", 0xE74C3C)
            try:
                await inter.response.edit_message(embed=embed, view=MinesResultView(g))
                if g.control_message:
                    await g.control_message.delete()
            except Exception:
                pass
            return

        g.opened_count += 1
        g.multiplier = calc_step_multiplier(g.bombs, g.opened_count)

        if g.check_all_opened():
            g.game_over = True
            win = int(g.bet * g.multiplier)
            add_point_value(g.user_id, win)
            last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
            game_states.pop(g.user_id, None)
            save_history_entry({
                "user_id": g.user_id,
                "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
                "bombs": g.bombs,
                "bet": g.bet,
                "result": "win",
                "amount": win,
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

        try:
            await inter.response.edit_message(embed=g.playing_embed(), view=MinesBoardView(g))
            if g.control_message:
                await g.control_message.edit(view=MinesControlView(g))
        except Exception:
            pass

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
        if self.game.game_over or self.game.user_id not in game_states:
            return False
        return inter.user.id == self.game.user_id

    async def on_end(self, inter):
        g = self.game
        if g.game_over or g.opened_count == 0:
            return await inter.response.defer(ephemeral=True)
        g.game_over = True
        win = int(g.bet * g.multiplier)
        add_point_value(g.user_id, win)
        last_settings[g.user_id] = {"bombs": g.bombs, "bet": g.bet}
        game_states.pop(g.user_id, None)
        save_history_entry({
            "user_id": g.user_id,
            "time": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S"),
            "bombs": g.bombs,
            "bet": g.bet,
            "result": "cashout",
            "amount": win,
            "multiplier": format_mul(g.multiplier)
        })
        embed = g.result_embed("💰 回収完了！",
            f"🔹 賭け：{format_value(g.bet)}\n🔹 確定倍率：{format_mul(g.multiplier)}\n🔹 獲得：+{format_value(win)}", 0x2ECC71)
        try:
            if g.message:
                await g.message.edit(embed=embed, view=MinesResultView(g))
            await inter.response.edit_message(content="✅ 終了しました", view=None)
        except Exception:
            pass

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
            return await inter.response.send_message("❌ ゲーム進行中です！", ephemeral=True)
        setting = last_settings.get(uid)
        if not setting:
            return await inter.response.send_message("❌ 設定が見つかりません", ephemeral=True)
        bal = get_point_value(uid)
        if setting["bet"] > bal:
            return await inter.response.send_message(
                f"❌ ポイントが足りません\n賭け額：{format_value(setting['bet'])}\n保有：{format_value(bal)}", ephemeral=True)
        channel = channel_map.get(uid)
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
            board_msg = await channel.send(embed=new_game.playing_embed(), view=board_view)
            new_game.message = board_msg
            message_map[uid] = board_msg
            control_msg = await channel.send("👇 操作ボタン", view=control_view)
            new_game.control_message = control_msg
            control_message_map[uid] = control_msg
            await inter.response.send_message("✅ 新しいゲームを開始しました！", ephemeral=True)
        except Exception as e:
            game_states.pop(uid, None)
            await inter.response.send_message(f"❌ メッセージ送信失敗：{e}", ephemeral=True)

    async def on_close(self, inter):
        uid = self.game.user_id
        c = channel_map.pop(uid, None)
        message_map.pop(uid, None)
        control_message_map.pop(uid, None)
        game_states.pop(uid, None)
        last_settings.pop(uid, None)
        try:
            if c:
                await c.delete(reason="ゲーム終了")
            await inter.response.send_message("✅ チャンネルを閉じました", ephemeral=True)
        except Exception:
            pass

class MinesStartPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ かんたん [3個]", style=discord.ButtonStyle.grey, row=0, custom_id="mine_v10_easy")
    async def easy(self, inter, btn):
        await self._start_fixed(inter, 3)

    @discord.ui.button(label="⚪ ふつう [5個]", style=discord.ButtonStyle.blurple, row=0, custom_id="mine_v10_normal")
    async def normal(self, inter, btn):
        await self._start_fixed(inter, 5)

    @discord.ui.button(label="🔴 むずかしい [8個]", style=discord.ButtonStyle.red, row=0, custom_id="mine_v10_hard")
    async def hard(self, inter, btn):
        await self._start_fixed(inter, 8)

    @discord.ui.button(label="⚙️ 自分で設定", style=discord.ButtonStyle.green, row=1, custom_id="mine_v10_custom")
    async def custom(self, inter, btn):
        uid = inter.user.id
        # ✅ 全消去後はここが必ず通るようになる
        if uid in game_states:
            return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
        bal = get_point_value(uid)
        class BetInputModal(discord.ui.Modal, title="💎 自分で設定"):
            bet_in = discord.ui.TextInput(
                label=f"賭けるポイント（例：1.5京 / 10兆）\n保有：{format_value(bal)}",
                placeholder="例：1京", required=True
            )
            bomb_in = discord.ui.TextInput(
                label="爆弾の数（1～24）", placeholder="例：5", required=True
            )
            async def on_submit(s, m):
                bet_val = parse_value(s.bet_in.value)
                bomb_val = parse_value(s.bomb_in.value)
                if bet_val is None or bomb_val is None:
                    return await m.response.send_message(
                        "❌ 入力形式が正しくありません\n例：1京 / 5000 / 2.5兆", ephemeral=True)
                bet_val = int(bet_val)
                bomb_val = int(bomb_val)
                if bet_val <= 0 or bet_val > bal:
                    return await m.response.send_message(
                        f"❌ ポイントが足りません\n賭け額：{format_value(bet_val)}\n保有：{format_value(bal)}", ephemeral=True)
                if bomb_val < 1 or bomb_val > 24:
                    return await m.response.send_message(
                        "❌ 爆弾の数は1～24で指定してください", ephemeral=True)
                await start_game(m.user, m.guild, bomb_val, bet_val)
                await m.response.send_message("✅ ゲームチャンネルを作成しました！", ephemeral=True)
        await inter.response.send_modal(BetInputModal())

    # ✅ 全消去ボタン：履歴＋状態＋チャンネル情報 まとめてリセット
    @discord.ui.button(label="🗑️ 全履歴・状態消去", style=discord.ButtonStyle.danger, row=2, custom_id="mine_v10_resetall")
    async def reset_all(self, inter, btn):
        uid = inter.user.id
        user_history = load_history(uid)
        history_count = len(user_history)
        is_active = uid in game_states
        
        confirm_view = discord.ui.View(timeout=60)
        yes_btn = discord.ui.Button(label="✅ 全部消去する", style=discord.ButtonStyle.danger)
        no_btn = discord.ui.Button(label="❌ キャンセル", style=discord.ButtonStyle.secondary)
        
        async def confirm_yes(i):
            clear_all_user_data(uid)
            await i.response.edit_message(
                content="✅ プレイ履歴・チャンネル情報・状態 全て消去しました！\n"
                        "これで「自分で設定」を再び押せるようになります ✨",
                view=None
            )
        
        async def confirm_no(i):
            await i.response.edit_message(content="❌ キャンセルしました", view=None)
        
        yes_btn.callback = confirm_yes
        no_btn.callback = confirm_no
        confirm_view.add_item(yes_btn)
        confirm_view.add_item(no_btn)
        
        status_line = []
        if history_count > 0:
            status_line.append(f"・プレイ履歴：{history_count}件")
        if is_active:
            status_line.append("・進行中のゲーム情報あり")
        if not status_line:
            status_line.append("・削除する情報は見つかりませんでした")
        
        await inter.response.send_message(
            f"⚠️ 以下の情報を全て消去しますか？\n"
            + "\n".join(status_line) + "\n"
            "・設定履歴\n"
            "・チャンネル情報\n"
            "・その他残留データ\n\n"
            "この操作は取り消せません！",
            view=confirm_view,
            ephemeral=True
        )

    async def _start_fixed(self, inter, bombs):
        uid = inter.user.id
        if uid in game_states:
            return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
        mul = format_mul(FINAL_MULTIPLIER[bombs])
        bal = get_point_value(uid)
        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個"):
            bet_in = discord.ui.TextInput(
                label=f"🔥 最大倍率：{mul}\n賭けるポイント（例：1京 / 10兆）",
                placeholder="例：1000", required=True
            )
            async def on_submit(s, m):
                val = parse_value(s.bet_in.value)
                if val is None:
                    return await m.response.send_message(
                        "❌ 入力形式が正しくありません\n例：1京 / 5000 / 2.5兆", ephemeral=True)
                val = int(val)
                if val <= 0 or val > bal:
                    return await m.response.send_message(
                        f"❌ ポイントが足りません\n賭け額：{format_value(val)}\n保有：{format_value(bal)}", ephemeral=True)
                await start_game(m.user, m.guild, bombs, val)
                await m.response.send_message("✅ ゲームチャンネルを作成しました！", ephemeral=True)
        await inter.response.send_modal(BetModal())

async def start_game(user, guild, bombs, bet):
    uid = user.id
    game_states.pop(uid, None)
    channel = channel_map.get(uid)
    if not channel:
        channel = await create_game_channel(guild, user)
        channel_map[uid] = channel
    game = MinesGame(user, bombs, bet)
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
    except Exception as e:
        game_states.pop(uid, None)
        raise Exception(f"メッセージ送信失敗：{e}")

async def setup(tree, bot):
    global main_panel_view
    main_panel_view = MinesStartPanelView()
    bot.add_view(main_panel_view)
    print("✅ マインスパネルView登録完了")
