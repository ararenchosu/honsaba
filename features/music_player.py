import os
import re
import random
import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands
import yt_dlp

# ============================================================
# ✅ 設定
# ============================================================
FFMPEG_PATH = "ffmpeg"
MUSIC_PATH = "./music"

# ============================================================
# ✅ Cookie（そのまま使えます）
# ============================================================
COOKIE_TEXT = """# Netscape HTTP Cookie File
# https://curl.haxx.se/rfc/cookie_spec.html
# This is a generated file! Do not edit.

.youtube.com	TRUE	/	TRUE	1808671270	__Secure-YNID	CtsBCAUSjQEBDB6PDItwbqNY-uBuukuNiHBeEpr1JSs4Y2n1TNRGOjpNt91jfZhjIpvDaEDyAzedQEXnAoDgpxq4K5vA9CYFtoR5fCGCuqYrrsI694qgnx8iN6IOOeFIYO7K5aWPkjfJkzNI8k_bnCR5Xv7kutrvjEVsaSnbUipH3DgZLfwrdhrOSRdfBku7FKwxryooBTJFARxY9WqxykglhWBD0gK-efjpJSM-DXERaMYq53jOQZ08iz9mjDA-V4xlpW-NzWkQLg9AbsFmkkUhyjNO52MPqef3LKYG
.youtube.com	TRUE	/	TRUE	1808674566	VISITOR_INFO1_LIVE	APAAx1e4Dpw
.youtube.com	TRUE	/	TRUE	1808674566	VISITOR_PRIVACY_METADATA	CgJKUBIEGgAgHw%3D%3D
.youtube.com	TRUE	/	TRUE	1827682567	PREF	f6=40000000&tz=Asia.Tokyo
.youtube.com	TRUE	/	TRUE	1793124287	GPS	1
.youtube.com	TRUE	/	TRUE	0	YSC	bg4_Yj5UzpI
.youtube.com	TRUE	/	TRUE	1824658559	__Secure-1PSIDTS	sidts-CjQBnJZzaoU3OyIvC6ftqFCg9diwBxuTH1J1f36ZcbGO_fjORPyPyHg1CBS1BF2NCP93KoNAEAA
.youtube.com	TRUE	/	TRUE	1824658559	__Secure-3PSIDTS	sidts-CjQBnJZzaoU3OyIvC6ftqFCg9diwBxuTH1J1f36ZcbGO_fjORPyPyHg1CBS1BF2NCP93KoNAEAA
.youtube.com	TRUE	/	FALSE	1827682559	HSID	AnUePsyR0GXMPFmE_
.youtube.com	TRUE	/	TRUE	1827682559	SSID	AVen-JT-bnON9haHV
.youtube.com	TRUE	/	FALSE	1827682559	APISID	vj7B05fpEd-i25j0/A6lXhia8Cr_BjBqiO
.youtube.com	TRUE	/	TRUE	1827682559	SAPISID	HkCsWWkZn8k54v9G/AhrAFLLrSgLCIGx5c
.youtube.com	TRUE	/	TRUE	1827682559	__Secure-1PAPISID	HkCsWWkZn8k54v9G/AhrAFLLrSgLCIGx5c
.youtube.com	TRUE	/	TRUE	1827682559	__Secure-3PAPISID	HkCsWWkZn8k54v9G/AhrAFLLrSgLCIGx5c
.youtube.com	TRUE	/	FALSE	1827682559	SID	g.a000EAmaMREf4OM09yH0e9Ah3fHANMKKAbJ1LLcda9HmKCaQTHWSG6T-HJtLnU2IGVlMcMbOHgACgYKAUsSARcSFQHGX2MinW4o8FIpcUw57Berw3mtuRoVAUF8yKoEfYQQsxldgMvGY2wmifse0076
.youtube.com	TRUE	/	TRUE	1827682559	__Secure-1PSID	g.a000EAmaMREf4OM09yH0e9Ah3fHANMKKAbJ1LLcda9HmKCaQTHWSI3C3kEFJQhP1gok3kKGUEQACgYKAdkSARcSFQHGX2MiBD2hsb44UiZ56q3VoE8jpBoVAUF8yKpSmPjedPo4kXVAW5oVs67K0076
.youtube.com	TRUE	/	TRUE	1827682559	__Secure-3PSID	g.a000EAmaMREf4OM09yH0e9Ah3fHANMKKAbJ1LLcda9HmKCaQTHWSLQXsg1X4OkLqVEm2peNFZQACgYKAd4SARcSFQHGX2MiKTUOKVWLmuJSahGsfM8efRoVAUF8yKpz0vjJx_k5H3-aENZIHXuL0076
.youtube.com	TRUE	/	FALSE	1824658569	SIDCC	APD_SKE6Gyxm_tnGv_oZLrqVs0QfYan8QwcALc67U-U_iKDR44jbelqwIeY2qL6fzevJy-mtQg
.youtube.com	TRUE	/	TRUE	1824658569	__Secure-1PSIDCC	APD_SKHTO8NRuKgZjjOOWbeYAqyPVx2JghyfTOiZlOkHVCazoEnwEaNcdzcvvJaBUjkgDMMuZw
.youtube.com	TRUE	/	TRUE	1824658569	__Secure-3PSIDCC	APD_SKGKQ7gD1Gt3n7Lgi5btIL2t8FoHjw406Fu-B5fkWaOGOOwq7S0x-pLNJdM1EpuH8TeqbA
.youtube.com	TRUE	/	TRUE	1827682566	LOGIN_INFO	AFmmF2swRgIhAKg2BuqrUY4EnC4gOzsPFHJvTKPX9_rtPgHFoy2uJDkGAiEAg36p78IVHlV7-RGDx1tViwwqN1rWo6YrpVnr37VbIb4:QUQ3MjNmeVVVSVlWc1dxWWVXS0Z4Y2N2RWZnaVdacnYza0k3eEtrQnRrXzlPWkhzTmdvYUh2M1c5SUlJTFJBaDVpZXRsbUJiaDhFcEgzUEFGbTI1aEVlM0FkR25XVUc3ZDN3d0hZVUN1VXctWWZBZFlSV1JrWmtLT2NKZThJNzhWdmd4NThjcnNJTjBVR2t1UFNmOFhuN0lUcmJicWd3bEF3
.youtube.com	TRUE	/	TRUE	1808674487	__Secure-ROLLOUT_TOKEN	COaJuYigo57ShQEQ09e-6dHalwMYvOvt5t3alwM%3D
"""

