from .base import Finder
from openai import AsyncOpenAI

class LLMSearchFinder(Finder):
    def __init__(self, api_key: str):
        """
        Initialize the finder with OpenAI API key.
        
        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        
    async def find(self, company_name: str, **context) -> dict:
        """
        Use LLM to search for company information.
        
        Args:
            company_name: Company name
            context: Additional context
            
        Returns:
            dict: Search result {"source": "llm_search", "result": information or None}
        """
        result = await self._ask_llm_search_model(company_name)
        return {"source": "llm_search", "result": result}
        
    async def _ask_llm_search_model(self, company_name: str) -> str | None:
        """
        Запрашивает у LLM информацию о компании.
        
        Args:
            company_name: Название компании
            
        Returns:
            str | None: Информация о компании или None в случае ошибки
        """
        try:
            system_prompt = """You are a helpful assistant that provides information about companies.
Your task is to provide the most likely official website URL of the company based on your knowledge.
If you don't know the website, respond with "I don't know" and nothing else.
Always verify that your answer is the official company website and not just any website related to the company.
Only provide the URL, no additional explanation or text."""

            user_prompt = f"What is the official website URL of {company_name}?"
            
            response = await self.client.chat.completions.create(
                model="gpt-4",  # Используем более мощную модель, которая может иметь знания о компаниях
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=100
            )
            
            answer = response.choices[0].message.content.strip()
            
            # Если LLM не знает ответа, возвращаем None
            if "I don't know" in answer.lower() or not answer:
                return None
                
            return answer
            
        except Exception as e:
            print(f"Ошибка при использовании LLM: {e}")
            return None 