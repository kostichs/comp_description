import re

def normalize_markdown_format(markdown_text):
    """
    Нормализует форматирование markdown-текста, удаляя лишние пустые строки.
    """
    if not markdown_text:
        return markdown_text
    
    # Обязательно заменяем слишком большое количество пустых строк (более двух подряд)
    normalized = re.sub(r'\n{3,}', r'\n\n', markdown_text)
    
    # Удаляем пустые строки между последовательными элементами списка с тем же маркером,
    # но только если их больше одной
    normalized = re.sub(r'(\n- [^\n]+)\n\n+(?=- )', r'\1\n', normalized)
    normalized = re.sub(r'(\n\* [^\n]+)\n\n+(?=\* )', r'\1\n', normalized)
    
    # Заменяем все оставшиеся последовательности из трех и более пустых строк 
    # на максимум одну пустую строку
    normalized = re.sub(r'\n{3,}', r'\n\n', normalized)
    
    return normalized

# Тестовые примеры
test_cases = {
    "case1_tight": """1. **Basic Company Information:**
* **Company Name:** Your Job is Our Responsibility (Wdeftk Alina)
* **Founding Year:** 2012
* **Headquarters Location:** Al Jubail, Saudi Arabia
* **Official Homepage URL:** https://www.wdeftksa.com

2. **Products and Technology:**
* **Core Products & Services:**
- **App:** Job search app
* **Underlying Technologies:** No data""",

    "case2_too_spaced": """**1. Basic Company Information:**


- **Company Name:** Docker, Inc.


- **Founding Year:** 2008


- **Official Homepage URL:** https://www.docker.com/

**2. Products and Technology:**


- **Core Products & Services:**

- **Docker Desktop:** A GUI application""",

    "case3_normal": """1. **Basic Company Information:**

- **Company Name:** LinkedIn China (领英中国)

- **Founding Year:** 2014

- **Headquarters Location:** Beijing, China

- **Official Homepage URL:** https://www.linkedin.cn/

2. **Products and Technology:**

- **Core Products & Services:**

- **InCareer:** A job platform

- **Talent Solutions:** HR services"""
}

# Запускаем тесты и сохраняем результаты в файл
with open("normalization_test_results.txt", "w", encoding="utf-8") as f:
    for case_name, test_text in test_cases.items():
        f.write(f"\n\n{'='*50}\n")
        f.write(f"TEST CASE: {case_name}\n")
        f.write(f"{'='*50}\n\n")
        
        f.write("--- ORIGINAL TEXT ---\n")
        f.write(test_text)
        f.write("\n\n")
        
        normalized = normalize_markdown_format(test_text)
        
        f.write("--- NORMALIZED TEXT ---\n")
        f.write(normalized)
        f.write("\n\n")

print("Тесты выполнены, результаты сохранены в файл 'normalization_test_results.txt'") 