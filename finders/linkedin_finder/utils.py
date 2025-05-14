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
    Нормализует LinkedIn URL к стандартному формату: 
    https://www.linkedin.com/company/company-slug/
    Удаляет подпути типа /about/ и параметры запроса.
    Обрабатывает /company/, /school/, /showcase/, если они содержат явный slug.
    Декодирует URL-кодированные символы в слаге.
    
    Args:
        url: LinkedIn URL для нормализации
        
    Returns:
        str | None: Нормализованный URL или None, если не удалось нормализовать
    """
    if not url or not isinstance(url, str):
        return None

    # Пытаемся обработать URL с использованием urllib.parse для корректного разделения компонентов
    try:
        parsed_url = urlparse(url.lower()) # Приводим к нижнему регистру для единообразия
        
        # Ищем /company/, /school/, /showcase/ в пути
        # и извлекаем только идентификатор (слаг)
        match = re.search(r"/(company|school|showcase)/([^/?#]+)", parsed_url.path)
        
        if not match:
            return None # Если не найдена ожидаемая структура, не можем надежно нормализовать

        profile_type = match.group(1)  # company, school или showcase
        slug = match.group(2)

        # Декодируем URL-кодированные символы в слаге
        try:
            decoded_slug = unquote(slug)
        except Exception:
            decoded_slug = slug 

        # Очищаем slug от возможных внутренних слешей, если они не часть имени
        # (хотя обычно слаги их не содержат, но на всякий случай)
        cleaned_slug = decoded_slug.strip('/')

        if not cleaned_slug:
            return None

        # Собираем чистый URL, без подпутей после слага и без параметров
        # Всегда добавляем слеш в конце базового URL компании/школы/витрины
        return f"https://www.linkedin.com/{profile_type}/{cleaned_slug}/"
    except Exception as e:
        # Можно добавить логирование ошибки, если есть логгер
        # logger.error(f"Error normalizing LinkedIn URL '{url}': {e}")
        return None # В случае любой ошибки при парсинге возвращаем None 