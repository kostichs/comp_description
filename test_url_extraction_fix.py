import asyncio
import sys
import os

# Добавляем корневую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.pipeline.core import _extract_homepage_from_report_text_async

async def test_url_extraction():
    """Тестирует извлечение URL из markdown текста LLM"""
    
    # Тестовый текст с markdown ссылкой как в примере DCSG TECH
    test_text = """
**1. Basic Company Information:**

- **Company Name:** DCSG TECH CO. L.L.C.
- **Founding Year:** No specific data found on the founding year.
- **Headquarters Location:** No specific data found on the headquarters location.
- **Founders:** No specific data found on the founders.
- **Ownership Background:** No specific data found on the ownership structure.
- **Official Homepage URL:** [https://dcsg.tech/](https://dcsg.tech/)

**2. Products and Technology:**

- **Core Products & Services:**
- **Network & CDN:** Enhances performance and minimizes latency through a global network.
"""
    
    print("Тестирую извлечение URL из markdown текста...")
    
    # Тестируем извлечение URL
    extracted_url = await _extract_homepage_from_report_text_async(
        test_text, 
        "DCSG TECH CO. L.L.C.", 
        url_only_mode=False
    )
    
    print(f"Извлеченный URL: {extracted_url}")
    
    # Проверяем результат
    expected_url = "https://dcsg.tech/"
    if extracted_url == expected_url:
        print("✅ УСПЕХ: URL извлечен правильно!")
        return True
    else:
        print(f"❌ ОШИБКА: Ожидался {expected_url}, получен {extracted_url}")
        return False

async def test_multiple_formats():
    """Тестирует различные форматы URL в тексте"""
    
    test_cases = [
        # Markdown ссылка с протоколом
        ("**Official Homepage URL:** [https://example.com/](https://example.com/)", "https://example.com/"),
        # Markdown ссылка без протокола
        ("**Website:** [example.com](example.com)", "https://example.com"),
        # Простой URL с протоколом
        ("Official Website: https://example.com", "https://example.com"),
        # Простой домен
        ("Website: example.com", "https://example.com"),
        # Сложный случай с путем
        ("**Official Site:** [https://dcsg.tech/about](https://dcsg.tech/about)", "https://dcsg.tech/about"),
    ]
    
    print("\nТестирую различные форматы URL...")
    
    all_passed = True
    for i, (test_text, expected) in enumerate(test_cases, 1):
        print(f"\nТест {i}: {test_text}")
        
        extracted = await _extract_homepage_from_report_text_async(
            test_text, 
            "Test Company", 
            url_only_mode=False
        )
        
        print(f"Ожидается: {expected}")
        print(f"Получено: {extracted}")
        
        if extracted == expected:
            print("✅ ПРОШЕЛ")
        else:
            print("❌ НЕ ПРОШЕЛ")
            all_passed = False
    
    return all_passed

async def main():
    print("=== ТЕСТ ИСПРАВЛЕНИЯ ИЗВЛЕЧЕНИЯ URL ===\n")
    
    # Основной тест
    test1_passed = await test_url_extraction()
    
    # Дополнительные тесты
    test2_passed = await test_multiple_formats()
    
    print(f"\n=== РЕЗУЛЬТАТЫ ===")
    print(f"Основной тест: {'✅ ПРОШЕЛ' if test1_passed else '❌ НЕ ПРОШЕЛ'}")
    print(f"Дополнительные тесты: {'✅ ПРОШЛИ' if test2_passed else '❌ НЕ ПРОШЛИ'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Логика извлечения URL исправлена.")
    else:
        print("\n❌ ЕСТЬ ПРОБЛЕМЫ. Нужно дополнительно исправлять логику.")

if __name__ == "__main__":
    asyncio.run(main()) 