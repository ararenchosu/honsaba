import discord
from discord import app_commands
from core.common import is_owner
import json
import os

# ========== 🔧 設定ファイル ==========
CONFIG_FILE = "elevator_config.json"
DEFAULT_CONFIG = {
    "ALWAYS_VISIBLE_CATEGORY_IDS": [
        1542788842078216295,
        1558092186602704947,
    ],
    "MEMBER_ROLE_NAME": "鯖メン",
    "FLOOR_ORDER": ["0階"],  # ✅ 順番を保持するリストを追加
    "FLOOR_CONFIG": {
        "0階": {
            "role_name": None,
            "role_id": None,
            "category_ids": [
                1542788842078216295,
                1558092186602704947,
            ]
        },
    },
    "PANEL_EMBED": {
        "title": "🏢 エレベーター",
        "description": (
            "📌 **0階**：固定カテゴリ＋💬雑談（常時表示）\n"
            "🔄 設定変更後は「パネル更新」を押してください"
        ),
        "color": 0x3498DB
    }
}

ALWAYS_VISIBLE_CATEGORY_IDS = []
MEMBER_ROLE_NAME = ""
FLOOR_ORDER = []  # ✅ 順番用
FLOOR_CONFIG = {}
PANEL_EMBED = {}

def load_config():
    global ALWAYS_VISIBLE_CATEGORY_IDS, MEMBER_ROLE_NAME, FLOOR_ORDER, FLOOR_CONFIG, PANEL_EMBED
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ALWAYS_VISIBLE_CATEGORY_IDS = data.get("ALWAYS_VISIBLE_CATEGORY_IDS", DEFAULT_CONFIG["ALWAYS_VISIBLE_CATEGORY_IDS"])
            MEMBER_ROLE_NAME = data.get("MEMBER_ROLE_NAME", DEFAULT_CONFIG["MEMBER_ROLE_NAME"])
            FLOOR_ORDER = data.get("FLOOR_ORDER", list(DEFAULT_CONFIG["FLOOR_CONFIG"].keys()))
            FLOOR_CONFIG = data.get("FLOOR_CONFIG", DEFAULT_CONFIG["FLOOR_CONFIG"])
            PANEL_EMBED = data.get("PANEL_EMBED", DEFAULT_CONFIG["PANEL_EMBED"])
        except Exception as e:
            print(f"⚠️ 設定読み込みエラー: {e}")
            set_default_config()
    else:
        set_default_config()

def set_default_config():
    global ALWAYS_VISIBLE_CATEGORY_IDS, MEMBER_ROLE_NAME, FLOOR_ORDER, FLOOR_CONFIG, PANEL_EMBED
    ALWAYS_VISIBLE_CATEGORY_IDS = DEFAULT_CONFIG["ALWAYS_VISIBLE_CATEGORY_IDS"]
    MEMBER_ROLE_NAME = DEFAULT_CONFIG["MEMBER_ROLE_NAME"]
    FLOOR_ORDER = list(DEFAULT_CONFIG["FLOOR_CONFIG"].keys())
    FLOOR_CONFIG = DEFAULT_CONFIG["FLOOR_CONFIG"]
    PANEL_EMBED = DEFAULT_CONFIG["PANEL_EMBED"]
    save_config()

