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
EXPORT_DIR = f"{DATA_DIR}/exports"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

def load_sessions() -> dict:
    if not os.path.exists(SESSION_FILE):
        return {}
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_sessions(sessions: dict):
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

def normalize_account_list(user_data) -> list:
    if not user_data:
        return []
    if isinstance(user_data, list):
        return user_data
    return [user_data]

# ============================================================
# 🗺️ マップ名定義（IDパターン → 表示名）
# ============================================================
MAP_NAME_RULES = [
    # メインステージ
    {"prefix": "1001", "name": "📖 第1章 序章"},
    {"prefix": "1002", "name": "📖 第1章 中盤"},
    {"prefix": "1003", "name": "📖 第1章 終章"},
    {"prefix": "1901", "name": "📖 第2章 〜"},
    
    # サブステージ
    {"prefix": "5001", "name": "🎯 サブ 練習場"},
    {"prefix": "5002", "name": "🎯 サブ 森の道"},
    {"prefix": "5003", "name": "🎯 サブ 湖畔"},
    {"prefix": "5004", "name": "🎯 サブ 山岳"},
    {"prefix": "5005", "name": "🎯 サブ 洞窟"},
    {"prefix": "5006", "name": "🎯 サブ 遺跡"},
    {"prefix": "5007", "name": "🎯 サブ 砂漠"},
    {"prefix": "5008", "name": "🎯 サブ 雪原"},
    {"prefix": "5009", "name": "🎯 サブ 海岸"},
    {"prefix": "5010", "name": "🎯 サブ 空中庭園"},
    {"prefix": "5011", "name": "🎯 サブ 終末の地"},
    
    # イベントステージ
    {"prefix": "9002", "name": "🎪 期間限定イベント"},
    {"prefix": "9003", "name": "🔙 イベント 裏ステージ"},
    
    # 強敵ステージ
    {"prefix": "2880", "name": "💪 強敵 〜"},
    {"prefix": "2890", "name": "💪 最強 〜"},
    
    # 夜叉ステージ
    {"prefix": "2900", "name": "🌙 夜叉伝"},
]

def get_map_name(sid: int) -> str:
    """ステージIDからマップ名を返す"""
    s = str(sid)
    for rule in MAP_NAME_RULES:
        if s.startswith(rule["prefix"]):
            return rule["name"]
    # 未知のパターン
    return f"❓ 新規マップ:{s[:4]}"

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
            result[sid] = {
                "cleared": cleared,
                "map_name": get_map_name(sid)
            }
        except: pass
    return result

