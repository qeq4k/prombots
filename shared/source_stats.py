#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Source Stats — Статистика по источникам новостей

Использование:
    from shared import SourceStats
    
    stats = SourceStats(db_path)
    report = await stats.get_report(days=7)
    print(report)
"""
import aiosqlite
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class SourceStats:
    """Статистика по источникам новостей"""
    
    def __init__(self, db_path: str):
        """
        Args:
            db_path: Путь к базе данных бота
        """
        self.db_path = db_path
    
    async def get_report(self, days: int = 7) -> Dict[str, Any]:
        """
        Получение отчёта за период

        Args:
            days: Количество дней

        Returns:
            Отчёт со статистикой
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_ts = cutoff.timestamp()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                # 1. Постов по источникам (без priority - нет в схеме БД)
                async with db.execute("""
                    SELECT source, COUNT(*) as count
                    FROM posted
                    WHERE posted_at > datetime(?, 'unixepoch')
                    GROUP BY source
                    ORDER BY count DESC
                """, (cutoff_ts,)) as cursor:
                    sources = await cursor.fetchall()

                # 2. Всего постов
                total = sum(row[1] for row in sources)

                # 3. Топ источников
                top_sources = [
                    {
                        "source": row[0],
                        "count": row[1],
                        "percent": round(row[1] / total * 100, 1) if total else 0,
                    }
                    for row in sources[:10]
                ]

                return {
                    "period_days": days,
                    "total_posts": total,
                    "total_sources": len(sources),
                    "top_sources": top_sources,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return {
                "error": str(e),
                "period_days": days,
                "total_posts": 0
            }
    
    async def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Статистика по дням
        
        Args:
            days: Количество дней
        
        Returns:
            Список статистики по дням
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute("""
                    SELECT date(posted_at) as date, COUNT(*) as count
                    FROM posted
                    WHERE posted_at > datetime('now', ? days)
                    GROUP BY date(posted_at)
                    ORDER BY date DESC
                """, (-days,)) as cursor:
                    rows = await cursor.fetchall()
                
                return [
                    {"date": row[0], "count": row[1]}
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return []
    
    def format_report(self, report: Dict[str, Any]) -> str:
        """
        Форматирование отчёта в текст

        Args:
            report: Отчёт из get_report

        Returns:
            Красивый текст
        """
        if "error" in report:
            return f"❌ Ошибка: {report['error']}"

        text = f"📊 <b>Статистика за {report['period_days']} дн.</b>\n\n"
        text += f"📝 Постов: <b>{report['total_posts']}</b>\n"
        text += f"📡 Источников: <b>{report['total_sources']}</b>\n\n"

        text += f"<b>🏆 Топ источников:</b>\n"
        for i, src in enumerate(report['top_sources'][:5], 1):
            emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1] if i <= 5 else f"{i}."
            text += f"{emoji} <b>{src['source']}</b>\n"
            text += f"   📝 {src['count']} постов ({src['percent']}%)\n"

        return text


__all__ = ['SourceStats']