def save_config():
    data = {
        "ALWAYS_VISIBLE_CATEGORY_IDS": ALWAYS_VISIBLE_CATEGORY_IDS,
        "MEMBER_ROLE_NAME": MEMBER_ROLE_NAME,
        "FLOOR_ORDER": FLOOR_ORDER,  # ✅ 順番も保存
        "FLOOR_CONFIG": FLOOR_CONFIG,
        "PANEL_EMBED": PANEL_EMBED,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

load_config()

def build_floor_options(selected_floor=None):
    options = []
    # ✅ FLOOR_ORDER の順番通りに表示
    for floor_name in FLOOR_ORDER:
        if floor_name not in FLOOR_CONFIG:
            continue
        info = FLOOR_CONFIG[floor_name]
        desc = "固定＋雑談が常時表示" if floor_name == "0階" else f"{len(info['category_ids'])}個のカテゴリを表示"
        options.append(discord.SelectOption(
            label=floor_name,
            description=desc,
            emoji="🏢",
            default=(floor_name == selected_floor)
        ))
    return options

def make_embed():
    return discord.Embed(
        title=PANEL_EMBED["title"],
        description=PANEL_EMBED["description"],
        color=PANEL_EMBED["color"]
    )

class EditEmbedModal(discord.ui.Modal, title="✏️ パネル内容変更"):
    def __init__(self, current_title, current_desc):
        super().__init__(timeout=None)
        self.title_input = discord.ui.TextInput(
            label="タイトル", default=current_title, max_length=100, required=True
        )
        self.desc_input = discord.ui.TextInput(
            label="説明文", default=current_desc, style=discord.TextStyle.long,
            max_length=2000, required=True
        )
        self.add_item(self.title_input)
        self.add_item(self.desc_input)
    async def on_submit(self, itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        PANEL_EMBED["title"] = self.title_input.value
        PANEL_EMBED["description"] = self.desc_input.value
        save_config()
        await itx.response.edit_message(embed=make_embed(), view=ElevatorView())
        await itx.followup.send("✅ 更新完了", ephemeral=True)

class EditFloorModal(discord.ui.Modal, title="🏢 階設定"):
    def __init__(self, floor_name=None):
        super().__init__(timeout=None)
        self.floor_name_target = floor_name
        if floor_name and floor_name in FLOOR_CONFIG:
            info = FLOOR_CONFIG[floor_name]
            name_default = floor_name
            role_default = info.get("role_name") or ""
            cats_default = "\n".join(map(str, info.get("category_ids", [])))
        else:
            name_default = role_default = cats_default = ""
        self.floor_name_input = discord.ui.TextInput(
            label="階名（例：1階）", default=name_default,
            placeholder="1階", max_length=20, required=True
        )
        self.role_input = discord.ui.TextInput(
            label="ロール名（0階の場合は空欄）", default=role_default,
            placeholder="1階入出許可証", max_length=100, required=False
        )
        self.cats_input = discord.ui.TextInput(
            label="カテゴリID（改行区切り）", default=cats_default,
            placeholder="123456789\n987654321", style=discord.TextStyle.long,
            required=bool(name_default and name_default != "0階")
        )
        if not self.cats_input.required:
            self.cats_input.label = "カテゴリID（任意・改行区切り）"
        self.add_item(self.floor_name_input)
        self.add_item(self.role_input)
        self.add_item(self.cats_input)
    async def on_submit(self, itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        new_name = self.floor_name_input.value.strip()
        role_name = self.role_input.value.strip() or None
        cats_text = self.cats_input.value.strip()
        category_ids = []
        if cats_text:
            for line in cats_text.splitlines():
                line = line.strip()
                if line.isdigit():
                    category_ids.append(int(line))
        # ✅ 名前変更時は順番リストも更新
        if self.floor_name_target and self.floor_name_target in FLOOR_CONFIG:
            if self.floor_name_target != new_name:
                idx = FLOOR_ORDER.index(self.floor_name_target)
                FLOOR_ORDER[idx] = new_name
            del FLOOR_CONFIG[self.floor_name_target]
        else:
            # ✅ 新規追加 → 末尾に追加
            FLOOR_ORDER.append(new_name)
        FLOOR_CONFIG[new_name] = {
            "role_name": role_name, "role_id": None, "category_ids": category_ids,
        }
        save_config()
        await itx.response.send_message(
            f"✅ 【{new_name}】を保存しました！\n"
            f"🔐 ロール：`{role_name or 'なし'}`\n"
            f"📂 カテゴリ：{len(category_ids)}件", ephemeral=True
        )

class ElevatorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self._floor_select.options = build_floor_options()

    @discord.ui.select(
        placeholder="🏢 行き先の階を選択してください",
        custom_id="elevator:select_floor"
    )
    async def _floor_select(self, itx: discord.Interaction, select: discord.ui.Select):
        target_floor = select.values[0]
        guild = itx.guild
        user = itx.user
        if not is_owner(itx):
            for floor_name in FLOOR_ORDER:
                if floor_name == "0階":
                    continue
                info = FLOOR_CONFIG[floor_name]
                role = None
                if info.get("role_id"):
                    role = guild.get_role(info["role_id"])
                if not role and info.get("role_name"):
                    role = discord.utils.get(guild.roles, name=info["role_name"])
                if role and role in user.roles:
                    await user.remove_roles(role)
        if target_floor == "0階":
            common_list = []
            for cid in FLOOR_CONFIG["0階"]["category_ids"]:
                cat = guild.get_channel(cid)
                common_list.append(f"✅ {cat.name if cat else f'ID:{cid}'}")
            await itx.response.send_message(
                "✅ 0階に移動しました！\n固定カテゴリ＋雑談が表示されます。\n\n"
                "📌 表示カテゴリ：\n" + "\n".join(common_list), ephemeral=True
            )
            return
        target_info = FLOOR_CONFIG[target_floor]
        if not is_owner(itx):
            target_role = None
            if target_info.get("role_id"):
                target_role = guild.get_role(target_info["role_id"])
            if not target_role and target_info.get("role_name"):
                target_role = discord.utils.get(guild.roles, name=target_info["role_name"])
            if not target_role:
                await itx.response.send_message(
                    f"❌ 「{target_info['role_name']}」ロールが見つかりません。", ephemeral=True
                )
                return
            await user.add_roles(target_role)
            role_note = f"付与ロール：`{target_role.name}`"
        else:
            role_note = "👑 オーナー：全カテゴリ表示中"
        common_list = []
        for cid in ALWAYS_VISIBLE_CATEGORY_IDS:
            cat = guild.get_channel(cid)
            common_list.append(f"✅ {cat.name if cat else f'ID:{cid}'}")
        floor_list = []
        for cid in target_info["category_ids"]:
            cat = guild.get_channel(cid)
            floor_list.append(f"✅ {cat.name if cat else f'ID:{cid}'}")
        await itx.response.send_message(
            f"✅ {target_floor} に移動しました！\n{role_note}\n\n"
            f"📌 常に表示：\n" + "\n".join(common_list) + "\n\n"
            f"📂 {target_floor}のカテゴリ：\n" + "\n".join(floor_list), ephemeral=True
        )

    @discord.ui.button(
        label="✏️ 内容変更", style=discord.ButtonStyle.secondary,
        custom_id="elevator:edit_embed", row=1
    )
    async def _edit_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        embed = itx.message.embeds[0] if itx.message.embeds else None
        current_title = embed.title if embed and embed.title else PANEL_EMBED["title"]
        current_desc = embed.description if embed and embed.description else PANEL_EMBED["description"]
        await itx.response.send_modal(EditEmbedModal(current_title, current_desc))

    @discord.ui.button(
        label="🔄 パネル更新", style=discord.ButtonStyle.primary,
        custom_id="elevator:refresh", row=1
    )
    async def _refresh_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        load_config()
        await itx.response.edit_message(embed=make_embed(), view=ElevatorView())
        await itx.followup.send("✅ パネルを更新しました！", ephemeral=True)

    @discord.ui.button(
        label="❌ 全階を閉じる", style=discord.ButtonStyle.danger,
        custom_id="elevator:clear", row=2
    )
    async def _clear_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if is_owner(itx):
            await itx.response.send_message("👑 オーナー：常に全カテゴリ表示中", ephemeral=True)
            return
        guild = itx.guild
        user = itx.user
        for floor_name in FLOOR_ORDER:
            if floor_name == "0階":
                continue
            info = FLOOR_CONFIG[floor_name]
            role = None
            if info.get("role_id"):
                role = guild.get_role(info["role_id"])
            if not role and info.get("role_name"):
                role = discord.utils.get(guild.roles, name=info["role_name"])
            if role and role in user.roles:
                await user.remove_roles(role)
        await itx.response.send_message(
            "✅ 全ての階を閉じました。\n📌 0階の状態に戻ります。", ephemeral=True
        )

class AdminFloorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.selected_floor = None
        self._update_options()

    def _update_options(self):
        self._floor_select.options = build_floor_options(self.selected_floor)

    @discord.ui.select(
        placeholder="操作する階を選択してください",
        custom_id="elevator_admin:select_floor"
    )
    async def _floor_select(self, itx: discord.Interaction, select: discord.ui.Select):
        self.selected_floor = select.values[0]
        self._update_options()
        await itx.response.edit_message(view=self)
        await itx.followup.send(f"✅ 【{self.selected_floor}】を選択しました！", ephemeral=True)

    @discord.ui.button(
        label="⬆️ 上へ移動", style=discord.ButtonStyle.secondary,
        custom_id="elevator_admin:move_up", row=1
    )
    async def _move_up_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        if not self.selected_floor:
            await itx.response.send_message("⚠️ 先に上から移動する階を選択してください", ephemeral=True)
            return
        idx = FLOOR_ORDER.index(self.selected_floor)
        if idx == 0:
            await itx.response.send_message("⚠️ 最上部です（0階は先頭固定）", ephemeral=True)
            return
        # ✅ 0階より上には移動不可
        if FLOOR_ORDER[idx-1] == "0階":
            await itx.response.send_message("⚠️ 0階より上には移動できません", ephemeral=True)
            return
        FLOOR_ORDER[idx], FLOOR_ORDER[idx-1] = FLOOR_ORDER[idx-1], FLOOR_ORDER[idx]
        save_config()
        self._update_options()
        await itx.response.edit_message(view=self)
        await itx.followup.send(f"✅ 【{self.selected_floor}】を上へ移動しました！", ephemeral=True)

    @discord.ui.button(
        label="⬇️ 下へ移動", style=discord.ButtonStyle.secondary,
        custom_id="elevator_admin:move_down", row=1
    )
    async def _move_down_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        if not self.selected_floor:
            await itx.response.send_message("⚠️ 先に上から移動する階を選択してください", ephemeral=True)
            return
        idx = FLOOR_ORDER.index(self.selected_floor)
        if idx == len(FLOOR_ORDER) - 1:
            await itx.response.send_message("⚠️ 最下部です", ephemeral=True)
            return
        FLOOR_ORDER[idx], FLOOR_ORDER[idx+1] = FLOOR_ORDER[idx+1], FLOOR_ORDER[idx]
        save_config()
        self._update_options()
        await itx.response.edit_message(view=self)
        await itx.followup.send(f"✅ 【{self.selected_floor}】を下へ移動しました！", ephemeral=True)

    @discord.ui.button(
        label="➕ 新規階追加", style=discord.ButtonStyle.success,
        custom_id="elevator_admin:add", row=2
    )
    async def _add_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        await itx.response.send_modal(EditFloorModal())

    @discord.ui.button(
        label="✏️ 選択階を編集", style=discord.ButtonStyle.primary,
        custom_id="elevator_admin:edit", row=2
    )
    async def _edit_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        if not self.selected_floor:
            await itx.response.send_message("⚠️ 先に上から編集する階を選択してください", ephemeral=True)
            return
        await itx.response.send_modal(EditFloorModal(self.selected_floor))

    @discord.ui.button(
        label="🗑️ 選択階を削除", style=discord.ButtonStyle.danger,
        custom_id="elevator_admin:delete", row=3
    )
    async def _del_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ オーナー専用", ephemeral=True)
            return
        if not self.selected_floor:
            await itx.response.send_message("⚠️ 先に上から削除する階を選択してください", ephemeral=True)
            return
        target = self.selected_floor
        if target == "0階":
            await itx.response.send_message("❌ 0階は削除できません", ephemeral=True)
            return
        if target in FLOOR_CONFIG:
            del FLOOR_CONFIG[target]
            FLOOR_ORDER.remove(target)  # ✅ 順番リストからも削除
            save_config()
            self.selected_floor = None
            self._update_options()
            await itx.response.edit_message(view=self)
            await itx.followup.send(
                f"✅ 【{target}】を削除しました！\n🔄 パネルを更新して反映してください", ephemeral=True
            )
        else:
            await itx.response.send_message("❌ 見つかりません", ephemeral=True)

    @discord.ui.button(
        label="📋 一覧再読込", style=discord.ButtonStyle.secondary,
        custom_id="elevator_admin:reload", row=3
    )
    async def _reload_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        load_config()
        self.selected_floor = None
        self._update_options()
        await itx.response.edit_message(view=self)
        await itx.followup.send("✅ 設定を再読み込みしました", ephemeral=True)

async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None:
        if not hasattr(bot, "_elevator_view_registered"):
            bot.add_view(ElevatorView())
            bot._elevator_view_registered = True
            print("✅ elevator_panel 永続View登録完了")
        if not hasattr(bot, "_elevator_admin_view"):
            bot.add_view(AdminFloorView())
            bot._elevator_admin_view = True
            print("✅ elevator_panel 管理View登録完了")

    @tree.command(name="エレベーター設置", description="🏢 階層別カテゴリ切り替えパネル")
    @app_commands.check(is_owner)
    async def cmd_panel(itx: discord.Interaction):
        load_config()
        await itx.response.send_message(embed=make_embed(), view=ElevatorView())
        await itx.followup.send("✅ 設置完了", ephemeral=True)

    @tree.command(name="エレベーターパネル管理", description="⚙️ 階の追加・編集・削除・順番変更")
    @app_commands.check(is_owner)
    async def cmd_admin(itx: discord.Interaction):
        load_config()
        embed = discord.Embed(
            title="⚙️ エレベーター管理パネル",
            description=(
                "下のリストから階を選択してから各ボタンを押してください。\n"
                "✅ 0階は常に先頭固定です\n"
                "⬆️ 上へ移動 / ⬇️ 下へ移動 → 表示順を入れ替え\n"
                "➕ 新規追加 → 新しい階を作成\n"
                "✏️ 編集 → 選択した階の設定を変更\n"
                "🗑️ 削除 → 選択した階を削除（0階は不可）"
            ),
            color=0x9B59B6
        )
        await itx.response.send_message(embed=embed, view=AdminFloorView(), ephemeral=True)
