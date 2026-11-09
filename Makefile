.PHONY: install run test lint typecheck check audit bench docker tunnel web web-dev

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

audit:        ## known vulnerabilities in Python and production npm dependencies
	pip-audit --skip-editable
	cd web && npm audit --omit=dev

bench:        ## re-score cached Prisma transcripts, no API calls
	python benchmark/run_eval.py --analyze-only

docker:
	docker build -t kadal-kural . && docker run --rm -p 127.0.0.1:8000:8000 --env-file .env kadal-kural

tunnel:       ## public HTTPS URL for the Gnani Agent Builder phone action
	cloudflared tunnel --url http://localhost:8000

web:          ## build the React desk into src/kadal_kural/api/static
	cd web && npm ci && npm run build

web-dev:      ## desk dev server on :5173 (proxies the API on :8000)
	cd web && npm run dev
