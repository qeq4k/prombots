#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌐 Глобальная дедупликация — общая для всех парсеров
✅ Учитывает категорию (politics/economy/movies)
✅ Одна новость может быть в разных категориях
✅ Улучшенная защита от дубликатов (строгая нормализация)
✅ Fuzzy matching для новостей написанных по-разному
"""
import hashlib
import re
import logging
import aiosqlite
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from difflib import SequenceMatcher
from typing import Tuple

logger = logging.getLogger(__name__)


DB_PATH = Path("global_dedup.db")

# ✅ Расширенные списки для нормализации
COMMON_NAMES = [
    'путин', 'трамп', 'байден', 'лавро', 'песков', 'макрон', 'шольц', 'си',
    'зеленск', 'меркел', 'маккарт', 'эрдоган', 'нетаньяху', 'медведе', 'мишустин',
    'собянин', 'johnson', 'boris', 'sunak', 'truss', 'biden', 'obama', 'clinton',
    'putin', 'zelens', 'lukashen', 'navarro', 'pompeo', 'kerry', 'nato',
    # Должности
    'президент', 'премьер', 'министр', 'посол', 'представитель', 'секретарь',
    'спикер', 'глава', 'руковод', 'директор', 'советник', 'помощник',
    # Страны и прилагательные (добавлены окончания)
    'иран', 'ирана', 'ирану', 'ираном', 'иране', 'иранский', 'иранских', 'иранские',
    'израил', 'израиля', 'израилю', 'израилем', 'израиле', 'израильский', 'израильских',
    'росси', 'россии', 'россию', 'россией', 'россий', 'российский', 'российских', 'российские',
    'украин', 'украины', 'украине', 'украину', 'украиной', 'украинский', 'украинских',
    'сша', 'сша', 'америк', 'америки', 'америке', 'америку', 'американский', 'американских',
]

COUNTRIES = [
    'росси', 'украин', 'сша', 'америк', 'китай', 'европ', 'германи', 'франци',
    'британи', 'израил', 'иран', 'сауд', 'арави', 'турци', 'польш', 'итали',
    'испани', 'япони', 'корей', 'инди', 'беларус', 'казахстан', 'узбекистан',
    'англи', 'канад', 'австрали', 'бразили', 'аргентин', 'мексик', 'египет',
    'пакистан', 'бангладеш', 'нигер', 'эфиоп', 'вьетнам', 'таиланд', 'малайзи',
    'индонези', 'филиппин', 'колумби', 'венесуэл', 'чил', 'перу', 'куб',
    'russia', 'ukrain', 'america', 'china', 'europe', 'german', 'france',
    'britain', 'israel', 'iran', 'turkey', 'poland', 'italy', 'spain', 'japan',
]

CITIES = [
    'москв', 'киев', 'минск', 'лондон', 'париж', 'берлин', 'рим', 'мадрид',
    'токио', 'пекин', 'дели', 'вашингтон', 'нью-йорк', 'брюссел', 'женев',
    'вен', 'праг', 'варшав', 'анкар', 'тегеран', 'эр-рияд', 'каир', 'канберра',
    'оттав', 'стокольм', 'осл', 'хельсинк', 'копенгаген', 'амстердам', 'брюссел',
    'страсбург', 'люксембург', 'цинц', 'давос', 'рияд', 'дубай', 'абу-даби',
]

ORGANIZATIONS = [
    'оон', 'нато', 'es', 'снг', 'брис', 'g7', 'g20', 'мвф', 'вомт', 'wto', 'imf',
    'ек', 'сб оон', 'совет безопасност', 'госдум', 'совет федераци', 'кремль',
    'белый дом', 'конгресс', 'сенат', 'парламент', 'правительств', 'министерств',
    'мид', 'фсб', 'цру', 'пентагон', 'евросоюз', 'eurounion', 'united nations',
    'security council', 'white house', 'kremlin', 'congress', 'senate',
    'council of europe', 'european commission', 'federal reserve', 'центробанк',
    'цб рф', 'банк россии', 'правительство рф', 'госдума', 'совфед',
    'совет безопасности', 'сб', 'рада', 'верховн', 'кабинет министров',
]

CURRENCIES = [
    'доллар', 'евро', 'рубл', 'юань', 'фунт', 'иен', 'bitcoin', 'биткоин', 'crypt',
    'dollar', 'euro', 'ruble', 'rouble', 'yuan', 'pound', 'yen', 'btc', 'eth',
    'криптовалют', 'крипта', 'stablecoin', 'usdt', 'usdc',
]

ACTION_WORDS = [
    # Действия
    'заявил', 'заявлен', 'сообщил', 'сообщ', 'сказал', 'рассказал', 'объявил',
    'объяснил', 'подчеркнул', 'отметил', 'указал', 'добавил', 'продолжил',
    'начал', 'завершил', 'закончил', 'прекратил', 'возобновил', 'продолжил',
    'провел', 'провела', 'прошли', 'состоялся', 'состоялась', 'состоится',
    'пройдет', 'проходила', 'проходит', 'начался', 'началась', 'завершился',
    # Решения
    'принял', 'принято', 'решил', 'решено', 'постановил', 'постановлено',
    'утвердил', 'утверждено', 'одобрил', 'одобрено', 'согласовал', 'согласовано',
    'подписал', 'подписано', 'ратифицировал', 'ратифицировано',
    # Изменения
    'изменил', 'изменено', 'поменял', 'поменяно', 'скорректировал', 'обновил',
    'пересмотрел', 'пересмотрено', 'аннулировал', 'аннулировано', 'отменил',
    'отменено', 'приостановил', 'приостановлено', 'возобновил', 'возобновлено',
    # Движения
    'вырос', 'увеличил', 'увеличено', 'поднялся', 'поднят', 'подорожал',
    'упал', 'снизился', 'снижено', 'уменьшил', 'уменьшено', 'подешевел',
    'колеблется', 'стабилизировался', 'достиг', 'превысил', 'превышено',
    # Встречи
    'встретился', 'встретилась', 'встреча', 'переговоры', 'саммит', 'совещание',
    'заседание', 'сессия', 'конференция', 'форум', 'дискуссия', 'дебаты',
    # Конфликты
    'атаковал', 'атаковано', 'ударил', 'удар', 'обстрелял', 'обстрел', 'уничтожил',
    'уничтожено', 'разрушил', 'разрушено', 'повредил', 'повреждено', 'пострадал',
    'погиб', 'погибло', 'ранен', 'ранено', 'эвакуировал', 'эвакуировано',
]

EVENT_TYPES = [
    # События
    'новость', 'новости', 'сообщение', 'доклад', 'отчет', 'отчёт', 'заявление',
    'интервью', 'пресс-релиз', 'пресс-конференция', 'брифинг', 'коммюнике',
    # Документы
    'закон', 'фз', 'указ', 'постановление', 'распоряжение', 'приказ', 'решение',
    'резолюция', 'декларация', 'соглашение', 'договор', 'контракт', 'сделка',
    'меморандум', 'протокол', 'конвенция', 'пакт', 'хартия', 'санкция', 'эмбарго',
    # Встречи
    'встреча', 'переговоры', 'саммит', 'совещание', 'заседание', 'сессия',
    'конференция', 'форум', 'дискуссия', 'дебаты', 'слушания', 'консультации',
]


def normalize_text_for_dedup(text: str) -> str:
    """
    ✅ ОЧЕНЬ СТРОГАЯ нормализация текста для дедупликации.
    Убирает ВСЁ, что может отличаться в одинаковых новостях, написанных по-разному.
    """
    text = text.lower().strip()

    # 0. Сначала нормализуем общие аббревиатуры и составные термины
    # Важно: делаем это до основной нормализации организаций
    text = re.sub(r'\b(сб\s+оон|с\.?б\.?\s+оон|совет\s+безопасности\s+оон|совет\s+безопасности\s+при\s+оон)\b', 'UNSC', text)
    text = re.sub(r'\b(сша|соединенные\s+штаты|америка|штаты)\b', 'USA', text)
    text = re.sub(r'\b(россия|рф|российская\s+федерация)\b', 'RUSSIA', text)
    text = re.sub(r'\b(украина|укр)\b', 'UKRAINE', text)
    text = re.sub(r'\b(евросоюз|ес|европейский\s+союз)\b', 'EU', text)
    text = re.sub(r'\b(великобритания|соединенное\s+королевство|британия)\b', 'UK', text)
    text = re.sub(r'\b(срочн|экстренн|внеочередн)[а-яё]*\b', 'URGENT', text)
    text = re.sub(r'\b(заседани|совещани|встреч|собрани)[а-яё]*\b', 'MEETING', text)
    text = re.sub(r'\b(созвал|инициировал|предложил|организовал)\b', 'CALLED', text)
    text = re.sub(r'\b(по\s+инициативе|по\s+предложени|по\s+просьб)\b', 'INITIATED', text)
    text = re.sub(r'\b(президент|лидер|глава)\b', 'LEADER', text)
    
    # 1. Убираем цифры (годы, даты, суммы, проценты, количества)
    text = re.sub(r'\d+', 'N', text)
    text = re.sub(r'N[\s]*[%,.]\s*N', ' NUM ', text)  # Числа с разделителями
    text = re.sub(r'N\s*(млн|млрд|трлн|тыс|k|m|b|million|billion|thousand)', ' NUM ', text)

    # 2. Убираем очень короткие слова (1-2 символа) - это важно!
    text = re.sub(r'\b[а-яёa-z]{1,2}\b', ' ', text)

    # 3. Убираем распространённые имена/фамилии/должности
    names_pattern = r'\b(' + '|'.join(COMMON_NAMES) + r')\b'
    text = re.sub(names_pattern, 'NAME', text)

    # 4. Убираем страны
    countries_pattern = r'\b(' + '|'.join(COUNTRIES) + r')\b'
    text = re.sub(countries_pattern, 'COUNTRY', text)

    # 5. Убираем города
    cities_pattern = r'\b(' + '|'.join(CITIES) + r')\b'
    text = re.sub(cities_pattern, 'CITY', text)

    # 6. Убираем организации
    orgs_pattern = r'\b(' + '|'.join(ORGANIZATIONS) + r')\b'
    text = re.sub(orgs_pattern, 'ORG', text)

    # 7. Убираем валюты
    currencies_pattern = r'\b(' + '|'.join(CURRENCIES) + r')\b'
    text = re.sub(currencies_pattern, 'CURRENCY', text)

    # 8. Убираем слова действия (чтобы осталось только "кто" + "что")
    actions_pattern = r'\b(' + '|'.join(ACTION_WORDS) + r')\b'
    text = re.sub(actions_pattern, 'ACTION', text)

    # 9. Убираем типы событий
    events_pattern = r'\b(' + '|'.join(EVENT_TYPES) + r')\b'
    text = re.sub(events_pattern, 'EVENT', text)

    # 10. Убираем даты и время
    text = re.sub(r'\b(январ|феврал|март|апрел|ма|июн|июл|август|сентябр|октябр|ноябр|декабр)[а-яё]*\b', 'MONTH', text)
    text = re.sub(r'\b(понедельник|вторник|среда|четверг|пятниц|суббот|воскресен)[а-яё]*\b', 'DAY', text)
    text = re.sub(r'\b(сегодня|вчера|завтра|намедни|накануне|утром|вечером|днем|ночью)\b', 'TIME', text)
    text = re.sub(r'\b(недел|месяц|год|день|час|минут|секунд)[а-яё]*\b', 'TIMEUNIT', text)

    # 11. Нормализуем проценты
    text = re.sub(r'N\s*%', ' PERCENT ', text)

    # 12. Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()

    # 13. Убираем специальные символы и пунктуацию
    text = re.sub(r'[^\w\s]', ' ', text)

    # 14. Финальная очистка пробелов
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def get_universal_hash(title: str, link: str, pub_date: datetime = None, category: str = "") -> str:
    """
    ✅ Единый хеш для ВСЕХ парсеров с учётом категории
    Одна новость может быть опубликована в разных категориях (politics + economy)

    ⚠️ ВАЖНО: pub_date не используется в хеше, т.к. разные парсеры могут получать
    разное время публикации из RSS. Вместо этого используется только домен + заголовок.
    """
    domain = urlparse(link.strip()).netloc
    
    # ✅ Нормализуем дату до дня (игнорируем время)
    date_str = pub_date.strftime("%Y-%m-%d") if pub_date else ""
    
    # ✅ Строгая нормализация заголовка
    normalized = normalize_text_for_dedup(title)
    
    # ✅ Добавляем категорию в хеш — одна новость может быть в разных каналах
    raw = f"{normalized}|{domain}|{date_str}|{category.lower()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def get_content_dedup_hash(title: str, body: str, category: str = "") -> str:
    """
    ✅ Улучшенный хеш для дедупликации по содержанию.
    Использует ОЧЕНЬ СТРОГУЮ нормализацию текста.
    """
    # Берём заголовок + первые 400 символов тела (увеличили для лучшего покрытия)
    text = f"{title} {body[:400]}"

    # Строгая нормализация
    normalized = normalize_text_for_dedup(text)

    # Добавляем категорию
    raw = f"{normalized}|{category.lower()}"

    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def get_semantic_hash(title: str, category: str = "") -> str:
    """
    ✅ Семантический хеш для дедупликации.
    Извлекает только ключевые сущности (кто + что) без действий.
    """
    # Нормализуем заголовок
    normalized = normalize_text_for_dedup(title)
    
    # Оставляем только уникальные слова (ключевые сущности)
    words = normalized.split()
    # Убираем повторяющиеся и сортируем для стабильности
    unique_words = sorted(set(words))
    semantic_text = ' '.join(unique_words)
    
    raw = f"{semantic_text}|{category.lower()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def texts_are_similar(text1: str, text2: str, threshold: float = 0.85) -> bool:
    """
    ✅ Проверяет схожесть двух текстов через SequenceMatcher.
    Используется для дополнительной проверки дубликатов.
    """
    norm1 = normalize_text_for_dedup(text1)
    norm2 = normalize_text_for_dedup(text2)
    
    # Если после нормализации тексты идентичны — это дубликат
    if norm1 == norm2:
        return True
    
    # Иначе используем fuzzy matching
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    return ratio >= threshold


def extract_key_entities(title: str) -> dict:
    """
    ✅ Извлекает ключевые сущности из заголовка.
    Возвращает множество ключевых слов для сравнения.
    """
    normalized = normalize_text_for_dedup(title)
    words = set(normalized.split())
    
    # Оставляем только значимые слова (не плейсхолдеры)
    entities = {
        'countries': [w for w in words if w == 'COUNTRY'],
        'cities': [w for w in words if w == 'CITY'],
        'orgs': [w for w in words if w == 'ORG'],
        'names': [w for w in words if w == 'NAME'],
        'currencies': [w for w in words if w == 'CURRENCY'],
        'other': [w for w in words if w not in ('ACTION', 'EVENT', 'TIME', 'TIMEUNIT', 'NUM', 'PERCENT')]
    }
    
    return entities


def are_duplicates_by_entities(title1: str, title2: str, min_common_entities: int = 2) -> bool:
    """
    ✅ Сравнивает две новости по ключевым сущностям.
    Дубликат если есть минимум min_common_entities общих сущностей.
    
    ✅ УЛУЧШЕННАЯ ЛОГИКА:
    - Считаем сущности с весами (countries/orgs важнее other)
    - Требуем совпадение по разным категориям (не только COUNTRY)
    """
    entities1 = extract_key_entities(title1)
    entities2 = extract_key_entities(title2)

    common_count = 0
    category_matches = 0

    # Считаем общие сущности по категориям с весами
    for key in ['countries', 'cities', 'orgs', 'names', 'currencies', 'other']:
        set1 = set(entities1.get(key, []))
        set2 = set(entities2.get(key, []))
        common = len(set1 & set2)
        
        if common > 0:
            category_matches += 1
            
        # Важные категории (countries, orgs) дают больше веса
        if key in ['countries', 'orgs', 'names']:
            common_count += common * 1.5
        elif key in ['cities', 'currencies']:
            common_count += common * 1.2
        else:
            common_count += common * 0.5

    # ✅ НОВОЕ: требуем совпадение по 2+ категориям (не только COUNTRY)
    # Это предотвращает ложные срабатывания когда все новости просто про "COUNTRY ACTION"
    if category_matches < 2:
        return False
        
    return common_count >= min_common_entities


async def init_global_db():
    """Инициализация общей БД с миграцией"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Создаём таблицу если не существует
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_posted (
                content_hash TEXT PRIMARY KEY,
                category TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL,
                parser_name TEXT NOT NULL,
                title_preview TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ✅ МИГРАЦИЯ: добавляем колонку category если её нет
        try:
            await db.execute("ALTER TABLE global_posted ADD COLUMN category TEXT DEFAULT ''")
            logger.info("✅ Добавлена колонка category в global_posted")
        except Exception as e:
            # Колонка уже существует — это нормально
            pass

        await db.execute("CREATE INDEX IF NOT EXISTS idx_category ON global_posted(category)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_channel ON global_posted(channel_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_posted_at ON global_posted(posted_at)")
        await db.commit()


async def is_global_duplicate(content_hash: str, category: str = "", hours: int = 48) -> bool:
    """
    Проверка: уже постили такую новость в этой категории?
    ✅ Одна новость может быть в разных категориях (politics + economy)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем хеш + категорию
        async with db.execute(
            "SELECT 1 FROM global_posted WHERE content_hash = ? AND category = ? AND posted_at > ?",
            (content_hash, category.lower(), cutoff)
        ) as cursor:
            return await cursor.fetchone() is not None


async def is_similar_recent_news(title: str, category: str = "", hours: int = 12, threshold: float = 0.75) -> bool:
    """
    ✅ ПРОВЕРКА НА ПОХОЖИЕ НОВОСТИ через fuzzy matching.
    Ищет похожие новости за последние N часов даже если хеши не совпадают.
    
    ✅ СНИЖЕН ПОРОГ: 0.75 вместо 0.80 для лучшей ловли дубликатов
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем все новости за период в этой категории
        async with db.execute(
            "SELECT title_preview FROM global_posted WHERE category = ? AND posted_at > ?",
            (category.lower(), cutoff)
        ) as cursor:
            rows = await cursor.fetchall()

            for (prev_title,) in rows:
                if prev_title and texts_are_similar(title, prev_title, threshold):
                    logger.info(f"🔄 Fuzzy дубликат ({threshold*100:.0f}%): '{title[:50]}' ~ '{prev_title[:50]}'")
                    return True

    return False


async def is_similar_recent_news_extended(title: str, category: str = "", hours: int = 48, threshold: float = 0.75) -> bool:
    """
    ✅ РАСШИРЕННАЯ ПРОВЕРКА НА ПОХОЖИЕ НОВОСТИ.
    Для HOT-постов: более строгая проверка (ниже порог, больше период).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT title_preview FROM global_posted WHERE category = ? AND posted_at > ?",
            (category.lower(), cutoff)
        ) as cursor:
            rows = await cursor.fetchall()

            for (prev_title,) in rows:
                if prev_title and texts_are_similar(title, prev_title, threshold):
                    logger.info(f"🔄 Extended fuzzy дубликат ({threshold*100:.0f}%): '{title[:40]}' ~ '{prev_title[:40]}'")
                    return True

    return False


async def check_duplicate_multi_layer(title: str, body: str, category: str = "", hours: int = 48) -> Tuple[bool, str]:
    """
    ✅ МНОГОУРОВНЕВАЯ проверка на дубликаты.
    Returns: (is_duplicate, reason)

    Слои проверки:
    1. Content hash (строгая нормализация)
    2. Semantic hash (ключевые сущности)
    3. Fuzzy matching (похожесть текста) - БАЗОВЫЙ
    4. Extended fuzzy matching (для HOT-постов) - НОВЫЙ СЛОЙ
    5. Entity matching (общие сущности)
    """
    # Слой 1: Content hash
    content_hash = get_content_dedup_hash(title, body, category)
    if await is_global_duplicate(content_hash, category, hours):
        return True, "content_hash"

    # Слой 2: Semantic hash
    semantic_hash = get_semantic_hash(title, category)
    if await is_global_duplicate(semantic_hash, category, hours):
        return True, "semantic_hash"

    # Слой 3: Fuzzy matching по недавним новостям (базовый)
    if await is_similar_recent_news(title, category, hours=min(hours, 12), threshold=0.75):
        return True, "fuzzy_match"

    # Слой 4: Extended fuzzy matching (для HOT-постов) - НОВЫЙ СЛОЙ
    if await is_similar_recent_news_extended(title, category, hours=48, threshold=0.70):
        return True, "extended_fuzzy_match"

    # Слой 5: Entity matching (только для очень похожих новостей)
    # ✅ УВЕЛИЧЕН ПОРОГ: теперь требуется 4+ общих сущностей (было 2)
    async with aiosqlite.connect(DB_PATH) as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        async with db.execute(
            "SELECT title_preview FROM global_posted WHERE category = ? AND posted_at > ?",
            (category.lower(), cutoff)
        ) as cursor:
            rows = await cursor.fetchall()
            for (prev_title,) in rows:
                if prev_title and are_duplicates_by_entities(title, prev_title, min_common_entities=4):
                    logger.info(f"🔄 Дубликат по сущностям (4+): '{title[:50]}' == '{prev_title[:50]}'")
                    return True, "entity_match"

    return False, ""


async def mark_global_posted(content_hash: str, channel_id: str, parser: str, title: str, category: str = ""):
    """Отметить новость как опубликованную (глобально) с категорией"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO global_posted (content_hash, category, channel_id, parser_name, title_preview) VALUES (?, ?, ?, ?, ?)",
            (content_hash, category.lower(), channel_id, parser, title[:100])
        )
        await db.commit()


