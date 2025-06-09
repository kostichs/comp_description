# Краткая сводка по развертыванию Company Canvas

## Подготовка к развертыванию

**Готово к развертыванию:**
✅ Dockerfile актуален
✅ Requirements.txt проверен  
✅ Контейнеризация исправлена (v08g+)
✅ sessions_metadata.json поддержка добавлена
✅ Документация и скрипты обновлены

## Быстрый старт

### На Windows (локально):

1. **Запустите Docker Desktop** (обязательно!)

2. **Автоматическое развертывание:**
   ```powershell
   .\deploy.ps1
   ```

3. **Или вручную:**
   ```bash
   docker build -t company-canvas-app .
   docker tag company-canvas-app sergeykostichev/company-canvas-app:v08h
   docker push sergeykostichev/company-canvas-app:v08h
   ```

### На виртуальной машине:

1. **Подготовка данных (ВАЖНО!):**
   ```bash
   sudo mkdir -p /srv/company-canvas/output
   sudo chown -R $USER:$USER /srv/company-canvas/output
   
   # Создать файл метаданных сессий если его нет
   if [ ! -f /srv/company-canvas/sessions_metadata.json ]; then
       echo '[]' > /srv/company-canvas/sessions_metadata.json
   fi
   chmod 666 /srv/company-canvas/sessions_metadata.json
   ```

2. **Автоматическое развертывание:**
   ```bash
   chmod +x deploy_vm.sh
   ./deploy_vm.sh v08h
   ```

3. **Или вручную:**
   ```bash
   docker stop company-canvas-prod
   docker rm company-canvas-prod
   docker pull sergeykostichev/company-canvas-app:v08h
   
   docker run -d --restart unless-stopped -p 80:8000 \
     -e OPENAI_API_KEY="ваш_ключ" \
     -e SERPER_API_KEY="ваш_ключ" \
     -e SCRAPINGBEE_API_KEY="ваш_ключ" \
     -e HUBSPOT_API_KEY="ваш_ключ" \
     --name company-canvas-prod \
     -v /srv/company-canvas/output:/app/output \
     -v /srv/company-canvas/sessions_metadata.json:/app/sessions_metadata.json \
     sergeykostichev/company-canvas-app:v08h
   ```

## Проверка работы

```bash
# Статус контейнера
docker ps

# Логи
docker logs -f company-canvas-prod

# Проверка API
curl http://localhost/api/sessions
curl http://localhost/api/criteria/sessions

# Веб-интерфейс
# http://IP_адрес_вашей_VM
```

## Версии и история исправлений

### Проблемы контейнеризации (v08e - v08g):
- **v08e**: первая попытка - проблемы с .dockerignore
- **v08f**: исправление путей - проблемы с импортами  
- **v08g**: исправление импортов - проблемы с метаданными
- **v08h**: полное исправление контейнеризации ✅

### Следующие версии:
- **v08i**: следующая версия для новых функций

## Критические исправления в v08h

### 🔧 Контейнеризация исправлена:
- ✅ Убрали `output/` и `sessions_metadata.json` из .dockerignore
- ✅ Заменили относительные пути на абсолютные (`/app/output/sessions/`)
- ✅ Исправили конфликты импортов модулей
- ✅ Добавили монтирование `sessions_metadata.json` как отдельный том

### 🐛 Решенные проблемы:
1. **Не видны сессии во 2-й вкладке** → исправлено монтированием метаданных
2. **"File not found" ошибки** → исправлено абсолютными путями
3. **"cannot access local variable 'os'"** → исправлено порядком импортов
4. **Потеря метаданных при перезапуске** → исправлено отдельным томом

## Функциональные возможности v08h

1. **Criteria Processor микросервис**: полная интеграция анализа критериев
2. **Async параллельная обработка**: 5-8x ускорение анализа компаний
3. **Международные кодировки**: поддержка UTF-8, Cyrillic, специальных символов
4. **Контейнерная стабильность**: все пути и зависимости корректно работают в Docker
5. **Сохранение состояния**: метаданные сессий сохраняются между перезапусками

## Структура файлов развертывания

- `DEPLOY_INSTRUCTIONS.md` - подробная инструкция с troubleshooting
- `deploy.ps1` - PowerShell скрипт для Windows
- `deploy_vm.sh` - Bash скрипт для VM
- `DEPLOY_SUMMARY.md` - эта сводка
- `docs/DEPLOYMENT_GUIDE.md` - полная документация

## Диагностика проблем

### Быстрая проверка:
```bash
# Контейнер запущен?
docker ps | grep company-canvas-prod

# Есть ли монтированные файлы?
docker exec company-canvas-prod ls -la /app/sessions_metadata.json

# Работают ли API?
curl -s http://localhost/api/sessions | jq length
curl -s http://localhost/api/criteria/sessions | jq length
```

### Если что-то не работает:
```bash
# Подробные логи с фильтрацией
docker logs -f company-canvas-prod | grep -E "(ERROR|criteria|sessions|WARN)"

# Проверка структуры в контейнере
docker exec company-canvas-prod find /app -name "*.json" -o -name "sessions"

# Перезапуск с чистыми логами
docker restart company-canvas-prod
``` 