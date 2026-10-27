import os
from dotenv import load_dotenv

# .env ファイルを読み込み（存在しなくてもエラーにしない）
load_dotenv()

class Config:
    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    # YouTube
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    
    # FFmpeg
    FFMPEG_PATH = os.getenv("FFMPEG_Path", "ffmpeg")
    
    # 音楽保存先
    MUSIC_PATH = os.getenv("MUSIC_PATH", "./music")

    @classmethod
    def validate(cls):
        """必須設定が揃っているか確認"""
        missing = []
        if not cls.DISCORD_TOKEN:
            missing.append("DISCORD_BOT_TOKEN")
        if not cls.YOUTUBE_API_KEY:
            missing.append("YOUTUBE_API_KEY")
        
        if missing:
            print(f"❌ 環境変数が不足しています: {', '.join(missing)}")
            return False
        
        # 保存先フォルダ作成
        os.makedirs(cls.MUSIC_PATH, exist_ok=True)
        return True
