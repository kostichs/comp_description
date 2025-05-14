import json
import pandas as pd
from typing import List, Dict, Any
import os

class ResultProcessor:
    @staticmethod
    def save_to_json(results: List[Dict[str, Any]], output_file: str) -> None:
        """
        Сохраняет результаты в JSON-файл.
        
        Args:
            results: Список результатов поиска
            output_file: Путь к файлу для сохранения
        """
        # Создаем директорию, если не существует
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"Результаты сохранены в JSON: {output_file}")
            
    @staticmethod
    def save_to_excel(results: List[Dict[str, Any]], output_file: str) -> None:
        """
        Сохраняет результаты в Excel-файл.
        
        Args:
            results: Список результатов поиска
            output_file: Путь к файлу для сохранения
        """
        # Создаем директорию, если не существует
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Формируем данные для DataFrame
        data = []
        for r in results:
            # Базовая информация о компании
            row = {
                'Company': r['company'],
                'Success': r['successful'],
                'Sources': ', '.join([res['source'] for res in r['results'] if res.get('result') is not None]),
                'Results': ', '.join([str(res['result']) for res in r['results'] if res.get('result') is not None])
            }
            
            # Добавляем детальную информацию по каждому источнику
            for res in r['results']:
                if res.get('result') is not None:
                    row[f"Source: {res['source']}"] = str(res['result'])
                    
            # Добавляем описание, если есть
            if 'description' in r:
                row['Description'] = r['description']
                
            data.append(row)
        
        # Создаем DataFrame и сохраняем
        df = pd.DataFrame(data)
        df.to_excel(output_file, index=False)
        
        print(f"Результаты сохранены в Excel: {output_file}")
            
    @staticmethod
    def print_stats(results: List[Dict[str, Any]]) -> None:
        """
        Выводит статистику по результатам поиска.
        
        Args:
            results: Список результатов поиска
        """
        # Общая статистика
        total = len(results)
        successful = sum(1 for r in results if r['successful'])
        
        # Статистика по источникам
        sources = {}
        for r in results:
            for res in r['results']:
                if res.get('result') is not None:
                    source = res['source']
                    sources[source] = sources.get(source, 0) + 1
        
        # Вывод результатов
        print("\n=== Статистика поиска ===")
        print(f"Всего компаний: {total}")
        print(f"Успешно найдено: {successful} ({successful/total*100:.1f}%)")
        print("\nПо источникам:")
        for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
            print(f"- {source}: {count} ({count/total*100:.1f}%)")
            
        # Если есть ошибки, показываем их количество
        errors = sum(1 for r in results for res in r['results'] if 'error' in res)
        if errors > 0:
            print(f"\nОшибок при поиске: {errors}")
            
    @staticmethod
    def filter_by_source(results: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
        """
        Фильтрует результаты по конкретному источнику.
        
        Args:
            results: Список результатов поиска
            source: Название источника для фильтрации
            
        Returns:
            list: Отфильтрованный список результатов
        """
        filtered = []
        for r in results:
            for res in r['results']:
                if res['source'] == source and res.get('result') is not None:
                    filtered.append({
                        'company': r['company'],
                        'source': source,
                        'result': res['result']
                    })
                    break
        
        return filtered 