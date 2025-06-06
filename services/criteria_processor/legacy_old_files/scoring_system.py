"""
Модуль для расчета скоров компаний по критериям Nice-to-Have
"""

from typing import Dict, List, Tuple

# Веса для разных типов критериев
CRITERIA_WEIGHTS = {
    'mandatory': 1.0,  # Обязательные критерии (блокирующие)
    'nth': 1.0,        # Nice-to-Have критерии
    'nd_penalty': 0.1  # Штраф за каждый ND
}

def calculate_nth_score(nth_results: Dict[str, str], audience: str) -> Tuple[float, Dict]:
    """
    Рассчитывает скор Nice-to-Have для конкретной аудитории
    
    Args:
        nth_results: Результаты NTH критериев
        audience: Целевая аудитория
    
    Returns:
        Tuple[float, Dict]: (score, details)
    """
    passed = 0
    total = 0
    nd_count = 0
    
    details = {
        'passed': 0,
        'failed': 0,
        'nd': 0,
        'total': 0,
        'raw_score': 0.0,
        'nd_penalty': 0.0,
        'final_score': 0.0
    }
    
    # Подсчет результатов NTH критериев для данной аудитории
    for key, value in nth_results.items():
        if f"NTH_{audience}_" in key and not key.endswith("_Source"):
            total += 1
            if value == "Passed":
                passed += 1
                details['passed'] += 1
            elif value == "ND":
                nd_count += 1
                details['nd'] += 1
            else:
                details['failed'] += 1
    
    details['total'] = total
    
    if total == 0:
        return 0.0, details
    
    # Расчет базового скора
    raw_score = passed / total
    details['raw_score'] = raw_score
    
    # Применение штрафа за ND
    nd_penalty = nd_count * CRITERIA_WEIGHTS['nd_penalty']
    details['nd_penalty'] = nd_penalty
    
    # Финальный скор (не может быть меньше 0)
    final_score = max(0.0, raw_score - nd_penalty)
    details['final_score'] = final_score
    
    return final_score, details

def calculate_mandatory_status(mandatory_results: Dict[str, str], audience: str) -> Dict:
    """
    Анализирует статус обязательных критериев
    
    Args:
        mandatory_results: Результаты mandatory критериев
        audience: Целевая аудитория
    
    Returns:
        Dict: Статистика по mandatory критериям
    """
    passed = 0
    failed = 0
    nd_count = 0
    total = 0
    
    for key, value in mandatory_results.items():
        if f"Mandatory_{audience}_" in key and not key.endswith("_Source"):
            total += 1
            if value == "Passed":
                passed += 1
            elif value == "Not Passed":
                failed += 1
            elif value == "ND":
                nd_count += 1
    
    return {
        'passed': passed,
        'failed': failed,
        'nd': nd_count,
        'total': total,
        'success_rate': passed / total if total > 0 else 0.0,
        'nd_rate': nd_count / total if total > 0 else 0.0
    }

def generate_scoring_summary(company_results: Dict) -> Dict:
    """
    Генерирует итоговую сводку по скорингу компании
    
    Args:
        company_results: Результаты всех проверок компании
    
    Returns:
        Dict: Сводка по скорингу
    """
    summary = {
        'audiences': {},
        'overall_status': 'Not Qualified'
    }
    
    # Найти все аудитории, для которых есть квалификация
    qualified_audiences = []
    for key, value in company_results.items():
        if key.startswith("Qualification_") and value == "Yes":
            audience = key.replace("Qualification_", "")
            qualified_audiences.append(audience)
    
    # Анализ каждой квалифицированной аудитории
    for audience in qualified_audiences:
        # Проверка mandatory критериев
        mandatory_stats = calculate_mandatory_status(company_results, audience)
        
        # Если mandatory провалены - аудитория исключается
        if mandatory_stats['failed'] > 0:
            summary['audiences'][audience] = {
                'status': 'Failed Mandatory',
                'mandatory': mandatory_stats,
                'nth_score': 0.0,
                'nth_details': {}
            }
            continue
        
        # Расчет NTH скора
        nth_score, nth_details = calculate_nth_score(company_results, audience)
        
        summary['audiences'][audience] = {
            'status': 'Qualified',
            'mandatory': mandatory_stats,
            'nth_score': nth_score,
            'nth_details': nth_details
        }
    
    # Определение общего статуса
    if any(aud['status'] == 'Qualified' for aud in summary['audiences'].values()):
        summary['overall_status'] = 'Qualified'
    
    return summary 