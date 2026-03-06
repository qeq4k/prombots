# 🔄 Crosspost Service — Кросс-постинг между Telegram каналами

## 📖 Описание

Сервис автоматического кросс-постинга между каналами:
- **@I_Politika** (политика)
- **@eco_steroid** (экономика)
- **@Film_orbita** (кино)

Сервис анализирует опубликованные посты через LLM, определяет пригодность для кросс-постинга, адаптирует текст под стиль целевого канала и отправляет на модерацию.

---

## 🎯 Как это работает

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Пост опубликован в канале (через bot_handler.py)           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Crosspost анализирует пост через LLM                       │
│     • Тематика (можно ли адаптировать?)                        │
│     • Целевые каналы (politics/economy/cinema)                 │
│     • Оценка интереса (0-100)                                  │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Адаптация текста под стиль канала                          │
│     • Политика → официально-деловой стиль                      │
│     • Экономика → аналитический стиль                          │
│     • Кино → развлекательный стиль                             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Отправка на модерацию в предложку                          │
│     • Бот отправляет пост с кнопками                           │
│     • ✅ Опубликовать  ❌ Отклонить  ✏️ Редактировать           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Модерация (ручная или автоматическая)                      │
│     • При approve → публикация в целевой канал                 │
│     • При reject → удаление                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Структура файлов

```
/root/projectss/
├── crosspost/
│   ├── __init__.py         # Пакет
│   ├── config.py           # Конфигурация
│   ├── database.py         # SQLite БД
│   ├── analyzer.py         # LLM анализ
│   ├── publisher.py        # Публикация
│   ├── crossposter.py      # Основная логика
│   ├── bot.py              # Бот модерации
│   └── main.py             # Точка входа
├── crosspost.db            # База данных
├── crosspost.log           # Лог
└── bot_handler.py          # ✅ Обновлён с интеграцией
```

---

## 🚀 Запуск

### Вариант 1: Прямой запуск

```bash
cd /root/projectss
python crosspost/main.py
```

### Вариант 2: Через PM2 (рекомендуется)

Добавь в `ecosystem.config.js`:

```javascript
{
  name: "crosspost",
  script: "crosspost/main.py",
  interpreter: "python3",
  cwd: "/root/projectss",
  instances: 1,
  autorestart: true,
  max_memory_restart: "200M",
  env: {
    PYTHONPATH: "/root/projectss"
  }
}
```

Затем:

```bash
pm2 start ecosystem.config.js --name crosspost
pm2 save
```

---

## ⚙️ Настройка

### Переменные окружения (.env)

```bash
# Telegram
TG_TOKEN=1234567890:AAH...

# Каналы
TG_CHANNEL_POLITICS=-1003739906790
TG_CHANNEL_ECONOMY=-1003701005081
TG_CHANNEL_CINEMA=-1003635948209

# Предложки
SUGGESTION_CHAT_ID_POLITICS=-1003659350130
SUGGESTION_CHAT_ID_ECONOMY=-1003711339547
SUGGESTION_CHAT_ID_CINEMA=-1003892651191

# Подписи
SIGNATURE_POLITICS="@I_Politika"
SIGNATURE_ECONOMY="@eco_steroid"
SIGNATURE_CINEMA="@Film_orbita"

# LLM
ROUTER_API_KEY=sk-...
```

### Настройки в crosspost/config.py

```python
# Минимальный интерес для кросс-поста (0-100)
min_interest_score: int = 60

# Автопубликация без модерации
auto_publish: bool = False  # ⚠️ Рекомендуется False

# Минимум между кросс-постами (минуты)
min_interval_minutes: int = 30

# Макс кросс-постов в день в один канал
max_per_day_per_channel: int = 10
```

---

## 📊 Метрики Prometheus

Кросс-постинг отправляет метрики на порт **8006**:

| Метрика | Описание |
|---------|----------|
| `bot_posts_sent_total{bot="crosspost"}` | Опубликовано кросс-постов |
| `bot_duplicates_total{bot="crosspost"}` | Дубликаты |
| `bot_llm_calls_total{bot="crosspost"}` | LLM вызовы (анализ + адаптация) |

Проверка:

```bash
curl http://localhost:8006/metrics
```

---

## 🤖 Бот для модерации

Бот слушает в предложках и добавляет кнопки под кросс-постами:

```
🔄 Кросс-пост из 🏛️ Политика
🎯 Для: 💰 Экономика
⭐ Интерес: 75/100

[Текст поста...]

[✅ Опубликовать] [❌ Отклонить]
[✏️ Редактировать]
```

### Команды бота:

- `/start` — Запуск
- `/help` — Помощь
- `/stats` — Статистика кросс-постинга

---

## 📈 Статистика

Просмотр статистики через БД:

```bash
sqlite3 crosspost.db "SELECT status, COUNT(*) FROM crossposts GROUP BY status;"
```

Или через бота командой `/stats`.

---

## 🔧 Интеграция с bot_handler.py

bot_handler.py автоматически отправляет новые посты на анализ:

```python
# ✅ CROSSPOST: Отправляем на анализ
if CROSSPOST_ENABLED and crossposter_service:
    await crossposter_service.analyze_and_queue(
        post_text=draft.text,
        source_channel=channel_key,
        post_id=post_id
    )
```

### Отключение кросс-постинга

Если нужно временно отключить:

```python
# В bot_handler.py
CROSSPOST_ENABLED = False
```

Или не запускать crosspost/main.py.

---

## 🐛 Troubleshooting

### Кросс-посты не создаются

1. Проверь логи:
   ```bash
   tail -f crosspost.log
   ```

2. Проверь что LLM API работает:
   ```bash
   curl -H "Authorization: Bearer $ROUTER_API_KEY" \
        https://routerai.ru/v1/models
   ```

3. Проверь что bot_handler.py отправляет посты:
   ```bash
   grep "Crosspost" bot_handler.log
   ```

### Бот модерации не отвечает

1. Проверь что бот запущен:
   ```bash
   pm2 status crosspost
   ```

2. Проверь токен бота:
   ```bash
   curl https://api.telegram.org/bot$TG_TOKEN/getMe
   ```

### Дубликаты кросс-постов

Проверь БД:

```bash
sqlite3 crosspost.db "SELECT * FROM published_crossposts ORDER BY published_at DESC LIMIT 10;"
```

---

## 📝 Планы развития

- [ ] Автоматическая публикация для постов с interest > 90
- [ ] A/B тестирование заголовков
- [ ] Интеграция с Grafana
- [ ] Веб-интерфейс модерации
- [ ] Поддержка других каналов

---

## 📞 Поддержка

По вопросам и багам — в чат разработки.
