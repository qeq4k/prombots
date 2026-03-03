# 🔧 ИСПРАВЛЕНИЕ МЕТРИК PROMETHEUS

## 🐛 ПРОБЛЕМА
Метрики не отображались в Grafana правильно, потому что:
1. **Politika бот** использовал старый локальный класс `PrometheusMetrics` **БЕЗ label `bot`**
2. Метрики отправлялись как: `bot_posts_sent_total{channel="politics",type="suggestion"}` (НЕТ label `bot`!)
3. Grafana не могла фильтровать по ботам

## ✅ РЕШЕНИЕ
Заменили локальный класс на универсальный модуль `prometheus_metrics.PrometheusMetrics`

### Изменения в politika.py:
```python
# БЫЛО (строка 537):
class PrometheusMetrics:
    def __init__(self):
        self.posts_sent = Counter('bot_posts_sent_total', 'Posts sent', ['channel', 'type'])
        # ... нет label 'bot'!

# СТАЛО (строка 537):
from prometheus_metrics import PrometheusMetrics
prom_metrics = PrometheusMetrics(bot_name='politics', port=8000)
# ✅ Теперь метрики будут: bot_posts_sent_total{bot="politics",...}
```

## 🚀 ПЕРЕЗАПУСК БОТОВ

### 1. Остановите старых ботов:
```bash
pkill -f politika.py
pkill -f economika.py
pkill -f movie.py
```

### 2. Проверьте что порты освободились:
```bash
netstat -tlnp | grep -E "8000|8001|8002"
# Должно быть пусто
```

### 3. Запустите ботов заново:
```bash
# Terminal 1 - Politika
cd /root/projectss
python politika.py

# Terminal 2 - Economy
cd /root/projectss
python economika.py

# Terminal 3 - Cinema (опционально)
cd /root/projectss
python movie.py
```

### 4. Проверьте метрики:
```bash
# Politika
curl http://localhost:8000/metrics | grep "bot_posts_sent_total"
# Ожидаемый вывод: bot_posts_sent_total{bot="politics",...}  ← label bot есть!

# Economy
curl http://localhost:8001/metrics | grep "bot_posts_sent_total"
# Ожидаемый вывод: bot_posts_sent_total{bot="economy",...}  ← label bot есть!

# Cinema
curl http://localhost:8002/metrics | grep "bot_posts_sent_total"
# Ожидаемый вывод: bot_posts_sent_total{bot="cinema",...}  ← label bot есть!
```

## 📊 ОБНОВЛЕНИЕ GRAFANA

1. Откройте Grafana: http://localhost:3000
2. Импортируйте обновлённый дашборд: `/root/projectss/grafana_dashboard.json`
3. Выберите переменную **Бот: All** чтобы видеть все боты

## 🎨 ЦВЕТОВАЯ СХЕМА

| Бот | Цвет | Пример |
|-----|------|--------|
| **Politics** | 🔵 Синий | `#5794F2` |
| **Economy** | 🟡 Жёлтый | `#F2CC0C` |
| **Cinema** | 🔴 Красный | `#E02F44` |

## ✅ ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

После перезапуска:
- ✅ Все 3 бота отображаются **разными цветами**
- ✅ Метрики **обновляются каждые 10 секунд**
- ✅ **3 линии** на графиках (по одной на бота)
- ✅ Дубликаты по типам — **4 цвета** (exact/fuzzy/global/content)

## 🔍 PROMQL ЗАПРОСЫ (ТЕПЕРЬ РАБОТАЮТ)

```promql
# Постов отправлено (все боты)
sum by (bot) (bot_posts_sent_total{bot=~"$bot"})

# Постов в час (все боты)
sum by (bot) (rate(bot_posts_sent_total{bot=~"$bot"}[1h])) * 3600

# Дубликаты по типам
sum by (type) (rate(bot_duplicates_total{bot=~"$bot"}[5m])) * 300
```

## ⚠️ ВОЗМОЖНЫЕ ПРОБЛЕМЫ

### Метрики не отображаются
1. Проверьте что боты запущены: `ps aux | grep python`
2. Проверьте порты: `netstat -tlnp | grep 800`
3. Проверьте Prometheus: http://localhost:9090/targets

### Все линии одного цвета
1. Убедитесь что метрики имеют label `bot`: `curl localhost:8000/metrics | grep bot_`
2. Импортируйте обновлённый дашборд из `/root/projectss/grafana_dashboard.json`

### Метрики не обновляются
1. Проверьте refresh в Grafana (должно быть 10s)
2. Проверьте что боты активны и постят новости
