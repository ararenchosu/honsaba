import discord
from discord import app_commands
import random
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"
SLOT_RESULT_CHANNEL_ID = 1558766953114370158

SYMBOLS = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
# ✅ 元の数字をそれぞれ15倍に
PAYOUT = {
    ("💎", "💎", "💎"): 10 * 15,   # 10倍 → 150倍
    ("7️⃣", "7️⃣", "7️⃣"): 7 * 15,   # 7倍 → 105倍
    ("🔔", "🔔", "🔔"): 5 * 15,     # 5倍 → 75倍
    ("🍋", "🍋", "🍋"): 3 * 15,    # 3倍 → 45倍
    ("🍒", "🍒", "🍒"): 2 * 15,    # 2倍 → 30倍
    ("🍒", "🍒"): 1 * 15,          # 1倍 → 15倍
}

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"points": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"points": {}}

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

def spin_slot():
    return [random.choice(SYMBOLS) for _ in range(3)]

def calc_payout(reels, bet):
    triple = tuple(reels)
    if triple in PAYOUT:
        return bet * PAYOUT[triple], f"✨ {PAYOUT[triple]}倍！"
    if tuple(reels[:2]) in PAYOUT:
        return bet * PAYOUT[tuple(reels[:2])], f"🍒🍒 {PAYOUT[tuple(reels[:2])]}倍"
    return -bet, "💔 ハズレ"

async def send_result_embed(client, user, reels, result_text, change, total, bet):
    channel = client.get_channel(SLOT_RESULT_CHANNEL_ID)
    if not channel:
        print(f"⚠️ 結果チャンネルが見つかりません: {SLOT_RESULT_CHANNEL_ID}")
        return
    
    is_free = bet == 0
    
    embed = discord.Embed(
        title="🎰 スロット結果" if not is_free else "🎰 スロット結果（お試し）",
        description=f"{user.mention} がプレイ",
        color=0xFFD700 if change >= 0 else (0x999999 if is_free else 0x666666),
        timestamp=datetime.now(JST)
    )
    embed.add_field(name="絵柄", value=f"{reels[0]} | {reels[1]} | {reels[2]}", inline=False)
    embed.add_field(name="結果", value=result_text, inline=True)
    if bet > 0:
        embed.add_field(name="賭けP", value=f"{bet}P", inline=True)
        embed.add_field(name="変動", value=f"{change:+d}P", inline=True)
        embed.add_field(name="合計P", value=f"{total}P", inline=True)
    else:
        embed.add_field(name="備考", value="お試しモード", inline=True)
    
    embed.set_thumbnail(url=user.display_avatar.url)
    await channel.send(embed=embed)

games = {}

class SlotGameView(discord.ui.View):
    def __init__(self, user_id, bet):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.bet = bet
        games[user_id] = self

    async def end_game(self):
        if self.user_id in games:
            del games[self.user_id]

    @discord.ui.button(label="🎰 回す", style=discord.ButtonStyle.primary, row=0)
    async def spin_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if itx.user.id != self.user_id:
            await itx.response.send_message("❌ 自分のゲームではありません", ephemeral=True)
            return
        
        pts = get_points(self.user_id)
        if pts < self.bet:
            await itx.response.send_message(
                f"❌ ポイントが足りません！（所持：{pts}P / 必要：{self.bet}P）",
                ephemeral=True
            )
            await self.end_game()
            return
        
        reels = spin_slot()
        gain, result_text = calc_payout(reels, self.bet)
        new_total = add_points(self.user_id, gain) if self.bet > 0 else get_points(self.user_id)
        
        await self.end_game()
        
        await itx.response.edit_message(
            content=f"🎰 {reels[0]} | {reels[1]} | {reels[2]}\n"
                    f"{result_text}\n"
                    f"💳 合計：{new_total}P",
            view=None
        )
        await send_result_embed(itx.client, itx.user, reels, result_text, gain, new_total, self.bet)

class SlotPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ 永続化

    @discord.ui.button(
        label="🔍 途中のゲーム",
        style=discord.ButtonStyle.secondary,
        custom_id="slot:resume",
        row=0
    )
    async def resume_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        g = games.get(itx.user.id)
        if not g:
            await itx.response.send_message("❌ 進行中のゲームはありません", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎰 スロット【途中再開】",
            description=f"賭け：{g.bet}P\n下の「🎰 回す」を押してスタート！",
            color=0xFFD700
        )
        await itx.response.send_message(embed=embed, view=g, ephemeral=True)

    @discord.ui.button(
        label="💳 ポイント確認",
        style=discord.ButtonStyle.success,
        custom_id="slot:check_points",
        row=1
    )
    async def check_points_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        pts = get_points(itx.user.id)
        await itx.response.send_message(
            f"💳 {itx.user.mention} が現在持っているポイントは **{pts}P** です✨",
            ephemeral=True
        )

    @discord.ui.button(
        label="🍀 お試し",
        style=discord.ButtonStyle.secondary,
        custom_id="slot:free",
        row=2
    )
    async def free_slot(self, itx: discord.Interaction, btn: discord.ui.Button):
        reels = spin_slot()
        result_text = "🍀 お試し回転！"
        await itx.response.send_message(
            f"🎰 {reels[0]} | {reels[1]} | {reels[2]}\n{result_text}",
            ephemeral=True
        )
        await send_result_embed(itx.client, itx.user, reels, result_text, 0, get_points(itx.user.id), 0)

    @discord.ui.button(
        label="🎰 1P スロット",
        style=discord.ButtonStyle.primary,
        custom_id="slot:bet1",
        row=3
    )
    async def bet1_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await start_game(itx, 1)

    @discord.ui.button(
        label="🎰 10P スロット",
        style=discord.ButtonStyle.primary,
        custom_id="slot:bet10",
        row=3
    )
    async def bet10_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await start_game(itx, 10)

    @discord.ui.button(
        label="🎰 50P スロット",
        style=discord.ButtonStyle.primary,
        custom_id="slot:bet50",
        row=4
    )
    async def bet50_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await start_game(itx, 50)

    @discord.ui.button(
        label="🎰 100P スロット",
        style=discord.ButtonStyle.danger,
        custom_id="slot:bet100",
        row=4
    )
    async def bet100_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        await start_game(itx, 100)

async def start_game(itx, bet):
    pts = get_points(itx.user.id)
    
    if itx.user.id in games:
        await itx.response.send_message(
            "❌ ゲーム進行中です。「🔍 途中のゲーム」から再開してください",
            ephemeral=True
        )
        return
    
    if pts < bet:
        await itx.response.send_message(
            f"❌ ポイントが足りません！（所持：{pts}P / 必要：{bet}P）",
            ephemeral=True
        )
        return
    
    view = SlotGameView(itx.user.id, bet)
    embed = discord.Embed(
        title="🎰 スロットマシン",
        description=f"賭け：{bet}P\n下の「🎰 回す」を押してスタート！",
        color=0xFFD700
    )
    await itx.response.send_message(embed=embed, view=view, ephemeral=True)

# ✅ botを受け取って永続View登録
async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None and not hasattr(bot, "_slots_panel_registered"):
        bot.add_view(SlotPanelView())
        bot._slots_panel_registered = True
        print("✅ slots_panel 永続View登録完了")

    @tree.command(name="スロットパネル設置", description="スロットパネルを設置（オーナー専用）")
    async def cmd(itx):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return
        embed = discord.Embed(
            title="🎰 スロットマシン",
            description=(
                "🔍 **途中のゲーム** → 消しても再表示\n"
                "💳 **ポイント確認** → 現在の所持ポイントを表示\n"
                "🍀 **お試し** → 無料プレイ\n"
                "🎰 **1P/10P/50P/100P** → ポイントで対戦\n"
                "💎💎💎：150倍 / 7️⃣7️⃣7️⃣：105倍 / 🔔🔔🔔：75倍\n"
                "🍋🍋🍋：45倍 / 🍒🍒🍒：30倍 / 🍒🍒：15倍"
            ),
            color=0xFFD700
        )
        await itx.response.send_message(embed=embed, view=SlotPanelView())
        await itx.followup.send("✅ スロットパネル設置完了", ephemeral=True)
