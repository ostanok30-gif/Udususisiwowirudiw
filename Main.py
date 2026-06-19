# -*- coding: utf-8 -*-
import re
import time
import random
import datetime
import sqlite3
import threading
import logging
import os
import requests
import json
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from telebot import types
import telebot

# Импорты для Telethon
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.account import CheckUsernameRequest

# Импорт для ИИ-общения
import google.generativeai as genai

# ==================== ПАПКА ДЛЯ СЕССИЙ ====================
SESSION_DIR = 'sessions'
os.makedirs(SESSION_DIR, exist_ok=True)

# ==================== НАСТРОЙКА ЛОГОВ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== АСИНХРОННЫЙ ДВИЖОК ====================
_async_loop = asyncio.new_event_loop()

def _start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=_start_async_loop, args=(_async_loop,), daemon=True).start()

def run_async(coro):
    """Выполняет асинхронную функцию в фоновом цикле и возвращает результат"""
    return asyncio.run_coroutine_threadsafe(coro, _async_loop).result()

# ==================== ТОКЕН И БОТ ====================
TOKEN = '8289373453:AAHhtCsNGdgn4LcRYTerqvOIYk4XDomI578'
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=50)
bot.skip_pending = True

# ==================== НАСТРОЙКА ИИ GEMINI ====================
GEMINI_API_KEY = "ТВОЙ_GEMINI_API_КЛЮЧ"  # ❗️ Вставь сюда свой ключ от Google AI Studio

if GEMINI_API_KEY != "ТВОЙ_GEMINI_API_КЛЮЧ":
    genai.configure(api_key=GEMINI_API_KEY)
    ai_config = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 1024,
    }
    # Настраиваем промпт под твой проект
    system_prompt = (
        "Ты — дружелюбный ИИ-консультант и модератор цифровой экосистемы «Крестбл» (Krestbl). "
        "Ты помогаешь пользователям разбираться с ботами экосистемы: поиском коротких и красивых юзернеймов "
        "(включая функционал Telegram Fragment и TON) и временными почтами. Отвечай кратко, "
        "по делу, иногда используй эмодзи. Также ты следишь за порядком в чатах."
    )
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=ai_config,
        system_instruction=system_prompt
    )

# Список запрещенных слов для модерации (в нижнем регистре)
FORBIDDEN_WORDS = ['скам', 'scam', 'наеб', 'спам', 'казино', 'порно'] 

last_interaction = {}

def clean_previous_interaction(user_id, chat_id):
    if user_id in last_interaction:
        try:
            if last_interaction[user_id]["user_msg_id"]:
                bot.delete_message(chat_id, last_interaction[user_id]["user_msg_id"])
        except: pass
        try:
            if last_interaction[user_id]["bot_msg_id"]:
                bot.delete_message(chat_id, last_interaction[user_id]["bot_msg_id"])
        except: pass
        del last_interaction[user_id]

def send_clean_message(user_id, chat_id, text, parse_mode='HTML', reply_markup=None, user_msg_id=None):
    clean_previous_interaction(user_id, chat_id)
    msg = bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    last_interaction[user_id] = {
        "user_msg_id": user_msg_id,
        "bot_msg_id": msg.message_id
    }
    return msg

# ==================== БАЗА ДАННЫХ ====================
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.RLock()

# ==================== НАСТРОЙКИ ====================
ADMIN_ID = 8727723180
YOUR_USERNAME = "@ubmuh"
REQUIRED_CHANNEL = "@krestbII"
CHANNEL_LINK = "https://t.me/krestbII"
SELLER_USERNAME = "@nuemc"

API_ID = 25874957
API_HASH = 'c89ef6fd9ba5c8a479abb1f4d2de248d'
MAX_SESSIONS = 40
SESSION_TIMEOUT = 4
FLOOD_MAX_WAIT = 600
FLOOD_CHECK_INTERVAL = 2

vowels = 'aeiouy'
consonants = 'bcdfghklmnprstvw'
all_letters = 'abcdefghijklmnopqrstuvwxyz'
BASE_SEARCHES = 5
SEARCH_ATTEMPTS = 20
FILTER_ATTEMPTS = 20

patterns_5 = ['CVCVC', 'VCVCV', 'CVCCV', 'VCCVC', 'CCVCC', 'CVVCC']
patterns_6 = ['CVCVCV', 'VCVCVC', 'CVCCVC', 'VCCVCC', 'CVCVCC', 'CVVCVC']

PREMIUM_PRICES = {1: 50, 3: 120, 7: 210, 30: 400}
REFERRAL_REWARDS = {5: 1, 10: 2, 15: 3, 20: 4}
CRYPTO_BOT_TOKEN = "559739:AALFf0i5EFhsnAiXQ2CCrKtWVf2MZFfMmTz"

EMOJI = {
    'search': '🔍', 'found': '✅', 'error': '❌', 'premium': '💎',
    'profile': '👤', 'stats': '📊', 'info': 'ℹ️', 'referral': '👥',
    'top': '🏆', 'trap': '🎯', 'filter': '🔎', 'channel': '📢',
    'admin': '⚙️', 'star': '⭐', 'crown': '👑', 'fire': '🔥',
    'rocket': '🚀', 'zap': '⚡', 'lock': '🔒', 'time': '⏱️',
    'ban': '🚫', 'unban': '✅', 'gift': '🎁', 'promo': '🎟️'
}

