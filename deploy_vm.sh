#!/bin/bash
# Bash скрипт для развертывания Company Canvas на VM
# Автор: AI Assistant
# Версия: 1.0

# Параметры по умолчанию
VERSION="v07"
DOCKER_HUB_USER="sergeykostichev"
IMAGE_NAME="company-canvas-app"
CONTAINER_NAME="company-canvas-prod"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log_info() {
    echo -e "${CYAN}$1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}! $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Проверка параметров
if [ "$1" != "" ]; then
    VERSION="$1"
fi

FULL_IMAGE_NAME="$DOCKER_HUB_USER/$IMAGE_NAME:$VERSION"

echo -e "${GREEN}=== Развертывание Company Canvas на VM ===${NC}"
echo -e "${YELLOW}Версия: $VERSION${NC}"
echo -e "${YELLOW}Полное имя образа: $FULL_IMAGE_NAME${NC}"

# 1. Проверка Docker
log_info "\n1. Проверка Docker..."
if ! command -v docker &> /dev/null; then
    log_error "Docker не найден! Установите Docker."
    exit 1
fi

DOCKER_VERSION=$(docker --version)
log_success "Docker найден: $DOCKER_VERSION"

# 2. Остановка и удаление старого контейнера
log_info "\n2. Остановка старого контейнера..."
if docker ps -q --filter "name=$CONTAINER_NAME" | grep -q .; then
    docker stop $CONTAINER_NAME
    log_success "Контейнер $CONTAINER_NAME остановлен"
else
    log_warning "Контейнер $CONTAINER_NAME не запущен"
fi

if docker ps -aq --filter "name=$CONTAINER_NAME" | grep -q .; then
    docker rm $CONTAINER_NAME
    log_success "Контейнер $CONTAINER_NAME удален"
else
    log_warning "Контейнер $CONTAINER_NAME не найден"
fi

# 3. Удаление старых образов (опционально)
log_info "\n3. Очистка старых образов..."
OLD_IMAGES=$(docker images --filter "repository=$DOCKER_HUB_USER/$IMAGE_NAME" --format "{{.Repository}}:{{.Tag}}" | grep -v "$VERSION" || true)
if [ ! -z "$OLD_IMAGES" ]; then
    echo "$OLD_IMAGES" | xargs docker rmi 2>/dev/null || true
    log_success "Старые образы удалены"
else
    log_warning "Старые образы не найдены"
fi

# 4. Скачивание нового образа
log_info "\n4. Скачивание образа $FULL_IMAGE_NAME..."
if docker pull $FULL_IMAGE_NAME; then
    log_success "Образ скачан успешно"
else
    log_error "Ошибка скачивания образа!"
    exit 1
fi

# 5. Создание директории для данных
log_info "\n5. Подготовка директорий..."
sudo mkdir -p /srv/company-canvas/output
sudo chown -R $USER:$USER /srv/company-canvas/output
log_success "Директории подготовлены"

# 6. Проверка переменных окружения
log_info "\n6. Проверка переменных окружения..."
if [ -z "$OPENAI_API_KEY" ]; then
    log_warning "OPENAI_API_KEY не установлен. Добавьте его вручную в команду запуска."
fi
if [ -z "$SERPER_API_KEY" ]; then
    log_warning "SERPER_API_KEY не установлен. Добавьте его вручную в команду запуска."
fi
if [ -z "$SCRAPINGBEE_API_KEY" ]; then
    log_warning "SCRAPINGBEE_API_KEY не установлен. Добавьте его вручную в команду запуска."
fi

# 7. Запуск нового контейнера
log_info "\n7. Запуск нового контейнера..."

# Формируем команду запуска
DOCKER_CMD="docker run -d --restart unless-stopped -p 80:8000"
DOCKER_CMD="$DOCKER_CMD --name $CONTAINER_NAME"
DOCKER_CMD="$DOCKER_CMD -v /srv/company-canvas/output:/app/output"

# Добавляем переменные окружения если они установлены
if [ ! -z "$OPENAI_API_KEY" ]; then
    DOCKER_CMD="$DOCKER_CMD -e OPENAI_API_KEY=\"$OPENAI_API_KEY\""
fi
if [ ! -z "$SERPER_API_KEY" ]; then
    DOCKER_CMD="$DOCKER_CMD -e SERPER_API_KEY=\"$SERPER_API_KEY\""
fi
if [ ! -z "$SCRAPINGBEE_API_KEY" ]; then
    DOCKER_CMD="$DOCKER_CMD -e SCRAPINGBEE_API_KEY=\"$SCRAPINGBEE_API_KEY\""
fi
if [ ! -z "$HUBSPOT_API_KEY" ]; then
    DOCKER_CMD="$DOCKER_CMD -e HUBSPOT_API_KEY=\"$HUBSPOT_API_KEY\""
fi
if [ ! -z "$HUBSPOT_BASE_URL" ]; then
    DOCKER_CMD="$DOCKER_CMD -e HUBSPOT_BASE_URL=\"$HUBSPOT_BASE_URL\""
fi

DOCKER_CMD="$DOCKER_CMD -e DEBUG=\"false\""
DOCKER_CMD="$DOCKER_CMD $FULL_IMAGE_NAME"

# Выводим команду для справки
echo -e "${CYAN}Команда запуска:${NC}"
echo "$DOCKER_CMD"

# Если переменные окружения не установлены, показываем пример
if [ -z "$OPENAI_API_KEY" ] || [ -z "$SERPER_API_KEY" ] || [ -z "$SCRAPINGBEE_API_KEY" ]; then
    echo ""
    log_warning "Некоторые переменные окружения не установлены!"
    echo "Выполните команду с вашими API ключами:"
    echo ""
    echo "docker run -d --restart unless-stopped -p 80:8000 \\"
    echo "  -e OPENAI_API_KEY=\"ваш_openai_ключ\" \\"
    echo "  -e SERPER_API_KEY=\"ваш_serper_ключ\" \\"
    echo "  -e SCRAPINGBEE_API_KEY=\"ваш_scrapingbee_ключ\" \\"
    echo "  -e HUBSPOT_API_KEY=\"ваш_hubspot_ключ\" \\"
    echo "  -e HUBSPOT_BASE_URL=\"https://app.hubspot.com/contacts/ваш_portal_id/record/0-2/\" \\"
    echo "  -e DEBUG=\"false\" \\"
    echo "  --name $CONTAINER_NAME \\"
    echo "  -v /srv/company-canvas/output:/app/output \\"
    echo "  $FULL_IMAGE_NAME"
    echo ""
    read -p "Продолжить запуск без API ключей? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warning "Развертывание прервано. Установите переменные окружения и запустите снова."
        exit 1
    fi
fi

# Запускаем контейнер
if eval $DOCKER_CMD; then
    log_success "Контейнер запущен успешно"
else
    log_error "Ошибка запуска контейнера!"
    exit 1
fi

# 8. Проверка работы
log_info "\n8. Проверка работы..."
sleep 3

if docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}" | grep -q "$CONTAINER_NAME"; then
    log_success "Контейнер работает"
    
    # Показываем статус
    echo ""
    echo "Статус контейнера:"
    docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    
    # Показываем логи
    echo ""
    log_info "Последние логи контейнера:"
    docker logs --tail 10 $CONTAINER_NAME
    
    echo ""
    log_success "Развертывание завершено!"
    echo -e "${YELLOW}Приложение доступно по адресу: http://$(hostname -I | awk '{print $1}')${NC}"
    echo ""
    echo "Полезные команды:"
    echo "  Логи: docker logs -f $CONTAINER_NAME"
    echo "  Перезапуск: docker restart $CONTAINER_NAME"
    echo "  Остановка: docker stop $CONTAINER_NAME"
    
else
    log_error "Контейнер не запустился!"
    echo "Логи ошибок:"
    docker logs $CONTAINER_NAME
    exit 1
fi 