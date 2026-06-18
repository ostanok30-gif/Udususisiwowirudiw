import re
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import ChatBannedRights
from telethon.tl.functions.channels import EditBannedRequest
from telethon.errors import ChatAdminRequiredError
import g4f
from g4f.client import Client as G4FClient

# ========== КОНФИГ ==========
BOT_TOKEN = "8633489750:AAGgfQvvx-Vl2XZ6qmRY2QivqScCnOGKaW8"
CHAT_ID = -1003816593056
OWNER_ID = 608502324
API_ID = 34928216
API_HASH = "29f66350a892e8b69a83b50d7e99bd27"

WARN_EXPIRE_DAYS = 30
DELETE_WARN_MSG_AFTER = 10
NOTIFY_USER_DM = True
MAX_WARNS = 5
MUTE_HOURS = 12

FORBIDDEN_WORDS_ENABLED = True
FORBIDDEN_LINKS_ENABLED = False
FORBIDDEN_STICKERS_ENABLED = False
FORBIDDEN_GIFS_ENABLED = False
FORBIDDEN_VOICE_ENABLED = False
FORBIDDEN_VIDEO_ENABLED = False
FORBIDDEN_PHOTOS_ENABLED = False
FORBIDDEN_FORWARDS_ENABLED = False
FORBIDDEN_CAPS_ENABLED = False
FORBIDDEN_SPAM_ENABLED = False
WELCOME_ENABLED = False
WELCOME_TEXT = "Добро пожаловать, {name}!"
CHAT_LOCKED = False
NIGHT_MODE_ENABLED = False

FLOOD_MAX_MSG = 5
FLOOD_SECONDS = 5
CAPS_MIN_LENGTH = 10
CAPS_RATIO = 0.7

# ====== AI CHAT SETTINGS ======
AI_ENABLED = True  # Включить/выключить ИИ
AI_TRIGGER = "крестбл"  # Ключевое слово для активации
AI_MODEL = "gpt-3.5-turbo"  # Модель g4f
AI_MAX_HISTORY = 10  # Максимальное количество сообщений в истории
AI_SYSTEM_PROMPT = "Ты полезный ассистент в чате. Отвечай кратко и по делу. Будь дружелюбным."

user_messages = {}
g4f_client = G4FClient()
ai_contexts = {}  # Хранилище контекстов для ИИ

import sqlite3

