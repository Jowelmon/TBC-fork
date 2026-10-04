.PHONY: help install test demo serve reset docker-up docker-down lint clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime + test dependencies
	pip install -r requirements.txt
test:  ## Run the repository unit test suite
	PYTHONPATH=. python -m pytest -q tests

test:  ## Run the full test suite
	PYTHONPATH=. python3 -m pytest tests/ -q

demo:  ## Run the end-to-end console demo
	PYTHONPATH=. python3 -m technical_services_pill.demo

serve:  ## Start the app with the UI on :8000 (open http://localhost:8000/ui)
	PYTHONPATH=. uvicorn frontend.serve:app --port 8000

reset:  ## Wipe persisted state (data/tbc.sqlite) for a clean demo
	rm -f data/tbc.sqlite

docker-up:  ## Build and start the API container
	docker compose up --build -d
	@echo "API at http://localhost:8000  (docs at /docs)"

docker-down:  ## Stop and remove containers
	docker compose down

docker-demo:  ## Run the demo inside a container
	docker compose run --rm demo

lint:  ## Quick syntax check on all modules
	python3 -m py_compile technical_services_pill/*.py tests/*.py

clean:  ## Remove bytecode caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true