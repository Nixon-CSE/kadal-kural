# Phone channel: Gnani Agent Builder → Kadal Kural firewall

The browser client runs our own audio pipeline (paced 8 kHz Prisma v2.5 stream, assembler,
barge-in, Timbre v2.5). The phone channel puts **Gnani Agent Builder** in front of the *same*
deterministic firewall: Agent Builder handles dialling, telephony audio, speech recognition and
speech output, and forwards each caller turn to `POST /api/v1/phone-turn`. The firewall books,
holds or asks to repeat, and the agent speaks the returned `reply_text`.

```
trader's phone ⇄ Gnani Agent Builder (call, STT, TTS)
                     │ On-Call custom action
                     │ POST /api/v1/phone-turn  transcript={{transcript}}
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
| Request | `transcript` (aliases `user_text`, `text`) as a JSON body, JSON string, form fields, plain text, query parameters or a header; optional `conversation_id`. A missing or unfilled `{{placeholder}}` transcript returns 200 with the clarification prompt and writes nothing |
| Response | `reply_text` (Tamil, always non-empty: each decision's reply, or the clarification prompt), `booked_count`, `held_count`, `statuses`, `conversation_id`, `transcript_received` |
| Logging | One `PHONE` line per request: content type, body size, field names, header names (never the token), and the decision |
| Side effects | One ledger row per parsed trade, visible live on the dashboard (`/`) with what was heard |
| Exposure | Behind a proxy or tunnel, this and `/healthz` are the only reachable routes (`KADAL_PUBLIC_EDGE_GUARD`, on by default) |

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
   `https://….trycloudflare.com` URL. Through it, only `/api/v1/phone-turn` (token required) and
   `/healthz` answer: the edge guard (`api/edge.py`) returns 403 for every other route and closes
   the live-audio socket for any request a proxy forwarded, so the ledger, reset and Gnani credits
   are not exposed. Verified through a live quick tunnel on 2026-11-09.
3. **Whitelist your phone** in the Agent Builder console: *Phone Numbers → Whitelisted → Add
   Number*, then confirm the OTP (docs: `A04_Whitelisting`). No other paperwork is documented.