class Database:
    def __init__(self, db_path="moderator.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS forbidden_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE, added_by INTEGER, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY, role TEXT DEFAULT 'admin', added_by INTEGER, added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS warns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, admin_id INTEGER, reason TEXT, silent INTEGER DEFAULT 0, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS punishments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, until TIMESTAMP, admin_id INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, text TEXT, added_by INTEGER, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS warns_config (
            id INTEGER PRIMARY KEY, max_warns INTEGER DEFAULT 5, mute_hours INTEGER DEFAULT 12)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS reputation (
            user_id INTEGER PRIMARY KEY, rep INTEGER DEFAULT 0, last_rep TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY, messages INTEGER DEFAULT 0, warns_got INTEGER DEFAULT 0, last_active TIMESTAMP)""")
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS chat_config (
            id INTEGER PRIMARY KEY, log_channel INTEGER, welcome_text TEXT, night_start INTEGER DEFAULT 23, night_end INTEGER DEFAULT 7)""")
        self.cursor.execute("INSERT OR IGNORE INTO warns_config (id, max_warns, mute_hours) VALUES (1, 5, 12)")
        self.cursor.execute("INSERT OR IGNORE INTO chat_config (id) VALUES (1)")
        self.conn.commit()

    def add_word(self, word, added_by):
        try:
            self.cursor.execute("INSERT INTO forbidden_words (word, added_by) VALUES (?, ?)", (word.lower(), added_by))
            self.conn.commit()
            return True
        except: return False

    def remove_word(self, word):
        self.cursor.execute("DELETE FROM forbidden_words WHERE word = ?", (word.lower(),))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_all_words(self):
        self.cursor.execute("SELECT word FROM forbidden_words")
        return [r[0] for r in self.cursor.fetchall()]

    def add_admin(self, user_id, role="admin", added_by=None):
        self.cursor.execute("INSERT OR REPLACE INTO admins VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (user_id, role, added_by))
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_admin(self, user_id):
        self.cursor.execute("SELECT role FROM admins WHERE user_id = ?", (user_id,))
        r = self.cursor.fetchone()
        return r[0] if r else None

    def get_all_admins(self):
        self.cursor.execute("SELECT user_id, role FROM admins")
        return self.cursor.fetchall()

    def add_warn(self, user_id, admin_id, reason="", silent=0):
        self.cursor.execute("INSERT INTO warns (user_id, admin_id, reason, silent) VALUES (?, ?, ?, ?)", (user_id, admin_id, reason, silent))
        self.cursor.execute("UPDATE user_stats SET warns_got = warns_got + 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def remove_warn(self, user_id, warn_id):
        self.cursor.execute("DELETE FROM warns WHERE id = ? AND user_id = ?", (warn_id, user_id))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def clear_warns(self, user_id):
        self.cursor.execute("DELETE FROM warns WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_warns(self, user_id):
        expire = datetime.now() - timedelta(days=WARN_EXPIRE_DAYS)
        self.cursor.execute("SELECT id, reason, date, silent FROM warns WHERE user_id = ? AND date >= ? ORDER BY date DESC", (user_id, expire))
        return self.cursor.fetchall()

    def count_warns(self, user_id):
        expire = datetime.now() - timedelta(days=WARN_EXPIRE_DAYS)
        self.cursor.execute("SELECT COUNT(*) FROM warns WHERE user_id = ? AND date >= ?", (user_id, expire))
        return self.cursor.fetchone()[0]

    def get_top_warns(self, limit=10):
        expire = datetime.now() - timedelta(days=WARN_EXPIRE_DAYS)
        self.cursor.execute("SELECT user_id, COUNT(*) as cnt FROM warns WHERE date >= ? GROUP BY user_id ORDER BY cnt DESC LIMIT ?", (expire, limit))
        return self.cursor.fetchall()

    def add_punishment(self, user_id, ptype, until=None, admin_id=None):
        self.cursor.execute("INSERT INTO punishments (user_id, type, until, admin_id) VALUES (?, ?, ?, ?)", (user_id, ptype, until, admin_id))
        self.conn.commit()

    def get_active_punishment(self, user_id):
        self.cursor.execute("SELECT type, until FROM punishments WHERE user_id = ? AND (until IS NULL OR until > ?) ORDER BY date DESC LIMIT 1", (user_id, datetime.now()))
        return self.cursor.fetchone()

    def remove_punishment(self, user_id):
        self.cursor.execute("UPDATE punishments SET until = ? WHERE user_id = ? AND (until IS NULL OR until > ?)", (datetime.now(), user_id, datetime.now()))
        self.conn.commit()

    def add_note(self, name, text, added_by):
        try:
            self.cursor.execute("INSERT INTO notes (name, text, added_by) VALUES (?, ?, ?)", (name.lower(), text, added_by))
            self.conn.commit()
            return True
        except:
            self.cursor.execute("UPDATE notes SET text = ?, added_by = ?, date = CURRENT_TIMESTAMP WHERE name = ?", (text, added_by, name.lower()))
            self.conn.commit()
            return True

    def remove_note(self, name):
        self.cursor.execute("DELETE FROM notes WHERE name = ?", (name.lower(),))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_note(self, name):
        self.cursor.execute("SELECT text FROM notes WHERE name = ?", (name.lower(),))
        r = self.cursor.fetchone()
        return r[0] if r else None

    def get_all_notes(self):
        self.cursor.execute("SELECT name FROM notes")
        return [r[0] for r in self.cursor.fetchall()]

    def get_warns_config(self):
        self.cursor.execute("SELECT max_warns, mute_hours FROM warns_config WHERE id = 1")
        return self.cursor.fetchone()

    def update_warns_config(self, max_warns, mute_hours):
        self.cursor.execute("UPDATE warns_config SET max_warns = ?, mute_hours = ? WHERE id = 1", (max_warns, mute_hours))
        self.conn.commit()

    def get_rep(self, user_id):
        self.cursor.execute("SELECT rep FROM reputation WHERE user_id = ?", (user_id,))
        r = self.cursor.fetchone()
        return r[0] if r else 0

    def add_rep(self, from_id, to_id):
        if from_id == to_id: return False
        self.cursor.execute("SELECT last_rep FROM reputation WHERE user_id = ?", (from_id,))
        r = self.cursor.fetchone()
        now = datetime.now()
        if r and r[0]:
            last = datetime.fromisoformat(r[0]) if isinstance(r[0], str) else r[0]
            if (now - last).seconds < 3600: return False
        self.cursor.execute("INSERT INTO reputation (user_id, rep, last_rep) VALUES (?, 1, ?) ON CONFLICT(user_id) DO UPDATE SET rep = rep + 1, last_rep = ?", (to_id, now, now))
        self.cursor.execute("INSERT INTO reputation (user_id, rep, last_rep) VALUES (?, 0, ?) ON CONFLICT(user_id) DO UPDATE SET last_rep = ?", (from_id, now, now))
        self.conn.commit()
        return True

    def get_top_rep(self, limit=10):
        self.cursor.execute("SELECT user_id, rep FROM reputation ORDER BY rep DESC LIMIT ?", (limit,))
        return self.cursor.fetchall()

    def update_stats(self, user_id):
        self.cursor.execute("INSERT INTO user_stats (user_id, messages, last_active) VALUES (?, 1, ?) ON CONFLICT(user_id) DO UPDATE SET messages = messages + 1, last_active = ?", (user_id, datetime.now(), datetime.now()))
        self.conn.commit()

    def get_stats(self, user_id):
        self.cursor.execute("SELECT messages, warns_got FROM user_stats WHERE user_id = ?", (user_id,))
        r = self.cursor.fetchone()
        return r if r else (0, 0)

    def get_chat_config(self):
        self.cursor.execute("SELECT log_channel, welcome_text, night_start, night_end FROM chat_config WHERE id = 1")
        return self.cursor.fetchone()

    def update_chat_config(self, **kwargs):
        for k, v in kwargs.items():
            self.cursor.execute(f"UPDATE chat_config SET {k} = ? WHERE id = 1", (v,))
        self.conn.commit()


db = Database("moderator.db")
bot = TelegramClient("bot_session", api_id=API_ID, api_hash=API_HASH)


# ========== СУПЕР-ЗАЩИТА ==========

REPLACE_MAP = {
    '0': 'о', '1': 'и', '2': 'з', '3': 'з', '4': 'ч', '5': 'с',
    '6': 'б', '7': 'т', '8': 'в', '9': 'д',
    '@': 'а', '#': 'н', '$': 'с', '+': 'т',
    'x': 'х', 'e': 'е', 'a': 'а', 'o': 'о', 'p': 'р', 'c': 'с',
    'y': 'у', 'k': 'к', 'm': 'м', 'n': 'н', 't': 'т', 'b': 'б',
    'u': 'и', 'h': 'н', 'w': 'в', 'l': 'л', 'r': 'г', 's': 'с',
    'd': 'д', 'f': 'ф', 'g': 'г', 'j': 'й', 'z': 'з', 'v': 'в',
    'ё': 'е', 'й': 'и', 'α': 'а', 'β': 'б', 'γ': 'г', 'δ': 'д',
    'ε': 'е', 'ζ': 'з', 'η': 'н', 'θ': 'о', 'ι': 'и', 'κ': 'к',
    'λ': 'л', 'μ': 'м', 'ν': 'н', 'ξ': 'к', 'ο': 'о', 'π': 'п',
    'ρ': 'р', 'σ': 'с', 'τ': 'т', 'υ': 'у', 'φ': 'ф', 'χ': 'х',
    'ψ': 'п', 'ω': 'о',
}

BUILTIN_BAD_WORDS = [
    'nfdhjyrxzsdfvc',
]

SYSTEM_COMMANDS = [
    'команды', 'команда', 'help', 'меню', 'инфо', 'мои варны', 'варн', 'анварн',
    'варны', 'мут', 'размут', 'бан', 'разбан', 'кик', 'ид', 'стата', 'реп',
    'топ реп', 'топ варнов', 'добавить слово', 'удалить слово', 'список слов',
    'добавить админ', 'удалить админ', 'список админов', 'заметка',
    'удалить заметку', 'список заметок', 'варн лимит', 'настройки',
    'лог канал', 'ночной режим', 'лок', 'анлок', 'объявление', 'голосование',
    'очистить варны', '+реп', 'правила', 'приветствие',
    '+слова', '-слова', '+ссылки', '-ссылки', '+стикеры', '-стикеры',
    '+гифки', '-гифки', '+голосовые', '-голосовые', '+видео', '-видео',
    '+фото', '-фото', '+пересылки', '-пересылки', '+капс', '-капс',
    '+антиспам', '-антиспам', '+приветствие', '-приветствие',
]


def super_normalize(text):
    if not text: return ""
    text = text.lower()
    text = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2060-\u2064\ufeff]', '', text)
    result = []
    for c in text:
        result.append(REPLACE_MAP.get(c, c))
    text = ''.join(result)
    text = re.sub(r'[^а-яёa-z]', '', text)
    text = re.sub(r'(.)\1+', r'\1', text)
    return text


def is_system_command(text):
    text_lower = text.lower().strip()
    for cmd in SYSTEM_COMMANDS:
        if text_lower.startswith(cmd):
            return True
    return False


def is_forbidden(text):
    if not text: return None
    if not FORBIDDEN_WORDS_ENABLED: return None
    if is_system_command(text): return None
    
    clean = super_normalize(text)
    if len(clean) < 2: return None
    
    for bad in BUILTIN_BAD_WORDS:
        if super_normalize(bad) in clean: return bad
    
    for word in db.get_all_words():
        w_clean = super_normalize(word)
        if len(w_clean) < 2: continue
        if w_clean in clean: return word
        pattern = '.*'.join(re.escape(c) for c in w_clean)
        if re.search(pattern, clean): return word
        for i in range(len(clean) - len(w_clean) + 1):
            if re.search(pattern, clean[i:i + len(w_clean) * 3]): return word
    return None


def get_role(user_id):
    if user_id == OWNER_ID: return "owner"
    admin = db.get_admin(user_id)
    if admin: return admin
    return "user"


def can(user_id, action):
    perms = {
        "owner": ["warn","unwarn","mute","unmute","ban","unban","add_word","del_word",
                   "list_words","add_admin","del_admin","list_admins","kick",
                   "links","stickers","gifs","voice","video","photos","forwards",
                   "caps","spam","welcome","settings","note_add","note_del",
                   "note_list","note","clear_warns","warn_config","pin","unpin",
                   "id","stat","top_warns","top_rep","rep","log","night",
                   "lock","unlock","announce","poll"],
        "senior_admin": ["warn","unwarn","mute","unmute","ban","unban","clear_warns","kick","pin","unpin","lock","unlock"],
        "admin": ["warn","unwarn","mute","unmute","ban","kick","lock","unlock"],
    }
    return action in perms.get(get_role(user_id), [])


def parse_time(t):
    t = t.lower().strip()
    match = re.match(r"(\d+)\s*(м|мин|m|min|ч|час|h|hour|д|день|d|day|$)", t)
    if match:
        v = int(match.group(1))
        u = match.group(2) if match.group(2) else "м"
        if u in ['m','м','мин','min']: return timedelta(minutes=v)
        elif u in ['h','ч','час','hour']: return timedelta(hours=v)
        elif u in ['d','д','день','day']: return timedelta(days=v)
    return None


def format_time(minutes):
    if minutes == 0: return "навсегда"
    days = minutes // 1440
    hours = (minutes % 1440) // 60
    mins = minutes % 60
    parts = []
    if days: parts.append(f"{days}д")
    if hours: parts.append(f"{hours}ч")
    if mins: parts.append(f"{mins}м")
    return " ".join(parts)


async def get_reply_sender(event):
    if event.message.reply_to:
        reply_msg = await event.message.get_reply_message()
        if reply_msg: return await reply_msg.get_sender()
    return None


async def punish(chat, user, uid, action, minutes=0):
    try:
        if action == "мут":
            until = datetime.now() + timedelta(minutes=minutes) if minutes else None
            rights = ChatBannedRights(until_date=until, send_messages=True)
            await bot(EditBannedRequest(chat, user, rights))
            db.add_punishment(uid, "mute", until)
        elif action == "бан":
            until = datetime.now() + timedelta(minutes=minutes) if minutes else None
            rights = ChatBannedRights(until_date=until, view_messages=True)
            await bot(EditBannedRequest(chat, user, rights))
            db.add_punishment(uid, "ban", until)
        elif action == "размут":
            rights = ChatBannedRights(until_date=None, send_messages=False)
            await bot(EditBannedRequest(chat, user, rights))
            db.remove_punishment(uid)
        elif action == "разбан":
            rights = ChatBannedRights(until_date=None, view_messages=False)
            await bot(EditBannedRequest(chat, user, rights))
            db.remove_punishment(uid)
        elif action == "кик":
            await bot.kick_participant(chat, user)
        return True
    except:
        return False


async def check_punish(uid):
    count = db.count_warns(uid)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    
    if count >= max_warns:
        mute_hours = config[1] if config else MUTE_HOURS
        if not db.get_active_punishment(uid):
            return "мут", mute_hours * 60, max_warns
    
    if count >= 3:
        if not db.get_active_punishment(uid):
            return "мут", 60, 3
    
    return None, 0, 0


async def auto_del(msg, sec):
    if sec > 0:
        await asyncio.sleep(sec)
        try: await msg.delete()
        except: pass


async def add_warn_and_check(event, uid, reason, silent=0):
    db.add_warn(uid, 0, reason, silent)
    count = db.count_warns(uid)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    
    if count >= max_warns:
        mute_hours = config[1] if config else MUTE_HOURS
        await punish(event.chat_id, await event.get_sender(), uid, "мут", mute_hours * 60)
        return count, True, mute_hours * 60
    elif count >= 3:
        await punish(event.chat_id, await event.get_sender(), uid, "мут", 60)
        return count, True, 60
    else:
        return count, False, 0


async def log_action(text):
    config = db.get_chat_config()
    if config and config[0]:
        try:
            await bot.send_message(int(config[0]), text)
        except:
            pass


def is_night_time():
    config = db.get_chat_config()
    if not config: return False
    start = config[2] if config[2] else 23
    end = config[3] if config[3] else 7
    hour = datetime.now().hour
    if start < end:
        return start <= hour < end
    else:
        return hour >= start or hour < end


# ========== AI CHAT FUNCTIONS ==========

async def get_ai_response(user_id, user_message):
    """Получает ответ от g4f с учётом контекста"""
    try:
        # Инициализируем контекст для пользователя, если его нет
        if user_id not in ai_contexts:
            ai_contexts[user_id] = [
                {"role": "system", "content": AI_SYSTEM_PROMPT}
            ]
        
        # Добавляем сообщение пользователя в контекст
        ai_contexts[user_id].append({"role": "user", "content": user_message})
        
        # Ограничиваем историю
        if len(ai_contexts[user_id]) > AI_MAX_HISTORY * 2 + 1:
            # Оставляем system prompt и последние сообщения
            ai_contexts[user_id] = [ai_contexts[user_id][0]] + ai_contexts[user_id][-(AI_MAX_HISTORY * 2):]
        
        # Получаем ответ от g4f
        response = await asyncio.to_thread(
            g4f_client.chat.completions.create,
            model=AI_MODEL,
            messages=ai_contexts[user_id],
            max_tokens=500,
            temperature=0.7
        )
        
        reply = response.choices[0].message.content
        
        # Сохраняем ответ в контекст
        ai_contexts[user_id].append({"role": "assistant", "content": reply})
        
        return reply
    
    except Exception as e:
        print(f"AI Error: {e}")
        return "Извините, произошла ошибка при обработке запроса. Попробуйте позже."


def is_ai_command(text):
    """Проверяет, является ли сообщение командой к ИИ"""
    text_lower = text.lower().strip()
    return text_lower.startswith(AI_TRIGGER.lower())


def extract_ai_message(text):
    """Извлекает сообщение для ИИ после ключевого слова"""
    text = text.strip()
    # Убираем ключевое слово
    if text.lower().startswith(AI_TRIGGER.lower()):
        return text[len(AI_TRIGGER):].strip()
    return text


async def handle_ai_chat(event):
    """Обработчик сообщений для ИИ"""
    text = event.message.text or ""
    
    if not is_ai_command(text):
        return False
    
    user_message = extract_ai_message(text)
    
    if not user_message:
        await event.reply(
            f"🤖 Используйте: **{AI_TRIGGER} ваш вопрос**\n"
            f"Например: {AI_TRIGGER} привет как дела?\n"
            "Команды для ИИ:\n"
            f"• {AI_TRIGGER} очистить - сбросить историю диалога"
        )
        return True
    
    # Команда очистки контекста
    if user_message.lower() in ["очистить", "сброс", "забыть", "новый диалог"]:
        ai_contexts.pop(event.sender_id, None)
        await event.reply("🧹 Контекст диалога очищен!")
        return True
    
    # Отправляем "печатает..."
    async with bot.action(event.chat_id, 'typing'):
        response = await get_ai_response(event.sender_id, user_message)
    
    # Разбиваем длинные сообщения
    if len(response) > 4000:
        parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
        for part in parts:
            await event.reply(part)
            await asyncio.sleep(0.5)
    else:
        await event.reply(f"🤖 {response}")
    
    return True


# ========== КОМАНДЫ УПРАВЛЕНИЯ ИИ ==========

@bot.on(events.NewMessage(pattern=rf"(?i)^\+ии$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=rf"(?i)^\-ии$", chats=[CHAT_ID]))
async def cmd_toggle_ai(event):
    global AI_ENABLED
    if get_role(event.sender_id) != "owner":
        return
    
    AI_ENABLED = not AI_ENABLED
    status = "включен" if AI_ENABLED else "выключен"
    await event.reply(f"🤖 ИИ-помощник {status}")


@bot.on(events.NewMessage(pattern=rf"(?i)^{AI_TRIGGER} очистить$", chats=[CHAT_ID]))
async def cmd_clear_ai_context(event):
    ai_contexts.pop(event.sender_id, None)
    await event.reply("🧹 Ваша история диалога с ИИ очищена!")


# ========== АВТО-МОДЕРАЦИЯ ==========

@bot.on(events.NewMessage(chats=[CHAT_ID]))
async def auto_mod(event):
    uid = event.sender_id
    db.update_stats(uid)
    
    text = event.message.text or ""
    
    # Проверяем ИИ-команды ДО системных команд
    if AI_ENABLED and await handle_ai_chat(event):
        return
    
    if is_system_command(text): return
    
    if CHAT_LOCKED and uid != OWNER_ID and get_role(uid) not in ["senior_admin", "admin"]:
        try: await event.message.delete()
        except: pass
        return
    
    if NIGHT_MODE_ENABLED and is_night_time():
        if uid != OWNER_ID and get_role(uid) not in ["senior_admin", "admin"]:
            try: await event.message.delete()
            except: pass
            return
    
    if uid == OWNER_ID: return
    if get_role(uid) in ["senior_admin", "admin"]: return
    
    if FORBIDDEN_WORDS_ENABLED:
        word = is_forbidden(text)
        if word:
            try: await event.message.delete()
            except: pass
            count, punished, mins = await add_warn_and_check(event, uid, f"Запрещённое слово: {word}")
            name = event.sender.first_name or "Юзер"
            t = f"Авто-модерация\n└ {name} — запрещённое слово\n└ Варнов: {count}/{MAX_WARNS}"
            if punished: t += f"\n└ Мут на {format_time(mins)}"
            msg = await event.respond(t)
            await log_action(f"🚫 {name} — запрещённое слово: {word}\nВарнов: {count}/{MAX_WARNS}")
            asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))
            return
    
    if FORBIDDEN_LINKS_ENABLED and re.search(r'(https?://|t\.me/|@\w+)', text):
        try: await event.message.delete()
        except: pass
        count, punished, mins = await add_warn_and_check(event, uid, "Ссылка")
        name = event.sender.first_name or "Юзер"
        t = f"Авто-модерация\n└ {name} — ссылка запрещена\n└ Варнов: {count}/{MAX_WARNS}"
        if punished: t += f"\n└ Мут на {format_time(mins)}"
        msg = await event.respond(t)
        asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))
        return
    
    if FORBIDDEN_CAPS_ENABLED and len(text) >= CAPS_MIN_LENGTH:
        caps_count = sum(1 for c in text if c.isupper())
        if caps_count / len(text) >= CAPS_RATIO:
            try: await event.message.delete()
            except: pass
            count, punished, mins = await add_warn_and_check(event, uid, "CAPS")
            name = event.sender.first_name or "Юзер"
            t = f"Авто-модерация\n└ {name} — капс запрещён\n└ Варнов: {count}/{MAX_WARNS}"
            if punished: t += f"\n└ Мут на {format_time(mins)}"
            msg = await event.respond(t)
            asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))
            return
    
    if FORBIDDEN_SPAM_ENABLED:
        now = datetime.now()
        if uid not in user_messages: user_messages[uid] = []
        user_messages[uid] = [t for t in user_messages[uid] if (now - t).seconds < FLOOD_SECONDS]
        user_messages[uid].append(now)
        if len(user_messages[uid]) > FLOOD_MAX_MSG:
            try: await event.message.delete()
            except: pass
            count, punished, mins = await add_warn_and_check(event, uid, "Флуд")
            name = event.sender.first_name or "Юзер"
            t = f"Авто-модерация\n└ {name} — флуд запрещён\n└ Варнов: {count}/{MAX_WARNS}"
            if punished: t += f"\n└ Мут на {format_time(mins)}"
            msg = await event.respond(t)
            asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))
            return
    
    checks = [
        (FORBIDDEN_STICKERS_ENABLED, event.message.sticker, "Стикер", "Стикеры запрещены"),
        (FORBIDDEN_GIFS_ENABLED, event.message.gif, "GIF", "GIF запрещены"),
        (FORBIDDEN_VOICE_ENABLED, event.message.voice, "Голосовое", "Голосовые запрещены"),
        (FORBIDDEN_VIDEO_ENABLED, event.message.video, "Видео", "Видео запрещены"),
        (FORBIDDEN_PHOTOS_ENABLED, event.message.photo, "Фото", "Фото запрещены"),
        (FORBIDDEN_FORWARDS_ENABLED, event.message.forward, "Пересылка", "Пересылки запрещены"),
    ]
    
    for enabled, condition, reason, display in checks:
        if enabled and condition:
            try: await event.message.delete()
            except: pass
            count, punished, mins = await add_warn_and_check(event, uid, reason)
            t = f"Авто-модерация\n└ {display}\n└ Варнов: {count}/{MAX_WARNS}"
            if punished: t += f"\n└ Мут на {format_time(mins)}"
            msg = await event.respond(t)
            asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))
            return


