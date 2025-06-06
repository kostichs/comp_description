"""
Модуль для проверки квалификационных критериев
"""

from src.external.openai_client import get_openai_response
from src.utils.logging import log_info, log_debug

def check_qualification_questions(description, company_info, qualification_questions):
    """Check qualification questions for a company - batch processing"""
    log_debug(f"🔍 Проверяем {len(qualification_questions)} квалификационных вопросов одним запросом")
    
    # Create batch prompt for all questions
    questions_list = "\n".join([f"{i+1}. {audience}: {question}" 
                               for i, (audience, question) in enumerate(qualification_questions.items())])
    
    prompt = f"""
Analyze this company description and answer the following qualification questions.
For each question, respond with only "Yes" or "No".

Company Description: {description}

Questions:
{questions_list}

Response format (one line per question):
1. Yes/No
2. Yes/No
3. Yes/No
... etc
"""
    
    try:
        response = get_openai_response(prompt, max_tokens=200)
        lines = response.strip().split('\n')
        
        qualified_count = 0
        
        for i, (audience, question) in enumerate(qualification_questions.items()):
            if i < len(lines):
                line = lines[i].strip()
                result = "Yes" if "yes" in line.lower() else "No"
            else:
                result = "No"
            
            company_info[f"Qualification_{audience}"] = result  # Оставляем только для временной логики
            
            if result == "Yes":
                qualified_count += 1
                log_debug(f"   ✅ {audience}: {result}")
            else:
                log_debug(f"   ❌ {audience}: {result}")
                
    except Exception as e:
        log_debug(f"   ⚠️ Ошибка батчевой проверки: {e}")
        for audience in qualification_questions.keys():
            company_info[f"Qualification_{audience}"] = "ND"
        qualified_count = 0
    
    log_info(f"Квалификация: {qualified_count}/{len(qualification_questions)} аудиторий")
    
    return qualified_count > 0 