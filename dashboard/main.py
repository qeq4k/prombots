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
import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

import requests
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
    def _parse_prometheus_metrics(url: str) -> Dict[str, Any]:
        """Парсинг метрик из Prometheus endpoints"""
        metrics = {
            "posts_sent": 0,
            "duplicates": 0,
            "llm_calls": 0,
            "llm_cache_hits": 0,
            "llm_errors": 0,
            "fake_dates": 0,
            "english_blocked": 0,
        }

        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return metrics

            for line in resp.text.split('\n'):
                # Пропускаем комментарии, пустые строки и _created метрики
                if line.startswith('#') or not line.strip() or '_created' in line:
                    continue

                parts = line.split('{')
                if len(parts) < 2:
                    continue

                metric_name = parts[0]

                # bot_posts_sent_total
                if 'bot_posts_sent_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["posts_sent"] += int(float(match.group(1)))

                # bot_duplicates_total
                elif 'bot_duplicates_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["duplicates"] += int(float(match.group(1)))

                # bot_llm_calls_total
                elif 'bot_llm_calls_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["llm_calls"] += int(float(match.group(1)))

                # bot_llm_cache_hits_total
                elif 'bot_llm_cache_hits_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["llm_cache_hits"] += int(float(match.group(1)))

                # bot_llm_errors_total
                elif 'bot_llm_errors_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["llm_errors"] += int(float(match.group(1)))

                # bot_fake_dates_total
                elif 'bot_fake_dates_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["fake_dates"] += int(float(match.group(1)))

                # bot_english_blocked_total
                elif 'bot_english_blocked_total' in metric_name:
                    match = re.search(r'\{[^}]*\}\s+([\d.]+)', line)
                    if match:
                        metrics["english_blocked"] += int(float(match.group(1)))

        except Exception as e:
            logger.debug(f"⚠️ Ошибка чтения метрик {url}: {e}")

        return metrics

    @staticmethod
    def get_stats_from_prometheus() -> Dict[str, Any]:
        """Получение статистики из Prometheus endpoints ботов"""
        stats = {
            "posts_today": 0,
            "posts_week": 0,
            "duplicates_blocked": 0,
            "llm_calls": 0,
            "llm_cache_hits": 0,
            "llm_errors": 0,
        }

        # Prometheus endpoints для каждого бота
        prometheus_urls = [
            ("politics", "http://localhost:8000/metrics"),
            ("economy", "http://localhost:8001/metrics"),
            ("cinema", "http://localhost:8002/metrics"),
            ("bot_handler", "http://localhost:8003/metrics"),
            ("urgent", "http://localhost:8005/metrics"),
            ("crosspost", "http://localhost:8006/metrics"),
        ]

        for bot_name, url in prometheus_urls:
            try:
                metrics = DashboardData._parse_prometheus_metrics(url)
                stats["duplicates_blocked"] += metrics["duplicates"]
                stats["llm_calls"] += metrics["llm_calls"]
                stats["llm_cache_hits"] += metrics["llm_cache_hits"]
                stats["llm_errors"] += metrics["llm_errors"]
            except Exception as e:
                logger.debug(f"⚠️ Ошибка чтения метрик {bot_name}: {e}")

        # ✅ posts_today и posts_week берём из БД (Prometheus хранит кумулятивные данные)
        db_stats = DashboardData._get_posts_from_db()
        stats["posts_today"] = db_stats["today"]
        stats["posts_week"] = db_stats["week"]
        # ✅ Добавляем детализацию по каналам
        stats["today_politics"] = db_stats["today_politics"]
        stats["today_economy"] = db_stats["today_economy"]
        stats["today_cinema"] = db_stats["today_cinema"]
        stats["week_politics"] = db_stats["week_politics"]
        stats["week_economy"] = db_stats["week_economy"]
        stats["week_cinema"] = db_stats["week_cinema"]

        return stats

    @staticmethod
    def _get_posts_from_db() -> Dict[str, int]:
        """Получение количества постов из БД за сегодня и неделю по каналам"""
        result = {
            "today": 0,
            "week": 0,
            "today_politics": 0,
            "today_economy": 0,
            "today_cinema": 0,
            "week_politics": 0,
            "week_economy": 0,
            "week_cinema": 0,
        }

        db_configs = [
            ("politics", "politics/polit_memory.db"),
            ("economy", "economy/eco_memory.db"),
            ("cinema", "cinema/cinema_memory.db"),
        ]

        for channel, db_path in db_configs:
            try:
                full_path = Path("/root/projectss") / db_path
                if full_path.exists():
                    conn = sqlite3.connect(str(full_path))
                    cursor = conn.cursor()

                    # Посты за сегодня
                    cursor.execute(
                        "SELECT COUNT(*) FROM posted WHERE date(posted_at) = date('now')",
                    )
                    today_count = cursor.fetchone()[0]
                    result[f"today_{channel}"] = today_count
                    result["today"] += today_count

                    # Посты за неделю
                    cursor.execute(
                        "SELECT COUNT(*) FROM posted WHERE posted_at >= datetime('now', '-7 days')",
                    )
                    week_count = cursor.fetchone()[0]
                    result[f"week_{channel}"] = week_count
                    result["week"] += week_count

                    conn.close()
            except Exception as e:
                logger.debug(f"⚠️ Ошибка чтения БД {db_path}: {e}")

        return result
    
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
                        SELECT title_normalized as title, source, posted_at
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
                            "priority": 0,
                        })

                    conn.close()
            except Exception as e:
                logger.debug(f"⚠️ Ошибка чтения БД {bot_name}: {e}")

        # Сортируем по времени
        posts.sort(key=lambda x: x["posted_at"], reverse=True)
        return posts[:limit]
    
    @staticmethod
    def get_recent_posts_by_channel(channel: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Получение последних постов по конкретному каналу"""
        posts = []

        channel_db_map = {
            "politics": ("politics/polit_memory.db", "posted"),
            "economy": ("economy/eco_memory.db", "posted"),
            "cinema": ("cinema/cinema_memory.db", "posted"),
        }

        db_path, table_name = channel_db_map.get(channel, ("politics/polit_memory.db", "posted"))

        try:
            full_path = Path("/root/projectss") / db_path
            if full_path.exists():
                conn = sqlite3.connect(str(full_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    f"""
                    SELECT title_normalized as title, source, posted_at
                    FROM {table_name}
                    WHERE posted_at >= datetime('now', '-7 days')
                    ORDER BY posted_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                )

                for row in cursor.fetchall():
                    posts.append({
                        "title": row["title"][:80] if row["title"] else "Без названия",
                        "source": row["source"],
                        "posted_at": row["posted_at"],
                        "priority": 0,
                    })

                conn.close()
        except Exception as e:
            logger.debug(f"⚠️ Ошибка чтения БД {channel}: {e}")

        return posts
    
    @staticmethod
    def get_checkerrr_stats() -> Dict[str, Any]:
        """Получение статистики из checkerrr (кинобот)"""
        stats = {
            "movies": 0,
            "users": 0,
            "searches_week": 0,
            "favorites": 0,
            "new_users_week": 0,
            "new_users_month": 0,
        }

        try:
            db_path = Path("/root/projectss/checkerrr/movies.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                # Фильмы
                cursor.execute("SELECT COUNT(*) FROM movies")
                stats["movies"] = cursor.fetchone()[0]

                # Пользователи
                cursor.execute("SELECT COUNT(*) FROM users")
                stats["users"] = cursor.fetchone()[0]

                # Поисковые запросы за неделю
                cursor.execute("""
                    SELECT COUNT(*) FROM search_history
                    WHERE created_at > datetime('now', '-7 days')
                """)
                stats["searches_week"] = cursor.fetchone()[0]

                # Избранное
                cursor.execute("SELECT COUNT(*) FROM favorites")
                stats["favorites"] = cursor.fetchone()[0]
                
                # Новые пользователи за неделю
                cursor.execute("""
                    SELECT COUNT(*) FROM users
                    WHERE subscribed_at > datetime('now', '-7 days')
                """)
                stats["new_users_week"] = cursor.fetchone()[0]
                
                # Новые пользователи за месяц
                cursor.execute("""
                    SELECT COUNT(*) FROM users
                    WHERE subscribed_at > datetime('now', '-30 days')
                """)
                stats["new_users_month"] = cursor.fetchone()[0]

                conn.close()
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения статистики checkerrr: {e}")

        return stats
    
    @staticmethod
    def get_other_bots_stats() -> Dict[str, Any]:
        """Получение статистики с других ботов (politika, economika, movie)"""
        stats = {
            "politika_posts_week": 0,
            "economika_posts_week": 0,
            "movie_posts_week": 0,
        }
        
        try:
            # Politika
            db_path = Path("/root/projectss/politics/polit_memory.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM posted 
                    WHERE posted_at > datetime('now', '-7 days')
                """)
                stats["politika_posts_week"] = cursor.fetchone()[0] or 0
                conn.close()
            
            # Economy
            db_path = Path("/root/projectss/economy/eco_memory.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM posted 
                    WHERE posted_at > datetime('now', '-7 days')
                """)
                stats["economika_posts_week"] = cursor.fetchone()[0] or 0
                conn.close()
            
            # Cinema
            db_path = Path("/root/projectss/cinema/cinema_memory.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM posted 
                    WHERE posted_at > datetime('now', '-7 days')
                """)
                stats["movie_posts_week"] = cursor.fetchone()[0] or 0
                conn.close()
                
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения статистики других ботов: {e}")
        
        return stats

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
    # ✅ ИСПОЛЬЗУЕМ PROMETHEUS METRICS ВМЕСТО БД
    stats = DashboardData.get_stats_from_prometheus()
    system = DashboardData.get_system_info()

    # Получаем статистику по источникам
    source_stats = {}
    for bot_name, db_path in [("politics", "politics/polit_memory.db"), 
                               ("economy", "economy/eco_memory.db"),
                               ("cinema", "cinema/cinema_memory.db")]:
        try:
            full_path = Path("/root/projectss") / db_path
            if full_path.exists():
                from shared import SourceStats
                src_stats = SourceStats(str(full_path))
                source_stats[bot_name] = await src_stats.get_report(days=7)
        except Exception as e:
            logger.debug(f"⚠️ Ошибка получения статистики {bot_name}: {e}")

    # Получаем последние посты по каждому каналу
    recent_by_channel = {
        "politics": DashboardData.get_recent_posts_by_channel("politics", 5),
        "economy": DashboardData.get_recent_posts_by_channel("economy", 5),
        "cinema": DashboardData.get_recent_posts_by_channel("cinema", 5),
    }

    # Получаем статистику из checkerrr
    checkerrr_stats = DashboardData.get_checkerrr_stats()
    
    # Получаем статистику с других ботов (politika, economika, movie)
    other_bots_stats = DashboardData.get_other_bots_stats()

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
            "recent_by_channel": recent_by_channel,
            "system": system,
            "ram_percent": ram_percent,
            "source_stats": source_stats,
            "checkerrr_stats": checkerrr_stats,
            "other_bots_stats": other_bots_stats,
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
    return JSONResponse(content=DashboardData.get_stats_from_prometheus())


@app.get("/api/recent")
async def api_recent(limit: int = 10):
    """API: Последние посты"""
    return JSONResponse(content={"posts": DashboardData.get_recent_posts(limit)})


@app.post("/api/checkerrr_stats")
async def api_checkerrr_stats(stats: dict):
    """API: Получение статистики от checkerrr"""
    # Сохраняем в глобальную переменную или кэш
    # Для простоты просто логируем
    logger.info(f"📊 Checkerrr stats: {stats}")
    return JSONResponse(content={"status": "ok"})


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
