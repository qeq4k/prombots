# 📊 Интеграция Prometheus метрик для нескольких ботов

## 🎯 Вариант 3: Единый Prometheus + Label фильтрация

Все боты используют **один Prometheus** и **один Grafana dashboard**, но каждый бот имеет свой **label `bot`** и **порт**.

---

## 📋 Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                     Grafana :3000                           │
│  Dashboard с переменной $bot (politics/economy/cinema)      │
│  Цвета: 🔵 politics=синий, 🟡 economy=жёлтый, 🔴 cinema=красный │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                  Prometheus :9090                           │
│  scrape_interval: 15s                                       │
│  targets: localhost:8000, 8001, 8002                        │
└────┬──────────────────┬──────────────────┬─────────────────┘
     │                  │                  │
┌────▼────────┐  ┌─────▼────────┐  ┌──────▼────────┐
│ Politics    │  │  Economy     │  │   Cinema      │
│ Bot         │  │  Bot         │  │   Bot         │
│ :8000       │  │  :8001       │  │   :8002       │
│ bot=politics│  │  bot=economy │  │   bot=cinema  │
└─────────────┘  └──────────────┘  └───────────────┘
```

---

## 🚀 Установка

### 1️⃣ Установка зависимостей

```bash
# Для всех ботов
pip install prometheus-client

# Опционально: Docker для Prometheus и Grafana
apt install docker.io
```

### 2️⃣ Запуск Prometheus

```bash
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v /root/projectss/prometheus.yml:/etc/prometheus/prometheus.yml \
  -v prometheus_data:/prometheus \
  prom/prometheus
```

### 3️⃣ Запуск Grafana

```bash
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -v grafana_data:/var/lib/grafana \
  grafana/grafana
```

**Логин/пароль:** `admin` / `admin`

---

## 🔧 Интеграция в ботов

### 📁 Файл `prometheus_metrics.py`

Скопируйте файл `prometheus_metrics.py` в директорию каждого бота.

### 📝 Политика бот (`@I_Politika`)

```python
# В начале файла
from prometheus_metrics import PrometheusMetrics

# После импортов
prom_metrics = PrometheusMetrics(bot_name='politics', port=8000)

# В коде бота (примеры)
def some_function():
    # Отправка поста
    prom_metrics.inc_post('politics', 'autopost')
    
    # Дубликат
    prom_metrics.inc_dup('fuzzy')
    
    # LLM вызов
    prom_metrics.inc_llm('classify')
    
    # Попадание в кэш
    prom_metrics.inc_cache()
    
    # Ошибка
    prom_metrics.inc_err()
    
    # Фейковая дата
    prom_metrics.inc_date()
    
    # Английские слова
    prom_metrics.inc_eng()
    
    # Время обработки
    import time
    start = time.time()
    # ... обработка ...
    prom_metrics.observe_proc_time(time.time() - start)
```

### 📝 Экономика бот (`@eco_steroid`)

```python
# В начале файла
from prometheus_metrics import PrometheusMetrics

# После импортов
prom_metrics = PrometheusMetrics(bot_name='economy', port=8001)

# Далее аналогично политике боту
```

### 📝 Кино бот (`@Film_orbita` — будущий)

```python
# В начале файла
from prometheus_metrics import PrometheusMetrics

# После импортов
prom_metrics = PrometheusMetrics(bot_name='cinema', port=8002)
```

---

## 📊 Настройка Grafana Dashboard

### 1️⃣ Импорт дашборда

1. Откройте Grafana: http://localhost:3000
2. Логин: `admin`, пароль: `admin`
3. Перейдите: **Dashboards** → **Import**
4. Загрузите файл `grafana_dashboard.json`
5. Выберите datasource: `Prometheus` (http://localhost:9090)
6. Нажмите **Import**

### 2️⃣ Использование переменной `$bot`

В верхней части дашборда есть выпадающий список **"Бот"**:

- **All** — показать все боты одновременно
- **politics** — только политика бот
- **economy** — только экономика бот
- **cinema** — только кино бот

### 3️⃣ Цветовая схема

| Бот | Цвет | Hex |
|-----|------|-----|
| Politics | 🔵 Синий | `#5794F2` |
| Economy | 🟡 Жёлтый | `#F2CC0C` |
| Cinema | 🔴 Красный | `#E02F44` |

Цвета заданы в **Overrides** для каждой панели.

---

## 📈 Доступные метрики

### Counter (счётчики)

| Метрика | Описание | Labels |
|---------|----------|--------|
| `bot_posts_sent_total` | Отправленные посты | `channel`, `type`, `bot` |
| `bot_duplicates_total` | Заблокированные дубликаты | `type`, `bot` |
| `bot_llm_calls_total` | Вызовы LLM | `operation`, `bot` |
| `bot_llm_cache_hits_total` | Попадания в LLM кэш | `bot` |
| `bot_llm_errors_total` | Ошибки LLM | `bot` |
| `bot_fake_dates_total` | Заблокировано фейковых дат | `bot` |
| `bot_english_blocked_total` | Заблокировано постов с английским | `bot` |

