"""
Модуль для проверки NTH критериев
"""

from src.criteria.base import get_structured_response
from src.external.serper import get_information_for_criterion
from src.utils.logging import log_info, log_error

def check_nth_criteria(description, company_info, audience, nth_df):
    """Check NTH criteria for an audience - updated for manager requirements"""
    filtered_df = nth_df[nth_df["Target Audience"] == audience]
    passed_count = 0
    nd_count = 0
    total = 0
    
    log_info(f"Начинаем проверку {len(filtered_df)} NTH критериев для {audience}", console=False)
    
    # НОВОЕ ТРЕБОВАНИЕ: Обрабатывать ВСЕ NTH критерии независимо от результатов
    for _, row in filtered_df.iterrows():
        crit = row["Criteria"]
        place = row.get("Place", "gen_descr")
        search_query = row.get("Search Query", None)
        
        log_info(f"NTH {audience}: {crit}", console=False)
        
        # Get information based on the Place field
        information, source_desc = get_information_for_criterion(company_info, place, search_query)
        log_info(f"Источник: {source_desc}", console=False)
        
        result, error = get_structured_response("nth", information, crit, "standard")
        
        if error:
            log_error(f"Ошибка NTH {audience} {crit}: {error}")
            company_info[f"NTH_{audience}_{crit}"] = "Error"
            # Считаем ошибки как ND
            nd_count += 1
        else:
            log_info(f"{result}", console=False)
            company_info[f"NTH_{audience}_{crit}"] = result
            
            if result == "Passed":
                passed_count += 1
                log_info(f"NTH критерий пройден", console=False)
            elif result == "ND":
                nd_count += 1
                log_info(f"Недостаточно данных для NTH критерия", console=False)
            else:
                log_info(f"NTH критерий не пройден", console=False)
        
        total += 1
    
    # НОВОЕ ТРЕБОВАНИЕ: Детальная статистика для скоринга
    if total > 0:
        success_rate = passed_count / total
        nd_rate = nd_count / total
        
        company_info[f"NTH_Score_{audience}"] = round(success_rate, 3)
        company_info[f"NTH_Total_{audience}"] = total
        company_info[f"NTH_Passed_{audience}"] = passed_count
        company_info[f"NTH_ND_{audience}"] = nd_count
        company_info[f"NTH_ND_Rate_{audience}"] = round(nd_rate, 3)
        
        log_info(f"NTH Статистика для {audience}:", console=False)
        log_info(f"   Пройдено: {passed_count}/{total} ({success_rate:.1%})", console=False)
        log_info(f"   ND: {nd_count}/{total} ({nd_rate:.1%})", console=False)
    
    return None 