"""
Модуль для проверки общих критериев
"""

from src.external.openai_client import get_openai_response
from src.utils.logging import log_info, log_debug

def check_general_criteria(description, company_info, general_criteria):
    """Check general criteria for a company - batch processing with detailed results"""
    log_debug(f"🌐 Проверяем {len(general_criteria)} общих критериев одним запросом")
    
    # Create batch prompt for all criteria
    criteria_list = "\n".join([f"{i+1}. {criteria}" for i, criteria in enumerate(general_criteria)])
    
    prompt = f"""
Analyze this company description against the following criteria. 
For each criterion, respond with only "Yes" or "No".

Company Description: {description}

Criteria:
{criteria_list}

Response format (one line per criterion):
1. Yes/No
2. Yes/No
3. Yes/No
... etc
"""
    
    detailed_general_results = []
    passed_count = 0
    
    try:
        response = get_openai_response(prompt, max_tokens=100)
        lines = response.strip().split('\n')
        
        for i, criteria in enumerate(general_criteria):
            if i < len(lines):
                line = lines[i].strip()
                result = "Yes" if "yes" in line.lower() else "No"
            else:
                result = "No"
            
            # Store detailed information about each general criterion
            criterion_info = {
                "criteria_text": criteria,
                "result": "Pass" if result == "Yes" else "Fail"
            }
            detailed_general_results.append(criterion_info)
            
            if result == "Yes":
                passed_count += 1
                log_debug(f"   ✅ Критерий {i+1}: {result}")
            else:
                log_debug(f"   ❌ Критерий {i+1}: {result}")
                
    except Exception as e:
        log_debug(f"   ⚠️ Ошибка батчевой проверки: {e}")
        # If error, create failed entries for all criteria
        for i, criteria in enumerate(general_criteria):
            criterion_info = {
                "criteria_text": criteria,
                "result": "Error"
            }
            detailed_general_results.append(criterion_info)
        passed_count = 0
    
    # Store detailed results in company_info for later use
    company_info["General_Detailed_Results"] = detailed_general_results
    company_info["General_Passed_Count"] = passed_count
    company_info["General_Total_Count"] = len(general_criteria)
    
    # Consider passed if majority of criteria are met
    threshold = len(general_criteria) / 2
    passed = passed_count > threshold
    
    log_info(f"General критерии: {passed_count}/{len(general_criteria)} пройдено → {'PASS' if passed else 'FAIL'}")
    
    return passed 