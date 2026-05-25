# Токен бота
BOT_TOKEN = "8647879379:AAEA17ZXW3cOBwwjdxkWM90s1Tlv9yrs5R8"

# API (my.telegram.org)
API_ID = 34928216
API_HASH = "29f66350a892e8b69a83b50d7e99bd27"

# ID чата
CHAT_ID = -1003805492078

# Владелец бота
OWNER_ID = 8779822711

# ========== НАСТРОЙКИ ВАРНОВ ==========
WARN_ON_FORBIDDEN_WORD = True
WARN_ON_LINKS = False
WARN_ON_FLOOD = False
FLOOD_MAX_MSG = 5
FLOOD_SECONDS = 5

# Штрафы: кол-во варнов : (действие, минуты, 0=навсегда)
PUNISHMENTS = {
    3: ("мут", 60),
    5: ("мут", 1440),
    7: ("бан", 0),
}

WARN_EXPIRE_DAYS = 30
ALLOW_DIRECT_BAN = True
ALLOW_UNBAN = True
ALLOW_DIRECT_MUTE = True
NOTIFY_USER_DM = True
DELETE_WARN_MSG_AFTER = 10
WHITELIST_WORDS = []