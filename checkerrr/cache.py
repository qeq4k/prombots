"""
Модуль кэширования на Redis.
Если Redis недоступен, автоматически переключается на in-memory кэш.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
from functools import wraps

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis as redis
        REDIS_AVAILABLE = True
    except ImportError:
        redis = None
        REDIS_AVAILABLE = False
        logger.warning("⚠️ Redis не установлен. Используем in-memory кэш.")


class MemoryCache:
    """In-memory кэш как fallback если Redis недоступен"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    async def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry:
            if entry['expires_at'] > datetime.now():
                return entry['value']
            else:
                del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any, expire: int = 300):
        self._cache[key] = {
            'value': value,
            'expires_at': datetime.now() + timedelta(seconds=expire)
        }
    
    async def delete(self, key: str):
        self._cache.pop(key, None)
    
    async def clear(self):
        self._cache.clear()
    
    async def close(self):
        pass


class RedisCache:
    """Redis кэш с автоматическим fallback на memory"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, password: str = None):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self._redis: Optional[Any] = None
        self._fallback = MemoryCache()
        self._connected = False
    
    async def connect(self):
        """Подключение к Redis"""
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis библиотека не установлена, используем in-memory кэш")
            return False
        
        try:
            self._redis = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True
            )
            await self._redis.ping()
            self._connected = True
            logger.info(f"✅ Redis подключен: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis недоступен ({e}), используем in-memory кэш")
            self._connected = False
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        if not self._connected:
            return await self._fallback.get(key)

        try:
            value = await self._redis.get(f"bot:{key}")
            if value:
                logger.debug(f"📦 Cache HIT: {key}")
                # Пытаемся десериализовать JSON
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value
            logger.debug(f"📦 Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения из Redis: {e}")
            return await self._fallback.get(key)
    
    async def set(self, key: str, value: Any, expire: int = 300):
        if not self._connected:
            await self._fallback.set(key, value, expire)
            return

        try:
            # Сериализуем значение в JSON
            value_serialized = json.dumps(value, ensure_ascii=False)
            await self._redis.setex(f"bot:{key}", expire, value_serialized)
            logger.debug(f"💾 Cache SET: {key} (expire={expire}s)")
        except Exception as e:
            logger.error(f"❌ Ошибка записи в Redis: {e}")
            await self._fallback.set(key, value, expire)
    
    async def delete(self, key: str):
        if not self._connected:
            await self._fallback.delete(key)
            return
        
        try:
            await self._redis.delete(f"bot:{key}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления из Redis: {e}")
            await self._fallback.delete(key)
    
    async def clear_pattern(self, pattern: str):
        """Очистка ключей по паттерну"""
        if not self._connected:
            await self._fallback.clear()
            return
        
        try:
            keys = await self._redis.keys(f"bot:{pattern}")
            if keys:
                await self._redis.delete(*keys)
                logger.info(f"🧹 Очищено {len(keys)} ключей по паттерну {pattern}")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки паттерна: {e}")
    
    async def close(self):
        if self._redis and self._connected:
            await self._redis.close()
            logger.info("✅ Redis отключен")
        await self._fallback.close()
    
    @property
    def is_connected(self) -> bool:
        return self._connected


# Глобальный экземпляр кэша
cache: Optional[RedisCache] = None


def init_cache(host: str = 'localhost', port: int = 6379, password: str = None) -> RedisCache:
    """Инициализация кэша"""
    global cache
    cache = RedisCache(host=host, port=port, password=password)
    return cache


def get_cache() -> RedisCache:
    """Получение экземпляра кэша"""
    global cache
    if cache is None:
        cache = RedisCache()
    return cache


# === Кэш-декораторы ===

def cached(expire: int = 300, key_prefix: str = ""):
    """
    Декоратор для кэширования результатов асинхронных функций.
    
    Args:
        expire: Время жизни кэша в секундах
        key_prefix: Префикс для ключа кэша
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_instance = get_cache()
            
            # Генерируем ключ из аргументов
            key_parts = [key_prefix, func.__name__]
            for arg in args:
                key_parts.append(str(arg))
            for k, v in sorted(kwargs.items()):
                key_parts.append(f"{k}={v}")
            
            cache_key = ":".join(key_parts)
            
            # Проверяем кэш
            cached_result = await cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Вызываем функцию
            result = await func(*args, **kwargs)
            
            # Сохраняем в кэш
            await cache_instance.set(cache_key, result, expire)
            
            return result
        return wrapper
    return decorator


# === Специализированные кэш-функции ===

class SearchCache:
    """Кэш для поисковых запросов"""
    
    @staticmethod
    async def get_search_results(query: str, query_type: str) -> Optional[List[Dict]]:
        cache_instance = get_cache()
        key = f"search:{query_type}:{query.lower()}"
        result = await cache_instance.get(key)
        return result
    
    @staticmethod
    async def set_search_results(query: str, query_type: str, results: List[Dict], expire: int = 600):
        cache_instance = get_cache()
        key = f"search:{query_type}:{query.lower()}"
        await cache_instance.set(key, results, expire)
    
    @staticmethod
    async def clear_search():
        cache_instance = get_cache()
        await cache_instance.clear_pattern("search:*")


class SubscriptionCache:
    """Кэш для проверки подписок"""
    
    @staticmethod
    async def get(user_id: int) -> Optional[Dict]:
        cache_instance = get_cache()
        key = f"subscription:{user_id}"
        return await cache_instance.get(key)
    
    @staticmethod
    async def set(user_id: int, is_subscribed: bool, failed_channels: List[str] = None, expire: int = 60):
        cache_instance = get_cache()
        key = f"subscription:{user_id}"
        value = {
            'is_subscribed': is_subscribed,
            'failed_channels': failed_channels or [],
            'checked_at': datetime.now().isoformat()
        }
        await cache_instance.set(key, value, expire)
    
    @staticmethod
    async def invalidate(user_id: int):
        cache_instance = get_cache()
        await cache_instance.delete(f"subscription:{user_id}")


class MovieCache:
    """Кэш для фильмов"""
    
    @staticmethod
    async def get_by_code(code: str) -> Optional[Dict]:
        cache_instance = get_cache()
        return await cache_instance.get(f"movie:code:{code}")
    
    @staticmethod
    async def set_by_code(code: str, movie: Dict, expire: int = 3600):
        cache_instance = get_cache()
        await cache_instance.set(f"movie:code:{code}", movie, expire)
    
    @staticmethod
    async def invalidate_all():
        cache_instance = get_cache()
        await cache_instance.clear_pattern("movie:*")
