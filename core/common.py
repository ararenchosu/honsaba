# ========== サーバー固有設定 ==========
OWNER_IDS = [
    1256574550901133377,
    1546348374922625065,
]

CALL_CHANNEL_ID = 1558080580112089198
WELCOME_LEAVE_CHANNEL_ID = 1542788842078216297
RESULT_CHANNEL_ID = 1558468434596077661
OTHELLO_CATEGORY_ID = 1558467161146663023  # ← 追加！

from datetime import timezone, timedelta
JST = timezone(timedelta(hours=9), "JST")

def is_owner(interaction):
    return interaction.user.id in OWNER_IDS
