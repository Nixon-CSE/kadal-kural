# Contributing

## Set up

Python 3.11+ and Node 20.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # a Gnani API key is needed only for live speech
make run                  # http://localhost:8000
make web-dev              # desk with hot reload on :5173 (optional)
```

## Before you open a pull request

```bash
make check    # ruff, mypy --strict, pytest: what CI runs
make audit    # known vulnerabilities in dependencies
make web      # if you changed anything under web/: rebuild the committed desk bundle
```

## Rules that keep the money right

- **No model does arithmetic.** Amounts, balances and credit checks are deterministic code in
  `src/kadal_kural/domain/`. Speech recognition supplies words, nothing else.
- **The ledger is append-only.** Never update or delete a row; corrections and undo add rows.
- **Unsure means ask.** A change that books an order the confidence gate would have held needs a
  benchmark run (`make bench`) and a written reason in the pull request.
- **Every fix to the normalizer or matcher comes with the transcript that broke it** as a test,
  copied verbatim from a live Prisma run or `benchmark/results.csv`.
- **Synthetic data only.** No real phone numbers, account numbers or recorded customer calls.

## Commits

Conventional style: `feat(ledger): …`, `fix(normalizer): …`, `docs: …`, `ci: …`. Say why in the body
when it is not obvious from the diff.

Security issues: see [SECURITY.md](SECURITY.md), not a public issue.
