import logging
import os
from pathlib import Path
import time
import sys

def setup_logger(logger_name='pipeline_app', 
                 log_level=logging.INFO, 
                 log_directory="output/logs", # Относительно корня проекта
                 log_to_console=True,
                 log_to_file=True,
                 project_root_path=None):
    """
    Настраивает и возвращает кастомный логгер.

    Args:
        logger_name (str): Имя логгера.
        log_level (int): Уровень логирования (например, logging.INFO, logging.DEBUG).
        log_directory (str): Директория для сохранения файлов логов (относительно корня проекта).
        log_to_console (bool): Включить ли вывод логов в консоль.
        log_to_file (bool): Включить ли запись логов в файл.
        project_root_path (Path, optional): Абсолютный путь к корню проекта. 
                                            Если None, пытается определить автоматически.
    """
    logger = logging.getLogger(logger_name)
    
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(log_level)
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    if project_root_path is None:
        # Попытка определить корень проекта (может потребовать доработки в зависимости от структуры)
        try:
            # Если этот файл logger_config.py находится в src/
            current_file_path = Path(__file__).resolve()
            project_root_path = current_file_path.parent.parent # src -> project_root
        except NameError: # __file__ не определен, если код выполняется интерактивно без файла
            project_root_path = Path.cwd() # Используем текущую рабочую директорию как fallback

    if log_to_file:
        log_dir_abs_path = project_root_path / log_directory
        log_dir_abs_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file_path = log_dir_abs_path / f"{logger_name.replace('.', '_')}_{timestamp}.log"
        
        file_handler = logging.FileHandler(log_file_path, mode='w', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # print(f"INFO: Логирование в файл включено: {log_file_path}") # Для начальной отладки

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout) # Явно указываем sys.stdout
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        # print(f"INFO: Логирование в консоль для '{logger_name}' включено.") # Для начальной отладки

    logger.propagate = False
    return logger

if __name__ == '__main__':
    # Пример настройки пути к корню проекта, если запускаем logger_config.py напрямую
    # Это нужно, чтобы output/logs создавался относительно корня проекта, а не src/output/logs
    example_project_root = Path(__file__).resolve().parent.parent

    # Тестирование основного логгера
    main_logger = setup_logger('my_main_app', log_level=logging.DEBUG, project_root_path=example_project_root)
    main_logger.debug("Это debug сообщение от my_main_app.")
    main_logger.info("Это info сообщение от my_main_app.")

    # Тестирование логгера для компонента
    component_logger = setup_logger('my_main_app.component_x', log_level=logging.DEBUG, project_root_path=example_project_root)
    component_logger.debug("Это debug сообщение от my_main_app.component_x.")
    component_logger.info("Это info сообщение от my_main_app.component_x.")

    # Проверка, что они разные и не дублируют сообщения (из-за propagate=False)
    main_logger.info("Еще одно info сообщение от my_main_app (после настройки component_logger).") 