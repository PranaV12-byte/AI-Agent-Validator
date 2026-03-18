.PHONY: dev db migrate test

db:
	docker compose -f docker-compose.dev.yml up -d

migrate:
	cd backend && alembic upgrade head

dev:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	cd backend && pytest -v

celery:
	cd backend && celery -A app.worker worker --loglevel=info

frontend:
	cd frontend && npm run dev
