# 📊 Мониторинг Clay Integration API

## 🚀 Запуск сервера для тестирования

Для тестирования в Clay запустите сервер с логированием:

```bash
python clay_server_with_logs.py
```

## 👀 Что вы увидите в терминале

### При запуске сервера:
```
🚀 Запуск Clay Integration API сервера...
📊 Логи будут сохранены в файл: clay_requests.log
🌐 URL для Clay: https://aidoc-trigger.loca.lt/process_company
============================================================
```

### При каждом запросе от Clay:
```
🌐 ВХОДЯЩИЙ ЗАПРОС: POST /process_company
📍 IP клиента: 127.0.0.1
📋 Headers: {'host': 'aidoc-trigger.loca.lt', 'content-type': 'application/json', ...}
📄 JSON Body: {
  "company.name": "Tesla",
  "domain": "tesla.com"
}
🏢 ОБРАБОТКА КОМПАНИИ
   Название: Tesla
   Домен: tesla.com
   Описание: Нет...
   Отрасль: None
🔄 Запуск обработки описания...
🎨 Улучшение описания для Tesla
📝 Создано новое описание (исходное было пустое)
✨ Описание обработано: 156 символов
✅ УСПЕШНАЯ ОБРАБОТКА для Tesla
⏱️ Время обработки: 0.025 секунд
✅ Ответ: 200
============================================================
```

## 📝 Файл логов

Все запросы также сохраняются в файл `clay_requests.log` для последующего анализа.

## ❌ Возможные ошибки и их решения

### 1. Ошибка валидации
```
❌ ОШИБКА ВАЛИДАЦИИ: Требуется указать либо company.name, либо domain
```
**Решение:** Проверьте настройки в Clay - должны быть заполнены поля company.name или domain

### 2. Ошибка подключения
```
❌ Не удается подключиться к https://aidoc-trigger.loca.lt
```
**Решение:** Перезапустите localtunnel:
```bash
lt --port 5000 --subdomain aidoc-trigger
```

### 3. Внутренняя ошибка сервера
```
❌ ВНУТРЕННЯЯ ОШИБКА: [описание ошибки]
```
**Решение:** Смотрите детали ошибки в логах и корректируйте код

## 🔧 Настройки в Clay

**URL:** `https://aidoc-trigger.loca.lt/process_company`  
**Method:** POST  
**Content-Type:** application/json

**JSON Body:**
```json
{
  "company.name": "/enrich_company_name",
  "domain": "/domain"
}
```

**Fields to return:**
- `processed_description`
- `enriched_data.confidence_score`
- `enriched_data.word_count`
- `success` 