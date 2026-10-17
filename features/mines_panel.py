import discord
from discord import app_commands
import random
from datetime import datetime, timedelta, timezone
from core.common import is_owner
JST = timezone(timedelta(hours=9))

# ========== ポイント読み書き ==========
DATA_FILE = "kn_points_data.json"
def load_points_all():
    import json, os
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "points" not in data:
            return {"points": data}
        return data
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

# ========== 倍率固定値 ==========
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

# ========== ゲーム本体 ==========
active_games = {}
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
        for p in random.sample(range(25), bombs):
            self.grid[p] = True
        self._build()

    def _build(self):
        self.clear_items()
        for idx in range(25):
            if self.opened[idx]:
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
        if not self.game_over and self.opened_count > 0:
            self.add_item(discord.ui.Button(
                label="💰 回収", style=discord.ButtonStyle.primary, row=4,
                custom_id=f"mine:cash:{self.user_id}"
            ))

    def embed(self):
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
            self.game_over = True
            add_point_value(self.user_id, -self.bet)
            e = discord.Embed(title="💣 爆弾！",
                description=f"🔹 賭け：{self.bet:,}pt\n🔹 結果：-{self.bet:,}pt",
                color=0xE74C3C)
            self._build()
            await inter.response.edit_message(embed=e, view=self)
        else:
            self.opened_count += 1
            self.multiplier = calc_step_multiplier(self.bombs, self.opened_count)
            self._build()
            await inter.response.edit_message(embed=self.embed(), view=self)

    async def cash_out(self, inter):
        if inter.user.id != self.user_id or self.game_over:
            return await inter.response.defer()
        self.game_over = True
        win = int(self.bet * self.multiplier)
        add_point_value(self.user_id, win)
        e = discord.Embed(title="💰 回収完了！",
            description=f"🔹 賭け：{self.bet:,}pt\n🔹 倍率：{self.multiplier}倍\n🔹 獲得：+{win:,}pt",
            color=0x2ECC71)
        await inter.response.edit_message(embed=e, view=None)

# ========== 爆弾数選択 ==========
BOMBS_PER_PAGE = 8
class BombsSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.page = 0
        self.selected = None
        self._render()

    def _render(self):
        self.clear_items()
        start = self.page * BOMBS_PER_PAGE + 1
        end = min(24, start + BOMBS_PER_PAGE - 1)
        for n in range(start, end + 1):
            style = discord.ButtonStyle.secondary if self.selected == n else discord.ButtonStyle.grey
            self.add_item(discord.ui.Button(
                label=str(n), style=style,
                custom_id=f"mine:bomb_sel:{n}"
            ))
        prev_d = self.page == 0
        next_d = end >= 24
        self.add_item(discord.ui.Button(
            label="◀ 前", style=discord.ButtonStyle.grey, disabled=prev_d,
            custom_id="mine:bomb_prev", row=4
        ))
        self.add_item(discord.ui.Button(
            label=f"{self.page+1}/3", style=discord.ButtonStyle.secondary, disabled=True,
            custom_id="mine:bomb_page_info", row=4
        ))
        self.add_item(discord.ui.Button(
            label="次 ▶", style=discord.ButtonStyle.grey, disabled=next_d,
            custom_id="mine:bomb_next", row=4
        ))
        self.add_item(discord.ui.Button(
            label="✅ 決定する", style=discord.ButtonStyle.primary,
            custom_id="mine:bomb_confirm", row=4
        ))

    def embed(self):
        mul_text = "選択してください"
        if self.selected:
            mul_text = format_mul(FINAL_MULTIPLIER[self.selected])
        e = discord.Embed(color=0x2b2b2b)
        e.add_field(name="**爆弾数**", value=f"最終倍率：{mul_text}", inline=False)
        if self.selected:
            e.add_field(name="選択中", value=f"**{self.selected}個**", inline=False)
        return e

# ========== スタートパネル ==========
class MinesStartPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ かんたん [3個]", style=discord.ButtonStyle.success, row=0, custom_id="mine:panel_easy")
    async def easy(self, inter, btn):
        await self._bet_modal(inter, 3)

    @discord.ui.button(label="⚪ ふつう [5個]", style=discord.ButtonStyle.secondary, row=0, custom_id="mine:panel_normal")
    async def normal(self, inter, btn):
        await self._bet_modal(inter, 5)

    @discord.ui.button(label="🔴 むずかしい [8個]", style=discord.ButtonStyle.danger, row=1, custom_id="mine:panel_hard")
    async def hard(self, inter, btn):
        await self._bet_modal(inter, 8)

    @discord.ui.button(label="⚙️ 自分で設定 [1～24個]", style=discord.ButtonStyle.primary, row=1, custom_id="mine:panel_custom")
    async def custom(self, inter, btn):
        await inter.response.send_message(embed=BombsSelectView().embed(), view=BombsSelectView(), ephemeral=True)

    async def _bet_modal(self, inter, bombs):
        mul = format_mul(FINAL_MULTIPLIER[bombs])
        class BetModal(discord.ui.Modal(title="💎 マインス - 賭け額入力")):
            bet_in = discord.ui.TextInput(label=f"爆弾{bombs}個 最終倍率：{mul}\n賭けるポイント", required=True)
            async def on_submit(s, m):
                try:
                    val = int(s.bet_in.value.strip())
                except:
                    return await m.response.send_message("❌ 数値を入力", ephemeral=True)
                bal = get_point_value(m.user.id)
                if val <= 0 or val > bal:
                    return await m.response.send_message(f"❌ 無効\n保有：{bal:,}pt", ephemeral=True)
                game = MinesGameView(m.user.id, bombs, val)
                active_games[m.user.id] = game
                await m.response.send_message(embed=game.embed(), view=game, ephemeral=True)
        await inter.response.send_modal(BetModal())

