.PHONY: up down logs ps build test test-unit lint clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f gateway

ps:
	docker compose ps

build:
	docker compose build

test: test-unit

test-unit:
	python -m pytest tests/unit/ -v

lint:
	ruff check gateway/ mock_llm/ tests/

clean:
	docker compose down -v --rmi local
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
