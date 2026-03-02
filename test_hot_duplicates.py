#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧪 ТЕСТЫ ДЛЯ ПРОВЕРКИ HOT-ДУБЛИКАТОВ

Проверяет что одинаковые HOT-новости не проходят как дубликаты.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем projectss в path
sys.path.insert(0, str(Path(__file__).parent))

from global_dedup import (
    get_content_dedup_hash,
    normalize_text_for_dedup,
    texts_are_similar,
    are_duplicates_by_entities,
    is_similar_recent_news_extended,
    check_duplicate_multi_layer,
    init_global_db,
    mark_global_posted,
    cleanup_global_db
)


async def test_normalize():
    """Тест нормализации текста"""
    print("\n=== ТЕСТ НОРМАЛИЗАЦИИ ===")
    
    titles = [
        "Иран направил десятки БПЛА для нанесения ударов по Израилю",
        "Иран атаковал Израиль десятками беспилотников",
        "Десятки иранских БПЛА атаковали Израиль",
    ]
    
    for title in titles:
        normalized = normalize_text_for_dedup(title)
        print(f"  '{title[:50]}...' -> '{normalized}'")
    

async def test_fuzzy_similarity():
    """Тест fuzzy схожести"""
    print("\n=== ТЕСТ FUZZY СХОЖЕСТИ ===")
    
    pairs = [
        ("Иран направил десятки БПЛА для нанесения ударов", 
         "Иран атаковал Израиль десятками беспилотников"),
        ("США ввели санкции против России", 
         "Америка ввела ограничительные меры против РФ"),
        ("Путин провел совещание с Совбезом", 
         "Президент провел заседание Совета Безопасности"),
    ]
    
    for title1, title2 in pairs:
        similar = texts_are_similar(title1, title2, threshold=0.65)
        print(f"  '{title1[:40]}' vs '{title2[:40]}' -> similar={similar}")


async def test_entity_matching():
    """Тест entity matching"""
    print("\n=== ТЕСТ ENTITY MATCHING ===")
    
    pairs = [
        ("Иран направил БПЛА для ударов по Израилю", 
         "Иран атаковал Израиль беспилотниками"),
        ("Путин провел совещание с членами Совбеза", 
         "Президент провел заседание Совета Безопасности"),
        ("США ударили по Ирану", 
         "Америка нанесла удары по Исламской Республике"),
    ]
    
    for title1, title2 in pairs:
        dup = are_duplicates_by_entities(title1, title2, min_common_entities=2)
        print(f"  '{title1[:40]}' vs '{title2[:40]}' -> duplicate={dup}")


async def test_hot_duplicates():
    """Тест HOT-дубликатов"""
    print("\n=== ТЕСТ HOT-ДУБЛИКАТОВ ===")
    
    # Инициализация БД
    await init_global_db()
    
    # Очистка старых записей
    await cleanup_global_db(days=1)
    
    category = "politics"
    
    # Симулируем HOT-новости которые должны быть дубликатами
    hot_news = [
        ("Иран направил десятки БПЛА для нанесения ударов по Израилю", "Тегеран атаковал..."),
        ("Иран атаковал Израиль десятками беспилотников", "Множество БПЛА..."),
        ("Десятки иранских БПЛА атаковали Израиль", "В результате атаки..."),
        ("Израиль подвергся массовой атаке иранских дронов", "Системы ПВО..."),
    ]
    
    print(f"  Категория: {category}")
    print(f"  Проверяем {len(hot_news)} HOT-новостей...\n")
    
    results = []
    for title, body in hot_news:
        # Проверяем на дубликат
        is_dup, reason = await check_duplicate_multi_layer(title, body, category, hours=48)
        
        if not is_dup:
            # Отмечаем как опубликованную
            content_hash = get_content_dedup_hash(title, body, category)
            await mark_global_posted(content_hash, "test_bot", "test_parser", title, category)
            print(f"  ✅ НОВАЯ: '{title[:50]}'")
            results.append(("новая", title, reason))
        else:
            print(f"  🔄 ДУБЛИКАТ ({reason}): '{title[:50]}'")
            results.append(("дубликат", title, reason))
    
    # Статистика
    new_count = sum(1 for r in results if r[0] == "новая")
    dup_count = sum(1 for r in results if r[0] == "дубликат")
    
    print(f"\n  📊 ИТОГИ: {new_count} новых, {dup_count} дубликатов")
    
    # Очистка
    await cleanup_global_db(days=1)
    
    return dup_count > 0  # Успех если нашли дубликаты


async def test_extended_fuzzy():
    """Тест extended fuzzy проверки"""
    print("\n=== ТЕСТ EXTENDED FUZZY ===")
    
    await init_global_db()
    await cleanup_global_db(days=1)
    
    category = "politics"
    
    # Сначала публикуем новость
    title1 = "США ввели новые санкции против России"
    body1 = "Администрация президента..."
    content_hash = get_content_dedup_hash(title1, body1, category)
    await mark_global_posted(content_hash, "test_bot", "test_parser", title1, category)
    print(f"  📝 Опубликована: '{title1}'")
    
    # Проверяем похожие новости
    similar_titles = [
        "Америка ввела новые ограничительные меры против РФ",
        "Вашингтон ввел санкции в отношении Москвы",
        "США расширили санкционный список против России",
    ]
    
    for title in similar_titles:
        is_dup = await is_similar_recent_news_extended(title, category, hours=72, threshold=0.65)
        status = "🔄 ДУБЛИКАТ" if is_dup else "✅ НОВАЯ"
        print(f"  {status}: '{title[:50]}'")
    
    await cleanup_global_db(days=1)


async def main():
    print("🧪 ТЕСТЫ УЛУЧШЕННОЙ ДЕДУПЛИКАЦИИ")
    print("=" * 50)
    
    await test_normalize()
    await test_fuzzy_similarity()
    await test_entity_matching()
    await test_hot_duplicates()
    await test_extended_fuzzy()
    
    print("\n" + "=" * 50)
    print("✅ ТЕСТЫ ЗАВЕРШЕНЫ")


if __name__ == "__main__":
    asyncio.run(main())
