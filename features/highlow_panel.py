import discord
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
HL_RESULT_CHANNEL_ID = 1558772472881488004

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
CARD_VALUES = {
    "A": 1,
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
    "J": 11, "Q": 12, "K": 13
}
SUITS = ["♠", "♥", "♦", "♣"]

def create_deck():
    deck = [(s, r) for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def card_value(rank):
    return CARD_VALUES[rank]

def load_data():
    if not os.path.exists(DATA_FILE): return {"points": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception: return {"points": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_points(user_id):
    return load_data().get("points", {}).get(str(user_id), 0)

def add_points(user_id, amount):
    data = load_data()
    uid = str(user_id)
    data["points"][uid] = data["points"].get(uid, 0) + amount
    save_data(data)
    return data["points"][uid]

def get_multiplier(streak):
    return 1.0 + (streak - 1) * 0.3

async def send_result_embed(client, user, first_card, next_card, choice, result_text, change, bet, total, streak, is_free=False, is_cashout=False):
    channel = client.get_channel(HL_RESULT_CHANNEL_ID)
    if not channel:
        print(f"⚠️ HL_RESULT_CHANNEL_ID が見つかりません: {HL_RESULT_CHANNEL_ID}")
        return
    title = "📈 ハイ＆ロー確定" if is_cashout else ("📈 結果（お試し）" if is_free else "📈 結果")
    color = 0x999999 if is_free else (0x2ECC71 if change >= 0 else 0xE74C3C)
    embed = discord.Embed(title=title, description=f"{user.mention} がプレイ", color=color, timestamp=datetime.now(JST))
    embed.add_field(name="1枚目", value=f"{card_value(first_card[1])}", inline=True)
    if next_card:
        embed.add_field(name="選択", value="📈ハイ" if choice=="high" else "📉ロー", inline=True)
        embed.add_field(name="2枚目", value=f"{card_value(next_card[1])}", inline=True)
    embed.add_field(name="結果", value=result_text, inline=False)
    if streak > 0:
        embed.add_field(name="連続", value=f"{streak}回\n×{get_multiplier(streak):.1f}", inline=True)
    if not is_free:
        embed.add_field(name="賭け", value=f"{bet}P", inline=True)
        embed.add_field(name="変動", value=f"{change:+d}P", inline=True)
        embed.add_field(name="合計", value=f"{total}P", inline=True)
    await channel.send(embed=embed)

games = {}

class HighLowGameView(discord.ui.View):
    def __init__(self, uid, bet, is_free=False):
        super().__init__(timeout=180)  # ゲーム中は3分でタイムアウト
        self.user_id = uid
        self.bet = bet
        self.is_free = is_free
        self.deck = create_deck()
        self.first_card = self.deck.pop()
        self.streak = 0
        games[uid] = self

    def disable_all_items(self):
        for c in self.children:
            if isinstance(c, discord.ui.Button): c.disabled = True

    async def end_game(self):
        if self.user_id in games: del games[self.user_id]

    async def show_choice_ui(self, itx):
        mode = "🍀 お試し" if self.is_free else f"賭け：{self.bet}P"
        if self.streak > 0: mode += f"\n🔥{self.streak}連続 ×{get_multiplier(self.streak):.1f}"
        embed = discord.Embed(title="📈 ハイ＆ロー", description=mode, color=0x3498DB)
        embed.add_field(name="現在のカード", value=f"**{card_value(self.first_card[1])}**", inline=False)
        await itx.response.edit_message(embed=embed, view=self)

    async def process_result(self, itx, choice, next_card):
        v1 = card_value(self.first_card[1])
        v2 = card_value(next_card[1])
        won = v2 > v1 if choice=="high" else v2 < v1
        if v2 == v1:
            await send_result_embed(itx.client, itx.user, self.first_card, next_card, choice, "⚖️ 引き分け", 0, self.bet, get_points(self.user_id) if not self.is_free else 0, self.streak, self.is_free)
            self.first_card = next_card
            await self.show_choice_ui(itx)
            return
        if won:
            self.streak += 1
            await send_result_embed(itx.client, itx.user, self.first_card, next_card, choice, f"🎉 当たり！×{get_multiplier(self.streak):.1f}", 0, self.bet, get_points(self.user_id) if not self.is_free else 0, self.streak, self.is_free)
            self.first_card = next_card
            await self.show_choice_ui(itx)
        else:
            await self.end_game()
            change = -self.bet if not self.is_free else 0
            total = 0 if self.is_free else add_points(self.user_id, change)
            self.disable_all_items()
            embed = discord.Embed(title="📈 ハイ＆ロー", description="🍀 お試し" if self.is_free else f"賭け：{self.bet}P", color=0xE74C3C)
            embed.add_field(name="1枚目", value=f"{v1}", inline=True)
            embed.add_field(name="2枚目", value=f"{v2}", inline=True)
            embed.add_field(name="結果", value="💔 ハズレ…没収", inline=False)
            if not self.is_free:
                embed.add_field(name="変動", value=f"{change:+d}P", inline=True)
                embed.add_field(name="所持P", value=f"{total}P", inline=True)
            await itx.response.edit_message(embed=embed, view=self)
            await send_result_embed(itx.client, itx.user, self.first_card, next_card, choice, "💔 ハズレ", change, self.bet, total, 0, self.is_free)

    @discord.ui.button(label="📈 ハイ", style=discord.ButtonStyle.primary, row=0)
    async def high_btn(self, itx, btn):
        if itx.user.id != self.user_id:
            await itx.response.send_message("❌ 自分のゲームではありません", ephemeral=True)
            return
        await self.process_result(itx, "high", self.deck.pop())

    @discord.ui.button(label="📉 ロー", style=discord.ButtonStyle.danger, row=0)
    async def low_btn(self, itx, btn):
        if itx.user.id != self.user_id:
            await itx.response.send_message("❌ 自分のゲームではありません", ephemeral=True)
            return
        await self.process_result(itx, "low", self.deck.pop())

    @discord.ui.button(label="💰 確定", style=discord.ButtonStyle.success, row=1)
    async def cashout(self, itx, btn):
        if itx.user.id != self.user_id:
            await itx.response.send_message("❌ 自分のゲームではありません", ephemeral=True)
            return
        if self.streak == 0:
            await itx.response.send_message("❌ まだ当たっていません", ephemeral=True)
            return
        await self.end_game()
        mult = get_multiplier(self.streak)
        amount = int(self.bet * mult)
        change = amount if not self.is_free else 0
        total = 0 if self.is_free else add_points(self.user_id, change)
        self.disable_all_items()
        embed = discord.Embed(title="📈 配当確定！", description="🍀 お試し" if self.is_free else f"賭け：{self.bet}P", color=0xF1C40F)
        embed.add_field(name=f"{self.streak}連続", value=f"×{mult:.1f}", inline=True)
        embed.add_field(name="確定額", value=f"+{amount}P", inline=True)
        if not self.is_free:
            embed.add_field(name="所持P", value=f"{total}P", inline=True)
        await itx.response.edit_message(embed=embed, view=self)
        await send_result_embed(itx.client, itx.user, self.first_card, None, "cashout", f"✅ {self.streak}回連続！×{mult:.1f}→{amount}P", change, self.bet, total, self.streak, self.is_free, True)

class HighLowPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永久有効

    @discord.ui.button(
        label="🔍 途中のゲーム",
        style=discord.ButtonStyle.secondary,
        custom_id="hl:resume",
        row=0
    )
    async def resume(self, itx, btn):
        g = games.get(itx.user.id)
        if not g:
            await itx.response.send_message("❌ 進行中のゲームはありません", ephemeral=True)
            return
        mode = "🍀 お試し" if g.is_free else f"賭け：{g.bet}P"
        if g.streak > 0: mode += f" | {g.streak}連続 ×{get_multiplier(g.streak):.1f}"
        embed = discord.Embed(title="📈 ハイ＆ロー【途中再開】", description=mode, color=0x3498DB)
        embed.add_field(name="現在のカード", value=f"**{card_value(g.first_card[1])}**", inline=False)
        await itx.response.send_message(embed=embed, view=g, ephemeral=True)

    @discord.ui.button(
        label="💳 ポイント確認",
        style=discord.ButtonStyle.success,
        custom_id="hl:check_points",
        row=1
    )
    async def check_points(self, itx, btn):
        pts = get_points(itx.user.id)
        await itx.response.send_message(f"💳 あなたのポイント：**{pts}P**", ephemeral=True)

    @discord.ui.button(
        label="🍀 お試し",
        style=discord.ButtonStyle.secondary,
        custom_id="hl:free",
        row=2
    )
    async def free(self, itx, btn):
        await start_game(itx, 0, True)

    @discord.ui.button(
        label="💳 1P",
        style=discord.ButtonStyle.primary,
        custom_id="hl:1",
        row=3
    )
    async def p1(self, itx, btn):
        await start_game(itx, 1)

    @discord.ui.button(
        label="💳 10P",
        style=discord.ButtonStyle.primary,
        custom_id="hl:10",
        row=3
    )
    async def p10(self, itx, btn):
        await start_game(itx, 10)

    @discord.ui.button(
        label="💳 50P",
        style=discord.ButtonStyle.primary,
        custom_id="hl:50",
        row=4
    )
    async def p50(self, itx, btn):
        await start_game(itx, 50)

    @discord.ui.button(
        label="💳 100P",
        style=discord.ButtonStyle.danger,
        custom_id="hl:100",
        row=4
    )
    async def p100(self, itx, btn):
        await start_game(itx, 100)

async def start_game(itx, bet, is_free=False):
    pts = get_points(itx.user.id)
    if itx.user.id in games:
        await itx.response.send_message("❌ 進行中です。「🔍 途中のゲーム」から再開してください", ephemeral=True)
        return
    if not is_free and pts < bet:
        await itx.response.send_message(f"❌ ポイント不足（所持:{pts}P / 必要:{bet}P）", ephemeral=True)
        return
    view = HighLowGameView(itx.user.id, bet, is_free)
    mode = "🍀 お試し\nA=1 ～ K=13" if is_free else f"賭け：{bet}P\n📈大きい / 📉小さい\n💰確定→配当GET\nA=1 ～ K=13"
    embed = discord.Embed(title="📈 ハイ＆ロー", description=mode, color=0x3498DB)
    embed.add_field(name="最初の数字", value=f"**{card_value(view.first_card[1])}**", inline=False)
    await itx.response.send_message(embed=embed, view=view, ephemeral=True)

# ✅ 引数をbot=Noneに統一
async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None and not hasattr(bot, "_highlow_registered"):
        bot.add_view(HighLowPanelView())
        bot._highlow_registered = True
        print("✅ highlow_panel 永続View登録完了")

    @tree.command(name="ハイローパネル設置", description="ハイローパネル設置（オーナー専用）")
    async def cmd(itx):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用コマンドです", ephemeral=True)
            return
        embed = discord.Embed(
            title="📈 ハイ＆ロー",
            description="""🔍 途中のゲーム → 消しても再表示
💳 ポイント確認 → 現在のポイントを表示
🍀 お試し → 無料プレイ
💳 1P/10P/50P/100P → ポイントで対戦
A=1 ～ K=13 の数字で勝負！""",
            color=0x3498DB
        )
        await itx.response.send_message(embed=embed, view=HighLowPanelView())
        await itx.followup.send("✅ 設置完了", ephemeral=True)