# ========== ПРИВЕТСТВИЕ ==========

@bot.on(events.ChatAction(chats=[CHAT_ID]))
async def welcome_handler(event):
    if not WELCOME_ENABLED: return
    if event.user_joined or event.user_added:
        user = await event.get_user()
        name = user.first_name or "Гость"
        config = db.get_chat_config()
        wt = config[1] if config and config[1] else WELCOME_TEXT
        text = wt.replace("{name}", name).replace("{chat}", event.chat.title or "Чат")
        try: await event.respond(text)
        except: pass


# ========== КОМАНДЫ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^(команды|команда|help|меню)$", chats=[CHAT_ID]))
async def cmd_help(event):
    role = get_role(event.sender_id)
    
    base = (
        "команды — список команд\n"
        "инфо — информация\n"
        "мои варны — предупреждения\n"
        "ид — ID\n"
        "стата — статистика\n"
        "реп — репутация\n"
        "топ реп — топ репутации\n"
        "топ варнов — топ нарушителей\n"
        f"{AI_TRIGGER} — общение с ИИ"
    )
    
    mod = (
        "варн — выдать (+ -смс)\n"
        "анварн — снять\n"
        "варны — список\n"
        "очистить варны\n"
        "мут — замутить (1м/1ч/1д)\n"
        "размут\n"
        "бан — забанить (1м/1ч/1д/навсегда)\n"
        "разбан\n"
        "кик — выгнать"
    )
    
    admin_panel = (
        "добавить слово\n"
        "удалить слово\n"
        "список слов\n"
        "добавить админ\n"
        "удалить админ\n"
        "список админов\n"
        "варн лимит\n"
        "заметка — сохранить/показать\n"
        "лог канал — ID канала\n"
        "ночной режим — вкл/выкл/23 7\n"
        "лок / анлок — закрыть чат\n"
        "объявление — закрепить\n"
        "голосование — вопрос | вар1 | вар2\n"
        "+слова / -слова — маты\n"
        "+ссылки ... +антиспам\n"
        "+ии / -ии — вкл/выкл ИИ\n"
        "настройки"
    )
    
    if role == "owner":
        t = f"Владелец\n\nОбщие:\n{base}\n\nМодерация:\n{mod}\n\nУправление:\n{admin_panel}"
    elif role == "senior_admin":
        t = f"Ст. Админ\n\nОбщие:\n{base}\n\nМодерация:\n{mod}\nлок / анлок\nпин"
    elif role == "admin":
        t = f"Админ\n\nОбщие:\n{base}\n\nМодерация:\n{mod}\nлок / анлок"
    else:
        t = f"Пользователь\n\nОбщие:\n{base}"
    
    await event.reply(t)


