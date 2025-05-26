import asyncio
import sys
import os
import json
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import aiohttp
import ssl
from openai import AsyncOpenAI
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient
from src.config import load_env_vars, load_llm_config
from src.pipeline.core import process_companies
from description_generator import DescriptionGenerator

async def test_dcsg_tech_url_extraction():
    """Тестирует полную обработку компании DCSG TECH с извлечением URL из LLM данных"""
    
    print("=== ФИНАЛЬНЫЙ ТЕСТ DCSG TECH ===\n")
    
    # Настройки для теста
    company_names = ["DCSG TECH CO. L.L.C."]
    
    print(f"Обрабатываю компанию: {company_names[0]}")
    print(f"Режим: use_raw_llm_data_as_description = True")
    print()
    
    try:
        # Загружаем конфигурацию
        scrapingbee_api_key, openai_api_key, serper_api_key, _ = load_env_vars()
        llm_config = load_llm_config()
        
        # Создаем клиентов
        openai_client = AsyncOpenAI(api_key=openai_api_key)
        sb_client = CustomScrapingBeeClient(scrapingbee_api_key) if scrapingbee_api_key else None
        
        # Создаем SSL контекст
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            # Запускаем обработку
            results = await process_companies(
                company_names=company_names,
                openai_client=openai_client,
                aiohttp_session=session,
                sb_client=sb_client,
                serper_api_key=serper_api_key,
                llm_config=llm_config,
                raw_markdown_output_path=Path("test_output"),
                batch_size=1,
                use_raw_llm_data_as_description=True,  # Ключевая настройка!
                run_llm_deep_search_pipeline_cfg=True,
                run_standard_pipeline_cfg=True,
                run_domain_check_finder_cfg=False,
                output_csv_path="test_dcsg_tech_result.csv",
                output_json_path="test_dcsg_tech_result.json",
                expected_csv_fieldnames=["Company_Name", "Official_Website", "LinkedIn_URL", "Description", "Timestamp"]
            )
        
        if results and len(results) > 0:
            result = results[0]
            
            print("=== РЕЗУЛЬТАТ ===")
            print(f"Компания: {result.get('Company_Name', 'N/A')}")
            print(f"Официальный сайт: {result.get('Official_Website', 'N/A')}")
            print(f"LinkedIn: {result.get('LinkedIn_URL', 'N/A')}")
            print(f"Длина описания: {len(result.get('Description', '')) if result.get('Description') else 0} символов")
            
            # Проверяем что URL извлечен правильно
            official_website = result.get('Official_Website', '')
            expected_url = "https://dcsg.tech/"
            
            if official_website == expected_url:
                print(f"\n✅ УСПЕХ: URL извлечен правильно из LLM данных!")
                print(f"Ожидался: {expected_url}")
                print(f"Получен: {official_website}")
                
                # Проверяем что описание содержит URL
                description = result.get('Description', '')
                if expected_url in description or 'dcsg.tech' in description:
                    print("✅ URL также присутствует в описании")
                else:
                    print("⚠️ URL не найден в описании")
                
                return True
            else:
                print(f"\n❌ ОШИБКА: URL не извлечен правильно!")
                print(f"Ожидался: {expected_url}")
                print(f"Получен: {official_website}")
                
                # Показываем часть описания для диагностики
                description = result.get('Description', '')
                if description:
                    print(f"\nПервые 500 символов описания:")
                    print(description[:500] + "..." if len(description) > 500 else description)
                
                return False
        else:
            print("❌ ОШИБКА: Результаты не получены")
            return False
            
    except Exception as e:
        print(f"❌ ОШИБКА при обработке: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    success = await test_dcsg_tech_url_extraction()
    
    print(f"\n=== ФИНАЛЬНЫЙ РЕЗУЛЬТАТ ===")
    if success:
        print("🎉 ТЕСТ ПРОШЕЛ! Система правильно извлекает URL из LLM данных.")
    else:
        print("❌ ТЕСТ НЕ ПРОШЕЛ! Нужно дополнительно исправлять систему.")

if __name__ == "__main__":
    asyncio.run(main()) 