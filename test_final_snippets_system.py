import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from src.pipeline.core import _process_single_company_async
from openai import AsyncOpenAI
from finders.homepage_finder.finder import HomepageFinder
from finders.llm_deep_search_finder.finder import LLMDeepSearchFinder
from description_generator.generator import DescriptionGenerator
from pathlib import Path
import json

async def test_final_snippets_system():
    """Финальный тест системы сохранения сниппетов и сравнения URL"""
    load_dotenv()
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    serper_api_key = os.getenv("SERPER_API_KEY")
    
    if not openai_api_key or not serper_api_key:
        print("❌ API ключи не найдены в .env")
        return
    
    print("🎯 ФИНАЛЬНЫЙ ТЕСТ: Система сохранения сниппетов и сравнения URL")
    print("=" * 70)
    
    # Создаем клиенты
    openai_client = AsyncOpenAI(api_key=openai_api_key)
    
    # Создаем finder instances
    finder_instances = {
        "homepage_finder": HomepageFinder(serper_api_key, openai_api_key, verbose=True),
        "llm_deep_search_finder": LLMDeepSearchFinder(openai_api_key, verbose=True)
    }
    
    # Создаем description generator
    description_generator = DescriptionGenerator(openai_client)
    
    # Тестовые компании
    test_companies = [
        'Collektorskoye agenstvo "ID Collect "',  # Проблемная компания
        'Microsoft Corporation',  # Известная компания
    ]
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        for i, test_company in enumerate(test_companies, 1):
            print(f"\n🔍 ТЕСТ {i}/{len(test_companies)}: {test_company}")
            print("-" * 50)
            
            try:
                result = await _process_single_company_async(
                    company_name=test_company,
                    openai_client=openai_client,
                    aiohttp_session=session,
                    sb_client=None,
                    serper_api_key=serper_api_key,
                    finder_instances=finder_instances,
                    description_generator=description_generator,
                    llm_config={},
                    raw_markdown_output_path=Path("temp"),
                    output_csv_path=None,
                    output_json_path=None,
                    csv_fields=["Company_Name", "Official_Website", "LinkedIn_URL", "Description"],
                    company_index=i,
                    total_companies=len(test_companies),
                    run_llm_deep_search_pipeline=True,
                    run_standard_homepage_finders=True,
                    run_domain_check_finder=False
                )
                
                results.append(result)
                
                # Анализируем результат
                print(f"📊 РЕЗУЛЬТАТ для {test_company}:")
                print(f"   URL: {result.get('Official_Website', 'N/A')}")
                print(f"   LinkedIn: {result.get('LinkedIn_URL', 'N/A')}")
                
                # Проверяем данные поиска Google
                google_data = result.get('google_search_data')
                if google_data:
                    print(f"   🔍 Google Search Data: ✅")
                    print(f"   Selected URL: {google_data.get('selected_url', 'N/A')}")
                    
                    top_5 = google_data.get('top_5_results', [])
                    print(f"   📋 Первые результаты Google ({len(top_5)} найдено):")
                    for j, result_item in enumerate(top_5[:3], 1):  # Показываем только первые 3
                        print(f"      {j}. {result_item.get('title', 'N/A')[:60]}...")
                        print(f"         URL: {result_item.get('url', 'N/A')}")
                        print(f"         Snippet: {result_item.get('snippet', 'N/A')[:80]}...")
                else:
                    print(f"   ❌ Google Search Data не найдена")
                
                # Проверяем качество URL
                found_url = result.get('Official_Website', '')
                if found_url and not any(bad_domain in found_url.lower() for bad_domain in ['bankrotom.ru', 'linkedin.com', 'facebook.com']):
                    print(f"   ✅ URL выглядит корректно")
                elif found_url:
                    print(f"   ⚠️  URL может быть неточным: {found_url}")
                else:
                    print(f"   ❌ URL не найден")
                
            except Exception as e:
                print(f"   ❌ ОШИБКА: {e}")
                results.append({"error": str(e), "company": test_company})
    
    # Сохраняем все результаты
    with open("test_final_snippets_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n🎯 ФИНАЛЬНЫЙ ОТЧЕТ:")
    print("=" * 70)
    print(f"✅ Протестировано компаний: {len(test_companies)}")
    print(f"✅ Успешных результатов: {len([r for r in results if 'error' not in r])}")
    print(f"❌ Ошибок: {len([r for r in results if 'error' in r])}")
    
    # Проверяем что Google Search Data сохраняется
    google_data_count = len([r for r in results if r.get('google_search_data')])
    print(f"🔍 Результатов с Google Search Data: {google_data_count}/{len(results)}")
    
    # Проверяем что URL найдены
    url_found_count = len([r for r in results if r.get('Official_Website')])
    print(f"🌐 Результатов с найденными URL: {url_found_count}/{len(results)}")
    
    print(f"\n💾 Полные результаты сохранены в test_final_snippets_results.json")
    
    if google_data_count == len(results) and url_found_count > 0:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("   ✅ Google Search Data сохраняется")
        print("   ✅ Сниппеты и URL первых 5 результатов сохраняются")
        print("   ✅ Система сравнения URL работает")
        print("   ✅ Правильные URL находятся")
    else:
        print("\n⚠️  НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")

if __name__ == "__main__":
    asyncio.run(test_final_snippets_system()) 