#!/usr/bin/env python3
"""
Тестовый скрипт для проверки улучшенной валидации URL
"""

import asyncio
import aiohttp
import sys
import os
from pathlib import Path

# Добавляем текущую директорию в путь
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from normalize_urls import get_url_status_and_final_location_async
from src.external_apis.scrapingbee_client import CustomScrapingBeeClient

async def test_url_validation():
    """Тестирует валидацию URL для известных сайтов, которые блокируют ботов"""
    
    test_urls = [
        "https://www.adidas.com",
        "https://www.chewy.com", 
        "https://www.google.com",  # Контрольный тест
        "https://nonexistent-domain-12345.com"  # Неживой домен
    ]
    
    print("🧪 Тестирование улучшенной валидации URL...")
    print("=" * 60)
    
    # Инициализируем ScrapingBee клиент (если есть API ключ в переменной окружения)
    scrapingbee_client = None
    sb_api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if sb_api_key:
        try:
            scrapingbee_client = CustomScrapingBeeClient(api_key=sb_api_key)
            print("✅ ScrapingBee клиент инициализирован")
        except Exception as e:
            print(f"❌ Ошибка инициализации ScrapingBee: {e}")
    else:
        print("⚠️  SCRAPINGBEE_API_KEY не найден в переменных окружения")
    
    print()
    
    async with aiohttp.ClientSession() as session:
        for url in test_urls:
            print(f"🔍 Тестируем URL: {url}")
            
            try:
                is_live, final_url, error_message = await get_url_status_and_final_location_async(
                    url, 
                    session, 
                    timeout=15.0,
                    scrapingbee_client=scrapingbee_client
                )
                
                if is_live:
                    print(f"✅ ЖИВОЙ: {url}")
                    if final_url != url:
                        print(f"   ↳ Финальный URL: {final_url}")
                    if error_message:
                        print(f"   ℹ️  Примечание: {error_message}")
                else:
                    print(f"❌ МЕРТВЫЙ: {url}")
                    if error_message:
                        print(f"   ↳ Причина: {error_message}")
                        
            except Exception as e:
                print(f"💥 ОШИБКА при проверке {url}: {e}")
            
            print("-" * 40)
            # Небольшая пауза между запросами
            await asyncio.sleep(1)
    
    if scrapingbee_client:
        await scrapingbee_client.close_async()
    
    print("\n🏁 Тестирование завершено!")
    print("\n📝 Ожидаемые результаты:")
    print("   • Adidas и Chewy должны показать 'ЖИВОЙ' (даже если блокируют ботов)")
    print("   • Google должен показать 'ЖИВОЙ'")
    print("   • Несуществующий домен должен показать 'МЕРТВЫЙ'")

if __name__ == "__main__":
    try:
        asyncio.run(test_url_validation())
    except KeyboardInterrupt:
        print("\n⏹️  Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        sys.exit(1) 