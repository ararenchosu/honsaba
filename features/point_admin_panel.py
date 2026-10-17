import discord
from discord import app_commands
import json
import os
from datetime import datetime, timedelta, timezone
from core.common import is_owner

JST = timezone(timedelta(hours=9))
DATA_FILE = "kn_points_data.json"

# ========== データ読み書き ==========
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_points(user_id: int):
    data = load_data()
    return data.get(str(user_id), 0)

def add_points(user_id: int, amount: int):
    data = load_data()
    uid = str(user_id)
    data[uid] = data.get(uid, 0) + amount
    save_data(data)
    return data[uid]

def set_points(user_id: int, amount: int):
    data = load_data()
    data[str(user_id)] = amount
    save_data(data)

# ========== ユーザー選択View（旧バージョン対応） ==========
class SelectUserView(discord.ui.View):
    def __init__(self, callback):
        super().__init__(timeout=120)
        self._callback = callback
        self.selected_user = None
        # UserSelect を直接使う
        self.add_item(
            discord.ui.UserSelect(
                placeholder="ユーザーを選択してください",
                min_values=1,
                max_values=1,
                custom_id="point_admin:select_user"
            )
        )

    async def interaction_check(self, inter: discord.Interaction) -> bool:
        self.selected_user = self.children[0].values[0]
        await self._callback(inter, self.selected_user)
        self.stop()
        return True

# ========== 管理パネル ==========
class PointAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="➕ ポイントを付与",
        style=discord.ButtonStyle.success,
        row=0,
        custom_id="point:add"
    )
    async def add_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        async def on_user_selected(inter, user):
            class AmountModal(discord.ui.Modal, title="ポイント付与"):
                amount = discord.ui.TextInput(
                    label="付与するポイント数",
                    required=True
                )
                async def on_submit(self, m_itx):
                    try:
                        val = int(self.amount.value.strip())
                    except ValueError:
                        await m_itx.response.send_message("❌ 数値を正しく入力してください", ephemeral=True)
                        return
                    now_pts = add_points(user.id, val)
                    await m_itx.response.send_message(
                        f"✅ {user.mention} に {val:,} pt 付与しました\n"
                        f"💳 現在：{now_pts:,} pt",
                        ephemeral=True
                    )
            await inter.response.send_modal(AmountModal())

        view = SelectUserView(on_user_selected)
        await itx.response.send_message(
            "対象ユーザーを選択してください",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="➖ ポイントを減算",
        style=discord.ButtonStyle.danger,
        row=0,
        custom_id="point:sub"
    )
    async def sub_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        async def on_user_selected(inter, user):
            class AmountModal(discord.ui.Modal, title="ポイント減算"):
                amount = discord.ui.TextInput(
                    label="減算するポイント数",
                    required=True
                )
                async def on_submit(self, m_itx):
                    try:
                        val = int(self.amount.value.strip())
                    except ValueError:
                        await m_itx.response.send_message("❌ 数値を正しく入力してください", ephemeral=True)
                        return
                    now_pts = add_points(user.id, -val)
                    await m_itx.response.send_message(
                        f"✅ {user.mention} から {val:,} pt 減算しました\n"
                        f"💳 現在：{now_pts:,} pt",
                        ephemeral=True
                    )
            await inter.response.send_modal(AmountModal())

        view = SelectUserView(on_user_selected)
        await itx.response.send_message(
            "対象ユーザーを選択してください",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="🔢 ポイントを設定",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="point:set"
    )
    async def set_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        async def on_user_selected(inter, user):
            class AmountModal(discord.ui.Modal, title="ポイント設定"):
                amount = discord.ui.TextInput(
                    label="設定するポイント数",
                    required=True
                )
                async def on_submit(self, m_itx):
                    try:
                        val = int(self.amount.value.strip())
                    except ValueError:
                        await m_itx.response.send_message("❌ 数値を正しく入力してください", ephemeral=True)
                        return
                    set_points(user.id, val)
                    await m_itx.response.send_message(
                        f"✅ {user.mention} のポイントを {val:,} pt に設定しました",
                        ephemeral=True
                    )
            await inter.response.send_modal(AmountModal())

        view = SelectUserView(on_user_selected)
        await itx.response.send_message(
            "対象ユーザーを選択してください",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="📊 ポイント確認",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="point:check"
    )
    async def check_btn(self, itx: discord.Interaction, btn):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用です", ephemeral=True)
            return

        async def on_user_selected(inter, user):
            pts = get_points(user.id)
            await inter.response.send_message(
                f"{user.mention} の保有ポイント：**{pts:,}** pt",
                ephemeral=True
            )

        view = SelectUserView(on_user_selected)
        await itx.response.send_message(
            "対象ユーザーを選択してください",
            view=view,
            ephemeral=True
        )

async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None and not hasattr(bot, "_point_admin_registered"):
        bot.add_view(PointAdminView())
        bot._point_admin_registered = True
        print("✅ point_admin_panel 永続View登録完了")

    @tree.command(
        name="ポイント管理パネル",
        description="ポイント付与・設定パネル（オーナー専用）"
    )
    @app_commands.check(is_owner)
    async def cmd(itx: discord.Interaction):
        embed = discord.Embed(title="💰 ポイント管理パネル", color=0xF1C40F)
        embed.description = "各ボタンから操作してください"
        await itx.response.send_message(embed=embed, view=PointAdminView())
        await itx.followup.send("✅ パネルを設置しました", ephemeral=True)
