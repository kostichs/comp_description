import os
from datetime import datetime
from configparser import ConfigParser
from dotenv import load_dotenv

# Base directory - исправлено для корня criteria_processor  
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Criteria type configuration - изменено для поддержки новых требований
CRITERIA_TYPE = "VM2"  # Можно изменить на "CDN2", "VM2" и т.д.

# Новая схема именования файлов критериев с префиксом "критерий_"
INDUSTRY_MAPPING = {
    "VM2": "VM",
    "CDN2": "CDN", 
    "Fintech": "Fintech",
    "Gaming": "Gaming",
    "Gambling": "Gambling"
}

# Configuration files
ENV_PATH = os.path.join(BASE_DIR, ".env")
YAML_PATH = os.path.join(BASE_DIR, "promt_generate.yaml")

# Input files - автоматически находить CSV файлы в папке data
DATA_DIR = os.path.join(BASE_DIR, "data")

# Criteria directory - новая папка для всех критериев
CRITERIA_DIR = os.path.join(BASE_DIR, "criteria")

# Output configuration
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CSV_OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"{CRITERIA_TYPE}_analysis_{timestamp}.csv")

# Processing limits
COMPANIES_LIMIT = 0  # 0 = без ограничений, обрабатывать все компании

# New processing configuration - новые настройки для требований менеджера
PROCESSING_CONFIG = {
    'enable_hubspot_integration': False,     # HubSpot интеграция (пока выключена)
    'sequential_processing': True,           # Последовательная обработка отраслей
    'use_serper_for_mandatory': True,        # Использовать Serper для mandatory критериев
    'use_general_desc_for_qualification': True,  # General description для квалификации
    'json_output_format': True,              # JSON структура вывода
    'calculate_nth_scores': True,            # Расчет скоров NTH
    'exclude_on_mandatory_fail': True        # Исключать при провале mandatory
}

# Debug settings
DEBUG_SERPER = True  # Show detailed Serper inputs/outputs
DEBUG_OPENAI = True  # Show detailed OpenAI inputs/outputs
DEBUG_SCORING = True  # Show detailed scoring calculations

# Load API keys
load_dotenv(dotenv_path=ENV_PATH)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")

# If .env file not found but environment variables are set, use them directly
if not OPENAI_API_KEY:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not SERPER_API_KEY:
    SERPER_API_KEY = os.environ.get("SERPER_API_KEY")  
if not SCRAPINGBEE_API_KEY:
    SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY")

# Deep analysis via ScrapingBee
USE_SCRAPINGBEE_DEEP_ANALYSIS = True  # Master switch for the new feature
SCRAPE_TOP_N_RESULTS = 5  # Number of Google results to scrape

# Async ScrapingBee configuration
ASYNC_SCRAPING_CONFIG = {
    'enable_async_scraping': True,           # Use async ScrapingBee client for better performance
    'max_concurrent_scrapes': 8,             # Увеличиваем с 5 до 8 для лучшей производительности  
    'scraping_rate_limit_delay': 0.2,        # Delay between requests (seconds)
    'scraping_timeout': 120,                # Request timeout (seconds)
    'fallback_to_sync': True                 # Fallback to sync scraping if async fails
}

# Async GPT configuration
ASYNC_GPT_CONFIG = {
    'enable_async_gpt': False,               # ОТКЛЮЧАЕМ обратно - async версия дает плохие результаты
    'max_concurrent_gpt_requests': 15,       # Увеличиваем с 10 до 15 для лучшей производительности
    'gpt_rate_limit_delay': 0.1,             # Delay between requests (seconds)
    'gpt_timeout': 60,                       # Request timeout (seconds)
    'fallback_to_sync': True                 # Fallback to sync GPT if async fails
}

# Circuit Breaker configuration для OpenAI API rate limiting
CIRCUIT_BREAKER_CONFIG = {
    'enable_circuit_breaker': True,          # Мастер-переключатель Circuit Breaker
    'failure_threshold': 5,                  # Количество rate limit ошибок для открытия circuit
    'recovery_timeout': 120,                 # Секунд ожидания в OPEN состоянии перед попыткой восстановления
    'success_threshold': 3,                  # Успешных запросов для закрытия circuit из HALF_OPEN
    'rate_limit_keywords': [                 # Ключевые слова для определения rate limit ошибок
        'rate_limit', 'quota_exceeded', 'too_many_requests', 
        'rate limit', 'limit exceeded', 'throttled',
        'rate limiting', 'usage limit', 'api limit'
    ],
    'max_half_open_requests': 3              # Максимум тестовых запросов в HALF_OPEN состоянии
}

