## What changes

<!-- One or two sentences: what the desk, phone line or ledger now does differently. -->

## How it was checked

- [ ] `make check` passes (ruff, mypy --strict, pytest)
- [ ] `make web` rebuilt the desk, if anything under `web/` changed
- [ ] New behaviour has a test; money paths (normalizer, matcher, firewall, ledger) have one that fails without the change
- [ ] No secrets, real phone numbers or real customer data
