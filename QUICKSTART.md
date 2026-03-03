# 🚀 Быстрый старт для Economy бота с Prometheus метриками

## ✅ Что уже сделано

1. **Установлен prometheus-client** ✅
2. **Интегрирован в economika.py** ✅
   - Добавлен импорт `prometheus_metrics`
   - Создан экземпляр `prom_metrics = PrometheusMetrics(bot_name='economy', port=8001)`
   - Добавлены вызовы метрик в ключевых местах

## 📁 Файлы

```
/root/projectss/
├── economika.py                # ✅ Обновлён с метриками
├── prometheus_metrics.py       # ✅ Универсальный модуль
├── prometheus.yml              # ✅ Конфиг Prometheus (3 бота)
├── grafana_dashboard.json      # ✅ Дашборд с цветами
├── show_metrics.sh             # ✅ Скрипт проверки
└── QUICKSTART.md               # ✅ Этот файл
```

## 🚀 Запуск бота

```bash
cd /root/projectss
python economika.py
```

**Ожидаемый вывод:**
```
✅ Prometheus метрики запущены на порту 8001
📊 Prometheus метрики запущены на порту http://localhost:8001/metrics (bot=economy)
```

## 📊 Проверка метрик

### Вариант 1: Быстрая проверка в терминале

```bash
cd /root/projectss
./show_metrics.sh
```

### Вариант 2: Проверка через curl

```bash
curl http://localhost:8001/metrics | grep bot_posts
```

### Вариант 3: Prometheus UI

Откройте: http://localhost:9090

**Пример запроса:**
```promql
bot_posts_sent_total{bot="economy"}
```

## 📈 Настройка Grafana

### 1️⃣ Запуск Prometheus

```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /root/projectss/prometheus.yml:/etc/prometheus/prometheus.yml \
  -v prometheus_data:/prometheus \
  --restart unless-stopped \
  prom/prometheus
```

### 2️⃣ Запуск Grafana

```bash
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -v grafana_data:/var/lib/grafana \
  --restart unless-stopped \
  grafana/grafana
```

### 3️⃣ Настройка datasource в Grafana

1. Откройте: http://localhost:3000
2. Логин: `admin`, Пароль: `admin`
3. Перейдите: **Configuration** → **Data sources** → **Add data source**
4. Выберите: **Prometheus**
5. URL: `http://host.docker.internal:9090`
6. Нажмите: **Save & test**

> ⚠️ Если `host.docker.internal` не работает, используйте IP хоста:
> ```bash
> # Узнайте IP хоста
> ip addr show docker0 | grep "inet " | awk '{print $2}'
> # Например: 172.17.0.1
> ```

### 4️⃣ Импорт дашборда

1. Скачайте файл дашборда: https://github.com/grafana/grafana/tree/main/public/dashboards
2. Или используйте локальный: `/root/projectss/grafana_dashboard.json`
3. В Grafana: **Dashboards** → **Import**
4. Загрузите файл `grafana_dashboard.json`
5. Выберите datasource: `Prometheus`
6. Нажмите: **Import**

## 🎨 Цветовая схема

| Бот | Цвет | Порт |
|-----|------|------|
| 🔵 Politics | Синий `#5794F2` | 8000 |
| 🟡 Economy | Жёлтый `#F2CC0C` | 8001 |
| 🔴 Cinema | Красный `#E02F44` | 8002 |

## 📊 Доступные метрики

### Отправляемые Economy ботом:

| Метрика | Описание | Пример |
|---------|----------|--------|
| `bot_posts_sent_total` | Отправленные посты | `channel="economy", type="suggestion"` |
| `bot_duplicates_total` | Дубликаты | `type="fuzzy"`, `type="content"`, `type="global"` |
| `bot_llm_calls_total` | LLM вызовы | `operation="rewrite"` |
| `bot_llm_cache_hits_total` | Попадания в кэш | - |
| `bot_llm_errors_total` | Ошибки LLM | - |
| `bot_fake_dates_total` | Фейковые даты | - |
| `bot_english_blocked_total` | Английские слова | - |

## 🔍 Примеры PromQL запросов

### Постов отправлено за последний час
```promql
rate(bot_posts_sent_total{bot="economy"}[1h])
```

### LLM Cache Hit Rate
```promql
rate(bot_llm_cache_hits_total{bot="economy"}[5m]) / (rate(bot_llm_calls_total{bot="economy"}[5m]) + rate(bot_llm_cache_hits_total{bot="economy"}[5m]))
```

### Дубликаты по типам
```promql
sum by (type) (rate(bot_duplicates_total{bot="economy"}[5m]))
```

### Ошибки LLM
```promql
rate(bot_llm_errors_total{bot="economy"}[5m])
```

## 🛠️ Добавление Politics бота

1. Скопируйте `prometheus_metrics.py` в директорию Politics бота
2. Добавьте в код Politics бота:
   ```python
   from prometheus_metrics import PrometheusMetrics
   prom_metrics = PrometheusMetrics(bot_name='politics', port=8000)
   ```
3. Добавьте вызовы `prom_metrics.inc_*()` аналогично Economy боту

## 🛠️ Добавление Cinema бота (будущий)

1. Скопируйте `prometheus_metrics.py` в директорию Cinema бота
2. Добавьте в код Cinema бота:
   ```python
   from prometheus_metrics import PrometheusMetrics
   prom_metrics = PrometheusMetrics(bot_name='cinema', port=8002)
   ```

## ⚠️ Troubleshooting

### Метрики не отображаются

1. Проверьте, что бот запущен:
   ```bash
   ps aux | grep economika.py
   ```

2. Проверьте порт:
   ```bash
   netstat -tlnp | grep 8001
   ```

3. Проверьте метрики напрямую:
   ```bash
   curl http://localhost:8001/metrics
   ```

### Prometheus не скрейпит

1. Проверьте статус в Prometheus UI: http://localhost:9090/targets
2. Проверьте конфиг:
   ```bash
   docker exec prometheus cat /etc/prometheus/prometheus.yml
   ```

### Grafana не показывает данные

1. Проверьте datasource (должен быть активен)
2. Проверьте временной диапазон (выберите "Last 1 hour")
3. Проверьте PromQL запросы в панелях

## 📚 Документация

- Полная инструкция: `INTEGRATION_GUIDE.md`
- Prometheus: https://prometheus.io/docs/
- Grafana: https://grafana.com/docs/
- Prometheus Client: https://github.com/prometheus/client_python

---

**🎉 Готово!** Economy бот отправляет метрики в Prometheus!