# Smart filtering configuration
SMART_FILTERING_CONFIG = {
    'enable_signals_prioritization': True,    # Use Signals column for content prioritization
    'priority_section_header': "=== PRIORITY CONTENT (Contains signals keywords) ===",
    'full_content_header': "=== FULL SCRAPED CONTENT ===",
    'context_sentences_around_match': 2,      # Number of sentences around signal matches
    'min_priority_content_length': 100,       # Minimum chars for priority section
    'max_priority_content_ratio': 0.3,        # Max ratio of priority to full content
    'case_sensitive_matching': False,         # Case sensitivity for keyword matching
    'phrase_matching_enabled': True           # Support for quoted phrase matching
}

# Smart filtering configuration
SMART_FILTERING_CONFIG = {
    'enable_signals_prioritization': True,    # Use Signals column for content prioritization
    'priority_section_header': "=== PRIORITY CONTENT (Contains signals keywords) ===",
    'full_content_header': "=== FULL SCRAPED CONTENT ===",
    'context_sentences_around_match': 2,      # Number of sentences around signal matches
    'min_priority_content_length': 100,       # Minimum chars for priority section
    'max_priority_content_ratio': 0.3,        # Max ratio of priority to full content
    'case_sensitive_matching': False,         # Case sensitivity for keyword matching
    'phrase_matching_enabled': True           # Support for quoted phrase matching
}

# Serper.dev API configuration
SERPER_API_URL = "https://google.serper.dev/search"
# Number of retries for Serper.dev API
SERPER_MAX_RETRIES = 3
# Delay between retries (in seconds)
SERPER_RETRY_DELAY = 3

# Output directory for results and logs
LOGS_DIR = "logs"

def validate_config():
    """Validate that all required files exist"""
    required_files = {
        "YAML_PATH": YAML_PATH
    }
    
    # Check .env file only if environment variables are not already set
    if not (OPENAI_API_KEY and SERPER_API_KEY):
        required_files["ENV_PATH"] = ENV_PATH
    
    # Check for all required files
    missing = []
    for key, path in required_files.items():
        if not os.path.isfile(path):
            missing.append(f"{key}: {path}")
    
    # Check directories exist
    required_dirs = {
        "DATA_DIR": DATA_DIR,
        "CRITERIA_DIR": CRITERIA_DIR
    }
    
    for key, path in required_dirs.items():
        if not os.path.exists(path):
            missing.append(f"{key}: {path}")
    
    if missing:
        raise FileNotFoundError(f"Missing required files/directories: {', '.join(missing)}")
    
    # Check for CSV files in data directory
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in data directory: {DATA_DIR}")
    
    # Check for required API keys
    if not OPENAI_API_KEY:
        raise ValueError("Missing OPENAI_API_KEY in .env file or environment variables")
    
    if not SERPER_API_KEY:
        raise ValueError("Missing SERPER_API_KEY in .env file or environment variables")
    
    # Check for ScrapingBee API key if feature is enabled
    if USE_SCRAPINGBEE_DEEP_ANALYSIS and not SCRAPINGBEE_API_KEY:
        raise ValueError("USE_SCRAPINGBEE_DEEP_ANALYSIS is True, but SCRAPINGBEE_API_KEY is missing in .env file or environment variables")

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Validate processing configuration
    if PROCESSING_CONFIG['enable_hubspot_integration'] and not os.getenv("HUBSPOT_API_KEY"):
        print("Warning: HubSpot integration enabled but no HUBSPOT_API_KEY found")
    
    print(f"Configuration validated for criteria type: {CRITERIA_TYPE}")
    print(f"   Criteria directory: {CRITERIA_DIR}")
    print(f"   Data directory: {DATA_DIR}")
    print(f"   Available CSV files: {', '.join(csv_files)}")
    print(f"   Output: {CSV_OUTPUT_PATH}")
    
    return True 