MAINTENANCE_MODE = False

# ==================== СОЗДАНИЕ ТАБЛИЦ ====================
def migrate_database():
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'trial_used': 'INTEGER DEFAULT 0',
        'search_packages': 'INTEGER DEFAULT 0',
        'banned': 'INTEGER DEFAULT 0'
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                conn.commit()
            except: pass

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    subscription_end TEXT,
    searches_today INTEGER DEFAULT 0,
    last_search_date TEXT,
    created_date TEXT,
    total_searches INTEGER DEFAULT 0,
    found_count INTEGER DEFAULT 0,
    subscribed INTEGER DEFAULT 0,
    referral_activated INTEGER DEFAULT 0,
    trial_used INTEGER DEFAULT 0,
    search_packages INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS found (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    length INTEGER,
    price TEXT,
    found_date TEXT,
    finder_id INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS traps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target_username TEXT,
    status TEXT DEFAULT 'active',
    created_date TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER,
    receiver_id INTEGER,
    days INTEGER,
    payment_method TEXT,
    created_date TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS promocodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    reward_type TEXT,
    reward_amount INTEGER,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT,
    expires_at TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS promocode_activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    user_id INTEGER,
    activated_at TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admin_found (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    length INTEGER,
    price TEXT,
    found_date TEXT,
    status TEXT DEFAULT 'available'
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE,
    session_string TEXT,
    status TEXT DEFAULT 'active',
    last_error TEXT,
    flood_until TEXT,
    created_at TEXT,
    updated_at TEXT,
    error_count INTEGER DEFAULT 0,
    last_used TEXT
)''')

conn.commit()
migrate_database()

# ==================== МИГРАЦИЯ ДЛЯ ТАБЛИЦЫ SESSIONS ====================
def migrate_sessions_table():
    cursor.execute("PRAGMA table_info(sessions)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'session_string': 'TEXT',
        'phone': 'TEXT UNIQUE',
        'status': 'TEXT DEFAULT "active"',
        'last_error': 'TEXT',
        'flood_until': 'TEXT',
        'created_at': 'TEXT',
        'updated_at': 'TEXT',
        'error_count': 'INTEGER DEFAULT 0',
        'last_used': 'TEXT'
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {column_name} {column_type}")
                conn.commit()
            except Exception as e:
                print(f"⚠️ Ошибка при добавлении {column_name}: {e}")

migrate_sessions_table()

# ==================== КЛАСС СЕССИИ (TELETHON) ====================
class TelegramSession:
    def __init__(self, db_id, phone, session_string=None):
        self.id = db_id
        self.phone = phone
        self.status = 'active'
        self.session_string = session_string or ''
        self.client = TelegramClient(StringSession(self.session_string), API_ID, API_HASH, loop=_async_loop)
        self.error_count = 0
        self.last_error = None
        self.flood_until = None
        self.last_used = 0

    async def connect_client(self):
        try:
            if not self.client.is_connected():
                await self.client.connect()
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения сессии {self.phone}: {e}")
            return False

    async def disconnect_client(self):
        if self.client.is_connected():
            try:
                await self.client.disconnect()
            except:
                pass

    async def save_session_string(self):
        try:
            self.session_string = self.client.session.save()
            with db_lock:
                cursor.execute(
                    "UPDATE sessions SET session_string = ?, updated_at = ? WHERE id = ?",
                    (self.session_string, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.id)
                )
                conn.commit()
            session_file = f'{SESSION_DIR}/session_{self.id}.session'
            with open(session_file, 'w') as f:
                f.write(self.session_string)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения сессии {self.phone}: {e}")
            return False

    async def check_auth_once(self):
        try:
            await self.connect_client()
            authorized = await self.client.is_user_authorized()
            if authorized:
                self.status = 'active'
                self._update_db_status('active')
                await self.save_session_string()
                logger.info(f"💪 Сессия {self.phone} активна!")
                return True
            else:
                self.status = 'banned'
                self._update_db_status('banned')
                logger.error(f"❌ Сессия {self.phone} сдохла (разлогинена)")
                return False
        except Exception as e:
            logger.error(f"Ошибка проверки авторизации {self.phone}: {e}")
            return False

    async def keep_alive(self):
        try:
            if not self.client.is_connected():
                await self.connect_client()
            if self.client.is_connected() and self.status == 'active':
                await self.client.send_message('me', '❤️')
                self.last_used = time.time()
                return True
        except errors.UserDeactivatedError:
            self.status = 'banned'
            self._update_db_status('banned')
        except Exception:
            pass
        return False

    async def check_username(self, username):
        try:
            if self.client.is_connected():
                try:
                    await self.client.disconnect()
                except:
                    pass
            await self.client.connect()
            
            await asyncio.sleep(random.uniform(0.3, 0.7))
            try:
                result = await self.client(ResolveUsernameRequest(username))
                if result.peer:
                    return "taken"
            except errors.UsernameNotOccupiedError:
                try:
                    available = await self.client(CheckUsernameRequest(username))
                    if available:
                        return "free"
                    else:
                        return "banned"
                except (errors.UsernameOccupiedError, errors.UsernameInvalidError):
                    return "banned"
                except errors.FloodWaitError as e:
                    return f"flood:{e.seconds}"
            except errors.UsernameInvalidError:
                return "banned"
            except errors.FloodWaitError as e:
                return f"flood:{e.seconds}"
            except errors.UserDeactivatedError:
                self.status = 'banned'
                self._update_db_status('banned')
                return "flood:30"
            except Exception as e:
                err_str = str(e).lower()
                if "banned" in err_str or "deactivated" in err_str:
                    self.status = 'banned'
                    self._update_db_status('banned')
                    return "flood:30"
                return "taken"
        except errors.FloodWaitError as e:
            return f"flood:{e.seconds}"
        except Exception:
            return "taken"

    def _update_db_error(self, error_msg):
        self.last_error = error_msg
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with db_lock:
            cursor.execute(
                "UPDATE sessions SET last_error = ?, error_count = ?, updated_at = ? WHERE id = ?",
                (error_msg, self.error_count, now, self.id)
            )
            conn.commit()

    def _update_db_status(self, status_msg):
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with db_lock:
            cursor.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                (status_msg, now, self.id)
            )
            conn.commit()

# ==================== ЕДИНЫЙ МЕНЕДЖЕР СЕССИЙ ====================
class SessionManager:
    def __init__(self):
        self.sessions = []
        self.lock = threading.RLock()
        self._round_robin_idx = 0
        self.stats = {
            'checks_total': 0, 'checks_free': 0,
            'checks_taken': 0, 'checks_banned': 0, 'checks_error': 0
        }
        self.last_check_time = {}
        self.MIN_DELAY = 2
        self.GLOBAL_DELAY = 1
        self._last_global_check = 0
        self._start_pinger()
        logger.info("✅ SessionManager инициализирован")

    def load_from_db(self):
        with db_lock:
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "UPDATE sessions SET status = 'active', flood_until = NULL, error_count = 0, updated_at = ? WHERE status IN ('flood', 'banned')",
                (now,)
            )
            conn.commit()
            cursor.execute("SELECT id, phone, session_string, status, flood_until, error_count, last_error FROM sessions")
            rows = cursor.fetchall()
        with self.lock:
            self.sessions = []
            for row in rows:
                db_id, phone, session_string, status, flood_until, error_count, last_error = row
                session = TelegramSession(db_id, phone, session_string=session_string)
                session.status = 'active'
                session.error_count = 0
                session.last_error = None
                session.flood_until = None
                self.sessions.append(session)
                self.last_check_time[session.id] = 0
                try:
                    run_async(session.connect_client())
                except:
                    pass
        logger.info(f"✅ Загружено {len(self.sessions)} сессий")

    def _start_pinger(self):
        def pinger():
            while True:
                time.sleep(150)
                with self.lock:
                    for session in self.sessions:
                        if session.status == 'active' and session.session_string:
                            try:
                               run_async(session.keep_alive())
                            except:
                               pass
        threading.Thread(target=pinger, daemon=True).start()

    def force_recover_all(self):
        recovered = 0
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with db_lock:
            cursor.execute(
                "UPDATE sessions SET status = 'active', flood_until = NULL, error_count = 0, updated_at = ? WHERE status IN ('flood', 'banned')",
                (now,)
            )
            recovered = cursor.rowcount
            conn.commit()
        with self.lock:
            for session in list(self.sessions):
                if session.status in ('flood', 'banned'):
                    session.status = 'active'
                    session.flood_until = None
                    session.error_count = 0
                    session.last_error = None
                    self.last_check_time[session.id] = 0
        return recovered

    def get_next_session(self):
        with self.lock:
            now = time.time()
            time_since_last = now - self._last_global_check
            if time_since_last < self.GLOBAL_DELAY:
                time.sleep(self.GLOBAL_DELAY - time_since_last + 0.05)
            active_sessions = [s for s in self.sessions if s.status == 'active' and s.session_string]
            if not active_sessions:
                self.force_recover_all()
                active_sessions = [s for s in self.sessions if s.status == 'active' and s.session_string]
                if not active_sessions:
                    return None
            for session in active_sessions:
                last_used = self.last_check_time.get(session.id, 0)
                if now - last_used >= self.MIN_DELAY:
                    self.last_check_time[session.id] = now
                    session.last_used = now
                    self._last_global_check = now
                    return session
            oldest = min(active_sessions, key=lambda s: self.last_check_time.get(s.id, 0))
            wait = self.MIN_DELAY - (now - self.last_check_time.get(oldest.id, 0))
            if wait > 0: time.sleep(wait + 0.05)
            self.last_check_time[oldest.id] = time.time()
            oldest.last_used = time.time()
            self._last_global_check = now
            return oldest

    def mark_flood(self, session_id, seconds):
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.lock:
            session = next((s for s in self.sessions if s.id == session_id), None)
            if session:
                session.status = 'flood'
                session.flood_until = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
                self.last_check_time[session.id] = 0
                with db_lock:
                    until_str = (datetime.datetime.now() + datetime.timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')
                    cursor.execute(
                        "UPDATE sessions SET status = 'flood', flood_until = ?, updated_at = ? WHERE id = ?",
                        (until_str, now_str, session_id)
                    )
                    conn.commit()

    def remove_session(self, session_id):
        with self.lock:
            session = next((s for s in self.sessions if s.id == session_id), None)
            if session:
                try: run_async(session.disconnect_client())
                except: pass
                self.sessions.remove(session)
                if session.id in self.last_check_time:
                    del self.last_check_time[session.id]
        with db_lock:
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        return True

    def start_flood_monitor(self):
        while True:
            time.sleep(30)
            now = datetime.datetime.now()
            with self.lock:
                for session in list(self.sessions):
                    if session.status == 'flood' and session.flood_until and now >= session.flood_until:
                        session.status = 'active'
                        session.flood_until = None
                        session.error_count = 0
                        self.last_check_time[session.id] = 0
                        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
                        with db_lock:
                            cursor.execute(
                                "UPDATE sessions SET status = 'active', flood_until = NULL, error_count = 0, updated_at = ? WHERE id = ?",
                                (now_str, session.id)
                            )
                            conn.commit()

    def get_status(self):
        with self.lock:
            active = sum(1 for s in self.sessions if s.status == 'active')
            flood = sum(1 for s in self.sessions if s.status == 'flood')
        with db_lock:
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'banned'")
            banned = cursor.fetchone()[0]
        return {"active": active, "flood": flood, "banned": banned}

session_manager = SessionManager()

# ==================== ФИНАЛЬНАЯ ФУНКЦИЯ ПРОВЕРКИ ЮЗЕРНЕЙМА ====================
def verify_with_session(username):
    username = username.strip().replace('@', '').lower()
    if len(username) < 5 or len(username) > 32:
        return False

    for attempt in range(3):
        session = session_manager.get_next_session()
        if not session:
            session_manager.stats['checks_error'] += 1
            logger.warning(f"⚠️ Все сессии сдохли для {username}, пробую HTTP проверку")
            return checker.check(username, deep=True)

        session_manager.stats['checks_total'] += 1
        res = run_async(session.check_username(username))

        if res == "free":
            session_manager.stats['checks_free'] += 1
            return True
        elif res == "taken":
            session_manager.stats['checks_taken'] += 1
            return False
        elif res == "banned":
            session_manager.stats['checks_banned'] += 1
            return False
        elif res.startswith("flood:"):
            try: secs = min(int(res.split(":")[1]), 300)
            except: secs = 60
            session_manager.mark_flood(session.id, secs)
            session_manager.stats['checks_error'] += 1
            continue
        else:
            session_manager.stats['checks_error'] += 1
            return False

    logger.warning(f"⚠️ Все сессии в флуде для {username}, пробую HTTP проверку")
    return checker.check(username, deep=True)

# ==================== БАЗОВЫЕ ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ ====================
def get_user(user_id):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

def create_user(user_id, username=None, referrer_id=None):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return get_user(user_id), False
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO users (user_id, username, referrer_id, created_date) VALUES (?, ?, ?, ?)',
                       (user_id, username, referrer_id, now))
        conn.commit()
        return get_user(user_id), True

def update_user(user_id, **kwargs):
    allowed_fields = {
        'username', 'referrer_id', 'referrals_count', 'subscription_end',
        'searches_today', 'last_search_date', 'total_searches',
        'found_count', 'subscribed', 'referral_activated', 'trial_used',
        'search_packages', 'banned'
    }
    with db_lock:
        for key, val in kwargs.items():
            if key in allowed_fields:
                cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (val, user_id))
        conn.commit()

def is_banned(user_id):
    user = get_user(user_id)
    return user and user.get('banned', 0) == 1

def has_premium(user_id):
    user = get_user(user_id)
    if not user or not user.get('subscription_end'):
        return False
    try:
        return datetime.datetime.now() < datetime.datetime.strptime(user['subscription_end'], '%Y-%m-%d %H:%M:%S')
    except:
        return False

def get_available_searches(user_id):
    user = get_user(user_id)
    if not user: return BASE_SEARCHES
    if has_premium(user_id): return 9999
    packages = user.get('search_packages', 0)
    if packages > 0: return packages
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    last_date = user.get('last_search_date')
    if last_date != today:
        with db_lock:
            cursor.execute("UPDATE users SET searches_today = 0, last_search_date = ? WHERE user_id = ?", (today, user_id))
            conn.commit()
        return BASE_SEARCHES
    used_today = user.get('searches_today') or 0
    return max(BASE_SEARCHES - used_today, 0)

def use_search(user_id):
    user = get_user(user_id)
    if user:
        packages = user.get('search_packages', 0)
        if packages > 0:
            update_user(user_id, search_packages=packages - 1, total_searches=(user.get('total_searches', 0) + 1))
        else:
            update_user(user_id, searches_today=(user.get('searches_today', 0) + 1), total_searches=(user.get('total_searches', 0) + 1))

def add_found(user_id):
    user = get_user(user_id)
    if user: update_user(user_id, found_count=(user.get('found_count', 0) + 1))

def add_search_packages(user_id, amount):
    user = get_user(user_id)
    current = user.get('search_packages', 0) if user else 0
    update_user(user_id, search_packages=current + amount)

def add_premium(user_id, days, from_ref=False):
    user = get_user(user_id)
    if not user: return
    now = datetime.datetime.now()
    new_end = now + datetime.timedelta(days=days)
    if user.get('subscription_end'):
        try:
            old = datetime.datetime.strptime(user['subscription_end'], '%Y-%m-%d %H:%M:%S')
            if old > now: new_end = old + datetime.timedelta(days=days)
        except: pass
    update_user(user_id, subscription_end=new_end.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        if from_ref:
            ref_count = user.get('referrals_count', 0)
            text = (f"<b><tg-emoji emoji-id='5893034681636491040'>📱</tg-emoji> ПРЕМИУМ АКТИВИРОВАН!</b>\n\n"
                    f"<blockquote><b><tg-emoji emoji-id='5893203503915996356'>⚡️</tg-emoji> Вы собрали: {ref_count} рефералов. За это получили премиум на {days} дней.</b></blockquote>\n\n"
                    f"<b><tg-emoji emoji-id='5893203503915996356'>⚡️</tg-emoji> Спасибо, что пользуетесь нашим сервисом!</b>")
        else:
            text = (f"<b><tg-emoji emoji-id='5893034681636491040'>📱</tg-emoji> ПРЕМИУМ АКТИВИРОВАН!</b>\n\n"
                    f"<blockquote><b><tg-emoji emoji-id='5893203503915996356'>⚡️</tg-emoji> До {new_end.strftime('%d.%m.%Y')}</b></blockquote>\n\n"
                    f"<b><tg-emoji emoji-id='5893203503915996356'>⚡️</tg-emoji> Спасибо, что пользуетесь нашим сервисом!</b>")
        bot.send_message(user_id, text, parse_mode='HTML')
    except: pass

def activate_referral(user_id):
    user = get_user(user_id)
    if not user or user.get('referral_activated'): return False
    referrer_id = user.get('referrer_id')
    if not referrer_id or referrer_id == user_id: return False
    with db_lock:
        cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
        cursor.execute("UPDATE users SET referral_activated = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        cursor.execute("SELECT referrals_count FROM users WHERE user_id = ?", (referrer_id,))
        ref_count = cursor.fetchone()[0]
    next_milestone = None
    for need_refs in sorted(REFERRAL_REWARDS.keys()):
        if ref_count < need_refs:
            next_milestone = need_refs - ref_count
            break
    for need_refs, days in sorted(REFERRAL_REWARDS.items()):
        if ref_count >= need_refs:
            add_premium(referrer_id, days, from_ref=True)
    if next_milestone:
        remaining_text = f"<b><tg-emoji emoji-id='5895734085761896734'>©️</tg-emoji> Осталось до премиум: {next_milestone} реф.</b>"
    else:
        remaining_text = f"<b><tg-emoji emoji-id='5895734085761896734'>©️</tg-emoji> Все награды получены!</b>"
    try:
        text = (f"<b><tg-emoji emoji-id='5895713431264170680'>✅</tg-emoji> У вас новый реферал!</b>\n\n"
                f"<blockquote><b><tg-emoji emoji-id='5893450623449305489'>⚡️</tg-emoji> У вас рефералов: {ref_count}</b>\n"
                f"{remaining_text}</blockquote>\n\n"
                f"<b><tg-emoji emoji-id='5895213106228891182'>♥️</tg-emoji> Спасибо, что пользуетесь нашим сервисом!</b>")
        bot.send_message(referrer_id, text, parse_mode='HTML')
    except: pass
    return True

def estimate_price(username):
    name = username.lower()
    score = 0
    if len(name) == 5: score += 80
    elif len(name) == 6: score += 50
    elif len(name) <= 8: score += 30
    else: score += 10
    if name.isalpha(): score += 40
    common_words = ['star', 'king', 'god', 'fire', 'moon', 'sun', 'dark', 'light', 'ice', 'gold', 'rose', 
                   'blue', 'red', 'sky', 'wolf', 'lion', 'eagle', 'ghost', 'storm', 'night', 'lord', 'soul',
                   'love', 'life', 'time', 'fate', 'luck', 'myth', 'hero', 'legend', 'demon', 'angel', 'magic',
                   'dream', 'hope', 'fear', 'rain', 'cloud', 'stone', 'steel', 'iron', 'void', 'zero',
                   'nova', 'zen', 'pro', 'max', 'ultra', 'mega', 'super', 'boss', 'og', 'prime', 'elite']
    for word in common_words:
        if word in name: score += 25
    for c in set(name):
        if name.count(c) >= 3 and c.isalpha(): score -= 15
    vowel_count = sum(1 for c in name if c in 'aeiouy')
    if 1 <= vowel_count <= 3 and len(name) >= 5: score += 15
    premium_letters = sum(1 for c in name if c in 'xzqvjk')
    score += premium_letters * 8
    if score >= 150: return "250-500 ⭐"
    elif score >= 120: return "150-300 ⭐"
    elif score >= 90: return "100-200 ⭐"
    elif score >= 60: return "50-100 ⭐"
    elif score >= 40: return "25-75 ⭐"
    else: return "10-50 ⭐"

def validate_username(username):
    if not username: return False, "Пустой username"
    username = username.strip().lower().replace('@', '')
    if len(username) < 5 or len(username) > 32: return False, "Username должен быть от 5 до 32 символов"
    if not re.match(r'^[a-z0-9_]+$', username): return False, "Только латиница, цифры и _"
    return True, username

def check_subscription(user_id):
    try:
        status = bot.get_chat_member(REQUIRED_CHANNEL, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return True

def subscription_required(func):
    def wrapper(message):
        if check_subscription(message.from_user.id):
            return func(message)
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Подписаться", url=CHANNEL_LINK))
            bot.send_message(message.from_user.id, f"<tg-emoji emoji-id='4916105371858240403'>🔒</tg-emoji> <b>Подпишись на канал</b>\n\n{CHANNEL_LINK}", parse_mode='HTML', reply_markup=markup)
    return wrapper

def check_rate_limit(user_id, action_type='general'):
    if not hasattr(check_rate_limit, 'user_actions'):
        check_rate_limit.user_actions = defaultdict(list)
        check_rate_limit.blocked_users = {}
    current_time = time.time()
    user_actions = check_rate_limit.user_actions
    blocked_users = check_rate_limit.blocked_users
    if user_id in blocked_users:
        if current_time < blocked_users[user_id]:
            return False, "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы!</b>"
        else:
            del blocked_users[user_id]
            user_actions[user_id] = []
    if action_type == 'start':
        actions = [t for t in user_actions[user_id] if current_time - t < 5]
        if len(actions) >= 3:
            blocked_users[user_id] = current_time + 300
            user_actions[user_id] = []
            return False, "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы на 5 минут!</b>"
        user_actions[user_id].append(current_time)
        return True, None
    else:
        actions = [t for t in user_actions[user_id] if current_time - t < 3]
        if actions and (current_time - actions[-1]) < 3:
            return False, "<tg-emoji emoji-id='5134438483867206614'>⏱️</tg-emoji> <b>Подожди немного</b>"
        user_actions[user_id].append(current_time)
        return True, None

def error_handler(func):
    def wrapper(message):
        try: return func(message)
        except Exception as e: logger.error(f"Ошибка: {e}")
    return wrapper

# ==================== ГЕНЕРАЦИЯ НИКОВ ====================
def generate_fast_nick(length=5):
    patterns = patterns_5 if length == 5 else patterns_6
    pattern = random.choice(patterns)
    result = []
    for ch in pattern:
        if ch == 'C': result.append(random.choice(consonants))
        elif ch == 'V': result.append(random.choice(vowels))
        else: result.append(ch)
    nick = ''.join(result)
    for _ in range(3):
        if 'yy' in nick or 'aa' in nick or 'ii' in nick or 'uu' in nick:
            result = []
            for ch in pattern:
                if ch == 'C': result.append(random.choice(consonants))
                elif ch == 'V': result.append(random.choice(vowels))
                else: result.append(ch)
            nick = ''.join(result)
        else: break
    return nick

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("Поиск"),
        types.KeyboardButton("Рефералка"),
        types.KeyboardButton("Профиль"),
        types.KeyboardButton("Премиум")
    ]
    if user_id == ADMIN_ID:
        buttons.append(types.KeyboardButton("⚙️ АДМИН"))
    markup.add(*buttons)
    return markup

# ==================== ТЕХНИЧЕСКИЕ РАБОТЫ ====================
def maintenance_check(user_id):
    if MAINTENANCE_MODE and user_id != ADMIN_ID: return True
    return False

def maintenance_blocked(func):
    def wrapper(message):
        if maintenance_check(message.from_user.id):
            bot.send_message(message.chat.id, "🔧 <b>Бот на технических работах</b>\n\nПожалуйста, зайдите позже.", parse_mode='HTML')
            return
        return func(message)
    return wrapper

def maintenance_callback_blocked(func):
    def wrapper(call):
        if maintenance_check(call.from_user.id):
            bot.answer_callback_query(call.id, "🔧 Технические работы", show_alert=True)
            return
        return func(call)
    return wrapper

class UsernameChecker:
    def __init__(self, delay=0.05):
        self.delay = delay
        self.cache = {}
        self.cache_ttl = 300
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
    
    def check_is_banned(self, username):
        try:
            embed_r = self.session.get(f"https://t.me/{username}?embed=1", timeout=8)
            if embed_r.status_code == 200:
                embed_size = len(embed_r.text)
                if embed_size > 5000:
                    return True
                if embed_size < 3500:
                    return False
            return None
        except:
            return None
    
    def check(self, username, deep=True):
        username = username.lower().strip().replace('@', '').replace(' ', '')
        if not username or len(username) < 3: return False
        if username in self.cache:
            cached_time, result = self.cache[username]
            if time.time() - cached_time < self.cache_ttl: return result
        time.sleep(self.delay)
        try:
            r = self.session.get(f"https://t.me/{username}", timeout=8, allow_redirects=False)
            if r.status_code == 404 or r.status_code in [301, 302, 303, 307, 308]:
                self.cache[username] = (time.time(), True)
                return True
            if r.status_code == 200:
                html = r.text
                og_desc = re.search(r'<meta property="og:description" content="([^"]*)"', html)
                if og_desc:
                    if og_desc.group(1).strip() == "":
                        is_banned = self.check_is_banned(username)
                        if is_banned is True:
                            self.cache[username] = (time.time(), False)
                            return False
                        self.cache[username] = (time.time(), True)
                        return True
                    else:
                        self.cache[username] = (time.time(), False)
                        return False
                is_banned = self.check_is_banned(username)
                if is_banned is True:
                    self.cache[username] = (time.time(), False)
                    return False
                self.cache[username] = (time.time(), True)
                return True
            self.cache[username] = (time.time(), False)
            return False
        except:
            self.cache[username] = (time.time(), False)
            return False

checker = UsernameChecker(delay=0.05)

def perform_search(user_id, length, user_msg_id=None):
    if get_available_searches(user_id) <= 0:
        send_clean_message(user_id, user_id, 
            f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Лимит исчерпан!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купите премиум", 
            parse_mode='HTML', user_msg_id=user_msg_id)
        return
    
    clean_previous_interaction(user_id, user_id)
    msg = bot.send_message(user_id, f"<b><tg-emoji emoji-id='5902050947567194830'>⏰</tg-emoji> Ищу подходящий вам никнейм...</b>", parse_mode='HTML')
    last_interaction[user_id] = {"user_msg_id": user_msg_id, "bot_msg_id": msg.message_id}
    
    found_usernames = set()
    last_update = 0
    UPDATE_INTERVAL = 5
    
    for i in range(SEARCH_ATTEMPTS):
        username = generate_fast_nick(length)
        if username in found_usernames: continue
        if not checker.check(username, deep=True):
            if i - last_update >= UPDATE_INTERVAL:
                last_update = i
                try: bot.edit_message_text(f"<b><tg-emoji emoji-id='5902050947567194830'>⏰</tg-emoji> До сих пор ищу...</b>", user_id, msg.message_id, parse_mode='HTML')
                except: pass
            continue
        
        found_usernames.add(username)
        is_free = verify_with_session(username)
        if not is_free: continue
        
        use_search(user_id)
        add_found(user_id)
        price_range = estimate_price(username)
        
        try:
            with db_lock:
                cursor.execute("INSERT OR IGNORE INTO found (username, length, price, found_date, finder_id) VALUES (?, ?, ?, datetime('now'), ?)", 
                             (username, length, price_range, user_id))
                conn.commit()
        except: pass
        
        searches_left = get_available_searches(user_id)
        prem_text = "Безлимит" if has_premium(user_id) else str(searches_left)
        
        win_text = (f"<b><tg-emoji emoji-id='5895652322469482989'>📱</tg-emoji> Никнейм найден.</b>\n\n"
       f"<blockquote><b><tg-emoji emoji-id='5123344136665039833'>✝️</tg-emoji>┌ Ник:</b> @{username}\n"
       f"<b><tg-emoji emoji-id='5123344136665039833'>✝️</tg-emoji>├ Кликабельно:</b> <code>{username}</code>\n"
       f"<b><tg-emoji emoji-id='5123344136665039833'>✝️</tg-emoji>└ Букв:</b> {length}</blockquote>\n\n"
       f"<b><tg-emoji emoji-id='5904238507555033712'>⛔️</tg-emoji> У вас осталось поисков:</b> {prem_text}\n"
       f"<b><tg-emoji emoji-id='5902016123972358349'>🛡</tg-emoji> Канал:</b> {REQUIRED_CHANNEL}")
        
        search_markup = types.InlineKeyboardMarkup(row_width=2)
        search_markup.add(
            types.InlineKeyboardButton("Найти ещё", callback_data=f"search_mode_{length}"),
            types.InlineKeyboardButton("Назад", callback_data="search_back_to_menu")
        )
        
        clean_previous_interaction(user_id, user_id)
        final_msg = bot.send_message(user_id, win_text, parse_mode='HTML', reply_markup=search_markup)
        last_interaction[user_id] = {"user_msg_id": None, "bot_msg_id": final_msg.message_id}
        return
    
    clean_previous_interaction(user_id, user_id)
    fail_markup = types.InlineKeyboardMarkup()
    fail_markup.add(types.InlineKeyboardButton("Назад", callback_data="search_back_to_menu"))
    fail_msg = bot.send_message(user_id, 
        f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Не удалось найти свободный ник. Поиски не потрачены. Попробуй ещё раз.</b>", 
        parse_mode='HTML', reply_markup=fail_markup)
    last_interaction[user_id] = {"user_msg_id": None, "bot_msg_id": fail_msg.message_id}

# ==================== /start ====================
@bot.message_handler(commands=['start'])
@maintenance_blocked
@error_handler
def start(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    allowed, error_msg = check_rate_limit(user_id, 'start')
    if not allowed:
        bot.send_message(user_id, error_msg, parse_mode='HTML')
        return
    username = message.from_user.username
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id: referrer_id = None
        except: pass
    user, is_new = create_user(user_id, username, referrer_id)
    if check_subscription(user_id):
        activate_referral(user_id)
        welcome = (f"<b><tg-emoji emoji-id='5895338626648117927'>⭐</tg-emoji> ДОБРО ПОЖАЛОВАТЬ!</b>\n\n"
                  f"<b><tg-emoji emoji-id='5893072412924187198'>💎</tg-emoji> Что тут есть:</b>\n"
                  f"<blockquote><b><tg-emoji emoji-id='5339113303522161846'>⭐</tg-emoji> Поиск 5-6 значных юзернеймов</b>\n"
                  f"<b><tg-emoji emoji-id='5339113303522161846'>⭐</tg-emoji> Поиск по слову</b>\n"
                  f"<b><tg-emoji emoji-id='5339113303522161846'>⭐</tg-emoji> Поиск по фильтру</b></blockquote>\n\n"
                  f"<b><tg-emoji emoji-id='5895652322469482989'>💎</tg-emoji> Premium от 50 stars — безлимит + все функции</b>\n\n"
                  f"<b><tg-emoji emoji-id='5904692292324692386'>⚠️</tg-emoji> Бот может иногда выдавать занятые юзернеймы.</b>")
        bot.send_photo(user_id, photo="https://i.postimg.cc/PqfGg2zv/Picsart-26-06-05-14-31-15-543.jpg", caption=welcome, parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Подписаться", url=CHANNEL_LINK))
        bot.send_message(user_id, "<b><tg-emoji emoji-id='5893365724830765382'>💎</tg-emoji> Чтобы продолжить, подпишись на канал, и нажми /start.</b>", parse_mode='HTML', reply_markup=markup)

# ==================== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (МЕНЮ И Т.Д.) ====================
# Здесь остается весь твой остальной код до функции Premium без изменений...
# (Поиск, фильтр, слова, профиль, рефералка и т.д. Я их сократил визуально, чтобы не засорять ответ, 
# но ты их оставляй как есть в своем файле).

# ==================== ПРЕМИУМ (ВОССТАНОВЛЕННАЯ ФУНКЦИЯ) ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_sel_'))
def premium_selection_callback(call):
    days = int(call.data.split('_')[-1])
    price_stars = PREMIUM_PRICES[days]
    
    text = (f"<b><tg-emoji emoji-id='5904692292324692386'>💳</tg-emoji> Оплата</b>\n\n"
            f"<b><tg-emoji emoji-id='5902056028513505203'>🍀</tg-emoji> Вы выбрали:</b>\n"
            f"<blockquote><b><tg-emoji emoji-id='5893402730268987918'>⚠️</tg-emoji> дней: {days} дн.</b>\n"
            f"<b><tg-emoji emoji-id='5893224751119208859'>⭐</tg-emoji> К оплате: {price_stars} Stars</b></blockquote>\n\n"
            f"Оплата происходит в автоматическом режиме.")
    
    markup = types.InlineKeyboardMarkup()
    # Заглушка для оплаты. Тебе нужно будет подключить Invoice или Cryptobot
    markup.add(types.InlineKeyboardButton(f"Оплатить {price_stars} Stars", pay=True)) 
    markup.add(types.InlineKeyboardButton("Назад", callback_data="search_close"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

# ==================== МОДЕРАЦИЯ И ИИ-ОБЩЕНИЕ ====================
@bot.message_handler(func=lambda message: True)
@error_handler
def chat_and_moderate(message):
    chat_id = message.chat.id
    text = message.text.lower() if message.text else ""

    # 1. Жесткая модерация (работает везде: в ЛС бота и в группах)
    if any(word in text for word in FORBIDDEN_WORDS):
        try:
            bot.delete_message(chat_id, message.message_id)
            warning = f"🚫 <b>Модерация:</b> @{message.from_user.username or message.from_user.first_name}, такие выражения запрещены!"
            bot.send_message(chat_id, warning, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение (возможно нет прав админа): {e}")
        return

    # 2. Общение (Консультант работает в ЛС или если бота тегнули в группе)
    if message.chat.type == 'private' or (bot.get_me().username and f"@{bot.get_me().username}" in text):
        
        if GEMINI_API_KEY == "ТВОЙ_GEMINI_API_КЛЮЧ":
            bot.reply_to(message, "Я пока не умею общаться. Хозяин еще не вставил мой API-ключ мозгов 🧠.")
            return
        
        try:
            # Отправляем сообщение ИИ
            bot.send_chat_action(chat_id, 'typing')
            response = model.generate_content(message.text)
            bot.reply_to(message, response.text)
        except Exception as e:
            logger.error(f"Ошибка ИИ: {e}")
            bot.reply_to(message, "Я немного задумался и не могу сейчас ответить. Попробуй чуть позже ⚙️")

# ==================== ЗАПУСК БОТА ====================
if __name__ == '__main__':
    logger.info("🤖 Бот успешно запущен!")
    bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
