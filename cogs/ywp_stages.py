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

# ============================================================
# 自動分類エンジン
# ============================================================
CATEGORY_RULES = {
    "100": "📖 メインステージ",
    "190": "📖 メイン（2章以降）",
    "500": "🎯 サブステージ",
    "900": "🎪 イベントステージ",
    "288": "💪 強敵ステージ",
    "289": "💪 強敵ステージ",
    "290": "🌙 夜叉ステージ",
}

def classify_stage(sid: int) -> str:
    s = str(sid)
    prefix = s[:3] if len(s) >= 3 else s
    for key, cat in CATEGORY_RULES.items():
        if s.startswith(key):
            return cat
    return f"❓ 新規:{prefix}"

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
            result[sid] = {"cleared": cleared, "category": classify_stage(sid)}
        except: pass
    return result

def export_to_file(stages: dict, user_id: int) -> str:
    """解析結果をファイル出力してパスを返す"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{EXPORT_DIR}/stages_{user_id}_{timestamp}.txt"
    
    categorized = {}
    total = len(stages)
    cleared = sum(1 for v in stages.values() if v["cleared"])
    
    for info in stages.values():
        cat = info["category"]
        if cat not in categorized:
            categorized[cat] = {"total": 0, "cleared": 0, "ids": []}
        categorized[cat]["total"] += 1
        if info["cleared"]:
            categorized[cat]["cleared"] += 1
        categorized[cat]["ids"].append(info)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write(f"🎮 ステージ解析結果\n")
        f.write(f"📅 実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"📊 全体: クリア済み {cleared} / {total} 件\n")
        f.write("=" * 50 + "\n\n")
        
        for cat_name, data in categorized.items():
            f.write(f"{cat_name} （{data['cleared']}/{data['total']}件）\n")
            f.write("-" * 40 + "\n")
            lines = []
            for i in range(0, len(data["ids"]), 15):
                chunk = data["ids"][i:i+15]
                line = "  ".join(
                    f"{'✅' if v['cleared'] else '⬜'}{k}"
                    for k, v in [(d, stages[d]) for d in stages if stages[d] == d]
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
        self.accounts = sessions.get(str(user_id), [])
        if not isinstance(self.accounts, list):
            self.accounts = [self.accounts] if self.accounts else []
        
        self._build_select()

    def _build_select(self):
        self.clear_items()
        if not self.accounts:
            self.add_item(ui.Button(label="ログインしてください", disabled=True))
            return
        
        # アカウント選択メニュー
        options = [
            discord.SelectOption(
                label=f"アカウント {i+1}",
                description=f"ユーザーID: {acc.get('userId', '不明')}",
                value=str(i)
            )
            for i, acc in enumerate(self.accounts)
        ]
        select = ui.Select(
            placeholder="解析するアカウントを選択",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)

        # 実行ボタン
        run_btn = ui.Button(
            label="🔍 解析を実行",
            style=discord.ButtonStyle.green
        )
        run_btn.callback = self.run_analysis
        self.add_item(run_btn)

    async def on_select(self, interaction: discord.Interaction):
        self.selected_index = int(interaction.data["values"][0])
        await interaction.response.defer()

    async def run_analysis(self, interaction: discord.Interaction):
        if not self.accounts:
            await interaction.response.send_message("❌ ログイン情報がありません", ephemeral=True)
            return
        
        acc = self.accounts[self.selected_index]
        await interaction.response.send_message(
            f"🔍 解析を開始します...\nアカウント: `{acc.get('userId', '不明')}`",
            ephemeral=True
        )
        
        # データ取得
        try:
            client = Client(acc["udkey"])
            client.gdkey = acc["gdkey"]
            client.userId = acc["userId"]
            client.token = acc["token"]
            client.mst = acc.get("mst", 16897)
            
            await asyncio.to_thread(client.login, acc["userId"])
            
            # トークン更新
            sessions = load_sessions()
            sessions[str(self.user_id)][self.selected_index]["token"] = client.token
            save_sessions(sessions)
            
            stage_raw = client.save.get("ywp_user_stage")
            if not stage_raw:
                await interaction.followup.send("❌ ステージデータが見つかりません", ephemeral=True)
                return
            
            # 解析
            stages = parse_stages(stage_raw)
            if not stages:
                await interaction.followup.send("❌ 解析できるステージがありません", ephemeral=True)
                return
            
            # ファイル出力
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
            except Exception as dm_err:
                await interaction.followup.send(
                    f"⚠️ DM送信に失敗しました。ファイルを添付します:\n"
                    f"※ プライベートチャンネルでご確認ください",
                    file=discord.File(filepath),
                    ephemeral=True
                )
            
            # 一時ファイル削除（任意）
            # os.remove(filepath)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 解析エラー: `{str(e)[:200]}`",
                ephemeral=True
            )

# ============================================================
# Cog本体
# ============================================================
class StageAnalysisCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ステージ解析", description="アカウントを選んで解析→ファイル出力")
    async def stage_analysis(self, interaction: discord.Interaction):
        sessions = load_sessions()
        user_data = sessions.get(str(interaction.user.id))
        
        if not user_data:
            await interaction.response.send_message(
                "❌ まず `/ywp_login` でログインしてください。",
                ephemeral=True
            )
            return
        
        # 単アカウントをリスト形式に正規化
        if not isinstance(user_data, list):
            sessions[str(interaction.user.id)] = [user_data]
            save_sessions(sessions)
        
        view = AccountSelectView(interaction.user.id)
        embed = discord.Embed(
            title="📋 ステージ解析パネル",
            description=f"登録済みアカウント: {len(view.accounts)} 件\n"
                        "👇 下から解析するアカウントを選び、「🔍 解析を実行」を押してください",
            color=0x5865F2
        )
        embed.set_footer(text="結果はDMにファイルで送信されます")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(StageAnalysisCog(bot))
