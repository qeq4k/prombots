# 📊 НАСТРОЙКА METRICS ДЛЯ 3 БОТОВ

## ✅ Статус

Все 3 бота настроены и отправляют метрики в Prometheus:

| Бот | Файл | Порт | Статус |
|-----|------|------|--------|
| **Politika** | politika.py | 8000 | ✅ Работает |
| **Economy** | economika.py | 8001 | ✅ Работает |
| **Cinema** | movie.py | 8002 | ✅ Работает |

## 📋 Отправляемые метрики

### Counter (счётчики)

| Метрика | Description | Labels | Пример |
|---------|-------------|--------|--------|
| `bot_posts_sent_total` | Отправленные посты | `bot`, `channel`, `type` | `bot="politics", type="suggestion"` |
| `bot_duplicates_total` | Заблокированные дубликаты | `bot`, `type` | `type="fuzzy"`, `type="global"` |
| `bot_llm_calls_total` | Вызовы LLM | `bot`, `operation` | `operation="classify"`, `operation="rewrite"` |
| `bot_llm_cache_hits_total` | Попадания в кэш LLM | `bot` | - |
| `bot_llm_errors_total` | Ошибки LLM | `bot` | - |
| `bot_fake_dates_total` | Заблокировано фейковых дат | `bot` | - |
| `bot_english_blocked_total` | Заблокировано постов с английским | `bot` | - |

### Gauge (измерители)

| Метрика | Description | Labels |
|---------|-------------|--------|
| `bot_candidates_current` | Кандидатов в очереди | `bot` |

### Histogram (гистограммы)

| Метрика | Description | Labels | Buckets |
|---------|-------------|--------|---------|
| `bot_post_proc_seconds` | Время обработки поста | `bot` | 0.1-120s |

## 🔍 PromQL запросы для Grafana

### Постов отправлено (все боты)
```promql
sum by (bot) (bot_posts_sent_total{bot=~"$bot"})
```

### Постов в час
```promql
sum by (bot) (rate(bot_posts_sent_total{bot=~"$bot"}[1h])) * 3600
```

### Дубликаты по типам
```promql
sum by (type) (rate(bot_duplicates_total{bot=~"$bot"}[5m])) * 300
```

### LLM Cache Hit Rate %
```promql
sum by (bot) (rate(bot_llm_cache_hits_total{bot=~"$bot"}[5m])) / 
  (sum by (bot) (rate(bot_llm_calls_total{bot=~"$bot"}[5m])) + 
   sum by (bot) (rate(bot_llm_cache_hits_total{bot=~"$bot"}[5m])))
```

### Время обработки (p95)
```promql
histogram_quantile(0.95, sum(rate(bot_post_proc_seconds_bucket{bot=~"$bot"}[5m])) by (le, bot))
```

### Ошибки LLM
```promql
sum by (bot) (rate(bot_llm_errors_total{bot=~"$bot"}[5m])) * 300
```

## 🎨 Цветовая схема в Grafana

| Бот | Цвет | Hex Code |
|-----|------|----------|
| **Politics** | 🔵 Синий | `#5794F2` |
| **Economy** | 🟡 Жёлтый | `#F2CC0C` |
| **Cinema** | 🔴 Красный | `#E02F44` |

## 📊 Типы дубликатов (цвета)

| Тип | Цвет | Hex Code |
|-----|------|----------|
| `exact` | Розовый | `#FF7383` |
| `fuzzy` | Светло-розовый | `#FFA6C1` |
| `global` | Тёмно-красный | `#C4162A` |
| `content` | Оранжевый | `#FA6400` |
| `entity` | Зелёный | `#96D98D` |

## 🚀 Проверка работы

### 1. Проверка метрик каждого бота
```bash
# Politika
curl http://localhost:8000/metrics | grep "^bot_posts_sent_total"

# Economy
curl http://localhost:8001/metrics | grep "^bot_posts_sent_total"

# Cinema
curl http://localhost:8002/metrics | grep "^bot_posts_sent_total"
```

### 2. Проверка Prometheus
Откройте: http://localhost:9090/targets

Все 3 target должны быть **UP** (зелёные).

### 3. Проверка Grafana
1. Откройте: http://localhost:3000
2. Импортируйте: `/root/projectss/grafana_dashboard.json`
3. Выберите переменную **Бот: All**
4. Проверьте что все панели отображают 3 линии разных цветов

## ⚠️ Troubleshooting

### Метрики не отображаются в Grafana
1. Проверьте что боты запущены: `ps aux | grep python`
2. Проверьте порты: `netstat -tlnp | grep 800`
3. Проверьте Prometheus: http://localhost:9090/targets

### Все линии одного цвета
1. Убедитесь что метрики имеют label `bot`: `curl localhost:8000/metrics | grep bot_`
2. Импортируйте обновлённый дашборд из `/root/projectss/grafana_dashboard.json`

### Метрики не обновляются
1. Проверьте refresh в Grafana (должно быть 10s)
2. Проверьте что боты активны и постят новости
3. Проверьте логи ботов на наличие ошибок

## 📁 Структура файлов

```
/root/projectss/
├── prometheus_metrics.py       # Универсальный модуль метрик
├── grafana_dashboard.json      # Дашборд Grafana
├── prometheus.yml              # Конфиг Prometheus
├── politika.py                 # Politics бот (порт 8000)
├── economika.py                # Economy бот (порт 8001)
├── movie.py                    # Cinema бот (порт 8002)
└── METRICS_SETUP.md            # Эта инструкция
```

## 🎉 Готово!

Все 3 бота отправляют метрики в Prometheus с правильными labels.
Grafana отображает данные с цветовой дифференциацией по ботам.
