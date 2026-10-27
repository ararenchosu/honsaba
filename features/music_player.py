import asyncio
import os
import discord
import yt_dlp
from discord import app_commands, ui
from discord.ext import commands
from googleapiclient.discovery import build

# 設定を環境変数から直接取得
def get_env(name, default=None):
    return os.getenv(name, default)

YOUTUBE_API_KEY = get_env("YOUTUBE_API_KEY")
FFMPEG_PATH = get_env("FFMPEG_Path", "ffmpeg")
MUSIC_PATH = get_env("MUSIC_PATH", "./music")

os.makedirs(MUSIC_PATH, exist_ok=True)


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_list = []
        self.current_player = None
        self.is_playing = False

    async def youtube_search(self, query):
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.search().list(
            q=query, part='snippet', type='video', maxResults=5
        )
        response = request.execute()
        return response.get('items', [])

    async def download_audio(self, url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{MUSIC_PATH}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            thumb = info.get('thumbnail', '')
            if not thumb and 'thumbnails' in info:
                thumb = info['thumbnails'].get('high', {}).get('url', '')
            return {
                'title': info['title'],
                'path': f"{MUSIC_PATH}/{info['id']}.{info['ext']}",
                'duration': info.get('duration', 0),
                'url': url,
                'thumbnail': thumb
            }

    async def play_next(self, interaction=None):
        if not self.music_list:
            self.is_playing = False
            embed = discord.Embed(title="✅ 再生リストが空になりました", color=0x2ecc71)
            if interaction:
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.send(embed=embed)
            return

        self.is_playing = True
        track = self.music_list.pop(0)
        guild_voice = interaction.guild.voice_client if interaction else None

        def after_play(err):
            if track['path'] and os.path.exists(track['path']):
                try: os.remove(track['path'])
                except: pass
            asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.bot.loop)

        if guild_voice:
            audio = discord.FFmpegPCMAudio(executable=FFMPEG_PATH, source=track['path'])
            guild_voice.play(audio, after=after_play)
            self.current_player = track

            embed = discord.Embed(title="▶️ 再生中", description=f"**{track['title']}**", color=0x2ecc71)
            if track.get('thumbnail'):
                embed.set_thumbnail(url=track['thumbnail'])
            embed.add_field(name="長さ", value=f"{track['duration']//60}:{track['duration']%60:02d}", inline=True)
            embed.add_field(name="残り", value=f"{len(self.music_list)}曲", inline=True)

            if interaction and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed)
            elif interaction:
                await interaction.send(embed=embed)

    # ========== 検索モーダル ==========
    class SearchModal(ui.Modal, title="🎵 曲を検索"):
        keyword = ui.TextInput(label="検索キーワード", placeholder="曲名・アーティスト名", max_length=100)
        def __init__(self, cog, parent_view):
            super().__init__()
            self.cog = cog
            self.parent_view = parent_view
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer()
            results = await self.cog.youtube_search(str(self.keyword))
            if not results:
                return await interaction.followup.send("❌ 見つかりませんでした", ephemeral=True)
            view = self.cog.SearchResultSelect(self.cog, results, self.parent_view)
            embed = discord.Embed(title=f"🔍 「{self.keyword}」 検索結果", color=0x3498db)
            for idx, item in enumerate(results):
                snippet = item['snippet']
                embed.add_field(name=f"{idx+1}. {snippet['title'][:40]}", value=f"📺 {snippet['channelTitle']}", inline=False)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ========== 検索結果選択パネル ==========
    class SearchResultSelect(ui.View):
        def __init__(self, cog, results, parent_view):
            super().__init__(timeout=120)
            self.cog = cog
            self.results = results
            self.parent_view = parent_view
            for idx, item in enumerate(results):
                snippet = item['snippet']
                video_id = item['id']['videoId']
                title = snippet['title'][:35]
                thumb = snippet['thumbnails']['high']['url']
                btn = ui.Button(label=f"{idx+1}. {title}", style=discord.ButtonStyle.primary)
                btn.callback = self.make_callback(video_id, title, thumb)
                self.add_item(btn)
        def make_callback(self, video_id, title, thumb):
            async def callback(interaction: discord.Interaction):
                await interaction.response.defer()
                url = f"https://www.youtube.com/watch?v={video_id}"
                msg = await interaction.followup.send(f"⬇️ `{title}` をダウンロード中...", ephemeral=True)
                try:
                    track = await self.cog.download_audio(url)
                    self.cog.music_list.append(track)
                    embed = discord.Embed(title="✅ 追加完了", description=f"**{track['title']}**", color=0x2ecc71)
                    embed.set_thumbnail(url=thumb)
                    embed.add_field(name="再生リスト", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                    await msg.edit(content="", embed=embed)
                    await self.parent_view.update_panel()
                except Exception as e:
                    await msg.edit(content=f"❌ 追加失敗: {str(e)[:100]}")
            return callback

    # ========== メインパネル ==========
    class MusicPanel(ui.View):
        def __init__(self, cog, author):
            super().__init__(timeout=None)
            self.cog = cog
            self.author = author
            self.message = None
        def make_panel_embed(self):
            embed = discord.Embed(title="🎵 音楽再生パネル", color=0x3498db)
            if self.cog.current_player:
                embed.add_field(name="▶️ 再生中", value=f"**{self.cog.current_player['title']}**", inline=False)
                if self.cog.current_player.get('thumbnail'):
                    embed.set_thumbnail(url=self.cog.current_player['thumbnail'])
            else:
                embed.add_field(name="状態", value="停止中", inline=False)
            embed.add_field(name="📋 待機中", value=f"{len(self.cog.music_list)}曲", inline=True)
            return embed
        async def update_panel(self):
            if self.message:
                await self.message.edit(embed=self.make_panel_embed())
        @ui.Button(label="🔍 曲を検索", style=discord.ButtonStyle.blurple, row=0)
        async def search_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ あなたの操作ではありません", ephemeral=True)
            await interaction.response.send_modal(MusicPlayerCog.SearchModal(self.cog, self))
        @ui.Button(label="📋 内容更新", style=discord.ButtonStyle.secondary, row=0)
        async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            await self.update_panel()
            await interaction.followup.send("✅ 更新しました", ephemeral=True)
        @ui.Button(label="▶️ 再生", style=discord.ButtonStyle.success, row=1)
        async def play_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            if not interaction.guild.voice_client:
                if interaction.user.voice:
                    await interaction.user.voice.channel.connect()
                else:
                    return await interaction.response.send_message("❌ 先にボイスチャンネルに入ってください", ephemeral=True)
            if not self.cog.is_playing and self.cog.music_list:
                await interaction.response.defer()
                await self.cog.play_next(interaction)
                await self.update_panel()
            else:
                await interaction.response.send_message("❌ 再生する曲がありません", ephemeral=True)
        @ui.Button(label="⏸ 一時停止", style=discord.ButtonStyle.secondary, row=1)
        async def pause_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.pause()
                await interaction.response.send_message("⏸ 一時停止", ephemeral=True)
        @ui.Button(label="⏯ 再開", style=discord.ButtonStyle.secondary, row=2)
        async def resume_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.response.send_message("⏯ 再開", ephemeral=True)
        @ui.Button(label="⏭ スキップ", style=discord.ButtonStyle.primary, row=2)
        async def skip_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭ スキップしました", ephemeral=True)
                await self.update_panel()
        @ui.Button(label="⏹ 停止/切断", style=discord.ButtonStyle.danger, row=2)
        async def stop_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            interaction.guild.voice_client.stop()
            await interaction.guild.voice_client.disconnect()
            self.cog.music_list.clear()
            self.cog.is_playing = False
            self.cog.current_player = None
            await interaction.response.send_message("⏹ 停止しました", ephemeral=True)
            await self.update_panel()

    @app_commands.command(name="音楽パネル", description="🎵 音楽再生パネルを開く")
    async def music_panel(self, interaction: discord.Interaction):
        panel = self.MusicPanel(self, interaction.user)
        embed = panel.make_panel_embed()
        panel.message = await interaction.response.send_message(embed=embed, view=panel)


async def setup(bot):
    if not YOUTUBE_API_KEY:
        print("⚠️ YOUTUBE_API_KEY が未設定のため音楽プレイヤーをスキップします")
        return
    await bot.add_cog(MusicPlayerCog(bot))
