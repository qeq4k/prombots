# 🚀 Запуск Crosspost Service

## ✅ Что сделано

1. **Создан пакет `/root/projectss/crosspost/`**:
   - `config.py` — конфигурация
   - `database.py` — SQLite для истории
   - `analyzer.py` — LLM анализ постов
   - `publisher.py` — публикация в каналы
   - `crossposter.py` — основная логика
   - `bot.py` — бот для модерации
   - `main.py` — точка входа

2. **Обновлён `bot_handler.py`**:
   - Добавлена интеграция с crosspost
   - При публикации поста → автоматический анализ для кросс-постинга

3. **Обновлён `ecosystem.config.js`**:
   - Добавлен процесс `crosspost`

4. **Создана документация**:
   - `CROSSPOST_README.md` — полная документация

---

## 📝 Проверка перед запуском

### 1. Проверь что все модули импортируются:

```bash
cd /root/projectss
python3 -c "from crosspost.main import service; print('✅ OK')"
```

**Ожидаемый вывод:**
```
✅ Prometheus метрики на порту 8006
✅ OK
```

### 2. Проверь что bot_handler видит crosspost:

```bash
cd /root/projectss
python3 -c "import bot_handler; print('✅ OK')"
```

**Ожидаемый вывод:**
```
✅ Crosspost сервис загружен
✅ bot_handler loaded successfully
```

---

## 🚀 Запуск через PM2 (рекомендуется)

### 1. Запусти crosspost:

```bash
cd /root/projectss
pm2 start ecosystem.config.js --name crosspost
pm2 save
```

### 2. Проверь статус:

```bash
pm2 status crosspost
pm2 logs crosspost --lines 50
```

### 3. Перезапусти bot_handler (чтобы применилась интеграция):

```bash
pm2 restart bot_handler
pm2 save
```

---

## 🧪 Тестовый запуск

### Вариант 1: Прямой запуск (для тестов)

```bash
cd /root/projectss
python3 crosspost/main.py
```

**Ожидаемый вывод:**
```
🚀 Запуск crosspost service...
✅ БД кросс-постинга подключена: crosspost.db
✅ HTTP сессия анализатора создана
✅ Сессия Telegram publisher запущена
✅ Crosspost service запущен
📡 Notification to bot_handler: started
🌐 Webhook сервер запущен на порту 8080
🔄 Запуск основного цикла...
```

### Вариант 2: Через PM2

```bash
pm2 start crosspost
pm2 logs crosspost
```

---

## 📊 Проверка работы

### 1. Проверь метрики Prometheus:

```bash
curl http://localhost:8006/metrics | head -30
```

**Ожидаемые метрики:**
```
bot_posts_sent_total{bot="crosspost"} 0
bot_llm_calls_total{bot="crosspost"} 0
bot_duplicates_total{bot="crosspost"} 0
```

### 2. Проверь базу данных:

```bash
sqlite3 crosspost.db "SELECT name FROM sqlite_master WHERE type='table';"
```

**Ожидаемые таблицы:**
```
crossposts
published_crossposts
sqlite_sequence
```

### 3. Проверь логи:

```bash
tail -f logs/crosspost-out.log
tail -f logs/crosspost-error.log
```

---

## 🤖 Как тестировать кросс-постинг

### Шаг 1: Опубликуй пост в любом канале

Через bot_handler (в предложке нажми ✅ Опубликовать).

### Шаг 2: Проверь логи crosspost

```bash
tail -f logs/crosspost-out.log | grep "Анализ поста"
```

**Ожидаемый лог:**
```
📊 Анализ поста из politics: can_crosspost=True, targets=['economy'], score=75
✅ Добавлен кросс-пост: politics → economy
```

### Шаг 3: Проверь предложку целевого канала

Бот должен отправить пост на модерацию с кнопками:
```
🔄 Кросс-пост из 🏛️ Политика
🎯 Для: 💰 Экономика
⭐ Интерес: 75/100

[Текст...]

[✅ Опубликовать] [❌ Отклонить] [✏️ Редактировать]
```

### Шаг 4: Нажми ✅ Опубликовать

Пост будет опубликован в целевом канале.

---

## ⚙️ Настройки

### Включить автопубликацию (без модерации)

В `crosspost/config.py`:

```python
auto_publish: bool = True  # ⚠️ Только для тестов!
```

### Изменить минимальный интерес

В `crosspost/config.py`:

```python
min_interest_score: int = 50  # Порог интереса (0-100)
```

### Отключить кросс-постинг временно

В `bot_handler.py`:

```python
CROSSPOST_ENABLED = False
```

Или просто останови crosspost:

```bash
pm2 stop crosspost
```

---

## 🛑 Остановка

```bash
pm2 stop crosspost
pm2 delete crosspost
pm2 save
```

---

## 📈 Мониторинг

### Статистика через БД:

```bash
sqlite3 crosspost.db "SELECT status, COUNT(*) FROM crossposts GROUP BY status;"
```

### Статистика через бота:

Отправь `/stats` боту модерации в любой предложке.

### Метрики Prometheus:

```bash
curl -s http://localhost:8006/metrics | grep crosspost
```

---

## 🐛 Troubleshooting

### Crosspost не запускается

1. Проверь логи:
   ```bash
   pm2 logs crosspost --lines 100
   ```

2. Проверь что LLM API доступен:
   ```bash
   curl -H "Authorization: Bearer $ROUTER_API_KEY" \
        https://routerai.ru/v1/models
   ```

### Бот модерации не отвечает

1. Проверь токен:
   ```bash
   curl https://api.telegram.org/bot$TG_TOKEN/getMe
   ```

2. Перезапусти:
   ```bash
   pm2 restart crosspost
   ```

### Кросс-посты не создаются

1. Проверь что bot_handler отправляет посты:
   ```bash
   grep "Crosspost" logs/bot_handler-out.log
   ```

2. Проверь что interest_score достаточный:
   ```bash
   sqlite3 crosspost.db "SELECT source_channel, target_channel, interest_score FROM crossposts ORDER BY created_at DESC LIMIT 5;"
   ```

---

## 📞 Поддержка

По вопросам — в чат разработки.
