# Краткая сводка по развертыванию Company Canvas

## Подготовка к развертыванию

**Готово к развертыванию:**
✅ Dockerfile актуален
✅ Requirements.txt проверен  
✅ Исправления соединений применены
✅ Документация и скрипты созданы

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
   docker tag company-canvas-app sergeykostichev/company-canvas-app:v08
   docker push sergeykostichev/company-canvas-app:v08
   ```

### На виртуальной машине:

1. **Автоматическое развертывание:**
   ```bash
   chmod +x deploy_vm.sh
   ./deploy_vm.sh v08
   ```

2. **Или вручную:**
   ```bash
   docker stop company-canvas-prod
   docker rm company-canvas-prod
   docker pull sergeykostichev/company-canvas-app:v08
   
   docker run -d --restart unless-stopped -p 80:8000 \
     -e OPENAI_API_KEY="ваш_ключ" \
     -e SERPER_API_KEY="ваш_ключ" \
     -e SCRAPINGBEE_API_KEY="ваш_ключ" \
     -e HUBSPOT_API_KEY="ваш_ключ" \
     --name company-canvas-prod \
     -v /srv/company-canvas/output:/app/output \
     sergeykostichev/company-canvas-app:v08
   ```

## Проверка работы

```bash
# Статус контейнера
docker ps

# Логи
docker logs -f company-canvas-prod

# Веб-интерфейс
# http://IP_адрес_вашей_VM
```

## Версии

- **v07**: предыдущая версия с исправлениями соединений
- **v08**: текущая версия с criteria processor микросервисом
- **v09**: следующая версия

## Важные изменения в v08

1. **Criteria Processor микросервис**: полная интеграция анализа критериев
2. **Async параллельная обработка**: 5-8x ускорение анализа компаний
3. **Международные кодировки**: поддержка UTF-8, Cyrillic, специальных символов
4. **Чистая JSON структура**: только criteria_text и result без лишних полей
5. **Сохранение форматирования**: переносы строк и параграфы в описаниях

## Структура файлов развертывания

- `DEPLOY_INSTRUCTIONS.md` - подробная инструкция
- `deploy.ps1` - PowerShell скрипт для Windows
- `deploy_vm.sh` - Bash скрипт для VM
- `DEPLOY_SUMMARY.md` - эта сводка
- `docs/DEPLOYMENT_GUIDE.md` - полная документация 