import re
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import ChatBannedRights
from telethon.tl.functions.channels import EditBannedRequest
from telethon.errors import ChatAdminRequiredError
from config import *
from database import Database

db = Database("moderator.db")
bot = TelegramClient("bot_session", api_id=API_ID, api_hash=API_HASH)


REPLACES = str.maketrans({
    'а': 'а', 'А': 'а',
    'е': 'е', 'Е': 'е',
    'о': 'о', 'О': 'о',
    'с': 'с', 'С': 'с',
    'р': 'р', 'Р': 'р',
    'х': 'х', 'Х': 'х',
    'у': 'у', 'У': 'у',
    'к': 'к', 'К': 'к',
    'м': 'м', 'М': 'м',
    'н': 'н', 'Н': 'н',
    'т': 'т', 'Т': 'т',
    'в': 'в', 'В': 'в',
    'б': 'б', 'Б': 'б',
    'и': 'и', 'И': 'и',
    'з': 'з', 'З': 'з',
    'д': 'д', 'Д': 'д',
    'л': 'л', 'Л': 'л',
    'п': 'п', 'П': 'п',
    'ф': 'ф', 'Ф': 'ф',
    'г': 'г', 'Г': 'г',
    'ч': 'ч', 'Ч': 'ч',
    'ш': 'ш', 'Ш': 'ш',
    'щ': 'щ', 'Щ': 'щ',
    'ж': 'ж', 'Ж': 'ж',
    'й': 'й', 'Й': 'й',
    'ц': 'ц', 'Ц': 'ц',
    'ь': 'ь', 'Ь': 'ь',
    'ъ': 'ъ', 'Ъ': 'ъ',
    'э': 'э', 'Э': 'э',
    'ю': 'ю', 'Ю': 'ю',
    'я': 'я', 'Я': 'я',
    'ё': 'е', 'Ё': 'е',
    'ї': 'и', 'Ї': 'и',
    'є': 'е', 'Є': 'е',
    'і': 'и', 'І': 'и',
    'ґ': 'г', 'Ґ': 'г',
    
    '0': 'о', '1': 'и', '2': 'з', '3': 'з', '4': 'ч',
    '5': 'с', '6': 'б', '7': 'т', '8': 'в', '9': 'д',
    
    # Спецсимволы -> буквы
    '@': 'а', '#': 'н', '$': 'с', '%': 'о',
    '^': 'л', '&': 'и', '*': 'х', '(': 'с', ')': 'с',
    '+': 'т', '=': 'е', '{': 'и', '}': 'и',
    '[': 'и', ']': 'и', '|': 'л', '/': 'л', '\\': 'л',
    
    # Unicode lookalikes
    'à': 'а', 'á': 'а', 'â': 'а', 'ã': 'а', 'ä': 'а', 'å': 'а',
    'è': 'е', 'é': 'е', 'ê': 'е', 'ë': 'е',
    'ì': 'и', 'í': 'и', 'î': 'и', 'ï': 'и',
    'ò': 'о', 'ó': 'о', 'ô': 'о', 'õ': 'о', 'ö': 'о',
    'ù': 'у', 'ú': 'у', 'û': 'у', 'ü': 'у',
    'ñ': 'н', 'ç': 'с', 'ş': 'с', 'š': 'с',
    'ř': 'р', 'þ': 'р',
    'ý': 'у', 'ÿ': 'у',
    'œ': 'о', 'æ': 'а',
    'α': 'а', 'β': 'б', 'γ': 'г', 'δ': 'д', 'ε': 'е',
    'ζ': 'з', 'η': 'н', 'θ': 'о', 'ι': 'и', 'κ': 'к',
    'λ': 'л', 'μ': 'м', 'ν': 'н', 'ξ': 'к', 'ο': 'о',
    'π': 'п', 'ρ': 'р', 'σ': 'с', 'τ': 'т', 'υ': 'у',
    'φ': 'ф', 'χ': 'х', 'ψ': 'п', 'ω': 'о',
    
    # Разделители -> ничего (удаляем)
    ' ': '', '.': '', ',': '', '/': '', '|': '', '\\': '',
    '*': '', '_': '', '-': '', '+': '', '=': '', ':': '',
    ';': '', '"': '', "'": '', '`': '', '~': '', '!': '',
    '?': '', '^': '', '&': '', '%': '', '$': '', '#': '',
    '@': '', '(': '', ')': '', '{': '', '}': '', '[': '',
    ']': '', '<': '', '>': '', '«': '', '»': '', '„': '',
    '"': '', '′': '', '‴': '', '›': '', '‹': '',
    '∙': '', '⋅': '', '⋆': '', '⋄': '', '∘': '', '∙': '',
    '⬤': '', '●': '', '○': '', '◉': '', '◎': '', '◯': '',
    '﻿': '',  # Zero-width no-break space
    '​': '',  # Zero-width space
    '‌': '',  # Zero-width non-joiner
    '‍': '',  # Zero-width joiner
    '‎': '',  # Left-to-right mark
    '‏': '',  # Right-to-left mark
})


