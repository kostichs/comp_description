# Инструкция по развертыванию Company Canvas на виртуальной машине

## Шаг 1: Подготовка локально (Windows)

### 1.1. Запуск Docker Desktop
Запустите Docker Desktop вручную из меню Пуск или с рабочего стола.

### 1.2. Остановка и удаление старых контейнеров
```bash
# Проверить запущенные контейнеры
docker ps

# Остановить старые контейнеры (если есть)
docker stop company-canvas-prod
docker rm company-canvas-prod

# Удалить старые образы (опционально)
docker rmi company-canvas-app
docker rmi sergeykostichev/company-canvas-app:v08f
```

### 1.3. Сборка нового образа
```bash
# Собрать локальный образ
docker build -t company-canvas-app .

# Тестирование локально (опционально)
docker run --rm -p 8080:8000 \
  -e OPENAI_API_KEY="ваш_ключ" \
  -e SERPER_API_KEY="ваш_ключ" \
  -e SCRAPINGBEE_API_KEY="ваш_ключ" \
  company-canvas-app
```

### 1.4. Логин в Docker Hub
```bash
docker login
```

### 1.5. Тегирование и публикация
```bash
# Тегировать образ (увеличить номер версии v08g -> v08h)
docker tag company-canvas-app sergeykostichev/company-canvas-app:v08h

# Отправить на Docker Hub
docker push sergeykostichev/company-canvas-app:v08h
```

## Шаг 2: Развертывание на виртуальной машине

### 2.1. Подключение к VM
```bash
ssh ваш_пользователь@IP_адрес_VM
```

### 2.2. Остановка и удаление старого контейнера
```bash
# Остановить старый контейнер
docker stop company-canvas-prod
docker rm company-canvas-prod

# Удалить старые образы (опционально, для экономии места)
docker rmi sergeykostichev/company-canvas-app:v08g
```

### 2.3. Скачивание нового образа
```bash
docker pull sergeykostichev/company-canvas-app:v08h
```

### 2.4. Создание директорий для данных
```bash
# Создать основную директорию для данных
sudo mkdir -p /srv/company-canvas/output
sudo chown -R $USER:$USER /srv/company-canvas/output

# ⚠️ ВАЖНО: Создать файл метаданных сессий, если его еще нет
if [ ! -f /srv/company-canvas/sessions_metadata.json ]; then
    echo '[]' > /srv/company-canvas/sessions_metadata.json
    echo "Создан пустой файл sessions_metadata.json"
fi

# Убедиться что файл доступен для записи
chmod 666 /srv/company-canvas/sessions_metadata.json
```

### 2.5. Запуск нового контейнера
```bash
docker run -d --restart unless-stopped -p 80:8000 \
  -e OPENAI_API_KEY="ваш_реальный_openai_ключ" \
  -e SERPER_API_KEY="ваш_реальный_serper_ключ" \
  -e SCRAPINGBEE_API_KEY="ваш_реальный_scrapingbee_ключ" \
  -e HUBSPOT_API_KEY="ваш_реальный_hubspot_ключ" \
  -e HUBSPOT_BASE_URL="https://app.hubspot.com/contacts/ваш_portal_id/record/0-2/" \
  -e DEBUG="false" \
  --name company-canvas-prod \
  -v /srv/company-canvas/output:/app/output \
  -v /srv/company-canvas/sessions_metadata.json:/app/sessions_metadata.json \
  sergeykostichev/company-canvas-app:v08h
```

### 2.6. Проверка работы
```bash
# Проверить статус контейнера
docker ps

# Посмотреть логи
docker logs company-canvas-prod

# Следить за логами в реальном времени
docker logs -f company-canvas-prod
```

## Шаг 3: Проверка веб-интерфейса

Откройте в браузере: `http://IP_адрес_вашей_VM`

### Тестирование функциональности:
1. **Первая вкладка**: создайте тестовую сессию описания компании
2. **Вторая вкладка**: проверьте что завершенные сессии отображаются для анализа критериев
3. **Статус API**: проверьте `/api/sessions` и `/api/criteria/sessions`

## Решенные проблемы контейнеризации

### Проблема 1: Неправильный .dockerignore
**Симптом**: контейнер не видел сессии во второй вкладке
**Решение**: убрали исключения `output/` и `sessions_metadata.json` из .dockerignore

### Проблема 2: Относительные пути в контейнере
**Симптом**: ошибки "File not found" в логах контейнера
**Решение**: заменили относительные пути на абсолютные (`/app/output/sessions/`)

### Проблема 3: Проблемы с импортами
**Симптом**: "cannot access local variable 'os'" ошибки
**Решение**: исправили порядок импортов в Python модулях

### Проблема 4: Отсутствие sessions_metadata.json
**Симптом**: контейнер не сохранял метаданные между перезапусками
**Решение**: добавили монтирование файла как отдельный том

## Важные изменения в текущей версии

1. **Исправлена контейнеризация**: все пути адаптированы для Docker
2. **Добавлено монтирование sessions_metadata.json**: метаданные сохраняются между перезапусками
3. **Исправлены импорты**: устранены конфликты модулей в контейнере
4. **Улучшена диагностика**: добавлены логи для отладки проблем

## Номера версий

- **v08e**: первая попытка исправления контейнеризации
- **v08f**: исправление путей для контейнера
- **v08g**: исправление импортов и логики
- **v08h**: текущая рабочая версия
- При следующем обновлении используйте v08i

## Что делать, если что-то пошло не так

### Общие проблемы:
1. **Проверить логи контейнера**: `docker logs company-canvas-prod`
2. **Перезапустить контейнер**: `docker restart company-canvas-prod`
3. **Проверить открытые порты**: `sudo ufw status`
4. **Проверить монтированные директории**: `ls -la /srv/company-canvas/`

### Специфичные проблемы:

**Не видны сессии во второй вкладке:**
```bash
# Проверить монтирование sessions_metadata.json
docker exec company-canvas-prod ls -la /app/sessions_metadata.json

# Проверить содержимое
docker exec company-canvas-prod cat /app/sessions_metadata.json
```

**Ошибки "File not found":**
```bash
# Проверить структуру папок в контейнере
docker exec company-canvas-prod find /app/output -type d

# Проверить права доступа
docker exec company-canvas-prod ls -la /app/output/
```

**Проблемы с анализом критериев:**
```bash
# Проверить API эндпоинты
curl http://localhost/api/sessions
curl http://localhost/api/criteria/sessions

# Посмотреть подробные логи
docker logs -f company-canvas-prod | grep -E "(ERROR|criteria|sessions)"
```

## Мониторинг и обслуживание

### Регулярные проверки:
```bash
# Размер лог файлов контейнера
docker logs company-canvas-prod --details | wc -l

# Использование места на диске
du -sh /srv/company-canvas/

# Количество сессий
wc -l /srv/company-canvas/sessions_metadata.json
```

### Очистка данных (при необходимости):
```bash
# Архивировать старые сессии (старше 30 дней)
find /srv/company-canvas/output/sessions -type d -mtime +30 -exec tar -czf {}.tar.gz {} \; -exec rm -rf {} \;

# Очистить логи контейнера
docker logs company-canvas-prod --details 2>/dev/null | tail -1000 > /tmp/recent_logs.txt
# (затем пересоздать контейнер для сброса логов)
``` 