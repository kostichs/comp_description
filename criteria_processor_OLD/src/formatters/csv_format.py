"""
Модуль для форматирования результатов в CSV формат
"""

import json
from typing import Dict

def format_for_csv_output(structured_results: Dict, criteria_type: str) -> Dict:
    """Format structured results for CSV output compatibility"""
    
    # Create main CSV row structure
    csv_row = {
        'Company_Name': structured_results['company_info']['company_name'],
        'Official_Website': structured_results['company_info']['website'], 
        'Description': structured_results['company_info']['description']
    }
    
    # Add analysis results as JSON string (for compatibility)
    analysis_data = {
        'general_criteria': structured_results['general_criteria'],
        'qualification_results': structured_results['qualification_results'],
        'mandatory_results': structured_results['mandatory_results'],
        'nth_results': structured_results['nth_results'],
        'scoring_summary': structured_results['scoring_summary'],
        'metadata': structured_results['metadata']
    }
    
    # Store analysis as JSON string in product-specific column
    csv_row[f'{criteria_type}_analysis'] = json.dumps(analysis_data, ensure_ascii=False, indent=2)
    
    return csv_row

def format_qualification_results(company_results: Dict) -> Dict:
    """
    Форматирует результаты квалификационных вопросов
    
    Args:
        company_results: Результаты проверок компании
    
    Returns:
        Dict: Отформатированные результаты квалификации
    """
    qualification_results = {}
    
    for key, value in company_results.items():
        if key.startswith("Qualification_"):
            audience = key.replace("Qualification_", "")
            qualification_results[audience] = {
                'result': value,
                'qualified': value == "Yes"
            }
    
    return qualification_results

def format_mandatory_results(company_results: Dict) -> Dict:
    """
    Форматирует результаты обязательных критериев
    
    Args:
        company_results: Результаты проверок компании
    
    Returns:
        Dict: Отформатированные результаты mandatory
    """
    mandatory_results = {}
    
    # Группировка по аудиториям
    for key, value in company_results.items():
        if key.startswith("Mandatory_") and not key.endswith("_Source"):
            parts = key.split("_", 2)
            if len(parts) >= 3:
                audience = parts[1]
                criterion = parts[2]
                
                if audience not in mandatory_results:
                    mandatory_results[audience] = {}
                
                mandatory_results[audience][criterion] = {
                    'result': value,
                    'passed': value == "Passed",
                    'nd': value == "ND"
                }
    
    return mandatory_results

def format_nth_results(company_results: Dict) -> Dict:
    """
    Форматирует результаты Nice-to-Have критериев
    
    Args:
        company_results: Результаты проверок компании
    
    Returns:
        Dict: Отформатированные результаты NTH
    """
    nth_results = {}
    
    # Группировка по аудиториям
    for key, value in company_results.items():
        if key.startswith("NTH_") and not key.endswith("_Source"):
            parts = key.split("_", 2)
            if len(parts) >= 3:
                audience = parts[1]
                criterion = parts[2]
                
                if audience not in nth_results:
                    nth_results[audience] = {}
                
                nth_results[audience][criterion] = {
                    'result': value,
                    'passed': value == "Passed",
                    'nd': value == "ND"
                }
    
    return nth_results 