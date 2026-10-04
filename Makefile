.PHONY: help test demo serve docker-up docker-down lint clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test:  ## Run the repository unit test suite
	PYTHONPATH=. python -m pytest -q tests

demo:  ## Run the 3-case end-to-end demo
	PYTHONPATH=. python3.11 -m technical_services_pill.demo

serve:  ## Start the FastAPI API server locally on :8000
	PYTHONPATH=. uvicorn technical_services_pill.app:app --reload --port 8000

docker-up:  ## Build and start the API container
	docker compose up --build -d
	@echo "API at http://localhost:8000  (docs at /docs)"

docker-down:  ## Stop and remove containers
	docker compose down

docker-demo:  ## Run the demo inside a container
	docker compose run --rm demo

lint:  ## Quick syntax check on all modules
	python3.11 -m py_compile technical_services_pill/*.py tests/*.py

clean:  ## Remove bytecode caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true