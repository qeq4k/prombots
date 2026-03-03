# 🔧 Настройка портов и подключение к Grafana

## ❓ Как работают порты

Вам **НЕ НУЖНО** менять порты в Grafana! Всё работает автоматически:

```
┌─────────────────────────────────────┐
│     Grafana (порт 3000)             │
│  → Показывает данные из Prometheus  │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   Prometheus (порт 9090)            │
│  → Сам собирает метрики с ботов     │
│    - Politics: 8000                 │
│    - Economy:  8001                 │
│    - Cinema:   8002                 │
└─────────────────────────────────────┘
```

---

## 🚀 Пошаговая настройка

### Шаг 1: Запуск Prometheus

```bash
docker run -d \
  --name prometheus \
  --restart unless-stopped \
  -p 9090:9090 \
  -v /root/projectss/prometheus.yml:/etc/prometheus/prometheus.yml \
  -v prometheus_data:/prometheus \
  prom/prometheus
```

**Проверка:**
```bash
curl http://localhost:9090/targets
# Должен вернуть JSON со статусом targets
```

Или откройте в браузере: **http://localhost:9090/targets**

Все 3 бота должны быть **UP** (зелёные).

---

### Шаг 2: Запуск Grafana

```bash
docker run -d \
  --name grafana \
  --restart unless-stopped \
  -p 3000:3000 \
  -v grafana_data:/var/lib/grafana \
  grafana/grafana
```

**Проверка:**
```bash
docker ps | grep grafana
```

---

### Шаг 3: Настройка datasource в Grafana

1. Откройте: **http://localhost:3000**
2. Логин: `admin`, Пароль: `admin`
3. При первом входе предложат сменить пароль (можно пропустить)
4. Перейдите: **⚙️ Configuration** → **Data sources**
5. Нажмите: **Add data source**
6. Выберите: **Prometheus**
7. В поле **Prometheus server URL** введите:
   ```
   http://host.docker.internal:9090
   ```
   
   > ⚠️ **Если не работает**, попробуйте:
   > ```
   > http://172.17.0.1:9090
   > ```
   > или
   > ```
   > http://<IP-вашего-сервера>:9090
   > ```

8. Нажмите: **Save & test**
9. Должно появиться: **"Data source is working"**

---

### Шаг 4: Импорт дашборда

1. В Grafana перейдите: **Dashboards** → **Import**
2. Выберите: **Upload dashboard JSON file**
3. Загрузите файл: `/root/projectss/grafana_dashboard.json`
4. В поле **Prometheus** выберите ваш datasource
5. Нажмите: **Import**

---

### Шаг 5: Проверка дашборда

После импорта вы увидите:

**Верхний ряд (STAT):**
- 📨 Постов отправлено
- 🔄 Дубликатов
- 🤖 LLM вызовов
- 📋 Кандидатов в очереди

**Средний ряд (TIMESERIES):**
- 📨 Постов в час (график)
- ⏱️ Время обработки поста (p95) — **график вместо цифры!**

**Нижний ряд (TIMESERIES):**
- 💾 LLM Cache Hit Rate %
- 🔄 Дубликатов по типам
- ⚠️ Ошибки LLM

**Последний ряд (STAT):**
- 🚫 Фейковых дат
- 🇬🇧 Постов с английским

---

## 🎨 Что изменилось в дашборде

### Было:
```
Ряд 2: [Постов в час] [LLM Cache Hit Rate]
Ряд 3: [Дубликаты по типам] [Ошибки LLM]
Ряд 4: [Фейковые даты] [Английский] [⏱️ Время обработки (STAT)]
```

### Стало:
```
Ряд 2: [Постов в час] [⏱️ Время обработки (ГРАФИК)] ← ПЕРЕМЕЩЕНО
Ряд 3: [💾 LLM Cache Hit Rate] [Дубликаты по типам] ← СДВИНУТО
Ряд 4: [⚠️ Ошибки LLM] [Фейковые даты] [Английский]
```

**Изменения:**
1. ⏱️ **Время обработки** — теперь **график (timeseries)** вместо STAT
2. 💾 **LLM Cache Hit Rate** — перемещён на ряд ниже
3. Все панели теперь логично сгруппированы

