import discord
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"

def load_points_all():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "points" not in data:
            return {"points": data}
        return data

def save_points_all(data):
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

active_games = {}
user_state = {}
last_settings = {}

class MinesGameView(discord.ui.View):
    def __init__(self, user_id: int, bombs: int, bet: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bombs = bombs
        self.bet = bet
        self.grid = [False] * 25
        self.opened = [False] * 25
        self.opened_count = 0
        self.multiplier = 1.0
        self.game_over = False
        self.reveal_all = False  # 全マス表示モード
        for p in random.sample(range(25), bombs):
            self.grid[p] = True
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        for idx in range(25):
            # ゲーム終了時は全マス表示
            if self.game_over or self.reveal_all:
                label = "💣" if self.grid[idx] else "💎"
                style = discord.ButtonStyle.danger if self.grid[idx] else discord.ButtonStyle.success
                disabled = True
            elif self.opened[idx]:
                label = "💣" if self.grid[idx] else "💎"
                style = discord.ButtonStyle.danger if self.grid[idx] else discord.ButtonStyle.success
                disabled = True
            else:
                label = "□"
                style = discord.ButtonStyle.secondary
                disabled = False
            self.add_item(discord.ui.Button(
                label=label, style=style, disabled=disabled,
                custom_id=f"mine:cell:{self.user_id}:{idx}"
            ))
        # ゲーム中は回収ボタン表示
        if not self.game_over and self.opened_count > 0:
            self.add_item(discord.ui.Button(
                label="💰 回収", style=discord.ButtonStyle.primary, row=4,
                custom_id=f"mine:cash:{self.user_id}"
            ))

    def _build_end_buttons(self):
        self.clear_items()
        # 同じ設定でもう1回
        if self.user_id in last_settings:
            self.add_item(discord.ui.Button(
                label="🔄 同じ設定でもう1回", style=discord.ButtonStyle.primary, row=0,
                custom_id=f"mine:retry:{self.user_id}"
            ))
        # パネルに戻る
        self.add_item(discord.ui.Button(
            label="📋 パネルに戻る", style=discord.ButtonStyle.secondary, row=0,
            custom_id=f"mine:back_panel:{self.user_id}"
        ))

    def make_embed(self):
        if self.game_over:
            return None
        e = discord.Embed(title="💎 マインス 💣", color=0x1a1a1a)
        e.add_field(name="🔹 爆弾数", value=f"{self.bombs}個", inline=True)
        e.add_field(name="🔹 賭け額", value=f"{self.bet:,}pt", inline=True)
        e.add_field(name="🔹 現在倍率", value=f"**{self.multiplier}倍**", inline=True)
        return e

    async def open_cell(self, inter, idx):
        if inter.user.id != self.user_id or self.game_over:
            return await inter.response.defer()
        
        self.opened[idx] = True
        
        if self.grid[idx]:
            # 爆弾を引いた → ゲームオーバー・全マス表示
            self.game_over = True
            self.reveal_all = True
            add_point_value(self.user_id, -self.bet)
            if self.user_id in active_games:
                del active_games[self.user_id]
            last_settings[self.user_id] = {"bombs": self.bombs, "bet": self.bet}
            e = discord.Embed(title="💣 爆弾！",
                description=f"🔹 賭け：{self.bet:,}pt\n🔹 結果：-{self.bet:,}pt",
                color=0xE74C3C)
            self._build_buttons()    # 全マスをめくって表示
            self._build_end_buttons() # 再挑戦・戻るボタン
            await inter.response.edit_message(embed=e, view=self)
        else:
            # 当たりマス
            self.opened_count += 1
            self.multiplier = calc_step_multiplier(self.bombs, self.opened_count)
            self._build_buttons()
            await inter.response.edit_message(embed=self.make_embed(), view=self)

    async def cash_out(self, inter):
        if inter.user.id != self.user_id or self.game_over:
            return await inter.response.defer()
        # 回収 → ゲーム終了・全マス表示
        self.game_over = True
        self.reveal_all = True
        win = int(self.bet * self.multiplier)
        add_point_value(self.user_id, win)
        if self.user_id in active_games:
            del active_games[self.user_id]
        last_settings[self.user_id] = {"bombs": self.bombs, "bet": self.bet}
        e = discord.Embed(title="💰 回収完了！",
            description=f"🔹 賭け：{self.bet:,}pt\n🔹 倍率：{self.multiplier}倍\n🔹 獲得：+{win:,}pt",
            color=0x2ECC71)
        self._build_buttons()    # 全マスをめくって表示
        self._build_end_buttons() # 再挑戦・戻るボタン
        await inter.response.edit_message(embed=e, view=self)

BOMBS_PER_PAGE = 8

class BombsSelectView(discord.ui.View):
    def __init__(self, user_id=None):
        super().__init__(timeout=None)
        if user_id:
            self._build_content(user_id)

    def _build_content(self, user_id):
        self.clear_items()
        state = user_state.get(user_id, {})
        page = state.get("page", 0)
        selected = state.get("selected_bombs")
        start = page * BOMBS_PER_PAGE + 1
        end = min(24, start + BOMBS_PER_PAGE - 1)
        for n in range(start, end + 1):
            style = discord.ButtonStyle.primary if selected == n else discord.ButtonStyle.secondary
            self.add_item(discord.ui.Button(
                label=str(n), style=style,
                custom_id=f"mine:bomb_sel:{user_id}:{n}"
            ))
        prev_d = page == 0
        next_d = end >= 24
        self.add_item(discord.ui.Button(
            label="◀ 前", style=discord.ButtonStyle.secondary, disabled=prev_d,
            custom_id=f"mine:bomb_prev:{user_id}", row=4
        ))
        self.add_item(discord.ui.Button(
            label=f"{page+1}/3", style=discord.ButtonStyle.secondary, disabled=True,
            custom_id="mine:bomb_page_info", row=4
        ))
        self.add_item(discord.ui.Button(
            label="次 ▶", style=discord.ButtonStyle.secondary, disabled=next_d,
            custom_id=f"mine:bomb_next:{user_id}", row=4
        ))
        self.add_item(discord.ui.Button(
            label="✅ 決定する", style=discord.ButtonStyle.primary,
            custom_id=f"mine:bomb_confirm:{user_id}", row=4
        ))

    def get_embed(self, user_id):
        state = user_state.get(user_id, {})
        selected = state.get("selected_bombs")
        bet = state.get("bet")
        mul_text = "選択してください"
        if selected:
            mul_text = format_mul(FINAL_MULTIPLIER[selected])
        e = discord.Embed(color=0x2b2b2b)
        if bet:
            e.add_field(name="💵 賭け額", value=f"**{bet:,}pt**", inline=False)
        e.add_field(name="💣 爆弾数", value=f"最終倍率：{mul_text}", inline=False)
        if selected:
            e.add_field(name="選択中", value=f"**{selected}個**", inline=False)
        return e

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

    @discord.ui.button(label="⚙️ 自分で設定", style=discord.ButtonStyle.primary, row=1, custom_id="mine:panel_custom")
    async def custom(self, inter, btn):
        uid = inter.user.id
        if uid in active_games:
            return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
        
        bal = get_point_value(uid)
        
        class BetInputModal(discord.ui.Modal, title="💎 賭け額を入力"):
            amount = discord.ui.TextInput(
                label=f"保有ポイント：{bal:,}pt",
                placeholder="例：1000",
                required=True
            )
            async def on_submit(s, m):
                try:
                    val = int(s.amount.value.strip())
                except:
                    return await m.response.send_message("❌ 数字を入力してください", ephemeral=True)
                if val <= 0 or val > bal:
                    return await m.response.send_message(f"❌ ポイントが足りません\n保有：{bal:,}pt", ephemeral=True)
                
                user_state[uid] = {"bet": val, "selected_bombs": None, "page": 0}
                view = BombsSelectView(uid)
                await m.response.send_message(embed=view.get_embed(uid), view=view, ephemeral=True)
        
        await inter.response.send_modal(BetInputModal())

    @discord.ui.button(label="💰 ポイント確認", style=discord.ButtonStyle.secondary, row=2, custom_id="mine:panel_check_point")
    async def check_point_btn(self, inter, btn):
        bal = get_point_value(inter.user.id)
        await inter.response.send_message(f"💎 保有ポイント：**{bal:,}pt**", ephemeral=True)

    @discord.ui.button(label="📝 パネル内容編集", style=discord.ButtonStyle.secondary, row=2, custom_id="mine:panel_edit")
    async def edit_panel_btn(self, inter, btn):
        if not is_owner(inter):
            return await inter.response.send_message("❌ オーナー専用です", ephemeral=True)
        class EditModal(discord.ui.Modal, title="📝 パネル編集"):
            t = discord.ui.TextInput(label="タイトル", default="💎 マインス 💣", required=True, max_length=30)
            d = discord.ui.TextInput(label="説明文", 
                default="下のボタンから難易度を選択してゲームを開始できます！\n✅ かんたん [3個] ｜ ⚪ ふつう [5個] ｜ 🔴 むずかしい [8個] ｜ ⚙️ 自分で設定",
                required=True, style=discord.TextStyle.long)
            async def on_submit(s, m):
                await m.response.edit_message(embed=discord.Embed(title=s.t.value, description=s.d.value, color=0x1a1a1a), view=MinesStartPanelView())
        await inter.response.send_modal(EditModal())

    async def _start_fixed(self, inter, bombs):
        uid = inter.user.id
        if uid in active_games:
            return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
        mul = format_mul(FINAL_MULTIPLIER[bombs])
        bal = get_point_value(uid)
        class BetModal(discord.ui.Modal, title=f"💎 爆弾{bombs}個"):
            bet_in = discord.ui.TextInput(label=f"倍率：{mul}\n賭けるポイント", required=True)
            async def on_submit(s, m):
                try:
                    val = int(s.bet_in.value.strip())
                except:
                    return await m.response.send_message("❌ 数字を入力", ephemeral=True)
                if val <= 0 or val > bal:
                    return await m.response.send_message(f"❌ ポイントが足りません\n保有：{bal:,}pt", ephemeral=True)
                game = MinesGameView(uid, bombs, val)
                active_games[uid] = game
                await m.response.send_message(embed=game.make_embed(), view=game, ephemeral=True)
        await inter.response.send_modal(BetModal())

async def start_retry(user_id, inter):
    if user_id in active_games:
        return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
    setting = last_settings.get(user_id)
    if not setting:
        return await inter.response.send_message("❌ 前回の設定が見つかりません", ephemeral=True)
    bal = get_point_value(user_id)
    if setting["bet"] > bal:
        return await inter.response.send_message(f"❌ ポイントが足りません\n賭け額：{setting['bet']:,}pt\n保有：{bal:,}pt", ephemeral=True)
    game = MinesGameView(user_id, setting["bombs"], setting["bet"])
    active_games[user_id] = game
    await inter.response.edit_message(embed=game.make_embed(), view=game)

async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is None:
        return

    if not hasattr(bot, "_mines_views_done"):
        bot.add_view(MinesStartPanelView())
        bot._mines_views_done = True
        print("✅ mines_panel View登録完了")

    if not hasattr(bot, "_mines_interaction_done"):
        bot._mines_interaction_done = True

        @bot.event
        async def on_interaction(inter):
            if not inter.data or "custom_id" not in inter.data:
                return
            cid = inter.data["custom_id"]
            parts = cid.split(":")

            if cid.startswith("mine:retry:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                await start_retry(uid, inter)
                return

            if cid.startswith("mine:back_panel:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                await inter.response.edit_message(
                    embed=discord.Embed(
                        title="💎 マインス 💣",
                        description="下のボタンから難易度を選択してゲームを開始できます！\n✅ かんたん [3個] ｜ ⚪ ふつう [5個] ｜ 🔴 むずかしい [8個] ｜ ⚙️ 自分で設定",
                        color=0x1a1a1a
                    ),
                    view=MinesStartPanelView()
                )
                return

            if cid.startswith("mine:bomb_sel:"):
                _, _, uid_str, num_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                if uid not in user_state:
                    return await inter.response.send_message("❌ 最初からやり直してください", ephemeral=True)
                user_state[uid]["selected_bombs"] = int(num_str)
                view = BombsSelectView(uid)
                await inter.response.edit_message(embed=view.get_embed(uid), view=view)

            elif cid.startswith("mine:bomb_prev:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                if uid not in user_state:
                    return await inter.response.send_message("❌ 最初からやり直してください", ephemeral=True)
                user_state[uid]["page"] = max(0, user_state[uid]["page"] - 1)
                view = BombsSelectView(uid)
                await inter.response.edit_message(embed=view.get_embed(uid), view=view)

            elif cid.startswith("mine:bomb_next:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                if uid not in user_state:
                    return await inter.response.send_message("❌ 最初からやり直してください", ephemeral=True)
                user_state[uid]["page"] = min(2, user_state[uid]["page"] + 1)
                view = BombsSelectView(uid)
                await inter.response.edit_message(embed=view.get_embed(uid), view=view)

            elif cid.startswith("mine:bomb_confirm:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                state = user_state.get(uid)
                if not state:
                    return await inter.response.send_message("❌ 最初からやり直してください", ephemeral=True)
                if not state.get("selected_bombs"):
                    return await inter.response.send_message("❌ 爆弾数を選択してください", ephemeral=True)
                if uid in active_games:
                    return await inter.response.send_message("❌ ゲーム進行中です！終了してから再開してください", ephemeral=True)
                game = MinesGameView(uid, state["selected_bombs"], state["bet"])
                active_games[uid] = game
                del user_state[uid]
                await inter.response.send_message(embed=game.make_embed(), view=game, ephemeral=True)

            elif cid.startswith("mine:cell:"):
                _, _, uid_str, idx_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                game = active_games.get(uid)
                if not game or game.game_over:
                    return await inter.response.defer()
                await game.open_cell(inter, int(idx_str))

            elif cid.startswith("mine:cash:"):
                _, _, uid_str = parts
                uid = int(uid_str)
                if inter.user.id != uid:
                    return await inter.response.defer()
                game = active_games.get(uid)
                if not game or game.game_over:
                    return await inter.response.defer()
                await game.cash_out(inter)
    return
