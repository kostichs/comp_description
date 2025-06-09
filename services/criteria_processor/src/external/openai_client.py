"""
OpenAI API client with Circuit Breaker integration
"""

import time
from openai import OpenAI
from src.utils.config import OPENAI_API_KEY, CIRCUIT_BREAKER_CONFIG
from src.utils.logging import log_debug, log_error, log_info

def get_openai_response(prompt, max_tokens=500, model="gpt-3.5-turbo"):
    """Get response from OpenAI API with Circuit Breaker and retry logic"""
    # Import circuit breaker here to avoid circular imports
    if CIRCUIT_BREAKER_CONFIG['enable_circuit_breaker']:
        from src.utils.circuit_breaker import get_circuit_breaker, CircuitOpenException
        circuit_breaker = get_circuit_breaker()
        
        # Check if circuit breaker allows execution
        if not circuit_breaker.can_execute():
            state_info = circuit_breaker.get_state_info()
            retry_after = state_info.get('time_until_retry', 0)
            raise CircuitOpenException(
                f"🔴 Circuit Breaker OPEN - OpenAI запросы заблокированы на {retry_after:.1f}s", 
                retry_after=retry_after
            )
    else:
        circuit_breaker = None
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            log_debug(f"🤖 OpenAI запрос: {prompt[:100]}...")
            
            # Initialize client inside function
            client = OpenAI(api_key=OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            log_debug(f"🤖 OpenAI ответ: {result}")
            
            # Record success in circuit breaker
            if circuit_breaker:
                circuit_breaker.record_success()
            
            return result
            
        except Exception as e:
            # Record failure in circuit breaker (only for rate limit errors)
            if circuit_breaker:
                is_rate_limit = circuit_breaker.record_failure(e)
                if is_rate_limit:
                    log_error(f"🛡️ Rate limit ошибка записана в Circuit Breaker")
            
            # Original retry logic with enhanced rate limit detection
            error_str = str(e).lower()
            is_rate_limit = any(keyword in error_str for keyword in 
                              CIRCUIT_BREAKER_CONFIG['rate_limit_keywords'])
            
            if is_rate_limit and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                log_info(f"⏳ Rate limit detected - ждем {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            elif attempt < max_retries - 1:
                log_error(f"⚠️ Попытка {attempt + 1} неудачна: {e}")
                time.sleep(2)
                continue
            else:
                log_error(f"❌ Ошибка OpenAI API после {max_retries} попыток: {e}")
                raise 