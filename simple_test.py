#!/usr/bin/env python3
"""
Простой тест системы проверки качества
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.integrations.hubspot.quality_checker import should_write_to_hubspot

# Тест 1: Плохое описание (неудачный поиск)
bad_description = "After an extensive search, I was unable to locate any information on a company named 'PalcyDev'."

print("🔍 Тестирование системы проверки качества")
print("\n📝 Тест 1: Плохое описание")
result1 = should_write_to_hubspot(bad_description, "PalcyDev")
print(f"Результат: {result1[0]} - {result1[1]}")

# Тест 2: Хорошее описание
good_description = """
BDSwiss Group is a privately held financial services company founded in 2012 and headquartered in Zug, Switzerland. The company specializes in online trading services, offering forex and CFD trading through multiple platforms including their proprietary BDSwiss WebTrader and mobile applications, as well as popular third-party platforms like MetaTrader 4 and MetaTrader 5.

The company serves individual retail traders globally, operating in over 180 countries with a focus on providing user-friendly trading solutions. BDSwiss offers trading in various financial instruments including currency pairs, commodities, indices, and cryptocurrencies through contracts for difference. Their technology stack includes React and React Native for their web and mobile platforms, with Node.js powering their backend infrastructure.

BDSwiss employs approximately 456 people and generates an estimated annual revenue of $119.7 million. The company maintains regulatory compliance through multiple licenses from financial authorities including the Financial Services Commission in Mauritius, Financial Services Authority in Seychelles, and the Securities & Commodities Authority in the UAE. Recent strategic initiatives include the introduction of Dynamic Leverage and Zero-Spread Account features in 2023 to enhance trading conditions for their clients.
"""

print("\n📝 Тест 2: Хорошее описание")  
result2 = should_write_to_hubspot(good_description, "BDSwiss")
print(f"Результат: {result2[0]} - {result2[1]}")

print(f"\n🏆 Тесты завершены")
print(f"Плохое описание: {'ОТКЛОНЕНО' if not result1[0] else 'ПРИНЯТО'}")
print(f"Хорошее описание: {'ПРИНЯТО' if result2[0] else 'ОТКЛОНЕНО'}") 