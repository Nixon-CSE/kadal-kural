# Kadal Kural (கடல் குரல்) — B2B Pre-Dispatch Credit Firewall

**Zero-Screen Tamil/Tanglish Voice Credit Ledger & Pre-Dispatch Gatekeeper for High-Noise Wholesale Markets.**
Built on **Gnani AI Sovereign Artha Stack** (`Prisma v2.5` 8kHz Streaming STT + `Timbre v2.5` Streaming TTS) with a Pipecat-compatible Frame Pipeline.

## Architectural Highlights

1. **Deterministic Credit Firewall ("STT Extracts; Code Calculates"):** Zero arithmetic is delegated to LLMs. All running balances, credit-limit breach holds, and compensating undo transactions execute deterministically over an append-only WAL SQLite ledger.
2. **Prisma v2.5 Hybrid Tamil Numeral & Suffix Normalizer:** Deterministically resolves hybrid Tamil-word + digit tokens (`எழுநூற்றி 40` -> `740`, `ஐநூற்றி 60` -> `560`) and strips dative suffixes (`-க்கு`, `-னுக்கு`) prior to bilingual phonetic matching.
3. **Strict 1,024-Byte / 64ms Ring-Buffer Audio Pacer:** Enforces Gnani Prisma v2.5 binary WebSocket frame rules (`1,024` bytes per frame at `8,000 Hz` 16-bit mono PCM) with mid-session `update_settings` word boosting and phonetic substitution maps.
4. **Pipecat Frame-Processor Pipeline & Sub-Millisecond Barge-In Flush:** Stitches multi-trade single-breath utterances across VAD pauses (`MultiSegmentTradeAssembler`) and flushes active TTS audio buffers on `StartInterruptionFrame` in `< 1 ms`.
5. **Confidence Gate (tau = 0.82):** Routes low-confidence or ambiguous utterances to an explicit `PENDING_CLARIFICATION` queue—driving the **Silent Financial Error Rate** toward zero under 85dB+ market noise.
