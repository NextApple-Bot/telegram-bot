.PHONY: help build up down logs shell clean

help:
	@echo "Доступные команды:"
	@echo "  make build  - собрать Docker образ"
	@echo "  make up     - запустить все сервисы"
	@echo "  make down   - остановить все сервисы"
	@echo "  make logs   - показать логи"
	@echo "  make shell  - открыть shell в контейнере бота"
	@echo "  make clean  - очистить всё"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "✅ Бот запущен. Логи: make logs"

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec bot /bin/bash

clean:
	docker-compose down -v
	docker system prune -f
