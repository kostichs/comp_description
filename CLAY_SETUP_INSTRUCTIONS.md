# Инструкция по настройке Clay HTTP API

## Проблема в вашей текущей настройке

Из логов видно что Clay отправляет **шаблонные переменные** вместо реальных данных:
```json
{
  "domain": "${Domain}",
  "companyName": "${Enrich Company?.name}"
}
```

Это означает что в настройке Clay вы используете неправильный формат ссылок на колонки.

## Правильная настройка в Clay

### 1. HTTP API Configuration

**Method:** `POST`  
**URL:** `https://aidoc-trigger.loca.lt/process_company`  
**Content-Type:** `application/json`

### 2. Request Body (JSON)

**НЕ ИСПОЛЬЗУЙТЕ шаблонный синтаксис ${...}**

**Правильный формат:**
```json
{
  "companyName": "/Company Name",
  "domain": "/Domain"
}
```

**Где:**
- `/Company Name` - точное название вашей колонки с названиями компаний
- `/Domain` - точное название вашей колонки с доменами

### 3. Пример правильной настройки

Если ваши колонки называются:
- `Enrich Company?.name` 
- `Domain`

То JSON должен быть:
```json
{
  "companyName": "/Enrich Company?.name",
  "domain": "/Domain"
}
```

### 4. Fields to return в Clay (ОБНОВЛЕНО - плоская структура)

API теперь возвращает все поля на верхнем уровне. Укажите эти поля для извлечения:

**Основные поля:**
- `success` - статус обработки (true/false)
- `processed_description` - обработанное описание компании
- `confidence_score` - уровень уверенности (0.95)
- `word_count` - количество слов в описании

**Дополнительные поля:**
- `input_company_name` - исходное название компании
- `input_domain` - исходный домен
- `processing_timestamp` - время обработки
- `industry_classification` - классификация отрасли
- `enhancement_applied` - применено ли улучшение (true/false)

### 5. Создание новых колонок в Clay

Создайте эти колонки и привяжите к полям API:

1. **Processed Description** → `processed_description`
2. **Confidence Score** → `confidence_score`  
3. **Word Count** → `word_count`
4. **Processing Success** → `success`
5. **Company Name** → `input_company_name`
6. **Domain Used** → `input_domain`
7. **Processing Time** → `processing_timestamp`
8. **Industry** → `industry_classification`

## Проверка правильности настройки

После правильной настройки в логах должны появиться реальные данные вместо шаблонных переменных:

**Правильно:**
```json
{
  "companyName": "Tesla",
  "domain": "tesla.com"
}
```

**Неправильно (ваша предыдущая настройка):**
```json
{
  "domain": "${Domain}",
  "companyName": "${Enrich Company?.name}"
}
```

## Новая структура ответа API

API теперь возвращает:
```json
{
  "success": true,
  "processed_description": "Tesla - инновационная компания...",
  "confidence_score": 0.95,
  "word_count": 22,
  "input_company_name": "Tesla",
  "input_domain": "tesla.com",
  "processing_timestamp": "2025-05-29T19:00:37.866320",
  "industry_classification": "Technology",
  "enhancement_applied": true,
  "error": null
}
```

## Устранение ошибок

Если видите в логах:
- `CLAY CONFIG ERROR: Domain contains template variable`
- `CLAY CONFIG ERROR: CompanyName contains template variable`

Значит нужно исправить настройку JSON body в Clay, используя правильный формат ссылок на колонки `/ColumnName` вместо `${ColumnName}`.

## Тестирование

1. Исправьте настройки в Clay согласно этой инструкции
2. Обновите "Fields to return" на новые поля без вложенности
3. Запустите обработку нескольких строк в Clay
4. Проверьте что новые колонки заполняются данными
5. В логах должны появиться реальные названия компаний и доменов 