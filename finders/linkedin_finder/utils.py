import re
from urllib.parse import urlparse, unquote

def normalize_name_for_domain_comparison(name: str) -> str:
    """
    Нормализует название компании для сравнения с доменами и слагами.
    
    Args:
        name: Название компании
        
    Returns:
        str: Нормализованное название
    """
    # Удаляем всё в скобках
    name = re.sub(r'\s*\([^)]*\)', '', name)
    name = name.lower()
    common_suffixes = [
        ', inc.', ' inc.', ', llc', ' llc', ', ltd.', ' ltd.', ' ltd', ', gmbh', ' gmbh',
        ', s.a.', ' s.a.', ' plc', ' se', ' ag', ' oyj', ' ab', ' as', ' nv', ' bv', ' co.', ' co'
        ' corporation', ' company', ' group', ' holding', ' solutions', ' services',
        ' technologies', ' systems', ' international'
    ]
    for suffix in common_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = re.sub(r'[^\w-]', '', name)
    return name.strip('-')

def normalize_linkedin_url(url: str) -> str | None:
    """
    Нормализует LinkedIn URL к стандартному формату: https://www.linkedin.com/company/company-slug/about/
    Обрабатывает /company/, /school/, /showcase/ если они содержат явный slug.
    Декодирует URL-кодированные символы в слаге.
    
    Args:
        url: LinkedIn URL для нормализации
        
    Returns:
        str | None: Нормализованный URL или None, если не удалось нормализовать
    """
    if not url or not isinstance(url, str):
        return None

    url_lower = url.lower()
    
    # Пытаемся найти /company/, /school/, /showcase/
    # Пример: linkedin.com/company/example-inc%C3%A9
    # Пример: linkedin.com/school/university-of-example/
    # Пример: linkedin.com/showcase/example-product-line/
    match = re.search(r"linkedin\.com/(company|school|showcase)/([^/?#]+)", url_lower)
    
    if not match:
        # Резервный вариант для менее распространенных, но допустимых URL-адресов профилей
        # например linkedin.com/in/profile-name (маловероятно для поиска компании, но в качестве защиты)
        # или прямые ссылки, такие как linkedin.com/company/example/ (без косой черты или /about)
        # Это регулярное выражение шире, но нас в основном интересует структура /company/
        if "linkedin.com/" in url_lower:  # Базовая проверка
            # Пытаемся найти часть, похожую на slug, даже без префикса /company/,
            # если она выглядит как профиль
            # Это менее надежно и в идеале должно быть поймано хорошим совпадением /company/ сначала
            pass  # Пока, если нет четкой структуры company/school/showcase, не нормализуем
        return None  # Если нет четкой структуры company/school/showcase, не можем надежно нормализовать

    profile_type = match.group(1)  # company, school или showcase
    slug = match.group(2)

    # Декодируем URL-кодированные символы в слаге (например, %20 для пробела, %C3%A9 для é)
    try:
        decoded_slug = unquote(slug)
    except Exception:
        decoded_slug = slug  # Используем оригинальный slug если декодирование не удалось

    # Дополнительно очищаем slug: удаляем лишние слэши или параметры запроса, если они случайно включены
    # Регулярное выражение уже обрабатывает ? и #, но слэши в конце могут быть частью slug
    cleaned_slug = decoded_slug.strip('/')

    if not cleaned_slug:  # Пустой slug после очистки
        return None

    # Для 'showcase' и 'school' мы все равно нормализуем до /about/ для согласованности,
    # хотя их фактический раздел "about" может отличаться или не существовать таким же образом.
    # Основная цель - иметь согласованную структуру URL для попыток скрейпинга.
    return f"https://www.linkedin.com/{profile_type}/{cleaned_slug}/about/" 