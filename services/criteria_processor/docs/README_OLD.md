Set up file names in Config
Run main
To reformat the results into the table run json_extractor


# Система анализа критериев компаний

## Структура проекта

```
202505_Criteria_Mikhail/
├── criteria/              # 📋 Папка для файлов критериев
│   ├── Criteria_VM2.csv   # Критерии для VM продукта
│   └── ...                # Другие файлы критериев
├── input/                 # 📊 Входные данные
│   └── results_250.csv    # Данные компаний
├── output/                # 💾 Результаты анализа
├── logs/                  # 📝 Логи работы системы
├── main.py               # 🚀 Основной модуль
├── config.py             # ⚙️ Конфигурация
├── data_utils.py         # 📊 Работа с данными
├── criteria_checkers.py  # 🔍 Проверка критериев
├── scoring_system.py     # 📊 Система скоринга
├── json_formatter.py     # 📝 Форматирование результатов
├── logger_config.py      # 📝 Настройка логирования
└── .env                  # 🔐 API ключи
```

## Автоматическая загрузка критериев

### Новая система работы с критериями

Система автоматически загружает **все файлы критериев** из папки `criteria/`:

1. **Размещение файлов**: Поместите все CSV файлы с критериями в папку `criteria/`
2. **Автоматическое обнаружение**: При запуске система найдет и загрузит все `.csv` файлы
3. **Объединение данных**: Все критерии объединяются в единый набор данных
4. **Умная фильтрация**: 
   - 🌐 **General критерии** собираются из **ВСЕХ файлов** и применяются ко всем компаниям
   - 🎯 **Остальные критерии** фильтруются по конкретному продукту

### Логика работы с критериями

#### General критерии (глобальные)
- Собираются из **всех файлов критериев** в папке `criteria/`
- Применяются ко **всем компаниям** независимо от продукта
- Если в одном файле есть General критерий, а в другом нет - он все равно применяется ко всем

#### Продуктовые критерии
- **Qualification** - фильтруются по продукту
- **Mandatory** - фильтруются по продукту  
- **NTH** - фильтруются по продукту

### Формат файлов критериев

Каждый файл критериев должен содержать колонки:
- `Product` - название продукта (VM, CDN, Fintech, и т.д.)
- `Target Audience` - целевая аудитория
- `Criteria Type` - тип критерия (**General**, Qualification, Mandatory, NTH)
- `Criteria` - текст критерия
- `Place` - где искать информацию
- `Search Query` - поисковый запрос
- `Signals` - сигналы для проверки

**Важно для General критериев:**
- `Product` = "General" (всегда)
- `Target Audience` = "" (пустое поле)

### Добавление новых критериев

1. Создайте новый CSV файл с критериями
2. Поместите его в папку `criteria/`
3. Запустите систему - новые критерии будут автоматически загружены
4. General критерии из нового файла автоматически применятся ко всем компаниям

## Настройка и запуск

### 1. Настройка API ключей

Создайте файл `.env`:
```env
OPENAI_API_KEY=your_openai_key_here
SERPER_API_KEY=your_serper_key_here
```

### 2. Настройка продукта

В файле `config.py` установите:
```python
CRITERIA_TYPE = "VM2"  # или другой продукт
```

### 3. Запуск анализа

```bash
python main.py
```

## Алгоритм работы

1. **Автоматическая загрузка** всех файлов критериев из папки `criteria/`
2. **Сбор General критериев** из всех файлов - применяются ко всем компаниям
3. **Фильтрация по продукту** остальных типов критериев
4. **Квалификационные вопросы** - определение подходящих аудиторий
5. **Обязательные критерии** - проверка через Serper.dev
6. **Nice-to-Have критерии** - дополнительный скоринг
7. **Генерация результатов** в JSON и CSV форматах

## Структура результатов

### JSON результаты
```json
{
  "Company_Name": "Название компании",
  "Global_Criteria_Status": "Passed/Failed",
  "Qualified_Audiences": ["Online Gaming", "Fintech"],
  "Qualification_Online Gaming": "Yes",
  "Mandatory_Online Gaming_Website": "Passed",
  "NTH_Online Gaming_Score": 0.75,
  "Final_Status": "Qualified"
}
```

### CSV результаты
Плоская структура для удобного анализа в Excel/Google Sheets.

## Логирование

Все операции записываются в файлы логов:
- Расположение: папка `logs/`
- Формат имени: `analysis_YYYYMMDD_HHMMSS.log`
- Уровни логирования: INFO, ERROR, DEBUG

## Тестирование

Запустите тест структуры:
```bash
python test_structure.py
```

Проверяет:
- ✅ Импорты модулей
- ✅ Наличие файлов данных
- ✅ Автоматическую загрузку критериев
- ✅ Систему скоринга

