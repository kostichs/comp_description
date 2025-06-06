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
   docker tag company-canvas-app sergeykostichev/company-canvas-app:v07
   docker push sergeykostichev/company-canvas-app:v07
   ```

### На виртуальной машине:

1. **Автоматическое развертывание:**
   ```bash
   chmod +x deploy_vm.sh
   ./deploy_vm.sh v07
   ```

2. **Или вручную:**
   ```bash
   docker stop company-canvas-prod
   docker rm company-canvas-prod
   docker pull sergeykostichev/company-canvas-app:v07
   
   docker run -d --restart unless-stopped -p 80:8000 \
     -e OPENAI_API_KEY="ваш_ключ" \
     -e SERPER_API_KEY="ваш_ключ" \
     -e SCRAPINGBEE_API_KEY="ваш_ключ" \
     -e HUBSPOT_API_KEY="ваш_ключ" \
     --name company-canvas-prod \
     -v /srv/company-canvas/output:/app/output \
     sergeykostichev/company-canvas-app:v07
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

- **v06**: предыдущая версия  
- **v07**: текущая версия с исправлениями соединений
- **v08**: следующая версия

## Важные изменения в v07

1. **Семафор для валидации URL**: ограничение до 5 одновременных проверок
2. **Ограничения соединений**: 10 общих, 2 на хост для этапа валидации  
3. **Сохранен batch processing**: основной pipeline работает с обычными ограничениями (50/10)
4. **Стабильность**: исправлена ошибка "too many file descriptors" на Windows

## Структура файлов развертывания

- `DEPLOY_INSTRUCTIONS.md` - подробная инструкция
- `deploy.ps1` - PowerShell скрипт для Windows
- `deploy_vm.sh` - Bash скрипт для VM
- `DEPLOY_SUMMARY.md` - эта сводка
- `docs/DEPLOYMENT_GUIDE.md` - полная документация 