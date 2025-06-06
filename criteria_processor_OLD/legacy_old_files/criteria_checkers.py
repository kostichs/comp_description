from models import ask_openai_structured, load_prompts
from serper_utils import get_information_for_criterion
from config import DEBUG_OPENAI, PROCESSING_CONFIG
from logger_config import log_info, log_error, log_debug

# Load prompt templates
prompts = load_prompts()

# Define standard JSON schemas
SCHEMAS = {
    "general": {
        "name": "general_criteria_response",
        "schema": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "enum": ["Passed", "Not Passed"]
                }
            },
            "required": ["result"],
            "additionalProperties": False
        },
        "strict": True
    },
    "qualification": {
        "name": "qualification_response",
        "schema": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "enum": ["Yes", "No"]
                }
            },
            "required": ["answer"],
            "additionalProperties": False
        },
        "strict": True
    },
    "standard": {
        "name": "standard_criteria_response",
        "schema": {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "enum": ["Passed", "Not Passed", "ND"]
                }
            },
            "required": ["result"],
            "additionalProperties": False
        },
        "strict": True
    }
}

def get_structured_response(prompt_type, information, criterion_or_question, schema_type):
    """Helper function to get structured response from OpenAI"""
    prompt = prompts[prompt_type].format(
        description=information, 
        criterion=criterion_or_question if prompt_type != "qualification" else None,
        question=criterion_or_question if prompt_type == "qualification" else None
    )
    
    # Debug output if enabled
    if DEBUG_OPENAI:
        # Get first 500 chars of information for preview
        info_preview = information[:500] + "..." if len(information) > 500 else information
        log_debug(f"\n===== OPENAI INPUT =====")
        log_debug(f"🔍 Criterion/Question: {criterion_or_question}")
        log_debug(f"📝 Prompt Type: {prompt_type}")
        log_debug(f"💡 Schema Type: {schema_type}")
        log_debug(f"📄 Information Preview: \n{info_preview}")
        log_debug(f"========================\n")
    
    try:
        result_json = ask_openai_structured(prompt, SCHEMAS[schema_type])
        result_key = "answer" if schema_type == "qualification" else "result"
        return result_json[result_key], None
    except Exception as e:
        return None, str(e)

def check_general_criteria(description, info, general_criteria):
    """Check general criteria for a company"""
    all_passed = True
    for criterion in general_criteria:
        log_info(f"🧪 General: {criterion}", console=False)
        result, error = get_structured_response("general", description, criterion, "general")
        
        if error:
            log_error(f"❌ Error General: {error}")
            info[f"General_Skipped_{criterion}"] = "Error"
            all_passed = False
        else:
            log_info(f"➡️  {result}", console=False)
            key = f"General_{'Passed' if result == 'Passed' else 'Skipped'}_{criterion}"
            info[key] = result
            if result != "Passed":
                all_passed = False
                
    return all_passed

def check_qualification_questions(description, company_info, qualification_questions):
    """Check qualification questions for a company"""
    for audience, question in qualification_questions.items():
        log_info(f"🔍 Qualification [{audience}]: {question}", console=False)
        result, error = get_structured_response("qualification", description, question, "qualification")
        
        if error:
            log_error(f"❌ Error Qualification {audience}: {error}")
            company_info[f"Qualification_{audience}"] = "ND"
        else:
            log_info(f"➡️  {result}", console=False)
            company_info[f"Qualification_{audience}"] = result

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

def check_nth_criteria(description, company_info, audience, nth_df):
    """Check NTH criteria for an audience - updated for manager requirements"""
    filtered_df = nth_df[nth_df["Target Audience"] == audience]
    passed_count = 0
    nd_count = 0
    total = 0
    
    log_info(f"✨ Начинаем проверку {len(filtered_df)} NTH критериев для {audience}", console=False)
    
    # НОВОЕ ТРЕБОВАНИЕ: Обрабатывать ВСЕ NTH критерии независимо от результатов
    for _, row in filtered_df.iterrows():
        crit = row["Criteria"]
        place = row.get("Place", "gen_descr")
        search_query = row.get("Search Query", None)
        
        log_info(f"✨ NTH {audience}: {crit}", console=False)
        
        # Get information based on the Place field
        information, source_desc = get_information_for_criterion(company_info, place, search_query)
        log_info(f"🔍 Источник: {source_desc}", console=False)
        
        result, error = get_structured_response("nth", information, crit, "standard")
        
        if error:
            log_error(f"❌ Ошибка NTH {audience} {crit}: {error}")
            company_info[f"NTH_{audience}_{crit}"] = "Error"
            # Считаем ошибки как ND
            nd_count += 1
        else:
            log_info(f"➡️  {result}", console=False)
            company_info[f"NTH_{audience}_{crit}"] = result
            
            if result == "Passed":
                passed_count += 1
                log_info(f"✅ NTH критерий пройден", console=False)
            elif result == "ND":
                nd_count += 1
                log_info(f"❓ Недостаточно данных для NTH критерия", console=False)
            else:
                log_info(f"❌ NTH критерий не пройден", console=False)
        
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
        
        log_info(f"📊 NTH Статистика для {audience}:", console=False)
        log_info(f"   Пройдено: {passed_count}/{total} ({success_rate:.1%})", console=False)
        log_info(f"   ND: {nd_count}/{total} ({nd_rate:.1%})", console=False)
    
    return None 