# Руководство по развертыванию приложения CompanyCanvas с использованием Docker

Это руководство описывает шаги по подготовке Docker-образа вашего FastAPI приложения CompanyCanvas, его тестированию локально и последующему развертыванию на виртуальной машине Ubuntu.

## 1. Подготовка проекта и Docker-файлов локально

Перед началом убедитесь, что ваш проект CompanyCanvas готов, и основная функциональность работает корректно при локальном запуске.

### 1.1. Файл `requirements.txt`

Этот файл должен содержать все Python-зависимости, необходимые для работы вашего приложения в продакшене.
- Если вы используете Poetry, создайте его командой: `poetry export -f requirements.txt --output requirements.txt --without-hashes`
- Если вы используете `pip freeze`: `pip freeze > requirements.txt`. В этом случае **обязательно** просмотрите файл и удалите из него:
    - Пакеты, специфичные для вашей ОС (например, `pywin32`).
    - Пакеты, используемые только для разработки и тестирования (например, `pytest`, `flake8`, `black`, `fastapi-cli`, `watchdog`, `watchfiles`, `typer`, `rich` и т.д.).
    - Ненужные зависимости (например, если случайно попал `Flask` со своими зависимостями, а приложение использует `FastAPI`).

**Ключевые зависимости, которые должны остаться (примерный список):**
`fastapi`, `uvicorn`, `openai`, `python-dotenv`, `aiofiles`, `openpyxl`, `python-multipart`, `requests`, `beautifulsoup4`, `lxml`, `pandas` (если используется для обработки Excel), `scrapingbee` (если используется), `google-search-results` (для Serper, если используется) и другие, непосредственно используемые вашим приложением.

### 1.2. Файл `.dockerignore`

Создайте файл `.dockerignore` в корне проекта, чтобы исключить ненужные файлы и директории из Docker-контекста и образа. Это уменьшит размер образа и ускорит сборку.

Пример содержимого `.dockerignore`:
```
# Git
.git
.gitignore
.gitattributes

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.env
dist/
build/
*.log
output/ # Данные сессий не должны попадать в образ

# Виртуальные окружения
.venv/
venv/
env/

# IDE / Редакторы
.vscode/
.idea/
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# OS specific
.DS_Store
Thumbs.db
```

### 1.3. Файл `Dockerfile`

Создайте файл `Dockerfile` (без расширения) в корне проекта. Этот файл описывает, как будет собираться ваш Docker-образ.

Пример содержимого `Dockerfile`:
```dockerfile
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

# Копируем необходимые директории и файлы проекта в рабочую директорию
COPY ./backend /app/backend
COPY ./frontend /app/frontend
COPY ./src /app/src
# Копируем конфигурационные файлы, если они есть в корне и нужны приложению
COPY llm_config.yaml /app/llm_config.yaml
# Если есть другие важные файлы/директории в корне, добавьте их сюда
# COPY main_script_if_any.py /app/

# Открываем порт, на котором будет работать приложение внутри контейнера
EXPOSE 8000

# Команда для запуска приложения
# Убедитесь, что путь к вашему FastAPI приложению (экземпляру app) корректен
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- **Проверьте пути в командах `COPY`**: они должны соответствовать структуре вашего проекта.
- **Проверьте команду `CMD`**: `backend.main:app` означает, что в директории `backend` есть файл `main.py`, в котором создан экземпляр FastAPI `app = FastAPI()`. Адаптируйте при необходимости.

## 2. Локальная сборка и тестирование Docker-образа

### 2.1. Сборка образа
Откройте терминал в корневой директории вашего проекта и выполните:
```bash
docker build -t company-canvas-app .
```
- `company-canvas-app` - это имя вашего локального образа. Вы можете выбрать другое.
- `.` указывает, что Dockerfile находится в текущей директории.
Если возникнут ошибки, внимательно прочитайте их. Чаще всего они связаны с проблемами в `requirements.txt` или неправильными путями в `Dockerfile`.

### 2.2. Локальный запуск и тестирование контейнера
После успешной сборки запустите контейнер:
```bash
docker run --rm -p 8080:8000 \
  -e OPENAI_API_KEY="ВАШ_OPENAI_КЛЮЧ" \
  -e SCRAPINGBEE_API_KEY="ВАШ_SCRAPINGBEE_КЛЮЧ" \
  -e SERPER_API_KEY="ВАШ_SERPER_КЛЮЧ" \
  company-canvas-app
