"""
Модуль для проверки Mandatory критериев
"""

from src.criteria.base import get_structured_response
from src.external.serper import get_information_for_criterion
from src.utils.config import PROCESSING_CONFIG
from src.utils.logging import log_info, log_error

def check_mandatory_criteria(description, company_info, audience, mandatory_df):
    """Check mandatory criteria for an audience - updated for manager requirements"""
    mandatory = mandatory_df[mandatory_df["Target Audience"] == audience]
    failed = False
    nd_count = 0
    total = 0
    
    for _, row in mandatory.iterrows():
        crit = row["Criteria"]
        place = row.get("Place", "gen_descr")
        search_query = row.get("Search Query", None)
        
        log_info(f"⚠️  Mandatory {audience}: {crit}", console=False)
        
        # НОВОЕ ТРЕБОВАНИЕ: Обязательно использовать Serper для mandatory критериев
        if PROCESSING_CONFIG['use_serper_for_mandatory'] and place == "gen_descr":
            log_info(f"🔄 Принудительно переключаем на website поиск для mandatory критерия", console=False)
            place = "website"
        
        # Get information based on the Place field
        information, source_desc = get_information_for_criterion(company_info, place, search_query)
        log_info(f"🔍 Источник: {source_desc}", console=False)
        
        result, error = get_structured_response("mandatory", information, crit, "standard")
        
        if error:
            log_error(f"❌ Ошибка Mandatory {audience} {crit}: {error}")
            company_info[f"Mandatory_{audience}_{crit}"] = "Error"
            # Считаем ошибки как ND для статистики
            nd_count += 1
        else:
            log_info(f"➡️  {result}", console=False)
            company_info[f"Mandatory_{audience}_{crit}"] = result
            
            # НОВОЕ ТРЕБОВАНИЕ: "Not Pass" исключает, ND не исключает
            if result == "Not Passed":
                failed = True
                log_info(f"🚫 КРИТИЧЕСКИЙ ПРОВАЛ mandatory критерия - аудитория исключается", console=False)
            elif result == "ND":
                nd_count += 1
                log_info(f"❓ ND на mandatory критерии - продолжаем обработку", console=False)
        
        total += 1
        
        # НОВОЕ ТРЕБОВАНИЕ: останавливаться только при "Not Passed", не при ND
        if failed:
            break
    
    # Статистика ND для mandatory критериев
    if total > 0:
        company_info[f"ND_Rate_Mandatory_{audience}"] = round(nd_count / total, 2)
    
    # Возвращаем True если НЕ провалился ни один mandatory (ND разрешены)
    return not failed 