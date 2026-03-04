#!/bin/bash
# 📊 Скрипт для быстрого просмотра метрик всех ботов
# Использование: ./show_metrics.sh

echo "=============================================="
echo "📊 МЕТРИКИ TELEGRAM БОТОВ"
echo "=============================================="
echo ""

# Цвета для ботов
COLOR_POLITICS="\033[1;34m"  # Синий
COLOR_ECONOMY="\033[1;33m"   # Жёлтый
COLOR_CINEMA="\033[1;31m"    # Красный
COLOR_HANDLER="\033[1;35m"   # Фиолетовый
COLOR_RESET="\033[0m"

# Функция для получения метрики (сумма по всем labels)
get_metric() {
    local port=$1
    local metric=$2
    curl -s "http://localhost:$port/metrics" 2>/dev/null | grep "^$metric" | awk '{sum+=$2} END {if (sum=="") print 0; else print sum}'
}

# Функция для отображения метрик бота
show_bot_metrics() {
    local name=$1
    local port=$2
    local color=$3
    
    echo -e "${color}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
    echo -e "${color}  $name (порт $port)${COLOR_RESET}"
    echo -e "${color}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${COLOR_RESET}"
    
    # Проверяем доступность
    if ! curl -s "http://localhost:$port/metrics" > /dev/null 2>&1; then
        echo "   ❌ Бот недоступен"
        echo ""
        return 1
    fi
    
    # Получаем метрики
    posts_sent=$(get_metric $port "bot_posts_sent_total{")
    duplicates=$(get_metric $port "bot_duplicates_total{")
    llm_calls=$(get_metric $port "bot_llm_calls_total{")
    llm_cache=$(get_metric $port "bot_llm_cache_hits_total{")
    llm_errors=$(get_metric $port "bot_llm_errors_total{")
    fake_dates=$(get_metric $port "bot_fake_dates_total{")
    english_blocked=$(get_metric $port "bot_english_blocked_total{")
    slipped_dups=$(get_metric $port "bot_slipped_duplicates_total{")

    # Отображаем
    printf "   📨 Постов отправлено:     %s\n" "${posts_sent:-0}"
    printf "   🔄 Дубликатов:            %s\n" "${duplicates:-0}"
    printf "   🤖 LLM вызовов:           %s\n" "${llm_calls:-0}"
    printf "   💾 LLM Cache Hits:        %s\n" "${llm_cache:-0}"
    printf "   ⚠️ LLM Ошибки:            %s\n" "${llm_errors:-0}"
    printf "   🚫 Фейковых дат:          %s\n" "${fake_dates:-0}"
    printf "   🇬🇧 Постов с английским:  %s\n" "${english_blocked:-0}"
    printf "   🎯 Проскоч. дубликатов:   %s\n" "${slipped_dups:-0}"
    echo ""
}

# Политика бот
show_bot_metrics "🔵 POLITICS BOT" "8000" "$COLOR_POLITICS"

# Экономика бот
show_bot_metrics "🟡 ECONOMY BOT" "8001" "$COLOR_ECONOMY"

# Кино бот
show_bot_metrics "🔴 CINEMA BOT" "8002" "$COLOR_CINEMA"

# Bot handler (предложка)
show_bot_metrics "🟣 BOT HANDLER" "8003" "$COLOR_HANDLER"

echo "=============================================="
echo "🌐 Prometheus: http://localhost:9090"
echo "📈 Grafana:    http://localhost:3000 (admin/admin)"
echo "=============================================="
echo ""
echo "📄 Детальные метрики:"
echo "   - Politics:  http://localhost:8000/metrics"
echo "   - Economy:   http://localhost:8001/metrics"
echo "   - Cinema:    http://localhost:8002/metrics"
echo "   - Handler:   http://localhost:8003/metrics"
echo ""
