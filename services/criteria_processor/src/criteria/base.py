"""
Базовые функции для проверки критериев
"""

from src.external.openai_client import get_openai_response
from src.utils.logging import log_debug, log_error

def get_structured_response(criteria_type, information, criteria_text, format_type="standard"):
    """Get structured response for criteria evaluation"""
    try:
        prompt = f"""
Analyze the following information and determine if it meets this criterion:

Information: {information}
Criterion: {criteria_text}

Respond with exactly one of: "Passed", "Not Passed", or "ND" (if insufficient data).
"""

        response = get_openai_response(prompt, max_tokens=20)
        
        # Clean up response
        result = response.strip()
        if "passed" in result.lower() and "not" not in result.lower():
            return "Passed", None
        elif "not passed" in result.lower():
            return "Not Passed", None  
        elif "nd" in result.lower():
            return "ND", None
        else:
            return "ND", None
            
    except Exception as e:
        log_error(f"❌ Ошибка получения ответа: {e}")
        return "ND", str(e) 