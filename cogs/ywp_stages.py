import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime
from cogs.ywp_auto import Client

# ============================================================
# データ
# ============================================================
DATA_DIR = "data"
SESSION_FILE = f"{DATA_DIR}/sessions.json"
NEW_PATTERNS_FILE = f"{DATA_DIR}/new_patterns.json"  # 新規パターン記録用

os.makedirs(DATA_DIR, exist_ok=True)

def load_sessions() -> dict:
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_new_pattern(prefix: str, example_id: int):
    """新しいパターンを記録"""
    patterns = {}
    if os.path.exists(NEW_PATTERNS_FILE):
        try:
            with open(NEW_PATTERNS_FILE, "r", encoding="utf-8") as f:
                patterns = json.load(f)
        except: pass
    if prefix not in patterns:
        patterns[prefix] = {
            "first_seen": datetime.now().isoformat(),
            "example_id": example_id,
            "count": 1
        }
    else:
        patterns[prefix]["count"] += 1
    with open(NEW_PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

# ============================================================
# ステージ分類ルール（先頭4桁で判定）
# ============================================================
CATEGORY_MAP = {
    # メインステージ
    "1001": "📖 メインステージ",
    "1002": "📖 メインステージ",
    "1003": "📖 メインステージ",
    # メイン2章以降
    "1901": "📖 メイン（2章以降）",
    # サブステージ
    "5001": "🎯 サブステージ",
    "5002": "🎯 サブステージ",
    "5003": "🎯 サブステージ",
    "5004": "🎯 サブステージ",
    "5005": "🎯 サブステージ",
    "5006": "🎯 サブステージ",
    "5007": "🎯 サブステージ",
    "5008": "🎯 サブステージ",
    "5009": "🎯 サブステージ",
    "5010": "🎯 サブステージ",
    "5011": "🎯 サブステージ",
    # イベント
    "9002": "🎪 イベントステージ",
    # 強敵
    "2880": "💪 強敵ステージ",
    "2890": "💪 強敵ステージ",
    # 夜叉
    "2900": "🌙 夜叉ステージ",
}

def categorize_stages(stage_ids: list) -> dict:
    """ステージIDを自動分類 — 未知のパターンは記録して「その他」へ"""
    result = {}
    for sid in sorted(stage_ids):
        s = str(sid)
        prefix4 = s[:4] if len(s) >= 4 else s
        
        # 登録済みパターンで判定
        if prefix4 in CATEGORY_MAP:
            cat_name = CATEGORY_MAP[prefix4]
        else:
            # 未知のパターン → 記録してその他へ
            save_new_pattern(prefix4, sid)
            cat_name = "❓ その他（新規パターン検出）"
        
        if cat_name not in result:
            result[cat_name] = []
        result[cat_name].append(sid)
    
    return result

# ============================================================
# 3秒対策
# ============================================================
async def safe_defer(interaction: discord.Interaction, ephemeral: bool = True, thinking: bool = True) -> bool:
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False

async def safe_reply(interaction: discord.Interaction, **kwargs):
    try:
        if interaction.response.is_done():
            return await interaction.followup.send(**kwargs)
        else:
            return await interaction.response.send_message(**kwargs)
    except (discord.NotFound, discord.HTTPException):
        pass

# ============================================================
# ステージパーサ
# ============================================================
def parse_stages(stage_raw: str) -> dict:
    result = {}
    if not stage_raw:
        return result
    for row in str(stage_raw).split("*"):
        if not row:
            continue
        cols = row.split("|")
        if not cols:
            continue
        try:
            sid = int(cols[0])
            if not (1 <= sid <= 99999999):
                continue
            cleared = len(cols) >= 2 and cols[1] == "1"
            result[sid] = {"cols": cols, "cleared": cleared}
        except (ValueError, IndexError):
            pass
    return result

# ============================================================
# Cog
# ============================================================
class YWPStages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ステージ一覧", description="クリア済みステージIDを分類別に表示")
    @app_commands.describe(
        keyword="検索キーワード（任意）",
        show_all="未クリアも含めて全部表示"
    )
    async def ywp_stages(
        self,
        interaction: discord.Interaction,
        keyword: str = "",
        show_all: bool = False
    ):
        if not await safe_defer(interaction):
            return

        sessions = load_sessions()
        sdata = sessions.get(str(interaction.user.id))
        if not sdata:
            return await safe_reply(
                interaction,
                content="❌ ログインしていません。先に `/ywp_login` を実行してください。",
                ephemeral=True
            )

        client = Client(sdata["udkey"])
        client.gdkey = sdata["gdkey"]
        client.userId = sdata["userId"]
        client.token = sdata["token"]
        client.mst = sdata.get("mst", 16897)

        try:
            await asyncio.to_thread(client.login, sdata["userId"])
            sessions[str(interaction.user.id)]["token"] = client.token
            sessions[str(interaction.user.id)]["mst"] = client.mst
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return await safe_reply(
                interaction,
                content=f"❌ ログイン再実行失敗: `{str(e)[:200]}`",
                ephemeral=True
            )

        stage_raw = client.save.get("ywp_user_stage")
        if not stage_raw:
            return await safe_reply(
                interaction,
                content="❌ `ywp_user_stage` が見つかりません。",
                ephemeral=True
            )

        stages = parse_stages(stage_raw)

        # フィルタリング
        if not show_all:
            ids = sorted([sid for sid, info in stages.items() if info["cleared"]])
            label = "クリア済み"
        else:
            ids = sorted(stages.keys())
            label = "全ステージ"

        if keyword:
            kw = keyword.strip()
            ids = [sid for sid in ids if kw in str(sid)]

        if not ids:
            return await safe_reply(
                interaction,
                content=f"❌ `{label}` に一致するステージIDがありません。",
                ephemeral=True
            )

        # 自動分類
        categorized = categorize_stages(ids)

        # メッセージ分割
        chunks = []
        current = ""
        for cat_name, cat_ids in categorized.items():
            header = f"\n**{cat_name}** ({len(cat_ids)}件)\n"
            body_lines = []
            for i in range(0, len(cat_ids), 10):
                c = cat_ids[i:i+10]
                body_lines.append(" ".join(f"`{sid}`" for sid in c))
            section = header + "\n".join(body_lines) + "\n"
            if len(current) + len(section) > 1900:
                chunks.append(current)
                current = section
            else:
                current += section
        if current:
            chunks.append(current)

        cleared_count = sum(1 for i in stages.values() if i["cleared"])
        total_count = len(stages)

        # 新規パターンがある場合
        new_pattern_note = ""
        if "❓ その他（新規パターン検出）" in categorized:
            new_pattern_note = "\n⚠️ 未登録のIDパターンが検出されました → `data/new_patterns.json` に記録済み"

        embed = discord.Embed(
            title=f"🎮 {label}ステージ一覧",
            description=(
                f"**表示**: {len(ids)}件\n"
                f"**クリア済み**: {cleared_count}件 / 全{total_count}件\n"
                f"**検索**: {keyword if keyword else '（なし）'}\n"
                f"**使い方**: `/ywp_farm stage:<ID> count:<回数>`"
                f"{new_pattern_note}"
            ),
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.add_field(name="📋 分類", value=chunks[0][:1024], inline=False)
        embed.set_footer(text="show_all:True で未クリアも表示 | 新規パターンは自動記録")

        await safe_reply(interaction, embed=embed, ephemeral=True)
        for chunk in chunks[1:]:
            try:
                await interaction.followup.send(chunk, ephemeral=True)
            except Exception:
                break

# ============================================================
# setup
# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(YWPStages(bot))