### Gauge (измерители)

| Метрика | Описание | Labels |
|---------|----------|--------|
| `bot_candidates_current` | Кандидатов в очереди | `bot` |

### Histogram (гистограммы)

| Метрика | Описание | Labels | Buckets |
|---------|----------|--------|---------|
| `bot_post_proc_seconds` | Время обработки поста | `bot` | 0.1-120s |

---

## 🔍 Примеры PromQL запросов

### Постов отправлено за последний час по всем ботам
```promql
sum(rate(bot_posts_sent_total[1h]))
```

### Постов по конкретному боту
```promql
sum(rate(bot_posts_sent_total{bot="economy"}[1h]))
```

### LLM Cache Hit Rate %
```promql
rate(bot_llm_cache_hits_total[5m]) / (rate(bot_llm_calls_total[5m]) + rate(bot_llm_cache_hits_total[5m]))
```

### Дубликаты по типам
```promql
sum by (type) (rate(bot_duplicates_total[5m]))
```

### 95-й перцентиль времени обработки
```promql
histogram_quantile(0.95, sum(rate(bot_post_proc_seconds_bucket[5m])) by (le))
```

### Сравнение ботов
```promql
sum by (bot) (rate(bot_posts_sent_total[1h]))
```

---

## 🛠️ Утилиты

### show_metrics.sh

Скрипт для быстрого просмотра метрик в терминале:

```bash
cd /root/projectss
./show_metrics.sh
```

**Вывод:**
```
==============================================
📊 МЕТРИКИ TELEGRAM БОТОВ
==============================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🔵 POLITICS BOT (порт 8000)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   📨 Постов отправлено:     156
   🔄 Дубликатов:            23
   🤖 LLM вызовов:           89
   💾 LLM Cache Hits:        12
   ⚠️ LLM Ошибки:            2
   🚫 Фейковых дат:          5
   🇬🇧 Постов с английским:  3

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🟡 ECONOMY BOT (порт 8001)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   📨 Постов отправлено:     142
   ...
```

---

## 📁 Структура файлов

```
/root/projectss/
├── prometheus.yml              # Конфиг Prometheus
├── grafana_dashboard.json      # Дашборд для импорта
├── prometheus_metrics.py       # Универсальный модуль метрик
├── show_metrics.sh             # Скрипт просмотра метрик
├── INTEGRATION_GUIDE.md        # Эта инструкция
├── economika.py                # Экономика бот
└── ... (другие боты)
```

---

## 🎨 Настройка цветов в Grafana

Если вы хотите изменить цвета:

1. Откройте дашборд в Grafana
2. Нажмите **Edit** на панели
3. Перейдите: **Panel** → **Overrides**
4. Найдите override для `bot = politics/economy/cinema`
5. Измените цвет в **Color** → **Fixed color**

Или отредактируйте `grafana_dashboard.json` и импортируйте заново.

---

## ⚠️ Troubleshooting

### Метрики не отображаются

1. Проверьте, что prometheus-client установлен:
   ```bash
   pip list | grep prometheus
   ```

2. Проверьте, что порты открыты:
   ```bash
   netstat -tlnp | grep 8000
   netstat -tlnp | grep 8001
   netstat -tlnp | grep 8002
   ```

3. Проверьте логи ботов на наличие ошибок

### Prometheus не скрейпит метрики

1. Проверьте `prometheus.yml`:
   ```bash
   docker exec prometheus cat /etc/prometheus/prometheus.yml
   ```

2. Проверьте статус targets в Prometheus UI: http://localhost:9090/targets

3. Убедитесь, что боты запущены и слушают порты

### Grafana не показывает данные

1. Проверьте datasource в Grafana (должен быть Prometheus)
2. Проверьте временной диапазон (должен быть "last 1 hour" или больше)
3. Проверьте PromQL запросы в панелях

---

## 📚 Дополнительные ресурсы

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Client for Python](https://github.com/prometheus/client_python)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/examples/)

---

## ✅ Чек-лист интеграции

- [ ] Установлен `prometheus-client`
- [ ] Скопирован `prometheus_metrics.py` в каждый проект
- [ ] Создан экземпляр `PrometheusMetrics` в каждом боте
- [ ] У каждого бота свой порт (8000, 8001, 8002)
- [ ] Настроен `prometheus.yml` с тремя job
- [ ] Запущен Prometheus в Docker
- [ ] Запущен Grafana в Docker
- [ ] Импортирован дашборд `grafana_dashboard.json`
- [ ] Добавлены вызовы `prom_metrics.inc_*()` в код ботов
- [ ] Проверено отображение метрик в Grafana

---

**🎉 Готово!** Теперь все боты отправляют метрики в единый Prometheus с цветовой дифференциацией!