4. **Create the agent** at **https://app.gnani.ai/agents/** (*Manage Agents → Create Agent*; if
   the first-run wizard insists on a template, pick any and replace its text entirely).
   - **Greeting:** `வணக்கம், கடல் குரல் ஆர்டர் லைன். வாங்குபவர் பெயர், அளவு, மீன் வகை, ரேட் சொல்லுங்க.`
   - **Instructions:** the full prompt in [phone_agent_prompt.md](phone_agent_prompt.md).
   - **Publish it.** Edits are saved as a *Draft*; calls run the published version. *Validate →
     Save as version →* make that version active, then *Save*. (Symptom when skipped: calls still
     use the template's greeting.)
5. **Configuration** (values used for the verified call):
   - *Agent Details:* language Tamil plus English (IN); region Asia, IST.
   - *Transcriber:* Gnani, Balanced; interruptions on at 0.8 s; Smart Pause on; initial-message
     interruption on; noise filtering 70; inverse text normalisation on; segmentation silence
     1.2 s; custom vocabulary (single words only): `செந்திலுக்கு, குமரனுக்கு, செந்தில், குமரன்,
     சீஃபுட்ஸ், ஸ்டோர்ஸ், வஞ்சரம், எக்ஸ்போர்ட், டைகர், பிரான், இறால், கிலோ, பாக்ஸ், ரேட்டு,
     கேன்சல், Senthil, Kumaran, Vanjaram, Tiger, Prawn, kg, box, rate, cancel`.
   - *LLM:* Gnani Evon, temperature 0.1, max tokens 500, no knowledge base.
   - *Voice persona:* a Tamil Timbre voice, rate 0.9. FAQ answers, post-call trigger: off.
6. **Integration** (*Actions → + Action → Integration → Add Custom Integration*): name
   `kadal_kural`, `POST`, URL `https://<tunnel>/api/v1/phone-turn`, auth header `X-Kadal-Token` =
   the secret.
7. **Action** `book_trade`, trigger **On call**:
   - *Before API Call Variables:* `transcript` (String), prompt: "The caller's latest order
     sentence, copied exactly as spoken, in Tamil script … Do not translate, summarise, correct,
     round or calculate anything."
   - *After API Call Variables:* `reply_text` (String): "the reply_text field of the response,
     unchanged".
   - *Headers* table: only `Content-Type: application/json`. *Body* table: `transcript` →
     `{{transcript}}`. The three tables share one panel; the underlined tab is the one being
     edited.
   - *Speak During Action:* `ஒரு நொடி…`; timeout 5 s.
   - *Test API Request* sends **no body** (expect 200, `transcript_received: false`); only a real
     call fills `{{transcript}}`.
8. **Whitelist and call:** *Phone Numbers → Whitelisted → Add Number* (OTP), then *Agent → Test →
   Trigger Agent Call*, or the Platform API:
   ```bash
   curl -X POST "https://api.inya.ai/platform/v1/agents/$BOT_ID/trigger_call?environment=development" \
     -H "x-api-key: $INYA_API_KEY" -H 'Content-Type: application/json' \
     -d '{"phone": "98XXXXXXXX", "countryCode": "+91", "name": "Demo trader"}'
   ```

## Verified on a live call (2026-11-09)

Caller said *குமரனுக்கு 20 கிலோ டைகர் பிரான் 500 ரேட்டு*. The agent fired the action twice:

| Time | What arrived | Decision |
|---|---|---|
| 11:50:24 | `குமரனுக்கு இருபது கிலோ டைகர் பிரான்` (before the rate was spoken) | `PENDING_CLARIFICATION`: no rate, so held and asked again |
| 11:50:26 | `குமரனுக்கு இருபது கிலோ டைகர் பிரான் ஐநூறு ரேட்` | `BOOKED` ₹10,000: Tamil number words normalised (இருபது → 20, ஐநூறு → 500) |

The agent spoke the firewall's Tamil `reply_text`, and both rows appeared on the desk with the
heard text.

What the integration taught us, and how the endpoint handles it:

- `{{user_text}}` is **not** filled for an On-Call action body: requests arrived as `{}`. A
  *Before API Call Variable* (`transcript`) is filled.
- The filled value arrived as a **query parameter** with an empty JSON body, and a field placed in
  the Headers table arrives as a header. The endpoint accepts every form, so the console layout
  does not matter.
- Every empty or partial turn was answered with "please repeat" and **nothing was booked from a
  guess** (fail closed).

## Known limits of this path

- **The agent's LLM fills `transcript`.** It is instructed to copy the caller's words verbatim,
  and the firewall re-validates everything (catalog match, per-unit bands, credit), but in
  principle it could reword. The desk's *Heard* column shows exactly what arrived.
- **The agent may fire early** (mid-sentence). The firewall holds the incomplete order; raising
  the segmentation silence or Smart Pause reduces it.
- **Different STT.** Calls use Agent Builder's speech recognition, not our tuned Prisma stream,
  so the noise benchmark in `benchmark/REPORT.md` does not describe this path.
- **Barge-in and the assembler** are the agent platform's on this path, not ours.
- **Quick tunnels change URL on restart**; update the integration URL, or use a named tunnel.

## Next step: our own pipeline on the phone

Twilio (or Exotel) Media Streams → `/ws/live-audio`-style socket, converting 8 kHz μ-law to the
16-bit PCM our pacer already sends to Prisma. That keeps the benchmarked pipeline end to end on
a real call. It needs a telephony number (regulatory paperwork for an Indian DID) and μ-law
transcoding, which is why the Agent Builder route came first.
