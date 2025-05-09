# Company Information Processor

Веб-приложение для обработки информации о компаниях с использованием LLM и веб-скрапинга.

## Требования

- Python 3.8+
- pip (менеджер пакетов Python)

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd company-description
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` в корневой директории проекта и добавьте необходимые переменные окружения:
```
OPENAI_API_KEY=your_openai_api_key
SCRAPINGBEE_API_KEY=your_scrapingbee_api_key
```

## Запуск

1. Запустите сервер:
```bash
python server.py
```

2. Откройте веб-браузер и перейдите по адресу:
```
http://localhost:5000
```

## Использование

1. Нажмите кнопку "New Session" для создания новой сессии
2. Загрузите входной файл (CSV или Excel) с названиями компаний
3. При необходимости добавьте дополнительный контекст
4. Нажмите "Create Session" для создания сессии
5. Нажмите "Start Processing" для начала обработки
6. Дождитесь завершения обработки
7. Просмотрите результаты в таблице
8. При необходимости скачайте результаты или просмотрите логи

## Структура проекта

```
company-description/
├── frontend/
│   ├── index.html
│   └── app.js
├── src/
│   ├── pipeline.py
│   ├── data_io.py
│   └── external_apis/
│       ├── serper_client.py
│       └── ...
├── input/
├── output/
│   └── sessions/
├── server.py
├── requirements.txt
└── README.md
```

## Лицензия

MIT

Output format:
- Company name
- Homepage link
- Linkedin link
- Description
- `timestamp`: Дата обработки записи в формате ГГГГ-ММ-ДД.