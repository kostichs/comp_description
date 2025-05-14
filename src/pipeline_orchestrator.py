import asyncio
import aiohttp
import os
import sys
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import logging # Импорт модуля logging

# Определение project_root в начале файла, чтобы он был доступен глобально в этом модуле
project_root = Path(__file__).resolve().parent.parent

# Импорт logger_config (должен быть после определения project_root, если logger_config его использует)
if str(project_root / 'src') not in sys.path:
     sys.path.insert(0, str(project_root / 'src'))
try:
    from logger_config import setup_logger
except ImportError as e:
    print(f"CRITICAL: Не удалось импортировать setup_logger из src/logger_config.py: {e}")
    # Базовый логгер, если setup_logger не удалось импортировать
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("fallback_orchestrator_logger")
    logger.critical(f"Не удалось импортировать setup_logger: {e}. Используется базовый логгер.")
    # sys.exit(1) # Решаем, нужно ли падать или работать с базовым логгером
    # Пока что продолжим с базовым, но это не идеальный вариант
else:
    # Настройка основного логгера для оркестратора
    # project_root уже определен выше
    logger = setup_logger('pipeline_orchestrator', log_level=logging.INFO, project_root_path=project_root)
    chf_logger = setup_logger('company_homepage_finder', log_level=logging.DEBUG, project_root_path=project_root)

# Добавляем корневую директорию проекта в sys.path для импорта CompanyHomepageFinder
# Ожидается, что company_homepage_finder.py находится в корне проекта,
# а этот скрипт (pipeline_orchestrator.py) находится в папке src.
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Теперь можно импортировать из company_homepage_finder.py
try:
    from company_homepage_finder import CompanyHomepageFinder, load_company_names
except ImportError as e:
    logger.critical(f"Ошибка импорта CompanyHomepageFinder или load_company_names: {e}")
    logger.critical(f"Убедитесь, что company_homepage_finder.py находится в {project_root} и доступен для импорта.")
    sys.exit(1)