## Преимущества новой структуры

- 🔄 **Автоматическая загрузка** всех файлов критериев
- 📁 **Централизованное управление** критериями в одной папке
- 🎯 **Гибкость** - добавляйте новые файлы без изменения кода
- 📊 **Масштабируемость** - поддержка множества продуктов
- 🔍 **Простота** - не нужно настраивать пути к файлам

## Отладка

Для детальной отладки установите в `config.py`:
```python
DEBUG_SERPER = True
DEBUG_OPENAI = True
DEBUG_SCORING = True
```


# Criteria Evaluation System

## 📘 Overview

This project evaluates companies against a set of business criteria. It processes company data, applies various criteria checks, and generates comprehensive reports in CSV format.

---

## 🏗️ Project Structure

The system is built with a modular architecture for maintainability and scalability:

### 📄 Core Files

#### `main.py`
The entry point of the application that orchestrates the entire evaluation process:
- Loads configuration and validates it
- Processes companies one by one
- Applies different criteria checks in sequence
- Collects and saves results

#### `config.py`
Manages configuration settings across the application:
- Defines file paths for inputs and outputs
- Sets processing limits and parameters
- Handles environment variables and API keys
- Validates that all required files exist

#### `data_utils.py`
Handles all data loading and saving operations:
- Loads company data and criteria from CSV files
- Processes and transforms the data into usable formats
- Saves the final evaluation results to CSV

#### `criteria_checkers.py`
Contains all the functions for evaluating companies against different types of criteria:
- General criteria checks
- Qualification questions
- Mandatory criteria
- Nice-to-Have (NTH) criteria

#### `serper_utils.py`
Utility functions for gathering information from search engines:
- Makes API calls to serper.dev for Google search results
- Processes search results to enhance criteria evaluation
- Provides functions to format queries and extract website information

#### `models.py`
Defines data structures and models used throughout the application.

---

## 🧠 Evaluation Process

The system follows a structured evaluation process:

1. **General Criteria Check**: Basic eligibility criteria that all companies must pass
2. **Qualification Questions**: Determines which audience segments a company qualifies for
3. **Audience-Specific Evaluation**:
   - **Mandatory Criteria**: Must-have requirements for each qualified audience
   - **NTH (Nice-to-Have) Criteria**: Additional beneficial characteristics

Each criteria is evaluated using the appropriate information source:
- **gen_descr**: Uses the company's general description
- **website**: Performs a Google search via serper.dev using the "Search Query" from the criteria file, then evaluates the results

Each company is processed independently, with comprehensive results saved to the output file.

---

## 🛠️ How to Run

```bash
python main.py
```

The program will:
1. Load and validate the configuration
2. Process each company against the criteria
3. Save the results to a timestamped CSV file in the output directory

---

## 📝 Environment Setup

### API Keys
The system requires the following API keys in your `.env` file:
- `OPENAI_API_KEY`: For OpenAI GPT access
- `SERPER_API_KEY`: For Google search via serper.dev

### Requirements
- Python 3.10+
- Required packages:
  ```bash
  pip install -r requirements.txt
  ```

---

## 📂 Input Files

### Company Data CSV
Contains the companies to be evaluated with the following columns:
- `Company_Name`: Name of the company
- `Description`: Detailed description of the company
- `Official_Website`: Company's website URL (used for website-based criteria)

### Criteria CSV
Contains the evaluation criteria with the following columns:
- `Product`: Product category
- `Target Audience`: Audience segment
- `Criteria Type`: Type of criteria (General, Qualification, Mandatory, NTH)
- `Criteria`: The actual criterion text
- `Place`: Source of information for evaluation ("gen_descr" or "website")
- `Search Query`: Query template to use for website-based criteria (when Place = "website")
- `Signals`: Signals to look for in the results (informational only)

---

## 📊 Output

The system generates a CSV file with detailed evaluation results for each company, including:
- Basic company information
- General criteria status
- Qualification status for each audience
- Mandatory criteria results with source information
- NTH criteria results with source information

The output file is saved with a timestamp to track different evaluation runs.

---

## 📝 CSV Format Requirements

**Important Update:** The system now uses comma (`,`) as the CSV delimiter instead of semicolon (`;`). 

- All input CSV files should use comma (`,`) as the delimiter
- Fields containing commas will be automatically quoted
- UTF-8 encoding is preferred, but the system will attempt to handle various encodings (utf-8, latin1, cp1251, iso-8859-1)
- All output files are generated with comma delimiters and proper quoting

⚠️ **Note:** Legacy files with semicolon delimiters have been moved to the `OLD_CODE` directory with a `_semicolon` suffix.

---

## ✅ Requirements

- Python 3.10+
- Required packages:
  ```bash
  pip install pandas python-dotenv
  ```
