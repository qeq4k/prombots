import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        """Инициализация подключения к БД и создание таблиц"""
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            logger.info(f"✅ Подключение к БД установлено: {db_path}")

            self.create_tables()
            self.run_migrations()
            logger.info("✅ Таблицы БД проверены/созданы")

        except Exception as e:
            logger.critical(f"❌ Ошибка инициализации БД: {e}", exc_info=True)
            raise

    def create_tables(self):
        """Создание всех необходимых таблиц"""
        # Таблица фильмов (обновлённая)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                year INTEGER,
                description TEXT,
                poster_url TEXT,
                banner_url TEXT,
                trailer_url TEXT,
                quality TEXT DEFAULT '1080p',
                views INTEGER DEFAULT 0,
                rating REAL DEFAULT 0.0,
                duration INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица жанров
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS genres (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')

        # Связь фильмов и жанров (многие-ко-многим)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movie_genres (
                movie_id INTEGER NOT NULL,
                genre_id INTEGER NOT NULL,
                PRIMARY KEY (movie_id, genre_id),
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
                FOREIGN KEY (genre_id) REFERENCES genres(id) ON DELETE CASCADE
            )
        ''')

        # Таблица актёров
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS actors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        ''')

        # Связь фильмов и актёров (многие-ко-многим)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movie_actors (
                movie_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                role TEXT,
                PRIMARY KEY (movie_id, actor_id),
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
                FOREIGN KEY (actor_id) REFERENCES actors(id) ON DELETE CASCADE
            )
        ''')

        # Таблица режиссёров
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS directors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        ''')

        # Связь фильмов и режиссёров (многие-ко-многим)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movie_directors (
                movie_id INTEGER NOT NULL,
                director_id INTEGER NOT NULL,
                PRIMARY KEY (movie_id, director_id),
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
                FOREIGN KEY (director_id) REFERENCES directors(id) ON DELETE CASCADE
            )
        ''')

        # Таблица каналов для подписки
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                link TEXT NOT NULL,
                chat_id TEXT NOT NULL UNIQUE
            )
        ''')

        # Таблица пользователей (обновлённая)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'ru',
                is_subscribed BOOLEAN DEFAULT 0,
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_search_at TIMESTAMP,
                total_searches INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # История поисков
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                query_type TEXT NOT NULL,
                results_count INTEGER DEFAULT 0,
                found_movie_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (found_movie_id) REFERENCES movies(id) ON DELETE SET NULL
            )
        ''')

        # Избранное пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, movie_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
            )
        ''')

        # Аналитика просмотров
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS view_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movie_id INTEGER NOT NULL,
                user_id INTEGER,
                viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
        ''')

        # Лог посещений бота
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # Лог пустых поисковых запросов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS empty_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT NOT NULL,
                query_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
        ''')

        # Миграции
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Индексы для ускорения поиска
        self.cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_code ON movies(code)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_history_created ON search_history(created_at)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_view_analytics_movie ON view_analytics(movie_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_empty_searches_created ON empty_searches(created_at)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_visits_user ON user_visits(user_id)')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_visits_time ON user_visits(visited_at)')

        # Таблица достижений пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL,
                achievement_type TEXT NOT NULL,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_type),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # Таблица реакций на фильмы
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS movie_reactions (
                user_id INTEGER NOT NULL,
                movie_id INTEGER NOT NULL,
                movie_code TEXT NOT NULL,
                reaction_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, movie_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
            )
        ''')

        # Таблица уведомлений
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                movie_id INTEGER,
                notification_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
            )
        ''')

        # Таблица настроек пользователей (уведомления и т.д.)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                notifications_enabled BOOLEAN DEFAULT 1,
                reminders_enabled BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        self.conn.commit()
        logger.info("✅ Таблицы БД созданы/проверены")

    def run_migrations(self):
        """Запуск миграций базы данных"""
        migrations = [
            ("add_rating_to_movies", self._migration_add_rating),
            ("add_duration_to_movies", self._migration_add_duration),
            ("add_user_stats", self._migration_add_user_stats),
            ("add_banner_trailer", self._migration_add_banner_trailer),
            ("add_user_visits", self._migration_add_user_visits),
        ]

        for name, migration_func in migrations:
            self.cursor.execute("SELECT 1 FROM migrations WHERE name = ?", (name,))
            if not self.cursor.fetchone():
                try:
                    migration_func()
                    self.cursor.execute("INSERT INTO migrations (name) VALUES (?)", (name,))
                    self.conn.commit()
                    logger.info(f"✅ Миграция применена: {name}")
                except Exception as e:
                    logger.error(f"❌ Ошибка миграции {name}: {e}")

    def _migration_add_banner_trailer(self):
        """Добавляет поля banner_url и trailer_url"""
        try:
            self.cursor.execute("ALTER TABLE movies ADD COLUMN banner_url TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE movies ADD COLUMN trailer_url TEXT")
        except sqlite3.OperationalError:
            pass

    def _migration_add_user_visits(self):
        """Создаёт таблицу для отслеживания посещений бота"""
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_visits_user ON user_visits(user_id)")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_visits_time ON user_visits(visited_at)")
            logger.info("✅ Таблица user_visits создана")
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблицы user_visits: {e}")

    def _migration_add_rating(self):
        """Добавляет рейтинг к фильмам"""
        try:
            self.cursor.execute("ALTER TABLE movies ADD COLUMN rating REAL DEFAULT 0.0")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

    def _migration_add_duration(self):
        """Добавляет длительность фильма"""
        try:
            self.cursor.execute("ALTER TABLE movies ADD COLUMN duration INTEGER")
        except sqlite3.OperationalError:
            pass

    def _migration_add_user_stats(self):
        """Добавляет статистику пользователям"""
        try:
            self.cursor.execute("ALTER TABLE users ADD COLUMN last_search_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE users ADD COLUMN total_searches INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    # ==================== MOVIES ====================

    def add_movie(self, code: str, title: str, link: str,
                  year: int = None, description: str = None,
                  poster_url: str = None, banner_url: str = None,
                  trailer_url: str = None, quality: str = "1080p",
                  genres: List[str] = None, actors: List[str] = None,
                  rating: float = None, duration: int = None,
                  directors: List[str] = None) -> bool:
        """Добавляет фильм в базу данных"""
        try:
            # Проверяем дубликаты с учётом универсального поиска
            if self.check_code_duplicate(code):
                logger.warning(f"❌ Попытка добавить дубликат кода '{code}' (универсальный поиск)")
                return False

            self.cursor.execute('''
                INSERT INTO movies (code, title, link, year, description, poster_url, banner_url, trailer_url, quality, views, rating, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, title, link, year, description, poster_url, banner_url, trailer_url, quality, 0, rating, duration))

            movie_id = self.cursor.lastrowid

            # Добавляем жанры
            if genres:
                for genre_name in genres:
                    genre_id = self._get_or_create_genre(genre_name)
                    if genre_id:
                        self.cursor.execute('''
                            INSERT OR IGNORE INTO movie_genres (movie_id, genre_id) VALUES (?, ?)
                        ''', (movie_id, genre_id))

            # Добавляем актёров
            if actors:
                for actor_name in actors:
                    actor_id = self._get_or_create_actor(actor_name)
                    if actor_id:
                        self.cursor.execute('''
                            INSERT OR IGNORE INTO movie_actors (movie_id, actor_id, role) VALUES (?, ?, ?)
                        ''', (movie_id, actor_id, None))

            # Добавляем режиссёров
            if directors:
                for director_name in directors:
                    director_id = self._get_or_create_director(director_name)
                    if director_id:
                        self.cursor.execute('''
                            INSERT OR IGNORE INTO movie_directors (movie_id, director_id) VALUES (?, ?)
                        ''', (movie_id, director_id))

            self.conn.commit()
            logger.info(f"✅ Фильм добавлен: код={code}, название={title}, ID={movie_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления фильма: {e}", exc_info=True)
            return False

    def check_code_duplicate(self, code: str) -> bool:
        """
        Проверяет есть ли дубликат кода с учётом универсального поиска.
        Например: если есть код "001", то код "1" будет дубликатом.
        
        Returns:
            True если дубликат найден, False если код уникален
        """
        import re
        
        # Очищаем код
        cleaned = re.sub(r'\D', '', code.strip())
        if not cleaned:
            return False
        
        # Получаем все коды из базы
        self.cursor.execute("SELECT code FROM movies")
        rows = self.cursor.fetchall()
        
        for row in rows:
            existing_code = row[0]
            existing_clean = re.sub(r'\D', '', existing_code)
            
            # Сравниваем нормализованные коды (без ведущих нулей)
            if cleaned.lstrip('0') == existing_clean.lstrip('0'):
                return True
        
        return False

    def get_movie_by_code(self, code: str):
        """Получает фильм по коду (синхронная версия)"""
        try:
            self.cursor.execute("SELECT * FROM movies WHERE code = ?", (code,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения фильма по коду {code}: {e}")
            return None

    async def get_movie_by_code_cached(self, code: str) -> Optional[Dict]:
        """Получает фильм по коду с кэшированием в Redis"""
        from cache import MovieCache
        
        # Проверяем кэш
        cached = await MovieCache.get_by_code(code)
        if cached:
            return cached
        
        # Получаем из БД
        movie = self.get_movie_by_code(code)
        
        # Сохраняем в кэш
        if movie:
            await MovieCache.set_by_code(code, movie, expire=3600)
        
        return movie

    def get_movie_by_id(self, movie_id: int):
        """Получает фильм по ID"""
        try:
            self.cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения фильма по ID {movie_id}: {e}")
            return None

    def get_all_movies(self, limit: int = 10000, offset: int = 0):
        """Получает все фильмы (с лимитом и offset), отсортированные по коду"""
        try:
            # Сортируем по коду как по числу (с учётом ведущих нулей)
            self.cursor.execute("""
                SELECT * FROM movies 
                ORDER BY 
                    CASE 
                        WHEN code GLOB '[0-9]*' THEN CAST(code AS INTEGER)
                        ELSE 999999999
                    END ASC,
                    code ASC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка фильмов: {e}")
            return []

    def get_movies_count(self) -> int:
        """Получает общее количество фильмов"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM movies")
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества фильмов: {e}")
            return 0
    
    def get_users_count(self) -> int:
        """Получает общее количество пользователей"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM users")
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества пользователей: {e}")
            return 0
    
    def get_searches_count_days(self, days: int = 7) -> int:
        """Получает количество поисковых запросов за N дней"""
        try:
            self.cursor.execute("""
                SELECT COUNT(*) FROM search_history 
                WHERE created_at > datetime('now', ? days)
            """, (-days,))
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества поисков: {e}")
            return 0
    
    def get_favorites_count(self) -> int:
        """Получает количество избранных фильмов"""
        try:
            self.cursor.execute("SELECT COUNT(*) FROM favorites")
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества избранных: {e}")
            return 0
    
    def get_new_users_count_days(self, days: int = 7) -> int:
        """Получает количество новых пользователей за N дней"""
        try:
            self.cursor.execute("""
                SELECT COUNT(*) FROM users 
                WHERE created_at > datetime('now', ? days)
            """, (-days,))
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества новых пользователей: {e}")
            return 0

    def update_movie(self, code: str, **kwargs) -> bool:
        """Обновляет данные фильма"""
        try:
            movie = self.get_movie_by_code(code)
            if not movie:
                return False

            allowed_fields = ['title', 'link', 'year', 'description', 'poster_url', 'banner_url', 'trailer_url', 'quality', 'rating', 'duration']
            updates = []
            values = []

            for field, value in kwargs.items():
                if field in allowed_fields:
                    updates.append(f"{field} = ?")
                    values.append(value)

            if not updates:
                return False

            values.append(code)
            query = f"UPDATE movies SET {', '.join(updates)} WHERE code = ?"
            self.cursor.execute(query, values)
            self.conn.commit()

            logger.info(f"✅ Фильм обновлён: код={code}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления фильма: {e}")
            return False

    def delete_movie(self, code: str) -> bool:
        """Удаляет фильм по коду"""
        try:
            movie = self.get_movie_by_code(code)
            if not movie:
                return False

            self.cursor.execute("DELETE FROM movies WHERE code = ?", (code,))
            self.conn.commit()
            logger.info(f"✅ Фильм удалён: код={code}")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления фильма: {e}")
            return False

    def increment_views(self, code: str):
        """Увеличивает счётчик просмотров"""
        try:
            self.cursor.execute("UPDATE movies SET views = views + 1 WHERE code = ?", (code,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка увеличения просмотров для {code}: {e}")

    def log_view(self, movie_id: int, user_id: int = None):
        """Логирует просмотр фильма для аналитики"""
        try:
            self.cursor.execute('''
                INSERT INTO view_analytics (movie_id, user_id) VALUES (?, ?)
            ''', (movie_id, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка логирования просмотра: {e}")

    # ==================== GENRES ====================

    def _get_or_create_genre(self, name: str) -> Optional[int]:
        """Получает или создаёт жанр, возвращает ID"""
        try:
            name = name.strip().lower()
            self.cursor.execute("SELECT id FROM genres WHERE LOWER(name) = ?", (name,))
            row = self.cursor.fetchone()
            if row:
                return row[0]

            self.cursor.execute("INSERT INTO genres (name) VALUES (?)", (name,))
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка работы с жанром {name}: {e}")
            return None

    def get_all_genres(self) -> List[Dict]:
        """Получает все жанры"""
        try:
            self.cursor.execute("SELECT * FROM genres ORDER BY name")
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения жанров: {e}")
            return []

    def get_movie_genres(self, movie_id: int) -> List[str]:
        """Получает жанры фильма"""
        try:
            self.cursor.execute('''
                SELECT g.name FROM genres g
                JOIN movie_genres mg ON g.id = mg.genre_id
                WHERE mg.movie_id = ?
            ''', (movie_id,))
            rows = self.cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения жанров фильма: {e}")
            return []

    def get_movies_by_genre(self, genre: str, limit: int = 20) -> List[Dict]:
        """Получает фильмы по жанру"""
        try:
            self.cursor.execute('''
                SELECT m.* FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE LOWER(g.name) = ?
                ORDER BY m.views DESC
                LIMIT ?
            ''', (genre.lower(), limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения фильмов по жанру: {e}")
            return []

    # ==================== ACTORS ====================

    def _get_or_create_actor(self, name: str) -> Optional[int]:
        """Получает или создаёт актёра, возвращает ID"""
        try:
            name = name.strip()
            self.cursor.execute("SELECT id FROM actors WHERE name = ?", (name,))
            row = self.cursor.fetchone()
            if row:
                return row[0]

            self.cursor.execute("INSERT INTO actors (name) VALUES (?)", (name,))
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка работы с актёром {name}: {e}")
            return None

    def get_movie_actors(self, movie_id: int) -> List[Dict]:
        """Получает актёров фильма"""
        try:
            self.cursor.execute('''
                SELECT a.name FROM actors a
                JOIN movie_actors ma ON a.id = ma.actor_id
                WHERE ma.movie_id = ?
            ''', (movie_id,))
            rows = self.cursor.fetchall()
            return [{'name': row[0]} for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения актёров фильма: {e}")
            return []

    def get_movies_by_actor(self, actor: str, limit: int = 20) -> List[Dict]:
        """Получает фильмы по актёру"""
        try:
            self.cursor.execute('''
                SELECT m.* FROM movies m
                JOIN movie_actors ma ON m.id = ma.movie_id
                JOIN actors a ON ma.actor_id = a.id
                WHERE a.name = ?
                ORDER BY m.views DESC
                LIMIT ?
            ''', (actor, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения фильмов по актёру: {e}")
            return []

    # ==================== DIRECTORS ====================

    def _get_or_create_director(self, name: str) -> Optional[int]:
        """Получает или создаёт режиссёра, возвращает ID"""
        try:
            name = name.strip()
            self.cursor.execute("SELECT id FROM directors WHERE name = ?", (name,))
            row = self.cursor.fetchone()
            if row:
                return row[0]

            self.cursor.execute("INSERT INTO directors (name) VALUES (?)", (name,))
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка работы с режиссёром {name}: {e}")
            return None

    def get_movie_directors(self, movie_id: int) -> List[Dict]:
        """Получает режиссёров фильма"""
        try:
            self.cursor.execute('''
                SELECT d.name FROM directors d
                JOIN movie_directors md ON d.id = md.director_id
                WHERE md.movie_id = ?
            ''', (movie_id,))
            rows = self.cursor.fetchall()
            return [{'name': row[0]} for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения режиссёров фильма: {e}")
            return []

    def get_movies_by_director(self, director: str, limit: int = 20) -> List[Dict]:
        """Получает фильмы по режиссёру"""
        try:
            self.cursor.execute('''
                SELECT m.* FROM movies m
                JOIN movie_directors md ON m.id = md.movie_id
                JOIN directors d ON md.director_id = d.id
                WHERE d.name = ?
                ORDER BY m.views DESC
                LIMIT ?
            ''', (director, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения фильмов по режиссёру: {e}")
            return []

    def get_all_directors(self, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получает уникальных режиссёров с количеством фильмов (с пагинацией)"""
        try:
            self.cursor.execute("""
                SELECT d.name, COUNT(md.movie_id) as film_count
                FROM directors d
                JOIN movie_directors md ON d.id = md.director_id
                GROUP BY d.name
                ORDER BY d.name
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = self.cursor.fetchall()
            return [{'name': row[0], 'film_count': row[1]} for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка режиссёров: {e}")
            return []

    def get_all_actors(self, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получает уникальных актёров с количеством фильмов (с пагинацией)"""
        try:
            self.cursor.execute("""
                SELECT a.name, COUNT(ma.movie_id) as film_count
                FROM actors a
                JOIN movie_actors ma ON a.id = ma.actor_id
                GROUP BY a.name
                ORDER BY a.name
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = self.cursor.fetchall()
            return [{'name': row[0], 'film_count': row[1]} for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка актёров: {e}")
            return []

    def get_actors_count(self) -> int:
        """Получает общее количество уникальных актёров"""
        try:
            self.cursor.execute("""
                SELECT COUNT(DISTINCT a.name) FROM actors a
                JOIN movie_actors ma ON a.id = ma.actor_id
            """)
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества актёров: {e}")
            return 0

    def get_directors_count(self) -> int:
        """Получает общее количество уникальных режиссёров"""
        try:
            self.cursor.execute("""
                SELECT COUNT(DISTINCT d.name) FROM directors d
                JOIN movie_directors md ON d.id = md.director_id
            """)
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка получения количества режиссёров: {e}")
            return 0

    def search_movies_by_actor_fuzzy(self, actor_query: str, limit: int = 20) -> List[Dict]:
        """Поиск фильмов по актёру с нечётким поиском (LIKE)"""
        try:
            self.cursor.execute('''
                SELECT DISTINCT m.* FROM movies m
                JOIN movie_actors ma ON m.id = ma.movie_id
                JOIN actors a ON ma.actor_id = a.id
                WHERE a.name LIKE ? COLLATE NOCASE
                ORDER BY m.views DESC
                LIMIT ?
            ''', (f"%{actor_query}%", limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка fuzzy-поиска по актёру: {e}")
            return []

    def search_movies_by_director_fuzzy(self, director_query: str, limit: int = 20) -> List[Dict]:
        """Поиск фильмов по режиссёру с нечётким поиском (LIKE)"""
        try:
            self.cursor.execute('''
                SELECT DISTINCT m.* FROM movies m
                JOIN movie_directors md ON m.id = md.movie_id
                JOIN directors d ON md.director_id = d.id
                WHERE d.name LIKE ? COLLATE NOCASE
                ORDER BY m.views DESC
                LIMIT ?
            ''', (f"%{director_query}%", limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка fuzzy-поиска по режиссёру: {e}")
            return []

    def search_movies_by_genre_fuzzy(self, genre_query: str, limit: int = 20) -> List[Dict]:
        """Поиск фильмов по жанру с нечётким поиском (LIKE)"""
        try:
            self.cursor.execute('''
                SELECT DISTINCT m.* FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE g.name LIKE ? COLLATE NOCASE
                ORDER BY m.views DESC
                LIMIT ?
            ''', (f"%{genre_query}%", limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка fuzzy-поиска по жанру: {e}")
            return []

    def get_movies_by_genre_count(self, genre: str) -> int:
        """Получает количество фильмов по жанру"""
        try:
            self.cursor.execute('''
                SELECT COUNT(DISTINCT m.id) FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE LOWER(g.name) = ?
            ''', (genre.lower(),))
            row = self.cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Ошибка подсчёта фильмов по жанру: {e}")
            return 0

    def get_movies_by_genre_paginated(self, genre: str, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Получает фильмы по жанру с пагинацией"""
        try:
            self.cursor.execute('''
                SELECT DISTINCT m.* FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                JOIN genres g ON mg.genre_id = g.id
                WHERE LOWER(g.name) = ?
                ORDER BY m.views DESC
                LIMIT ? OFFSET ?
            ''', (genre.lower(), limit, offset))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения фильмов по жанру с пагинацией: {e}")
            return []

    # ==================== CHANNELS ====================

    def add_channel(self, name: str, link: str, chat_id: str) -> bool:
        """Добавляет канал для проверки подписки"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO channels (name, link, chat_id)
                VALUES (?, ?, ?)
            ''', (name, link, chat_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления канала {name}: {e}")
            return False

    def get_channels(self):
        """Получает список всех каналов"""
        try:
            self.cursor.execute("SELECT * FROM channels")
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка полу��ения списка каналов: {e}")
            return []

    def delete_channel(self, chat_id: str) -> bool:
        """Удаляет канал"""
        try:
            self.cursor.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления канала: {e}")
            return False

    # ==================== USERS ====================

    def set_user_language(self, user_id: int, language: str):
        """Устанавливает язык пользователя"""
        try:
            self.cursor.execute('''
                INSERT INTO users (user_id, language)
                VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
            ''', (user_id, language))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка установки языка для {user_id}: {e}")

    def get_user_language(self, user_id: int) -> str:
        """Получает язык пользователя"""
        try:
            self.cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            return row[0] if row else "ru"
        except Exception as e:
            logger.error(f"Ошибка получения языка для {user_id}: {e}")
            return "ru"

    def update_user_subscription(self, user_id: int, is_subscribed: bool):
        """Обновляет статус подписки пользователя"""
        try:
            self.cursor.execute('''
                INSERT INTO users (user_id, is_subscribed, subscribed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET
                    is_subscribed = excluded.is_subscribed,
                    subscribed_at = CURRENT_TIMESTAMP
            ''', (user_id, is_subscribed))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления подписки для {user_id}: {e}")

    def log_user_search(self, user_id: int, query: str, query_type: str, 
                        results_count: int = 0, found_movie_id: int = None):
        """Логирует поисковый запрос пользователя"""
        try:
            self.cursor.execute('''
                INSERT INTO search_history (user_id, query, query_type, results_count, found_movie_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, query, query_type, results_count, found_movie_id))

            # Обновляем статистику пользователя
            self.cursor.execute('''
                INSERT INTO users (user_id, last_search_at, total_searches)
                VALUES (?, CURRENT_TIMESTAMP, 1) ON CONFLICT(user_id) DO UPDATE SET
                    last_search_at = CURRENT_TIMESTAMP,
                    total_searches = total_searches + 1
            ''', (user_id,))

            self.conn.commit()

            # Если ничего не найдено, логируем в empty_searches
            if results_count == 0:
                self.cursor.execute('''
                    INSERT INTO empty_searches (user_id, query, query_type)
                    VALUES (?, ?, ?)
                ''', (user_id, query, query_type))
                self.conn.commit()

        except Exception as e:
            logger.error(f"Ошибка логирования поиска: {e}")

    def get_user_search_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получает историю поисков пользователя"""
        try:
            self.cursor.execute('''
                SELECT * FROM search_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения истории поиска: {e}")
            return []

    def get_user_view_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получает историю просмотров фильмов пользователем (с кодами фильмов)"""
        try:
            self.cursor.execute('''
                SELECT m.code, m.title, m.year, m.link, v.viewed_at
                FROM view_analytics v
                JOIN movies m ON v.movie_id = m.id
                WHERE v.user_id = ?
                ORDER BY v.viewed_at DESC
                LIMIT ?
            ''', (user_id, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения истории просмотров: {e}")
            return []

    def get_user_stats(self, user_id: int) -> Dict:
        """Получает статистику пользователя"""
        try:
            self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = self.cursor.fetchone()
            if row:
                return dict(row)
            return {"user_id": user_id, "total_searches": 0, "last_search_at": None}
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя: {e}")
            return {}

    # ==================== FAVORITES ====================

    def add_to_favorites(self, user_id: int, movie_id: int) -> bool:
        """Добавляет фильм в избранное"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO favorites (user_id, movie_id) VALUES (?, ?)
            ''', (user_id, movie_id))
            self.conn.commit()
            logger.info(f"✅ Добавлено в избранное: user={user_id}, movie={movie_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления в избранное: {e}")
            return False

    def remove_from_favorites(self, user_id: int, movie_id: int) -> bool:
        """Удаляет фильм из избранного"""
        try:
            self.cursor.execute('''
                DELETE FROM favorites WHERE user_id = ? AND movie_id = ?
            ''', (user_id, movie_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления из избранного: {e}")
            return False

    def get_user_favorites(self, user_id: int) -> List[Dict]:
        """Получает избранные фильмы пользователя"""
        try:
            self.cursor.execute('''
                SELECT m.*, f.added_at FROM movies m
                JOIN favorites f ON m.id = f.movie_id
                WHERE f.user_id = ?
                ORDER BY f.added_at DESC
            ''', (user_id,))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения избранного: {e}")
            return []

    def is_in_favorites(self, user_id: int, movie_id: int) -> bool:
        """Проверяет, есть ли фильм в избранном"""
        try:
            self.cursor.execute('''
                SELECT 1 FROM favorites WHERE user_id = ? AND movie_id = ?
            ''', (user_id, movie_id))
            return self.cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка проверки избранного: {e}")
            return False

    # ==================== ANALYTICS ====================

    def get_top_movies(self, limit: int = 10, period_days: int = None) -> List[Dict]:
        """Получает топ фильмов по просмотрам"""
        try:
            if period_days:
                self.cursor.execute('''
                    SELECT m.*, COUNT(v.id) as period_views 
                    FROM movies m
                    LEFT JOIN view_analytics v ON m.id = v.movie_id 
                        AND v.viewed_at >= datetime('now', '-' || ? || ' days')
                    GROUP BY m.id
                    ORDER BY period_views DESC
                    LIMIT ?
                ''', (period_days, limit))
            else:
                self.cursor.execute('''
                    SELECT * FROM movies ORDER BY views DESC LIMIT ?
                ''', (limit,))

            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения топа фильмов: {e}")
            return []

    def get_top_searches(self, limit: int = 10, period_days: int = 7) -> List[Dict]:
        """Получает топ поисковых запросов"""
        try:
            self.cursor.execute('''
                SELECT query, query_type, COUNT(*) as search_count, 
                       SUM(results_count) as total_results
                FROM search_history
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY query, query_type
                ORDER BY search_count DESC
                LIMIT ?
            ''', (period_days, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения топа поисков: {e}")
            return []

    def get_empty_searches_stats(self, period_days: int = 7) -> List[Dict]:
        """Получает статистику пустых поисковых запросов"""
        try:
            self.cursor.execute('''
                SELECT query, query_type, COUNT(*) as count
                FROM empty_searches
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                GROUP BY query, query_type
                ORDER BY count DESC
                LIMIT 20
            ''', (period_days,))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения статистики пустых поисков: {e}")
            return []

    def get_general_stats(self) -> Dict:
        """Получает общую статистику"""
        try:
            stats = {}

            self.cursor.execute("SELECT COUNT(*) FROM movies")
            stats['total_movies'] = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT SUM(views) FROM movies")
            stats['total_views'] = self.cursor.fetchone()[0] or 0

            self.cursor.execute("SELECT COUNT(DISTINCT user_id) FROM search_history")
            stats['active_users'] = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM search_history WHERE created_at >= datetime('now', '-1 day')")
            stats['searches_today'] = self.cursor.fetchone()[0]

            self.cursor.execute("SELECT COUNT(*) FROM search_history WHERE created_at >= datetime('now', '-7 days')")
            stats['searches_week'] = self.cursor.fetchone()[0]

            return stats

        except Exception as e:
            logger.error(f"Ошибка получения общей статистики: {e}")
            return {}

    # ==================== SEARCH ====================

    def search_movies_by_title_sql(self, query: str, limit: int = 10) -> List[Dict]:
        """Поиск фильмов по названию через SQL LIKE"""
        try:
            query_clean = query.lower().strip()

            # Поиск по точному совпадению
            self.cursor.execute('''
                SELECT * FROM movies WHERE LOWER(title) = ? LIMIT ?
            ''', (query_clean, limit))
            exact = self.cursor.fetchall()

            # Поиск по началу названия
            self.cursor.execute('''
                SELECT * FROM movies WHERE LOWER(title) LIKE ? LIMIT ?
            ''', (f"{query_clean}%", limit))
            starts_with = self.cursor.fetchall()

            # Поиск по содержимому
            self.cursor.execute('''
                SELECT * FROM movies WHERE LOWER(title) LIKE ? LIMIT ?
            ''', (f"%{query_clean}%", limit))
            contains = self.cursor.fetchall()

            # Объединяем результаты с приоритетом
            seen = set()
            results = []

            for row in exact:
                if row['code'] not in seen:
                    results.append(dict(row))
                    seen.add(row['code'])

            for row in starts_with:
                if row['code'] not in seen:
                    results.append(dict(row))
                    seen.add(row['code'])

            for row in contains:
                if row['code'] not in seen:
                    results.append(dict(row))
                    seen.add(row['code'])

            return results[:limit]

        except Exception as e:
            logger.error(f"Ошибка поиска по названию: {e}")
            return []

    def search_movies_by_actor(self, actor_query: str, limit: int = 10) -> List[Dict]:
        """Поиск фильмов по актёру"""
        try:
            # Используем COLLATE NOCASE для регистронезависимого поиска
            self.cursor.execute('''
                SELECT DISTINCT m.* FROM movies m
                JOIN movie_actors ma ON m.id = ma.movie_id
                JOIN actors a ON ma.actor_id = a.id
                WHERE a.name LIKE ? COLLATE NOCASE
                ORDER BY m.views DESC
                LIMIT ?
            ''', (f"%{actor_query}%", limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка поиска по актёру: {e}")
            return []

    def get_similar_movies(self, movie_id: int, limit: int = 5) -> List[Dict]:
        """Получает похожие фильмы по жанрам"""
        try:
            self.cursor.execute('''
                SELECT DISTINCT m.*, COUNT(mg.genre_id) as common_genres
                FROM movies m
                JOIN movie_genres mg ON m.id = mg.movie_id
                WHERE mg.genre_id IN (
                    SELECT genre_id FROM movie_genres WHERE movie_id = ?
                )
                AND m.id != ?
                GROUP BY m.id
                ORDER BY common_genres DESC, m.views DESC
                LIMIT ?
            ''', (movie_id, movie_id, limit))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения похожих фильмов: {e}")
            return []

    # ==================== USER VISITS & STATS ====================

    def log_user_visit(self, user_id: int):
        """Логирует посещение бота пользователем"""
        try:
            self.cursor.execute('''
                INSERT INTO user_visits (user_id) VALUES (?)
            ''', (user_id,))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Ошибка логирования посещения: {e}")

    def get_user_visits_stats(self, admin_ids: list = None, period_days: int = None) -> Dict:
        """
        Получает статистику посещений пользователей (исключая админов)
        
        Args:
            admin_ids: Список ID админов для исключения
            period_days: Период в днях (None = за всё время)
        
        Returns:
            Dict со статистикой
        """
        try:
            stats = {}
            
            # Базовые условия
            where_clause = ""
            params = []
            
            if admin_ids:
                placeholders = ','.join('?' * len(admin_ids))
                where_clause = f"WHERE user_id NOT IN ({placeholders})"
                params = list(admin_ids)
            
            if period_days:
                if where_clause:
                    where_clause += f" AND visited_at >= datetime('now', '-{period_days} days')"
                else:
                    where_clause = f"WHERE visited_at >= datetime('now', '-{period_days} days')"
            
            # Общее количество посещений
            query = f"SELECT COUNT(*) FROM user_visits {where_clause}"
            self.cursor.execute(query, params)
            stats['total_visits'] = self.cursor.fetchone()[0]
            
            # Уникальные пользователи
            query = f"SELECT COUNT(DISTINCT user_id) FROM user_visits {where_clause}"
            self.cursor.execute(query, params)
            stats['unique_users'] = self.cursor.fetchone()[0]
            
            # Посещения сегодня
            self.cursor.execute(
                f"SELECT COUNT(*) FROM user_visits {where_clause} AND DATE(visited_at) = DATE('now')",
                params
            )
            stats['visits_today'] = self.cursor.fetchone()[0]
            
            # Посещения за неделю
            self.cursor.execute(
                f"SELECT COUNT(*) FROM user_visits {where_clause} AND visited_at >= datetime('now', '-7 days')",
                params
            )
            stats['visits_week'] = self.cursor.fetchone()[0]
            
            # Посещения за месяц
            self.cursor.execute(
                f"SELECT COUNT(*) FROM user_visits {where_clause} AND visited_at >= datetime('now', '-30 days')",
                params
            )
            stats['visits_month'] = self.cursor.fetchone()[0]
            
            # Топ пользователей по посещениям
            query = f"""
                SELECT user_id, COUNT(*) as visit_count
                FROM user_visits {where_clause}
                GROUP BY user_id
                ORDER BY visit_count DESC
                LIMIT 10
            """
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            stats['top_users'] = [{'user_id': row[0], 'visit_count': row[1]} for row in rows]
            
            # Новые пользователи (первое посещение)
            if period_days:
                query = f"""
                    SELECT user_id, MIN(visited_at) as first_visit
                    FROM user_visits {where_clause}
                    GROUP BY user_id
                    ORDER BY first_visit DESC
                    LIMIT 10
                """
                self.cursor.execute(query, params)
                rows = self.cursor.fetchall()
                stats['new_users'] = [{'user_id': row[0], 'first_visit': row[1]} for row in rows]
            else:
                stats['new_users'] = []
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики посещений: {e}")
            return {}

    def get_all_users_stats(self, admin_ids: list = None, limit: int = 50) -> List[Dict]:
        """
        Получает детальную статистику по всем пользователям (исключая админов)
        
        Args:
            admin_ids: Список ID админов для исключения
            limit: Лимит записей
        
        Returns:
            List[Dict] со статистикой пользователей
        """
        try:
            if admin_ids:
                placeholders = ','.join('?' * len(admin_ids))
                self.cursor.execute(f"""
                    SELECT 
                        u.user_id,
                        u.total_searches,
                        u.last_search_at,
                        u.created_at,
                        u.is_subscribed,
                        COUNT(v.id) as total_visits,
                        (SELECT COUNT(*) FROM favorites WHERE user_id = u.user_id) as favorites_count
                    FROM users u
                    LEFT JOIN user_visits v ON u.user_id = v.user_id
                    WHERE u.user_id NOT IN ({placeholders})
                    GROUP BY u.user_id
                    ORDER BY total_visits DESC
                    LIMIT ?
                """, list(admin_ids) + [limit])
            else:
                self.cursor.execute("""
                    SELECT 
                        u.user_id,
                        u.total_searches,
                        u.last_search_at,
                        u.created_at,
                        u.is_subscribed,
                        COUNT(v.id) as total_visits,
                        (SELECT COUNT(*) FROM favorites WHERE user_id = u.user_id) as favorites_count
                    FROM users u
                    LEFT JOIN user_visits v ON u.user_id = v.user_id
                    GROUP BY u.user_id
                    ORDER BY total_visits DESC
                    LIMIT ?
                """, [limit])
            
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователей: {e}")
            return []

    def get_users_activity_stats(self, admin_ids: list = None, period_days: int = 7) -> Dict:
        """
        Получает статистику активности пользователей за период
        
        Args:
            admin_ids: Список ID админов для исключения
            period_days: Период в днях
        
        Returns:
            Dict с активностью по дням
        """
        try:
            where_clause = ""
            params = []
            
            if admin_ids:
                placeholders = ','.join('?' * len(admin_ids))
                where_clause = f"AND user_id NOT IN ({placeholders})"
                params = list(admin_ids)
            
            # Активность по дням
            self.cursor.execute(f"""
                SELECT DATE(visited_at) as date, COUNT(*) as visits, COUNT(DISTINCT user_id) as unique_users
                FROM user_visits
                WHERE visited_at >= datetime('now', '-{period_days} days') {where_clause}
                GROUP BY DATE(visited_at)
                ORDER BY date DESC
            """, params)
            
            rows = self.cursor.fetchall()
            activity_by_day = [{'date': row[0], 'visits': row[1], 'unique_users': row[2]} for row in rows]
            
            return {
                'activity_by_day': activity_by_day,
                'period_days': period_days
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения активности пользователей: {e}")
            return {}

    def close(self):
        """Закрывает соединение с БД"""
        try:
            if self.conn:
                self.conn.close()
                logger.info("✅ Соединение с БД закрыто")
        except Exception as e:
            logger.error(f"Ошибка закрытия БД: {e}")

    # ==================== ACHIEVEMENTS ====================

    def unlock_achievement(self, user_id: int, achievement_type: str) -> bool:
        """Разблокировать достижение пользователю"""
        try:
            self.cursor.execute('''
                INSERT OR IGNORE INTO user_achievements (user_id, achievement_type)
                VALUES (?, ?)
            ''', (user_id, achievement_type))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка разблокировки достижения: {e}")
            return False

    def is_achievement_unlocked(self, user_id: int, achievement_type: str) -> bool:
        """Проверить, разблокировано ли достижение"""
        try:
            self.cursor.execute('''
                SELECT 1 FROM user_achievements
                WHERE user_id = ? AND achievement_type = ?
            ''', (user_id, achievement_type))
            return self.cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Ошибка проверки достижения: {e}")
            return False

    def get_user_achievements(self, user_id: int) -> List[Dict]:
        """Получить все разблокированные достижения пользователя"""
        try:
            self.cursor.execute('''
                SELECT achievement_type, unlocked_at
                FROM user_achievements
                WHERE user_id = ?
                ORDER BY unlocked_at
            ''', (user_id,))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения достижений: {e}")
            return []

    # ==================== REACTIONS ====================

    def add_reaction(self, user_id: int, movie_id: int, movie_code: str, reaction_type: str) -> bool:
        """Добавить реакцию на фильм"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO movie_reactions (user_id, movie_id, movie_code, reaction_type)
                VALUES (?, ?, ?, ?)
            ''', (user_id, movie_id, movie_code, reaction_type))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавлени�� реакции: {e}")
            return False

    def remove_reaction(self, user_id: int, movie_id: int) -> bool:
        """Удалить реакцию пользователя"""
        try:
            self.cursor.execute('''
                DELETE FROM movie_reactions
                WHERE user_id = ? AND movie_id = ?
            ''', (user_id, movie_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления реакции: {e}")
            return False

    def update_reaction(self, user_id: int, movie_id: int, reaction_type: str) -> bool:
        """Обновить реакцию пользователя"""
        try:
            self.cursor.execute('''
                UPDATE movie_reactions
                SET reaction_type = ?
                WHERE user_id = ? AND movie_id = ?
            ''', (reaction_type, user_id, movie_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления реакции: {e}")
            return False

    def get_user_reaction(self, user_id: int, movie_id: int) -> Dict | None:
        """Получить реакцию пользователя на фильм"""
        try:
            self.cursor.execute('''
                SELECT reaction_type, created_at
                FROM movie_reactions
                WHERE user_id = ? AND movie_id = ?
            ''', (user_id, movie_id))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения реакции: {e}")
            return None

    def get_movie_reactions(self, movie_id: int) -> List[Dict]:
        """Получить все реакции на фильм"""
        try:
            self.cursor.execute('''
                SELECT user_id, reaction_type, created_at
                FROM movie_reactions
                WHERE movie_id = ?
            ''', (movie_id,))
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения реакций фильма: {e}")
            return []

    # ==================== NOTIFICATIONS ====================

    def log_notification(self, user_id: int, movie_id: int, notification_type: str) -> bool:
        """Записать отправленное уведомление"""
        try:
            self.cursor.execute('''
                INSERT INTO notifications_log (user_id, movie_id, notification_type)
                VALUES (?, ?, ?)
            ''', (user_id, movie_id, notification_type))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка логирования уведомления: {e}")
            return False

    def get_all_users_with_notifications(self) -> List[Dict]:
        """Получить всех пользователей с включенными уведомлениями"""
        try:
            self.cursor.execute('''
                SELECT u.user_id, u.language
                FROM users u
                LEFT JOIN user_settings us ON u.user_id = us.user_id
                WHERE us.notifications_enabled IS NULL OR us.notifications_enabled = 1
            ''')
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения пользователей с уведомлениями: {e}")
            return []

    def set_user_notifications(self, user_id: int, enabled: bool) -> bool:
        """Включить/выключить уведомления пользователю"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO user_settings (user_id, notifications_enabled)
                VALUES (?, ?)
            ''', (user_id, 1 if enabled else 0))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка настройки уведомлений: {e}")
            return False

    def get_user_notifications_enabled(self, user_id: int) -> bool:
        """Проверить, включены ли уведомления у пользователя"""
        try:
            self.cursor.execute('''
                SELECT notifications_enabled
                FROM user_settings
                WHERE user_id = ?
            ''', (user_id,))
            row = self.cursor.fetchone()
            return row['notifications_enabled'] if row else True
        except Exception as e:
            logger.error(f"Ошибка проверки настроек уведомлений: {e}")
            return True

    # ==================== TRENDS & STATS ====================

    def get_active_users_count(self, minutes: int = 5) -> int:
        """Получить количество активных пользователей за последние N минут"""
        try:
            self.cursor.execute('''
                SELECT COUNT(DISTINCT user_id)
                FROM user_visits
                WHERE visited_at >= datetime('now', ?)
            ''', (f'-{minutes} minutes',))
            return self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return 0

    def get_new_users_count(self, date: datetime) -> int:
        """Получить количество новых пользователей за дату"""
        try:
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM users
                WHERE DATE(created_at) = DATE(?)
            ''', (date.strftime('%Y-%m-%d'),))
            return self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка получения новых пользователей: {e}")
            return 0

    def get_searches_count(self, date: datetime) -> int:
        """Получить количество поисковых запросов за дату"""
        try:
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM search_history
                WHERE DATE(created_at) = DATE(?)
            ''', (date.strftime('%Y-%m-%d'),))
            return self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка получения поисков: {e}")
            return 0

    def get_views_count(self, date: datetime) -> int:
        """Получить количество просмотров за дату"""
        try:
            self.cursor.execute('''
                SELECT COUNT(*)
                FROM view_analytics
                WHERE DATE(viewed_at) = DATE(?)
            ''', (date.strftime('%Y-%m-%d'),))
            return self.cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Ошибка получения просмотров: {e}")
            return 0

    def get_user_info(self, user_id: int) -> Dict | None:
        """Получить полную информацию о пользователе"""
        try:
            self.cursor.execute('''
                SELECT *
                FROM users
                WHERE user_id = ?
            ''', (user_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе: {e}")
            return None

    def get_user_created_at(self, user_id: int) -> datetime | None:
        """Получить дату регистрации пользователя"""
        try:
            self.cursor.execute('''
                SELECT created_at
                FROM users
                WHERE user_id = ?
            ''', (user_id,))
            row = self.cursor.fetchone()
            if row and row['created_at']:
                if isinstance(row['created_at'], str):
                    return datetime.fromisoformat(row['created_at'])
                return row['created_at']
            return None
        except Exception as e:
            logger.error(f"Ошибка получения даты регистрации: {e}")
            return None

    def get_movie_genres(self, movie_id: int) -> List[str]:
        """Получить жанры фильма"""
        try:
            self.cursor.execute('''
                SELECT g.name
                FROM genres g
                JOIN movie_genres mg ON g.id = mg.genre_id
                WHERE mg.movie_id = ?
            ''', (movie_id,))
            return [row['name'] for row in self.cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения жанров: {e}")
            return []

    def get_movie_actors(self, movie_id: int) -> List[str]:
        """Получить актёров фильма"""
        try:
            self.cursor.execute('''
                SELECT a.name
                FROM actors a
                JOIN movie_actors ma ON a.id = ma.actor_id
                WHERE ma.movie_id = ?
            ''', (movie_id,))
            return [row['name'] for row in self.cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения актёров: {e}")
            return []

    def get_movie_directors(self, movie_id: int) -> List[str]:
        """Получить режиссёров фильма"""
        try:
            self.cursor.execute('''
                SELECT d.name
                FROM directors d
                JOIN movie_directors md ON d.id = md.director_id
                WHERE md.movie_id = ?
            ''', (movie_id,))
            return [row['name'] for row in self.cursor.fetchall()]
        except Exception as e:
            logger.error(f"Ошибка получения режиссёров: {e}")
            return []

    def get_max_movie_code(self) -> int:
        """Получить максимальный короткий числовой код фильма в БД (до 999)"""
        try:
            self.cursor.execute('''
                SELECT MAX(CAST(code AS INTEGER)) FROM movies 
                WHERE code GLOB '[0-9]*' AND CAST(code AS INTEGER) < 1000
            ''')
            row = self.cursor.fetchone()
            return row[0] if row and row[0] else 0
        except Exception as e:
            logger.error(f"Ошибка получения максимального кода: {e}")
            return 0

    def admin_ids(self) -> list:
        """Вернуть список ID админов (для сервисов)"""
        from config import Config
        return Config.ADMIN_IDS