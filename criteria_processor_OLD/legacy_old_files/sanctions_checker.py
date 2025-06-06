"""
Модуль для проверки компаний на санкционные ограничения
"""

import re
from typing import Tuple
from logger_config import log_info, log_error, log_debug

# Список стран-санкций согласно требованиям менеджера
SANCTIONED_COUNTRIES = {
    'iran': ['iran', 'iranian', 'tehran', 'isfahan', 'mashhad'],
    'russia': ['russia', 'russian', 'moscow', 'petersburg', 'rf', 'russian federation'],
    'china': ['china', 'chinese', 'beijing', 'shanghai', 'prc', "people's republic of china"],
    'turkmenistan': ['turkmenistan', 'turkmen', 'ashgabat'],
    'north_korea': ['north korea', 'dprk', 'pyongyang', 'democratic people\'s republic of korea']
}

def check_sanctions(company_name: str, description: str, website: str = "") -> Tuple[bool, str]:
    """
    Проверяет компанию на попадание под санкции
    
    Args:
        company_name: Название компании
        description: Описание компании
        website: Веб-сайт компании (опционально)
    
    Returns:
        Tuple[bool, str]: (is_sanctioned, reason)
    """
    # Объединяем все данные для проверки
    text_to_check = f"{company_name} {description} {website}".lower()
    
    log_debug(f"🔍 Checking sanctions for: {company_name}")
    
    # Проверяем каждую страну-санкцию
    for country, keywords in SANCTIONED_COUNTRIES.items():
        for keyword in keywords:
            if keyword in text_to_check:
                reason = f"Company appears to be from sanctioned country: {country.replace('_', ' ').title()}"
                log_debug(f"🚫 САНКЦИЯ ОБНАРУЖЕНА: {reason}")
                return True, reason
    
    # Дополнительные проверки по доменам
    if website:
        sanctioned_domains = ['.ru', '.ir', '.cn', '.kp', '.tm']
        for domain in sanctioned_domains:
            if domain in website.lower():
                country_map = {'.ru': 'Russia', '.ir': 'Iran', '.cn': 'China', '.kp': 'North Korea', '.tm': 'Turkmenistan'}
                reason = f"Company website domain indicates sanctioned country: {country_map[domain]}"
                log_debug(f"🚫 САНКЦИЯ ОБНАРУЖЕНА: {reason}")
                return True, reason
    
    log_debug(f"✅ Санкции не обнаружены")
    return False, "No sanctions detected"

def apply_sanctions_filter(companies_data, verbose=True):
    """
    Применяет санкционный фильтр к списку компаний
    
    Args:
        companies_data: DataFrame с данными компаний
        verbose: Показывать детали фильтрации
    
    Returns:
        Tuple[DataFrame, list]: (filtered_companies, sanctioned_list)
    """
    from config import DEBUG_SANCTIONS
    
    log_info(f"�� Применяем санкционные фильтры к {len(companies_data)} компаниям")
    
    sanctioned_companies = []
    filtered_indices = []
    
    for idx, row in companies_data.iterrows():
        company = row['Company_Name']
        description = row.get('Description', '')
        website = row.get('Official_Website', '')
        
        is_sanctioned, reason = check_sanctions(company, description, website)
        
        if is_sanctioned:
            sanctioned_companies.append({
                'company': company,
                'reason': reason
            })
            if DEBUG_SANCTIONS:
                log_info(f"🚫 ИСКЛЮЧЕНО: {company} - {reason}")
        else:
            filtered_indices.append(idx)
    
    # Filter DataFrame
    filtered_df = companies_data.loc[filtered_indices].reset_index(drop=True)
    
    log_info(f"📊 Результат санкционной фильтрации:")
    log_info(f"   Исключено: {len(sanctioned_companies)} компаний")
    log_info(f"   Прошло фильтр: {len(filtered_df)} компаний")
    
    return filtered_df, sanctioned_companies 