---

## 🔍 Как использовать переменную "$bot"

В верхней части дашборда есть выпадающий список **"Бот"**:

| Выбор | Что показывает |
|-------|----------------|
| **All** | Все боты одновременно (3 линии разных цветов) |
| **politics** | Только политика бот (синяя линия) |
| **economy** | Только экономика бот (жёлтая линия) |
| **cinema** | Только кино бот (красная линия) |

---

## 🎨 Цветовая схема

| Бот | Цвет | Hex Code | Пример |
|-----|------|----------|--------|
| **Politics** | 🔵 Синий | `#5794F2` | <span style="color:#5794F2">████████</span> |
| **Economy** | 🟡 Жёлтый | `#F2CC0C` | <span style="color:#F2CC0C">████████</span> |
| **Cinema** | 🔴 Красный | `#E02F44` | <span style="color:#E02F44">████████</span> |

---

## 🛠️ Запуск ботов

### Economy бот (порт 8001)

```bash
cd /root/projectss
python economika.py
```

**Ожидаемый вывод:**
```
✅ Prometheus метрики запущены на порту 8001
📊 Prometheus метрики запущены на порту http://localhost:8001/metrics (bot=economy)
```

### Politics бот (порт 8000)

```bash
cd /root/politika
python politika.py
```

### Cinema бот (порт 8002)

```bash
cd /root/cinema
python cinema.py
```

---

## 🔍 Проверка работы

### 1. Проверка метрик Economy бота

```bash
curl http://localhost:8001/metrics | grep bot_posts
```

**Вывод:**
```
bot_posts_sent_total{channel="economy",type="suggestion",bot="economy"} 142
```

### 2. Проверка Prometheus

Откройте: **http://localhost:9090/targets**

Все targets должны быть **UP** (зелёные).

### 3. Проверка в Grafana

1. Откройте: **http://localhost:3000**
2. Выберите дашборд: **Telegram Bots Monitoring**
3. Выберите переменную **Бот: economy**
4. Подождите 1-2 минуты (данные обновляются каждые 10-15 сек)

---

## ⚠️ Troubleshooting

### Prometheus не видит ботов

**Проблема:** В http://localhost:9090/targets боты **DOWN**

**Решение:**
1. Проверьте, что боты запущены:
   ```bash
   ps aux | grep economika.py
   ```

2. Проверьте порты:
   ```bash
   netstat -tlnp | grep -E "8000|8001|8002"
   ```

3. Проверьте `prometheus.yml`:
   ```bash
   docker exec prometheus cat /etc/prometheus/prometheus.yml
   ```

### Grafana не подключается к Prometheus

**Проблема:** "Data source is not working"

**Решение:**
1. Попробуйте разные варианты URL:
   ```
   http://host.docker.internal:9090
   http://172.17.0.1:9090
   http://<IP-сервера>:9090
   ```

2. Проверьте, что Prometheus доступен:
   ```bash
   curl http://localhost:9090/-/healthy
   # Должен вернуть "Prometheus Server is Healthy."
   ```

### Нет данных в Grafana

**Проблема:** Графики пустые

**Решение:**
1. Проверьте временной диапазон (выберите "Last 1 hour")
2. Убедитесь, что боты запущены и отправляют метрики
3. Проверьте PromQL запросы в панелях

---

## 📊 Примеры PromQL запросов

### Постов отправлено за последний час
```promql
rate(bot_posts_sent_total{bot="economy"}[1h])
```

### LLM Cache Hit Rate
```promql
rate(bot_llm_cache_hits_total{bot="economy"}[5m]) / (rate(bot_llm_calls_total{bot="economy"}[5m]) + rate(bot_llm_cache_hits_total{bot="economy"}[5m]))
```

### Время обработки (p95)
```promql
histogram_quantile(0.95, sum(rate(bot_post_proc_seconds_bucket{bot="economy"}[5m])) by (le))
```

### Сравнение всех ботов
```promql
sum by (bot) (rate(bot_posts_sent_total[1h]))
```

---

## 📚 Дополнительные ресурсы

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/examples/)

---

**🎉 Готово!** Теперь у вас есть единый мониторинг для всех ботов с цветовой дифференциацией!
