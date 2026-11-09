.PHONY: install run test lint typecheck check bench docker tunnel

install:      ## venv deps incl. dev tools
	pip install -e ".[dev]"

run:          ## local server on :8000 (reads .env)
	uvicorn kadal_kural.api.main:app --port 8000

test:
	pytest -q

lint:
	ruff check src tests benchmark scripts

typecheck:
	mypy src

check: lint typecheck test   ## what CI runs

bench:        ## re-score cached Prisma transcripts, no API calls
	python benchmark/run_eval.py --analyze-only

docker:
	docker build -t kadal-kural . && docker run --rm -p 8000:8000 --env-file .env kadal-kural

tunnel:       ## public HTTPS URL for the Gnani Agent Builder phone action
	cloudflared tunnel --url http://localhost:8000
