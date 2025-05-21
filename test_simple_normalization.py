import re

def normalize_markdown_format(markdown_text):
    """
    Нормализует форматирование markdown-текста для обеспечения
    согласованного формата, но не добавляет лишних пустых строк.
    """
    if not markdown_text:
        return markdown_text
    
    print("Normalizing markdown format...")
    
    # Предварительная нормализация: заменяем множественные пустые строки на одинарные
    normalized_text = re.sub(r'\n{3,}', r'\n\n', markdown_text)
    
    # Простая коррекция: добавляем пустую строку между нумерованными заголовками и последующим текстом,
    # если ее еще нет
    normalized_text = re.sub(r'(\n\d+\.\s+\*\*[^*]+\*\*:)(\n)(?=[*-])', r'\1\n\2', normalized_text)
    
    # Обеспечиваем пустую строку между нумерованными заголовками, если ее еще нет
    normalized_text = re.sub(r'(\n\d+\.\s+\*\*[^*]+\*\*:)(\n)(?=\d+\.)', r'\1\n\2', normalized_text)
    
    print("Markdown format normalization complete")
    return normalized_text

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

# Нормализуем текст
normalized_text1 = normalize_markdown_format(test_text1)
normalized_text2 = normalize_markdown_format(test_text2)

# Выводим результат для первого примера
print("\n--- ORIGINAL TEXT 1 (плотный формат) ---")
print(test_text1)
print("\n--- NORMALIZED TEXT 1 ---")
print(normalized_text1)

# Выводим результат для второго примера
print("\n--- ORIGINAL TEXT 2 (разреженный формат) ---")
print(test_text2)
print("\n--- NORMALIZED TEXT 2 ---")
print(normalized_text2) 