# -*- coding: utf-8 -*-
import logging
import aiohttp
import json
import os
from dotenv import load_dotenv

# загружаем переменные из .env
load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
DEPSEARCH_TOKEN = os.getenv("DEPSEARCH_TOKEN")


import asyncio
import re
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Set
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)
from aiogram.enums import ParseMode
from collections import defaultdict
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- Конфигурация ---
API_TOKEN = os.getenv("API_TOKEN")
DEPSEARCH_TOKEN = os.getenv("DEPSEARCH_TOKEN")

ADMINS = [7409003051]
VIP_USERS = [968630098]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_FILE = os.path.join(BASE_DIR, "users.txt")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

CHANNEL_USERNAME = "@internetzuk"
CHANNEL_LINK = "https://t.me/internetzuk"
FLOOD_LIMIT = 1
REFERRAL_BONUS = 1
TEMP_FILES_DIR = os.path.join(BASE_DIR, "temp_files")
BOT_USERNAME = "@Internetzukbot"

os.makedirs(TEMP_FILES_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Состояния для FSM ---
class SearchState(StatesGroup):
    choosing_search_type = State()
    waiting_for_phone = State()
    waiting_for_email = State()
    waiting_for_nickname = State()
    waiting_for_social = State()
    waiting_for_vkid = State()
    waiting_for_vk_link = State()
    waiting_for_tgid = State()
    waiting_for_tg_link = State()
    waiting_for_okid = State()
    waiting_for_fcid = State()

class AdminState(StatesGroup):
    awaiting_broadcast_text = State()
    awaiting_vip_id = State()

# --- Лимиты запросов ---
LIMITS = {
    "admin": float('inf'),
    "vip": 30,
    "default": 5
}

# --- Клавиатуры ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Поиск"), KeyboardButton(text="❓ Помощь")],
        [KeyboardButton(text="🤖 О боте"), KeyboardButton(text="📈 Мой статус")],
        [KeyboardButton(text="🤝 Пригласить друга"), KeyboardButton(text="💎 Купить VIP со скидкой")]
    ],
    resize_keyboard=True
)

search_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📱 По номеру телефона", callback_data="search_phone")],
        [InlineKeyboardButton(text="📧 По email", callback_data="search_email")],
        [InlineKeyboardButton(text="👤 По нику", callback_data="search_nickname")],
        [InlineKeyboardButton(text="🌐 По соцсетям", callback_data="search_social")],
    ]
)

social_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="ВКонтакте", callback_data="social_vk")],
        [InlineKeyboardButton(text="Telegram", callback_data="social_tg")],
        [InlineKeyboardButton(text="Одноклассники", callback_data="social_ok")],
        [InlineKeyboardButton(text="Facebook", callback_data="social_fc")],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="back_to_search_type")]
    ]
)

vk_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="VK ID", callback_data="social_vk_id")],
        [InlineKeyboardButton(text="VK Ссылка", callback_data="social_vk_link")],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="back_to_social")]
    ]
)

tg_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="TG ID", callback_data="social_tg_id")],
        [InlineKeyboardButton(text="TG Ссылка", callback_data="social_tg_link")],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="back_to_social")]
    ]
)

ok_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="OK ID", callback_data="social_ok_id")],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="back_to_social")]
    ]
)

fc_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="FC ID", callback_data="social_fc_id")],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="back_to_social")]
    ]
)

admin_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📣 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="➕ Выдать VIP", callback_data="admin_add_vip")],
        [InlineKeyboardButton(text="📄 Получить базу", callback_data="admin_get_users")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ]
)

# --- Кеш и защита от флуда ---
results_cache = {}
user_last_request = defaultdict(float)

# --- Функции работы с данными ---
def load_user_data() -> Dict:
    """Загружает данные пользователей из JSON файла."""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Ошибка загрузки user_data: {e}")
            return {}
    return {}