def super_normalize(text):
    """Максимальная нормализация текста"""
    if not text:
        return ""
    
    # В нижний регистр
    text = text.lower()
    
    # Применяем таблицу замены
    text = text.translate(REPLACES)
    
    # Убираем всё кроме букв
    text = re.sub(r'[^а-яёa-z]', '', text)
    
    # Убираем повторяющиеся буквы (для защиты от "ззззаараабоотток")
    text = re.sub(r'(.)\1+', r'\1', text)
    
    return text


def is_forbidden(text):
    """Проверка с максимальной защитой"""
    if not text:
        return None
    
    # Нормализуем входящий текст
    clean = super_normalize(text)
    
    if len(clean) < 2:
        return None
    
    words = db.get_all_words()
    
    for word in words:
        # Нормализуем запрещённое слово
        w_clean = super_normalize(word)
        
        if len(w_clean) < 2:
            continue
        
        # 1. Прямое вхождение
        if w_clean in clean:
            return word
        
        # 2. Побуквенное вхождение (для "з а р а б о т о к")
        pattern = '.*'.join(re.escape(c) for c in w_clean)
        if re.search(pattern, clean):
            return word
        
        # 3. Вхождение с лишними буквами ("ззаработок")
        if len(clean) >= len(w_clean):
            for i in range(len(clean) - len(w_clean) + 1):
                # Проверяем подстроку на побуквенное совпадение
                sub = clean[i:i + len(w_clean) * 3]  # С запасом
                if re.search(pattern, sub):
                    return word
        
        # 4. Буквы в любом порядке но рядом
        if len(w_clean) <= len(clean):
            w_sorted = ''.join(sorted(w_clean))
            for i in range(len(clean) - len(w_clean) + 1):
                chunk = clean[i:i + len(w_clean) + 2]
                if len(chunk) >= len(w_clean):
                    # Проверяем что все буквы слова есть в chunk
                    if all(c in chunk for c in w_clean):
                        # И они в правильном порядке
                        idx = 0
                        for c in chunk:
                            if idx < len(w_clean) and c == w_clean[idx]:
                                idx += 1
                        if idx == len(w_clean):
                            return word
    
    return None


# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========

def get_role(user_id):
    if user_id == OWNER_ID: return "owner"
    admin = db.get_admin(user_id)
    if admin: return admin
    return "user"