os.makedirs(MUSIC_PATH, exist_ok=True)

# ========== Cookieを一時ファイルに書き出し ==========
def get_cookie_file():
    if not COOKIE_TEXT.strip():
        return None
    path = os.path.join(os.path.dirname(__file__), ".cookie_temp.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(COOKIE_TEXT.strip())
    return path

COOKIE_FILE = get_cookie_file()
USE_COOKIE = COOKIE_FILE is not None
if USE_COOKIE:
    print("🍪 Cookie: 有効（コード内から読み込み）")
else:
    print("⚠️ Cookie: 未設定")

# ========== 正規表現 ==========
VIDEO_ID_PATTERN = re.compile(r'(?:v=|/embed/|/shorts/|/live/|youtu\.be/|watch\?v=)([a-zA-Z0-9_-]{11})')
PLAYLIST_ID_PATTERN = re.compile(r'[?&]list=([a-zA-Z0-9_-]{34})')

def extract_video_id(url):
    m = VIDEO_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def extract_playlist_id(url):
    m = PLAYLIST_ID_PATTERN.search(url.strip())
    return m.group(1) if m else None

def get_error_reason(err_msg):
    err = str(err_msg).lower()
    if 'sign in' in err or 'bot' in err:
        return "⚠️ YouTubeのBot判定に引っかかりました。COOKIE_TEXTを更新してください。"
    if 'age' in err:
        return "🔞 年齢制限付き動画のため再生できません。"
    if 'available in' in err or 'vpn' in err or 'proxy' in err:
        return "🌍 地域制限がかかっているため再生できません。"
    if 'private' in err or 'unavailable' in err:
        return "🚫 非公開・削除されているため再生できません。"
    if 'format' in err:
        return "🎵 音声フォーマットが取得できません。別の動画をお試しください。"
    return f"❌ 再生できません: {str(err_msg)[:80]}"

# ========== サーバーごとの状態 ==========
class GuildMusicState:
    def __init__(self):
        self.queue = []
        self.current = None
        self.is_playing = False
        self.sub_panel_message = None
        self.sub_panel_view = None

# ========== メインクラス ==========
class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def get_state(self, guild_id):
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    async def youtube_search(self, query, max_results=5):
        """yt-dlpだけで検索（APIキー不要）"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'nocheckcertificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
            },
        }
        if USE_COOKIE and COOKIE_FILE:
            ydl_opts['cookiefile'] = COOKIE_FILE
        await asyncio.sleep(0.5)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                results = []
                for entry in info.get('entries', []):
                    results.append({
                        'id': {'videoId': entry.get('id')},
                        'snippet': {
                            'title': entry.get('title', '不明'),
                            'channelTitle': entry.get('channel', '不明'),
                            'thumbnails': {'high': {'url': entry.get('thumbnail', '')}}
                        }
                    })
                return results
            except Exception as e:
                print(f"検索エラー: {e}")
                return []

    async def get_stream_url(self, url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
            },
            'extractor_args': {'youtube': {'player_client': ['web', 'android']}},
            'nocheckcertificate': True,
            'socket_timeout': 30,
        }
        if USE_COOKIE and COOKIE_FILE:
            ydl_opts['cookiefile'] = COOKIE_FILE
        await asyncio.sleep(1.0)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info.get('url')
            if not stream_url and info.get('formats'):
                for ext in ['m4a', 'webm', 'mp4']:
                    audio = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('ext') == ext]
                    if audio:
                        stream_url = audio[0].get('url')
                        break
                if not stream_url:
                    av = [f for f in info['formats'] if f.get('acodec') != 'none']
                    if av:
                        stream_url = av[0].get('url')
            if not stream_url:
                raise Exception("音声フォーマットが見つかりません")
            return {
                'title': info['title'],
                'url': stream_url,
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail') or '',
                'video_id': info.get('id', '')
            }

    async def play_next(self, guild_id, voice_client, channel=None, author_id=None):
        state = self.get_state(guild_id)
        if not state.queue:
            state.is_playing = False
            state.current = None
            if state.sub_panel_message:
                try:
                    await state.sub_panel_message.delete()
                except: pass
                state.sub_panel_message = None
            return

        state.is_playing = True
        state.current = state.queue.pop(0)

        def _after(err):
            asyncio.run_coroutine_threadsafe(
                self.play_next(guild_id, voice_client, channel), self.bot.loop
            )

        if voice_client:
            voice_client.stop()
            voice_client.play(discord.FFmpegPCMAudio(
                executable=FFMPEG_PATH, source=state.current['url'],
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            ), after=_after)

        if author_id and channel and not state.sub_panel_message:
            await self.create_sub_panel(guild_id, channel, author_id)
        else:
            await self.update_sub_panel(guild_id)

    async def update_sub_panel(self, guild_id):
        state = self.get_state(guild_id)
        if not state.sub_panel_message:
            return
        emb = discord.Embed(title="🎵 再生中", color=0x2ecc71)
        if state.current:
            emb.add_field(name="▶️ 現在", value=f"**{state.current['title']}**", inline=False)
            if state.current.get('thumbnail'):
                emb.set_thumbnail(url=state.current['thumbnail'])
        else:
            emb.add_field(name="状態", value="停止中", inline=False)
        if state.queue:
            next_titles = "\n".join([f"{i+1}. {t['title'][:35]}" for i, t in enumerate(state.queue[:5])])
            if len(state.queue) > 5:
                next_titles += f"\n... 他 {len(state.queue)-5}曲"
            emb.add_field(name="⏭️ 次の曲", value=next_titles, inline=False)
        else:
            emb.add_field(name="⏭️ 次の曲", value="なし", inline=False)
        emb.set_footer(text=f"🔀 キュー: {len(state.queue)}曲")
        try:
            await state.sub_panel_message.edit(embed=emb)
        except: pass

    async def create_sub_panel(self, guild_id, channel, author_id):
        state = self.get_state(guild_id)
        if state.sub_panel_message:
            try:
                await state.sub_panel_message.delete()
            except: pass
        view = self.SubPanel(self, guild_id, author_id)
        emb = discord.Embed(title="🎵 再生中", color=0x2ecc71)
        emb.add_field(name="状態", value="準備中...", inline=False)
        msg = await channel.send(embed=emb, view=view)
        state.sub_panel_message = msg
        state.sub_panel_view = view
        await self.update_sub_panel(guild_id)

    # ========== 検索モーダル ==========
    class SearchModal(ui.Modal, title="🔍 曲を検索"):
        keyword = ui.TextInput(label="検索キーワード", max_length=200)
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            results = await self.cog.youtube_search(str(self.keyword).strip(), max_results=5)
            if not results:
                return await interaction.followup.send("❌ 見つかりませんでした", ephemeral=True)
            emb = discord.Embed(title=f"🔍 「{self.keyword}」検索結果", color=0x3498db)
            for i, item in enumerate(results):
                emb.add_field(name=f"{i+1}. {item['snippet']['title'][:40]}",
                              value=f"📺 {item['snippet']['channelTitle']}", inline=False)
            await interaction.followup.send(embed=emb, view=MusicBot.SearchSelect(self.cog, results), ephemeral=True)

    class SearchSelect(ui.View):
        def __init__(self, cog, results):
            super().__init__(timeout=120)
            self.cog = cog
            self.results = results
            for i, item in enumerate(results):
                vid = item['id']['videoId']
                title = item['snippet']['title'][:25]
                thumb = item['snippet']['thumbnails']['high']['url']
                btn = ui.Button(label=f"{i+1}. {title}", style=discord.ButtonStyle.primary)
                btn.callback = self._make_cb(vid, thumb)
                self.add_item(btn)
        def _make_cb(self, vid, thumb):
            async def cb(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                msg = await interaction.followup.send("⬇️ 取得中...", ephemeral=True)
                state = self.cog.get_state(interaction.guild_id)
                try:
                    trk = await self.cog.get_stream_url(f"https://www.youtube.com/watch?v={vid}")
                    state.queue.append(trk)
                    emb = discord.Embed(title="✅ 追加", description=f"**{trk['title']}**", color=0x2ecc71)
                    emb.set_thumbnail(url=thumb)
                    emb.add_field(name="キュー", value=f"計 {len(state.queue)}曲", inline=True)
                    await msg.edit(content="", embed=emb)
                    vc = interaction.guild.voice_client
                    if vc and not state.is_playing and state.queue:
                        await self.cog.play_next(interaction.guild_id, vc, interaction.channel, interaction.user.id)
                    elif not vc:
                        if interaction.user.voice:
                            await interaction.user.voice.channel.connect()
                            await self.cog.play_next(interaction.guild_id, interaction.guild.voice_client, interaction.channel, interaction.user.id)
                        else:
                            await interaction.followup.send("❌ VCに入ってください", ephemeral=True)
                except Exception as e:
                    await msg.edit(content=get_error_reason(e))
            return cb

    # ========== リンクモーダル ==========
    class LinkModal(ui.Modal, title="🔗 リンク追加"):
        url = ui.TextInput(label="YouTube URL ", max_length=500)
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            txt = str(self.url).strip()
            state = self.cog.get_state(interaction.guild_id)
            msg = await interaction.followup.send("⬇️ 処理中...", ephemeral=True)
            try:
                # YouTubeプレイリスト
                pid = extract_playlist_id(txt)
                if pid:
                    opts = {
                        'quiet': True,
                        'extract_flat': True,
                        'nocheckcertificate': True,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                            'Referer': 'https://www.youtube.com/',
                        },
                    }
                    if USE_COOKIE and COOKIE_FILE:
                        opts['cookiefile'] = COOKIE_FILE
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={pid}", download=False)
                    added = 0
                    for e in info.get('entries', []):
                        if not e: continue
                        try:
                            trk = await self.cog.get_stream_url(f"https://youtu.be/{e['id']}")
                            state.queue.append(trk)
                            added += 1
                            await asyncio.sleep(0.5)
                        except: pass
                    await msg.edit(content=f"✅ プレイリスト: {added}曲追加")
                    return
                # YouTube動画
                vid = extract_video_id(txt)
                if vid:
                    trk = await self.cog.get_stream_url(f"https://youtu.be/{vid}")
                    state.queue.append(trk)
                    await msg.edit(content=f"✅ 追加: **{trk['title']}**")
                    vc = interaction.guild.voice_client
                    if vc and not state.is_playing and state.queue:
                        await self.cog.play_next(interaction.guild_id, vc, interaction.channel, interaction.user.id)
                    elif not vc:
                        if interaction.user.voice:
                            await interaction.user.voice.channel.connect()
                            await self.cog.play_next(interaction.guild_id, interaction.guild.voice_client, interaction.channel, interaction.user.id)
                        else:
                            await interaction.followup.send("❌ VCに入ってください", ephemeral=True)
                    return
                await msg.edit(content="❌ YouTubeのURLを入力してください")
            except Exception as e:
                await msg.edit(content=get_error_reason(e))

    # ========== サブパネル（再生中制御） ==========
    class SubPanel(ui.View):
        def __init__(self, cog, guild_id, author_id):
            super().__init__(timeout=None)
            self.cog = cog
            self.guild_id = guild_id
            self.author_id = author_id

        def _check(self, interaction):
            return interaction.user.id == self.author_id

        @ui.button(label="▶️ 再生", style=discord.ButtonStyle.success, row=0)
        async def play_btn(self, interaction: discord.Interaction, btn):
            if not self._check(interaction):
                return await interaction.response.send_message("❌ 権限がありません", ephemeral=True)
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
                await interaction.response.send_message("⏯ 再開しました", ephemeral=True)
            elif not state.is_playing and state.queue:
                await interaction.response.defer(ephemeral=True)
                await self.cog.play_next(self.guild_id, vc, interaction.channel, interaction.user.id)
            else:
                await interaction.response.send_message("❌ 再生する曲がありません", ephemeral=True)

        @ui.button(label="⏸ 一時停止", style=discord.ButtonStyle.secondary, row=0)
        async def pause_btn(self, interaction: discord.Interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            if vc and vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸ 一時停止しました", ephemeral=True)

        @ui.button(label="⏯ 再開", style=discord.ButtonStyle.secondary, row=0)
        async def resume_btn(self, interaction: discord.Interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            if vc and vc.is_paused():
                vc.resume()
                await interaction.response.send_message("⏯ 再開しました", ephemeral=True)

        @ui.button(label="⏭ スキップ", style=discord.ButtonStyle.primary, row=1)
        async def skip_btn(self, interaction: discord.Interaction, btn):
            if not self._check(interaction):
                return
            vc = interaction.guild.voice_client
            state = self.cog.get_state(self.guild_id)
            if vc and (vc.is_playing() or state.queue):
                vc.stop()
                await interaction.response.send_message("⏭ スキップしました", ephemeral=True)
            else:
                await interaction.response.send_message("❌ スキップする曲がありません", ephemeral=True)

        @ui.button(label="🔀 シャッフル", style=discord.ButtonStyle.primary, row=1)
        async def shuffle_btn(self, interaction: discord.Interaction, btn):
            if not self._check(interaction):
                return
            state = self.cog.get_state(self.guild_id)
            if len(state.queue) < 2:
                return await interaction.response.send_message("❌ 2曲以上必要です", ephemeral=True)
            random.shuffle(state.queue)
            await interaction.response.send_message(f"🔀 シャッフルしました（{len(state.queue)}曲）", ephemeral=True)
            await self.cog.update_sub_panel(self.guild_id)

        @ui.button(label="⏹ 切断", style=discord.ButtonStyle.danger, row=1)
        async def stop_btn(self, interaction: discord.Interaction, btn):
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
            if state.sub_panel_message:
                try:
                    await state.sub_panel_message.delete()
                except: pass
            state.sub_panel_message = None
            await interaction.response.send_message("⏹ 切断しました", ephemeral=True)

    # ========== メインパネル ==========
    class MainPanel(ui.View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog

        @ui.button(label="🔍 検索", style=discord.ButtonStyle.blurple, custom_id="music_search")
        async def search_btn(self, interaction: discord.Interaction, btn):
            await interaction.response.send_modal(MusicBot.SearchModal(self.cog))

        @ui.button(label="🔗 リンク追加", style=discord.ButtonStyle.green, custom_id="music_link")
        async def link_btn(self, interaction: discord.Interaction, btn):
            await interaction.response.send_modal(MusicBot.LinkModal(self.cog))

    @app_commands.command(name="音楽パネル", description="🎵 音楽再生パネルを表示")
    async def music_panel(self, interaction: discord.Interaction):
        emb = discord.Embed(title="🎵 音楽再生パネル", color=0x3498db)
        emb.add_field(name="使い方", value="🔍 検索：曲名から探して選ぶ\n🔗 リンク追加：YouTubeのURLを貼る", inline=False)
        emb.add_field(name="対応", value="YouTube 動画・ショート・プレイリスト", inline=False)
        view = self.MainPanel(self)
        await interaction.response.send_message(embed=emb, view=view)
        self.bot.add_view(view)


# ========== Bot起動 ==========
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    TOKEN = os.getenv("DISCORD_TOKEN")

    if not TOKEN:
        print("❌ DISCORD_TOKEN 未設定")
        sys.exit(1)

    bot = commands.Bot(command_prefix="/", intents=discord.Intents.default())

    @bot.event
    async def on_ready():
        print(f"✅ ログイン: {bot.user}")
        try:
            await bot.add_cog(MusicBot(bot))
            synced = await bot.tree.sync()
            print(f"✅ コマンド同期: {len(synced)}件")
        except Exception as e:
            print(f"❌ 起動エラー: {e}")

    bot.run(TOKEN)
