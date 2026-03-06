# 📊 Digest — Ежедневные дайджесты для каналов

## ✅ Что сделано

Создан модуль `shared/digest.py` для генерации дайджестов за сутки.

**Возможности:**
- Автоматический сбор топ-5 новостей за день
- Генерация текста через LLM (2000-4096 символов)
- HTML-форматирование с эмодзи
- Проверка "не был ли уже отправлен"
- Планировщик на ежедневной основе

---

## 🚀 Интеграция в ботов

### 1. Politika (✅ уже интегрировано)

В `politika.py` добавлено:

```python
# Импорт
from shared import DigestGenerator, schedule_digest_for_category

# В main() после инициализации:
digest_task = asyncio.create_task(
    schedule_digest_for_category(llm, telegram_client, config, "politics", hour=22)
)
```

### 2. Economika

**Шаг 1:** Добавь импорт в начало файла:

```python
from shared import DigestGenerator, schedule_digest_for_category
```

**Шаг 2:** В функции `main()` после создания `llm` и `telegram_client`:

```python
# ✅ ЗАПУСК ПЛАНИРОВЩИКА ДАЙДЖЕСТОВ (ежедневно в 22:00)
digest_task = None
if config.autopost_enabled:
    try:
        digest_task = asyncio.create_task(
            schedule_digest_for_category(llm, telegram_client, config, "economy", hour=22)
        )
        logger.info("✅ Планировщик дайджестов запущен (22:00 daily)")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось запустить планировщик дайджестов: {e}")
```

**Шаг 3:** Перезапусти бота:

```bash
pm2 restart economy
```

### 3. Movie (Cinema)

**Шаг 1:** Импорт:

```python
from shared import DigestGenerator, schedule_digest_for_category
```

**Шаг 2:** В `main()`:

```python
# ✅ ЗАПУСК ПЛАНИРОВЩИКА ДАЙДЖЕСТОВ (ежедневно в 22:00)
digest_task = None
if config.autopost_enabled:
    try:
        digest_task = asyncio.create_task(
            schedule_digest_for_category(llm, telegram_client, config, "cinema", hour=22)
        )
        logger.info("✅ Планировщик дайджестов запущен (22:00 daily)")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось запустить планировщик дайджестов: {e}")
```

**Шаг 3:** Перезапуск:

```bash
pm2 restart cinema
```

---

## ⚙️ Настройки

### Изменить время отправки

В `main()` каждого бота:

```python
# Politika — в 22:00
schedule_digest_for_category(llm, tg, config, "politics", hour=22)

# Economy — в 21:00
schedule_digest_for_category(llm, tg, config, "economy", hour=21)

# Cinema — в 23:00
schedule_digest_for_category(llm, tg, config, "cinema", hour=23)
```

### Изменить количество топ-новостей

В `shared/digest.py`, метод `select_top_posts`:

```python
async def select_top_posts(self, posts: List[Dict], top_n: int = 5) -> List[Dict]:
    # Измени top_n на 3 или 7
```

### Изменить длину дайджеста

В `shared/digest.py`, метод `generate_digest_text`:

```python
prompt = f"""
...
6. Длина: 2000-3500 символов  # ← измени на нужное
...
"""
```

И в конце метода:

```python
return text[:4096]  # ← измени лимит
```

---

## 📊 Проверка работы

### 1. Логи бота

```bash
pm2 logs politics --lines 50 | grep -i digest
```

**Ожидаемый вывод:**
```
✅ Планировщик дайджестов запущен (22:00 daily)
⏰ Следующий дайджест через 2.5 ч
📊 Генерация дайджеста для politics...
📊 Топ-5 постов для дайджеста: [...]
✅ Дайджест отправлен (msg_id=12345)
```

### 2. Проверка в канале

В 22:00 (или другое время) в канале появится пост:

```
📊 ДАЙДЖЕСТ ЗА 06.03.2026

Главное за день в политике...

🏛️ Новость 1
Краткое описание...

💰 Новость 2
Краткое описание...

#дайджест #politics
```

### 3. Проверка БД

```bash
sqlite3 politika.db "SELECT title, posted_at FROM posts WHERE title LIKE '%ДАЙДЖЕСТ%' ORDER BY posted_at DESC LIMIT 5;"
```

---

## 🔧 Ручное создание дайджеста

Если нужно создать дайджест прямо сейчас:

```python
# В Python консоли или через скрипт
import asyncio
from shared import DigestGenerator

async def create_manual_digest():
    from politika import llm, telegram_client, config
    
    digest = DigestGenerator(llm, telegram_client, config)
    success = await digest.generate_and_send("politics", force=True)
    print(f"✅ Дайджест: {'успешно' if success else 'ошибка'}")

asyncio.run(create_manual_digest())
```

---

## 📈 Метрики Prometheus

Дайджесты отправляются как обычные посты, поэтому метрики:

```bash
curl http://localhost:8000/metrics | grep bot_posts_sent_total
```

---

## 🐛 Troubleshooting

### Дайджест не создаётся

1. Проверь что есть посты за сегодня:
   ```bash
   sqlite3 politika.db "SELECT COUNT(*) FROM posts WHERE posted_at > datetime('now', 'start of day');"
   ```

2. Проверь логи:
   ```bash
   pm2 logs politics --lines 100 | grep -i digest
   ```

### Дайджест слишком короткий

LLM может генерировать короткий текст. Измени промпт в `shared/digest.py`:

```python
prompt = f"""
...
6. Длина: 3000-4000 символов  # ← увеличь
...
"""
```

### Дайджест отправляется дважды

Проверка `is_digest_already_sent()` может не работать. Убедись что БД существует и запись сохраняется:

```bash
sqlite3 politika.db "SELECT * FROM posts WHERE title LIKE '%ДАЙДЖЕСТ%' ORDER BY posted_at DESC;"
```

---

## 💡 Идеи для улучшения

- [ ] Дайджест за неделю (в воскресенье)
- [ ] Персонализация по интересам пользователей
- [ ] Добавление статистики (сколько постов за день)
- [ ] Кнопки "Читать далее" с ссылками
- [ ] Голосование за лучший дайджест недели

---

## 📞 Поддержка

По вопросам — в чат разработки.
