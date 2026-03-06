#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📊 Admin Dashboard — Веб-дашборд для администратора

Запуск:
    python3 dashboard/main.py

Или через PM2:
    pm2 start dashboard/main.py --name dashboard --interpreter python3
"""
import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bot Admin Dashboard", version="1.0.0")

# Пути
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ================= ДАННЫЕ ДЛЯ ДАШБОРДА =================

class DashboardData:
    """Сбор данных для дашборда"""
    
    @staticmethod
    def get_bot_status() -> List[Dict[str, Any]]:
        """Получение статуса ботов из PM2"""
        bots = [
            {"name": "politics", "display": "🏛️ Политика", "channel": "@I_Politika"},
            {"name": "economy", "display": "💰 Экономика", "channel": "@eco_steroid"},
            {"name": "cinema", "display": "🎬 Кино", "channel": "@Film_orbita"},
            {"name": "urgent", "display": "🚨 Срочные", "channel": "мульти-канал"},
            {"name": "bot_handler", "display": "🤖 Handler", "channel": "общий"},
            {"name": "bot_new", "display": "🎬 Checker", "channel": "бот"},
            {"name": "crosspost", "display": "🔄 Crosspost", "channel": "сервис"},
        ]
        
        # Пытаемся получить статус из PM2
        try:
            import subprocess
            result = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                pm2_data = json.loads(result.stdout)
                pm2_status = {bot["name"]: bot for bot in pm2_data}
                
                for bot in bots:
                    pm2_bot = pm2_status.get(bot["name"], {})
                    bot["status"] = pm2_bot.get("pm2_env", {}).get("status", "unknown")
                    bot["memory"] = pm2_bot.get("pm2_env", {}).get("monit", {}).get("memory", 0)
                    bot["cpu"] = pm2_bot.get("pm2_env", {}).get("monit", {}).get("cpu", 0)
                    bot["uptime"] = pm2_bot.get("pm2_env", {}).get("pm_uptime", 0)
                    bot["restarts"] = pm2_bot.get("pm2_env", {}).get("restart_time", 0)
            else:
                for bot in bots:
                    bot["status"] = "unknown"
                    bot["memory"] = 0
                    bot["cpu"] = 0
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить PM2 статус: {e}")
            for bot in bots:
                bot["status"] = "unknown"
        
        return bots
    
    @staticmethod
    def get_stats_from_db() -> Dict[str, Any]:
        """Получение статистики из баз данных ботов"""
        stats = {
            "posts_today": 0,
            "posts_week": 0,
            "duplicates_blocked": 0,
            "llm_calls": 0,
        }

        # Пытаемся получить данные из БД каждого бота
        db_paths = [
            ("politics", "politics/polit_memory.db"),
            ("economy", "economy/eco_memory.db"),
            ("cinema", "cinema/cinema_memory.db"),
        ]

        import sqlite3

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = today.timestamp()
        week_ago = today - timedelta(days=7)
        week_ago_ts = week_ago.timestamp()

        for bot_name, db_path in db_paths:
            try:
                full_path = Path("/root/projectss") / db_path
                if full_path.exists():
                    conn = sqlite3.connect(full_path)
                    cursor = conn.cursor()

                    # Посты за сегодня (таблица posted)
                    cursor.execute(
                        "SELECT COUNT(*) FROM posted WHERE posted_at > datetime(?, 'unixepoch')",
                        (today_ts,)
                    )
                    count = cursor.fetchone()[0]
                    stats["posts_today"] += count

                    # Посты за неделю
                    cursor.execute(
                        "SELECT COUNT(*) FROM posted WHERE posted_at > datetime(?, 'unixepoch')",
                        (week_ago_ts,)
                    )
                    count = cursor.fetchone()[0]
                    stats["posts_week"] += count
                    
                    conn.close()
            except Exception as e:
                logger.debug(f"⚠️ Ошибка чтения БД {bot_name}: {e}")
        
        return stats
    
    @staticmethod
    def get_recent_posts(limit: int = 10) -> List[Dict[str, Any]]:
        """Получение последних постов"""
        posts = []

        import sqlite3

        db_paths = [
            ("politics", "politics/polit_memory.db"),
            ("economy", "economy/eco_memory.db"),
            ("cinema", "cinema/cinema_memory.db"),
        ]

        for bot_name, db_path in db_paths:
            try:
                full_path = Path("/root/projectss") / db_path
                if full_path.exists():
                    conn = sqlite3.connect(full_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    cursor.execute(
                        """
                        SELECT title_normalized as title, source, posted_at, 0 as priority
                        FROM posted
                        WHERE posted_at > datetime('now', '-30 days')
                        ORDER BY posted_at DESC
                        LIMIT ?
                        """,
                        (limit,)
                    )

                    for row in cursor.fetchall():
                        posts.append({
                            "bot": bot_name,
                            "title": row["title"][:100] if row["title"] else "Без названия",
                            "source": row["source"],
                            "posted_at": row["posted_at"],
                            "priority": row["priority"],
                        })

                    conn.close()
            except Exception as e:
                logger.debug(f"⚠️ Ошибка чтения БД {bot_name}: {e}")

        # Сортируем по времени
        posts.sort(key=lambda x: x["posted_at"], reverse=True)
        return posts[:limit]
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Информация о системе"""
        import subprocess
        
        info = {
            "ram_total": 0,
            "ram_used": 0,
            "disk_total": 0,
            "disk_used": 0,
        }
        
        try:
            # RAM
            result = subprocess.run(
                ["free", "-m"],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                info["ram_total"] = int(parts[1])
                info["ram_used"] = int(parts[2])
            
            # Disk
            result = subprocess.run(
                ["df", "-h", "/root"],
                capture_output=True,
                text=True,
                timeout=5
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                info["disk_total"] = parts[1]
                info["disk_used"] = parts[2]
                info["disk_percent"] = parts[4]
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить системную информацию: {e}")
        
        return info


# ================= API ENDPOINTS =================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Главная страница дашборда"""
    bots = DashboardData.get_bot_status()
    stats = DashboardData.get_stats_from_db()
    recent_posts = DashboardData.get_recent_posts(10)
    system = DashboardData.get_system_info()
    
    # Форматируем память ботов
    for bot in bots:
        if bot.get("memory"):
            bot["memory_mb"] = round(bot["memory"] / (1024 * 1024), 1)
        else:
            bot["memory_mb"] = 0
    
    # Форматируем RAM
    ram_percent = round((system["ram_used"] / system["ram_total"] * 100), 1) if system["ram_total"] else 0
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "bots": bots,
            "stats": stats,
            "recent_posts": recent_posts,
            "system": system,
            "ram_percent": ram_percent,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@app.get("/api/status")
async def api_status():
    """API: Статус ботов"""
    return JSONResponse(content={"bots": DashboardData.get_bot_status()})


@app.get("/api/stats")
async def api_stats():
    """API: Статистика"""
    return JSONResponse(content=DashboardData.get_stats_from_db())


@app.get("/api/recent")
async def api_recent(limit: int = 10):
    """API: Последние посты"""
    return JSONResponse(content={"posts": DashboardData.get_recent_posts(limit)})


@app.get("/api/health")
async def api_health():
    """API: Проверка здоровья"""
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ================= MAIN =================

def main():
    """Запуск сервера"""
    logger.info("=" * 60)
    logger.info("📊 Admin Dashboard 2026")
    logger.info("=" * 60)
    logger.info("🌐 Запуск на http://0.0.0.0:8080")
    logger.info("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )


if __name__ == "__main__":
    main()
