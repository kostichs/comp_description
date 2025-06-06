"""
OpenAI API client
"""

import time
from openai import OpenAI
from src.utils.config import OPENAI_API_KEY
from src.utils.logging import log_debug, log_error, log_info

def get_openai_response(prompt, max_tokens=500, model="gpt-3.5-turbo"):
    """Get response from OpenAI API with retry logic"""
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
            
            return result
            
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                log_info(f"⏳ Rate limit - ждем {wait_time} секунд...")
                time.sleep(wait_time)
                continue
            elif attempt < max_retries - 1:
                log_error(f"⚠️ Попытка {attempt + 1} неудачна: {e}")
                time.sleep(2)
                continue
            else:
                log_error(f"❌ Ошибка OpenAI API после {max_retries} попыток: {e}")
                raise 