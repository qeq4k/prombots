# 🎉 Новые фичи — Документация

## ✅ Что добавлено

### 1. 📊 Веб-дашборд для админа

**Запуск:**
```bash
pm2 status dashboard
```

**Доступ:**
- http://localhost:8080
- http://<твой_IP>:8080

**Что показывает:**
- ✅ Статус всех ботов (online/offline)
- ✅ Потребление памяти каждым ботом
- ✅ Постов отправлено за сегодня/неделю
- ✅ Последние посты из всех каналов
- ✅ Системная информация (RAM, диск)
- ✅ Автообновление каждые 30 секунд

**API endpoints:**
```bash
# Статус ботов
curl http://localhost:8080/api/status

# Статистика
curl http://localhost:8080/api/stats

# Последние посты
curl http://localhost:8080/api/recent?limit=10

# Health check
curl http://localhost:8080/api/health
```

---

### 2. 📑 Авто-рубрикация

**Что делает:**
- Автоматически добавляет рубрики к постам
- Использует LLM для классификации
- Кэширует результаты

**Использование в боте:**

```python
from shared import AutoRubrics, add_rubric_to_text

# Инициализация
rubrics = AutoRubrics(llm_client)

# Получение рубрики
rubric = await rubrics.get_rubric(
    title="ЦБ поднял ключевую ставку",
    text="Банк России принял решение...",
    category="economy"
)
# Результат: "#экономика #ставки"

# Добавление к тексту
text_with_rubric = add_rubric_to_text(text, rubric)
```

**Предопределённые рубрики:**

| Категория | Рубрики |
|-----------|---------|
| politics | #политика, #внешняя_политика, #дипломатия, #санкции, #конфликты... |
| economy | #экономика, #финансы, #нефть, #газ, #инфляция, #ставки... |
| cinema | #кино, #премьеры, #сериалы, #актёры, #режиссёры... |

**Добавление в politika.py/economika.py/movie.py:**

Найди место где формируется текст поста и добавь:

```python
# Перед отправкой в канал
from shared import AutoRubrics, add_rubric_to_text

rubrics_gen = AutoRubrics(llm)
rubric = await rubrics_gen.get_rubric(title, text, category="politics")
final_text = add_rubric_to_text(text, rubric)

# Отправляем final_text вместо text
```

---

### 3. 🎄 Сезонные шаблоны

**Что делает:**
- Добавляет праздничные заголовки в дайджесты
- Украшает посты сезонными эмодзи
- Автоматически определяет праздники

**Использование:**

```python
from shared import SeasonalTemplates, apply_seasonal_template

templates = SeasonalTemplates()

# Проверка: сегодня праздник?
if templates.is_holiday_today():
    holiday = templates.get_today_holiday()
    print(f"Сегодня: {holiday}")

# Заголовок для дайджеста
header = templates.get_header()
# 8 Марта: "🌷 <b>ПРАЗДНИЧНЫЙ ДАЙДЖЕСТ К 8 МАРТА</b> 🌷"
# Обычный: "📊 <b>ДАЙДЖЕСТ ЗА 06.03.2026</b>"

# Футер
footer = templates.get_footer()
# 8 Марта: "\n\n🌷 С 8 Марта! Весеннего настроения! 🌸"

# Украшение поста
decorated = templates.decorate_post(text)

# Или одним вызовом:
final = apply_seasonal_template(text, template_type="digest")
```

**Праздники:**

| Дата | Праздник | Шапка |
|------|----------|-------|
| 1 янв | Новый год | 🎄🎅 <b>НОВОГОДНИЙ ДАЙДЖЕСТ</b> 🎅🎄 |
| 7 янв | Рождество | ⭐ <b>РОЖДЕСТВЕНСКИЙ ДАЙДЖЕСТ</b> ⭐ |
| 23 фев | 23 Февраля | 🛡️ <b>ДАЙДЖЕСТ К 23 ФЕВРАЛЯ</b> 🛡️ |
| 8 мар | 8 Марта | 🌷 <b>ПРАЗДНИЧНЫЙ ДАЙДЖЕСТ К 8 МАРТА</b> 🌷 |
| 9 мая | День Победы | 🎖️ <b>ДАЙДЖЕСТ К ДНЮ ПОБЕДЫ</b> 🎖️ |
| 31 окт | Хэллоуин | 🎃 <b>ХЭЛЛОУИНСКИЙ ДАЙДЖЕСТ</b> 🎃 |

**Интеграция с дайджестами:**

В `shared/digest.py`, метод `generate_digest_text`:

```python
# После генерации текста через LLM
from shared import SeasonalTemplates

templates = SeasonalTemplates()
digest_text = apply_seasonal_template(digest_text, template_type="digest")
```

---

## 📁 Структура файлов

```
/root/projectss/
├── dashboard/              # ← НОВОЕ: Веб-дашборд
│   ├── main.py
│   └── templates/
│       └── dashboard.html
│
├── shared/
│   ├── rubrics.py          # ← НОВОЕ: Авто-рубрикация
│   └── seasonal.py         # ← НОВОЕ: Сезонные шаблоны
│
├── ecosystem.config.js     # ← Обновлён (dashboard)
└── ...
```

---

## 🚀 Управление

### Перезапуск дашборда:
```bash
pm2 restart dashboard
```

### Просмотр логов:
```bash
pm2 logs dashboard --lines 50
```

### Открыть дашборд:
```
http://<твой_IP>:8080
```

---

## 📊 Потребление ресурсов

| Процесс | Память |
|---------|--------|
| dashboard | ~47 MB |
| politics | ~181 MB |
| economy | ~182 MB |
| cinema | ~188 MB |
| bot_handler | ~43 MB |
| bot_new | ~116 MB |
| crosspost | ~43 MB |
| urgent | ~82 MB |

**Всего:** ~882 MB из 1.5 GB ✅

---

## 🔧 Настройки

### Изменить порт дашборда:

В `dashboard/main.py`:
```python
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8080,  # ← Измени порт
    log_level="info"
)
```

### Добавить праздник:

В `shared/seasonal.py`, словарь `HOLIDAYS`:
```python
HOLIDAYS = {
    # ...
    (12, 31): "Новый год (канун)",  # Добавь новую строку
}
```

### Добавить рубрику:

В `shared/rubrics.py`, словарь `RUBRICS`:
```python
RUBRICS = {
    "politics": [
        "#политика",
        "#новая_рубрика",  # Добавь новую
        # ...
    ],
}
```

---

## 🐛 Troubleshooting

### Дашборд не открывается:

1. Проверь что запущен:
   ```bash
   pm2 status dashboard
   ```

2. Проверь порт:
   ```bash
   netstat -tlnp | grep 8080
   ```

3. Перезапусти:
   ```bash
   pm2 restart dashboard
   ```

### Авто-рубрикация не работает:

1. Проверь что LLM доступен
2. Проверь логи:
   ```bash
   pm2 logs politics --lines 50 | grep rubric
   ```

### Сезонные шаблоны не применяются:

1. Проверь что сегодня праздник:
   ```python
   from shared import SeasonalTemplates
   t = SeasonalTemplates()
   print(t.get_today_holiday())
   ```

2. Если праздник в будущем — шаблоны применяются только в день праздника

---

## 📞 Поддержка

По вопросам — в чат разработки.
