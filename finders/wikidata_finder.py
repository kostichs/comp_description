from .base import Finder
import requests
import re

class WikidataFinder(Finder):
    async def find(self, company_name: str, **context) -> dict:
        """
        Ищет URL компании через Wikidata SPARQL запрос.
        
        Args:
            company_name: Название компании
            
        Returns:
            dict: Результат поиска {"source": "wikidata", "result": url или None}
        """
        url = self._get_wikidata_url(company_name)
        return {"source": "wikidata", "result": url}
        
    def _get_wikidata_url(self, company_name: str) -> str | None:
        """
        Получает официальный URL компании из Wikidata через SPARQL.
        
        Args:
            company_name: Название компании
            
        Returns:
            str | None: URL компании или None, если не найден
        """
        # Формируем SPARQL запрос
        query = f"""
        SELECT ?company ?url WHERE {{
          ?company rdfs:label "{company_name}"@en;
                   wdt:P856 ?url.
        }}
        """
        
        # URL для SPARQL эндпоинта Wikidata
        url = "https://query.wikidata.org/sparql"
        
        # Заголовки для запроса
        headers = {
            'Accept': 'application/sparql-results+json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            # Отправляем запрос
            response = requests.get(url, params={'query': query}, headers=headers)
            if response.status_code == 200:
                results = response.json()
                # Проверяем, есть ли результаты
                if results.get('results', {}).get('bindings'):
                    # Берем первый URL из результатов
                    return results['results']['bindings'][0]['url']['value']
        except Exception as e:
            print(f"Ошибка при запросе к Wikidata: {e}")
        
        return None 