import os
import re
import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands
from googleapiclient.discovery import build
import yt_dlp

# ===== 環境変数から直接取得 =====
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
FFMPEG_PATH = os.getenv("FFMPEG_Path", "ffmpeg")
MUSIC_PATH = os.getenv("MUSIC_PATH", "./music")

os.makedirs(MUSIC_PATH, exist_ok=True)

# YouTube URL/プレイリストからID抽出
YOUTUBE_PATTERNS = [
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})'),
    re.compile(r'(?:https?://)?music\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})'),
]
YOUTUBE_PLAYLIST_PATTERNS = [
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=([a-zA-Z0-9_-]{34})'),
    re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?.*list=([a-zA-Z0-9_-]{34})'),
]

def extract_video_id(url):
    url = url.strip()
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None

def extract_playlist_id(url):
    url = url.strip()
    for pattern in YOUTUBE_PLAYLIST_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_list = []
        self.current_title = None
        self.is_playing = False
        # Cookieファイルのパス
        self.COOKIE_FILE = os.path.join(os.path.dirname(__file__), '..', 'cookies.txt')
        self.use_cookie = os.path.exists(self.COOKIE_FILE)
        print(f"🍪 Cookieファイル: {'有効' if self.use_cookie else 'なし'} → {self.COOKIE_FILE}")

    async def youtube_search(self, query):
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        request = youtube.search().list(
            q=query, part='snippet', type='video', maxResults=5
        )
        response = request.execute()
        return response.get('items', [])

    async def get_stream_url(self, url):
        """ストリーミングURL取得（Cookie対応版）"""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['web'],
                    'skip': ['dash', 'hls'],
                }
            },
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'socket_timeout': 30,
        }

        if self.use_cookie:
            ydl_opts['cookiefile'] = self.COOKIE_FILE

        await asyncio.sleep(1.5)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            if not stream_url and info.get('formats'):
                stream_url = info['formats'][0].get('url')
            thumb = info.get('thumbnail', '')
            if not thumb and info.get('thumbnails'):
                thumb = info['thumbnails'].get('high', {}).get('url', '')
            return {
                'title': info['title'],
                'url': stream_url,
                'duration': info.get('duration', 0),
                'thumbnail': thumb,
                'video_id': info.get('id', '')
            }

    async def get_playlist_tracks(self, playlist_id):
        """プレイリスト内の動画を一括取得"""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
            },
            'nocheckcertificate': True,
            'ignoreerrors': True,
        }
        if self.use_cookie:
            ydl_opts['cookiefile'] = self.COOKIE_FILE

        playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        tracks = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    if entry and entry.get('id'):
                        tracks.append({
                            'id': entry['id'],
                            'title': entry.get('title', '不明')
                        })
        return tracks

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
            asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.bot.loop)

        if guild_voice and not guild_voice.is_playing():
            audio = discord.FFmpegPCMAudio(
                executable=FFMPEG_PATH,
                source=track['url'],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )
            guild_voice.play(audio, after=after_play)
            self.current_title = track['title']

            embed = discord.Embed(title="▶️ 再生中", description=f"**{track['title']}**", color=0x2ecc71)
            if track.get('thumbnail'):
                embed.set_thumbnail(url=track['thumbnail'])
            embed.add_field(name="長さ", value=f"{track['duration']//60}:{track['duration']%60:02d}", inline=True)
            embed.add_field(name="待機中", value=f"{len(self.music_list)}曲", inline=True)

            if interaction and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed)
            elif interaction:
                await interaction.send(embed=embed)

    # ========== 検索モーダル（URL/プレイリスト対応） ==========
    class SearchModal(ui.Modal, title="🎵 曲を検索 / URLを追加"):
        keyword = ui.TextInput(
            label="検索キーワード または YouTubeリンク",
            placeholder="曲名・アーティスト名 / 動画URL / プレイリストURL",
            max_length=500
        )
        def __init__(self, cog, parent_view):
            super().__init__()
            self.cog = cog
            self.parent_view = parent_view

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            input_text = str(self.keyword).strip()

            # --- プレイリストURL判定 ---
            playlist_id = extract_playlist_id(input_text)
            if playlist_id:
                msg = await interaction.followup.send(f"📋 プレイリスト取得中...", ephemeral=True)
                try:
                    entries = await self.cog.get_playlist_tracks(playlist_id)
                    if not entries:
                        return await msg.edit(content="❌ プレイリストが見つからない、または空です")
                    
                    added = 0
                    for entry in entries:
                        full_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        try:
                            track = await self.cog.get_stream_url(full_url)
                            self.cog.music_list.append(track)
                            added += 1
                            await asyncio.sleep(0.5)
                        except Exception:
                            continue
                    
                    embed = discord.Embed(title="✅ プレイリスト追加完了", color=0x2ecc71)
                    embed.add_field(name="追加した曲数", value=f"{added} / {len(entries)}曲", inline=True)
                    embed.add_field(name="再生リスト合計", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                    await msg.edit(content="", embed=embed)
                    await self.parent_view.update_panel()
                except Exception as e:
                    await msg.edit(content=f"❌ プレイリスト取得失敗: `{str(e)[:150]}`")
                return

            # --- 動画URL判定 ---
            video_id = extract_video_id(input_text)
            if video_id:
                full_url = f"https://www.youtube.com/watch?v={video_id}"
                msg = await interaction.followup.send(f"⬇️ 情報取得中...", ephemeral=True)
                try:
                    track = await self.cog.get_stream_url(full_url)
                    self.cog.music_list.append(track)
                    embed = discord.Embed(title="✅ 追加完了", description=f"**{track['title']}**", color=0x2ecc71)
                    if track.get('thumbnail'):
                        embed.set_thumbnail(url=track['thumbnail'])
                    embed.add_field(name="再生リスト", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                    await msg.edit(content="", embed=embed)
                    await self.parent_view.update_panel()
                except Exception as e:
                    await msg.edit(content=f"❌ 追加失敗: `{str(e)[:150]}`")
                return

            # --- 通常検索 ---
            results = await self.cog.youtube_search(input_text)
            if not results:
                return await interaction.followup.send("❌ 見つかりませんでした", ephemeral=True)
            view = MusicPlayerCog.SearchResultSelect(self.cog, results, self.parent_view)
            embed = discord.Embed(title=f"🔍 「{input_text}」 検索結果", color=0x3498db)
            for idx, item in enumerate(results):
                snippet = item['snippet']
                embed.add_field(name=f"{idx+1}. {snippet['title'][:40]}", value=f"📺 {snippet['channelTitle']}", inline=False)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ========== 検索結果選択 ==========
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
                btn = ui.Button(
                    label=f"{idx+1}. {title}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"add_{video_id}"
                )
                btn.callback = self._make_callback(video_id, title, thumb)
                self.add_item(btn)

        def _make_callback(self, video_id, title, thumb):
            async def callback(interaction: discord.Interaction):
                await interaction.response.defer()
                url = f"https://www.youtube.com/watch?v={video_id}"
                msg = await interaction.followup.send(f"⬇️ `{title}` 情報取得中...", ephemeral=True)
                try:
                    track = await self.cog.get_stream_url(url)
                    self.cog.music_list.append(track)
                    embed = discord.Embed(title="✅ 追加完了", description=f"**{track['title']}**", color=0x2ecc71)
                    embed.set_thumbnail(url=thumb)
                    embed.add_field(name="再生リスト", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                    await msg.edit(content="", embed=embed)
                    await self.parent_view.update_panel()
                except Exception as e:
                    await msg.edit(content=f"❌ 追加失敗: `{str(e)[:150]}`")
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
            if self.cog.current_title:
                embed.add_field(name="▶️ 再生中", value=f"**{self.cog.current_title}**", inline=False)
            else:
                embed.add_field(name="状態", value="停止中", inline=False)
            cookie_status = "🍪 有効" if self.cog.use_cookie else "⚠️ なし"
            embed.add_field(
                name="📋 待機中",
                value=f"{len(self.cog.music_list)}曲\nCookie: {cookie_status}",
                inline=True
            )
            embed.add_field(
                name="💡 使い方",
                value="🔍 曲を検索にリンクを入れても曲検索かかります。YouTubeのみ対応です。",
                inline=False
            )
            return embed

        async def update_panel(self):
            if self.message:
                await self.message.edit(embed=self.make_panel_embed())

        @ui.button(label="🔍 曲を検索", style=discord.ButtonStyle.blurple, row=0)
        async def search_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ あなたの操作ではありません", ephemeral=True)
            await interaction.response.send_modal(MusicPlayerCog.SearchModal(self.cog, self))

        @ui.button(label="📋 更新", style=discord.ButtonStyle.secondary, row=0)
        async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            await self.update_panel()
            await interaction.followup.send("✅ 更新しました", ephemeral=True)

        @ui.button(label="▶️ 再生", style=discord.ButtonStyle.success, row=1)
        async def play_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            if not interaction.guild.voice_client:
                if interaction.user.voice:
                    await interaction.user.voice.channel.connect()
                else:
                    return await interaction.response.send_message("❌ 先にボイスチャンネルに入ってください", ephemeral=True)
                            @ui.button(label="▶️ 再生", style=discord.ButtonStyle.success, row=1)
        async def play_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            if not interaction.guild.voice_client:
                if interaction.user.voice:
                    await interaction.user.voice.channel.connect()
                else:
                    return await interaction.response.send_message("❌ 先にボイスチャンネルに入ってください", ephemeral=True)
            if not self.cog.is_playing and self.cog.music_list:
                await interaction.response.defer(ephemeral=True)
                await self.cog.play_next(interaction)
                await self.update_panel()
            else:
                await interaction.response.send_message("❌ 再生する曲がありません", ephemeral=True)

        @ui.button(label="⏸ 一時停止", style=discord.ButtonStyle.secondary, row=1)
        async def pause_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.pause()
                await interaction.response.send_message("⏸ 一時停止", ephemeral=True)

        @ui.button(label="⏯ 再開", style=discord.ButtonStyle.secondary, row=2)
        async def resume_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.response.send_message("⏯ 再開", ephemeral=True)

        @ui.button(label="⏭ スキップ", style=discord.ButtonStyle.primary, row=2)
        async def skip_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing() or self.cog.music_list:
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭ スキップしました", ephemeral=True)
                await self.update_panel()
            else:
                await interaction.response.send_message("❌ スキップする曲がありません", ephemeral=True)

        @ui.button(label="⏹ 停止/切断", style=discord.ButtonStyle.danger, row=2)
        async def stop_btn(self, interaction: discord.Interaction, button: ui.Button):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            interaction.guild.voice_client.stop()
            await interaction.guild.voice_client.disconnect()
            self.cog.music_list.clear()
            self.cog.is_playing = False
            self.cog.current_title = None
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
