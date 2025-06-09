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
docker rmi sergeykostichev/company-canvas-app:v07
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
# Тегировать образ (увеличить номер версии v07 -> v08)
docker tag company-canvas-app sergeykostichev/company-canvas-app:v08

# Отправить на Docker Hub
docker push sergeykostichev/company-canvas-app:v08
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

# Удалить старые образы (опционально)
docker rmi sergeykostichev/company-canvas-app:v07
```

### 2.3. Скачивание нового образа
```bash
docker pull sergeykostichev/company-canvas-app:v08
```

### 2.4. Создание директории для данных (если еще не создана)
```bash
sudo mkdir -p /srv/company-canvas/output
sudo chown -R $USER:$USER /srv/company-canvas/output
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
  sergeykostichev/company-canvas-app:v08
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

## Важные изменения в текущей версии

1. **Исправлена проблема с file descriptors**: добавлены ограничения соединений для этапа валидации URL
2. **Улучшена стабильность**: семафор для ограничения одновременных проверок URL
3. **Сохранен batch processing**: основной pipeline работает с обычными ограничениями

## Номера версий

- **v06**: предыдущая версия
- **v07**: текущая версия с исправлениями соединений
- При следующем обновлении используйте v08

## Что делать, если что-то пошло не так

1. **Проверить логи контейнера**: `docker logs company-canvas-prod`
2. **Перезапустить контейнер**: `docker restart company-canvas-prod`
3. **Проверить открытые порты**: `sudo ufw status`
4. **Проверить монтированные директории**: `ls -la /srv/company-canvas/output` 