```
- **Замените плейсхолдеры** (`ВАШ_..._КЛЮЧ`) на ваши реальные API ключи.
- Добавьте другие переменные окружения с флагом `-e ИМЯ_ПЕРЕМЕННОЙ="ЗНАЧЕНИЕ"`, если ваше приложение их требует.
- `--rm`: автоматически удалит контейнер после остановки (удобно для тестов).
- `-p 8080:8000`: пробрасывает порт 8080 вашего компьютера на порт 8000 внутри контейнера.

**Тестирование:**
1. Откройте в браузере `http://localhost:8080`.
2. Убедитесь, что веб-интерфейс загружается.
3. Протестируйте основную функциональность: загрузите файл, запустите обработку.
4. Следите за логами в терминале, где запущен `docker run`. Там не должно быть ошибок, связанных с конфигурацией или API ключами.
5. Убедитесь, что результаты корректны.
6. Чтобы остановить контейнер, нажмите `Ctrl+C` в терминале.

## 3. Публикация Docker-образа на Docker Hub

Это позволит легко скачать образ на ваш сервер.

### 3.1. Создайте аккаунт на Docker Hub
Если у вас его нет, зарегистрируйтесь на [hub.docker.com](https://hub.docker.com/).

### 3.2. Войдите в Docker Hub из терминала
```bash
docker login
```
Введите ваш Docker ID и пароль (или Personal Access Token, если у вас включена 2FA).

### 3.3. Тегируйте локальный образ
Присвойте вашему локальному образу тег в формате `ВАШ_DOCKERHUB_USERNAME/ИМЯ_РЕПОЗИТОРИЯ:ТЕГ`.
```bash
docker tag company-canvas-app ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest
```
- Замените `ВАШ_DOCKERHUB_USERNAME` на ваше имя пользователя.
- `company-canvas-app` после слеша — это имя репозитория, которое будет создано на Docker Hub.
- `latest` — стандартный тег для последней версии.

### 3.4. Загрузите образ на Docker Hub
```bash
docker push ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest
```
Дождитесь завершения загрузки.

## 4. Развертывание Docker-контейнера на Ubuntu VM

Подключитесь к вашей Ubuntu VM по SSH.

### 4.1. Установка Docker Engine (если еще не установлен)
Если команда `docker --version` не найдена или доступна только через `sudo` и ваш пользователь не в группе `docker`:
1. **Установите Docker (официальный метод):**
   ```bash
   sudo apt-get update
   sudo apt-get install ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
   ```
2. **Добавьте вашего пользователя в группу `docker`:**
   ```bash
   sudo usermod -aG docker $USER
   ```
3. **ВАЖНО: Выйдите из SSH-сессии и зайдите снова**, чтобы изменения членства в группе применились.
4. **Проверка после перелогина:**
   ```bash
   docker --version  # Должно работать без sudo
   groups $USER      # Должна быть группа 'docker'
   ```

### 4.2. Скачайте образ с Docker Hub на VM
```bash
docker pull ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest
```
- Замените `ВАШ_DOCKERHUB_USERNAME` на ваше имя пользователя.

### 4.3. Создайте директорию для хранения данных сессий
Эта директория на сервере будет смонтирована в контейнер, чтобы данные сессий не терялись при перезапуске контейнера.
```bash
sudo mkdir -p /srv/company-canvas/output 
# Дайте права на запись (например, вашему пользователю, если он будет запускать docker run)
# Или, если вы запускаете Docker от root (не рекомендуется для docker run без rootless mode), 
# то Docker сможет писать туда. 
# Безопаснее дать права конкретному пользователю или группе docker:
sudo chown -R $USER:$USER /srv/company-canvas/output 
# (Или другой путь, который вы выберете)
```

### 4.4. Настройте брандмауэр UFW
Разрешите входящие соединения на SSH и HTTP.
```bash
sudo ufw allow ssh
sudo ufw allow 80/tcp  # Для HTTP
# sudo ufw allow 443/tcp # Если будете настраивать HTTPS позже
sudo ufw enable        # Включить, если еще не включен
sudo ufw status        # Проверить правила
```

### 4.5. Запустите Docker-контейнер на VM
```bash
docker run -d --restart unless-stopped -p 80:8000 \
  -e OPENAI_API_KEY="ВАШ_РЕАЛЬНЫЙ_OPENAI_КЛЮЧ" \
  -e SCRAPINGBEE_API_KEY="ВАШ_РЕАЛЬНЫЙ_SCRAPINGBEE_КЛЮЧ" \
  -e SERPER_API_KEY="ВАШ_РЕАЛЬНЫЙ_SERPER_КЛЮЧ" \
  --name company-canvas-prod \
  -v /srv/company-canvas/output:/app/output \
  ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest
```
- **Замените плейсхолдеры** для API ключей на ваши реальные значения.
- `-d`: запуск в фоновом (detached) режиме.
- `--restart unless-stopped`: автоматический перезапуск контейнера.
- `-p 80:8000`: проброс порта 80 сервера на порт 8000 контейнера. Приложение будет доступно по IP адресу сервера без указания порта.
- `--name company-canvas-prod`: имя для вашего "боевого" контейнера.
- `-v /srv/company-canvas/output:/app/output`: монтирование директории с данными. Убедитесь, что путь `/srv/company-canvas/output` (или ваш выбранный путь) существует на сервере и права доступа корректны.

## 5. Проверка работы на сервере

1.  **Проверьте статус контейнера:**
    ```bash
    docker ps 
    ```
    Вы должны увидеть контейнер `company-canvas-prod` со статусом `Up ...`.
2.  **Проверьте логи контейнера:**
    ```bash
    docker logs company-canvas-prod
    ```
    Для слежения за логами в реальном времени: `docker logs -f company-canvas-prod` (`Ctrl+C` для выхода).
    Убедитесь, что Uvicorn запустился без ошибок.
3.  **Доступ через браузер:**
    Откройте в браузере `http://ВАШ_IP_АДРЕС_СЕРВЕРА` (например, `http://202.78.163.133`).
    Ваше приложение должно быть доступно.
4.  **Протестируйте функциональность:** Загрузите файл, запустите обработку.
5.  **Проверьте сохранение данных:** Убедитесь, что файлы сессий появляются в директории `/srv/company-canvas/output/sessions/` (или в вашем выбранном пути) на сервере.

## 6. Обновление приложения

Если вы внесли изменения в код и хотите обновить приложение на сервере:
1. Внесите изменения в код локально.
2. Пересоберите Docker-образ локально: `docker build -t company-canvas-app .`
3. Тегируйте новый образ: `docker tag company-canvas-app ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest` (или с новым тегом версии, например, `...:1.0.1`)
4. Загрузите новый образ на Docker Hub: `docker push ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest` (или с новым тегом).
5. **На сервере Ubuntu VM:**
   a. Скачайте обновленный образ: `docker pull ВАШ_DOCKERHUB_USERNAME/company-canvas-app:latest`
   b. Остановите старый контейнер: `docker stop company-canvas-prod`
   c. Удалите старый контейнер: `docker rm company-canvas-prod`
   d. Запустите новый контейнер с теми же параметрами `docker run ...`, используя обновленный образ. (См. пункт 4.5). Данные в смонтированном томе (`-v`) останутся нетронутыми.

**Для более простого управления обновлениями рассмотрите использование Docker Compose.**

Это руководство должно помочь вам в будущем самостоятельно развертывать проект! 

# Краткая инструкция по развертыванию (версия 5)

Это краткое пошаговое руководство для быстрого развертывания приложения без лишних деталей.

## 1. Локальная сборка и публикация образа

```bash
# Залогиньтесь в Docker Hub
docker login

# Соберите локальный образ
docker build -t company-description-app .

# Тегируйте образ с правильным именем репозитория и версией
docker tag company-description-app sergeykostichev/company-canvas-app:v05

# Отправьте образ в Docker Hub
docker push sergeykostichev/company-canvas-app:v05
```

## 2. Развертывание на виртуальной машине

```bash
# Удалите предыдущий контейнер (если есть)
docker rm -f company-canvas-prod

# Скачайте новый образ
docker pull sergeykostichev/company-canvas-app:v05

# Запустите новый контейнер
docker run -d -p 80:8000 --restart unless-stopped --name company-canvas-prod \
  -e OPENAI_API_KEY=ваш_ключ \
  -e SCRAPINGBEE_API_KEY=ваш_ключ \
  -e SERPER_API_KEY=ваш_ключ \
  -v /srv/company-canvas/output:/app/output \
  sergeykostichev/company-canvas-app:v05
```

## 3. Проверка работы

```bash
# Проверьте работающие контейнеры
docker ps

# Проверьте логи контейнера
docker logs company-canvas-prod
```

Теперь приложение должно быть доступно по IP-адресу виртуальной машины на порту 80.

## 4. Информация о веб-интерфейсе

- Веб-интерфейс автоматически обновляет таблицу результатов каждые 2 секунды
- Параметр обновления находится в файле `frontend/app.js` (строка 326, значение 2000 ms)
- При успешной обработке таблица автоматически отобразит результаты 