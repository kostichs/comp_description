from abc import ABC, abstractmethod

class Finder(ABC):
    @abstractmethod
    async def find(self, company_name: str, **context) -> dict:
        """
        Находит информацию о компании и возвращает результат.
        
        Args:
            company_name: Название компании для поиска
            context: Дополнительный контекст (сессия, API-ключи и т.д.)
            
        Returns:
            dict: Словарь с информацией в формате 
                 {'source': 'название_источника', 'result': результат_или_None}
        """
        pass 