import os
import re
import random
import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands
from googleapiclient.discovery import build
import yt_dlp

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
FFMPEG_PATH = os.getenv("FFMPEG_Path", "ffmpeg")
MUSIC_PATH = os.getenv("MUSIC_PATH", "./music")

os.makedirs(MUSIC_PATH, exist_ok=True)

# ===== あらゆるYouTube URL形式に対応 =====
VIDEO_ID_PATTERN = re.compile(r'(?:v=|/embed/|/shorts/|/live/|youtu\.be/|watch\?v=)([a-zA-Z0-9_-]{11})')
PLAYLIST_ID_PATTERN = re.compile(r'[?&]list=([a-zA-Z0-9_-]{34})')

def is_youtube_url(url):
    url = url.strip().lower()
    return 'youtube.com' in url or 'youtu.be' in url

def extract_video_id(url):
    m = VIDEO_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def extract_playlist_id(url):
    m = PLAYLIST_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def get_error_reason(err_msg):
    """エラーメッセージから分かりやすい理由に変換"""
    err = str(err_msg).lower()
    if 'sign in' in err or 'bot' in err:
        return "⚠️ YouTubeのBot判定に引っかかりました。Cookieを更新してください。"
    if 'age' in err or 'age-restricted' in err:
        return "🔞 年齢制限付き動画のため再生できません。"
    if 'not available' in err or 'unavailable' in err or 'private' in err:
        return "🚫 この動画は非公開・削除・地域制限で再生できません。"
    if 'copyright' in err or 'blocked' in err:
        return "©️ 著作権の問題でこの動画は再生できません。"
    if 'format' in err or 'requested format' in err:
        return "🎵 この動画は音声フォーマットが取得できません。別の動画をお試しください。"
    if 'live' in err:
        return "📡 ライブ配信中の動画は再生できない場合があります。"
    return f"❌ 再生できませんでした: {str(err_msg)[:80]}"


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_list = []
        self.current_title = None
        self.is_playing = False
        self.COOKIE_FILE = os.path.join(os.path.dirname(__file__), '..', 'cookies.txt')
        self.use_cookie = os.path.exists(self.COOKIE_FILE)

    async def youtube_search(self, query):
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        res = youtube.search().list(q=query, part='snippet', type='video', maxResults=5).execute()
        return res.get('items', [])

    async def get_stream_url(self, url):
        ydl_opts = {
            'format': 'bestaudio/best[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            },
            'extractor_args': {'youtube': {'player_client': ['web'], 'skip': ['dash', 'hls']}},
            'nocheckcertificate': True,
            'socket_timeout': 30,
        }
        if self.use_cookie:
            ydl_opts['cookiefile'] = self.COOKIE_FILE
        await asyncio.sleep(1.5)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # 複数候補から確実にストリームURLを取得
            stream_url = None
            if info.get('url'):
                stream_url = info['url']
            elif info.get('formats'):
                audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_formats:
                    stream_url = audio_formats[0].get('url') or audio_formats[0].get('manifest_url')
                if not stream_url:
                    all_formats = [f for f in info['formats'] if f.get('acodec') != 'none']
                    if all_formats:
                        stream_url = all_formats[0].get('url') or all_formats[0].get('manifest_url')
            
            if not stream_url:
                raise Exception("有効な音声フォーマットが見つかりません")
            
            thumb = info.get('thumbnail')
            if not thumb and info.get('thumbnails'):
                thumbs = info['thumbnails']
                if isinstance(thumbs, list):
                    thumb = thumbs[-1].get('url') if thumbs else None
                elif isinstance(thumbs, dict):
                    thumb = thumbs.get('high', {}).get('url') or thumbs.get('default', {}).get('url')
            
            return {
                'title': info['title'],
                'url': stream_url,
                'duration': info.get('duration', 0),
                'thumbnail': thumb or '',
                'video_id': info.get('id', '')
            }

    async def get_playlist_tracks(self, playlist_id):
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'extract_flat': True,
            'nocheckcertificate': True,
        }
        if self.use_cookie:
            ydl_opts['cookiefile'] = self.COOKIE_FILE
        tracks = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
            if info.get('entries'):
                for e in info['entries']:
                    if e and e.get('id'):
                        tracks.append({'id': e['id'], 'title': e.get('title', '不明')})
        return tracks

    async def play_next(self, interaction=None):
        if not self.music_list:
            self.is_playing = False
            emb = discord.Embed(title="✅ 再生リストが空になりました", color=0x2ecc71)
            if interaction:
                if hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=emb, ephemeral=True)
                else:
                    await interaction.send(embed=emb)
            return
        self.is_playing = True
        track = self.music_list.pop(0)
        vc = interaction.guild.voice_client if interaction else None
        def _after(err):
            asyncio.run_coroutine_threadsafe(self.play_next(interaction), self.bot.loop)
        if vc and not vc.is_playing():
            vc.play(discord.FFmpegPCMAudio(
                executable=FFMPEG_PATH, source=track['url'],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            ), after=_after)
            self.current_title = track['title']
            emb = discord.Embed(title="▶️ 再生中", description=f"**{track['title']}**", color=0x2ecc71)
            if track.get('thumbnail'):
                emb.set_thumbnail(url=track['thumbnail'])
            emb.add_field(name="長さ", value=f"{track['duration']//60}:{track['duration']%60:02d}", inline=True)
            emb.add_field(name="待機中", value=f"{len(self.music_list)}曲", inline=True)
            if interaction and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=emb)
            elif interaction:
                await interaction.send(embed=emb)

    class SearchModal(ui.Modal, title="🎵 曲を検索 / URL追加"):
        keyword = ui.TextInput(
            label="検索キーワード または YouTubeリンク",
            placeholder="曲名 / 動画URL / ショート / プレイリストURL",
            max_length=500
        )
        def __init__(self, cog, parent_view):
            super().__init__()
            self.cog = cog
            self.parent_view = parent_view

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            txt = str(self.keyword).strip()

            # YouTube URLか判定
            if is_youtube_url(txt):
                # プレイリスト優先
                pid = extract_playlist_id(txt)
                if pid:
                    msg = await interaction.followup.send("📋 プレイリスト取得中...", ephemeral=True)
                    try:
                        entries = await self.cog.get_playlist_tracks(pid)
                        if not entries:
                            return await msg.edit(content="❌ プレイリストが空または取得不可です")
                        added = 0
                        failed = []
                        for entry in entries:
                            try:
                                trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={entry['id']}")
                                self.cog.music_list.append(trk)
                                added += 1
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                failed.append(f"{entry['title'][:20]}: {get_error_reason(e)}")
                                continue
                        emb = discord.Embed(title="✅ プレイリスト追加完了", color=0x2ecc71)
                        emb.add_field(name="追加成功", value=f"{added}/{len(entries)}曲", inline=True)
                        if failed:
                            emb.add_field(name="⚠️ 再生できなかった曲", value="\n".join(failed[:5]), inline=False)
                        await msg.edit(content="", embed=emb)
                        await self.parent_view.update_panel()
                    except Exception as e:
                        await msg.edit(content=get_error_reason(e))
                    return

                # 動画ID
                vid = extract_video_id(txt)
                if vid:
                    msg = await interaction.followup.send("⬇️ 情報取得中...", ephemeral=True)
                    try:
                        trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                        self.cog.music_list.append(trk)
                        emb = discord.Embed(title="✅ 追加完了", description=f"**{trk['title']}**", color=0x2ecc71)
                        if trk.get('thumbnail'):
                            emb.set_thumbnail(url=trk['thumbnail'])
                        emb.add_field(name="再生リスト", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                        await msg.edit(content="", embed=emb)
                        await self.parent_view.update_panel()
                    except Exception as e:
                        await msg.edit(content=get_error_reason(e))
                    return

                return await interaction.followup.send(
                    "❌ YouTube URLの形式が正しくありません。\n動画・ショート・プレイリストのURLを貼ってください。",
                    ephemeral=True
                )

            # 通常キーワード検索
            results = await self.cog.youtube_search(txt)
            if not results:
                return await interaction.followup.send("❌ 見つかりませんでした", ephemeral=True)
            view = MusicPlayerCog.SearchResultSelect(self.cog, results, self.parent_view)
            emb = discord.Embed(title=f"🔍 「{txt}」 検索結果", color=0x3498db)
            for i, item in enumerate(results):
                emb.add_field(name=f"{i+1}. {item['snippet']['title'][:40]}", value=f"📺 {item['snippet']['channelTitle']}", inline=False)
            await interaction.followup.send(embed=emb, view=view, ephemeral=True)

    class SearchResultSelect(ui.View):
        def __init__(self, cog, results, parent_view):
            super().__init__(timeout=120)
            self.cog = cog
            self.results = results
            self.parent_view = parent_view
            for i, item in enumerate(results):
                vid = item['id']['videoId']
                title = item['snippet']['title'][:35]
                thumb = item['snippet']['thumbnails']['high']['url']
                btn = ui.Button(label=f"{i+1}. {title}", style=discord.ButtonStyle.primary)
                btn.callback = self._make_cb(vid, thumb)
                self.add_item(btn)

        def _make_cb(self, vid, thumb):
            async def cb(interaction: discord.Interaction):
                await interaction.response.defer()
                msg = await interaction.followup.send("⬇️ 情報取得中...", ephemeral=True)
                try:
                    trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                    self.cog.music_list.append(trk)
                    emb = discord.Embed(title="✅ 追加完了", description=f"**{trk['title']}**", color=0x2ecc71)
                    emb.set_thumbnail(url=thumb)
                    emb.add_field(name="再生リスト", value=f"計 {len(self.cog.music_list)}曲", inline=True)
                    await msg.edit(content="", embed=emb)
                    await self.parent_view.update_panel()
                except Exception as e:
                    await msg.edit(content=get_error_reason(e))
            return cb

    class MusicPanel(ui.View):
        def __init__(self, cog, author):
            super().__init__(timeout=None)
            self.cog = cog
            self.author = author
            self.message = None

        def make_embed(self):
            emb = discord.Embed(title="🎵 音楽再生パネル", color=0x3498db)
            if self.cog.current_title:
                emb.add_field(name="▶️ 再生中", value=f"**{self.cog.current_title}**", inline=False)
            else:
                emb.add_field(name="状態", value="停止中", inline=False)
            cookie_status = "🍪有効" if self.cog.use_cookie else "⚠️なし"
            emb.add_field(name="📋 待機中", value=f"{len(self.cog.music_list)}曲\nCookie: {cookie_status}", inline=True)
            emb.add_field(
                name="💡 使い方",
                value="🔍 曲を検索にリンクを入れても検索できます。\nYouTubeのみ対応（動画・ショート・プレイリスト）。",
                inline=False
            )
            return emb

        async def update_panel(self):
            if self.message:
                await self.message.edit(embed=self.make_embed())

        @ui.button(label="🔍 曲を検索", style=discord.ButtonStyle.blurple, row=0)
        async def search_btn(self, interaction, btn):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            await interaction.response.send_modal(MusicPlayerCog.SearchModal(self.cog, self))

        @ui.button(label="📋 更新", style=discord.ButtonStyle.secondary, row=0)
        async def ref_btn(self, interaction, btn):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            await self.update_panel()
            await interaction.followup.send("✅ 更新", ephemeral=True)

        @ui.button(label="▶️ 再生", style=discord.ButtonStyle.success, row=1)
        async def play_btn(self, interaction, btn):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            if not interaction.guild.voice_client:
                if interaction.user.voice:
                    await interaction.user.voice.channel.connect()
                else:
                    return await interaction.response.send_message("❌ 先にVCに入ってください", ephemeral=True)
            if not self.cog.is_playing and self.cog.music_list:
                await interaction.response.defer(ephemeral=True)
                await self.cog.play_next(interaction)
                await self.update_panel()
            else:
                await interaction.response.send_message("❌ 再生する曲がありません", ephemeral=True)

        @ui.button(label="⏸ 一時停止", style=discord.ButtonStyle.secondary, row=1)
        async def pause_btn(self, interaction, btn):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.pause()
                await interaction.response.send_message("⏸ 一時停止", ephemeral=True)

        @ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.secondary, row=1)
        async def shuffle_btn(self, interaction, btn):
            if interaction.user.id != self.author.id:
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            if len(self.cog.music_list) < 2:
                return await interaction.response.send_message("❌ シャッフルする曲が2曲以上必要です", ephemeral=True)
            random.shuffle(self.cog.music_list)
            await interaction.response.send_message(f"🔀 シャッフル完了！（{len(self.cog.music_list)}曲）", ephemeral=True)
            await self.update_panel()

        @ui.button(label="⏯ 再開", style=discord.ButtonStyle.secondary, row=2)
        async def res_btn(self, interaction, btn):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.response.send_message("⏯ 再開", ephemeral=True)

        @ui.button(label="⏭ スキップ", style=discord.ButtonStyle.primary, row=2)
        async def skip_btn(self, interaction, btn):
            if interaction.user.id != self.author.id or not interaction.guild.voice_client:
                return
            if interaction.guild.voice_client.is_playing() or self.cog.music_list:
                interaction.guild.voice_client.stop()
                await interaction.response.send_message("⏭ スキップ", ephemeral=True)
                await self.update_panel()
            else:
                await interaction.response.send_message("❌ スキップする曲がありません", ephemeral=True)

        @ui.button(label="⏹ 停止/切断", style=discord.ButtonStyle.danger, row=2)
        async def stop_btn(self, interaction, btn):
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
        embed = panel.make_embed()
        panel.message = await interaction.response.send_message(embed=embed, view=panel)


async def setup(bot):
    if not YOUTUBE_API_KEY:
        print("⚠️ YOUTUBE_API_KEY が未設定のため音楽プレイヤーをスキップします")
        return
    await bot.add_cog(MusicPlayerCog(bot))
