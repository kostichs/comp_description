import re

def normalize_markdown_format(markdown_text):
    """
    Нормализует форматирование markdown-текста для обеспечения
    согласованного формата с пустыми строками между элементами списка.
    """
    if not markdown_text:
        return markdown_text
    
    print("Normalizing markdown format...")
    
    # Шаг 1: Нормализация заголовков - обеспечение пустой строки перед каждым заголовком,
    # кроме случаев, когда заголовок идет в начале текста
    header_normalized = re.sub(r'(?<!\n\n)(\n#+\s+)', r'\n\n\1', markdown_text)
    
    # Шаг 2: Нормализация элементов списка - добавление пустой строки между элементами списка,
    # но сохранение вложенных списков без пустых строк
    list_items_pattern = r'(\n- [^\n]+)(?=\n(?!- ))'
    list_normalized = re.sub(list_items_pattern, r'\1\n', header_normalized)
    
    # Шаг 3: Обеспечение пустой строки между разделами (основными заголовками и списками)
    section_pattern = r'(\n#+\s+[^\n]+\n)(?=- )'
    section_normalized = re.sub(section_pattern, r'\1\n', list_normalized)
    
    # Шаг 4: Удаление слишком большого количества пустых строк (более двух подряд)
    extra_newlines_removed = re.sub(r'\n{3,}', r'\n\n', section_normalized)
    
    # Шаг 5: Обеспечение пустой строки перед элементами списка верхнего уровня
    top_level_list_pattern = r'(?<!\n\n)(\n- )'
    final_text = re.sub(top_level_list_pattern, r'\n\n- ', extra_newlines_removed)
    
    print("Markdown format normalization complete")
    return final_text

# Тестовый текст из примера
test_text = """1. **Basic Company Information:**
- **Company Name:** Docker, Inc.
- **Founding Year:** 2008
- **Headquarters Location:** Palo Alto, California, USA
- **Founders:** Kamel Founadi, Solomon Hykes, Sebastien Pahl
- **Ownership Background:** Docker, Inc. is a privately held company.
- **Official Homepage URL:** https://www.docker.com/
2. **Products and Technology:**
- **Core Products & Services:**
- **Docker Desktop:** A GUI application for Windows, Linux, and macOS that enables developers to build, share, and run containerized applications.
- **Docker Hub:** A cloud-based repository service that allows developers to publish, share, and collaborate on container images.
- **Docker Engine:** An open-source containerization technology for building and containerizing applications."""

# Нормализуем текст
normalized_text = normalize_markdown_format(test_text)

# Выводим результат
print("\n--- ORIGINAL TEXT ---")
print(test_text)
print("\n--- NORMALIZED TEXT ---")
print(normalized_text) 