class PipelineOrchestrator:
    def __init__(self, batch_size=10):
        self.batch_size = batch_size
        load_dotenv(dotenv_path=project_root / '.env') # Ищем .env в корне проекта
        
        serper_api_key = os.getenv("SERPER_API_KEY")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not serper_api_key:
            logger.warning("SERPER_API_KEY не найден в .env. HomepageFinder может быть ограничен.")
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY не найден в .env. HomepageFinder (LLM) может быть ограничен.")

        # Передаем chf_logger в CompanyHomepageFinder
        self.homepage_finder = CompanyHomepageFinder(serper_api_key, openai_api_key, logger=chf_logger)

    async def _process_single_company(self, company_name: str, session: aiohttp.ClientSession):
        """
        Обрабатывает одну компанию, находя ее домашнюю страницу.
        aiohttp.ClientSession здесь для будущего использования компонентами, которым он нужен.
        CompanyHomepageFinder использует свои внутренние сессии.
        """
        logger.debug(f"Начало обработки компании: {company_name}")
        try:
            # CompanyHomepageFinder.find_official_website теперь синхронная в своей обертке,
            # но внутри использует asyncio для некоторых операций.
            # Для вызова из асинхронного _process_single_company, если бы find_official_website
            # была полностью асинхронной и мы бы хотели передать сессию, то это выглядело бы иначе.
            # Текущий CompanyHomepageFinder.find_official_website является async.
            url, method = await self.homepage_finder.find_official_website(company_name)
            
            logger.debug(f"Результат для {company_name}: URL={url}, Метод={method}")
            return {"name": company_name, "homepage_url": url, "homepage_method": method}
        except Exception as e:
            logger.error(f"Ошибка при обработке компании {company_name}: {e}", exc_info=True)
            return {"name": company_name, "homepage_url": "Error", "homepage_method": str(e)}

    async def run(self, company_list_path: str, output_csv_path: str):
        """
        Запускает пайплайн: загружает компании, обрабатывает их и сохраняет результаты.
        """
        logger.info(f"Запуск пайплайна. Входной файл: {company_list_path}, Выходной CSV: {output_csv_path}")
        companies = load_company_names(Path(company_list_path))
        if not companies:
            logger.error(f"Компании не загружены из файла: {company_list_path}")
            return

        total_companies = len(companies)
        logger.info(f"Загружено {total_companies} компаний для обработки. Размер батча: {self.batch_size}")
        
        output_path = Path(output_csv_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        processed_count = 0
        header_written = False

        async with aiohttp.ClientSession() as session: 
            for i in range(0, total_companies, self.batch_size):
                batch_companies = companies[i:i + self.batch_size]
                batch_number = (i // self.batch_size) + 1
                logger.info(f"Обработка батча {batch_number} ({len(batch_companies)} компаний)...")

                tasks = [self._process_single_company(name, session) for name in batch_companies]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_processed_results = []
                for j, result_or_exc in enumerate(results):
                    company_name_in_batch = batch_companies[j]
                    if isinstance(result_or_exc, Exception):
                        logger.error(f"Исключение в батче {batch_number} для '{company_name_in_batch}': {result_or_exc}", exc_info=True)
                        batch_processed_results.append({"name": company_name_in_batch, "homepage_url": "ExceptionInBatch", "homepage_method": str(result_or_exc)})
                    elif isinstance(result_or_exc, dict):
                        batch_processed_results.append(result_or_exc)
                    else:
                        logger.warning(f"Неожиданный тип результата в батче {batch_number} для '{company_name_in_batch}': {type(result_or_exc)}")
                        batch_processed_results.append({"name": company_name_in_batch, "homepage_url": "UnknownResultTypeInBatch", "homepage_method": str(type(result_or_exc))})
                
                if batch_processed_results:
                    df_batch = pd.DataFrame(batch_processed_results)
                    try:
                        if not header_written:
                            df_batch.to_csv(output_path, index=False, encoding='utf-8', mode='w') # mode='w' для первого батча
                            header_written = True
                            logger.info(f"Записан первый батч с заголовками в: {output_path}")
                        else:
                            df_batch.to_csv(output_path, index=False, encoding='utf-8', mode='a', header=False) # mode='a', header=False для последующих
                            logger.info(f"Добавлен батч в: {output_path}")
                    except Exception as e:
                        logger.error(f"Ошибка при сохранении батча в CSV: {e}", exc_info=True)
                else:
                    logger.info(f"Батч {batch_number} не дал результатов для сохранения.")
                
                processed_count += len(batch_companies)
                logger.info(f"Завершен батч {batch_number}. Всего обработано: {processed_count}/{total_companies}")

        logger.info(f"Пайплайн завершил обработку всех компаний. Результаты в {output_path}")

async def main():
    logger.info("Запуск Pipeline Orchestrator...")
    # Определение путей. Для input/part2.xlsx, company_homepage_finder.py создает его при первом запуске.
    # Убедитесь, что директория 'input' существует в корне проекта.
    # Убедитесь, что .env файл с API ключами существует в корне проекта.
    
    current_script_dir = Path(__file__).parent
    input_file = project_root / "input" / "part2.xlsx" # Ожидаем input/part2.xlsx в корне проекта
    output_file = project_root / "output" / "orchestrator_homepage_results.csv" # output/ в корне проекта

    # Создаем директорию input и пример файла, если их нет (аналогично company_homepage_finder.py)
    input_dir_for_orchestrator = project_root / "input"
    if not input_dir_for_orchestrator.exists():
        try:
            input_dir_for_orchestrator.mkdir(parents=True, exist_ok=True)
            logger.info(f"Создана папка '{input_dir_for_orchestrator}'.")
        except Exception as e:
            logger.error(f"Не удалось создать папку '{input_dir_for_orchestrator}': {e}", exc_info=True)
            return

    if not input_file.exists():
        logger.warning(f"Файл '{input_file}' не найден. Создается пример файла...")
        try:
            example_data = {'Company Name': ['Google', 'Microsoft', 'Apple', 'NonExistent123XYZ', 'Wikimedia Foundation']}
            example_df = pd.DataFrame(example_data)
            example_df.to_excel(input_file, index=False)
            logger.info(f"Создан пример файла: {input_file} с тестовыми данными.")
        except Exception as e:
            logger.error(f"Не удалось создать пример файла {input_file}: {e}", exc_info=True)
            logger.error(f"Пожалуйста, создайте файл '{input_file}' вручную с колонкой 'Company Name'.")
            return
            
    orchestrator = PipelineOrchestrator(batch_size=5) # Пример размера батча
    await orchestrator.run(str(input_file), str(output_file))
    logger.info("Pipeline Orchestrator завершил работу.")

if __name__ == "__main__":
    # Для Windows может потребоваться особая политика для asyncio
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main()) 