def can(user_id, action):
    perms = {
        "owner": ["warn","unwarn","mute","unmute","ban","unban","add_word","del_word","list_words","add_admin","del_admin","list_admins","emoji"],
        "senior_admin": ["warn","unwarn","mute","unmute","ban","unban"],
        "admin": ["warn","unwarn","mute","unmute","ban"],
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
        return True
    except:
        return False


async def check_punish(uid):
    count = db.count_warns(uid)
    for num, (act, mins) in sorted(PUNISHMENTS.items()):
        if count >= num:
            if not db.get_active_punishment(uid):
                return act, mins, num
    return None, 0, 0


async def auto_del(msg, sec):
    if sec > 0:
        await asyncio.sleep(sec)
        try: await msg.delete()
        except: pass


# ========== АВТО-МОДЕРАЦИЯ ==========

@bot.on(events.NewMessage(chats=[CHAT_ID]))
async def auto_mod(event):
    text = event.message.text or ""
    word = is_forbidden(text)
    if not word: return
    try: await event.message.delete()
    except: pass
    uid = event.sender_id
    db.add_warn(uid, 0, f"Запрещённое слово: {word}", 0)
    count = db.count_warns(uid)
    act, mins, num = await check_punish(uid)
    if act: await punish(event.chat_id, await event.get_sender(), uid, act, mins)
    name = event.sender.first_name or "Юзер"
    msg = await event.respond(f"Авто-модерация\n└ {name} — запрещённое слово\n└ Варнов: {count}")
    asyncio.create_task(auto_del(msg, DELETE_WARN_MSG_AFTER))


# ========== КОМАНДЫ ==========

@bot.on(events.NewMessage(pattern=r"(?i)^(команды|команда|help)$", chats=[CHAT_ID]))
async def cmd_help(event):
    role = get_role(event.sender_id)
    if role == "owner":
        t = """<b>Владелец</b>

<b>Общие:</b>
└ <code>команды</code> — список команд
└ <code>инфо</code> — информация
└ <code>мои варны</code> — свои предупреждения

<b>Модерация:</b>
└ <code>варн</code> — выдать (+ <code>-смс</code>)
└ <code>анварн</code> — снять последний
└ <code>варны</code> — список
└ <code>мут</code> — замутить (<code>1м</code>/<code>1ч</code>/<code>1д</code>)
└ <code>размут</code> — размутить
└ <code>бан</code> — забанить
└ <code>разбан</code> — разбанить

<b>Управление:</b>
└ <code>добавить слово</code>
└ <code>удалить слово</code>
└ <code>список слов</code>
└ <code>добавить админ</code>
└ <code>удалить админ</code>
└ <code>список админов</code>

<b>Прочее:</b>
└ <code>премиум эмодзи</code>"""
    elif role == "senior_admin":
        t = """<b>Ст. Админ</b>

<b>Общие:</b>
└ <code>команды</code>
└ <code>инфо</code>
└ <code>мои варны</code>

<b>Модерация:</b>
└ <code>варн</code> (+ <code>-смс</code>)
└ <code>анварн</code>
└ <code>варны</code>
└ <code>мут</code> (<code>1м</code>/<code>1ч</code>/<code>1д</code>)
└ <code>размут</code>
└ <code>бан</code>
└ <code>разбан</code>"""
    elif role == "admin":
        t = """<b>Админ</b>

<b>Общие:</b>
└ <code>команды</code>
└ <code>инфо</code>
└ <code>мои варны</code>

<b>Модерация:</b>
└ <code>варн</code> (+ <code>-смс</code>)
└ <code>анварн</code>
└ <code>варны</code>
└ <code>мут</code> (<code>1м</code>/<code>1ч</code>/<code>1д</code>)
└ <code>размут</code>
└ <code>бан</code>"""
    else:
        t = """<b>Пользователь</b>

<b>Общие:</b>
└ <code>команды</code>
└ <code>инфо</code>
└ <code>мои варны</code>"""
    await event.reply(t, parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^инфо", chats=[CHAT_ID]))
async def cmd_info(event):
    target = await get_reply_sender(event) or await event.get_sender()
    uid = target.id
    role = get_role(uid)
    warns = db.count_warns(uid)
    name = f"{target.first_name or ''} {target.last_name or ''}".strip()
    uname = f"@{target.username}" if target.username else "нет"
    roles = {"owner":"Владелец","senior_admin":"Ст. Админ","admin":"Админ"}
    rname = roles.get(role, "Пользователь")
    await event.reply(
        f"<b>Информация</b>\n\n"
        f"Имя: <b>{name}</b>\n"
        f"└ Username: {uname}\n"
        f"└ ID: <code>{uid}</code>\n"
        f"└ Роль: {rname}\n\n"
        f"Варнов: <b>{warns}</b>",
        parse_mode="html"
    )


@bot.on(events.NewMessage(pattern=r"(?i)^мои варны$", chats=[CHAT_ID]))
async def cmd_mywarns(event):
    w = db.get_warns(event.sender_id)
    if not w: return await event.reply("Нет предупреждений")
    t = f"<b>Ваши варны:</b> {len(w)}\n\n"
    for i, (wid, reason, date, silent) in enumerate(w, 1):
        s = " [тихо]" if silent else ""
        r = reason or "—"
        t += f"{i}. <code>#{wid}</code> {r}{s}\n└ {date}\n\n"
    await event.reply(t, parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^варн\b", chats=[CHAT_ID]))
async def cmd_warn(event):
    if not can(event.sender_id, "warn"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    tid = target.id
    if tid == OWNER_ID: return await event.reply("Нельзя владельца")
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
    db.add_warn(tid, event.sender_id, reason, 1 if silent else 0)
    count = db.count_warns(tid)
    act, mins, _ = await check_punish(tid)
    if act: await punish(event.chat_id, target, tid, act, mins)
    if not silent:
        t = f"<b>Варн</b>\n\n└ Кому: <b>{target.first_name}</b>\n└ От: <b>{event.sender.first_name}</b>\n└ Причина: {reason or '—'}\n└ Варнов: <b>{count}</b>"
        if act:
            t += f"\n└ {'Мут на '+format_time(mins) if act=='мут' else 'Бан'}"
        msg = await event.reply(t, parse_mode="html")
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
    await event.reply(f"Варн <code>#{last[0]}</code> снят с <b>{target.first_name}</b>\n└ Осталось: <b>{db.count_warns(target.id)}</b>", parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^варны$", chats=[CHAT_ID]))
async def cmd_warns(event):
    if not can(event.sender_id, "unwarn"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    w = db.get_warns(target.id)
    if not w: return await event.reply(f"У {target.first_name} нет варнов")
    t = f"<b>Варны {target.first_name}:</b> {len(w)}\n\n"
    for i, (wid, reason, date, silent) in enumerate(w, 1):
        s = " [тихо]" if silent else ""
        r = reason or "—"
        t += f"{i}. <code>#{wid}</code> {r}{s}\n└ {date}\n\n"
    await event.reply(t, parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^мут\b", chats=[CHAT_ID]))
async def cmd_mute(event):
    if not can(event.sender_id, "mute"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    parts = event.text.split(maxsplit=1)
    if len(parts) < 2: return await event.reply("Укажите время: <code>мут 1ч</code>", parse_mode="html")
    t = parse_time(parts[1])
    if not t: return await event.reply("Формат: <code>1м</code> / <code>1ч</code> / <code>1д</code>", parse_mode="html")
    minutes = int(t.total_seconds() // 60)
    if await punish(event.chat_id, target, target.id, "мут", minutes):
        await event.reply(f"<b>{target.first_name}</b> замучен на <b>{format_time(minutes)}</b>", parse_mode="html")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^размут", chats=[CHAT_ID]))
async def cmd_unmute(event):
    if not can(event.sender_id, "unmute"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if await punish(event.chat_id, target, target.id, "размут"):
        await event.reply(f"<b>{target.first_name}</b> размучен", parse_mode="html")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^бан\b", chats=[CHAT_ID]))
async def cmd_ban(event):
    if not can(event.sender_id, "ban"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    tid = target.id
    if tid == OWNER_ID: return await event.reply("Нельзя владельца")
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
        dur = f"на <b>{format_time(minutes)}</b>" if minutes else "<b>навсегда</b>"
        t = f"<b>{target.first_name}</b> забанен {dur}"
        if reason: t += f"\n└ {reason}"
        await event.reply(t, parse_mode="html")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^разбан", chats=[CHAT_ID]))
async def cmd_unban(event):
    if not can(event.sender_id, "unban"): return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if await punish(event.chat_id, target, target.id, "разбан"):
        await event.reply(f"<b>{target.first_name}</b> разбанен", parse_mode="html")
    else:
        await event.reply("Ошибка прав")


@bot.on(events.NewMessage(pattern=r"(?i)^добавить слово", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^добавить слово", from_users=[OWNER_ID]))
async def cmd_addword(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return await event.reply("Формат: <code>добавить слово текст</code>", parse_mode="html")
    word = parts[2].lower()
    if db.add_word(word, event.sender_id):
        await event.reply(f"Слово <b>\"{word}\"</b> добавлено", parse_mode="html")
    else:
        await event.reply(f"Слово <b>\"{word}\"</b> уже есть", parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^удалить слово", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^удалить слово", from_users=[OWNER_ID]))
async def cmd_delword(event):
    if get_role(event.sender_id) != "owner": return
    parts = event.text.split(maxsplit=2)
    if len(parts) < 3: return await event.reply("Формат: <code>удалить слово текст</code>", parse_mode="html")
    if db.remove_word(parts[2].lower()):
        await event.reply(f"Слово <b>\"{parts[2]}\"</b> удалено", parse_mode="html")
    else:
        await event.reply(f"Слово <b>\"{parts[2]}\"</b> не найдено", parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^список слов$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^список слов$", from_users=[OWNER_ID]))
async def cmd_listwords(event):
    if get_role(event.sender_id) != "owner": return
    words = db.get_all_words()
    if not words: return await event.reply("Список пуст")
    t = f"<b>Слова:</b> {len(words)}\n\n"
    for i, w in enumerate(words, 1):
        t += f"{i}. <code>{w}</code>\n"
    await event.reply(t, parse_mode="html")


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
    await event.reply(f"<b>{target.first_name}</b> теперь <b>{r}</b>", parse_mode="html")


@bot.on(events.NewMessage(pattern=r"(?i)^удалить админ", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^удалить админ", from_users=[OWNER_ID]))
async def cmd_deladmin(event):
    if get_role(event.sender_id) != "owner": return
    target = await get_reply_sender(event)
    if not target: return await event.reply("Ответьте на сообщение")
    if target.id == OWNER_ID: return await event.reply("Нельзя снять владельца")
    if db.remove_admin(target.id):
        await event.reply(f"<b>{target.first_name}</b> снят с админов", parse_mode="html")
    else:
        await event.reply("Не админ")


@bot.on(events.NewMessage(pattern=r"(?i)^список админов$", chats=[CHAT_ID]))
@bot.on(events.NewMessage(pattern=r"(?i)^список админов$", from_users=[OWNER_ID]))
async def cmd_listadmins(event):
    if get_role(event.sender_id) != "owner": return
    admins = db.get_all_admins()
    t = f"<b>Админы:</b>\n\n<code>{OWNER_ID}</code> — Владелец\n"
    for uid, role in admins:
        r = "Ст." if role == "senior_admin" else ""
        t += f"<code>{uid}</code> {r}\n"
    await event.reply(t, parse_mode="html")


@bot.on(events.NewMessage(func=lambda e: e.is_private and e.sender_id != OWNER_ID))
async def dm_block(event):
    pass


async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("Бот запущен")
    await bot.run_until_disconnected()

asyncio.run(main())