.PHONY: help install test eval demo serve reset docker-up docker-down lint clean

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime + test dependencies
	pip install -r requirements.txt
test:  ## Run the repository unit test suite
	PYTHONPATH=. python -m pytest -q tests

eval:  ## Run EVAL-01..12 acceptance evals and print a pass/fail table
	PYTHONPATH=. python3 tests/evals/run_evals.py

demo:  ## Run the end-to-end console demo
	PYTHONPATH=. python3 -m technical_services_pill.demo

serve:  ## Start the app with the UI on :8000 (open http://localhost:8000/ui)
	PYTHONPATH=. uvicorn frontend.serve:app --port 8000

reset:  ## Remove all demo state (cases, proposals, KB); the UI re-seeds demo cases on next load
	rm -f data/tbc.sqlite technical_services_pill.sqlite3

docker-up:  ## Build and start the API container
	docker compose up --build -d
	@echo "API at http://localhost:8000  (docs at /docs)"

docker-down:  ## Stop and remove containers
	docker compose down

docker-demo:  ## Run the demo inside a container
	docker compose run --rm demo

lint:  ## Quick syntax check on all modules
	python3 -m py_compile technical_services_pill/*.py frontend/*.py tests/*.py tests/evals/*.py

clean:  ## Remove bytecode caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true