.PHONY: help test migrate clean deploy rollback logs

help:
	@echo "Доступные команды:"
	@echo "  make test        - запустить тесты с покрытием"
	@echo "  make migrate     - применить миграции Alembic"
	@echo "  make clean       - очистить временные файлы и кэш"
	@echo "  make deploy      - отправить изменения в main (запушит)"
	@echo "  make rollback    - откатить последний коммит (ОПАСНО!)"
	@echo "  make logs        - показать логи бота (docker-compose)"

test:
	pytest tests/ -v --cov=bot --cov=web_admin --cov-report=html

migrate:
	alembic upgrade head

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage

deploy:
	git push origin main

rollback:
	@echo "⚠️ ВНИМАНИЕ: Откат последнего коммита с принудительным пушем!"
	@read -p "Вы уверены? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		git reset --hard HEAD~1; \
		git push --force; \
		echo "✅ Откат выполнен. Render пересоберёт образ."; \
	else \
		echo "❌ Откат отменён."; \
	fi

logs:
	docker-compose logs -f bot
