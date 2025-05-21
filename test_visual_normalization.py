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

def visualize_newlines(text):
    """
    Заменяет символы перевода строки на [↵], чтобы сделать их видимыми
    """
    return text.replace('\n', '[↵]\n')

# Тестовый пример с очень разреженным текстом
test_text = """**1. Basic Company Information:**



- **Company Name:** Docker, Inc.



- **Founding Year:** 2008



- **Official Homepage URL:** https://www.docker.com/


**2. Products and Technology:**


- **Core Products & Services:**


- **Docker Desktop:** A GUI application"""

# Выполняем нормализацию
normalized_text = normalize_markdown_format(test_text)

# Сохраняем результаты с визуализацией переводов строк
with open("visual_normalization_results.txt", "w", encoding="utf-8") as f:
    f.write("=== ОРИГИНАЛЬНЫЙ ТЕКСТ (с видимыми переводами строк) ===\n\n")
    f.write(visualize_newlines(test_text))
    f.write("\n\n")
    f.write("=== НОРМАЛИЗОВАННЫЙ ТЕКСТ (с видимыми переводами строк) ===\n\n")
    f.write(visualize_newlines(normalized_text))
    
print("Визуализация выполнена, результаты в файле 'visual_normalization_results.txt'")

# Выведем также на консоль для удобства
print("\n=== ОРИГИНАЛЬНЫЙ ТЕКСТ ===")
print(test_text)
print("\n=== НОРМАЛИЗОВАННЫЙ ТЕКСТ ===")
print(normalized_text)

# Дополнительно выведем количество строк до и после нормализации
original_lines = test_text.count('\n')
normalized_lines = normalized_text.count('\n')
print(f"\nКоличество строк в оригинале: {original_lines}")
print(f"Количество строк после нормализации: {normalized_lines}")
print(f"Сокращено строк: {original_lines - normalized_lines}") 