# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Устанавливаем переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Копируем файл с зависимостями
COPY requirements.txt .

# Обновляем pip и устанавливаем зависимости
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию
# (бэкенд, фронтенд и другие необходимые файлы)
COPY ./backend /app/backend
COPY ./frontend /app/frontend
COPY ./src /app/src
COPY ./description_generator /app/description_generator
COPY ./finders /app/finders
COPY llm_config.yaml /app/llm_config.yaml
COPY utils.py /app/utils.py
# Если есть другие директории или файлы в корне, которые нужны, их тоже нужно скопировать
# Например, если `main.py` или другие важные скрипты находятся в корне, а не в ./backend
# COPY main.py . 

# Открываем порт, на котором будет работать приложение
EXPOSE 8000

# Команда для запуска приложения
# Убедитесь, что путь к `backend.main:app` корректный относительно WORKDIR /app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"] 