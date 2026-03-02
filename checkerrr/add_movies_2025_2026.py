#!/usr/bin/env python3
"""
Скрипт для добавления новых фильмов (коды 053-117) в базу данных
"""

import sqlite3
import logging
from typing import Optional, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "/root/projectss/checkerrr/movies.db"

# Данные фильмов из таблицы
MOVIES = [
    # code, title, year, genres, actors, directors, rutube_link
    ("053", "Бешеные псы (Reservoir Dogs)", 1992, 
     ["Криминал", "Триллер", "Чёрная комедия"],
     ["Харви Кейтель (Kharvi Keytel)", "Тим Рот (Tim Rot)", "Майкл Мэдсен (Maykl Madsen)", "Стив Бушеми (Stiv Bushemi)"],
     ["Квентин Тарантино (Kventin Tarantino)"],
     "https://rutube.ru/video/пример-reservoir-dogs"),
    
    ("054", "Бегущий по лезвию 2049 (Blade Runner 2049)", 2017,
     ["Научная фантастика", "Нео-нуар", "Драма"],
     ["Райан Гослинг (Rayn Gosling)", "Харрисон Форд (Karrison Ford)", "Ана де Армас (Ana de Armas)"],
     ["Дени Вильнёв (Deni Vilnyov)"],
     "https://rutube.ru/video/blade-runner-2049-rus"),
    
    ("055", "Драйв (Drive)", 2011,
     ["Нео-нуар", "Боевик", "Драма"],
     ["Райан Гослинг (Rayn Gosling)", "Кэри Маллиган (Keri Malligan)", "Оскар Айзек (Oskar Ayzek)"],
     ["Николас Виндинг Рефн (Nikolas Vinding Refn)"],
     "https://rutube.ru/video/drive-2011-rus"),
    
    ("056", "Джон Уик (John Wick) — вся серия", 2014,
     ["Боевик", "Триллер", "Месть"],
     ["Киану Ривз (Kianu Rivz)", "Иэн МакШейн (Ian MakSheyn)", "Донни Йен (Donni Yen)"],
     ["Чад Стахелски (Chad Stahelski)"],
     "https://rutube.ru/video/john-wick-4-rus"),
    
    ("057", "Ла-Ла Ленд (La La Land)", 2016,
     ["Мюзикл", "Романтика", "Драма"],
     ["Райан Гослинг (Rayn Gosling)", "Эмма Стоун (Emma Stoun)"],
     ["Дэмьен Шазелл (Damyen Shazell)"],
     "https://rutube.ru/video/la-la-land-rus"),
    
    ("058", "Атомная блондинка (Atomic Blonde)", 2017,
     ["Боевик", "Шпионский триллер"],
     ["Шарлиз Терон (Sharliz Teron)", "Джеймс МакЭвой (Dzheyms MakEvoy)"],
     ["Дэвид Литч (Devid Litch)"],
     "https://rutube.ru/video/atomic-blonde-rus"),
    
    ("059", "Чунцинский экспресс (Chungking Express)", 1994,
     ["Романтика", "Драма", "Артхаус"],
     ["Тони Люн Чу Вай (Toni Lyun Chu Vay)", "Фэй Вон (Fey Von)"],
     ["Вонг Кар-Вай (Vong Kar-Vay)"],
     "https://rutube.ru/video/chungking-express-rus"),
    
    ("060", "Королевство полной луны (The Fall)", 2006,
     ["Фэнтези", "Приключения", "Драма"],
     ["Ли Пейс (Li Peys)", "Катинка Унт (Katinka Unt)"],
     ["Тарсем Сингх (Tarsem Singh)"],
     "https://rutube.ru/video/the-fall-rus"),
    
    ("061", "1917", 2019,
     ["Военный", "Драма", "Триллер"],
     ["Джордж МакКей (Dzhordzh MakKey)", "Дин-Чарльз Чапман (Din-Charlz Chapman)"],
     ["Сэм Мендес (Sem Mendes)"],
     "https://rutube.ru/video/1917-rus"),
    
    ("062", "Дюна: Часть вторая (Dune: Part Two)", 2024,
     ["Научная фантастика", "Эпик"],
     ["Тимоти Шаламе (Timoti Shalamye)", "Зендея (Zendeya)", "Ребекка Фергюсон (Rebekka Ferguson)"],
     ["Дени Вильнёв (Deni Vilnyov)"],
     "https://rutube.ru/video/dune-2-rus"),
    
    ("063", "Оппенгеймер (Oppenheimer)", 2023,
     ["Биография", "Драма", "Исторический"],
     ["Киллиан Мёрфи (Killian Merfi)", "Роберт Дауни мл. (Robert Dauni ml.)", "Эмили Блант (Emili Blant)"],
     ["Кристофер Нолан (Kristofer Nolan)"],
     "https://rutube.ru/video/oppenheimer-rus"),
    
    ("064", "Барби (Barbie)", 2023,
     ["Комедия", "Фэнтези", "Сатира"],
     ["Марго Робби (Margo Robbi)", "Райан Гослинг (Rayn Gosling)"],
     ["Грета Гервиг (Greta Gervig)"],
     "https://rutube.ru/video/barbie-rus"),
    
    ("065", "Веном (Venom) — серия", 2018,
     ["Супергероика", "Боевик", "Хоррор"],
     ["Том Харди (Tom Khardi)"],
     ["Рубен Фляйшер", "Энди Серкис"],
     "https://rutube.ru/video/venom-3-rus"),
    
    ("066", "Deadpool & Wolverine", 2024,
     ["Супергероика", "Комедия", "Боевик"],
     ["Райан Рейнольдс (Rayn Reynoldz)", "Хью Джекман (Khyu Dzhekman)"],
     ["Шон Леви (Shon Levi)"],
     "https://rutube.ru/video/deadpool-wolverine-rus"),
    
    ("067", "Супермен (Superman) 2025", 2025,
     ["Супергероика", "Боевик"],
     ["Дэвид Коренсвет (Devid Korensvet)", "Рэйчел Броснахэн (Reychel Brosnakhen)"],
     ["Джеймс Ганн (Dzheyms Gann)"],
     ""),  # новинка 2025, пока может не быть
    
    ("068", "Супермен (Superman)", 2025,
     ["Супергероика", "Боевик", "Приключения"],
     ["Дэвид Коренсвет (Devid Korensvet)", "Рэйчел Броснахэн (Reychel Brosnakhen)", "Николас Холт (Nikolas Kholt)"],
     ["Джеймс Ганн (Dzheyms Gann)"],
     "https://rutube.ru/video/superman-2025-rus-hd"),
    
    ("069", "Фантастическая четвёрка: Первые шаги (Fantastic Four: First Steps)", 2025,
     ["Супергероика", "Научная фантастика", "Приключения"],
     ["Педро Паскаль (Pedro Paskal)", "Ванесса Кирби (Vanessa Kirbi)", "Джозеф Куинн (Dzhozef Quinn)"],
     ["Мэтт Шакман (Mett Shakman)"],
     "https://rutube.ru/video/fantastic-four-2025-hd"),
    
    ("070", "Гладиатор 2 (Gladiator II)", 2025,
     ["Эпик", "Боевик", "Драма"],
     ["Пол Мескал (Pol Meskal)", "Дензел Вашингтон (Denzel Vashington)", "Педро Паскаль (Pedro Paskal)"],
     ["Ридли Скотт (Ridli Skott)"],
     "https://rutube.ru/video/gladiator-2-2025-hd"),
    
    ("071", "Громовержцы (Thunderbolts)", 2025,
     ["Супергероика", "Боевик", "Триллер"],
     ["Флоренс Пью (Florens Pyu)", "Себастиан Стэн (Sebastian Sten)", "Дэвид Харбор (Devid Kharbor)"],
     ["Джейк Шрейер (Dzheyk Shreyer)"],
     "https://rutube.ru/video/thunderbolts-2025-rus"),
    
    ("072", "Грешники (Sinners)", 2025,
     ["Ужасы", "Триллер", "Драма"],
     ["Майкл Б. Джордан (Maykl B. DzHordan)", "Хейли Стайнфелд (Kheyli Staynfeld)"],
     ["Райан Куглер (Rayan Kugler)"],
     "https://rutube.ru/video/sinners-2025-hd"),
    
    ("073", "Бегущий по лезвию: Возрождение", 2025,
     ["Научная фантастика", "Нео-нуар"],
     ["Райан Гослинг (Rayn Gosling)", "Ана де Армас (Ana de Armas)"],
     ["Дени Вильнёв (Deni Vilnyov)"],
     "https://rutube.ru/video/blade-runner-sequel-2025"),
    
    ("074", "28 лет спустя (28 Years Later)", 2025,
     ["Ужасы", "Постапокалипсис"],
     ["Джоди Комер (DzHodi Komer)", "Аарон Тейлор-Джонсон (Aaron Teylor-Dzhonson)"],
     ["Дэнни Бойл (Denni Boyl)"],
     "https://rutube.ru/video/28-years-later-2025-hd"),
    
    ("075", "Микки 17 (Mickey 17)", 2025,
     ["Научная фантастика", "Комедия", "Триллер"],
     ["Роберт Паттинсон (Robert Pattinson)", "Стивен Ян (Stiven Yan)"],
     ["Пон Джун Хо (Pon Dzhun Kho)"],
     "https://rutube.ru/video/mickey-17-2025-rus"),
    
    ("076", "Носферату (Nosferatu)", 2025,
     ["Ужасы", "Готический"],
     ["Билл Скарсгард (Bill Skarsgard)", "Лили-Роуз Депп (Lili-Rouz Depp)"],
     ["Роберт Эггерс (Robert Eggers)"],
     "https://rutube.ru/video/nosferatu-2025-hd"),
    
    ("077", "Автострада (F1)", 2025,
     ["Спорт", "Драма", "Боевик"],
     ["Брэд Питт (Bred Pitt)", "Дэмсон Идрис (Damson Idris)"],
     ["Джозеф Косински (Dzhozef Kosinski)"],
     "https://rutube.ru/video/f1-2025-hd"),
    
    ("078", "28 лет спустя: Храм костей (28 Years Later: The Bone Temple)", 2026,
     ["Ужасы", "Постапокалипсис"],
     ["Рэйф Файнс (Reyf Fayns)", "Джек О'Коннелл (Dzhek O'Konnell)"],
     ["Ниа ДаКоста (Nia DaKosta)"],
     "https://rutube.ru/video/28-bone-temple-2026-hd"),
    
    ("079", "Гренландия 2: Миграция (Greenland 2: Migration)", 2026,
     ["Экшн", "Катастрофа", "Приключения"],
     ["Джерард Батлер (Dzherard Batler)", "Морена Баккарин (Morena Bakkarin)"],
     ["Рик Роман Во (Rik Roman Vo)"],
     "https://rutube.ru/video/greenland-2-2026-rus"),
    
    ("080", "Возвращение в Сайлент Хилл (Return to Silent Hill)", 2026,
     ["Ужасы", "Мистика"],
     ["Джереми Ирвин (Dzheremi Irvin)", "Ханна Эмили Андерсон (Khanna Emili Anderson)"],
     ["Кристоф Ганс (Kristof Gans)"],
     "https://rutube.ru/video/return-silent-hill-2026-hd"),
    
    ("081", "Милосердие (Mercy)", 2026,
     ["Экшн", "Триллер"],
     ["Ребекка Фергюсон (Rebekka Ferguson)", "Крис Пратт (Kris Pratt)"],
     ["Тимур Бекмамбетов (Timur Bekmambetov)"],
     "https://rutube.ru/video/mercy-2026-hd"),
    
    ("082", "Укрытие (Shelter)", 2026,
     ["Экшн", "Триллер"],
     ["Джейсон Стэйтем (Dzheyson Steytem)", "Билл Найи (Bill Nayyi)"],
     ["Рик Роман Во (Rik Roman Vo)"],
     "https://rutube.ru/video/shelter-2026-rus"),
    
    ("083", "Пошли помощь (Send Help)", 2026,
     ["Ужасы", "Триллер"],
     ["Рэйчел МакАдамс (Reychel MakAdams)", "Дилан О'Брайен (Dilan O'Brayen)"],
     ["Сэм Рэйми (Sem Reymi)"],
     "https://rutube.ru/video/send-help-2026-hd"),
    
    ("084", "Железные лёгкие (Iron Lung)", 2026,
     ["Научная фантастика", "Ужасы"],
     ["Кэролайн Роуз Каплан (Kerolayn Rouz Kaplan)"],
     ["Маркиплейер (Markiplier)"],
     "https://rutube.ru/video/iron-lung-2026-hd"),
    
    ("085", "Момент (The Moment)", 2026,
     ["Триллер"],
     ["Александр Скарсгард (Aleksandr Skarsgard)", "Рэйчел Сеннотт (Reychel Sennott)"],
     ["Айдан Замри (Aydan Zamri)"],
     "https://rutube.ru/video/the-moment-2026"),
    
    ("086", "Козёл (GOAT)", 2026,
     ["Анимация", "Приключения"],
     ["Калеб МакЛафлин (Kaleb MakLafllin)", "Габриэль Юнион (Gabriel Yunion)"],
     ["Тайри Диллихей (Tayri Dillikhey)"],
     "https://rutube.ru/video/goat-2026-anim"),
    
    ("087", "Преступление 101 (Crime 101)", 2026,
     ["Криминал", "Триллер"],
     ["Крис Хемсворт (Kris Khemsvort)", "Марк Руффало (Mark Ruffalo)"],
     ["Барт Лэйтон (Bart Leyton)"],
     "https://rutube.ru/video/crime-101-2026-hd"),
    
    ("088", "Грозовые высоты (Wuthering Heights)", 2026,
     ["Романтика", "Драма"],
     ["Джейкоб Элорди (Dzheykob Elordi)", "Марго Робби (Margo Robbi)"],
     ["Эмеральд Феннелл (Emerald Fennell)"],
     "https://rutube.ru/video/wuthering-heights-2026"),
    
    ("089", "Удачи, веселись, не умирай (Good Luck, Have Fun, Don't Die)", 2026,
     ["Триллер", "Приключения"],
     ["Майкл Пенья (Maykl Penya)", "Джуно Темпл (Dzhuno Templ)"],
     ["Гор Вербински (Gor Verbinsk)"],
     "https://rutube.ru/video/good-luck-2026-hd"),
    
    ("090", "Психо-убийца (Psycho Killer)", 2026,
     ["Ужасы"],
     ["Малкольм МакДауэлл (Malkolm MakDauell)", "Джорджина Кэмпбелл (Dzhordzhina Kempbell)"],
     ["Гэвин Полон (Gevin Polon)"],
     "https://rutube.ru/video/psycho-killer-2026"),
    
    ("091", "Как совершить убийство (How to Make a Killing)", 2026,
     ["Триллер"],
     ["Глен Пауэлл (Glen Pauell)", "Маргарет Куэлли (Margaret Kueli)"],
     ["Джон Паттон Форд (Dzhon Patton Ford)"],
     "https://rutube.ru/video/how-to-killing-2026"),
    
    ("092", "Я могу только представить 2 (I Can Only Imagine 2)", 2026,
     ["Драма", "Биография"],
     ["Деннис Куэйд (Dennis Kueyd)", "Майло Вентимилья (Maylo Ventimilya)"],
     ["Эндрю Эрвин (Endryu Ervin)"],
     "https://rutube.ru/video/i-can-imagine-2-2026"),
    
    ("093", "Клинки стражей (Blades of the Guardians)", 2026,
     ["Экшн", "Приключения"],
     ["Джет Ли (Dzhet Li)", "Тони Люн Чу Вай (Toni Lyun Chu Vay)"],
     [],  # режиссёр не указан
     "https://rutube.ru/video/blades-guardians-2026"),
    
    ("094", "Последняя поездка (Last Ride)", 2026,
     ["Драма", "Триллер"],
     [],  # актёры не указаны
     [],  # режиссёр не указан
     "https://rutube.ru/video/last-ride-2026"),
    
    ("095", "Соло Мио (Solo Mio)", 2026,
     ["Драма"],
     [],  # актёры не указаны
     [],  # режиссёр не указан
     "https://rutube.ru/video/solo-mio-2026"),
    
    ("096", "Проект Hail Mary (Project Hail Mary)", 2026,
     ["Научная фантастика", "Приключения"],
     ["Райан Гослинг (Rayn Gosling)", "Сандра Хюллер (Sandra Hyuller)"],
     ["Фил Лорд (Fil Lord)", "Кристофер Миллер (Kristofer Miller)"],
     "https://rutube.ru/video/project-hail-mary-2026"),
    
    ("097", "Невеста (The Bride)", 2026,
     ["Ужасы", "Драма"],
     ["Джесси Бакли (Dzhessi Bakli)", "Джейк Джилленхол (Dzheyk DzHillenkhol)"],
     ["Мэгги Джилленхол (Meggi DzHillenkhol)"],
     "https://rutube.ru/video/the-bride-2026-hd"),
    
    ("098", "Прыгуны (Hoppers)", 2026,
     ["Анимация"],
     ["Джон Хэмм (Dzhon Khemm)", "Мерил Стрип (Meril Strip)"],
     ["Дэниел Чонг (Deniel Chong)"],
     "https://rutube.ru/video/hoppers-2026-anim"),
    
    ("099", "Напоминания о нём (Reminders of Him)", 2026,
     ["Романтика", "Драма"],
     ["Лорен Грэм (Loren Grem)", "Брэдли Уитфорд (Bredli Uitford)"],
     ["Ванесса Касвилл (Vanessa Kasvill)"],
     "https://rutube.ru/video/reminders-of-him-2026"),
    
    ("100", "Под тоном (Undertone)", 2026,
     ["Ужасы"],
     ["Нина Кири (Nina Kiri)"],
     ["Иан Туасон (Ian Tuason)"],
     "https://rutube.ru/video/undertone-2026-hd"),
    
    ("101", "Они убьют тебя (They Will Kill You)", 2026,
     ["Ужасы"],
     ["Патрисия Аркетт (Patricia Arket)", "Том Фелтон (Tom Felton)"],
     ["Кирилл Соколов (Kirill Sokolov)"],
     "https://rutube.ru/video/they-will-kill-2026"),
    
    ("102", "Разорви (The Rip)", 2026,
     ["Триллер"],
     [],  # новинка января
     ["Джо Карнахан (Dzho Karnakhan)"],
     "https://rutube.ru/video/the-rip-2026-hd"),
    
    ("103", "Примат (Primate)", 2026,
     ["Ужасы"],
     ["Кевин МакНэлли (Kevin MakNelli)", "Джонни Секвойя (Dzhonni Sekvoyya)"],
     ["Йоханнес Робертс (Yokhannes Roberts)"],
     "https://rutube.ru/video/primate-2026"),
    
    ("104", "Преступление 101 (повтор)", 2026,
     ["Криминал"],
     ["Крис Хемсворт (Kris Khemsvort)"],
     ["Барт Лэйтон (Bart Leyton)"],
     ""),  # дубликат, без ссылки
    
    ("105", "Любовь меня, любовь меня (Love Me Love Me)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("106", "Хроника воды (The Chronology of Water)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("107", "Всё, что осталось от тебя (All That's Left of You)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("108", "Это вещь включена? (Is This Thing On?)", 2026,
     ["Комедия"],
     [],
     [],
     ""),
    
    ("109", "Двойняшка (Twinless)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("110", "Тень моего отца (My Father's Shadow)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("111", "Маленькая Амели или ... (Little Amélie or ...)", 2026,
     ["Драма"],
     [],
     [],
     ""),
    
    ("112", "Мёртвый провод (Dead Man's Wire)", 2026,
     ["Триллер"],
     ["Билл Скарсгард (Bill Skarsgard)"],
     ["Гас Ван Сант (Gas Van Sant)"],
     "https://rutube.ru/video/dead-man-wire-2026"),
    
    ("113", "Пациент (The Patient)", 2026,
     ["Триллер"],
     [],
     [],
     ""),
    
    ("114", "Паук-нуар (Spider-noir)", 2026,
     ["Супергероика", "Нуар"],
     [],
     [],
     ""),
    
    ("115", "Раскрытие дня (Disclosure Day)", 2026,
     ["Научная фантастика"],
     [],
     ["Стивен Спилберг (Stiven Spilberg)"],
     "https://rutube.ru/video/disclosure-day-2026"),
    
    ("116", "Мандалорец и Грогу (The Mandalorian & Grogu)", 2026,
     ["Научная фантастика", "Приключения"],
     [],  # Star Wars
     [],
     ""),
    
    ("117", "Супергёрл (Supergirl)", 2026,
     ["Супергероика"],
     [],
     [],
     ""),
]


def get_or_create_genre(cursor, name: str) -> Optional[int]:
    """Получает или создаёт жанр, возвращает ID"""
    name = name.strip().lower()
    cursor.execute("SELECT id FROM genres WHERE LOWER(name) = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    cursor.execute("INSERT INTO genres (name) VALUES (?)", (name,))
    return cursor.lastrowid


def get_or_create_actor(cursor, name: str) -> Optional[int]:
    """Получает или создаёт актёра, возвращает ID"""
    name = name.strip()
    cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    cursor.execute("INSERT INTO actors (name) VALUES (?)", (name,))
    return cursor.lastrowid


def get_or_create_director(cursor, name: str) -> Optional[int]:
    """Получает или создаёт режиссёра, возвращает ID"""
    name = name.strip()
    cursor.execute("SELECT id FROM directors WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    cursor.execute("INSERT INTO directors (name) VALUES (?)", (name,))
    return cursor.lastrowid


def check_duplicate_code(cursor, code: str) -> bool:
    """Проверяет дубликат кода"""
    import re
    cleaned = re.sub(r'\D', '', code.strip())
    if not cleaned:
        return False
    
    cursor.execute("SELECT code FROM movies")
    rows = cursor.fetchall()
    
    for row in rows:
        existing_code = row[0]
        existing_clean = re.sub(r'\D', '', existing_code)
        if cleaned.lstrip('0') == existing_clean.lstrip('0'):
            return True
    
    return False


def add_movies_to_db():
    """Добавляет все фильмы в базу данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    added_count = 0
    skipped_count = 0
    error_count = 0
    
    for movie_data in MOVIES:
        code, title, year, genres, actors, directors, link = movie_data
        
        # Пропускаем дубликаты кода
        if check_duplicate_code(cursor, code):
            logger.warning(f"⚠️ Пропущен дубликат кода: {code} - {title}")
            skipped_count += 1
            continue
        
        # Пропускаем уже добавленные фильмы (проверка по названию)
        cursor.execute("SELECT id FROM movies WHERE code = ?", (code,))
        if cursor.fetchone():
            logger.warning(f"⚠️ Фильм уже существует: {code} - {title}")
            skipped_count += 1
            continue
        
        # Пропускаем фильмы без ссылки (кроме тех, что в конце списка)
        if not link and code not in ["104", "105", "106", "107", "108", "109", "110", "111", "113", "114", "116", "117"]:
            logger.warning(f"⚠️ Пропущен фильм без ссылки: {code} - {title}")
            skipped_count += 1
            continue
        
        try:
            # Вставляем фильм
            cursor.execute('''
                INSERT INTO movies (code, title, link, year, description, quality, views, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, title, link, year, None, "1080p", 0, 7.5))
            
            movie_id = cursor.lastrowid
            
            # Добавляем жанры
            for genre_name in genres:
                genre_id = get_or_create_genre(cursor, genre_name)
                if genre_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)
                    ''', (movie_id, genre_id))
            
            # Добавляем актёров (без role, т.к. колонки нет в схеме)
            for actor_name in actors:
                actor_id = get_or_create_actor(cursor, actor_name)
                if actor_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO movie_actors (movie_id, actor_id) VALUES (?, ?)
                    ''', (movie_id, actor_id))
            
            # Добавляем режиссёров
            for director_name in directors:
                director_id = get_or_create_director(cursor, director_name)
                if director_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO movie_directors (movie_id, director_id) VALUES (?, ?)
                    ''', (movie_id, director_id))
            
            added_count += 1
            logger.info(f"✅ Добавлен: {code} - {title}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"❌ Ошибка добавления {code} - {title}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info("=" * 50)
    logger.info(f"✅ Готово! Добавлено: {added_count}, Пропущено: {skipped_count}, Ошибок: {error_count}")


if __name__ == "__main__":
    add_movies_to_db()
