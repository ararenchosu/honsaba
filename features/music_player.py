import os
import re
import random
import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands
from googleapiclient.discovery import build
import yt_dlp

# Spotify対応（任意）
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIFY_AVAILABLE = True
except ImportError:
    SPOTIFY_AVAILABLE = False

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
FFMPEG_PATH = os.getenv("FFMPEG_Path", "ffmpeg")
MUSIC_PATH = os.getenv("MUSIC_PATH", "./music")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

os.makedirs(MUSIC_PATH, exist_ok=True)

# Spotify初期化
spotify_client = None
if SPOTIFY_AVAILABLE and SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify_client = spotipy.Spotify(auth_manager=auth_manager)
        print("✅ Spotify連携有効")
    except Exception as e:
        print(f"⚠️ Spotify連携エラー: {e}")

# URL判定
VIDEO_ID_PATTERN = re.compile(r'(?:v=|/embed/|/shorts/|/live/|youtu\.be/|watch\?v=)([a-zA-Z0-9_-]{11})')
PLAYLIST_ID_PATTERN = re.compile(r'[?&]list=([a-zA-Z0-9_-]{34})')
SPOTIFY_TRACK_PATTERN = re.compile(r'spotify\.com/track/([a-zA-Z0-9]+)')
SPOTIFY_PLAYLIST_PATTERN = re.compile(r'spotify\.com/playlist/([a-zA-Z0-9]+)')

def is_youtube_url(url):
    url = url.strip().lower()
    return 'youtube.com' in url or 'youtu.be' in url

def is_spotify_url(url):
    return 'spotify.com' in url.strip().lower()

def extract_video_id(url):
    m = VIDEO_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def extract_playlist_id(url):
    m = PLAYLIST_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def extract_spotify_track_id(url):
    m = SPOTIFY_TRACK_PATTERN.search(url.strip())
    return m.group(1) if m else None

def extract_spotify_playlist_id(url):
    m = SPOTIFY_PLAYLIST_PATTERN.search(url.strip())
    return m.group(1) if m else None

def get_error_reason(err_msg):
    err = str(err_msg).lower()
    if 'sign in' in err or 'bot' in err:
        return "⚠️ YouTubeのBot判定に引っかかりました。Cookieを更新してください。"
    if 'age' in err:
        return "🔞 年齢制限付き動画のため再生できません。"
    if 'available in' in err or 'vpn' in err or 'proxy' in err:
        return "🌍 地域制限がかかっているため再生できません。"
    if 'private' in err or 'unavailable' in err:
        return "🚫 非公開・削除されているため再生できません。"
    if 'copyright' in err or 'blocked' in err:
        return "©️ 著作権の問題で再生できません。"
    if 'format' in err:
        return "🎵 音声フォーマットが取得できません。別の動画をお試しください。"
    return f"❌ 再生できません: {str(err_msg)[:80]}"


class GuildMusicState:
    """サーバーごとの再生状態"""
    def __init__(self):
        self.queue = []
        self.current = None
        self.is_playing = False
        self.repeat_mode = 0  # 0:なし 1:1曲 2:全曲
        self.sub_panel_message = None
        self.sub_panel_view = None


class MusicPlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}  # guild_id -> GuildMusicState
        self.COOKIE_FILE = os.path.join(os.path.dirname(__file__), '..', 'cookies.txt')
        self.use_cookie = os.path.exists(self.COOKIE_FILE)

    def get_state(self, guild_id):
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    async def youtube_search(self, query, max_results=5):
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        res = youtube.search().list(q=query, part='snippet', type='video', maxResults=max_results).execute()
        return res.get('items', [])

    async def get_stream_url(self, url):
        ydl_opts = {
            'format': 'bestaudio/best[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
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
            stream_url = info.get('url')
            if not stream_url and info.get('formats'):
                audio_fmts = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_fmts:
                    stream_url = audio_fmts[0].get('url')
                if not stream_url:
                    all_fmts = [f for f in info['formats'] if f.get('acodec') != 'none']
                    if all_fmts:
                        stream_url = all_fmts[0].get('url')
            if not stream_url:
                raise Exception("音声フォーマットが見つかりません")
            thumb = info.get('thumbnail') or ''
            return {
                'title': info['title'],
                'url': stream_url,
                'duration': info.get('duration', 0),
                'thumbnail': thumb,
                'video_id': info.get('id', '')
            }

    async def get_spotify_track(self, track_id):
        """Spotifyトラック情報を取得→曲名+アーティスト名"""
        if not spotify_client:
            raise Exception("Spotify連携が無効です")
        track = spotify_client.track(track_id)
        name = track['name']
        artist = track['artists'][0]['name']
        return f"{name} {artist}"

    async def get_spotify_playlist(self, playlist_id):
        """Spotifyプレイリストの全曲を取得"""
        if not spotify_client:
            raise Exception("Spotify連携が無効です")
        results = spotify_client.playlist_tracks(playlist_id)
        tracks = []
        for item in results['items']:
            if item['track']:
                name = item['track']['name']
                artist = item['track']['artists'][0]['name']
                tracks.append(f"{name} {artist}")
        return tracks

    async def play_next(self, guild_id, voice_client, channel=None):
        state = self.get_state(guild_id)
        
        if not state.queue:
            state.is_playing = False
            state.current = None
            # サブパネル消去
            if state.sub_panel_message:
                try:
                    await state.sub_panel_message.delete()
                except:
                    pass
                state.sub_panel_message = None
                state.sub_panel_view = None
            return

        state.is_playing = True
        track = state.queue.pop(0)
        state.current = track

        def _after(err):
            if state.repeat_mode == 1:
                state.queue.insert(0, track)
            elif state.repeat_mode == 2:
                state.queue.append(track)
            asyncio.run_coroutine_threadsafe(
                self.play_next(guild_id, voice_client, channel), self.bot.loop
            )

        if voice_client and not voice_client.is_playing():
            voice_client.play(discord.FFmpegPCMAudio(
                executable=FFMPEG_PATH, source=track['url'],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            ), after=_after)

        # サブパネル更新
        await self.update_sub_panel(guild_id, channel)
        async def update_sub_panel(self, guild_id, channel=None):
        """サブパネルを自動更新"""
        state = self.get_state(guild_id)
        if not state.sub_panel_message:
            return

        emb = discord.Embed(title="🎵 再生中", color=0x2ecc71)
        if state.current:
            emb.add_field(name="▶️ 現在再生中", value=f"**{state.current['title']}**", inline=False)
            if state.current.get('thumbnail'):
                emb.set_thumbnail(url=state.current['thumbnail'])
        else:
            emb.add_field(name="状態", value="停止中", inline=False)

        if state.queue:
            next_titles = "\n".join([f"{i+1}. {t['title'][:30]}" for i, t in enumerate(state.queue[:5])])
            if len(state.queue) > 5:
                next_titles += f"\n... 他 {len(state.queue)-5}曲"
            emb.add_field(name="⏭️ 次の曲", value=next_titles, inline=False)
        else:
            emb.add_field(name="⏭️ 次の曲", value="なし", inline=False)

        repeat_text = ["なし", "1曲リピート", "全曲リピート"][state.repeat_mode]
        emb.set_footer(text=f"🔁 リピート: {repeat_text} | 🔀 キュー: {len(state.queue)}曲")

        try:
            await state.sub_panel_message.edit(embed=emb)
        except:
            pass

    # ========== 検索モーダル ==========
    class SearchModal(ui.Modal, title="🔍 曲を検索"):
        keyword = ui.TextInput(label="検索キーワード", placeholder="曲名・アーティスト名", max_length=200)
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            txt = str(self.keyword).strip()
            results = await self.cog.youtube_search(txt, max_results=10)
            if not results:
                return await interaction.followup.send("❌ 見つかりませんでした", ephemeral=True)
            
            state = self.cog.get_state(interaction.guild_id)
            added = 0
            failed = []
            msg = await interaction.followup.send(f"⬇️ {len(results)}曲を追加中...", ephemeral=True)
            
            for item in results:
                vid = item['id']['videoId']
                try:
                    trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                    state.queue.append(trk)
                    added += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    failed.append(f"{item['snippet']['title'][:20]}: {get_error_reason(e)}")
            
            emb = discord.Embed(title="✅ 追加完了", color=0x2ecc71)
            emb.add_field(name="追加", value=f"{added}/{len(results)}曲", inline=True)
            if failed:
                emb.add_field(name="⚠️ 再生不可", value="\n".join(failed[:3]), inline=False)
            await msg.edit(content="", embed=emb)
            
            # 自動再生開始
            vc = interaction.guild.voice_client
            if vc and not state.is_playing and state.queue:
                await self.cog.play_next(interaction.guild_id, vc, interaction.channel)

    # ========== リンク検索モーダル ==========
    class LinkModal(ui.Modal, title="🔗 リンクを追加"):
        url = ui.TextInput(label="YouTube / Spotify リンク", placeholder="動画URL / プレイリスト / Spotify URL", max_length=500)
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            txt = str(self.url).strip()
            state = self.cog.get_state(interaction.guild_id)
            msg = await interaction.followup.send("⬇️ 処理中...", ephemeral=True)
            
            try:
                # Spotifyトラック
                sid = extract_spotify_track_id(txt)
                if sid:
                    query = await self.cog.get_spotify_track(sid)
                    results = await self.cog.youtube_search(query, max_results=1)
                    if results:
                        vid = results[0]['id']['videoId']
                        trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                        state.queue.append(trk)
                        await msg.edit(content=f"✅ Spotify曲を追加: **{trk['title']}**")
                    else:
                        await msg.edit(content="❌ YouTubeで見つかりませんでした")
                    return

                # Spotifyプレイリスト
                spid = extract_spotify_playlist_id(txt)
                if spid:
                    queries = await self.cog.get_spotify_playlist(spid)
                    added = 0
                    for q in queries:
                        try:
                            results = await self.cog.youtube_search(q, max_results=1)
                            if results:
                                vid = results[0]['id']['videoId']
                                trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                                state.queue.append(trk)
                                added += 1
                                await asyncio.sleep(0.5)
                        except:
                            continue
                    await msg.edit(content=f"✅ Spotifyプレイリスト追加: {added}/{len(queries)}曲")
                    return

                # YouTubeプレイリスト
                pid = extract_playlist_id(txt)
                if pid:
                    ydl_opts = {'quiet': True, 'extract_flat': True, 'nocheckcertificate': True}
                    if self.cog.use_cookie:
                        ydl_opts['cookiefile'] = self.cog.COOKIE_FILE
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={pid}", download=False)
                    entries = [e for e in info.get('entries', []) if e and e.get('id')]
                    added = 0
                    for e in entries:
                        try:
                            trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={e['id']}")
                            state.queue.append(trk)
                            added += 1
                            await asyncio.sleep(0.5)
                        except:
                            continue
                    await msg.edit(content=f"✅ プレイリスト追加: {added}/{len(entries)}曲")
                    return

                # YouTube動画
                vid = extract_video_id(txt)
                if vid:
                    trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                    state.queue.append(trk)
                    await msg.edit(content=f"✅ 追加: **{trk['title']}**")
                    return

                await msg.edit(content="❌ 対応していないリンク形式です")
            except Exception as e:
                await msg.edit(content=get_error_reason(e))
                return

            # 自動再生
            vc = interaction.guild.voice_client
            if vc and not state.is_playing and state.queue:
                await self.cog.play_next(interaction.guild_id, vc, interaction.channel)

    # ========== サブパネル（再生制御） ==========
    class SubPanel(ui.View):
        def __init__(self, cog, guild_id, author_id):
            super().__init__(timeout=None)
            self.cog = cog
            self.guild_id = guild_id
            self.author_id = author_id

        def _check(self, interaction):
            return interaction.user.id == self.author_id

        @ui.button(label="▶️ 再生", style=discord.ButtonStyle.success, row=0)
        async def play_btn(self, interaction, btn):
            if not self._check(interaction):
                return await interaction.response.send_message("❌ 権限なし", ephemeral=True)
            state = self.cog.get_state(self.guild_id)
            vc = interaction.guild.voice_client
            if not vc:
                if interaction.user.voice:
                    await interaction.user.voice.channel.connect()
                    vc = interaction.guild.voice_client
                else:
                    return await interaction.response.send_message("❌ 先にVCに入ってください", ephemeral=True)
            if vc.is_paused():
                vc.resume()
                await interaction.response.send_message("⏯ 再開", ephemeral=True)
            elif not state.is_playing and state.queue:
                await interaction.response.defer(ephemeral=True)
                await self.cog.play_next(self.guild_id, vc, interaction.channel)
            else:
                await interaction.response.send_message("❌ 再生する曲がありません", ephemeral=True)

        @ui.button(label="⏸ 一時停止", style=discord.ButtonStyle.secondary, row=0)
        async def pause_btn(self, interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            if vc and vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸ 一時停止", ephemeral=True)

        @ui.button(label="⏯ 再開", style=discord.ButtonStyle.secondary, row=0)
        async def resume_btn(self, interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            if vc and vc.is_paused():
                vc.resume()
                await interaction.response.send_message("⏯ 再開", ephemeral=True)

        @ui.button(label="⏭ スキップ", style=discord.ButtonStyle.primary, row=1)
        async def skip_btn(self, interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            state = self.cog.get_state(self.guild_id)
            if vc and (vc.is_playing() or state.queue):
                state.repeat_mode = 0  # スキップ時はリピート解除
                vc.stop()
                await interaction.response.send_message("⏭ スキップ", ephemeral=True)
            else:
                await interaction.response.send_message("❌ スキップする曲がありません", ephemeral=True)

        @ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.primary, row=1)
        async def shuffle_btn(self, interaction, btn):
            if not self._check(interaction):
                return
            state = self.cog.get_state(self.guild_id)
            if len(state.queue) < 2:
                return await interaction.response.send_message("❌ 2曲以上必要です", ephemeral=True)
            random.shuffle(state.queue)
            await interaction.response.send_message(f"🔀 シャッフル完了（{len(state.queue)}曲）", ephemeral=True)
            await self.cog.update_sub_panel(self.guild_id)

        @ui.button(label="⏹ 切断", style=discord.ButtonStyle.danger, row=1)
        async def stop_btn(self, interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            state = self.cog.get_state(self.guild_id)
            if vc:
                vc.stop()
                await vc.disconnect()
            state.queue.clear()
            state.is_playing = False
            state.current = None
            # サブパネル消去
            if state.sub_panel_message:
                try:
                    await state.sub_panel_message.delete()
                except:
                    pass
            state.sub_panel_message = None
            state.sub_panel_view = None
            await interaction.response.send_message("⏹ 切断しました", ephemeral=True)

    # ========== メインパネル（永続化） ==========
    class MainPanel(ui.View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog

        @ui.button(label="🔍 検索", style=discord.ButtonStyle.blurple, custom_id="music_search")
        async def search_btn(self, interaction, btn):
            await interaction.response.send_modal(MusicPlayerCog.SearchModal(self.cog))

        @ui.button(label="🔗 リンク検索", style=discord.ButtonStyle.green, custom_id="music_link")
        async def link_btn(self, interaction, btn):
            await interaction.response.send_modal(MusicPlayerCog.LinkModal(self.cog))

    @app_commands.command(name="音楽パネル", description="🎵 音楽再生パネルを設置")
    async def music_panel(self, interaction: discord.Interaction):
        emb = discord.Embed(title="🎵 音楽再生パネル", color=0x3498db)
        emb.add_field(name="使い方", value="🔍 検索: 曲名で検索\n🔗 リンク検索: YouTube/SpotifyのURLを追加", inline=False)
        emb.add_field(name="対応", value="YouTube動画・ショート・プレイリスト\nSpotifyトラック・プレイリスト", inline=False)
        view = self.MainPanel(self)
        await interaction.response.send_message(embed=emb, view=view)
        # 永続化登録
        self.bot.add_view(view)


async def setup(bot):
    if not YOUTUBE_API_KEY:
        print("⚠️ YOUTUBE_API_KEY未設定 → 音楽プレイヤー無効")
        return
    await bot.add_cog(MusicPlayerCog(bot))
    print("✅ 高機能音楽プレイヤー読み込み完了")