# ========== ИНФО ==========

@bot.on(events.NewMessage(pattern=r"(?i)^инфо", chats=[CHAT_ID]))
async def cmd_info(event):
    target = await get_reply_sender(event) or await event.get_sender()
    uid = target.id
    role = get_role(uid)
    warns = db.count_warns(uid)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    stats = db.get_stats(uid)
    rep = db.get_rep(uid)
    name = f"{target.first_name or ''} {target.last_name or ''}".strip()
    uname = f"@{target.username}" if target.username else "нет"
    roles = {"owner":"Владелец","senior_admin":"Ст. Админ","admin":"Админ"}
    rname = roles.get(role, "Пользователь")
    
    await event.reply(
        f"Информация\n\n"
        f"Имя: {name}\n"
        f"Username: {uname}\n"
        f"ID: {uid}\n"
        f"Роль: {rname}\n\n"
        f"Варнов: {warns}/{max_warns}\n"
        f"Сообщений: {stats[0]}\n"
        f"Репутация: {rep}"
    )


# ========== ИД / СТАТА / РЕП ==========

@bot.on(events.NewMessage(pattern=r"(?i)^ид$", chats=[CHAT_ID]))
async def cmd_id(event):
    target = await get_reply_sender(event) or await event.get_sender()
    await event.reply(f"ID: {target.id}")


