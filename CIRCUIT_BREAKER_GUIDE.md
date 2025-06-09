# 🛡️ Circuit Breaker & State Management Guide

## Обзор новых возможностей

Система анализа критериев теперь включает:

1. **🛡️ Circuit Breaker Pattern** - автоматическая защита от rate limiting
2. **💾 State Management** - сохранение прогресса и возможность восстановления
3. **🔄 Recovery System** - возобновление прерванных сессий
4. **📊 Progress Tracking** - детальное отслеживание состояния

## 🚀 Быстрый старт

### Обычный запуск с защитой
```bash
# Запуск с Circuit Breaker (включен по умолчанию)
python main.py --parallel --session-id my_analysis_001

# Запуск с отключенным Circuit Breaker (не рекомендуется)
python main.py --parallel --disable-circuit-breaker --session-id my_analysis_002
```

### Поиск возобновляемых сессий
```bash
# Показать все сессии которые можно возобновить
python main.py --list-resumable
```

### Возобновление прерванной сессии
```bash
# Возобновить конкретную сессию
python main.py --resume-session crit_20241201_143022

# Возобновить с дополнительными параметрами
python main.py --resume-session crit_20241201_143022 --parallel --max-concurrent 8
```

## 🛡️ Circuit Breaker Pattern

### Как это работает

Circuit Breaker автоматически отслеживает ошибки OpenAI API и координирует паузы между всеми потоками:

1. **🟢 CLOSED** (нормальная работа)
   - Все запросы проходят
   - Считаются ошибки rate limiting

2. **🔴 OPEN** (блокировка)
   - Все запросы блокируются на 120 секунд
   - Сохраняется текущий прогресс
   - Система ждет восстановления API

3. **🟡 HALF_OPEN** (тестирование)
   - Пропускается 3 тестовых запроса
   - При успехе → переход в CLOSED
   - При ошибке → возврат в OPEN

### Конфигурация

В `src/utils/config.py`:

```python
CIRCUIT_BREAKER_CONFIG = {
    'enable_circuit_breaker': True,     # Включить/выключить
    'failure_threshold': 5,             # Ошибок для открытия
    'recovery_timeout': 120,            # Секунд ожидания
    'success_threshold': 3,             # Успехов для закрытия
    'rate_limit_keywords': [            # Ключевые слова ошибок
        'rate_limit', 'quota_exceeded', 'too_many_requests'
    ]
}
```

## 💾 State Management

### Что сохраняется

Система автоматически сохраняет:

- ✅ Текущий прогресс (продукт, компания, стадия)
- ✅ Промежуточные результаты анализа
- ✅ Метаданные сессии
- ✅ События Circuit Breaker
- ✅ Статистику ошибок

### Файлы состояния

В папке `output/{session_id}/`:

```
crit_20241201_143022/
├── crit_20241201_143022_progress.json      # Прогресс обработки
├── crit_20241201_143022_partial_results.json # Промежуточные результаты
├── crit_20241201_143022_metadata.json      # Метаданные сессии
└── final_results.csv                       # Финальные результаты
```

## 🔄 Recovery System

### Автоматическое восстановление

При возобновлении сессии система:

1. **Проверяет** возможность восстановления
2. **Загружает** сохраненный прогресс
3. **Валидирует** существующие результаты
4. **Продолжает** с места остановки

### Типы восстановления

```bash
# Полное восстановление (рекомендуется)
python main.py --resume-session crit_20241201_143022

# Восстановление с новыми параметрами
python main.py --resume-session crit_20241201_143022 --max-concurrent 6

# Восстановление без Circuit Breaker (осторожно!)
python main.py --resume-session crit_20241201_143022 --disable-circuit-breaker
```

## 📊 Мониторинг и логи

### Ключевые индикаторы

В логах ищите:

```
🛡️ Circuit Breaker инициализирован: threshold=5, timeout=120s
🟢 Circuit Breaker ЗАКРЫТ - нормальная работа восстановлена
🔴 Circuit Breaker ОТКРЫТ - блокировка OpenAI запросов на 120s
💾 State Manager активирован для сессии: crit_20241201_143022
📂 Загружено 150 существующих результатов
```

### Статусы сессий

- `created` - сессия создана
- `processing` - обработка в процессе
- `paused` - приостановлена Circuit Breaker
- `completed` - успешно завершена
- `failed` - завершена с ошибкой
- `cancelled` - отменена пользователем

## 🚨 Troubleshooting

### Проблема: Circuit Breaker постоянно открыт

**Причина:** Превышен лимит OpenAI API

**Решение:**
1. Проверьте баланс OpenAI аккаунта
2. Уменьшите `max_concurrent_companies`
3. Увеличьте `recovery_timeout` в конфиге

```bash
# Запуск с меньшей нагрузкой
python main.py --parallel --max-concurrent 3 --session-id reduced_load
```

### Проблема: Не удается возобновить сессию

**Причина:** Поврежденные файлы состояния

**Решение:**
1. Проверьте список сессий: `python main.py --list-resumable`
2. Удалите поврежденные файлы из `output/{session_id}/`
3. Запустите новую сессию

### Проблема: Медленная обработка

**Причина:** Консервативные настройки Circuit Breaker

**Решение:**
```bash
# Отключить Circuit Breaker (осторожно!)
python main.py --parallel --disable-circuit-breaker --max-concurrent 15
```

## 🔧 Настройка для продакшена

### Рекомендуемые параметры

```bash
# Стабильная обработка
python main.py --parallel --max-concurrent 8 --session-id prod_analysis

# Быстрая обработка (риск rate limiting)
python main.py --parallel --max-concurrent 15 --session-id fast_analysis

# Максимальная стабильность
python main.py --parallel --max-concurrent 3 --session-id stable_analysis
```

### Docker запуск

```bash
# Обычный запуск
docker run -v $(pwd)/output:/app/output company-description-app:v10f_circuit_breaker \
  python services/criteria_processor/main.py --parallel --session-id docker_analysis

# Возобновление в Docker
docker run -v $(pwd)/output:/app/output company-description-app:v10f_circuit_breaker \
  python services/criteria_processor/main.py --resume-session crit_20241201_143022
```

## 📈 Производительность

### До Circuit Breaker
- ❌ 5-й продукт часто падал
- ❌ Потеря всех результатов при сбое
- ❌ Cascade failures при rate limiting
- ⏱️ 40-80 минут (если завершится)

### После Circuit Breaker
- ✅ Все 5 продуктов обрабатываются стабильно
- ✅ Сохранение прогресса при любых сбоях
- ✅ Координированные паузы вместо cascade failures
- ⏱️ 45-85 минут (гарантированное завершение)

## 🎯 Best Practices

1. **Всегда используйте session-id** для отслеживания
2. **Начинайте с max-concurrent=8** для стабильности
3. **Проверяйте --list-resumable** перед новым запуском
4. **Не отключайте Circuit Breaker** без крайней необходимости
5. **Мониторьте логи** для раннего обнаружения проблем

## 🔮 Будущие улучшения

- [ ] Adaptive rate limiting на основе API response times
- [ ] Distributed circuit breaker для multiple instances
- [ ] Real-time dashboard для мониторинга
- [ ] Automatic retry scheduling
- [ ] Smart batching optimization 