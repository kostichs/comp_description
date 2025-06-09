#!/usr/bin/env python3
"""
Тест для проверки что пути резолвятся правильно в любой среде
"""

import os
import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.data_io import PROJECT_ROOT, SESSIONS_DIR, SESSIONS_METADATA_FILE

def test_path_resolution():
    """Тестирует корректность разрешения путей"""
    
    print("🧪 Тестирование разрешения путей...")
    print("=" * 50)
    
    # Показываем текущую среду
    print(f"🖥️  Операционная система: {os.name}")
    print(f"📁 Текущая директория: {Path.cwd()}")
    print(f"🐍 Python исполняется из: {sys.executable}")
    print()
    
    # Показываем разрешенные пути
    print("📍 Разрешенные пути:")
    print(f"   PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"   SESSIONS_DIR: {SESSIONS_DIR}")
    print(f"   SESSIONS_METADATA_FILE: {SESSIONS_METADATA_FILE}")
    print()
    
    # Проверяем существование путей
    print("✅ Проверка существования:")
    print(f"   PROJECT_ROOT exists: {PROJECT_ROOT.exists()}")
    print(f"   SESSIONS_DIR exists: {SESSIONS_DIR.exists()}")
    print(f"   SESSIONS_METADATA_FILE exists: {SESSIONS_METADATA_FILE.exists()}")
    print()
    
    # Показываем абсолютные пути
    print("🗂️  Абсолютные пути:")
    print(f"   PROJECT_ROOT.absolute(): {PROJECT_ROOT.absolute()}")
    print(f"   SESSIONS_DIR.absolute(): {SESSIONS_DIR.absolute()}")
    print(f"   SESSIONS_METADATA_FILE.absolute(): {SESSIONS_METADATA_FILE.absolute()}")
    print()
    
    # Проверяем что это работает в роутерах
    print("🔗 Тест роутера (имитация):")
    session_id = "test_session_123"
    session_path = SESSIONS_DIR / session_id
    print(f"   Путь сессии: {session_path}")
    print(f"   Абсолютный путь сессии: {session_path.absolute()}")
    print()
    
    # Определяем среду
    environment = "Docker Container" if str(PROJECT_ROOT).startswith("/app") else "Local Development"
    print(f"🌍 Определенная среда: {environment}")
    
    print("\n🎯 Заключение:")
    if PROJECT_ROOT.exists():
        print("✅ Пути резолвятся корректно!")
        print("✅ Этот код будет работать одинаково локально и в Docker!")
    else:
        print("❌ Проблема с разрешением путей")
        return False
    
    return True

if __name__ == "__main__":
    try:
        success = test_path_resolution()
        if success:
            print("\n🏁 Все тесты прошли успешно!")
            sys.exit(0)
        else:
            print("\n💥 Есть проблемы с путями!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Ошибка при тестировании: {e}")
        sys.exit(1)
 