@bot.on(events.NewMessage(pattern=r"(?i)^стата$", chats=[CHAT_ID]))
async def cmd_stat(event):
    target = await get_reply_sender(event) or await event.get_sender()
    stats = db.get_stats(target.id)
    warns = db.count_warns(target.id)
    rep = db.get_rep(target.id)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    name = target.first_name or "Юзер"
    
    await event.reply(
        f"Статистика — {name}\n\n"
        f"Сообщений: {stats[0]}\n"
        f"Варнов: {warns}/{max_warns}\n"
        f"Репутация: {rep}"
    )


@bot.on(events.NewMessage(pattern=r"(?i)^\+реп$", chats=[CHAT_ID]))
async def cmd_addrep(event):
    if not event.message.reply_to: return await event.reply("Ответьте на сообщение")
    target = await get_reply_sender(event)
    if db.add_rep(event.sender_id, target.id):
        rep = db.get_rep(target.id)
        await event.reply(f"{target.first_name} получил репутацию! (всего: {rep})")
    else:
        await event.reply("Нельзя (себя или раз в час)")


@bot.on(events.NewMessage(pattern=r"(?i)^топ реп$", chats=[CHAT_ID]))
async def cmd_toprep(event):
    top = db.get_top_rep(10)
    if not top: return await event.reply("Нет данных")
    t = "Топ репутации\n\n"
    for i, (uid, rep) in enumerate(top, 1):
        try:
            user = await bot.get_entity(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        t += f"{i}. {name} — {rep}\n"
    await event.reply(t)


@bot.on(events.NewMessage(pattern=r"(?i)^топ варнов$", chats=[CHAT_ID]))
async def cmd_topwarns(event):
    top = db.get_top_warns(10)
    if not top: return await event.reply("Нет нарушителей")
    t = "Топ нарушителей\n\n"
    for i, (uid, cnt) in enumerate(top, 1):
        try:
            user = await bot.get_entity(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        t += f"{i}. {name} — {cnt} варнов\n"
    await event.reply(t)


# ========== ПРАВИЛА ==========

@bot.on(events.NewMessage(pattern=r"(?i)^правила$", chats=[CHAT_ID]))
async def cmd_rules(event):
    text = db.get_note("правила")
    if text:
        await event.reply(text)
    else:
        await event.reply("Правила не установлены")


# ========== ВАРНЫ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^мои варны$", chats=[CHAT_ID]))
async def cmd_mywarns(event):
    w = db.get_warns(event.sender_id)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    if not w: return await event.reply(f"Нет предупреждений (0/{max_warns})")
    t = f"Ваши варны: {len(w)}/{max_warns}\n\n"
    for i, (wid, reason, date, silent) in enumerate(w, 1):
        s = " [тихо]" if silent else ""
        t += f"{i}. #{wid} {reason or '—'}{s}\n  {date}\n\n"
    await event.reply(t)


@bot.on(events.NewMessage(pattern=r"(?i)^варн\b", chats=[CHAT_ID]))
async def cmd_warn(event):
    if not can(event.sender_id, "warn"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    tid = target.id
    if tid == OWNER_ID: return await event.reply("Нельзя владельца")
    if tid == event.sender_id: return await event.reply("Нельзя себя")
    if get_role(tid) in ["senior_admin","admin"] and get_role(event.sender_id) != "owner": return await event.reply("Нельзя админа")
    
    parts = event.text.split(maxsplit=2)
    silent = False
    reason = ""
    if len(parts) > 1:
        if parts[1].lower() == "-смс":
            silent = True
            reason = parts[2] if len(parts) > 2 else ""
        else:
            reason = " ".join(parts[1:])
    
    count, punished, mins = await add_warn_and_check(event, tid, reason, 1 if silent else 0)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    
    if not silent:
        t = f"Варн\n\nКому: {target.first_name}\nОт: {event.sender.first_name}\nПричина: {reason or '—'}\nВарнов: {count}/{max_warns}"
        if punished:
            t += f"\nМут на {format_time(mins)}"
        msg = await event.reply(t)
        await log_action(f"⚠️ {target.first_name} получил варн от {event.sender.first_name}\nПричина: {reason or '—'}\nВарнов: {count}/{max_warns}")
        asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))


@bot.on(events.NewMessage(pattern=r"(?i)^анварн", chats=[CHAT_ID]))
async def cmd_unwarn(event):
    if not can(event.sender_id, "unwarn"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    warns = db.get_warns(target.id)
    if not warns: return await event.reply(f"У {target.first_name} нет варнов")
    last = warns[0]
    db.remove_warn(target.id, last[0])
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    await event.reply(f"Варн #{last[0]} снят\nОсталось: {db.count_warns(target.id)}/{max_warns}")


@bot.on(events.NewMessage(pattern=r"(?i)^варны$", chats=[CHAT_ID]))
async def cmd_warns(event):
    if not can(event.sender_id, "unwarn"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    w = db.get_warns(target.id)
    config = db.get_warns_config()
    max_warns = config[0] if config else MAX_WARNS
    if not w: return await event.reply(f"У {target.first_name} нет варнов")
    t = f"Варны {target.first_name}: {len(w)}/{max_warns}\n\n"
    for i, (wid, reason, date, silent) in enumerate(w, 1):
        s = " [тихо]" if silent else ""
        t += f"{i}. #{wid} {reason or '—'}{s}\n  {date}\n\n"
    await event.reply(t)


@bot.on(events.NewMessage(pattern=r"(?i)^очистить варны$", chats=[CHAT_ID]))
async def cmd_clear_warns(event):
    if not can(event.sender_id, "clear_warns"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    db.clear_warns(target.id)
    await event.reply(f"Варны {target.first_name} очищены")


# ========== МУТ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^мут\b", chats=[CHAT_ID]))
async def cmd_mute(event):
    if not can(event.sender_id, "mute"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if target.id == OWNER_ID: return await event.reply("Нельзя владельца")
    if target.id == event.sender_id: return await event.reply("Нельзя себя")
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2: return await event.reply("Укажите время: мут 1ч")
    t = parse_time(parts[1])
    if not t: return await event.reply("Формат: 1м / 1ч / 1д")
    minutes = int(t.total_seconds() // 60)
    if await punish(event.chat_id, target, target.id, "мут", minutes):
        await event.reply(f"{target.first_name} замучен на {format_time(minutes)}")
        await log_action(f"🔇 {target.first_name} замучен на {format_time(minutes)}")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^размут", chats=[CHAT_ID]))
async def cmd_unmute(event):
    if not can(event.sender_id, "unmute"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if await punish(event.chat_id, target, target.id, "размут"):
        await event.reply(f"{target.first_name} размучен")
    else:
        await event.reply("Ошибка прав")


# ========== БАН ==========

@bot.on(events.NewMessage(pattern=r"(?i)^бан\b", chats=[CHAT_ID]))
async def cmd_ban(event):
    if not can(event.sender_id, "ban"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    tid = target.id
    if tid == OWNER_ID: return await event.reply("Нельзя владельца")
    if tid == event.sender_id: return await event.reply("Нельзя себя")
    if get_role(tid) in ["senior_admin","admin"] and get_role(event.sender_id) != "owner": return await event.reply("Нельзя админа")
    parts = event.text.split(maxsplit=2)
    reason = ""
    minutes = 0
    if len(parts) > 1:
        pt = parse_time(parts[1])
        if pt:
            minutes = int(pt.total_seconds() // 60)
            reason = parts[2] if len(parts) > 2 else ""
        else:
            reason = " ".join(parts[1:])
    if await punish(event.chat_id, target, tid, "бан", minutes):
        dur = f"на {format_time(minutes)}" if minutes else "навсегда"
        t = f"{target.first_name} забанен {dur}"
        if reason: t += f"\nПричина: {reason}"
        await event.reply(t)
        await log_action(f"🚫 {target.first_name} забанен {dur}\nПричина: {reason}")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^разбан", chats=[CHAT_ID]))
async def cmd_unban(event):
    if not can(event.sender_id, "unban"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if await punish(event.chat_id, target, target.id, "разбан"):
        await event.reply(f"{target.first_name} разбанен")
    else:
        await event.reply("Ошибка прав")


# ========== КИК ==========

@bot.on(events.NewMessage(pattern=r"(?i)^кик", chats=[CHAT_ID]))
async def cmd_kick(event):
    if not can(event.sender_id, "kick"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if target.id == OWNER_ID: return await event.reply("Нельзя владельца")
    if target.id == event.sender_id: return await event.reply("Нельзя себя")
    if await punish(event.chat_id, target, target.id, "кик"):
        await event.reply(f"{target.first_name} кикнут")
    else:
        await event.reply("Ошибка прав")


# ========== СЛОВА ==========

@bot.on(events.NewMessage(pattern=r"(?i)^добавить слово", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^добавить слово", from_users=[OWNER_ID]))
async def cmd_addword(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return await event.reply("Формат: добавить слово текст")
    word = parts[2].lower()
    if db.add_word(word, event.sender_id):
        await event.reply(f"Слово \"{word}\" добавлено")
    else:
        await event.reply(f"Слово \"{word}\" уже есть")


@bot.on(events.NewMessage(pattern=r"(?i)^удалить слово", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^удалить слово", from_users=[OWNER_ID]))
async def cmd_delword(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return await event.reply("Формат: удалить слово текст")
    if db.remove_word(parts[2].lower()):
        await event.reply(f"Слово \"{parts[2]}\" удалено")
    else:
        await event.reply(f"Слово \"{parts[2]}\" не найдено")


@bot.on(events.NewMessage(pattern=r"(?i)^список слов$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^список слов$", from_users=[OWNER_ID]))
async def cmd_listwords(event):
    if get_role(event.sender_id) != "owner": return
    words = db.get_all_words()
    if not words: return await event.reply("Список пуст")
    t = f"Слова: {len(words)}\n\n"
    for i, w in enumerate(words, 1):
        t += f"{i}. {w}\n"
    await event.reply(t)


# ========== АДМИНЫ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^добавить админ", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^добавить админ", from_users=[OWNER_ID]))
async def cmd_addadmin(event):
    if get_role(event.sender_id) != "owner": return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    parts = event.text.split()
    role = "admin"
    if len(parts) > 2 and parts[2].lower() in ["senior","ст","старший"]: role = "senior_admin"
    db.add_admin(target.id, role, event.sender_id)
    r = "Ст. Админ" if role == "senior_admin" else "Админ"
    await event.reply(f"{target.first_name} теперь {r}")


@bot.on(events.NewMessage(pattern=r"(?i)^удалить админ", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^удалить админ", from_users=[OWNER_ID]))
async def cmd_deladmin(event):
    if get_role(event.sender_id) != "owner": return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if target.id == OWNER_ID: return await event.reply("Нельзя снять владельца")
    if db.remove_admin(target.id):
        await event.reply(f"{target.first_name} снят с админов")
    else:
        await event.reply("Не админ")


@bot.on(events.NewMessage(pattern=r"(?i)^список админов$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^список админов$", from_users=[OWNER_ID]))
async def cmd_listadmins(event):
    if get_role(event.sender_id) != "owner": return
    admins = db.get_all_admins()
    t = f"Админы\n\n{OWNER_ID} — Владелец\n"
    for uid, role in admins:
        r = "Ст." if role == "senior_admin" else ""
        t += f"{uid} {r}\n"
    await event.reply(t)


# ========== ЗАМЕТКИ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^заметка\s+\S+\s+", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^заметка\s+\S+\s+", from_users=[OWNER_ID]))
async def cmd_addnote(event):
    if not can(event.sender_id, "note_add"): return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return
    db.add_note(parts[1].lower(), parts[2], event.sender_id)
    await event.reply(f"Заметка \"{parts[1]}\" сохранена")


@bot.on(events.NewMessage(pattern=r"(?i)^удалить заметку\s+", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^удалить заметку\s+", from_users=[OWNER_ID]))
async def cmd_delnote(event):
    if not can(event.sender_id, "note_del"): return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return
    if db.remove_note(parts[2].lower()):
        await event.reply(f"Заметка \"{parts[2]}\" удалена")
    else:
        await event.reply("Не найдена")


@bot.on(events.NewMessage(pattern=r"(?i)^список заметок$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^список заметок$", from_users=[OWNER_ID]))
async def cmd_listnotes(event):
    if not can(event.sender_id, "note_list"): return
    notes = db.get_all_notes()
    if not notes: return await event.reply("Нет заметок")
    t = "Заметки\n\n"
    for n in notes:
        t += f"• {n}\n"
    await event.reply(t)


@bot.on(events.NewMessage(pattern=r"(?i)^заметка\s+\S+$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^заметка\s+\S+$", from_users=[OWNER_ID]))
async def cmd_note(event):
    if not can(event.sender_id, "note"): return
    parts = event.text.split()
    if len(parts) < 2: return
    name = parts[1].lower()
    if name == "правила": return
    text = db.get_note(name)
    if text:
        await event.reply(text)
    else:
        await event.reply("Не найдена")


# ========== НАСТРОЙКИ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^варн лимит", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^варн лимит", from_users=[OWNER_ID]))
async def cmd_warn_config(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split()
    if len(parts) < 3:
        config = db.get_warns_config()
        return await event.reply(f"Макс варнов: {config[0]}\nМут на: {config[1]}ч")
    try:
        max_warns = int(parts[2])
        mute_hours = int(parts[3]) if len(parts) > 3 else 12
        db.update_warns_config(max_warns, mute_hours)
        await event.reply(f"Лимит: {max_warns} варнов → мут {mute_hours}ч")
    except:
        await event.reply("варн лимит 5 12")


@bot.on(events.NewMessage(pattern=r"(?i)^настройки$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^настройки$", from_users=[OWNER_ID]))
async def cmd_settings(event):
    if get_role(event.sender_id) != "owner": return
    config = db.get_warns_config()
    s = lambda x: "вкл" if x else "выкл"
    await event.reply(
        f"Настройки\n\n"
        f"ИИ-помощник: {s(AI_ENABLED)}\n"
        f"Слова: {s(FORBIDDEN_WORDS_ENABLED)}\n"
        f"Ссылки: {s(FORBIDDEN_LINKS_ENABLED)}\n"
        f"Стикеры: {s(FORBIDDEN_STICKERS_ENABLED)}\n"
        f"Гифки: {s(FORBIDDEN_GIFS_ENABLED)}\n"
        f"Голосовые: {s(FORBIDDEN_VOICE_ENABLED)}\n"
        f"Видео: {s(FORBIDDEN_VIDEO_ENABLED)}\n"
        f"Фото: {s(FORBIDDEN_PHOTOS_ENABLED)}\n"
        f"Пересылки: {s(FORBIDDEN_FORWARDS_ENABLED)}\n"
        f"Капс: {s(FORBIDDEN_CAPS_ENABLED)}\n"
        f"Антиспам: {s(FORBIDDEN_SPAM_ENABLED)}\n"
        f"Приветствие: {s(WELCOME_ENABLED)}\n"
        f"Ночной режим: {s(NIGHT_MODE_ENABLED)}\n"
        f"Лок чата: {s(CHAT_LOCKED)}\n"
        f"Макс варнов: {config[0]}\n"
        f"Мут на: {config[1]}ч"
    )


@bot.on(events.NewMessage(pattern=r"(?i)^лог канал", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^лог канал", from_users=[OWNER_ID]))
async def cmd_log_channel(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split()
    if len(parts) < 3: return await event.reply("лог канал ID")
    try:
        db.update_chat_config(log_channel=int(parts[2]))
        await event.reply(f"Лог канал: {parts[2]}")
    except:
        await event.reply("Неверный ID")


@bot.on(events.NewMessage(pattern=r"(?i)^ночной режим", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^ночной режим", from_users=[OWNER_ID]))
async def cmd_night(event):
    if get_role(event.sender_id) != "owner": return
    global NIGHT_MODE_ENABLED
    parts = event.text.split()
    
    if len(parts) == 2:
        NIGHT_MODE_ENABLED = not NIGHT_MODE_ENABLED
        return await event.reply(f"Ночной режим: {'вкл' if NIGHT_MODE_ENABLED else 'выкл'}")
    
    if len(parts) >= 4:
        try:
            start = int(parts[2])
            end = int(parts[3])
            NIGHT_MODE_ENABLED = True
            db.update_chat_config(night_start=start, night_end=end)
            return await event.reply(f"Ночной режим: {start}:00 — {end}:00")
        except:
            return await event.reply("Формат: ночной режим 23 7")


@bot.on(events.NewMessage(pattern=r"(?i)^лок$", chats=[CHAT_ID]))
async def cmd_lock(event):
    if not can(event.sender_id, "lock"): return
    global CHAT_LOCKED
    CHAT_LOCKED = True
    await event.reply("Чат закрыт")


@bot.on(events.NewMessage(pattern=r"(?i)^анлок$", chats=[CHAT_ID]))
async def cmd_unlock(event):
    if not can(event.sender_id, "unlock"): return
    global CHAT_LOCKED
    CHAT_LOCKED = False
    await event.reply("Чат открыт")


@bot.on(events.NewMessage(pattern=r"(?i)^объявление", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^объявление", from_users=[OWNER_ID]))
async def cmd_announce(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2: return await event.reply("объявление текст")
    msg = await event.reply(parts[1])
    try: await msg.pin()
    except: pass


@bot.on(events.NewMessage(pattern=r"(?i)^голосование", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^голосование", from_users=[OWNER_ID]))
async def cmd_poll(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split("|")
    if len(parts) < 3: return await event.reply("голосование Вопрос | Да | Нет")
    question = parts[0].replace("голосование ", "", 1).strip()
    options = [p.strip() for p in parts[1:]]
    try:
        await bot.send_message(event.chat_id, f"Голосование\n\n{question}\n\n" + "\n".join(f"• {o}" for o in options))
        await event.delete()
    except:
        await event.reply("Ошибка")


# ========== ТОГГЛЫ ==========

toggles = ["слова","ссылки","стикеры","гифки","голосовые","видео","фото","пересылки","капс","антиспам","приветствие"]

for name in toggles:
    @bot.on(events.NewMessage(pattern=rf"(?i)^\+{name}$", chats=[CHAT_ID]))
    @bot.on(events.NewMessage(pattern=rf"(?i)^\-{name}$", chats=[CHAT_ID]))
    @bot.on(events.NewMessage(pattern=rf"(?i)^\+{name}$", from_users=[OWNER_ID]))
    @bot.on(events.NewMessage(pattern=rf"(?i)^\-{name}$", from_users=[OWNER_ID]))
    async def toggle_handler(event, name=name):
        if get_role(event.sender_id) != "owner": return
        var_map = {
            "слова": "FORBIDDEN_WORDS_ENABLED",
            "ссылки": "FORBIDDEN_LINKS_ENABLED",
            "стикеры": "FORBIDDEN_STICKERS_ENABLED",
            "гифки": "FORBIDDEN_GIFS_ENABLED",
            "голосовые": "FORBIDDEN_VOICE_ENABLED",
            "видео": "FORBIDDEN_VIDEO_ENABLED",
            "фото": "FORBIDDEN_PHOTOS_ENABLED",
            "пересылки": "FORBIDDEN_FORWARDS_ENABLED",
            "капс": "FORBIDDEN_CAPS_ENABLED",
            "антиспам": "FORBIDDEN_SPAM_ENABLED",
            "приветствие": "WELCOME_ENABLED",
        }
        globals()[var_map[name]] = event.text.startswith("+")
        status = "вкл" if globals()[var_map[name]] else "выкл"
        await event.reply(f"{name.capitalize()}: {status}")


@bot.on(events.NewMessage(pattern=r"(?i)^приветствие\s+", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^приветствие\s+", from_users=[OWNER_ID]))
async def set_welcome(event):
    global WELCOME_TEXT
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2: return
    WELCOME_TEXT = parts[1]
    db.update_chat_config(welcome_text=WELCOME_TEXT)
    await event.reply(f"Приветствие:\n{WELCOME_TEXT}")


# ========== ЛС ==========

@bot.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id != OWNER_ID))
async def dm_block(event):
    pass


# ========== ЗАПУСК ==========

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Бот запущен")
    print(f"ИИ-помощник: {'включен' if AI_ENABLED else 'выключен'}")
    print(f"Ключевое слово: {AI_TRIGGER}")
    print(f"Модель: {AI_MODEL}")
    await bot.run_until_disconnected()

asyncio.run(main())
