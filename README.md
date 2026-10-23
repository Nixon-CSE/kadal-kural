# Kadal Kural (கடல் குரல்) — B2B Pre-Dispatch Credit Firewall

**Zero-Screen Tamil/Tanglish Voice Credit Ledger & Pre-Dispatch Gatekeeper for High-Noise Wholesale Markets.**  
Built on **Gnani AI's Sovereign Artha Stack** (`Prisma v2.5` 8kHz Streaming STT + `Timbre v2.5` Streaming TTS) with a Pipecat-compatible Frame Pipeline.

---

## Architectural Highlights

1. **Deterministic Credit Firewall ("LLM/STT Extracts; Code Calculates"):**  
   Zero arithmetic is delegated to generative models. All running balances, credit-limit breach holds, and compensating undo transactions execute deterministically over an append-only WAL SQLite ledger.
2. **Prisma v2.5 Hybrid Tamil Numeral & Suffix Normalizer:**  
   Deterministically resolves hybrid Tamil-word + Arabic-digit tokens (e.g., `எழுநூற்றி 40` → `740`, `ஐநூற்றி 60` → `560`) and strips dative case suffixes (`-க்கு`, `-னுக்கு`) prior to bilingual phonetic matching.
3. **Strict 1,024-Byte / 64ms Ring-Buffer Audio Pacer:**  
   Enforces Gnani Prisma v2.5's binary WebSocket frame requirement (`1,024` bytes per frame at `8,000 Hz` 16-bit mono PCM) with mid-session `update_settings` word boosting and phonetic substitution maps.
4. **Pipecat Frame-Processor Pipeline & Sub-Millisecond Barge-In Flush:**  
   Stitches multi-trade single-breath utterances across VAD pauses (`MultiSegmentTradeAssembler`) and flushes active TTS audio buffers on `StartInterruptionFrame` in `< 1 ms`.
5. **Confidence Gate ($\tau = 0.82$):**  
   Routes low-confidence or ambiguous utterances to an explicit `PENDING_CLARIFICATION` queue—driving the **Silent Financial Error Rate** toward zero under 85dB+ market noise.

---

## Repository Structure (Hexagonal Architecture)

```text
kadal-kural/
├── pyproject.toml
├── requirements.txt
├── src/
│   └── kadal_kural/
│       ├── config.py                        # 12-Factor immutable settings
│       ├── data/catalog.json                # Bilingual (Tamil + Latin) B2B catalog seed
│       ├── domain/
│       │   ├── models.py                    # Frozen Pydantic domain entities & value objects
│       │   ├── normalizer.py                # Hybrid Tamil numeral & dative suffix normalizer
│       │   ├── matcher.py                   # Bilingual RapidFuzz matcher & multi-clause parser
│       │   └── service.py                   # Pre-Dispatch Credit Firewall & Confidence Gate
│       ├── infrastructure/
│       │   ├── persistence.py               # Thread-safe WAL SQLite append-only repository
│       │   ├── gnani_client.py              # 1,024-byte RingBuffer pacer, Prisma & Timbre WS
│       │   └── pipecat_pipeline.py          # Typed FrameProcessor pipeline & barge-in controller
│       └── api/                             # FastAPI WebSocket & REST gateway (Phase 5)
└── tests/                                   # Automated pytest verification suite              
