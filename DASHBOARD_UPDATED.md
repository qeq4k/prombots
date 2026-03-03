# ✅ GRAFANA DASHBOARD ОБНОВЛЁН

## 📊 Что исправлено

В файле `grafana_dashboard.json` исправлены все PromQL запросы:

### Было (неправильно):
```promql
sum by (policy) (bot_posts_sent_total{bot=~"$bot"})
legendFormat: {{policy}}
```

### Стало (правильно):
```promql
sum by (bot) (bot_posts_sent_total{bot=~"$bot"})
legendFormat: {{bot}}
```

## 📋 Список панелей

| ID | Панель | Тип | Метрика |
|----|--------|-----|---------|
| 1 | 📨 Постов отправлено | Stat | `bot_posts_sent_total` |
| 2 | 🔄 Дубликатов | Stat | `bot_duplicates_total` |
| 3 | 🤖 LLM вызовов | Stat | `bot_llm_calls_total` |
| 4 | 📋 Кандидатов в очереди | Stat | `bot_candidates_current` |
| 5 | 📨 Постов в час | Timeseries | `rate(bot_posts_sent_total[1h])` |
| 6 | ⏱️ Время обработки (p95) | Timeseries | `histogram_quantile(bot_post_proc_seconds_bucket)` |
| 7 | 💾 LLM Cache Hit Rate % | Timeseries | `bot_llm_cache_hits_total / bot_llm_calls_total` |
| 8 | 🔄 Дубликаты по типам | Timeseries | `bot_duplicates_total by (type)` |
| 9 | ⚠️ Ошибки LLM | Timeseries | `rate(bot_llm_errors_total[5m])` |
| 10 | 🚫 Фейковых дат | Stat | `bot_fake_dates_total` |
| 11 | 🇬🇧 Постов с английским | Stat | `bot_english_blocked_total` |

## 🎨 Цвета ботов

| Бот | Цвет |
|-----|------|
| politics | 🔵 Синий (#5794F2) |
| economy | 🟡 Жёлтый (#F2CC0C) |
| cinema | 🔴 Красный (#E02F44) |

## 📥 Импорт в Grafana

### Вариант 1: Через UI
1. Откройте Grafana
2. Dashboards → Import
3. Загрузите файл `grafana_dashboard.json`
4. Выберите Prometheus datasource
5. Нажмите **Import**

### Вариант 2: Через API
```bash
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @grafana_dashboard.json
```

## ✅ Проверка работы

### 1. Проверка метрик
```bash
# Политика (порт 8000)
curl localhost:8000/metrics | grep "^bot_"

# Экономика (порт 8001)
curl localhost:8001/metrics | grep "^bot_"

# Кино (порт 8002)
curl localhost:8002/metrics | grep "^bot_"
```

### 2. Примеры PromQL запросов

**Постов за всё время по ботам:**
```promql
sum by (bot) (bot_posts_sent_total)
```

**Постов в час:**
```promql
sum by (bot) (rate(bot_posts_sent_total[1h])) * 3600
```

**Дубликатов по типам:**
```promql
sum by (type, bot) (bot_duplicates_total)
```

**Cache Hit Rate:**
```promql
sum by (bot) (rate(bot_llm_cache_hits_total[5m])) / 
(sum by (bot) (rate(bot_llm_calls_total[5m])) + sum by (bot) (rate(bot_llm_cache_hits_total[5m]))) * 100
```

**Ошибки LLM за 5 минут:**
```promql
sum by (bot) (rate(bot_llm_errors_total[5m])) * 300
```

## 📁 Файлы

```
/root/projectss/
├── grafana_dashboard.json    # ✅ Обновлённый дашборд
├── prometheus_metrics.py     # Модуль метрик
├── politika.py               # Бот политики
├── economika.py              # Бот экономики
└── movie.py                  # Бот кино
```

## 🎯 Итого

- ✅ Все 11 панелей используют правильный label `bot`
- ✅ Все PromQL запросы используют `sum by (bot)` вместо `sum by (policy)`
- ✅ legendFormat использует `{{bot}}` вместо `{{policy}}`
- ✅ JSON валидный и готов к импорту
