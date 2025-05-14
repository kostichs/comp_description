from openai import AsyncOpenAI
from typing import List, Dict, Any

class DescriptionGenerator:
    def __init__(self, api_key: str):
        """
        Инициализирует генератор описаний с API ключом для OpenAI.
        
        Args:
            api_key: API ключ для OpenAI
        """
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        
    async def generate_description(self, company_name: str, findings: List[Dict[str, Any]]) -> str:
        """
        Генерирует описание компании на основе найденных данных.
        
        Args:
            company_name: Название компании
            findings: Список результатов от различных финдеров
            
        Returns:
            str: Сгенерированное описание компании
        """
        # Подготовка данных для LLM
        data_points = []
        llm_deep_search_report = None
        
        for finding in findings:
            source = finding.get("source", "")
            result = finding.get("result")
            
            if not result:
                continue
                
            # Если это отчет от LLM Deep Search, сохраняем его отдельно
            if source == "llm_deep_search":
                llm_deep_search_report = result
                data_points.append(f"Source: {source}, Result: подробный отчет от LLM Deep Search (сохранен отдельно)")
            else:
                data_points.append(f"Source: {source}, Result: {result}")
                
        if not data_points and not llm_deep_search_report:
            return f"Недостаточно данных для генерации описания компании {company_name}."
            
        # Формирование промпта для LLM
        system_prompt = """Ты - эксперт по созданию деловых профилей компаний. 
Твоя задача - создавать краткие, информативные и объективные описания компаний,
основываясь на предоставленных источниках данных.

Описание должно быть:
1. Профессиональным и нейтральным по тону
2. Информативным и точным, с конкретными фактами о компании
3. Хорошо структурированным, освещая:
   - Основную деятельность компании
   - Ключевые продукты/услуги
   - Географию присутствия
   - Финансовые показатели (если доступны)
   - Важные клиенты/рынки/технологии
4. Длиной 3-5 предложений

Избегай:
- Субъективных оценок или рекламных утверждений
- Непроверенной информации
- Избыточных деталей
- Повторения одной и той же информации из разных источников

Ответ должен быть кратким профессиональным описанием на русском языке."""
        
        # Создаем разные варианты промпта в зависимости от наличия отчета от LLM Deep Search
        if llm_deep_search_report:
            user_prompt = f"""Создай краткое деловое описание компании {company_name} на основе следующих данных.

Основной отчет (содержит наиболее полную информацию):
{llm_deep_search_report}

Дополнительные источники информации:
{chr(10).join(data_points)}

Описание должно быть информативным, лаконичным и профессиональным, длиной 3-5 предложений на русском языке. 
Сфокусируйся на фактической информации о компании - сфере деятельности, продуктах, клиентах, географии и т.д."""
        else:
            user_prompt = f"""Создай краткое деловое описание компании {company_name} на основе следующих данных:

{chr(10).join(data_points)}

Описание должно быть информативным, лаконичным и профессиональным, длиной 3-5 предложений на русском языке."""
        
        # Вызов LLM для генерации описания
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Ошибка при генерации описания: {e}")
            return f"Не удалось сгенерировать описание для {company_name}: {str(e)}"
    
    async def generate_batch_descriptions(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Генерирует описания для списка результатов поиска компаний.
        
        Args:
            results: Список результатов поиска компаний
            
        Returns:
            list: Список результатов с добавленными описаниями
        """
        enriched_results = []
        
        for result in results:
            if result.get("successful"):
                description = await self.generate_description(
                    result["company"], 
                    result["results"]
                )
                result["description"] = description
            else:
                result["description"] = f"Недостаточно данных для генерации описания компании {result['company']}."
                
            enriched_results.append(result)
            
        return enriched_results