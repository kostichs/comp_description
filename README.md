# Company Canvas - Генератор описаний компаний с анализом критериев

Веб-приложение для автоматической генерации описаний компаний на основе их веб-сайтов с последующим анализом по заданным критериям.

## 🚀 Быстрый старт
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001

### Развертывание на виртуальной машине

1. **Автоматическое развертывание:**
   ```bash
   chmod +x deploy_vm.sh
   ./deploy_vm.sh v08h
   ```

2. **Подробные инструкции:** см. [DEPLOY_INSTRUCTIONS.md](DEPLOY_INSTRUCTIONS.md)

3. **Краткая сводка:** см. [DEPLOY_SUMMARY.md](DEPLOY_SUMMARY.md)

## 📋 Основные возможности

- **Генерация описаний**: автоматическое создание описаний компаний на основе их веб-сайтов
- **Анализ критериев**: проверка компаний по заданным критериям квалификации
- **Параллельная обработка**: быстрая обработка множества компаний одновременно
- **Веб-интерфейс**: удобный интерфейс с двумя основными вкладками
- **API интеграция**: поддержка OpenAI, Serper, ScrapingBee, HubSpot

## 🐳 Docker развертывание

Приложение полностью контейнеризовано и готово к развертыванию:

```bash
docker run -d --restart unless-stopped -p 80:8000 \
  -e OPENAI_API_KEY="ваш_ключ" \
  -e SERPER_API_KEY="ваш_ключ" \
  -e SCRAPINGBEE_API_KEY="ваш_ключ" \
  -e HUBSPOT_API_KEY="ваш_ключ" \
  --name company-canvas-prod \
  -v /srv/company-canvas/output:/app/output \
  -v /srv/company-canvas/sessions_metadata.json:/app/sessions_metadata.json \
  sergeykostichev/company-canvas-app:v13a
```

## ⚠️ Важные моменты развертывания

### Обязательные файлы и директории:
- `/srv/company-canvas/output/` - папка для результатов сессий
- `/srv/company-canvas/sessions_metadata.json` - файл метаданных сессий

### Создание перед запуском:
```bash
sudo mkdir -p /srv/company-canvas/output
echo '[]' > /srv/company-canvas/sessions_metadata.json
chmod 666 /srv/company-canvas/sessions_metadata.json
```

## 🔧 Решенные проблемы контейнеризации

В версии v13a исправлены критические проблемы валидации URL и выравнивания данных:
- ✅ Исправлена логика валидации URL - мертвые ссылки корректно отфильтровываются
- ✅ Исправлено выравнивание данных - описания компаний соответствуют правильным компаниям
- ✅ Исправлен порядок сохранения результатов HubSpot адаптера
- ✅ Улучшена валидация URL с обнаружением DNS ошибок

## 📚 Документация

- **[DEPLOY_INSTRUCTIONS.md](DEPLOY_INSTRUCTIONS.md)** - подробная инструкция по развертыванию
- **[DEPLOY_SUMMARY.md](DEPLOY_SUMMARY.md)** - краткая сводка и диагностика
- **[services/criteria_processor/README.md](services/criteria_processor/README.md)** - документация микросервиса анализа критериев

## 🏗️ Архитектура

- **Frontend**: React.js интерфейс
- **Backend**: FastAPI с асинхронной обработкой  
- **Criteria Processor**: отдельный микросервис для анализа критериев
- **Storage**: файловая система с JSON метаданными
- **APIs**: интеграция с внешними сервисами

## 🔍 Диагностика

### Быстрая проверка работоспособности:
```bash
# Статус контейнера
docker ps | grep company-canvas-prod

# Проверка API
curl http://localhost/api/sessions
curl http://localhost/api/criteria/sessions

# Логи
docker logs -f company-canvas-prod
```

### Если что-то не работает:
```bash
# Проверить монтированные файлы
docker exec company-canvas-prod ls -la /app/sessions_metadata.json

# Подробные логи с фильтрацией
docker logs -f company-canvas-prod | grep -E "(ERROR|criteria|sessions)"
```

## 📈 Версионирование

- **v13a** - текущая стабильная версия с исправленной валидацией URL и выравниванием данных
- **v13b** - следующая версия для новых функций

## 🔑 Переменные окружения

Необходимые API ключи:
- `OPENAI_API_KEY` - для генерации описаний и анализа
- `SERPER_API_KEY` - для поиска информации  
- `SCRAPINGBEE_API_KEY` - для извлечения контента сайтов
- `HUBSPOT_API_KEY` - для интеграции с HubSpot (опционально)

## 🤝 Поддержка

При возникновении проблем:
1. Проверьте логи контейнера
2. Убедитесь что все файлы и директории правильно смонтированы
3. Проверьте доступность API эндпоинтов
4. Обратитесь к разделу диагностики в документации 