def export_to_file(stages: dict, user_id: int) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{EXPORT_DIR}/stages_{user_id}_{timestamp}.txt"
    
    # マップ名ごとにまとめる
    grouped = {}
    total = len(stages)
    cleared_count = sum(1 for v in stages.values() if v["cleared"])
    
    for sid, info in stages.items():
        name = info["map_name"]
        if name not in grouped:
            grouped[name] = {"total": 0, "cleared": 0, "ids": []}
        grouped[name]["total"] += 1
        if info["cleared"]:
            grouped[name]["cleared"] += 1
        grouped[name]["ids"].append(sid)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("🎮 ステージ解析結果\n")
        f.write(f"📅 実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"📊 全体: クリア済み {cleared_count} / {total} 件\n")
        f.write("=" * 60 + "\n\n")
        
        for map_name, data in grouped.items():
            ratio = f"{data['cleared']}/{data['total']}"
            f.write(f"{map_name} （{ratio}）\n")
            f.write("-" * 40 + "\n")
            
            lines = []
            for i in range(0, len(data["ids"]), 12):
                chunk = data["ids"][i:i+12]
                line = "  ".join(
                    f"{'✅' if stages[sid]['cleared'] else '⬜'}{sid}"
                    for sid in chunk
                )
                lines.append(line)
            
            f.write("\n".join(lines))
            f.write("\n\n")
    
    return filename

# ============================================================
# 📋 アカウント選択パネル
# ============================================================
class AccountSelectView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.selected_index = 0
        sessions = load_sessions()
        self.accounts = normalize_account_list(sessions.get(str(user_id), []))
        self._build_select()

    def _build_select(self):
        self.clear_items()
        if not self.accounts:
            self.add_item(ui.Button(label="ログインしてください", disabled=True))
            return
        
        options = [
            discord.SelectOption(
                label=f"アカウント {i+1}",
                description=f"ID: {acc.get('userId', '不明')}",
                value=str(i)
            )
            for i, acc in enumerate(self.accounts)
        ]
        select = ui.Select(placeholder="解析するアカウントを選択", options=options)
        select.callback = self.on_select
        self.add_item(select)
        
        run_btn = ui.Button(label="🔍 解析を実行", style=discord.ButtonStyle.green)
        run_btn.callback = self.run_analysis
        self.add_item(run_btn)

    async def on_select(self, interaction: discord.Interaction):
        self.selected_index = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def run_analysis(self, interaction: discord.Interaction):
        if not self.accounts:
            await interaction.followup.send("❌ ログイン情報がありません", ephemeral=True)
            return
        
        acc = self.accounts[self.selected_index]
        await interaction.followup.send(
            f"🔍 解析を開始します…\nアカウント: `{acc.get('userId', '不明')}`",
            ephemeral=True
        )
        
        try:
            # udkey を正しく取得
            udkey = acc.get("udkey") or acc.get("udkey_encoded")
            if not udkey:
                await interaction.followup.send(
                    "❌ エラー: `udkey` が見つかりません。再ログインしてください。",
                    ephemeral=True
                )
                return
            
            client = Client(udkey)
            client.gdkey = acc.get("gdkey", "")
            client.userId = acc.get("userId")
            client.token = acc.get("token", "")
            client.mst = acc.get("mst", 16897)
            
            await asyncio.to_thread(client.login, acc["userId"])
            
            # トークン更新
            sessions = load_sessions()
            sessions[str(self.user_id)][self.selected_index]["token"] = client.token
            sessions[str(self.user_id)][self.selected_index]["mst"] = client.mst
            save_sessions(sessions)
            
            stage_raw = client.save.get("ywp_user_stage")
            if not stage_raw:
                await interaction.followup.send("❌ ステージデータが見つかりません", ephemeral=True)
                return
            
            stages = parse_stages(stage_raw)
            if not stages:
                await interaction.followup.send("❌ 解析できるステージがありません", ephemeral=True)
                return
            
            filepath = export_to_file(stages, self.user_id)
            
            # DM送信
            try:
                file = discord.File(filepath, filename=os.path.basename(filepath))
                await interaction.user.send(
                    f"✅ 解析完了！\n"
                    f"📊 ステージ数: {len(stages)} 件\n"
                    f"📁 ファイル: {os.path.basename(filepath)}",
                    file=file
                )
                await interaction.followup.send(
                    "✅ 解析結果をDMに送信しました！確認してください📩",
                    ephemeral=True
                )
            except:
                await interaction.followup.send(
                    "⚠️ DM送信不可 → こちらにファイルを添付します",
                    file=discord.File(filepath),
                    ephemeral=True
                )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 解析エラー: `{str(e)[:200]}`",
                ephemeral=True
            )

# ============================================================
class StageAnalysisCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ステージ解析", description="マップ名別に解析→ファイル出力")
    async def stage_analysis(self, interaction: discord.Interaction):
        sessions = load_sessions()
        user_data = sessions.get(str(interaction.user.id))
        
        if not user_data:
            await interaction.response.send_message(
                "❌ まず `/ywp_login` でログインしてください。",
                ephemeral=True
            )
            return
        
        # リスト形式に正規化して保存
        accounts = normalize_account_list(user_data)
        if not isinstance(user_data, list):
            sessions[str(interaction.user.id)] = accounts
            save_sessions(sessions)
        
        view = AccountSelectView(interaction.user.id)
        embed = discord.Embed(
            title="📋 ステージ解析パネル",
            description=f"登録済みアカウント: {len(view.accounts)} 件\n"
                        "👇 下からアカウントを選び「🔍 解析を実行」を押してください\n"
                        "📁 結果はマップ名別に整理されDMに送信されます",
            color=0x5865F2
        )
        embed.set_footer(text="未知のマップ名は「新規マップ」として記録されます")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # 🔧 マップ名追加用コマンド
    @app_commands.command(name="マップ名追加", description="新しいマップ名を登録")
    @app_commands.describe(
        prefix="ID先頭4桁 例:9004",
        name="表示名 例:🎪 春祭りイベント"
    )
    async def add_map_name(
        self,
        interaction: discord.Interaction,
        prefix: str,
        name: str
    ):
        global MAP_NAME_RULES
        MAP_NAME_RULES.insert(0, {"prefix": prefix, "name": name})
        await interaction.response.send_message(
            f"✅ マップ名追加: `{prefix}` → `{name}`",
            ephemeral=True
        )

# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(StageAnalysisCog(bot))
