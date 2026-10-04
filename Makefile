up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

burst:
	./scripts/burst.sh $${BASE_URL:-http://localhost:8000} $${REQUESTS:-500} $${WORKERS:-100}

health:
	curl -fsS $${BASE_URL:-http://localhost:8000}/health/live && echo
	curl -fsS $${BASE_URL:-http://localhost:8000}/health/ready && echo

metrics:
	curl -fsS $${BASE_URL:-http://localhost:8000}/metrics