def save_user_data(data: Dict) -> None:
    """Безопасно сохраняет данные пользователей в JSON файл."""
    temp_file = USER_DATA_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(temp_file, USER_DATA_FILE)
        logger.info("Данные пользователей успешно сохранены.")
    except Exception as e:
        logger.error(f"Ошибка сохранения user_data: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

def get_current_date() -> str:
    """Возвращает текущую дату в формате YYYY-MM-DD."""
    return str(date.today())

def get_user_limit(user_id: int) -> int:
    """Определяет лимит запросов для пользователя."""
    user_data = load_user_data()
    is_vip = user_data.get(str(user_id), {}).get("is_vip", False) or user_id in VIP_USERS
    
    if user_id in ADMINS:
        return float('inf')
    elif is_vip:
        return LIMITS["vip"]
    return LIMITS["default"]

def initialize_user_data(user_id: int) -> dict:
    """Создает словарь с данными для нового пользователя."""
    return {
        "search_count": 0,
        "last_search_date": get_current_date(),
        "is_admin": user_id in ADMINS,
        "is_vip": user_id in VIP_USERS,
        "subscribed": True,
        "queries": [],
        "referred_by": None,
        "referrals_count": 0,
    }

async def check_subscription(user_id: int) -> bool:
    """Проверяет подписку пользователя на канал."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id} в {CHANNEL_USERNAME}: {e}")
        return False

async def require_subscription(message: Message):
    """Отправляет сообщение с просьбой подписаться на канал."""
    subscribe_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Подписаться на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")]
        ]
    )
    try:
        await message.answer(
            "❗️ **Для использования бота необходимо подписаться на наш канал!**\n\n"
            "После подписки нажмите кнопку 'Я подписался'",
            reply_markup=subscribe_kb,
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramForbiddenError:
        logger.warning(f"Пользователь {message.from_user.id} заблокировал бота.")
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения о подписке пользователю {message.from_user.id}: {e}")

async def notify_admin(text: str):
    """Отправляет уведомление всем администраторам."""
    for admin_id in ADMINS:
        try:
            await bot.send_message(admin_id, f"(Уведомление): {text}")
        except TelegramForbiddenError:
            logger.warning(f"Админ {admin_id} заблокировал бота. Не удалось отправить уведомление.")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

async def detect_operator_info(phone: str) -> Dict[str, str]:
    """Определяет оператора и регион по номеру телефона."""
    phone = phone.strip().replace("+", "").replace(" ", "")
    ukr_data = {
        '039': {'operator': 'Киевстар', 'region': 'Запад (Львов, Ивано-Франковск)'}, '050': {'operator': 'Vodafone', 'region': 'Центр/Восток (Киев, Харьков)'}, '063': {'operator': 'lifecell', 'region': 'Юг (Одесса, Николаев)'}, '066': {'operator': 'Vodafone', 'region': 'Днепр, Запорожье'}, '067': {'operator': 'Киевстар', 'region': 'Север (Чернигов, Сумы)'}, '068': {'operator': 'Киевстар', 'region': 'Центр (Киев, Винница)'}, '073': {'operator': 'lifecell', 'region': 'Центр (Полтава, Черкассы)'}, '091': {'operator': 'TriMob', 'region': 'Крым*'}, '092': {'operator': 'PEOPLEnet', 'region': 'Киев, Одесса'}, '093': {'operator': 'lifecell', 'region': 'Восток (Донецк, Луганск)*'}, '094': {'operator': 'Інтертелеком', 'region': 'Юг (Херсон)'}, '095': {'operator': 'Vodafone', 'region': 'Крым*'}, '096': {'operator': 'Киевстар', 'region': 'Центр (Киев, Житомир)'}, '097': {'operator': 'Киевстар', 'region': 'Восток (Днепр, Кривой Рог)'}, '098': {'operator': 'Киевстар', 'region': 'Запад (Тернополь, Ровно)'}, '099': {'operator': 'Vodafone', 'region': 'Север (Чернигов, Сумы)'},
    }
    ru_data = {
        '900': {'operator': 'Tele2', 'region': 'Москва, СПб'}, '901': {'operator': 'МТС', 'region': 'Москва'}, '902': {'operator': 'МТС', 'region': 'Дальний Восток'}, '903': {'operator': 'МТС', 'region': 'Сибирь'}, '904': {'operator': 'МТС', 'region': 'Урал'}, '905': {'operator': 'МТС', 'region': 'Центр'}, '906': {'operator': 'МТС', 'region': 'Поволжье'}, '908': {'operator': 'МТС', 'region': 'Северо-Запад'}, '909': {'operator': 'МТС', 'region': 'Юг'}, '910': {'operator': 'МТС', 'region': 'Центр'}, '911': {'operator': 'МТС', 'region': 'Северо-Запад'}, '912': {'operator': 'МТС', 'region': 'Урал'}, '913': {'operator': 'МТС', 'region': 'Сибирь'}, '914': {'operator': 'МТС', 'region': 'Дальний Восток'}, '915': {'operator': 'МТС', 'region': 'Центр'}, '916': {'operator': 'МТС', 'region': 'Центр'}, '917': {'operator': 'МТС', 'region': 'Поволжье'}, '918': {'operator': 'МТС', 'region': 'Юг'}, '919': {'operator': 'МТС', 'region': 'Центр'}, '920': {'operator': 'Мегафон', 'region': 'Москва'}, '921': {'operator': 'Мегафон', 'region': 'СПб'}, '922': {'operator': 'Мегафон', 'region': 'Урал'}, '923': {'operator': 'Мегафон', 'region': 'Сибирь'}, '924': {'operator': 'Мегафон', 'region': 'Дальний Восток'}, '925': {'operator': 'Мегафон', 'region': 'Центр'}, '926': {'operator': 'Мегафон', 'region': 'Москва'}, '927': {'operator': 'Мегафон', 'region': 'Поволжье'}, '928': {'operator': 'Мегафон', 'region': 'Юг'}, '929': {'operator': 'Мегафон', 'region': 'Центр'}, '930': {'operator': 'Мегафон', 'region': 'Центр'}, '931': {'operator': 'Мегафон', 'region': 'Северо-Запад'}, '932': {'operator': 'Мегафон', 'region': 'Сибирь'}, '933': {'operator': 'Мегафон', 'region': 'Дальний Восток'}, '934': {'operator': 'Мегафон', 'region': 'Северный Кавказ'}, '936': {'operator': 'Мегафон', 'region': 'Центр'}, '937': {'operator': 'Мегафон', 'region': 'Поволжье'}, '938': {'operator': 'Мегафон', 'region': 'Северо-Запад'}, '939': {'operator': 'Мегафон', 'region': 'Юг'}, '950': {'operator': 'Билайн', 'region': 'Москва'}, '951': {'operator': 'Билайн', 'region': 'Поволжье'}, '952': {'operator': 'Билайн', 'region': 'Северо-Запад'}, '953': {'operator': 'Билайн', 'region': 'Сибирь'}, '954': {'operator': 'Билайн', 'region': 'Дальний Восток'}, '955': {'operator': 'Билайн', 'region': 'Центр'}, '956': {'operator': 'Билайн', 'region': 'Урал'}, '958': {'operator': 'Билайн', 'region': 'Центр'}, '960': {'operator': 'Билайн', 'region': 'Москва'}, '961': {'operator': 'Билайн', 'region': 'Юг'}, '962': {'operator': 'Билайн', 'region': 'Центр'}, '963': {'operator': 'Билайн', 'region': 'Сибирь'}, '964': {'operator': 'Билайн', 'region': 'Дальний Восток'}, '965': {'operator': 'Билайн', 'region': 'Центр'}, '966': {'operator': 'Билайн', 'region': 'Москва'}, '967': {'operator': 'Билайн', 'region': 'Поволжье'}, '968': {'operator': 'Билайн', 'region': 'Северо-Запад'}, '969': {'operator': 'Билайн', 'region': 'Москва'}, '970': {'operator': 'Билайн', 'region': 'Москва'}, '971': {'operator': 'Билайн', 'region': 'СПб'}, '980': {'operator': 'МТС', 'region': 'Москва'}, '981': {'operator': 'МТС', 'region': 'СПб'}, '982': {'operator': 'МТС', 'region': 'Центр'}, '983': {'operator': 'МТС', 'region': 'Сибирь'}, '984': {'operator': 'МТС', 'region': 'Дальний Восток'}, '985': {'operator': 'МТС', 'region': 'Центр'}, '986': {'operator': 'МТС', 'region': 'Поволжье'}, '987': {'operator': 'МТС', 'region': 'Урал'}, '988': {'operator': 'МТС', 'region': 'Юг'}, '989': {'operator': 'МТС', 'region': 'Северо-Запад'},
    }
    if phone.startswith('380') and len(phone) == 12:
        code = phone[3:5]
        return ukr_data.get(code, {'operator': 'Неизвестно', 'region': 'Неизвестно'})
    elif phone.startswith('7') and len(phone) == 11:
        code = phone[1:4]
        return ru_data.get(code, {'operator': 'Неизвестно', 'region': 'Неизвестно'})
    return {'operator': 'Неизвестно', 'region': 'Неизвестно'}


def split_message(text: str, chunk_size: int = 4000) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    parts = []
    current_chunk = ""
    lines = text.split('\n')
    for line in lines:
        if len(current_chunk) + len(line) + 1 > chunk_size:
            parts.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += "\n" + line if current_chunk else line
    if current_chunk:
        parts.append(current_chunk)
    return parts

async def generate_html_report(query_type: str, query_value: str, data: dict) -> str:
    """
    Генерирует HTML-отчет на основе предоставленных данных.
    """
    results = data.get('results', [])

    # Блок с информацией об операторе, только для поиска по телефону
    operator_info_html = ""
    if query_type == "phone":
        op_info = await detect_operator_info(query_value)
        operator_info_html = f"""
    <div class="section-title">ИНФОРМАЦИЯ ОБ ОПЕРАТОРЕ</div>
    <div class="info-block">
        <div class="info-item">
            <strong>ОПЕРАТОР:</strong>
            <span>{op_info['operator']}</span>
        </div>
        <div class="info-item">
            <strong>РЕГИОН:</strong>
            <span>{op_info['region']}</span>
        </div>
    </div>
        """

    # Создаем HTML для каждой записи
    records_html = []
    for i, record in enumerate(results):
        record_items = []
        for key, value in record.items():
            if key in ["data", "source", "database"]:
                continue
            
            display_key = key.replace('_', ' ').capitalize().upper()
            
            display_value = ""
            if isinstance(value, list):
                display_value = ", ".join(str(item) for item in value)
            elif isinstance(value, dict):
                nested_items = [f"<strong>{sub_key.replace('_', ' ').capitalize().upper()}:</strong> {sub_value}" for sub_key, sub_value in value.items()]
                display_value = "<br>".join(nested_items)
            else:
                display_value = str(value)
            
            record_items.append(f"<li><strong>{display_key}:</strong> {display_value}</li>")
        
        sources_list = []
        if record.get('data'): sources_list.append(f"<code>{record['data']}</code>")
        if record.get('source'): sources_list.append(f"<code>{record['source']}</code>")
        if record.get('database'): sources_list.append(f"<code>{record['database']}</code>")
        if sources_list:
            record_items.append(f"<li><strong>ИСТОЧНИК:</strong> {', '.join(sources_list)}</li>")

        records_html.append(f"""
    <div class="record-card">
        <div class="record-header">
            <h4>ЗАПИСЬ #{i + 1}</h4>
            <div class="toggle-icon">▼</div>
        </div>
        <div class="record-details">
            <ul>
                {"".join(record_items)}
            </ul>
        </div>
    </div>
""")

    # Динамически собираем весь HTML-отчет
    final_html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ОТЧЕТ INTERNET ЖУК</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600&display=swap');
        
        body {{
            background-color: #0a0a0a;
            font-family: 'Montserrat', sans-serif;
            color: #dcdcdc;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            overflow-x: hidden;
        }}

        /* Анимация "Жучков" */
        @keyframes move {{
            0% {{ transform: translate(0, 0); opacity: 0; }}
            10% {{ opacity: 0.1; }}
            50% {{ opacity: 0.2; }}
            100% {{ transform: translate(calc(var(--x) * 1px), calc(var(--y) * 1px)); opacity: 0; }}
        }}

        .bug {{
            position: fixed;
            background-color: rgba(255, 255, 255, 0.5);
            border-radius: 50%;
            pointer-events: none;
            width: 2px;
            height: 2px;
            animation: move linear infinite;
        }}

        .report-container {{
            max-width: 900px;
            margin: 40px auto;
            background: rgba(18, 18, 18, 0.95);
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            padding: 40px;
            position: relative;
            z-index: 10;
        }}

        header {{
            text-align: center;
            border-bottom: 2px solid #2a2a2a;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}

        header h1 {{
            font-size: 2.5rem;
            color: #f5f5f5;
            margin: 0;
        }}

        .section-title {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #dcdcdc;
            margin-top: 40px;
            padding-bottom: 10px;
            border-bottom: 1px solid #2a2a2a;
            transition: color 0.3s ease;
        }}
        
        .section-title:hover {{
            color: #fff;
        }}

        .info-block {{
            background-color: #1a1a1a;
            border-left: 5px solid #444;
            padding: 20px;
            margin-bottom: 25px;
            border-radius: 8px;
        }}

        .info-item {{
            margin-bottom: 10px;
        }}

        .info-item strong {{
            display: block;
            color: #fff;
            font-weight: 600;
        }}

        .info-item span {{
            color: #ccc;
            font-size: 0.95rem;
        }}

        .record-card {{
            background-color: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            cursor: pointer;
            transition: all 0.3s ease;
        }}

        .record-card:hover {{
            background-color: #222;
            transform: translateY(-5px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        }}
        
        .record-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .record-header h4 {{
            font-size: 1.2rem;
            color: #dcdcdc;
            margin: 0;
            padding-bottom: 10px;
            border-bottom: 1px solid #2a2a2a;
            flex-grow: 1;
            transition: color 0.3s ease;
        }}
        
        .record-card:hover .record-header h4 {{
            color: #fff;
        }}
        
        .toggle-icon {{
            font-size: 1.2rem;
            transform: rotate(0deg);
            transition: transform 0.3s ease;
        }}
        
        .record-card.active .toggle-icon {{
            transform: rotate(-180deg);
        }}

        .record-details {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.5s ease-out, padding 0.5s ease-out;
            padding-top: 0;
        }}
        
        .record-card.active .record-details {{
            max-height: 1000px; /* Достаточно большое значение */
            padding-top: 15px;
        }}

        .record-details ul {{
            list-style-type: none;
            padding: 0;
            margin: 0;
        }}

        .record-details li {{
            background-color: #2a2a2a;
            margin-bottom: 8px;
            padding: 10px;
            border-radius: 4px;
            transition: background-color 0.3s ease;
        }}
        
        .record-details li:hover {{
            background-color: #333;
        }}

        .footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #2a2a2a;
            font-size: 0.8rem;
            color: #aaa;
        }}
    </style>
</head>
<body>

<div class="report-container">
    <header>
        <h1>ОТЧЕТ INTERNET ЖУК</h1>
    </header>
    
    <div class="info-block">
        <div class="info-item">
            <strong>ТИП ЗАПРОСА:</strong>
            <span>{query_type.capitalize()}</span>
        </div>
        <div class="info-item">
            <strong>ЗНАЧЕНИЕ ЗАПРОСА:</strong>
            <span>{query_value}</span>
        </div>
        <div class="info-item">
            <strong>ОБЩЕЕ КОЛИЧЕСТВО ЗАПИСЕЙ:</strong>
            <span>{len(results)}</span>
        </div>
    </div>
    
    {operator_info_html}

    <div class="section-title">ДЕТАЛИЗИРОВАННЫЕ РЕЗУЛЬТАТЫ</div>
    
    {"".join(records_html)}

</div>

<footer class="footer">
    <p>Отчет сгенерирован ботом @INTERNETZUK</p>
    <p>Отчет предназначен для личного пользования.</p>
</footer>

<script>
    document.addEventListener('DOMContentLoaded', () => {{
        const recordCards = document.querySelectorAll('.record-card');
        recordCards.forEach(card => {{
            const header = card.querySelector('.record-header');
            header.addEventListener('click', () => {{
                card.classList.toggle('active');
            }});
        }});
        
        // Создание "жучков"
        function createBugs() {{
            for (let i = 0; i < 50; i++) {{
                const bug = document.createElement('div');
                bug.classList.add('bug');
                document.body.appendChild(bug);
                
                const size = Math.random() * 3 + 1;
                bug.style.width = size + 'px';
                bug.style.height = size + 'px';
                bug.style.top = Math.random() * 100 + 'vh';
                bug.style.left = Math.random() * 100 + 'vw';
                
                const duration = Math.random() * 15 + 10;
                bug.style.animationDuration = duration + 's';
                
                const x_offset = (Math.random() - 0.5) * 500;
                const y_offset = (Math.random() - 0.5) * 500;
                
                bug.style.setProperty('--x', x_offset);
                bug.style.setProperty('--y', y_offset);
                bug.style.animationDelay = -Math.random() * duration + 's';
            }}
        }}
        createBugs();
    }});
</script>

</body>
</html>
"""

    return final_html

async def format_depsearch_results(query_type: str, query_value: str, data: dict, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """
    Форматирует результаты поиска, объединяя дубликаты и группируя данные,
    с улучшенным визуальным оформлением.
    """
    results = data.get('results', [])

    # 1. Объединение и уникализация данных
    consolidated_data = defaultdict(set)
    for item in results:
        for key, value in item.items():
            if value and not (isinstance(value, (str, list)) and not value):
                key_lower = key.lower().replace(' ', '_').replace('-', '_')
                
                if 'фио' in key_lower or 'fullname' in key_lower or 'имя' in key_lower or 'name' in key_lower:
                    consolidated_data['ФИО'].add(str(value))
                elif 'инн' in key_lower:
                    consolidated_data['ИНН'].add(str(value))
                elif 'телефон' in key_lower or 'phone' in key_lower or 'number' in key_lower:
                    if isinstance(value, list):
                        for sub_item in value:
                            consolidated_data['Телефон'].add(str(sub_item))
                    else:
                        consolidated_data['Телефон'].add(str(value))
                elif 'почта' in key_lower or 'email' in key_lower or 'mail' in key_lower:
                    if isinstance(value, list):
                        for sub_item in value:
                            consolidated_data['Почта'].add(str(sub_item))
                    else:
                        consolidated_data['Почта'].add(str(value))
                elif key_lower in ["data", "source", "database"]:
                    continue
                else:
                    if isinstance(value, list):
                        for sub_item in value:
                            consolidated_data[key_lower].add(str(sub_item))
                    elif isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if sub_value:
                                consolidated_data[key_lower].add(f"{sub_key}: {sub_value}")
                    else:
                        consolidated_data[key_lower].add(str(value))

    display_query_type = query_type
    if query_type.startswith("vkid"): display_query_type = "ВКонтакте (ID)"
    elif query_type.startswith("vk.com"): display_query_type = "ВКонтакте (ссылка)"
    elif query_type.startswith("tgid"): display_query_type = "Telegram (ID)"
    elif query_type.startswith("t.me"): display_query_type = "Telegram (ссылка)"
    elif query_type.startswith("okid"): display_query_type = "Одноклассники (ID)"
    elif query_type.startswith("fcid"): display_query_type = "Facebook (ID)"
    elif query_type == "phone": display_query_type = "номеру телефона"
    elif query_type == "email": display_query_type = "email"
    elif query_type == "nickname": display_query_type = "нику"

    response_lines = [
        f"🔎 **Результаты по {display_query_type}**: `{query_value}`",
        f"📊 **Найдено записей**: `{len(results)}`"
    ]
    
    if query_type == "phone":
        operator_info = await detect_operator_info(query_value)
        response_lines.append(f"📡 **Оператор**: `{operator_info['operator']}`")
        response_lines.append(f"🌍 **Регион**: `{operator_info['region']}`")
    
    response_lines.append("\n━━━━━━ Сводка ━━━━━━")
    
    has_summary_data = False
    
    # Ключи для сводки, в порядке отображения
    summary_keys = ['ФИО', 'ИНН', 'Телефон', 'Почта']
    
    for key in summary_keys:
        values = sorted(list(set(v for v in consolidated_data.get(key, set()) if v and v.lower() != 'null' and v.strip())))
        if values:
            response_lines.append(f"**{key}**: `{', '.join(values)}`")
            has_summary_data = True
    
    if not has_summary_data:
        response_lines.append("Нет данных для сводки.")
    
    response_lines.append("\n━━━━━━━━━━━━━━━━")
    
    cache_key = f"{user_id}_{int(time.time())}"
    results_cache[cache_key] = {
        "data": data,
        "query_type": query_type,
        "query_value": query_value,
        "expires": datetime.now() + timedelta(hours=1)
    }
    inline_buttons = []
    if data.get('results'):
        inline_buttons.append([InlineKeyboardButton(text="📄 Скачать полный отчет (HTML)", callback_data=f"full_report|{cache_key}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    
    final_response = [line for line in response_lines if line and line.strip()]
    return "\n".join(final_response), kb

async def handle_nickname_search(message: Message, nickname: str):
    """
    Обрабатывает поиск по нику, предоставляя ссылки на популярные соцсети.
    """
    sites = {
        "Instagram": "https://instagram.com/{}",
        "Telegram": "https://t.me/{}",
        "TikTok": "https://tiktok.com/@{}",
        "Facebook": "https://facebook.com/{}",
        "X (Twitter)": "https://x.com/{}",
        "VK": "https://vk.com/{}",
        "GitHub": "https://github.com/{}",
        "Reddit": "https://www.reddit.com/user/{}",
        "YouTube": "https://www.youtube.com/@{}",
        "Steam": "https://steamcommunity.com/id/{}"
    }
    response_lines = [f"🌐 **Возможные профили для ника**: `{nickname}`\n"]
    for name, url_template in sites.items():
        link = url_template.format(nickname)
        response_lines.append(f" • <a href='{link}'>{name}</a>")
    for part in split_message("\n".join(response_lines), 4000):
        await message.answer(part, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --- Обработчики колбэков и команд ---
@dp.message(CommandStart())
async def start_handler(message: Message, bot: Bot):
    """Обработчик команды /start."""
    logger.info(f"Получена команда /start от пользователя {message.from_user.id} ({message.from_user.full_name})")
    user_id = message.from_user.id
    user_data = load_user_data()
    referral_id = None
    if message.text and message.text.startswith('/start ref_'):
        try:
            referral_id = int(message.text.split('_')[1])
            if referral_id != user_id:
                logger.info(f"Пользователь {user_id} пришел по реферальной ссылке от {referral_id}")
        except (IndexError, ValueError):
            logger.warning(f"Неверный формат реферальной ссылки от пользователя {user_id}")
    if str(user_id) not in user_data:
        user_data[str(user_id)] = initialize_user_data(user_id)
        if referral_id and str(referral_id) in user_data:
            user_data[str(user_id)]["referred_by"] = referral_id
            user_data[str(referral_id)]["referrals_count"] += 1
            user_data[str(referral_id)]["search_count"] -= REFERRAL_BONUS
            if user_data[str(referral_id)]["search_count"] < 0:
                user_data[str(referral_id)]["search_count"] = 0
            logger.info(f"Пользователю {referral_id} начислен бонус за реферала {user_id}")
            try:
                await bot.send_message(referral_id, f"🎉 **У вас новый реферал!**\n"
                                                  f"Пользователь {message.from_user.full_name} запустил бота по вашей ссылке. Вам начислено 1 бонусный запрос!",
                                        parse_mode=ParseMode.MARKDOWN)
            except TelegramForbiddenError:
                logger.warning(f"Не удалось отправить уведомление о реферале пользователю {referral_id}, он заблокировал бота.")
        save_user_data(user_data)
        logger.info(f"Созданы данные для нового пользователя: {user_id}")
    await message.answer(
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        "Я бот для поиска информации по открытым источникам: Depsearch. Выбери, что хочешь найти:",
        reply_markup=main_kb,
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(F.text == "❓ Помощь")
async def help_handler(message: Message):
    """Обработчик кнопки 'Помощь'."""
    user_id = message.from_user.id
    user_data = load_user_data()
    
    is_vip = user_id in VIP_USERS or user_data.get(str(user_id), {}).get("is_vip", False)
    
    help_text = (
        "🤖 **Я — Internet Жук**, ваш помощник для поиска информации в открытых источниках.\n\n"
        "**Как пользоваться?**\n"
        "1. Нажмите кнопку `🔎 Поиск`.\n"
        "2. Выберите тип поиска (по номеру, email и т.д.).\n"
        "3. Введите данные для поиска.\n\n"
        "**Ограничения:**\n"
        f" • Обычные пользователи: `{LIMITS['default']}` запросов в день.\n"
        f" • VIP-пользователи: `{LIMITS['vip']}` запросов в день.\n"
        f" • Админы: Безлимитно.\n\n"
        f"**Как получить VIP?**\n"
        f" • Нажмите кнопку `💎 Купить VIP со скидкой`."
    )
    
    await message.answer(help_text, reply_markup=main_kb, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "🔎 Поиск")
async def search_handler(message: Message, state: FSMContext):
    """Обработчик кнопки 'Поиск'."""
    user_id = message.from_user.id
    user_data = load_user_data()
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await require_subscription(message)
        return
        
    current_date = get_current_date()
    if user_data.get(str(user_id), {}).get("last_search_date") != current_date:
        user_data.setdefault(str(user_id), initialize_user_data(user_id))
        user_data[str(user_id)]["last_search_date"] = current_date
        user_data[str(user_id)]["search_count"] = 0
        save_user_data(user_data)

    current_count = user_data.get(str(user_id), {}).get("search_count", 0)
    limit = get_user_limit(user_id)
    
    if current_count >= limit:
        await message.answer(
            "🚫 **Лимит запросов исчерпан!**\n\n"
            f"Ваш лимит на сегодня: `{limit}`.\n"
            "Чтобы снять ограничения, получите VIP-статус.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await message.answer("Выберите тип поиска:", reply_markup=search_inline_kb)
    await state.set_state(SearchState.choosing_search_type)

@dp.message(F.text == "📈 Мой статус")
async def status_handler(message: Message):
    """Обработчик кнопки 'Мой статус'."""
    user_id = message.from_user.id
    user_data = load_user_data()
    
    user_info = user_data.get(str(user_id), initialize_user_data(user_id))
    
    is_vip = user_id in VIP_USERS or user_info.get("is_vip", False)
    is_admin = user_id in ADMINS
    
    limit = "Безлимитно" if is_admin else LIMITS['vip'] if is_vip else LIMITS['default']
    
    status_text = (
        f"👤 **Ваш статус:**\n\n"
        f" • ID: `{user_id}`\n"
        f" • Статус: {'👑 Админ' if is_admin else '💎 VIP' if is_vip else '👥 Обычный'}\n"
        f" • Запросов сегодня: `{user_info.get('search_count', 0)}` / `{limit}`\n"
        f" • Приглашенных друзей: `{user_info.get('referrals_count', 0)}`"
    )
    
    await message.answer(status_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text == "🤝 Пригласить друга")
async def invite_handler(message: Message):
    """Обработчик кнопки 'Пригласить друга'."""
    user_id = message.from_user.id
    referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    await message.answer(
        "🚀 **Пригласите друга и получите бонус!**\n\n"
        "Отправьте эту ссылку другу. Когда он запустит бота, вы получите `1 бесплатный запрос`.\n\n"
        f"Ваша реферальная ссылка:\n`{referral_link}`",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message(F.text == "💎 Купить VIP со скидкой")
@dp.callback_query(F.data == "buy_vip_discount")
async def buy_vip_discount_handler(data_obj: types.Message | types.CallbackQuery):
    """
    Обработчик кнопки 'Купить VIP со скидкой' и колбэка.
    """
    user_id = data_obj.from_user.id
    
    vip_text = (
        "💎 **Получите VIP-статус по выгодной цене!**\n\n"
        "**Преимущества VIP:**\n"
        f" • `{LIMITS['vip']}` запросов в день.\n"
        " • Доступ к эксклюзивным функциям.\n"
        " • Приоритетная поддержка.\n"
        " • Возможность скачивать полные HTML-отчеты.\n\n"
        "**Для покупки VIP со скидкой напишите:**\n"
        f"[сюда](https://t.me/devilosint)"
    )
    
    if isinstance(data_obj, types.Message):
        await data_obj.answer(vip_text, parse_mode=ParseMode.MARKDOWN)
    elif isinstance(data_obj, types.CallbackQuery):
        await data_obj.message.answer(vip_text, parse_mode=ParseMode.MARKDOWN)
        await data_obj.answer()

@dp.message(F.text == "🤖 О боте")
async def about_bot_handler(message: Message):
    """Обработчик кнопки 'О боте'."""
    about_text = (
        "**Internet Жук** - это бот, который помогает найти информацию о людях "
        "по открытым источникам. Это могут быть утекшие базы данных, "
        "социальные сети, публичные реестры и т.д. "
        "Наша цель - предоставить доступ к публичной информации "
        "для обеспечения безопасности и проверки данных."
    )
    
    await message.answer(about_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("admin"))
async def admin_panel_handler(message: Message):
    """Обработчик команды /admin."""
    user_id = message.from_user.id
    if user_id in ADMINS:
        user_data = load_user_data()
        user_count = len(user_data)
        await message.answer(f"Добро пожаловать в панель администратора.\n\n"
                             f"Текущее количество пользователей: **{user_count}**",
                             reply_markup=admin_kb, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("У вас нет прав для доступа к этой панели.")

@dp.callback_query(F.data.in_(["admin_close"]))
async def close_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id in ADMINS:
        await callback.message.edit_text("Панель администратора закрыта.", reply_markup=None)
    await callback.answer()

@dp.callback_query(F.data.in_(["admin_broadcast"]))
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in ADMINS:
        await callback.message.edit_text("Введите текст для рассылки всем пользователям:")
        await state.set_state(AdminState.awaiting_broadcast_text)
    await callback.answer()

@dp.message(AdminState.awaiting_broadcast_text)
async def send_broadcast(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await message.answer("Начинаю рассылку. Это может занять некоторое время.")
        user_data = load_user_data()
        count = 0
        for user_id_str in user_data:
            user_id = int(user_id_str)
            try:
                await bot.send_message(user_id, message.text)
                count += 1
            except TelegramForbiddenError:
                logger.warning(f"Пользователь {user_id} заблокировал бота. Удаляю из списка.")
                user_data[user_id_str]["subscribed"] = False
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
                
        save_user_data(user_data)
        await message.answer(f"Рассылка завершена. Сообщение отправлено {count} пользователям.", reply_markup=main_kb)
        await state.clear()
    else:
        await message.answer("У вас нет прав для выполнения этой команды.")

@dp.callback_query(F.data.in_(["admin_add_vip"]))
async def start_add_vip(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in ADMINS:
        await callback.message.edit_text("Введите ID пользователя, которому хотите выдать VIP-статус:")
        await state.set_state(AdminState.awaiting_vip_id)
    await callback.answer()

@dp.message(AdminState.awaiting_vip_id)
async def add_vip_user(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        try:
            vip_id = int(message.text)
            user_data = load_user_data()
            if str(vip_id) not in user_data:
                await message.answer(f"Пользователь с ID {vip_id} не найден в базе.")
            else:
                user_data[str(vip_id)]["is_vip"] = True
                save_user_data(user_data)
                VIP_USERS.append(vip_id)
                await message.answer(f"Пользователю с ID {vip_id} выдан VIP-статус.", reply_markup=main_kb)
                await bot.send_message(vip_id, "🎉 **Поздравляем!** Вам выдан VIP-статус.", parse_mode=ParseMode.MARKDOWN)
                await state.clear()
        except ValueError:
            await message.answer("ID должен быть числом. Попробуйте еще раз.")
        except Exception as e:
            await message.answer(f"Произошла ошибка: {e}")
            logger.error(f"Ошибка при выдаче VIP: {e}")
    else:
        await message.answer("У вас нет прав для выполнения этой команды.")

@dp.callback_query(F.data.in_(["admin_get_users"]))
async def get_user_db(callback: types.CallbackQuery):
    if callback.from_user.id in ADMINS:
        try:
            user_db_path = os.path.join(BASE_DIR, "users.txt")
            if os.path.exists(user_db_path):
                file = FSInputFile(user_db_path, filename="users.txt")
                await bot.send_document(callback.from_user.id, file, caption="База данных пользователей.")
            else:
                await bot.send_message(callback.from_user.id, "Файл с базой данных не найден.")
        except Exception as e:
            logger.error(f"Ошибка при отправке базы данных: {e}")
            await bot.send_message(callback.from_user.id, f"Произошла ошибка при отправке файла: {e}")
    await callback.answer()

@dp.callback_query(F.data.in_([
    "search_phone", "search_email", "search_nickname", "search_social",
    "social_vk", "social_tg", "social_ok", "social_fc",
    "social_vk_id", "social_vk_link", "social_tg_id", "social_tg_link", "social_ok_id", "social_fc_id",
    "back_to_search_type", "back_to_social"
]))
async def search_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = load_user_data()
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await require_subscription(callback.message)
        await callback.answer()
        return

    current_count = user_data.get(str(user_id), {}).get("search_count", 0)
    limit = get_user_limit(user_id)

    if current_count >= limit:
        await callback.message.answer(
            "🚫 **Лимит запросов исчерпан!**\n\n"
            f"Ваш лимит на сегодня: `{limit}`.\n"
            "Чтобы снять ограничения, получите VIP-статус.",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return

    action = callback.data
    response_text = ""
    reply_markup = None
    state_to_set = None

    if action == "back_to_search_type":
        response_text = "Выберите тип поиска:"
        reply_markup = search_inline_kb
        state_to_set = SearchState.choosing_search_type
    elif action == "back_to_social":
        response_text = "Выберите социальную сеть:"
        reply_markup = social_inline_kb
        state_to_set = SearchState.waiting_for_social
    elif action == "search_phone":
        response_text = "📱 Отправьте номер телефона для поиска (например, `79991234567`):"
        state_to_set = SearchState.waiting_for_phone
    elif action == "search_email":
        response_text = "📧 Отправьте email для поиска:"
        state_to_set = SearchState.waiting_for_email
    elif action == "search_nickname":
        response_text = "👤 Отправьте никнейм для поиска:"
        state_to_set = SearchState.waiting_for_nickname
    elif action == "search_social":
        response_text = "Выберите социальную сеть для поиска:"
        reply_markup = social_inline_kb
        state_to_set = SearchState.waiting_for_social
    elif action == "social_vk":
        response_text = "Выберите, что будете искать ВКонтакте:"
        reply_markup = vk_inline_kb
    elif action == "social_tg":
        response_text = "Выберите, что будете искать в Telegram:"
        reply_markup = tg_inline_kb
    elif action == "social_ok":
        response_text = "Выберите, что будете искать в Одноклассниках:"
        reply_markup = ok_inline_kb
    elif action == "social_fc":
        response_text = "Выберите, что будете искать в Facebook:"
        reply_markup = fc_inline_kb
    elif action == "social_vk_id":
        response_text = "Введите VK ID:"
        state_to_set = SearchState.waiting_for_vkid
    elif action == "social_vk_link":
        response_text = "Отправьте ссылку на профиль VK:"
        state_to_set = SearchState.waiting_for_vk_link
    elif action == "social_tg_id":
        response_text = "Введите Telegram ID:"
        state_to_set = SearchState.waiting_for_tgid
    elif action == "social_tg_link":
        response_text = "Отправьте ссылку на профиль Telegram:"
        state_to_set = SearchState.waiting_for_tg_link
    elif action == "social_ok_id":
        response_text = "Введите OK ID:"
        state_to_set = SearchState.waiting_for_okid
    elif action == "social_fc_id":
        response_text = "Введите FC ID:"
        state_to_set = SearchState.waiting_for_fcid
    
    await callback.message.edit_text(response_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    if state_to_set:
        await state.set_state(state_to_set)

    await callback.answer()

@dp.message(F.text, StateFilter(SearchState.waiting_for_phone, SearchState.waiting_for_email, 
                                SearchState.waiting_for_nickname, SearchState.waiting_for_vkid,
                                SearchState.waiting_for_vk_link, SearchState.waiting_for_tgid,
                                SearchState.waiting_for_tg_link, SearchState.waiting_for_okid,
                                SearchState.waiting_for_fcid))
async def handle_search_query(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    current_state = await state.get_state()
    user_query = message.text.strip()
    
    now = time.time()
    if now - user_last_request[user_id] < FLOOD_LIMIT:
        await message.answer("⚠️ Пожалуйста, не флудите. Повторите запрос через 1 секунду.")
        return
    user_last_request[user_id] = now
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await require_subscription(message)
        await state.set_state(SearchState.choosing_search_type)
        return

    user_data = load_user_data()
    current_count = user_data.get(str(user_id), {}).get("search_count", 0)
    limit = get_user_limit(user_id)
    if current_count >= limit:
        await message.answer(
            "🚫 **Лимит запросов исчерпан!**\n\n"
            f"Ваш лимит на сегодня: `{limit}`.\n"
            "Чтобы снять ограничения, получите VIP-статус.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    is_valid = False
    query_type = ""
    api_query_value = ""

    if current_state == SearchState.waiting_for_phone:
        query_type = "phone"
        user_query = re.sub(r'[^0-9+]', '', user_query)
        if re.fullmatch(r'^(7|8)?[0-9]{10}$|^380[0-9]{9}$', user_query):
            user_query = "7" + user_query[1:] if user_query.startswith("8") else user_query
            api_query_value = f"+{user_query}"
            is_valid = True
        else:
            await message.answer("🚫 Неверный формат номера. Попробуйте еще раз. (Например, `79991234567`)")
            return
    elif current_state == SearchState.waiting_for_email:
        query_type = "email"
        if re.fullmatch(r'[^@]+@[^@]+\.[^@]+', user_query):
            api_query_value = user_query
            is_valid = True
        else:
            await message.answer("🚫 Неверный формат email. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_nickname:
        query_type = "nickname"
        api_query_value = user_query
        is_valid = True
    elif current_state == SearchState.waiting_for_vkid:
        query_type = "vkid"
        if user_query.isdigit():
            api_query_value = f"vkid{user_query}"
            is_valid = True
        else:
            await message.answer("🚫 ID должен состоять только из цифр. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_vk_link:
        query_type = "vk.com"
        if "vk.com/" in user_query:
            api_query_value = user_query
            is_valid = True
        else:
            await message.answer("🚫 Неверный формат ссылки. Она должна начинаться с `vk.com/`. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_tgid:
        query_type = "tgid"
        if user_query.isdigit():
            api_query_value = f"tgid{user_query}"
            is_valid = True
        else:
            await message.answer("🚫 ID должен состоять только из цифр. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_tg_link:
        query_type = "t.me"
        if "t.me/" in user_query:
            api_query_value = user_query
            is_valid = True
        else:
            await message.answer("🚫 Неверный формат ссылки. Она должна начинаться с `t.me/`. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_okid:
        query_type = "okid"
        if user_query.isdigit():
            api_query_value = f"okid{user_query}"
            is_valid = True
        else:
            await message.answer("🚫 ID должен состоять только из цифр. Попробуйте еще раз.")
            return
    elif current_state == SearchState.waiting_for_fcid:
        query_type = "fcid"
        if user_query.isdigit():
            api_query_value = f"fcid{user_query}"
            is_valid = True
        else:
            await message.answer("🚫 ID должен состоять только из цифр. Попробуйте еще раз.")
            return

    if not is_valid:
        await message.answer("🚫 Неверный запрос. Пожалуйста, попробуйте еще раз.")
        return

    await message.answer("⏳ Ваш запрос обрабатывается, это может занять до 1-2 минут.")
    
    if query_type == "nickname":
        await handle_nickname_search(message, user_query)
        await state.clear()
        return

    try:
        url = f"https://api.depsearch.digital/quest={api_query_value}?token={DEPSEARCH_TOKEN}&lang=ru"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get('results'):
                        user_data = load_user_data()
                        user_data[str(user_id)]["search_count"] = user_data.get(str(user_id), {}).get("search_count", 0) + 1
                        user_data[str(user_id)]["queries"].append(
                            {"type": query_type, "value": user_query, "date": str(datetime.now())}
                        )
                        save_user_data(user_data)
                        
                        formatted_response, kb = await format_depsearch_results(query_type, user_query, data, user_id)
                        
                        for part in split_message(formatted_response):
                            await message.answer(part, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)

                    else:
                        await message.answer(f"❌ По запросу `{user_query}` ничего не найдено.", parse_mode=ParseMode.MARKDOWN)

                elif response.status == 404:
                    await message.answer(f"❌ По запросу `{user_query}` ничего не найдено.", parse_mode=ParseMode.MARKDOWN)

                elif response.status == 429:
                    await message.answer("⚠️ Слишком много запросов. Попробуйте позже.")
                else:
                    await message.answer(f"❌ Произошла ошибка. Код: {response.status}")
                    logger.error(f"DepSearch API вернул ошибку {response.status}: {await response.text()}")

    except Exception as e:
        logger.error(f"Ошибка при поиске по {query_type} для {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при обработке вашего запроса.")
    
    await state.clear()

@dp.callback_query(F.data.startswith("full_report|"))
async def send_full_report(callback: types.CallbackQuery):
    cache_key = callback.data.split("|")[1]
    user_id = callback.from_user.id
    
    cached_data = results_cache.get(cache_key)
    
    if cached_data and cached_data["expires"] > datetime.now():
        data = cached_data["data"]
        query_type = cached_data.get("query_type", "unknown")
        query_value = cached_data.get("query_value", "unknown")
        
        try:
            html_content = await generate_html_report(query_type, query_value, data)
            file_name = f"report_{query_type}_{query_value}_{user_id}.html"
            file_path = os.path.join(TEMP_FILES_DIR, file_name)
            
            # Использование более надежного метода записи в двоичном режиме
            with open(file_path, "wb") as f:
                f.write(html_content.encode('utf-8'))
            
            await bot.send_document(
                chat_id=user_id,
                document=FSInputFile(file_path, filename=file_name),
                caption=f"**Полный отчет по запросу** `{query_value}`",
                parse_mode=ParseMode.MARKDOWN
            )
            os.remove(file_path)
            del results_cache[cache_key]
        except FileNotFoundError:
            await callback.message.answer("❌ Временный файл отчета не найден.")
        except Exception as e:
            logger.error(f"Ошибка при отправке полного отчета для {user_id}: {e}", exc_info=True)
            await callback.message.answer("❌ Произошла непредвиденная ошибка при генерации отчета. Попробуйте еще раз.")
    else:
        await callback.message.answer("❌ Срок действия отчета истек. Пожалуйста, сделайте новый запрос.")

    await callback.answer()

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)
    if is_subscribed:
        await callback.message.edit_text(
            f"✅ **Отлично, {callback.from_user.full_name}!**\n"
            "Вы успешно подписались на наш канал. Теперь можете пользоваться ботом.",
            reply_markup=None,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.message.answer("Выберите тип поиска:", reply_markup=search_inline_kb)
    else:
        await callback.answer("Вы еще не подписались на канал.", show_alert=True)
    await callback.answer()

@dp.message(F.text)
async def handle_text_messages(message: Message):
    """Обработчик любых текстовых сообщений, не соответствующих другим хэндлерам."""
    await message.answer(
        "👋 **Привет!** Используйте кнопки, чтобы взаимодействовать со мной.",
        reply_markup=main_kb,
        parse_mode=ParseMode.MARKDOWN
    )
    
async def main() -> None:
    logging.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())