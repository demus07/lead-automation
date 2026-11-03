.PHONY: dev-infra api worker beat test test-live migrate up down logs backup restore

dev-infra:            ## start postgres + redis for local development
	docker compose up -d postgres redis
migrate:
	cd backend && .venv/bin/alembic upgrade head
api:
	cd backend && .venv/bin/uvicorn app.main:app --port $${API_PORT:-8100} --reload
worker:
	cd backend && .venv/bin/celery -A app.worker worker -Q default,research,ai,email --loglevel=INFO --pool=threads --concurrency=4  # threads: macOS-safe for dev
beat:
	cd backend && .venv/bin/celery -A app.worker beat --loglevel=INFO
test:                 ## automated suite (mocked providers, CI-safe)
	cd backend && .venv/bin/pytest
test-live:            ## tests that hit real public sources
	cd backend && .venv/bin/pytest -m live
up:                   ## full stack in Docker
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f api worker beat
backup:
	docker compose --profile backup run --rm backup
restore:
	./scripts/restore.sh $(FILE)
