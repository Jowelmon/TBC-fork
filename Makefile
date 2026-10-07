.PHONY: help install test eval demo serve reset docker-up docker-down docker-demo lint clean

# Use the project venv when it exists, so `make test` works without activating it.
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Create .venv and install runtime + test dependencies
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

test:  ## Run the repository unit test suite
	PYTHONPATH=. $(PY) -m pytest -q tests

eval:  ## Run EVAL-01..12 acceptance evals and print a pass/fail table
	PYTHONPATH=. $(PY) tests/evals/run_evals.py

demo:  ## Run the end-to-end console demo
	PYTHONPATH=. $(PY) -m technical_services_pill.demo

serve:  ## Start the app with the UI on :8000 (open http://localhost:8000/ui)
	PYTHONPATH=. $(PY) -m uvicorn frontend.serve:app --port 8000

reset:  ## Stop a running server, then remove all demo state (cases, proposals, KB); restart with make serve
	@# A server shutting down saves its state; let it finish first, or the
	@# snapshot reappears right after it is deleted.
	@pkill -f "uvicorn frontend.serve" 2>/dev/null && echo "stopped running server" || true
	@while pgrep -f "uvicorn frontend.serve" >/dev/null; do sleep 1; done
	rm -f data/tbc.sqlite technical_services_pill.sqlite3

docker-up:  ## Build and start the API container
	docker compose up --build -d
	@echo "API at http://localhost:8000  (docs at /docs)"

docker-down:  ## Stop and remove containers
	docker compose down

docker-demo:  ## Run the demo inside a container
	docker compose run --rm demo

lint:  ## Quick syntax check on all modules
	$(PY) -m py_compile technical_services_pill/*.py frontend/*.py tests/*.py tests/evals/*.py

clean:  ## Remove bytecode caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
