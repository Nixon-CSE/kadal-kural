# Security

## Reporting

Please report vulnerabilities privately through GitHub's **Report a vulnerability** (Security tab),
not in a public issue. Expect an acknowledgement within three working days.

## What runs where

| Surface | Who can reach it | Protection |
|---|---|---|
| Desk UI and API (`/`, `/api/v1/*`, `/ws/live-audio`) | The machine running it (localhost) | Host allow-list, cross-site request refusal, security headers, size limits |
| Phone channel (`POST /api/v1/phone-turn`) | The internet, through a tunnel | Shared secret, rate limit, body and transcript limits, path allow-list |
| Health check (`GET /healthz`) | The internet, through a tunnel | Read-only, reveals only whether a Gnani key is set |
| Gnani Prisma / Timbre | Outbound only, `wss://api.vachana.ai` | API key from the environment, never logged or sent to the browser |

## Threat model and controls

| Threat | Control | Where | Tests |
|---|---|---|---|
| A tunnel exposes every route (ledger reset, live audio that spends Gnani credits) | Proxied requests may reach only the phone channel and `/healthz`; others get 403, WebSockets close 1008 | `api/edge.py` | `tests/test_edge_guard.py` |
| Forged phone turns | Token in `X-Kadal-Token` or `Authorization: Bearer`, compared in constant time; unset token disables the endpoint (503) | `api/main.py` | `tests/test_phone_turn.py` |
| Token guessing, or abuse with a leaked token | Per-caller sliding-window limit (60/min by default), counted before the token check; 429 with `Retry-After` | `api/security.py` | `tests/test_security.py` |
| Another website in the user's browser POSTs to the desk (CSRF) or opens the live-audio socket (cross-site WebSocket hijacking) | Unsafe methods and WebSocket handshakes with a foreign `Origin`, `Origin: null` or `Sec-Fetch-Site: cross-site` are refused | `api/security.py` | `tests/test_security.py` |
| DNS rebinding: a hostile domain pointed at 127.0.0.1 | Direct requests must name an expected `Host` (localhost or `KADAL_ALLOWED_HOSTS`); others get 421 | `api/security.py` | `tests/test_security.py` |
| Script injection, clickjacking, MIME sniffing | Strict CSP (`script-src 'self'`, no inline script, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `no-referrer`; React escapes all text and no raw HTML is rendered | `api/security.py`, `web/` | `tests/test_security.py`, `tests/test_desk_ui.py` |
| Microphone access by embedded content | `Permissions-Policy: microphone=(self)`; camera, location, payment and USB off | `api/security.py` | `tests/test_security.py` |
| Memory or CPU exhaustion | Bodies capped per route (phone 32 KB, upload 10 MB, other 64 KB), counted while streaming so chunked bodies are capped too; transcripts capped at 500 characters; live frames capped at 64 KB; live sessions closed after 20 minutes; the rate limiter's memory is bounded | `api/security.py`, `api/main.py` | `tests/test_security.py` |
| SQL injection | Every query is parameterised | `infrastructure/persistence.py` | — |
| Tampering with the ledger | Append-only: an undo adds a reversing row; nothing is updated in place or deleted (except the demo reset, which is local-only) | `infrastructure/persistence.py` | `tests/test_kadal_kural.py` |
| Wrong money from a misheard number | The confidence gate holds or re-asks anything unsure; no AI model does arithmetic | `domain/service.py` | benchmark, `tests/` |
| Personal data | Synthetic buyers only; buyer contact numbers stay on the server and are non-dialable; mic capture for debugging is off by default | `data/catalog.json`, `api/main.py` | `tests/test_channels.py` |
| Secrets in the repository | `.env` is git-ignored; `.env.example` has placeholders only; the history holds no keys | `.gitignore` | — |
| Vulnerable dependencies | Floors pinned to patched versions; `pip-audit` and `npm audit --omit=dev` in CI; Dependabot weekly; CodeQL on every push | `pyproject.toml`, `.github/` | CI |
| Container escape impact | Runs as an unprivileged user (uid 10001); the data volume is the only writable path it needs | `Dockerfile` | CI smoke test checks the user |

## Operating notes

- **Rotate the phone token** after any demo where it was shown or shared: set a new
  `KADAL_PHONE_WEBHOOK_TOKEN` in `.env` and the same value in the Agent Builder integration.
  Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- **Publish the container on localhost only** (`-p 127.0.0.1:8000:8000`, as `make docker` does).
  To use the desk from another device, add its address to `KADAL_ALLOWED_HOSTS`; the desk has no
  user accounts, so anyone who can reach it can use it.
- **Quick tunnels** (`trycloudflare.com`) get a new URL on every start and are for demos. For a fixed
  address use a named Cloudflare tunnel; the edge guard works the same behind either.
- The phone channel's words come from Agent Builder's speech recognition and LLM; the firewall
  re-validates every field, but the transcript is treated as untrusted input throughout.
