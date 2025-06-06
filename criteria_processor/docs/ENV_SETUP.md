# Настройка переменных окружения

## Создание .env файла

Создайте файл `.env` в корневой папке проекта со следующим содержимым:

```env
# API Keys для системы верификации критериев
OPENAI_API_KEY=your_openai_api_key_here
SERPER_API_KEY=your_serper_api_key_here

# Опциональные ключи для будущих интеграций
HUBSPOT_API_KEY=your_hubspot_api_key_here
```

## Где получить API ключи

### OpenAI API Key
1. Зайдите на https://platform.openai.com/api-keys
2. Создайте новый API ключ
3. Скопируйте ключ и замените `your_openai_api_key_here`

### Serper API Key
1. Зайдите на https://serper.dev
2. Зарегистрируйтесь или войдите
3. Получите API ключ из дашборда
4. Скопируйте ключ и замените `your_serper_api_key_here`

### HubSpot API Key (опционально)
1. Войдите в HubSpot
2. Перейдите в Settings > Integrations > API key
3. Создайте новый ключ
4. Скопируйте ключ и замените `your_hubspot_api_key_here`

## Важно!

⚠️ **НЕ ДОБАВЛЯЙТЕ .env ФАЙЛ В GIT!**

Файл `.env` специально добавлен в `.gitignore` для защиты ваших API ключей.

## Тестирование настройки

После создания .env файла запустите:

```bash
python main.py
```

Если все настроено правильно, вы увидите:
```
✅ Configuration validated for criteria type: VM2
``` 