# ========== セットアップ ==========
async def setup(tree, bot):
    if not hasattr(bot, "_mines_views_ready"):
        bot.add_view(MinesStartPanelView())
        bot.add_view(BombsSelectView())
        bot._mines_views_ready = True
        print("✅ mines_panel 永久View登録完了")

    # ✅ 指定されたサーバーIDで即時反映
    GUILD_ID = 1542788841465978880

    @tree.command(
        name="マインズパネル設置",
        description="💎 マインス パネルを設置",
        guild=discord.Object(id=GUILD_ID)
    )
    @app_commands.check(is_owner)
    async def setup_panel(inter):
        e = discord.Embed(title="💎 マインス 💣", color=0x1a1a1a)
        e.description = (
            "爆弾を避けて金塊を集め、好きなタイミングで回収！\n"
            "────────────────────────────\n"
            "✅ かんたん  [3個]  約15.7倍\n"
            "⚪ ふつう    [5個]  約32.9倍\n"
            "🔴 むずかしい [8個]  約96.3倍\n"
            "⚙️ 自分で設定 [1～24個]"
        )
        await inter.response.send_message(embed=e, view=MinesStartPanelView())

    @bot.listen()
    async def on_interaction(inter):
        if not inter.data or "custom_id" not in inter.data:
            return
        cid = inter.data["custom_id"]

        if cid.startswith("mine:bomb_sel:"):
            num = int(cid.split(":")[-1])
            view = BombsSelectView()
            if inter.message.components:
                for comp in inter.message.components:
                    for btn in comp.children:
                        if hasattr(btn, "label") and isinstance(btn.label, str) and "/" in btn.label:
                            try:
                                view.page = int(btn.label.split("/")[0]) - 1
                            except: pass
            view.selected = num
            await inter.response.edit_message(embed=view.embed(), view=view)

        elif cid == "mine:bomb_prev":
            view = BombsSelectView()
            if inter.message.components:
                for comp in inter.message.components:
                    for btn in comp.children:
                        if hasattr(btn, "label") and isinstance(btn.label, str) and "/" in btn.label:
                            try:
                                view.page = max(0, int(btn.label.split("/")[0]) - 2)
                            except: pass
            await inter.response.edit_message(embed=view.embed(), view=view)

        elif cid == "mine:bomb_next":
            view = BombsSelectView()
            if inter.message.components:
                for comp in inter.message.components:
                    for btn in comp.children:
                        if hasattr(btn, "label") and isinstance(btn.label, str) and "/" in btn.label:
                            try:
                                view.page = min(2, int(btn.label.split("/")[0]))
                            except: pass
            await inter.response.edit_message(embed=view.embed(), view=view)

        elif cid == "mine:bomb_confirm":
            selected = None
            for comp in inter.message.components:
                for btn in comp.children:
                    if getattr(btn, "style", None) == discord.ButtonStyle.secondary and getattr(btn, "label", "").isdigit():
                        selected = int(btn.label)
                        break
            if not selected:
                return await inter.response.send_message("❌ 爆弾数を選択してください", ephemeral=True)
            mul = format_mul(FINAL_MULTIPLIER[selected])
            class CustomModal(discord.ui.Modal(title="💎 マインス - 賭け額入力")):
                bet_in = discord.ui.TextInput(label=f"爆弾{selected}個 最終倍率：{mul}\n賭けるポイント", required=True)
                async def on_submit(s, m):
                    try:
                        val = int(s.bet_in.value.strip())
                    except:
                        return await m.response.send_message("❌ 数値を入力", ephemeral=True)
                    bal = get_point_value(m.user.id)
                    if val <= 0 or val > bal:
                        return await m.response.send_message(f"❌ 無効\n保有：{bal:,}pt", ephemeral=True)
                    game = MinesGameView(m.user.id, selected, val)
                    active_games[m.user.id] = game
                    await m.response.send_message(embed=game.embed(), view=game, ephemeral=True)
            await inter.response.send_modal(CustomModal())

        elif cid.startswith("mine:cell:"):
            _, _, uid, idx = cid.split(":")
            if int(uid) != inter.user.id:
                return await inter.response.defer()
            game = active_games.get(inter.user.id)
            if not game or game.game_over:
                return await inter.response.defer()
            await game.open_cell(inter, int(idx))

        elif cid.startswith("mine:cash:"):
            _, _, uid = cid.split(":")
            if int(uid) != inter.user.id:
                return await inter.response.defer()
            game = active_games.get(inter.user.id)
            if not game or game.game_over:
                return await inter.response.defer()
            await game.cash_out(inter)
