import re

def normalize_markdown_format(markdown_text):
    """
    Нормализует форматирование markdown-текста, удаляя лишние пустые строки 
    и обеспечивая согласованное форматирование списков.
    """
    if not markdown_text:
        return markdown_text
    
    print("Normalizing markdown format...")
    
    # Шаг 1: Заменяем множественные последовательности пустых строк на максимум одну пустую строку
    normalized = re.sub(r'\n{3,}', r'\n\n', markdown_text)
    
    # Шаг 2: Нормализуем последовательности списка с маркером "-"
    # Находим ситуации, когда между элементами списка с маркером "-" более одной пустой строки
    normalized = re.sub(r'(\n- [^\n]+)\n\n+(?=- )', r'\1\n', normalized)
    
    # Шаг 3: Делаем то же самое для элементов списка с маркером "*"
    normalized = re.sub(r'(\n\* [^\n]+)\n\n+(?=\* )', r'\1\n', normalized)
    
    # Шаг 4: Но сохраняем одну пустую строку между разделами
    # Обеспечиваем пустую строку между нумерованными заголовками
    normalized = re.sub(r'(\n\d+\.\s+[^\n]+)(?=\n\d+\.)', r'\1\n', normalized)
    
    # Шаг 5: Финальная очистка - снова заменяем множественные пустые строки на максимум одну,
    # так как предыдущие операции могли создать новые множественные пустые строки
    normalized = re.sub(r'\n{3,}', r'\n\n', normalized)
    
    print("Markdown format normalization complete")
    return normalized

# Тестовый текст из примера с двумя вариантами - плотным и разреженным
test_text1 = """1. **Basic Company Information:**
* **Company Name:** Your Job is Our Responsibility (Wdeftk Alina)
* **Founding Year:** 2012
* **Headquarters Location:** Al Jubail, Kingdom of Saudi Arabia
* **Founders:** No specific data found on founders
* **Ownership Background:** A non-profit organization officially registered under the name "Amwaj Al Jubail Foundation"
* **Official Homepage URL:** [https://www.wdeftksa.com](https://www.wdeftksa.com)

2. **Products and Technology:**
* **Core Products & Services:**
- **Your Job is Our Responsibility App:** A dedicated app providing job news in the Kingdom of Saudi Arabia, including military, government, and corporate jobs, as well as acceptance results and training courses.
* **Underlying Technologies:** No specific data found on underlying technologies"""

test_text2 = """**1. Basic Company Information:**


- **Company Name:** Docker, Inc.


- **Founding Year:** Docker, Inc. was originally founded as dotCloud in 2008.


- **Headquarters Location:** 3790 El Camino Real #1052, Palo Alto, CA 94306, United States.


- **Founders:** Kamel Founadi, Solomon Hykes, and Sebastien Pahl.


- **Ownership Background:** Docker, Inc. is a privately held company.


- **Official Homepage URL:** https://www.docker.com/

**2. Products and Technology:**


- **Core Products & Services:**

- **Docker Desktop:** A GUI application for Windows, Linux, and macOS that enables developers to build, share, and run containerized applications."""

test_text3 = """1. **Basic Company Information:**

- **Company Name:** LinkedIn China (领英中国)

- **Founding Year:** 2014

- **Headquarters Location:** Beijing, China (中国北京市)

- **Founders:** LinkedIn China was established by LinkedIn when it entered the Chinese market in 2014; specific founder information has not been disclosed.

- **Ownership Background:** LinkedIn China is a subsidiary of LinkedIn. LinkedIn was acquired by Microsoft for $31.2 billion in 2016, becoming a wholly-owned subsidiary.

- **Official Homepage URL:** https://www.linkedin.cn/

2. **Products and Technology:**

- **Core Products & Services:**

- **InCareer (领英职场):** Launched in December 2021, a job-seeking platform focused on connecting career opportunities.

- **Talent Solutions:** Provides services for talent acquisition, employer branding, and more for businesses.

- **Marketing Solutions:** Helps businesses with brand promotion and marketing."""

# Нормализуем текст
normalized_text1 = normalize_markdown_format(test_text1)
normalized_text2 = normalize_markdown_format(test_text2)
normalized_text3 = normalize_markdown_format(test_text3)

# Выводим результат для первого примера (плотный формат)
print("\n--- ORIGINAL TEXT 1 (плотный формат) ---")
print(test_text1)
print("\n--- NORMALIZED TEXT 1 ---")
print(normalized_text1)

# Выводим результат для второго примера (слишком разреженный формат)
print("\n--- ORIGINAL TEXT 2 (слишком разреженный формат) ---")
print(test_text2)
print("\n--- NORMALIZED TEXT 2 ---")
print(normalized_text2)

# Выводим результат для третьего примера (нормальный формат с пустыми строками)
print("\n--- ORIGINAL TEXT 3 (нормальный формат с пустыми строками) ---")
print(test_text3)
print("\n--- NORMALIZED TEXT 3 ---")
print(normalized_text3) 