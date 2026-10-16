import discord
from discord import app_commands
from core.common import is_owner
import qrcode
import io

ALLOWED_MEMBER_ROLE = "鯖メン"

def is_owner_or_member(itx: discord.Interaction) -> bool:
    if is_owner(itx):
        return True
    user = itx.user
    if not isinstance(user, discord.Member):
        return False
    return any(role.name == ALLOWED_MEMBER_ROLE for role in user.roles)

def is_regular_member(itx: discord.Interaction) -> bool:
    if is_owner(itx):
        return False
    user = itx.user
    if not isinstance(user, discord.Member):
        return False
    return any(role.name == ALLOWED_MEMBER_ROLE for role in user.roles)

class InviteDurationMemberView(discord.ui.View):
    """鯖メン専用：24時間のみ"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="⏱️ 24時間",
        style=discord.ButtonStyle.primary,
        custom_id="invite:duration_24h_member"
    )
    async def day1(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner_or_member(itx):
            await itx.response.send_message(
                "❌ この機能は「鯖メン」以上のメンバーのみ使用可能です",
                ephemeral=True
            )
            return
        await self._generate(itx, max_age=86400)

    async def _generate(self, itx: discord.Interaction, max_age: int):
        invite = await itx.channel.create_invite(
            max_age=max_age,
            max_uses=0,
            unique=True
        )
        expiry_text = "24時間"
        qr_img = qrcode.make(invite.url)
        qr_img = qr_img.resize((200, 200))
        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")
        buffer.seek(0)
        qr_file = discord.File(fp=buffer, filename="qrcode.png")
        embed = discord.Embed(
            title="🔗 サーバー招待リンク",
            description="👇 リンクを押すとブラウザが開きます",
            color=0x2ECC71
        )
        embed.add_field(
            name="📋 招待リンク",
            value=f"[👉 ここを押してリンクを開く]({invite.url})\n```\n{invite.url}\n```\n⏳ 有効期限：{expiry_text}",
            inline=True
        )
        embed.set_thumbnail(url="attachment://qrcode.png")
        dm_view = discord.ui.View()
        dm_view.add_item(discord.ui.Button(
            label="🔗 ブラウザで開く",
            style=discord.ButtonStyle.link,
            url=invite.url
        ))
        dm_success = False
        try:
            await itx.user.send(embed=embed, file=qr_file, view=dm_view)
            dm_success = True
        except Exception as e:
            print(f"DM送信エラー: {e}")
        if dm_success:
            message = (
                "✅ 招待リンクをDMに送信しました！\n"
                f"⏳ 有効期限：{expiry_text}\n"
                "リンクを押す → 開く / テキスト部分をコピー どちらも可能です"
            )
        else:
            message = (
                f"⚠️ DMに送信できませんでした（{expiry_text}）\n"
                f"[👉 ここを押して開く]({invite.url})\n```\n{invite.url}\n```"
            )
        await itx.response.edit_message(content=message, view=None)

class InviteDurationOwnerView(discord.ui.View):
    """オーナー専用：全選択肢"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="♾️ 永久",
        style=discord.ButtonStyle.success,
        custom_id="invite:duration_forever"
    )
    async def forever(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ 永久リンクはオーナー専用です", ephemeral=True)
            return
        await self._generate(itx, max_age=0)

    @discord.ui.button(
        label="📅 7日",
        style=discord.ButtonStyle.primary,
        custom_id="invite:duration_7d"
    )
    async def day7(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ 7日リンクはオーナー専用です", ephemeral=True)
            return
        await self._generate(itx, max_age=604800)

    @discord.ui.button(
        label="⏱️ 24時間",
        style=discord.ButtonStyle.primary,
        custom_id="invite:duration_24h_owner"
    )
    async def day1(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner(itx):
            await itx.response.send_message("❌ この機能はオーナー専用です", ephemeral=True)
            return
        await self._generate(itx, max_age=86400)

    async def _generate(self, itx: discord.Interaction, max_age: int):
        invite = await itx.channel.create_invite(
            max_age=max_age,
            max_uses=0,
            unique=True
        )
        if max_age == 0:
            expiry_text = "永久"
        elif max_age == 86400:
            expiry_text = "24時間"
        else:
            expiry_text = "7日"
        qr_img = qrcode.make(invite.url)
        qr_img = qr_img.resize((200, 200))
        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")
        buffer.seek(0)
        qr_file = discord.File(fp=buffer, filename="qrcode.png")
        embed = discord.Embed(
            title="🔗 サーバー招待リンク",
            description="👇 リンクを押すとブラウザが開きます",
            color=0x2ECC71
        )
        embed.add_field(
            name="📋 招待リンク",
            value=f"[👉 ここを押してリンクを開く]({invite.url})\n```\n{invite.url}\n```\n⏳ 有効期限：{expiry_text}",
            inline=True
        )
        embed.set_thumbnail(url="attachment://qrcode.png")
        dm_view = discord.ui.View()
        dm_view.add_item(discord.ui.Button(
            label="🔗 ブラウザで開く",
            style=discord.ButtonStyle.link,
            url=invite.url
        ))
        dm_success = False
        try:
            await itx.user.send(embed=embed, file=qr_file, view=dm_view)
            dm_success = True
        except Exception as e:
            print(f"DM送信エラー: {e}")
        if dm_success:
            message = (
                "✅ 招待リンクをDMに送信しました！\n"
                f"⏳ 有効期限：{expiry_text}\n"
                "リンクを押す → 開く / テキスト部分をコピー どちらも可能です"
            )
        else:
            message = (
                f"⚠️ DMに送信できませんでした（{expiry_text}）\n"
                f"[👉 ここを押して開く]({invite.url})\n```\n{invite.url}\n```"
            )
        await itx.response.edit_message(content=message, view=None)

class InvitePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔗 招待リンクを生成",
        style=discord.ButtonStyle.primary,
        custom_id="invite:panel"
    )
    async def create_btn(self, itx: discord.Interaction, btn: discord.ui.Button):
        if not is_owner_or_member(itx):
            await itx.response.send_message(
                "❌ この機能は「鯖メン」以上のメンバーのみ使用可能です",
                ephemeral=True
            )
            return
        if is_regular_member(itx):
            await itx.response.send_message(
                "⏳ 24時間有効なリンクを生成します",
                view=InviteDurationMemberView(),
                ephemeral=True
            )
        else:
            await itx.response.send_message(
                "⏳ リンクの有効期限を選択してください",
                view=InviteDurationOwnerView(),
                ephemeral=True
            )

# ✅ 引数をbot=Noneに統一
async def setup(tree: app_commands.CommandTree, bot=None):
    if bot is not None and not hasattr(bot, "_invite_views_registered"):
        bot.add_view(InvitePanelView())
        bot.add_view(InviteDurationMemberView())
        bot.add_view(InviteDurationOwnerView())
        bot._invite_views_registered = True
        print("✅ invite_link 永続View登録完了")

    @tree.command(
        name="招待リンクパネル",
        description="招待リンク生成パネルを表示（オーナー専用）"
    )
    async def invite_panel_cmd(itx: discord.Interaction):
        if not is_owner(itx):
            await itx.response.send_message(
                "❌ このコマンドはオーナー専用です",
                ephemeral=True
            )
            return
        embed = discord.Embed(
            title="🔗 招待リンク生成",
            description=(
                "下のボタンを押して招待リンクを作成できます\n"
                "✅ 押して開く・テキストからコピー 両方可能\n"
                "※ サーバー側にログは残りません"
            ),
            color=0x3498DB
        )
        embed.add_field(
            name="📝 権限",
            value=(
                "👑 オーナー：永久・7日・24時間 すべて選択可\n"
                "👥 鯖メン：24時間リンクのみ生成可"
            ),
            inline=False
        )
        await itx.response.send_message(embed=embed, view=InvitePanelView())
        await itx.followup.send("✅ パネルを表示しました", ephemeral=True)
