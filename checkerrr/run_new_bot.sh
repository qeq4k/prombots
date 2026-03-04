#!/bin/bash

# 🚀 Скрипт проверки и запуска новой версии бота

echo "🔍 Проверка новой версии бота..."
echo ""

# Проверка Python
echo "1️⃣ Проверка Python..."
python3 --version
if [ $? -ne 0 ]; then
    echo "❌ Python3 не найден!"
    exit 1
fi
echo "✅ Python3 найден"
echo ""

# Проверка зависимостей
echo "2️⃣ Проверка зависимостей..."
pip3 install -r requirements.txt --break-system-packages -q 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Попытка установки с --break-system-packages..."
    pip3 install -r requirements.txt --break-system-packages
    if [ $? -ne 0 ]; then
        echo "❌ Ошибка установки зависимостей!"
        exit 1
    fi
fi
echo "✅ Зависимости установлены"
echo ""

# Проверка синтаксиса
echo "3️⃣ Проверка синтаксиса..."
python3 -m py_compile constants.py types.py database.py
if [ $? -ne 0 ]; then
    echo "❌ Ошибка в основных файлах!"
    exit 1
fi

python3 -m py_compile services/*.py
if [ $? -ne 0 ]; then
    echo "❌ Ошибка в сервисах!"
    exit 1
fi

python3 -m py_compile handlers/*.py
if [ $? -ne 0 ]; then
    echo "❌ Ошибка в handlers!"
    exit 1
fi

python3 -m py_compile middlewares/*.py
if [ $? -ne 0 ]; then
    echo "❌ Ошибка в middleware!"
    exit 1
fi

python3 -m py_compile bot_new.py
if [ $? -ne 0 ]; then
    echo "❌ Ошибка в bot_new.py!"
    exit 1
fi
echo "✅ Синтаксис в порядке"
echo ""

# Проверка .env
echo "4️⃣ Проверка .env..."
if [ ! -f .env ]; then
    echo "⚠️  .env не найден. Копируем из .env.example..."
    cp .env.example .env
    echo "❗ Отредактируйте .env и добавьте BOT_TOKEN и ADMIN_IDS"
    exit 1
fi
echo "✅ .env найден"
echo ""

# Проверка БД
echo "5️⃣ Проверка базы данных..."
if [ ! -f movies.db ]; then
    echo "⚠️  База данных не найдена. Создаём..."
    python3 fill_db.py
fi
echo "✅ База данных готова"
echo ""

# Вывод информации
echo "=========================================="
echo "✅ Все проверки пройдены!"
echo "=========================================="
echo ""
echo "📋 Новые функции:"
echo "  🎲 Случайный фильм"
echo "  📈 Тренды"
echo "  🏆 Достижения"
echo "  🔔 Уведомления"
echo "  👍 Реакции"
echo "  🔍 Похожие фильмы"
echo ""
echo "🚀 Для запуска используйте:"
echo "   python3 bot_new.py"
echo ""
echo "📚 Документация:"
echo "   - README.md - основная документация"
echo "   - MIGRATION.md - руководство по миграции"
echo "   - CHANGELOG.md - список изменений"
echo ""
echo "=========================================="