async def cleanup_global_db(days: int = 30):
    """Удалить записи старше N дней"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM global_posted WHERE posted_at < ?", (cutoff,))
        deleted = cursor.rowcount
        await db.commit()
        return deleted


async def get_duplicate_stats(category: str = None, days: int = 7) -> dict:
    """
    ✅ Получить статистику дубликатов за период.
    Полезно для анализа эффективности дедупликации.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with aiosqlite.connect(DB_PATH) as db:
        if category:
            async with db.execute(
                "SELECT COUNT(*) FROM global_posted WHERE category = ? AND posted_at > ?",
                (category.lower(), cutoff)
            ) as cursor:
                count = await cursor.fetchone()
                return {'category': category, 'count': count[0] if count else 0}
        else:
            async with db.execute(
                "SELECT category, COUNT(*) FROM global_posted WHERE posted_at > ? GROUP BY category",
                (cutoff,)
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: row[1] for row in rows}


# ================= УНИВЕРСАЛЬНАЯ ПРОВЕРКА ДУБЛИКАТОВ =================
async def is_duplicate_advanced(
    title: str,
    summary: str,
    link: str,
    local_db_path: str,
    category: str = "",
    duplicate_check_hours: int = 72,
    global_enabled: bool = True
) -> Tuple[bool, str]:
    """
    ✅ УНИВЕРСАЛЬНАЯ ПЯТИУРОВНЕВАЯ проверка дубликатов для всех парсеров.
    
    Args:
        title: Заголовок новости
        summary: Текст новости
        link: Ссылка на новость
        local_db_path: Путь к локальной БД парсера
        category: Категория (politics/economy/cinema)
        duplicate_check_hours: Период проверки дубликатов (часы)
        global_enabled: Включена ли глобальная дедупликация
    
    Returns:
        (is_duplicate, reason)
    
    Слои проверки:
    1. Глобальная проверка через content hash (межканальная)
    2. Проверка по link (точная)
    3. Content dedup hash (локальный)
    4. Fuzzy по заголовку (70%+)
    5. Entity matching (ключевые сущности)
    """
    import aiosqlite
    from rapidfuzz import fuzz
    
    logger = logging.getLogger(__name__)
    
    # ✅ 1. Глобальная проверка (межканальная) через content hash
    if global_enabled:
        try:
            content_hash = get_content_dedup_hash(title, summary, category)
            if await is_global_duplicate(content_hash, category, hours=48):
                logger.info(f"🌐 Глобальный дубликат (content): {title[:50]}")
                return True, "global_content_duplicate"
        except Exception as e:
            logger.warning(f"⚠️ Ошибка глобальной проверки: {e}")

    # ✅ 2. Проверка по link (точная)
    async with aiosqlite.connect(local_db_path) as db:
        async with db.execute(
            "SELECT 1 FROM posted WHERE link = ?",
            (link,)
        ) as cursor:
            if await cursor.fetchone():
                logger.info(f"🔗 Дубликат по ссылке: {title[:50]}")
                return True, "link_duplicate"

    # ✅ 3. Content dedup hash (локальный)
    content_dedup_hash = get_content_dedup_hash(title, summary, category)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=duplicate_check_hours)
    async with aiosqlite.connect(local_db_path) as db:
        # Проверяем в локальной таблице content_dedup если существует
        try:
            async with db.execute(
                "SELECT 1 FROM content_dedup WHERE content_hash = ? AND posted_at > ?",
                (content_dedup_hash, cutoff)
            ) as cursor:
                if await cursor.fetchone():
                    logger.info(f"🔄 Content дубликат: {title[:50]}")
                    return True, "content_duplicate"
        except aiosqlite.OperationalError:
            # Таблица content_dedup не существует — пропускаем
            pass

    # ✅ 4. Fuzzy по заголовку (70%+)
    title_norm = normalize_title_for_dedup(title)
    async with aiosqlite.connect(local_db_path) as db:
        async with db.execute(
            """SELECT title_normalized FROM posted
            WHERE posted_at > ? AND title_normalized IS NOT NULL
            ORDER BY posted_at DESC LIMIT 500""",
            (cutoff,)
        ) as cursor:
            recent_posts = await cursor.fetchall()
            for post in recent_posts:
                stored = post[0] if isinstance(post, tuple) else post
                if not stored:
                    continue
                ratio = fuzz.token_set_ratio(title_norm, stored)
                if ratio >= 70:
                    logger.info(f"🔄 Fuzzy дубликат ({ratio}%): {title[:50]}")
                    return True, f"fuzzy_{ratio}"

    # ✅ 5. Проверка через entity matching (для новостей написанных по-разному)
    if global_enabled:
        try:
            cutoff_recent = datetime.now(timezone.utc) - timedelta(hours=24)
            async with aiosqlite.connect(local_db_path) as db:
                async with db.execute(
                    """SELECT title_normalized FROM posted
                    WHERE posted_at > ? AND title_normalized IS NOT NULL
                    ORDER BY posted_at DESC LIMIT 300""",
                    (cutoff_recent,)
                ) as cursor:
                    recent_posts = await cursor.fetchall()
                    for post in recent_posts:
                        stored = post[0] if isinstance(post, tuple) else post
                        if stored and are_duplicates_by_entities(title, stored, min_common_entities=2):
                            logger.info(f"🔄 Entity дубликат: {title[:50]}")
                            return True, "entity_duplicate"
        except Exception as e:
            logger.warning(f"⚠️ Ошибка entity проверки: {e}")

    return False, "unique"


def normalize_title_for_dedup(title: str) -> str:
    """
    ✅ Нормализация заголовка для fuzzy-сравнения.
    Упрощённая версия normalize_text_for_dedup для скорости.
    """
    import re
    
    title = title.lower().strip()
    
    # Убираем пунктуацию
    title = re.sub(r'[^\w\s\-]', ' ', title)
    
    # Убираем стоп-слова
    stop_words = {'и', 'в', 'на', 'с', 'по', 'о', 'об', 'из', 'к', 'для', 'что', 'это', 'а', 'но', 'же', 'бы', 'ли'}
    words = [w for w in title.split() if w not in stop_words and len(w) > 2]
    
    return ' '.join(words)