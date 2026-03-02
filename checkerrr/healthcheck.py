"""
Health-check модуль для мониторинга состояния бота.
"""
import logging
import sqlite3
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HealthChecker:
    """Проверка здоровья компонентов бота"""
    
    def __init__(self, db_path: str, bot_token: Optional[str] = None):
        self.db_path = db_path
        self.bot_token = bot_token
        self._last_check: Optional[datetime] = None
        self._health_status: Dict[str, Any] = {}
    
    async def check_all(self) -> Dict[str, Any]:
        """Проверка всех компонентов"""
        self._last_check = datetime.now()
        self._health_status = {
            'timestamp': self._last_check.isoformat(),
            'status': 'healthy',
            'components': {}
        }
        
        # Проверка БД
        db_status = self.check_database()
        self._health_status['components']['database'] = db_status
        
        # Проверка токена бота
        bot_status = self.check_bot_token()
        self._health_status['components']['bot_token'] = bot_status
        
        # Проверка файлов
        files_status = self.check_files()
        self._health_status['components']['files'] = files_status
        
        # Проверка памяти (примерная)
        memory_status = self.check_memory()
        self._health_status['components']['memory'] = memory_status
        
        # Определяем общий статус
        all_healthy = all(
            comp.get('status') == 'healthy' 
            for comp in self._health_status['components'].values()
        )
        self._health_status['status'] = 'healthy' if all_healthy else 'degraded'
        
        return self._health_status
    
    def check_database(self) -> Dict[str, Any]:
        """Проверка состояния БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Проверка подключения
            cursor.execute("SELECT 1")
            
            # Проверка основных таблиц
            tables = ['movies', 'users', 'channels']
            missing_tables = []
            
            for table in tables:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
                    (table,)
                )
                if not cursor.fetchone():
                    missing_tables.append(table)
            
            # Статистика
            cursor.execute("SELECT COUNT(*) FROM movies")
            movies_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users")
            users_count = cursor.fetchone()[0]
            
            conn.close()
            
            if missing_tables:
                return {
                    'status': 'unhealthy',
                    'message': f'Отсутствуют таблицы: {missing_tables}',
                    'movies_count': movies_count,
                    'users_count': users_count
                }
            
            return {
                'status': 'healthy',
                'message': 'БД в порядке',
                'movies_count': movies_count,
                'users_count': users_count,
                'path': self.db_path
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки БД: {e}")
            return {
                'status': 'unhealthy',
                'message': str(e)
            }
    
    def check_bot_token(self) -> Dict[str, Any]:
        """Проверка токена бота"""
        if not self.bot_token:
            return {
                'status': 'unhealthy',
                'message': 'BOT_TOKEN не установлен'
            }
        
        if not self.bot_token.startswith(('AIza', 'bot', 'http')):
            # Простая эвристика для токена Telegram
            if ':' in self.bot_token and len(self.bot_token) > 40:
                return {
                    'status': 'healthy',
                    'message': 'Токен валиден'
                }
        
        return {
            'status': 'healthy',
            'message': 'Токен установлен'
        }
    
    def check_files(self) -> Dict[str, Any]:
        """Проверка необходимых файлов"""
        import os
        
        required_files = [
            ('config.py', 'Файл конфигурации'),
            ('bot.py', 'Основной файл бота'),
            ('database.py', 'Модуль БД'),
        ]
        
        missing = []
        existing = []
        
        for filename, description in required_files:
            if os.path.exists(filename):
                existing.append(filename)
            else:
                missing.append(filename)
        
        if missing:
            return {
                'status': 'degraded',
                'message': f'Отсутствуют файлы: {missing}',
                'existing': existing
            }
        
        return {
            'status': 'healthy',
            'message': 'Все файлы на месте',
            'files': existing
        }
    
    def check_memory(self) -> Dict[str, Any]:
        """Проверка использования памяти"""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = usage.ru_maxrss / 1024  # Конвертация в MB (на Linux)
            
            return {
                'status': 'healthy' if memory_mb < 500 else 'warning',
                'message': f'Использование памяти: {memory_mb:.1f} MB',
                'memory_mb': round(memory_mb, 1)
            }
        except Exception:
            return {
                'status': 'unknown',
                'message': 'Не удалось получить статистику памяти'
            }
    
    def get_status_text(self) -> str:
        """Возвращает текстовое представление статуса"""
        if not self._health_status:
            return "❓ Статус ещё не проверялся"
        
        status = self._health_status
        lines = [
            f"🔍 **Health Check** ({status['timestamp']})",
            f"Общий статус: **{status['status']}**",
            ""
        ]
        
        for component, data in status['components'].items():
            icon = "✅" if data['status'] == 'healthy' else "⚠️" if data['status'] == 'degraded' else "❌"
            lines.append(f"{icon} **{component}**: {data.get('message', 'N/A')}")
            
            # Добавляем дополнительную информацию
            if component == 'database':
                if 'movies_count' in data:
                    lines.append(f"   📊 Фильмов: {data['movies_count']}")
                if 'users_count' in data:
                    lines.append(f"   👥 Пользователей: {data['users_count']}")
        
        return "\n".join(lines)


# Глобальный экземпляр
health_checker: Optional[HealthChecker] = None


def init_health_checker(db_path: str, bot_token: str = None) -> HealthChecker:
    """Инициализация health checker"""
    global health_checker
    health_checker = HealthChecker(db_path, bot_token)
    return health_checker


def get_health_checker() -> Optional[HealthChecker]:
    """Получение экземпляра health checker"""
    return health_checker
