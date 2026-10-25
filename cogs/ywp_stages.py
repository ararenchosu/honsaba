import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime
from cogs.ywp_auto import Client

# ============================================================
# データ管理
# ============================================================
DATA_DIR = "data"
SESSION_FILE = f"{DATA_DIR}/sessions.json"
LEARNED_RULES_FILE = f"{DATA_DIR}/learned_rules.json"
os.makedirs(DATA_DIR, exist_ok=True)

def load_sessions() -> dict:
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def load_learned_rules() -> dict:
    """学習済みの分類ルールを読み込み"""
    if not os.path.exists(LEARNED_RULES_FILE):
        return {
            "prefix_map": {},
            "stats": {}
        }
    try:
        with open(LEARNED_RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"prefix_map": {}, "stats": {}}

def save_learned_rule(prefix: str, category: str):
    """新しいルールを学習・保存"""
    rules = load_learned_rules()
    rules["prefix_map"][prefix] = category
    rules["stats"][prefix] = {
        "category": category,
        "learned_at": datetime.now().isoformat()
    }
    with open(LEARNED_RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

# ============================================================
# 自動分類エンジン
# ============================================================
class AutoClassifier:
    def __init__(self):
        # 基本ルール：最初の1回だけ使用、以降は自動学習が優先
        self.base_rules = {
            "100": "📖 メインステージ",
            "190": "📖 メイン（2章以降）",
            "500": "🎯 サブステージ",
            "900": "🎪 イベントステージ",
            "288": "💪 強敵ステージ",
            "289": "💪 強敵ステージ",
            "290": "🌙 夜叉ステージ",
        }
        # 学習済みルールを読み込み
        self.learned = load_learned_rules()["prefix_map"]

    def guess_category(self, sid: int) -> str:
        """IDから自動的にカテゴリを判定 — 学習済み優先"""
        s = str(sid)
        prefix3 = s[:3] if len(s) >= 3 else s
        prefix4 = s[:4] if len(s) >= 4 else s

        # 1. 学習済み4桁一致
        if prefix4 in self.learned:
            return self.learned[prefix4]
        # 2. 学習済み3桁一致
        if prefix3 in self.learned:
            return self.learned[prefix3]
        # 3. 基本ルールで判定
        if prefix3 in self.base_rules:
            return self.base_rules[prefix3]
        # 4. 未知 → パターンを記録して仮分類
        self._record_unknown(prefix4, sid)
        return f"❓ 新規:{prefix4}"

    def _record_unknown(self, prefix: str, sid: int):
        """未知のパターンを記録"""
        unknown_file = f"{DATA_DIR}/unknown_patterns.json"
        data = {}
        if os.path.exists(unknown_file):
            try:
                with open(unknown_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except: pass
        if prefix not in data:
            data[prefix] = {"examples": [], "first_seen": datetime.now().isoformat()}
        if len(data[prefix]["examples"]) < 5:
            data[prefix]["examples"].append(sid)
        with open(unknown_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def categorize_all(self, stage_ids: list) -> dict:
        """全IDを一括自動分類"""
        result = {}
        for sid in sorted(stage_ids):
            cat = self.guess_category(sid)
            if cat not in result:
                result[cat] = []
            result[cat].append(sid)
        return result

# 分類器をグローバル初期化
classifier = AutoClassifier()

# ============================================================
# パーサ・ヘルパー
# ============================================================
def parse_stages(stage_raw: str) -> dict:
    result = {}
    if not stage_raw:
        return result
    for row in str(stage_raw).split("*"):
        if not row: continue
        cols = row.split("|")
        if not cols: continue
        try:
            sid = int(cols[0])
            if not (1 <= sid <= 99999999): continue
            cleared = len(cols) >= 2 and cols[1] == "1"
            result[sid] = {"cleared": cleared}
        except: pass
    return result

async def safe_defer(interaction, ephemeral=True):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        return True
    except: return False

# ============================================================
# 🎮 パネルビュー — 動的ボタン
# ============================================================
class AutoStagePanel(ui.View):
    def __init__(self, stages_data, all_ids, cleared_count, total_count, show_all=False):
        super().__init__(timeout=300)
        self.stages_data = stages_data
        self.all_ids = all_ids
        self.cleared_count = cleared_count
        self.total_count = total_count
        self.show_all = show_all
        self.categorized = classifier.categorize_all(all_ids)
        # 表示順を整理
        self.display_order = self._sort_categories()
        self.current_category = self.display_order[0] if self.display_order else "なし"
        self._build_buttons()

    def _sort_categories(self) -> list:
        """カテゴリを表示順に並び替え"""
        priority = {
            "📖": 1, "🎪": 2, "🎯": 3, "💪": 4, "🌙": 5
        }
        cats = list(self.categorized.keys())
        cats.sort(key=lambda c: (priority.get(c[:2], 99), c))
        return cats

    def _build_buttons(self):
        """カテゴリから自動的にボタンを生成"""
        self.clear_items()
        for cat_name in self.display_order:
            count = len(self.categorized[cat_name])
            is_active = cat_name == self.current_category
            btn = ui.Button(
                label=f"{cat_name} ({count})",
                style=discord.ButtonStyle.blurple if is_active else discord.ButtonStyle.secondary,
                custom_id=f"cat:{cat_name}"
            )
            btn.callback = self._make_callback(cat_name)
            self.add_item(btn)

    def _make_callback(self, cat_name):
        async def callback(interaction: discord.Interaction):
            self.current_category = cat_name
            self._build_buttons()
            await interaction.response.edit_message(embed=self._make_embed(), view=self)
        return callback

    def _make_embed(self) -> discord.Embed:
        cat_ids = self.categorized.get(self.current_category, [])
        label = "全ステージ" if self.show_all else "クリア済み"

        # 一覧を整形
        lines = []
        for i in range(0, len(cat_ids), 10):
            chunk = cat_ids[i:i+10]
            marks = []
            for sid in chunk:
                info = self.stages_data.get(sid, {})
                mark = "✅" if info.get("cleared") else "⬜"
                marks.append(f"{mark}`{sid}`")
            lines.append(" ".join(marks))

        desc = (
            f"**{label}**: {len(self.all_ids)}件  |  "
            f"**クリア済み**: {self.cleared_count}/{self.total_count}\n"
            f"**表示中**: {self.current_category} — {len(cat_ids)}件"
        )
        if "❓" in self.current_category:
            desc += "\n⚠️ 新しいパターンを検出！ → 管理者が分類追加できます"

        embed = discord.Embed(
            title="🎮 ステージ一覧（自動分類）",
            description=desc,
            color=0x5865F2,
            timestamp=datetime.now()
        )
        if lines:
            embed.add_field(name="📋 マップ番号", value="\n".join(lines)[:1024], inline=False)
        else:
            embed.add_field(name="📋 マップ番号", value="該当なし", inline=False)
        embed.set_footer(text="ボタンで切り替え｜未知のパターンは自動記録")
        return embed

# ============================================================
# Cog本体
# ============================================================
class AutoStageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ステージ一覧", description="自動分類＋ボタンパネル表示")
    @app_commands.describe(
        keyword="IDで絞り込み（任意）",
        show_all="未クリアも含めて全表示"
    )
    async def stage_list(
        self,
        interaction: discord.Interaction,
        keyword: str = "",
        show_all: bool = False
    ):
        if not await safe_defer(interaction):
            return

        # セッション確認
        sessions = load_sessions()
        sdata = sessions.get(str(interaction.user.id))
        if not sdata:
            await interaction.followup.send(
                "❌ 先に `/ywp_login` を実行してください。",
                ephemeral=True
            )
            return

        # ゲームからデータ取得
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
            await interaction.followup.send(
                f"❌ ログイン失敗: `{str(e)[:200]}`",
                ephemeral=True
            )
            return

        stage_raw = client.save.get("ywp_user_stage")
        if not stage_raw:
            await interaction.followup.send(
                "❌ `ywp_user_stage` が見つかりません。",
                ephemeral=True
            )
            return

        # データ解析
        stages = parse_stages(stage_raw)
        cleared_count = sum(1 for v in stages.values() if v["cleared"])
        total_count = len(stages)

        # 絞り込み
        if show_all:
            ids = sorted(stages.keys())
        else:
            ids = sorted([sid for sid, v in stages.items() if v["cleared"]])
        if keyword:
            ids = [sid for sid in ids if keyword in str(sid)]
        if not ids:
            await interaction.followup.send(
                "❌ 該当するステージが見つかりません。",
                ephemeral=True
            )
            return

        # パネル表示
        panel = AutoStagePanel(stages, ids, cleared_count, total_count, show_all)
        await interaction.followup.send(
            embed=panel._make_embed(),
            view=panel,
            ephemeral=True
        )

    # 🔧 新規パターンを手動で分類に追加する管理者用コマンド
    @app_commands.command(name="パターン追加", description="新しいステージパターンを分類に登録")
    @app_commands.describe(
        prefix="先頭3～4桁 例:9003",
        category="カテゴリ名 例:🎪 イベント裏ステージ"
    )
    async def add_pattern(
        self,
        interaction: discord.Interaction,
        prefix: str,
        category: str
    ):
        # 必要に応じて管理者権限制限を追加可能
        save_learned_rule(prefix, category)
        # 分類器をリロード
        global classifier
        classifier = AutoClassifier()
        await interaction.response.send_message(
            f"✅ パターン `{prefix}` → `{category}` を登録しました",
            ephemeral=True
        )

# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(AutoStageCog(bot))
