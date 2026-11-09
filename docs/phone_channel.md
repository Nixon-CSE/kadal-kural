# Phone channel: Gnani Agent Builder → Kadal Kural firewall

The browser client runs our own audio pipeline (paced 8 kHz Prisma v2.5 stream, assembler,
barge-in, Timbre v2.5). The phone channel puts **Gnani Agent Builder** in front of the *same*
deterministic firewall: Agent Builder handles dialling, telephony audio, speech recognition and
speech output, and forwards each caller turn to `POST /api/v1/phone-turn`. The firewall books,
holds or asks to repeat, and the agent speaks the returned `reply_text`.

```
trader's phone ⇄ Gnani Agent Builder (call, STT, TTS)
                     │ On-Call custom action
                     │ POST /api/v1/phone-turn  {"transcript": "{{user_text}}"}
                     │ X-Kadal-Token: <secret>
                     ▼
        HTTPS tunnel → FastAPI → normalizer → matcher → confidence gate → credit check → SQLite ledger
                     ◀ {"reply_text": "...", "booked_count": 1, "held_count": 0, "statuses": ["BOOKED"]}
```

The design rule holds on this path too: **the agent's LLM never extracts or computes an
amount.** It forwards the caller's words; all parsing, arithmetic and credit decisions stay in
`domain/`.

## Endpoint contract

`POST /api/v1/phone-turn`

| | |
|---|---|
| Auth | `X-Kadal-Token: <KADAL_PHONE_WEBHOOK_TOKEN>` or `Authorization: Bearer <token>`. Compared in constant time. Unset token → `503` (endpoint disabled); wrong/missing → `401`, nothing written. |
| Body | `transcript` (aliases: `user_text`, `text`), optional `conversation_id`, `caller_name` |
| Response | `reply_text` (Tamil, always non-empty: each decision's reply, or the clarification prompt), `booked_count`, `held_count`, `statuses`, `conversation_id` |
| Side effects | One ledger row per parsed trade, visible live on the dashboard (`/`) with what was heard |

```bash
curl -s localhost:8000/api/v1/phone-turn \
  -H "X-Kadal-Token: $KADAL_PHONE_WEBHOOK_TOKEN" -H 'Content-Type: application/json' \
  -d '{"transcript": "குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு"}'
```

Tests: `tests/test_phone_turn.py`.

## Setup (about 30 minutes)

1. **Secret and server**
   ```bash
   echo "KADAL_PHONE_WEBHOOK_TOKEN=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
   make run
   ```
2. **Public HTTPS URL** (`brew install cloudflared`, then `make tunnel`). Copy the
   `https://….trycloudflare.com` URL. A quick tunnel exposes the whole app, including
   `/api/v1/reset`; use it for demos only and stop it afterwards.
3. **Whitelist your phone** in the Agent Builder console: *Phone Numbers → Whitelisted → Add
   Number*, then confirm the OTP (docs: `A04_Whitelisting`). No other paperwork is documented.
4. **Create the agent** (*Manage Agents → Create*): language Tamil (add English for Tanglish),
   and this system prompt:
   > You are the order line of a fish wholesale dispatch desk. The caller states orders in Tamil
   > or Tanglish: buyer, quantity, unit, product and rate. For **every** caller turn that
   > contains an order, an undo/cancel request, or a correction, call the `book_trade` action
   > with the caller's exact words. Never compute amounts, never change numbers, never confirm
   > an order yourself. Speak the action's `reply_text` exactly as returned. If the caller says
   > nothing about an order, ask them to state the order.
5. **Integration** (*Integrations → Custom*, docs `D05_Custom`): name `kadal_kural`, method
   `POST`, URL `https://<tunnel>/api/v1/phone-turn`, auth key `X-Kadal-Token`, value = the
   secret.
6. **Action** (*Actions*, docs `M04_Actions`): name `book_trade`, trigger **On-Call**,
   description "Call for every order, cancel or correction the caller says", body
   `{"transcript": "{{user_text}}"}`, *Speak During Action* `ஒரு நொடி…`, timeout 5 s,
   After-API variable `reply_text`.
7. **Test call**: *Manage Agents → agent → Test → trigger call* to the whitelisted number, or
   via the Platform API:
   ```bash
   curl -X POST "https://api.inya.ai/platform/v1/agents/$BOT_ID/trigger_call?environment=development" \
     -H "x-api-key: $INYA_API_KEY" -H 'Content-Type: application/json' \
     -d '{"phone": "98XXXXXXXX", "countryCode": "+91", "name": "Demo trader"}'
   ```
   Check *More Options → View Logs* (docs `E04_Action_Logs`) for each request and response.

## Open points (verify on the first call)

- **Speaking the response.** Gnani's docs mark storing API responses in variables as "Coming
  Soon". If `reply_text` cannot be spoken, trades still book or hold correctly and appear live on
  the dashboard, but the caller does not hear the amount or the credit-hold alert.
- **`{{user_text}}` contents** must be the caller's latest words, not a summary. The ledger's
  *Heard* column shows exactly what arrived.
- **Different STT.** Calls use Agent Builder's speech recognition, not our tuned Prisma stream
  (word boosting, VAD settings), so the noise benchmark in `benchmark/REPORT.md` does not
  describe this path.
- **Barge-in and the assembler** are the agent platform's on this path, not ours.

## Next step: our own pipeline on the phone

Twilio (or Exotel) Media Streams → `/ws/live-audio`-style socket, converting 8 kHz μ-law to the
16-bit PCM our pacer already sends to Prisma. That keeps the benchmarked pipeline end to end on
a real call. It needs a telephony number (regulatory paperwork for an Indian DID) and μ-law
transcoding, which is why the Agent Builder route came first.
