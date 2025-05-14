import asyncio
import os
from dotenv import load_dotenv
from description_generator import DescriptionGenerator

async def test_generator():
    # Загрузка переменных окружения
    load_dotenv()
    
    # Получение API ключа
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return
    
    # Создаем генератор описаний
    generator = DescriptionGenerator(openai_api_key)
    
    # Тестовые данные
    company_name = "Microsoft"
    findings = [
        {
            "source": "homepage_finder",
            "result": "https://www.microsoft.com"
        },
        {
            "source": "linkedin_finder",
            "result": "https://www.linkedin.com/company/microsoft/",
            "snippet": "Microsoft develops, manufactures, licenses, supports, and sells computer software, consumer electronics, personal computers, and related services."
        },
        {
            "source": "llm_deep_search",
            "result": """Microsoft Corporation Business Analytics Report

1. Company Overview:
- Description: Microsoft Corporation is an American multinational technology company specializing in computer software, consumer electronics, personal computers, and related services.
- Founded: April 4, 1975 by Bill Gates and Paul Allen
- Headquarters: Redmond, Washington, United States
- Company Size: Approximately 221,000 employees as of 2023
- Status: Publicly traded (NASDAQ: MSFT)

2. Business Model & Revenue:
- Primary Business Model: Software and cloud services, hardware manufacturing, and licensing
- Revenue: $211.9 billion for fiscal year 2023, up 7% year-over-year
- Pricing Model: Combination of subscription-based services (Microsoft 365, Azure), one-time purchases (Windows, Office), and hardware sales
- Customer Segments: B2C and B2B, including consumers, small businesses, enterprises, educational institutions, and government agencies"""
        }
    ]
    
    # Генерируем описание
    description = await generator.generate_description(company_name, findings)
    
    # Выводим результат
    print(f"\nDescription for {company_name}:")
    print(f"{description}")

if __name__ == "__main__":
    asyncio.run(test_generator()) 