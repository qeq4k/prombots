"""
Сервис достижений
"""
import logging
from datetime import datetime, timedelta
from typing import List

from database import Database
from constants import AchievementType, ACHIEVEMENTS

logger = logging.getLogger(__name__)


class AchievementService:
    """Сервис для управления достижениями пользователей"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def check_and_unlock(
        self, 
        user_id: int,
        achievement_type: AchievementType
    ) -> bool:
        """
        Проверить и разблокировать достижение
        
        Returns:
            True если достижение было разблокировано
        """
        # Проверяем, не разблокировано ли уже
        if self.db.is_achievement_unlocked(user_id, achievement_type.value):
            return False
        
        # Проверяем условия
        unlocked = False
        
        if achievement_type == AchievementType.FIRST_SEARCH:
            unlocked = await self._check_first_search(user_id)
        elif achievement_type == AchievementType.SEARCH_10:
            unlocked = await self._check_search_count(user_id, 10)
        elif achievement_type == AchievementType.SEARCH_50:
            unlocked = await self._check_search_count(user_id, 50)
        elif achievement_type == AchievementType.SEARCH_100:
            unlocked = await self._check_search_count(user_id, 100)
        elif achievement_type == AchievementType.FAVORITE_1:
            unlocked = await self._check_first_favorite(user_id)
        elif achievement_type == AchievementType.FAVORITE_10:
            unlocked = await self._check_favorite_count(user_id, 10)
        elif achievement_type == AchievementType.FAVORITE_50:
            unlocked = await self._check_favorite_count(user_id, 50)
        elif achievement_type == AchievementType.DAYS_7:
            unlocked = await self._check_days_active(user_id, 7)
        elif achievement_type == AchievementType.DAYS_30:
            unlocked = await self._check_days_active(user_id, 30)
        elif achievement_type == AchievementType.DAYS_365:
            unlocked = await self._check_days_active(user_id, 365)
        
        if unlocked:
            self.db.unlock_achievement(user_id, achievement_type.value)
            logger.info(f"Пользователь {user_id} разблокировал достижение: {achievement_type.value}")
            return True
        
        return False
    
    async def _check_first_search(self, user_id: int) -> bool:
        """Проверка: первый поиск выполнен"""
        stats = self.db.get_user_stats(user_id)
        return stats.get('total_searches', 0) >= 1
    
    async def _check_search_count(self, user_id: int, count: int) -> bool:
        """Проверка: количество поисков"""
        stats = self.db.get_user_stats(user_id)
        return stats.get('total_searches', 0) >= count
    
    async def _check_first_favorite(self, user_id: int) -> bool:
        """Проверка: первый фильм в избранном"""
        favorites = self.db.get_user_favorites(user_id)
        return len(favorites) >= 1
    
    async def _check_favorite_count(self, user_id: int, count: int) -> bool:
        """Проверка: количество фильмов в избранном"""
        favorites = self.db.get_user_favorites(user_id)
        return len(favorites) >= count
    
    async def _check_days_active(self, user_id: int, days: int) -> bool:
        """Проверка: количество дней с первой активности"""
        created_at = self.db.get_user_created_at(user_id)
        if not created_at:
            return False
        
        delta = datetime.now() - created_at
        return delta.days >= days
    
    def get_user_achievements(self, user_id: int) -> List[dict]:
        """Получить все достижения пользователя"""
        unlocked = self.db.get_user_achievements(user_id)
        unlocked_types = {a['achievement_type'] for a in unlocked}
        
        result = []
        for ach_type, ach_data in ACHIEVEMENTS.items():
            is_unlocked = ach_type.value in unlocked_types
            unlocked_at = None
            
            if is_unlocked:
                for u in unlocked:
                    if u['achievement_type'] == ach_type.value:
                        unlocked_at = u.get('unlocked_at')
                        break
            
            result.append({
                'type': ach_type.value,
                'name_ru': ach_data['name_ru'],
                'name_en': ach_data['name_en'],
                'description_ru': ach_data['description_ru'],
                'description_en': ach_data['description_en'],
                'icon': ach_data['icon'],
                'is_unlocked': is_unlocked,
                'unlocked_at': unlocked_at
            })
        
        return result
    
    def get_all_achievements_info(self, lang: str = "ru") -> str:
        """Получить информацию обо всех достижениях"""
        text = "🏆 **Все достижения**\n\n"
        
        for ach_type, ach_data in ACHIEVEMENTS.items():
            icon = ach_data['icon']
            name = ach_data['name_ru'] if lang == "ru" else ach_data['name_en']
            desc = ach_data['description_ru'] if lang == "ru" else ach_data['description_en']
            
            text += f"{icon} **{name}**\n{desc}\n\n"
        
        return text
