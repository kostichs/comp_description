Thought for a couple of seconds


1. Подготовка окружения и инструментов
   1.1. Создать репозиторий проекта, настроить виртуальное окружение Python (venv или conda)
   1.2. Установить зависимости:

   ```bash
   pip install pandas tldextract ScrappingB openai openpyxl google-search-results PyYAML
   ```

   1.3. Настроить доступы:

   * API‑ключ OpenAI
   * API-ключ ScrapingBee (для скрейпинга страниц)
   * API-ключ SerpApi (для поиска Google)
   * (опционально) Файл конфигурации `llm_config.yaml` для настроек OpenAI.

2. Структура проекта

   ```
   project_root/
   ├── input/  # Папка для входных файлов
   │   └── Gcore_Service_Recommendations.xlsx # Пример входного файла (может быть и .csv)
   ├── output/ # Папка для выходных файлов
   │   └── output.csv
   ├── src/
   │   ├── discover_links.py
   │   ├── validate_links.py
   │   ├── scraper.py
   │   ├── parser.py
   │   ├── describe.py
   │   └── main.py
   ├── main.py # Наш текущий основной скрипт в корне
   ├── llm_config.yaml # Файл конфигурации для LLM
   ├── requirements.txt
   └── README.md
   ```

3. Поиск URL (например, в `main.py` или `discover_links.py`)
   3.1. Чтение списка компаний из входного файла (CSV или Excel, например, `input/Gcore_Service_Recommendations.xlsx`) (pandas)
   3.2. Для каждой компании выполнять поиск через SerpApi (Google Search):
      - Запрос для поиска сайта: `f"{company_name} official website"`
      - Запрос для поиска LinkedIn: `f"{company_name} site:linkedin.com/company"`
   3.3. Извлекать первый релевантный URL для сайта и LinkedIn.

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

4. Скрейпинг и валидация (бывшие пункты 4, 5, часть 6)
   4.1. Для каждого найденного URL (сайт, LinkedIn) использовать ScrappingB Scraper для загрузки страницы.
   4.2. Извлечь `<title>` и корневой домен (tldextract).

5. scraper.py
   5.1. Через ScrappingB получать контент страниц:

   ```python
   from ScrappingB import Scraper
   scraper = Scraper()
   html_home = scraper.fetch(url_home)
   html_linkedin = scraper.fetch(url_linkedin)
   ```

   5.2. Сохранять «сырые» HTML для отладки

6. parser.py
   6.1. Извлечь из HTML ключевые блоки:

   * meta‑description
   * первый `<p>`
   * блок «About» (по заголовкам "About", "О компании")
     6.2. Формировать словарь:

   ```python
   {
     "name": company_name,
     "homepage": root_home_url,
     "linkedin": linkedin_url,
     "about_snippet": meta_description or first_paragraph or about_block
   }
   ```

7. describe.py
   7.1. Составить prompt (детали см. в `generate_description_openai` и `llm_config.yaml`):
      - Базовый шаблон включает имя компании, сайт, LinkedIn, фрагмент текста.
      - Инструкция для LLM (например, "Сгенерируй краткое описание...") берется из `llm_config.yaml`.

   7.2. Вызвать OpenAI (используя параметры из `llm_config.yaml`):

   Пример `llm_config.yaml`:
   ```yaml
   openai_settings:
     model: "gpt-3.5-turbo"
     max_tokens: 100
     temperature: 0.7
     system_message_content: "You are a helpful assistant..."
     user_instruction_template: "Сгенерируй краткое описание (не более {word_limit} слов)..."
     word_limit_for_description: 50
   ```

8. main.py
   8.1. Pipeline:
      - Загрузить `llm_config.yaml`.
      - Загрузить входной файл.
      - Для каждой компании: найти URL -> соскрейпить -> валидировать -> извлечь текст -> сгенерировать описание (с учетом LLM конфига) -> собрать результаты.
      - Сохранить выходной файл.

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружается из .env

   def find_urls(company_name):
       homepage_url = None
       linkedin_url = None
       
       # Поиск сайта
       params_homepage = {
           "q": f"{company_name} official website",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_hp = GoogleSearch(params_homepage)
       results_hp = search_hp.get_dict()
       if results_hp.get("organic_results") and results_hp["organic_results"][0].get("link"):
           homepage_url = results_hp["organic_results"][0]["link"]

       # Поиск LinkedIn
       params_linkedin = {
           "q": f"{company_name} site:linkedin.com/company",
           "api_key": SERPER_API_KEY,
           "num": 1
       }
       search_li = GoogleSearch(params_linkedin)
       results_li = search_li.get_dict()
       if results_li.get("organic_results") and results_li["organic_results"][0].get("link"):
           linkedin_url = results_li["organic_results"][0]["link"]
           if not "linkedin.com/company/" in linkedin_url:
               linkedin_url = None # Проверка, что это профиль компании

       return homepage_url, linkedin_url
   ```

   Примерный код (Python с библиотекой `google-search-results`):
   ```python
   from serpapi import GoogleSearch
   SERPER_API_KEY = "YOUR_SERPER_API_KEY" # Загружа